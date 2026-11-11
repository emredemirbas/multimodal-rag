import "server-only";
import { getProject, requestJson } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { UUID_PATTERN } from "@/lib/api/identifiers";
import { parseSourceList } from "@/lib/api/source-contracts";
import {
  parseContextReceipt, parseDocumentList, parseDocumentationCatalog, parseDocumentView,
  verifyCatalogIntegrity, verifyDocumentIntegrity,
  type BrowserContextCreateBody, type LearningScope,
} from "@/lib/api/curriculum-contracts";

export function curriculumPath(projectId: string, suffix = ""): string {
  return `/api/v1/projects/${encodeURIComponent(projectId)}/curriculum${suffix}`;
}
export function validateLearningIds(...ids: string[]): void {
  if (ids.some((id) => !UUID_PATTERN.test(id))) throw new ApiError({ status: 404, code: "learning_target_not_found" });
}
export function invalidLearningResponse(cause?: unknown): ApiError { return new ApiError({ status: 502, code: "invalid_api_response", cause }); }
export async function authorizeLearningProject(projectId: string, expected?: LearningScope): Promise<LearningScope> {
  validateLearningIds(projectId);
  let project;
  try { project = await getProject(projectId); }
  catch (error) { if (error instanceof ApiError && error.status === 404) throw new ApiError({ status: 404, code: "project_not_found" }); throw error; }
  if (project.id.toLowerCase() !== projectId.toLowerCase() || !/^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$/.test(project.tenant_id)
      || expected && (expected.tenant_id !== project.tenant_id || expected.project_id.toLowerCase() !== project.id.toLowerCase())) throw invalidLearningResponse();
  return { tenant_id: project.tenant_id, project_id: project.id.toLowerCase() };
}
export async function decodeContextReceipt(payload: unknown, scope: LearningScope, contextId?: string, input?: BrowserContextCreateBody) {
  try { return parseContextReceipt(payload, scope, contextId, input); }
  catch (error) { throw invalidLearningResponse(error); }
}
export async function decodeDocumentReceipt(payload: unknown, scope: LearningScope, contextId?: string, documentId?: string) {
  try { return await verifyDocumentIntegrity(parseDocumentView(payload, scope, contextId, documentId)); }
  catch (error) { throw invalidLearningResponse(error); }
}
export async function getLearningContext(scope: LearningScope, contextId: string) {
  validateLearningIds(contextId);
  await authorizeLearningProject(scope.project_id, scope);
  return decodeContextReceipt(await requestJson(curriculumPath(scope.project_id, `/contexts/${encodeURIComponent(contextId)}`)), scope, contextId);
}
export async function getDocumentationCatalog(scope: LearningScope) {
  await authorizeLearningProject(scope.project_id, scope);
  const payload = await requestJson(curriculumPath(scope.project_id, "/documentation/catalog"));
  try { return await verifyCatalogIntegrity(parseDocumentationCatalog(payload)); }
  catch (error) { throw invalidLearningResponse(error); }
}
export async function listContextDocuments(scope: LearningScope, contextId: string) {
  validateLearningIds(contextId);
  await authorizeLearningProject(scope.project_id, scope);
  const payload = await requestJson(curriculumPath(scope.project_id, `/contexts/${encodeURIComponent(contextId)}/documentation`));
  try { const items = parseDocumentList(payload, scope, contextId); return await Promise.all(items.map(verifyDocumentIntegrity)); }
  catch (error) { throw invalidLearningResponse(error); }
}
export async function getDocument(scope: LearningScope, documentId: string, contextId?: string) {
  validateLearningIds(documentId);
  await authorizeLearningProject(scope.project_id, scope);
  return decodeDocumentReceipt(await requestJson(curriculumPath(scope.project_id, `/documentation/${encodeURIComponent(documentId)}`)), scope, contextId, documentId);
}
export async function listLearningSources(scope: LearningScope) {
  await authorizeLearningProject(scope.project_id, scope);
  const payload = await requestJson(`/api/v1/projects/${encodeURIComponent(scope.project_id)}/sources`);
  try {
    if (!payload || typeof payload !== "object" || !("items" in payload) || !Array.isArray(payload.items) || payload.items.length > 200) throw new TypeError();
    for (const item of payload.items) if (!item || typeof item !== "object" || item.tenant_id !== scope.tenant_id || typeof item.project_id !== "string" || item.project_id.toLowerCase() !== scope.project_id.toLowerCase()) throw new TypeError();
    const items = parseSourceList(payload);
    if (new Set(items.map((item) => item.id.toLowerCase())).size !== items.length) throw new TypeError();
    return items;
  } catch (error) { throw invalidLearningResponse(error); }
}
