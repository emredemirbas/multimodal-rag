import {
  learningDate, learningFields, learningId, learningInteger, learningScope,
  parseCommandKey, type LearningScope, type SavedLearningContext,
} from "./curriculum-contracts";
import { parseDraftRevision, type DraftRevision } from "./draft-contracts";

export interface AssignmentActivateBody {
  idempotency_key: string;
  expected_revision: number;
  consent: "activate_reviewed_revision";
}
export interface AssignmentActivation extends LearningScope {
  id: string;
  draft_id: string;
  context_id: string;
  revision: number;
  activated_at: string;
  activated_by: string;
  draft: DraftRevision;
}
export const ACTIVATION_FIELDS = ["id", "tenant_id", "project_id", "draft_id", "context_id", "revision", "activated_at", "activated_by", "draft"] as const;

export function parseAssignmentActivate(value: unknown): AssignmentActivateBody {
  const row = learningFields(value, ["idempotency_key", "expected_revision", "consent"]);
  if (row.consent !== "activate_reviewed_revision") throw new TypeError("Invalid assignment activation");
  return {
    idempotency_key: parseCommandKey(row.idempotency_key),
    expected_revision: learningInteger(row.expected_revision, 2_147_483_647),
    consent: row.consent,
  };
}

export function parseAssignmentActivation(
  value: unknown, expected: LearningScope, context: SavedLearningContext,
  draftId?: string, revision?: number, activationId?: string,
): AssignmentActivation {
  const row = learningFields(value, ACTIVATION_FIELDS);
  const id = learningId(row.id), pinnedDraft = learningId(row.draft_id);
  const pinnedRevision = learningInteger(row.revision, 2_147_483_647);
  if (learningId(row.context_id) !== context.id
      || draftId !== undefined && pinnedDraft !== learningId(draftId)
      || revision !== undefined && pinnedRevision !== revision
      || activationId !== undefined && id !== learningId(activationId)) throw new TypeError("Invalid assignment activation");
  return {
    ...learningScope(row, expected), id, draft_id: pinnedDraft, context_id: context.id,
    revision: pinnedRevision, activated_at: learningDate(row.activated_at),
    activated_by: learningId(row.activated_by),
    draft: parseDraftRevision(row.draft, expected, context, pinnedDraft, pinnedRevision),
  };
}
