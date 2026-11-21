import { describe, expect, it } from "vitest";
import { context, projectId, documentId } from "@/components/curriculum/test-fixtures";
import { draftFixture, draftId } from "@/components/curriculum/draft-fixtures";
import { parseAssignmentActivate, parseAssignmentActivation } from "./activation-contracts";

const scope = { tenant_id: context.tenant_id, project_id: projectId };
const activationId = "92345678-1234-4234-8234-123456789abc";
const actorId = "a2345678-1234-4234-8234-123456789abc";
const receipt = () => ({ ...scope, id: activationId, draft_id: draftId, context_id: context.id, revision: 1, activated_at: "2026-11-21T09:00:00+03:00", activated_by: actorId, draft: draftFixture() });
const command = () => ({ idempotency_key: "activate-revision-001", expected_revision: 1, consent: "activate_reviewed_revision" });

describe("assignment activation contracts", () => {
  it("retains the immutable version, actor, aware timestamp and pinned draft", () => {
    expect(parseAssignmentActivation(receipt(), scope, context, draftId, 1, activationId)).toEqual(receipt());
    expect(parseAssignmentActivate(command())).toEqual(command());
    expect(parseAssignmentActivate({ ...command(), expected_revision: 2_147_483_647 }).expected_revision).toBe(2_147_483_647);
  });
  it.each(["tenant", "project", "context", "draft", "revision", "actor", "date", "extra", "pinned-context", "pinned-revision", "pinned-scope", "pinned-evidence"])("rejects mismatched or invalid %s metadata", (kind) => {
    const value = receipt();
    if (kind === "tenant") value.tenant_id = "foreign";
    if (kind === "project") value.project_id = documentId;
    if (kind === "context") value.context_id = documentId;
    if (kind === "draft") value.draft_id = documentId;
    if (kind === "revision") value.revision = 1.5;
    if (kind === "actor") value.activated_by = "unverified";
    if (kind === "date") value.activated_at = "2026-11-21T09:00:00";
    if (kind === "extra") Object.assign(value, { trusted: true });
    if (kind === "pinned-context") value.draft.context_id = documentId;
    if (kind === "pinned-revision") value.draft.revision = 2;
    if (kind === "pinned-scope") value.draft.assignment.project_id = documentId;
    if (kind === "pinned-evidence") value.draft.assignment.tutorial_evidence[0].generation = 2;
    expect(() => parseAssignmentActivation(value, scope, context, draftId, 1, activationId)).toThrow();
  });
  it("matches exact assignment IDs, draft targets and expected revisions", () => {
    expect(() => parseAssignmentActivation(receipt(), scope, context, draftId, 2)).toThrow();
    expect(() => parseAssignmentActivation(receipt(), scope, context, documentId)).toThrow();
    expect(() => parseAssignmentActivation(receipt(), scope, context, draftId, 1, documentId)).toThrow();
  });
  it.each([
    { consent: true }, { consent: "retrieve_and_retain" }, { expected_revision: 0 },
    { expected_revision: 1.5 }, { expected_revision: "1" }, { expected_revision: 2_147_483_648 },
    { idempotency_key: "short" }, { idempotency_key: "has spaces" }, { tenant_id: "foreign" },
  ])("requires explicit consent, bounded revision, command key and no browser scope: %j", (change) => {
    expect(() => parseAssignmentActivate({ ...command(), ...change })).toThrow();
  });
});
