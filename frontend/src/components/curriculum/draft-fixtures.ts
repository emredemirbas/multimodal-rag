import type { DraftRevision } from "@/lib/api/draft-contracts";
import { context, projectId, sourceId } from "./test-fixtures";
export const draftId = "72345678-1234-4234-8234-123456789abc";
export const segmentId = "82345678-1234-4234-8234-123456789abc";
export function draftFixture(revision = 1): DraftRevision {
  const scope = { tenant_id: context.tenant_id, project_id: projectId };
  return { ...scope, id: draftId, context_id: context.id, revision, created_at: "2026-11-11T12:05:00Z", documentation_ids: [], assignment: { ...scope, draft: {
    ...scope, schema_version: "assignment-draft-v1", title: "Synthetic route exercise", scenario: "Build the tutorial health endpoint.", estimated_minutes: 45,
    objectives: [{ id: "route", description: "Expose a health route.", tutorial_segment_ids: [segmentId] }],
    requirements: [{ id: "health", label: "covered", description: "Expose GET /health.", objective_ids: ["route"], tutorial_segment_ids: [segmentId], documentation_excerpt_ids: [] }],
    constraints: ["Use the tutorial structure."], deliverables: ["Application code."], acceptance_criteria: [{ id: "responds", description: "The route responds.", requirement_ids: ["health"] }],
    rubric: [{ id: "behavior", description: "The response matches the criterion.", acceptance_criterion_ids: ["responds"] }], hints: [{ id: "hint", level: 1, text: "Find the route registration.", requirement_ids: ["health"] }],
  }, tutorial_evidence: [{ segment_id: segmentId, source_id: sourceId, source_filename: "lesson.vtt", start_ms: 1000, end_ms: 4000, text: "create_app exposes GET /health. <script>unsafe()</script>", modality: "transcript", generation: 1, processing_version: context.selected_sources[0].processing_version, asr_origin: null, frame_id: null, visual_origin: null }], documentation_snapshots: [] } };
}
export function rawContextFixture() { return { tenant_id: context.tenant_id, project_id: context.project_id, id: context.id, created_at: context.created_at, request: { tenant_id: context.tenant_id, project_id: context.project_id, selected_sources: context.selected_sources.map(({source_filename: _filename, ...pin}) => { void _filename; return { tenant_id: context.tenant_id, project_id: context.project_id, ...pin }; }), learner: context.learner }, tutorial_snapshots: [{ pin: { tenant_id: context.tenant_id, project_id: context.project_id, source_id: sourceId, generation: 1, processing_version: context.selected_sources[0].processing_version }, segments: draftFixture().assignment.tutorial_evidence }] }; }
