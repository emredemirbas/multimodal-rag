import "server-only";
import { NextResponse } from "next/server";
import { requestJson } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { requireSameOrigin } from "@/lib/api/request-origin";
import {
  parseContextCreate, parseDocumentApproval, parseDocumentCapture,
  type DocumentView,
} from "@/lib/api/curriculum-contracts";
import {
  authorizeLearningProject, curriculumPath, decodeContextReceipt, decodeDocumentReceipt,
  getDocumentationCatalog, getDocument, getLearningContext, invalidLearningResponse,
  listContextDocuments, validateLearningIds,
} from "@/lib/api/curriculum";

const PRIVATE_HEADERS = { "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff", "Cross-Origin-Resource-Policy": "same-origin" };
const MESSAGES: Record<string, string> = {
  curriculum_context_not_found: "The saved learning context is no longer available. It may have been deleted with a selected source.",
  documentation_not_found: "This document approval is no longer available.",
  project_not_found: "The project is no longer available.",
  learning_target_not_found: "This learning resource is not available.",
  invalid_curriculum_command: "Check the selected sources and explicit learning preferences.",
  curriculum_source_unavailable: "A selected source version is unavailable. Refresh the source list and choose published evidence.",
  curriculum_evidence_too_large: "Choose fewer or smaller sources for this learning context.",
  curriculum_not_configured: "Saved learning contexts require the local PostgreSQL services.",
  project_archived: "Restore the project before saving a context or capturing documentation.",
  idempotency_conflict: "This command key belongs to different input. Keep an uncertain request unchanged when retrying.",
  documentation_not_enabled: "This context does not allow external documentation. Save a new context with that permission if needed.",
  documentation_not_allowed: "Choose a document from the current official catalog.",
  documentation_policy_changed: "The document policy changed. Review and approve the current catalog entry.",
  documentation_limit: "This context has reached its document approval limit. Delete an unused approval first.",
  documentation_capture_in_progress: "Capture is already in progress. Refresh its status before issuing another command.",
  documentation_capture_lost: "The capture lease or its context changed. Refresh the document before explicitly trying again.",
  documentation_fetch_timeout: "The official document did not respond within the capture limit. A new explicit attempt can retry it.",
  documentation_fetch_unavailable: "The official document is unavailable. A new explicit attempt can retry it.",
  documentation_fetch_invalid: "The official page did not match the bounded document format. Its content was not retained.",
  documentation_fetch_not_allowed: "The official page could not be safely retrieved. Its content was not retained.",
  documentation_fetch_busy: "Another local document capture is running. Refresh and retry explicitly shortly.",
  request_timeout: "Delivery timed out and may already have completed. Refresh status, or resend the unchanged command with the same key.",
  upstream_unavailable: "The local API could not be reached. Keep the unchanged command key when retrying uncertain delivery.",
  invalid_api_response: "The local API returned a response that could not be verified. Refresh before retrying an uncertain write.",
};
export function curriculumProxyError(error: unknown, missingCode?: "curriculum_context_not_found" | "documentation_not_found" | "project_not_found"): NextResponse {
  const status = error instanceof ApiError && error.status >= 400 && error.status <= 599 ? error.status : 502;
  const code = error instanceof ApiError && Object.hasOwn(MESSAGES, error.code) ? error.code : status === 404 && missingCode ? missingCode : "request_failed";
  const message = MESSAGES[code] ?? (status === 401 || status === 403 ? "Your session could not be verified. Refresh and try again." : "The learning request could not be completed. Refresh and try again.");
  return NextResponse.json({ code, message }, { status, headers: PRIVATE_HEADERS });
}
export function curriculumJson(value: unknown, status = 200): NextResponse { return NextResponse.json(value, { status, headers: PRIVATE_HEADERS }); }

/** Parse original JSON, rejecting duplicate decoded keys before constructing objects. */
export function parseUniqueJson(input: string): unknown {
  let offset = 0;
  function whitespace() { while (/\s/.test(input[offset] ?? "") && offset < input.length) offset++; }
  function string(): string {
    const start = offset++;
    while (offset < input.length) {
      if (input[offset] === "\\") { offset += 2; continue; }
      if (input[offset++] === '"') return JSON.parse(input.slice(start, offset));
    }
    throw new TypeError("Invalid JSON");
  }
  function value(depth: number): unknown {
    if (depth > 32) throw new TypeError("Invalid JSON depth");
    whitespace();
    if (input[offset] === '"') return string();
    if (input[offset] === "{") {
      offset++; whitespace(); const result: Record<string, unknown> = Object.create(null); const keys = new Set<string>();
      if (input[offset] === "}") { offset++; return result; }
      while (true) {
        whitespace(); if (input[offset] !== '"') throw new TypeError("Invalid JSON key");
        const key = string(); if (keys.has(key)) throw new TypeError("Duplicate JSON key"); keys.add(key);
        whitespace(); if (input[offset++] !== ":") throw new TypeError("Invalid JSON field");
        result[key] = value(depth + 1); whitespace();
        const delimiter = input[offset++]; if (delimiter === "}") return result; if (delimiter !== ",") throw new TypeError("Invalid JSON object");
      }
    }
    if (input[offset] === "[") {
      offset++; whitespace(); const result: unknown[] = []; if (input[offset] === "]") { offset++; return result; }
      while (true) { result.push(value(depth + 1)); whitespace(); const delimiter = input[offset++]; if (delimiter === "]") return result; if (delimiter !== ",") throw new TypeError("Invalid JSON array"); }
    }
    const match = /^(?:-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?|true|false|null)/.exec(input.slice(offset));
    if (!match) throw new TypeError("Invalid JSON value"); offset += match[0].length;
    const parsed: unknown = JSON.parse(match[0]); if (typeof parsed === "number" && !Number.isFinite(parsed)) throw new TypeError("Invalid JSON number"); return parsed;
  }
  // Native JSON validation also rejects unsupported whitespace and bad escapes.
  JSON.parse(input);
  const result = value(0); whitespace(); if (offset !== input.length) throw new TypeError("Invalid JSON suffix"); return result;
}
export async function curriculumRequestBody(request: Request): Promise<unknown> {
  requireSameOrigin(request);
  if (!/^application\/json(?:\s*;|$)/i.test(request.headers.get("content-type") ?? "")) throw new ApiError({ status: 415 });
  const reader = request.body?.getReader(); if (!reader) throw new ApiError({ status: 422, code: "invalid_curriculum_command" });
  let bytes = 0, content = ""; const decoder = new TextDecoder("utf-8", { fatal: true });
  let timedOut = false;
  const timer = setTimeout(() => { timedOut = true; void reader.cancel(); }, 8_000);
  try {
    while (true) { const chunk = await reader.read(); if (chunk.done) break; bytes += chunk.value.byteLength; if (bytes > 16_384) throw new ApiError({ status: 413, code: "invalid_curriculum_command" }); content += decoder.decode(chunk.value, { stream: true }); }
    if (timedOut) throw new ApiError({ status: 408, code: "invalid_curriculum_command" });
    content += decoder.decode(); return parseUniqueJson(content);
  } catch (error) { if (error instanceof ApiError) throw error; throw new ApiError({ status: 422, code: "invalid_curriculum_command" }); }
  finally { clearTimeout(timer); await reader.cancel().catch(() => undefined); reader.releaseLock(); }
}
function input<T>(parse: (value: unknown) => T, value: unknown): T { try { return parse(value); } catch { throw new ApiError({ status: 422, code: "invalid_curriculum_command" }); } }
function sameApproval(before: DocumentView, after: DocumentView): void {
  if (before.context_id !== after.context_id || before.approved_by !== after.approved_by || before.approved_at !== after.approved_at || before.consent !== after.consent || JSON.stringify(before.policy) !== JSON.stringify(after.policy)) throw invalidLearningResponse();
  if (before.snapshot && (JSON.stringify(before.snapshot) !== JSON.stringify(after.snapshot) || before.raw_sha256 !== after.raw_sha256 || before.raw_bytes !== after.raw_bytes)) throw invalidLearningResponse();
}
export async function createLearningContext(request: Request, projectId: string) {
  const body = input(parseContextCreate, await curriculumRequestBody(request));
  const scope = await authorizeLearningProject(projectId);
  return curriculumJson(await decodeContextReceipt(await requestJson(curriculumPath(projectId, "/contexts"), { method: "POST", body: JSON.stringify(body) }), scope, undefined, body), 201);
}
export async function readLearningContext(projectId: string, contextId: string) { const scope = await authorizeLearningProject(projectId); return curriculumJson(await getLearningContext(scope, contextId)); }
export async function deleteLearningContext(request: Request, projectId: string, contextId: string) {
  requireSameOrigin(request); validateLearningIds(contextId); await authorizeLearningProject(projectId);
  await requestJson(curriculumPath(projectId, `/contexts/${contextId}`), { method: "DELETE" }, undefined, { expectedStatus: 204 });
  return new NextResponse(null, { status: 204, headers: PRIVATE_HEADERS });
}
export async function readDocumentationCatalog(projectId: string) { const scope = await authorizeLearningProject(projectId); return curriculumJson(await getDocumentationCatalog(scope)); }
export async function readContextDocuments(projectId: string, contextId: string) { const scope = await authorizeLearningProject(projectId); return curriculumJson(await listContextDocuments(scope, contextId)); }
export async function approveDocumentation(request: Request, projectId: string, contextId: string) {
  const body = input(parseDocumentApproval, await curriculumRequestBody(request));
  validateLearningIds(contextId);
  const scope = await authorizeLearningProject(projectId);
  const document = await decodeDocumentReceipt(await requestJson(curriculumPath(projectId, `/contexts/${contextId}/documentation`), { method: "POST", body: JSON.stringify(body) }), scope, contextId);
  // The backend checks new approvals against current policy, but replays the
  // original immutable approval before policy/archive checks. Do not replace it
  // with a preflight against today's catalog or silently approve changed input.
  if (document.policy.id !== body.catalog_id || document.policy.fingerprint !== body.catalog_sha256) throw invalidLearningResponse();
  return curriculumJson(document, 201);
}
export async function readDocumentation(projectId: string, documentId: string) { const scope = await authorizeLearningProject(projectId); return curriculumJson(await getDocument(scope, documentId)); }
export async function captureDocumentation(request: Request, projectId: string, documentId: string) {
  const body = input(parseDocumentCapture, await curriculumRequestBody(request));
  const scope = await authorizeLearningProject(projectId), before = await getDocument(scope, documentId);
  const after = await decodeDocumentReceipt(await requestJson(curriculumPath(projectId, `/documentation/${documentId}/capture`), { method: "POST", body: JSON.stringify(body) }, undefined, { timeoutMs: 25_000 }), scope, before.context_id, documentId);
  sameApproval(before, after); if (after.status !== "captured") throw invalidLearningResponse();
  return curriculumJson(after);
}
export async function deleteDocumentation(request: Request, projectId: string, documentId: string) {
  requireSameOrigin(request); validateLearningIds(documentId); await authorizeLearningProject(projectId);
  await requestJson(curriculumPath(projectId, `/documentation/${documentId}`), { method: "DELETE" }, undefined, { expectedStatus: 204 });
  return new NextResponse(null, { status: 204, headers: PRIVATE_HEADERS });
}
