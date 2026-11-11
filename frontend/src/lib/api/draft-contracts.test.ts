import { describe, expect, it } from "vitest";
import { draftContent, parseAssignmentContent, parseDraftList, parseDraftReplace, parseDraftRevision } from "./draft-contracts";
import { context, projectId, documentId, excerptId } from "@/components/curriculum/test-fixtures";
import { draftFixture, draftId } from "@/components/curriculum/draft-fixtures";
const scope = { tenant_id: context.tenant_id, project_id: projectId };
const parse = (value: unknown) => parseDraftRevision(value, scope, context, draftId);
describe("saved draft evidence and structure boundary", () => {
  it("preserves the exact content, pinned evidence and empty document selection", () => {
    const input = draftFixture(); expect(parse(input)).toEqual(input);
    expect(parseDraftReplace({ idempotency_key: "replace-key-001", expected_revision: 1, content: draftContent(input), documentation_ids: [] })).toMatchObject({ expected_revision: 1, documentation_ids: [] });
  });
  it.each(["tenant", "project", "context", "draft", "pin", "filename", "generation", "missing", "extra", "effort", "unknown"]) ("rejects a mismatched %s receipt", (kind) => {
    const value = draftFixture();
    if (kind === "tenant") value.assignment.tenant_id = "foreign";
    if (kind === "project") value.assignment.draft.project_id = documentId;
    if (kind === "context") value.context_id = documentId;
    if (kind === "draft") value.id = documentId;
    if (kind === "pin") value.assignment.tutorial_evidence[0].processing_version = "newer";
    if (kind === "filename") value.assignment.tutorial_evidence[0].source_filename = "foreign.vtt";
    if (kind === "generation") value.assignment.tutorial_evidence[0].generation = 2;
    if (kind === "missing") value.assignment.tutorial_evidence = [];
    if (kind === "extra") value.assignment.tutorial_evidence.push({ ...value.assignment.tutorial_evidence[0], segment_id: documentId });
    if (kind === "effort") value.assignment.draft.estimated_minutes = context.learner.available_minutes + 1;
    if (kind === "unknown") Object.assign(value.assignment.draft, { trusted: true });
    expect(() => parse(value)).toThrow();
  });
  it("rejects duplicate and incomplete rubric/reference graphs or invalid hint order", () => {
    const changes = [
      (value: ReturnType<typeof draftContent>) => { value.requirements[0].objective_ids = ["missing"]; },
      (value: ReturnType<typeof draftContent>) => { value.objectives.push(value.objectives[0]); },
      (value: ReturnType<typeof draftContent>) => { value.rubric[0].acceptance_criterion_ids = ["missing"]; },
      (value: ReturnType<typeof draftContent>) => { value.acceptance_criteria[0].requirement_ids = ["missing"]; },
      (value: ReturnType<typeof draftContent>) => { value.hints[0].level = 2; },
      (value: ReturnType<typeof draftContent>) => { value.requirements[0].tutorial_segment_ids = []; },
    ];
    for (const change of changes) { const value = draftContent(draftFixture()); change(value); expect(() => parseAssignmentContent(value)).toThrow(); }
  });
  it("requires external permission, explicit selection and a separately cited excerpt", () => {
    const value = draftFixture(); value.documentation_ids = [documentId];
    value.assignment.documentation_snapshots = [{ ...scope, id: documentId, url: "https://fastapi.tiangolo.com/tutorial/first-steps/", retrieved_at: "2026-11-11T12:02:00Z", detected_version: null, content_sha256: "a".repeat(64), excerpts: [{ id: excerptId, text: "A separate extension.", content_sha256: "b".repeat(64) }] }];
    value.assignment.draft.requirements[0].label = "extension"; value.assignment.draft.requirements[0].documentation_excerpt_ids = [excerptId];
    expect(() => parse(value)).toThrow();
    const allowed = { ...context, learner: { ...context.learner, allow_extensions: true } };
    expect(parseDraftRevision(value, scope, allowed, draftId).assignment.draft.requirements[0].label).toBe("extension");
    value.documentation_ids = []; expect(() => parseDraftRevision(value, scope, allowed, draftId)).toThrow();
  });
  it("validates discovery scope, sort order and continuation identity", () => {
    const { id, tenant_id, project_id, context_id, revision, created_at } = draftFixture();
    const item = { id, tenant_id, project_id, context_id, revision, created_at, title: "Untrusted <script>title</script>" };
    expect(parseDraftList({ items: [item], next_after: id }, scope, context.id)).toMatchObject({ next_after: id });
    for (const bad of [{ items: [item, item], next_after: null }, { items: [{ ...item, context_id: documentId }], next_after: null }, { items: [{ ...item, tenant_id: "other" }], next_after: null }, { items: [item], next_after: documentId }]) expect(() => parseDraftList(bad, scope, context.id)).toThrow();
    expect(() => parseDraftList({ items: [item], next_after: null }, scope, context.id, id)).toThrow();
  });
});
