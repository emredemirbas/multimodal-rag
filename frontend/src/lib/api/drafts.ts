import "server-only";
import { NextResponse } from "next/server";
import { requestJson } from "./client";
import { ApiError } from "./errors";
import { requireSameOrigin } from "./request-origin";
import { parseEvidence } from "./chat-contracts";
import { parseContextReceipt, learningId, learningScope, type LearningScope } from "./curriculum-contracts";
import { authorizeLearningProject, curriculumPath, getDocument, invalidLearningResponse, validateLearningIds } from "./curriculum";
import { curriculumJson, curriculumRequestBody } from "./curriculum-proxy";
import { draftContent, parseDraftList, parseDraftReplace, parseDraftRevision, type DraftReplaceBody } from "./draft-contracts";

async function decodeDraft(payload: unknown, expected: LearningScope, draftId: string, revision?: number) {
  try {
    if (!payload || typeof payload !== "object" || !("context_id" in payload)) throw new TypeError();
    learningScope(payload as Record<string, unknown>, expected);
    const contextId = learningId(payload.context_id);
    const rawContext = await requestJson(curriculumPath(expected.project_id, `/contexts/${contextId}`));
    const context = parseContextReceipt(rawContext, expected, contextId);
    const result = parseDraftRevision(payload, expected, context, draftId, revision);
    // Compare retained projections with the original immutable context, never
    // the latest source generation. A response may not substitute copied text.
    const snapshots = (rawContext as { tutorial_snapshots: { segments: unknown[] }[] }).tutorial_snapshots;
    const authoritative = new Map(snapshots.flatMap((item) => item.segments.map((value) => { const evidence = parseEvidence(value); return [evidence.segment_id.toLowerCase(), evidence] as const; })));
    for (const item of result.assignment.tutorial_evidence) {
      if (JSON.stringify(item) !== JSON.stringify(authoritative.get(item.segment_id))) throw new TypeError();
    }
    const selected = await Promise.all(result.documentation_ids.map((id) => getDocument(expected, id, contextId)));
    if (selected.some((document) => !document.snapshot)) throw new TypeError();
    for (const snapshot of result.assignment.documentation_snapshots) {
      const full = selected.find((document) => document.id === snapshot.id)!.snapshot!;
      if (snapshot.url !== full.url || snapshot.retrieved_at !== full.retrieved_at || snapshot.detected_version !== full.detected_version || snapshot.content_sha256 !== full.content_sha256) throw new TypeError();
      for (const excerpt of snapshot.excerpts) if (JSON.stringify(excerpt) !== JSON.stringify(full.excerpts.find((item) => item.id === excerpt.id))) throw new TypeError();
    }
    return { result, context };
  } catch (error) {
    if (error instanceof ApiError) throw error;
    throw invalidLearningResponse(error);
  }
}
export async function getDraft(scope: LearningScope, draftId: string, revision?: number) {
  validateLearningIds(draftId); await authorizeLearningProject(scope.project_id, scope);
  if (revision !== undefined && (!Number.isSafeInteger(revision) || revision < 1 || revision > 2_147_483_647)) throw new ApiError({ status: 404 });
  const suffix = `/drafts/${draftId}${revision === undefined ? "" : `/revisions/${revision}`}`;
  return decodeDraft(await requestJson(curriculumPath(scope.project_id, suffix)), scope, draftId, revision);
}
export async function listDrafts(scope: LearningScope, contextId: string, after?: string) {
  validateLearningIds(contextId, ...(after ? [after] : [])); await authorizeLearningProject(scope.project_id, scope);
  const payload = await requestJson(curriculumPath(scope.project_id, `/contexts/${contextId}/drafts${after ? `?after=${after}` : ""}`));
  try { return parseDraftList(payload, scope, contextId, after); } catch (error) { throw invalidLearningResponse(error); }
}
export async function readDraftList(projectId: string, contextId: string, request: Request) {
  const query = new URL(request.url).searchParams;
  if ([...query.keys()].some((key) => key !== "after") || query.getAll("after").length > 1 || query.has("after") && !query.get("after")) throw new ApiError({ status: 422, code: "invalid_curriculum_draft" });
  const scope = await authorizeLearningProject(projectId);
  return curriculumJson(await listDrafts(scope, contextId, query.get("after") ?? undefined));
}
export async function readDraft(projectId: string, draftId: string, revision?: number) {
  const scope = await authorizeLearningProject(projectId);
  return curriculumJson((await getDraft(scope, draftId, revision)).result);
}
export async function replaceDraft(request: Request, projectId: string, draftId: string) {
  let body: DraftReplaceBody;
  try { body = parseDraftReplace(await curriculumRequestBody(request, 272_384)); }
  catch (error) { if (error instanceof ApiError) throw error; throw new ApiError({ status: 422, code: "invalid_curriculum_draft" }); }
  validateLearningIds(draftId);
  const scope = await authorizeLearningProject(projectId);
  const { result: before } = await getDraft(scope, draftId);
  const payload = await requestJson(curriculumPath(projectId, `/drafts/${draftId}`), { method: "PUT", body: JSON.stringify(body) });
  const { result } = await decodeDraft(payload, scope, draftId, body.expected_revision + 1);
  if (result.context_id !== before.context_id || JSON.stringify(draftContent(result)) !== JSON.stringify(body.content) || JSON.stringify(result.documentation_ids) !== JSON.stringify(body.documentation_ids)) throw invalidLearningResponse();
  return curriculumJson(result);
}
export async function deleteDraft(request: Request, projectId: string, draftId: string) {
  requireSameOrigin(request); validateLearningIds(draftId); await authorizeLearningProject(projectId);
  await requestJson(curriculumPath(projectId, `/drafts/${draftId}`), { method: "DELETE" }, undefined, { expectedStatus: 204 });
  return new NextResponse(null, { status: 204, headers: { "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff", "Cross-Origin-Resource-Policy": "same-origin" } });
}
