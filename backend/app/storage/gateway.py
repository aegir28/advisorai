"""Signed-URL gateway for the private `case-documents` bucket.

Clients never touch storage directly (see the storage migration). The backend signs short-lived URLs
with the service-role key, which exists only in the backend environment.

* A `StoragePath` can only be built from owner, case and document IDs, which fixes the blueprint's
  `owner/case/document` layout and rules out path traversal by construction.
* A `SignedUrl` redacts itself in `repr`, `str` and logs. The URL is only available through
  `.reveal()`, at the single point where it is handed to the caller.
* Download URLs live for at most 5 minutes, whatever is asked for.
"""

import uuid
from dataclasses import dataclass
from typing import Protocol

import httpx

from app.core.config import MAX_SIGNED_URL_TTL_SECONDS, Settings


class StorageError(Exception):
    """A storage call failed. The message never contains a URL, token or key."""


class ObjectNotFoundError(StorageError):
    """The object does not exist (for an upload: the client never sent the file)."""


class ObjectTooLargeError(StorageError):
    """The object is bigger than the limit the caller allowed."""


@dataclass(frozen=True, slots=True)
class StoragePath:
    owner_user_id: uuid.UUID
    case_id: uuid.UUID
    document_id: uuid.UUID

    def __str__(self) -> str:
        return f"{self.owner_user_id}/{self.case_id}/{self.document_id}"


class SignedUrl:
    """A bearer capability. Treat like a password: it is never logged or included in an audit row."""

    __slots__ = ("_url", "expires_in")

    def __init__(self, url: str, expires_in: int) -> None:
        self._url = url
        self.expires_in = expires_in

    def reveal(self) -> str:
        return self._url

    def __repr__(self) -> str:
        return f"SignedUrl(<redacted>, expires_in={self.expires_in})"

    __str__ = __repr__


class StorageGateway(Protocol):
    async def create_download_url(self, path: StoragePath) -> SignedUrl: ...

    async def create_upload_url(self, path: StoragePath) -> SignedUrl: ...

    async def delete_objects(self, paths: list[StoragePath]) -> None: ...

    async def read_object(self, path: StoragePath, *, max_bytes: int) -> bytes:
        """The object's bytes, for server-side validation. Raises `ObjectNotFoundError` or
        `ObjectTooLargeError`. Never returns more than `max_bytes`."""
        ...


class SupabaseStorageGateway:
    def __init__(self, settings: Settings, http: httpx.AsyncClient) -> None:
        if settings.supabase_url is None or settings.supabase_service_role_key is None:
            raise ValueError("storage requires supabase_url and supabase_service_role_key")
        self._base = f"{settings.supabase_url.rstrip('/')}/storage/v1"
        self._bucket = settings.storage_bucket
        self._ttl = min(settings.signed_url_ttl_seconds, MAX_SIGNED_URL_TTL_SECONDS)
        key = settings.supabase_service_role_key.get_secret_value()
        self._headers = {"Authorization": f"Bearer {key}", "apikey": key}
        self._http = http

    async def _call(self, method: str, url: str, **kwargs: object) -> object:
        try:
            response = await self._http.request(method, url, headers=self._headers, timeout=10.0, **kwargs)  # type: ignore[arg-type]
            response.raise_for_status()
            body = response.json() if response.content else {}
        except httpx.HTTPStatusError as exc:
            # Status code only: the request URL can contain a token, the body can echo the path.
            raise StorageError(f"storage request failed with status {exc.response.status_code}") from None
        except (httpx.HTTPError, ValueError) as exc:
            raise StorageError(f"storage request failed ({type(exc).__name__})") from None
        return body

    async def _call_for_object(self, method: str, url: str, **kwargs: object) -> dict[str, object]:
        body = await self._call(method, url, **kwargs)
        if not isinstance(body, dict):
            raise StorageError("storage returned an unexpected response")
        return body

    async def create_download_url(self, path: StoragePath) -> SignedUrl:
        body = await self._call_for_object(
            "POST", f"{self._base}/object/sign/{self._bucket}/{path}", json={"expiresIn": self._ttl}
        )
        relative = body.get("signedURL")
        if not isinstance(relative, str):
            raise StorageError("storage returned an unexpected response")
        return SignedUrl(f"{self._base}{relative}", self._ttl)

    async def create_upload_url(self, path: StoragePath) -> SignedUrl:
        body = await self._call_for_object("POST", f"{self._base}/object/upload/sign/{self._bucket}/{path}")
        relative = body.get("url")
        if not isinstance(relative, str):
            raise StorageError("storage returned an unexpected response")
        return SignedUrl(f"{self._base}{relative}", self._ttl)

    async def delete_objects(self, paths: list[StoragePath]) -> None:
        if not paths:
            return
        await self._call(
            "DELETE", f"{self._base}/object/{self._bucket}", json={"prefixes": [str(p) for p in paths]}
        )

    async def read_object(self, path: StoragePath, *, max_bytes: int) -> bytes:
        url = f"{self._base}/object/authenticated/{self._bucket}/{path}"
        chunks: list[bytes] = []
        received = 0
        try:
            async with self._http.stream("GET", url, headers=self._headers, timeout=30.0) as response:
                if response.status_code in (400, 404):
                    # Storage answers a missing object with 400 or 404 depending on the version.
                    raise ObjectNotFoundError("object not found")
                response.raise_for_status()
                async for chunk in response.aiter_bytes():
                    received += len(chunk)
                    if received > max_bytes:
                        raise ObjectTooLargeError("object is larger than allowed")
                    chunks.append(chunk)
        except StorageError:
            raise
        except httpx.HTTPStatusError as exc:
            raise StorageError(f"storage request failed with status {exc.response.status_code}") from None
        except httpx.HTTPError as exc:
            raise StorageError(f"storage request failed ({type(exc).__name__})") from None
        return b"".join(chunks)
