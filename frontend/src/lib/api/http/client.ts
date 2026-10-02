import { ErrorEnvelopeSchema } from "@/domain/schemas";

export const API_PREFIX = "/api/v1";
export const REQUEST_ID_HEADER = "X-Request-ID";

/**
 * A failed API call. Carries the backend's error envelope (ADR 0002) when there was one, plus the
 * request ID so a person (or support) can quote it. `status` is 0 when no response arrived.
 */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly requestId: string,
    readonly details: Record<string, unknown> = {},
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/** Thrown by `httpApi` methods whose backend endpoint does not exist yet. */
export class ApiNotAvailableError extends Error {
  constructor(readonly method: string) {
    super(`${method}() is not available from the backend yet.`);
    this.name = "ApiNotAvailableError";
  }
}

export interface HttpClientOptions {
  baseUrl: string;
  fetchImpl?: typeof fetch;
  newRequestId?: () => string;
}

export interface RequestOptions {
  body?: unknown;
  signal?: AbortSignal;
}

export interface HttpClient {
  /** Returns the parsed JSON body (`undefined` for 204). Never validates the shape: callers decode. */
  request(method: string, path: string, options?: RequestOptions): Promise<unknown>;
}

export function defaultRequestId(): string {
  return `req_${crypto.randomUUID().replaceAll("-", "")}`;
}

export function createHttpClient({ baseUrl, fetchImpl, newRequestId = defaultRequestId }: HttpClientOptions): HttpClient {
  const root = baseUrl.replace(/\/+$/, "");

  return {
    async request(method, path, { body, signal } = {}) {
      const sentRequestId = newRequestId();
      const doFetch = fetchImpl ?? fetch;

      let response: Response;
      try {
        response = await doFetch(`${root}${API_PREFIX}${path}`, {
          method,
          signal,
          headers: {
            Accept: "application/json",
            [REQUEST_ID_HEADER]: sentRequestId,
            ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
          },
          body: body !== undefined ? JSON.stringify(body) : undefined,
        });
      } catch {
        throw new ApiError(0, "NETWORK_ERROR", "The service could not be reached.", sentRequestId);
      }

      // Prefer the ID the server used; fall back to the one we sent.
      const requestId = response.headers.get(REQUEST_ID_HEADER) ?? sentRequestId;

      if (response.status === 204) return undefined;

      let payload: unknown;
      try {
        payload = await response.json();
      } catch {
        throw new ApiError(response.status, "UNEXPECTED_RESPONSE", "The service sent an unreadable response.", requestId);
      }

      if (!response.ok) {
        const envelope = ErrorEnvelopeSchema.safeParse(payload);
        if (envelope.success) {
          const { code, message, request_id, details } = envelope.data.error;
          throw new ApiError(response.status, code, message, request_id, details);
        }
        throw new ApiError(response.status, "UNEXPECTED_RESPONSE", "The service sent an unexpected error.", requestId);
      }

      return payload;
    },
  };
}
