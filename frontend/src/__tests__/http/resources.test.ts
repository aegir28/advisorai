import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it, vi } from "vitest";
import { ApiError, ApiNotAvailableError, createHttpApi, createHttpClient } from "@/lib/api/http";
import { ZodError } from "zod";
import { withValidation } from "@/lib/api/validate";
import { encodeNewCase, guessDocumentType } from "@/lib/api/http/resources";

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
const envelope = (code: string, status = 404) => json(status, { error: { code, message: "m", request_id: "req_1", details: {} } });

type Handler = (method: string, path: string, init: RequestInit) => Response | Promise<Response>;

function setup(handler: Handler) {
  const calls: { method: string; path: string; body?: unknown }[] = [];
  const client = createHttpClient({
    baseUrl: "http://api.test",
    newRequestId: () => "req_sent",
    fetchImpl: (async (url: string, init: RequestInit) => {
      const path = url.replace("http://api.test/api/v1", "");
      calls.push({ method: init.method ?? "GET", path, body: init.body ? JSON.parse(String(init.body)) : undefined });
      return handler(init.method ?? "GET", path, init);
    }) as typeof fetch,
  });
  return { api: withValidation(createHttpApi(client)), calls };
}

const CASE = {
  id: "3f0c2a52-6a41-4d0e-9b57-1c9f4f7d9a10", code: "AC-9F2K", age_years: 52, sex: "M", concern: "Is this needed?",
  status: "awaiting_upload", document_count: 0, updated_at: "2026-10-04T10:00:00+00:00", title: "My heart",
};
const DOC = { id: "d1", name: "labs.pdf", type: "lab", pages: 2, size_kb: 12.5, status: "ready", uploaded_at: "2026-10-04T10:01:00+00:00" };

describe("cases", () => {
  it("lists, gets and maps the wire to the domain model (optional means absent)", async () => {
    const { api, calls } = setup((_m, path) => (path === "/cases" ? json(200, [CASE]) : json(200, CASE)));
    const [c] = await api.listCases();
    expect(c).toMatchObject({ id: CASE.id, code: "AC-9F2K", ageYears: 52, documentCount: 0, status: "awaiting_upload", title: "My heart" });
    expect(c).not.toHaveProperty("ownerLabel");
    expect(c.proposedTreatment).toBeUndefined();
    expect((await api.getCase(CASE.id))?.updatedAt).toBe(CASE.updated_at);
    expect(calls.map((x) => `${x.method} ${x.path}`)).toEqual(["GET /cases", `GET /cases/${CASE.id}`]);
  });

  it("answers null for a case that is not there, and rethrows anything else", async () => {
    expect(await setup(() => envelope("CASE_NOT_FOUND")).api.getCase("x")).toBeNull();
    await expect(setup(() => envelope("INTERNAL_ERROR", 500)).api.getCase("x")).rejects.toBeInstanceOf(ApiError);
    await expect(setup(() => envelope("UNAUTHENTICATED", 401)).api.getCase("x")).rejects.toMatchObject({ status: 401 });
  });

  it("creates with a snake_case body that omits empty optionals and never carries identity", async () => {
    const { api, calls } = setup(() => json(201, CASE));
    await api.createCase({ concern: "  Is this needed? ", ageYears: 52, sex: "M", intent: "", proposedTreatment: undefined });
    expect(calls[0]).toMatchObject({ method: "POST", path: "/cases", body: { concern: "Is this needed?", age_years: 52, sex: "M" } });
    expect(Object.keys(calls[0].body as object).sort()).toEqual(["age_years", "concern", "sex"]);
    expect(encodeNewCase({ concern: "c", ageYears: 1, sex: "F", intent: "Understand", proposedTreatment: "A" })).toEqual({
      concern: "c", age_years: 1, sex: "F", intent: "Understand", proposed_treatment: "A",
    });
  });

  it("deletes with 204", async () => {
    const { api, calls } = setup(() => new Response(null, { status: 204 }));
    await expect(api.deleteCase("c1")).resolves.toBeUndefined();
    expect(calls[0]).toMatchObject({ method: "DELETE", path: "/cases/c1" });
  });

  it("builds the overview from the case and its documents (no results exist yet)", async () => {
    const { api } = setup((_m, path) => (path.endsWith("/documents") ? json(200, [DOC]) : json(200, CASE)));
    const o = await api.getCaseOverview(CASE.id);
    expect(o?.analysisAvailable).toBe(false);
    expect(o?.highlights).toEqual([]);
    expect(o?.documents).toHaveLength(1);
    expect(await setup(() => envelope("CASE_NOT_FOUND")).api.getCaseOverview("x")).toBeNull();
  });

  it("rejects a key the backend should not send (the wire is strict)", async () => {
    const { api } = setup(() => json(200, [{ ...CASE, owner_user_id: "u1" }]));
    await expect(api.listCases()).rejects.toBeInstanceOf(ZodError);
    const { api: api2 } = setup(() => json(200, [{ ...CASE, status: "pending_upload" }]));
    await expect(api2.listCases()).rejects.toBeInstanceOf(ZodError);
  });

  it("encodes ids in paths", async () => {
    const { api, calls } = setup(() => envelope("CASE_NOT_FOUND"));
    await api.getCase("a/b?x=1");
    expect(calls[0].path).toBe("/cases/a%2Fb%3Fx%3D1");
  });
});

describe("safety check", () => {
  it("posts text and ticked symptoms and maps the answer", async () => {
    const { api, calls } = setup(() => json(200, { red_flag: true, matched: ["chest pain now"], category: "cardiac" }));
    expect(await api.safetyCheck({ text: "chest pain now", currentSymptoms: ["breathless_rest"] })).toEqual({
      redFlag: true, matched: ["chest pain now"], category: "cardiac",
    });
    expect(calls[0]).toMatchObject({ method: "POST", path: "/cases/safety-check", body: { text: "chest pain now", current_symptoms: ["breathless_rest"] } });
    const none = await setup(() => json(200, { red_flag: false, matched: [] })).api.safetyCheck({ text: "x", currentSymptoms: [] });
    expect(none).toEqual({ redFlag: false, matched: [] });
  });
});

describe("documents", () => {
  const pdf = () => new File([new Uint8Array([37, 80, 68, 70])], "labs.pdf", { type: "application/pdf" });

  it("lists, answering [] for a case that is not there", async () => {
    expect((await setup(() => json(200, [DOC])).api.getDocuments("c")).map((d) => d.pages)).toEqual([2]);
    expect(await setup(() => envelope("CASE_NOT_FOUND")).api.getDocuments("c")).toEqual([]);
  });

  it("keeps pages optional for a file that could not be read", async () => {
    const bad = { id: "d2", name: "x.pdf", type: "other", size_kb: 0, status: "needs_attention", uploaded_at: "2026-10-04T10:00:00+00:00", note: "This PDF is password protected." };
    const [d] = await setup(() => json(200, [bad])).api.getDocuments("c");
    expect(d.pages).toBeUndefined();
    expect(d.status).toBe("needs_attention");
  });

  it("uploads in three steps: signed URL, straight to storage, then validation", async () => {
    const put = vi.fn(async () => new Response(null, { status: 200 }));
    vi.stubGlobal("fetch", put);
    try {
      const { api, calls } = setup((_m, path) =>
        path.endsWith("/upload-url")
          ? json(200, { document_id: "d9", upload_url: "https://storage.test/upload?token=SECRET", expires_in: 7200 })
          : json(200, DOC),
      );
      const doc = await api.uploadDocument("c1", { name: "labs.pdf", sizeKb: 1, blob: pdf() });
      expect(doc.status).toBe("ready");
      expect(calls.map((c) => `${c.method} ${c.path}`)).toEqual(["POST /cases/c1/documents/upload-url", "POST /cases/c1/documents/d9/complete"]);
      expect(calls[0].body).toEqual({ name: "labs.pdf", type: "lab", mime_type: "application/pdf", size_bytes: 4 });
      // The file goes to the signed URL, never to the API.
      expect(put).toHaveBeenCalledTimes(1);
      const [url, init] = put.mock.calls[0] as unknown as [string, RequestInit];
      expect(url).toBe("https://storage.test/upload?token=SECRET");
      expect(init.method).toBe("PUT");
      expect(init.body).toBeInstanceOf(FormData);
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it("refuses an unsupported type or size before touching the network", async () => {
    const { api, calls } = setup(() => json(200, {}));
    const exe = new File([new Uint8Array([1])], "a.exe", { type: "application/x-msdownload" });
    await expect(api.uploadDocument("c", { name: "a.exe", sizeKb: 1, blob: exe })).rejects.toMatchObject({ code: "UNSUPPORTED_FILE_TYPE" });
    const empty = new File([], "a.pdf", { type: "application/pdf" });
    await expect(api.uploadDocument("c", { name: "a.pdf", sizeKb: 0, blob: empty })).rejects.toMatchObject({ code: "FILE_SIZE_NOT_ALLOWED" });
    await expect(api.uploadDocument("c", { name: "a.pdf", sizeKb: 1 })).rejects.toThrow(/needs the file itself/);
    expect(calls).toEqual([]);
  });

  it("reports a failed storage upload without calling complete, and never echoes the signed URL", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("denied", { status: 403 })));
    try {
      const { api, calls } = setup(() => json(200, { document_id: "d9", upload_url: "https://storage.test/u?token=SECRET", expires_in: 60 }));
      const err = (await api.uploadDocument("c1", { name: "labs.pdf", sizeKb: 1, blob: pdf() }).catch((e) => e)) as ApiError;
      expect(err).toMatchObject({ code: "UPLOAD_FAILED", status: 403 });
      expect(JSON.stringify([err.message, err.details])).not.toContain("SECRET");
      expect(calls.map((c) => c.path)).toEqual(["/cases/c1/documents/upload-url"]);
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it("removes a document", async () => {
    const { api, calls } = setup(() => new Response(null, { status: 204 }));
    await api.removeDocument("c1", "d1");
    expect(calls[0]).toMatchObject({ method: "DELETE", path: "/cases/c1/documents/d1" });
  });

  it("guesses a document type from the file name", () => {
    expect(["HbA1c.pdf", "ecg.png", "rx-list.jpg", "discharge summary.pdf", "knee mri.pdf", "referral.pdf", "other.pdf"].map(guessDocumentType)).toEqual([
      "lab", "ecg", "prescription", "discharge", "imaging", "consult", "other",
    ]);
  });
});

describe("runs and AI-dependent reads", () => {
  it("decodes run.v1 from the backend's own fixture", async () => {
    const wire = JSON.parse(readFileSync(fileURLToPath(new URL("../../../../backend/tests/fixtures/contracts/cardiology/run.v1.json", import.meta.url)), "utf8"));
    const run = await setup(() => json(200, wire)).api.getRun(wire.id);
    expect(run?.id).toBe(wire.id);
    expect(run?.steps).toHaveLength(14);
  });

  it("answers null for a run that is not there", async () => {
    expect(await setup(() => envelope("RUN_NOT_FOUND")).api.getRun("r")).toBeNull();
  });

  it("answers 'no results' (not an error, not fake data) until the AI phase exists", async () => {
    const { api, calls } = setup(() => json(500, {}));
    expect(await api.getReport("c")).toBeNull();
    expect(await api.getTimeline("c")).toBeNull();
    expect(await api.getPerspectives("c")).toBeNull();
    expect(await api.getQuestions("c")).toBeNull();
    expect(await api.getComparison("c")).toBeNull();
    expect(await api.getSecondOpinion("c")).toEqual({ status: "none" });
    expect(calls).toEqual([]); // nothing was asked of the backend
    await expect(api.startAnalysis("c")).rejects.toBeInstanceOf(ApiNotAvailableError);
  });
});
