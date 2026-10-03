"""/cases/{id}/documents: the document library and the secure two-step upload."""

import uuid
from typing import Any

from fastapi import APIRouter, Request, Response, status

from app.api.dependencies import DocumentServiceDep, client_ip
from app.auth.dependencies import CurrentUserDep
from app.schemas.case_api import DocumentItem, UploadUrlRequest, UploadUrlResponse

router = APIRouter(prefix="/cases/{case_id}/documents", tags=["documents"])

_AUTH: dict[int | str, dict[str, Any]] = {401: {"description": "Missing, invalid or expired token."}}
_NOT_FOUND: dict[int | str, dict[str, Any]] = {
    404: {"description": "No such case or document for this account."}
}


@router.get(
    "",
    response_model=list[DocumentItem],
    response_model_exclude_none=True,
    summary="The case's document library",
    operation_id="getDocuments",
    responses=_AUTH | _NOT_FOUND,
)
async def list_documents(
    case_id: uuid.UUID, user: CurrentUserDep, documents: DocumentServiceDep
) -> list[DocumentItem]:
    return await documents.list(user, case_id)


@router.post(
    "/upload-url",
    response_model=UploadUrlResponse,
    summary="Get a short-lived signed URL to upload one file straight to private storage",
    operation_id="createUploadUrl",
    responses=_AUTH | _NOT_FOUND | {409: {"description": "Document limit reached."}},
)
async def create_upload_url(
    case_id: uuid.UUID, body: UploadUrlRequest, user: CurrentUserDep, documents: DocumentServiceDep
) -> UploadUrlResponse:
    return await documents.create_upload(user, case_id, body)


@router.post(
    "/{document_id}/complete",
    response_model=DocumentItem,
    response_model_exclude_none=True,
    summary="Register the finished upload and validate the file (type, size, hash, pages)",
    operation_id="completeUpload",
    responses=_AUTH | _NOT_FOUND | {409: {"description": "The file has not been uploaded yet."}},
)
async def complete_upload(
    case_id: uuid.UUID,
    document_id: uuid.UUID,
    request: Request,
    user: CurrentUserDep,
    documents: DocumentServiceDep,
) -> DocumentItem:
    return await documents.complete_upload(user, case_id, document_id, client_ip=client_ip(request))


@router.delete(
    "/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove one document and its file",
    operation_id="removeDocument",
    responses=_AUTH | _NOT_FOUND,
)
async def remove_document(
    case_id: uuid.UUID,
    document_id: uuid.UUID,
    request: Request,
    user: CurrentUserDep,
    documents: DocumentServiceDep,
) -> Response:
    await documents.remove(user, case_id, document_id, client_ip=client_ip(request))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
