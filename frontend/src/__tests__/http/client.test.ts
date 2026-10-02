import { describe, expect, it } from "vitest";
import { ADVISOR_API_METHODS, ApiError, ApiNotAvailableError, createHttpApi, createHttpClient, fetchHealth } from "@/lib/api/http";
import { mockApi } from "@/mocks/mock-api";

const json = (status: number, body: unknown, headers: Record<string, string> = {}) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json", ...headers } });

function clientWith(respond: (url: string, init: RequestInit) => Response | Promise<Response>) {
  const calls: { url: string; init: RequestInit }[] = [];
  const client = createHttpClient({
    baseUrl: "http://api.test/",
    newRequestId: () => "req_sent",
    fetchImpl: (async (url: string, init: RequestInit) => {
      calls.push({ url, init });
      return respond(url, init);
    }) as typeof fetch,
  });
  return { client, calls };
}

describe("http client", () => {
  it("calls /api/v1, sends a request ID and returns the parsed health body", async () => {
    const { client, calls } = clientWith(() => json(200, { status: "ok", service: "s", version: "0.1.0", environment: "test" }));
    expect((await fetchHealth(client)).status).toBe("ok");
    expect(calls[0].url).toBe("http://api.test/api/v1/health");
    expect((calls[0].init.headers as Record<string, string>)["X-Request-ID"]).toBe("req_sent");
  });

  it("turns the error envelope into an ApiError carrying code, message and request ID", async () => {
    const { client } = clientWith(() =>
      json(404, { error: { code: "CASE_NOT_FOUND", message: "Case could not be found.", request_id: "req_123", details: {} } }),
    );
    const err = (await client.request("GET", "/cases/x").catch((e) => e)) as ApiError;
    expect(err).toBeInstanceOf(ApiError);
    expect(err).toMatchObject({ status: 404, code: "CASE_NOT_FOUND", message: "Case could not be found.", requestId: "req_123" });
  });

  it("keeps an error code a newer backend added", async () => {
    const { client } = clientWith(() => json(409, { error: { code: "SOME_NEW_CODE", message: "m", request_id: "r1", details: { a: 1 } } }));
    await expect(client.request("POST", "/x")).rejects.toMatchObject({ code: "SOME_NEW_CODE", details: { a: 1 } });
  });

  it("does not trust a non-envelope error body", async () => {
    const { client } = clientWith(() => json(500, { detail: "Traceback ..." }, { "X-Request-ID": "req_srv" }));
    const err = (await client.request("GET", "/x").catch((e) => e)) as ApiError;
    expect(err).toMatchObject({ status: 500, code: "UNEXPECTED_RESPONSE", requestId: "req_srv" });
    expect(String(err.message)).not.toContain("Traceback");
  });

  it("reports a network failure with the request ID it sent", async () => {
    const { client } = clientWith(() => {
      throw new TypeError("fetch failed");
    });
    await expect(client.request("GET", "/x")).rejects.toMatchObject({ status: 0, code: "NETWORK_ERROR", requestId: "req_sent" });
  });

  it("sends JSON bodies with a content type", async () => {
    const { client, calls } = clientWith(() => json(200, {}));
    await client.request("POST", "/x", { body: { a: 1 } });
    expect(calls[0].init.body).toBe('{"a":1}');
    expect((calls[0].init.headers as Record<string, string>)["Content-Type"]).toBe("application/json");
  });
});

describe("httpApi", () => {
  it("covers every AdvisorApi method (kept in step with the mock)", () => {
    expect([...ADVISOR_API_METHODS].sort()).toEqual(Object.keys(mockApi).sort());
  });

  it("reports, rather than fakes, data the backend does not serve yet", async () => {
    const api = createHttpApi();
    await expect(api.listCases()).rejects.toBeInstanceOf(ApiNotAvailableError);
    await expect(api.getReport("c_1")).rejects.toThrow(/not available from the backend yet/);
  });
});
