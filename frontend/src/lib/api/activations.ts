import "server-only";
import { requestJson } from "./client";
import { ApiError } from "./errors";
import { learningFields, learningId, learningInteger, learningScope, type LearningScope } from "./curriculum-contracts";
import { authorizeLearningProject, curriculumPath, invalidLearningResponse, validateLearningIds } from "./curriculum";
import { curriculumJson, curriculumRequestBody } from "./curriculum-proxy";
import { decodeDraft, getDraft } from "./drafts";
import { ACTIVATION_FIELDS, parseAssignmentActivate, parseAssignmentActivation, type AssignmentActivateBody } from "./activation-contracts";

async function decodeActivation(payload: unknown, scope: LearningScope, draftId?: string, revision?: number, activationId?: string) {
  try {
    const row = learningFields(payload, ACTIVATION_FIELDS);
    learningScope(row, scope);
    const pinnedDraftId = learningId(row.draft_id), pinnedRevision = learningInteger(row.revision, 2_147_483_647);
    if (draftId !== undefined && pinnedDraftId !== learningId(draftId)
        || revision !== undefined && pinnedRevision !== revision
        || activationId !== undefined && learningId(row.id) !== learningId(activationId)) throw new TypeError();
    const { context } = await decodeDraft(row.draft, scope, pinnedDraftId, pinnedRevision);
    return { activation: parseAssignmentActivation(payload, scope, context, draftId, revision, activationId), context };
  } catch (error) {
    if (error instanceof ApiError) throw error;
    throw invalidLearningResponse(error);
  }
}

export async function getAssignmentActivation(scope: LearningScope, activationId: string) {
  validateLearningIds(activationId);
  await authorizeLearningProject(scope.project_id, scope);
  return decodeActivation(await requestJson(curriculumPath(scope.project_id, `/assignments/${activationId}`)), scope, undefined, undefined, activationId);
}

export async function getDraftActivation(scope: LearningScope, draftId: string) {
  validateLearningIds(draftId);
  await authorizeLearningProject(scope.project_id, scope);
  const { result: current } = await getDraft(scope, draftId);
  const payload = await requestJson(curriculumPath(scope.project_id, `/drafts/${draftId}/activation`));
  try {
    const row = learningFields(payload, ["activation"]);
    if (row.activation === null) return null;
    const { activation } = await decodeActivation(row.activation, scope, draftId);
    if (activation.context_id !== current.context_id || activation.revision > current.revision) throw new TypeError();
    return activation;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    throw invalidLearningResponse(error);
  }
}

export async function activateAssignment(request: Request, projectId: string, draftId: string) {
  let body: AssignmentActivateBody;
  try { body = parseAssignmentActivate(await curriculumRequestBody(request)); }
  catch (error) {
    if (error instanceof ApiError) throw error;
    throw new ApiError({ status: 422, code: "invalid_assignment_activation" });
  }
  validateLearningIds(draftId);
  const scope = await authorizeLearningProject(projectId);
  // An accepted command can be replayed after edits or archive. Compare the
  // exact immutable reviewed revision rather than replacing it with today's head.
  const { result: before } = await getDraft(scope, draftId, body.expected_revision);
  const payload = await requestJson(curriculumPath(projectId, `/drafts/${draftId}/activate`), { method: "POST", body: JSON.stringify(body) });
  const { activation } = await decodeActivation(payload, scope, draftId, body.expected_revision);
  if (JSON.stringify(activation.draft) !== JSON.stringify(before)) throw invalidLearningResponse();
  return curriculumJson(activation, 201);
}

export async function readDraftActivation(projectId: string, draftId: string) {
  const scope = await authorizeLearningProject(projectId);
  return curriculumJson({ activation: await getDraftActivation(scope, draftId) });
}

export async function readAssignmentActivation(projectId: string, activationId: string) {
  const scope = await authorizeLearningProject(projectId);
  return curriculumJson((await getAssignmentActivation(scope, activationId)).activation);
}
