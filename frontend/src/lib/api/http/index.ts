import { z } from "zod";
import type { AdvisorApi } from "../types";
import { ApiError, ApiNotAvailableError, createHttpClient, type HttpClient } from "./client";
import {
  ALLOWED_UPLOAD_TYPES,
  MAX_UPLOAD_BYTES,
  UploadUrlWireSchema,
  decodeCaseSummary,
  decodeDocumentItem,
  decodeSafetyCheck,
  encodeNewCase,
  guessDocumentType,
} from "./resources";
import { type Health, HealthSchema, decodeRun } from "./wire";
import type { DocumentItem } from "@/domain/types";

export { ApiError, ApiNotAvailableError, createHttpClient } from "./client";
export { fromWire, toWire } from "./casing";
export { decodeCase, decodeReport, decodeRun, decodeSpecialistReport, decodeTrace } from "./wire";
export { decodeCaseSummary, decodeDocumentItem, decodeSafetyCheck, encodeNewCase } from "./resources";

/** Every `AdvisorApi` method. A test keeps this in step with the interface and the mock. */
export const ADVISOR_API_METHODS = [
  "listCases",
  "getCase",
  "getCaseOverview",
  "createCase",
  "deleteCase",
  "safetyCheck",
  "getDocuments",
  "uploadDocument",
  "removeDocument",
  "startAnalysis",
  "getRun",
  "getTimeline",
  "getPerspectives",
  "getEvidence",
  "getCrossReview",
  "getSynthesis",
  "getReport",
  "getQuestions",
  "updateQuestion",
  "getTrace",
  "getSecondOpinion",
  "submitSecondOpinion",
  "getComparison",
] as const satisfies readonly (keyof AdvisorApi)[];

/**
 * The HTTP implementation of `AdvisorApi` (Phase 2E).
 *
 * Served by the backend today: cases (list/get/create/delete), the safety check, documents (library, secure
 * upload, remove) and run status. Everything that needs the AI pipeline is NOT faked:
 *
 *  - result reads (timeline, perspectives, evidence, cross-review, synthesis, report, questions, trace,
 *    comparison) answer `null`: "no results exist for this case", which is true until the AI phase;
 *  - `getSecondOpinion` answers `{ status: "none" }`;
 *  - `startAnalysis`, `updateQuestion` and `submitSecondOpinion` report `ApiNotAvailableError`.
 */
export function createHttpApi(client: HttpClient = defaultHttpClient()): AdvisorApi {
  const notAvailable = (name: string) => () => Promise.reject(new ApiNotAvailableError(name));
  const noResults = () => Promise.resolve(null);

  /** A 404 from a "get one" call is "there is none", not an error the screen must show. */
  const orNull = async <T>(call: Promise<T>, codes: string[]): Promise<T | null> => {
    try {
      return await call;
    } catch (e) {
      if (e instanceof ApiError && e.status === 404 && codes.includes(e.code)) return null;
      throw e;
    }
  };

  const api: AdvisorApi = {
    async listCases() {
      const wire = await client.request("GET", "/cases");
      return z.array(z.unknown()).parse(wire).map(decodeCaseSummary);
    },
    async getCase(caseId) {
      const wire = await orNull(client.request("GET", `/cases/${enc(caseId)}`), ["CASE_NOT_FOUND"]);
      return wire === null ? null : decodeCaseSummary(wire);
    },
    async getCaseOverview(caseId) {
      const summary = await api.getCase(caseId);
      if (!summary) return null;
      const documents = await api.getDocuments(caseId);
      // Highlights come from analysis results, which do not exist yet.
      return { summary, documents, highlights: [], analysisAvailable: false };
    },
    async createCase(input) {
      return decodeCaseSummary(await client.request("POST", "/cases", { body: encodeNewCase(input) }));
    },
    async deleteCase(caseId) {
      await client.request("DELETE", `/cases/${enc(caseId)}`);
    },
    async safetyCheck(input) {
      const body = { text: input.text, current_symptoms: input.currentSymptoms };
      return decodeSafetyCheck(await client.request("POST", "/cases/safety-check", { body }));
    },

    async getDocuments(caseId) {
      const wire = await orNull(client.request("GET", `/cases/${enc(caseId)}/documents`), ["CASE_NOT_FOUND"]);
      return wire === null ? [] : z.array(z.unknown()).parse(wire).map(decodeDocumentItem);
    },
    async uploadDocument(caseId, file) {
      if (!file.blob) throw new Error("uploadDocument needs the file itself when talking to the backend.");
      return uploadDocument(client, caseId, file.name, file.blob);
    },
    async removeDocument(caseId, docId) {
      await client.request("DELETE", `/cases/${enc(caseId)}/documents/${enc(docId)}`);
    },

    startAnalysis: notAvailable("startAnalysis"),
    async getRun(runId) {
      const wire = await orNull(client.request("GET", `/analysis/${enc(runId)}`), ["RUN_NOT_FOUND"]);
      return wire === null ? null : decodeRun(wire);
    },

    getTimeline: noResults,
    getPerspectives: noResults,
    getEvidence: noResults,
    getCrossReview: noResults,
    getSynthesis: noResults,
    getReport: noResults,
    getQuestions: noResults,
    updateQuestion: notAvailable("updateQuestion"),
    getTrace: noResults,

    getSecondOpinion: () => Promise.resolve({ status: "none" as const }),
    submitSecondOpinion: notAvailable("submitSecondOpinion"),
    getComparison: noResults,
  };
  return api;
}

const enc = encodeURIComponent;

/**
 * Secure upload, in three steps (backend ADR 0007): ask for a short-lived signed URL, send the file straight to
 * private storage (it never passes through the API), then ask the backend to validate it. The backend checks the
 * real file type, size and content hash; the browser-declared type is only a request.
 */
async function uploadDocument(client: HttpClient, caseId: string, name: string, blob: Blob): Promise<DocumentItem> {
  if (!(ALLOWED_UPLOAD_TYPES as readonly string[]).includes(blob.type)) {
    throw new ApiError(0, "UNSUPPORTED_FILE_TYPE", "Only PDF, JPG and PNG files can be added.", "req_local");
  }
  if (blob.size === 0 || blob.size > MAX_UPLOAD_BYTES) {
    throw new ApiError(0, "FILE_SIZE_NOT_ALLOWED", "Files must be between 1 byte and 20 MB.", "req_local");
  }
  const slot = UploadUrlWireSchema.parse(
    await client.request("POST", `/cases/${enc(caseId)}/documents/upload-url`, {
      body: { name, type: guessDocumentType(name), mime_type: blob.type, size_bytes: blob.size },
    }),
  );

  // Same request shape the Supabase Storage client uses for a signed upload (multipart, file under the empty key).
  const form = new FormData();
  form.append("cacheControl", "3600");
  form.append("", blob);
  let put: Response;
  try {
    put = await fetch(slot.upload_url, { method: "PUT", body: form });
  } catch {
    throw new ApiError(0, "UPLOAD_FAILED", "The file could not be sent. Please try again.", "req_local");
  }
  if (!put.ok) throw new ApiError(put.status, "UPLOAD_FAILED", "The file could not be sent. Please try again.", "req_local");

  return decodeDocumentItem(
    await client.request("POST", `/cases/${enc(caseId)}/documents/${enc(slot.document_id)}/complete`),
  );
}

export async function fetchHealth(client: HttpClient): Promise<Health> {
  return HealthSchema.parse(await client.request("GET", "/health"));
}

/** The token getter is registered by the auth layer (see features/auth), so this module stays free of it. */
let tokenGetter: (() => Promise<string | null>) | undefined;
export function setAccessTokenGetter(getter: (() => Promise<string | null>) | undefined): void {
  tokenGetter = getter;
}

export function defaultHttpClient(): HttpClient {
  return createHttpClient({
    baseUrl: process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000",
    getAccessToken: () => (tokenGetter ? tokenGetter() : Promise.resolve(null)),
  });
}
