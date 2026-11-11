import { parseEvidence, type Evidence } from "./chat-contracts";
import {
  learningFields as fields, learningText as text, learningId as id,
  learningInteger as integer, learningDate as date, learningList as list,
  learningUnique as unique, learningScope as scope, learningDigest as digest,
  parseCommandKey, type DocumentationSnapshot, type LearningScope, type SavedLearningContext,
} from "./curriculum-contracts";

interface Objective { id: string; description: string; tutorial_segment_ids: string[] }
interface Requirement extends Objective { label: "covered" | "prerequisite" | "extension"; objective_ids: string[]; documentation_excerpt_ids: string[] }
interface Criterion { id: string; description: string; requirement_ids: string[] }
interface Rubric { id: string; description: string; acceptance_criterion_ids: string[] }
interface Hint { id: string; level: number; text: string; requirement_ids: string[] }
export interface AssignmentContent {
  schema_version: "assignment-draft-v1"; title: string; scenario: string; estimated_minutes: number;
  objectives: Objective[]; requirements: Requirement[]; constraints: string[]; deliverables: string[];
  acceptance_criteria: Criterion[]; rubric: Rubric[]; hints: Hint[];
}
export interface DraftSummary extends LearningScope { id: string; context_id: string; revision: number; title: string; created_at: string }
export interface DraftList { items: DraftSummary[]; next_after: string | null }
export interface DraftRevision extends LearningScope {
  id: string; context_id: string; revision: number; created_at: string; documentation_ids: string[];
  assignment: LearningScope & { draft: AssignmentContent & LearningScope; tutorial_evidence: Evidence[]; documentation_snapshots: DocumentationSnapshot[] };
}
export interface DraftReplaceBody { idempotency_key: string; expected_revision: number; content: AssignmentContent; documentation_ids: string[] }
function invalid(): never { throw new TypeError("Invalid saved assignment draft"); }
const CONTENT_KEYS = ["schema_version", "title", "scenario", "estimated_minutes", "objectives", "requirements", "constraints", "deliverables", "acceptance_criteria", "rubric", "hints"];
function localId(value: unknown): string { const result = text(value, 64); if (!/^[a-z][a-z0-9_-]{0,63}$/.test(result)) invalid(); return result; }
function ids(value: unknown, min: number, max: number, parse = id): string[] { const values = list(value, min, max).map(parse); unique(values); return values; }
function references(values: string[], targets: string[]): void { if (values.some((value) => !targets.includes(value))) invalid(); }
function equalSets(a: string[], b: string[]) { if (a.length !== b.length || a.some((item) => !b.includes(item))) invalid(); }
export function parseAssignmentContent(value: unknown): AssignmentContent {
  const row = fields(value, CONTENT_KEYS);
  if (row.schema_version !== "assignment-draft-v1") invalid();
  const objectives = list(row.objectives, 1, 20).map((value) => { const item = fields(value, ["id", "description", "tutorial_segment_ids"]); return { id: localId(item.id), description: text(item.description, 4000), tutorial_segment_ids: ids(item.tutorial_segment_ids, 1, 10) }; });
  const requirements = list(row.requirements, 1, 50).map((value) => {
    const item = fields(value, ["id", "description", "label", "objective_ids", "tutorial_segment_ids", "documentation_excerpt_ids"]);
    if (!["covered", "prerequisite", "extension"].includes(item.label as string)) invalid();
    const result: Requirement = { id: localId(item.id), description: text(item.description, 4000), label: item.label as Requirement["label"], objective_ids: ids(item.objective_ids, 1, 20, localId), tutorial_segment_ids: ids(item.tutorial_segment_ids, 0, 10), documentation_excerpt_ids: ids(item.documentation_excerpt_ids, 0, 10) };
    if (result.label === "covered" ? !result.tutorial_segment_ids.length : !result.documentation_excerpt_ids.length) invalid();
    return result;
  });
  const acceptance = list(row.acceptance_criteria, 1, 50).map((value) => { const item = fields(value, ["id", "description", "requirement_ids"]); return { id: localId(item.id), description: text(item.description, 4000), requirement_ids: ids(item.requirement_ids, 1, 20, localId) }; });
  const rubric = list(row.rubric, 1, 20).map((value) => { const item = fields(value, ["id", "description", "acceptance_criterion_ids"]); return { id: localId(item.id), description: text(item.description, 4000), acceptance_criterion_ids: ids(item.acceptance_criterion_ids, 1, 50, localId) }; });
  const hints = list(row.hints, 0, 10).map((value, index) => { const item = fields(value, ["id", "level", "text", "requirement_ids"]); if (integer(item.level, 10) !== index + 1) invalid(); return { id: localId(item.id), level: index + 1, text: text(item.text, 4000), requirement_ids: ids(item.requirement_ids, 1, 20, localId) }; });
  for (const group of [objectives, requirements, acceptance, rubric, hints]) unique(group.map((item) => item.id));
  for (const item of requirements) references(item.objective_ids, objectives.map((item) => item.id));
  for (const item of [...acceptance, ...hints]) references(item.requirement_ids, requirements.map((item) => item.id));
  for (const item of rubric) references(item.acceptance_criterion_ids, acceptance.map((item) => item.id));
  equalSets([...new Set(acceptance.flatMap((item) => item.requirement_ids))], requirements.map((item) => item.id));
  equalSets([...new Set(rubric.flatMap((item) => item.acceptance_criterion_ids))], acceptance.map((item) => item.id));
  const result: AssignmentContent = { schema_version: row.schema_version, title: text(row.title, 200), scenario: text(row.scenario, 4000), estimated_minutes: integer(row.estimated_minutes, 10_080), objectives, requirements, constraints: list(row.constraints, 0, 20).map((item) => text(item, 4000)), deliverables: list(row.deliverables, 1, 20).map((item) => text(item, 4000)), acceptance_criteria: acceptance, rubric, hints };
  if (new TextEncoder().encode(JSON.stringify(result)).length > 256_000) invalid();
  return result;
}
export function parseDraftReplace(value: unknown): DraftReplaceBody {
  const row = fields(value, ["idempotency_key", "expected_revision", "content", "documentation_ids"]);
  return { idempotency_key: parseCommandKey(row.idempotency_key), expected_revision: integer(row.expected_revision, 2_147_483_646), content: parseAssignmentContent(row.content), documentation_ids: ids(row.documentation_ids, 0, 20).sort() };
}
export function parseDraftList(value: unknown, expected: LearningScope, contextId: string, after?: string): DraftList {
  const row = fields(value, ["items", "next_after"]);
  const items = list(row.items, 0, 50).map((value) => {
    const item = fields(value, ["id", "tenant_id", "project_id", "context_id", "revision", "title", "created_at"]);
    if (id(item.context_id) !== id(contextId)) invalid();
    return { ...scope(item, expected), id: id(item.id), context_id: id(item.context_id), revision: integer(item.revision, 2_147_483_647), title: text(item.title, 200), created_at: date(item.created_at) };
  });
  unique(items.map((item) => item.id));
  if (items.some((item, i) => (i ? items[i - 1].id : after ?? "") >= item.id)) invalid();
  const next = row.next_after === null ? null : id(row.next_after);
  if (next && (!items.length || next !== items.at(-1)!.id)) invalid();
  return { items, next_after: next };
}
export function parseDraftRevision(value: unknown, expected: LearningScope, context: SavedLearningContext, draftId: string, revision?: number): DraftRevision {
  if (new TextEncoder().encode(JSON.stringify(value)).length > 5_000_000) invalid();
  const row = fields(value, ["id", "tenant_id", "project_id", "context_id", "revision", "created_at", "assignment", "documentation_ids"]);
  if (id(row.id) !== id(draftId) || id(row.context_id) !== context.id || revision !== undefined && row.revision !== revision) invalid();
  const assignment = fields(row.assignment, ["tenant_id", "project_id", "draft", "tutorial_evidence", "documentation_snapshots"]);
  scope(assignment, expected);
  const scopedContent = fields(assignment.draft, [...CONTENT_KEYS, "tenant_id", "project_id"]);
  scope(scopedContent, expected);
  const { tenant_id: _tenant, project_id: _project, ...rawContent } = scopedContent;
  void _tenant; void _project;
  const content = parseAssignmentContent(rawContent);
  if (content.estimated_minutes > context.learner.available_minutes) invalid();
  const selection = ids(row.documentation_ids, 0, 20);
  if (selection.join() !== [...selection].sort().join() || selection.length && !context.learner.allow_external_documentation) invalid();
  let characters = 0;
  const evidence = list(assignment.tutorial_evidence, 1, 500).map((value) => {
    const item = parseEvidence(value), pin = context.selected_sources.find((pin) => pin.source_id === item.source_id.toLowerCase());
    if (!pin || pin.generation !== item.generation || pin.processing_version !== item.processing_version || pin.source_filename !== item.source_filename || !["transcript", "frame"].includes(item.modality)) invalid();
    text(item.text, 10_000); characters += Array.from(item.text).length;
    return { ...item, segment_id: item.segment_id.toLowerCase(), source_id: item.source_id.toLowerCase() };
  });
  if (characters > 500_000) invalid(); unique(evidence.map((item) => item.segment_id));
  const documents = list(assignment.documentation_snapshots, 0, 20).map((value) => {
    const item = fields(value, ["id", "tenant_id", "project_id", "url", "retrieved_at", "detected_version", "content_sha256", "excerpts"]);
    const docId = id(item.id);
    if (!selection.includes(docId) || item.url !== "https://fastapi.tiangolo.com/tutorial/first-steps/" || item.detected_version !== null) invalid();
    const excerpts = list(item.excerpts, 1, 20).map((value) => { const excerpt = fields(value, ["id", "text", "content_sha256"]); return { id: id(excerpt.id), text: text(excerpt.text, 8000), content_sha256: digest(excerpt.content_sha256) }; });
    unique(excerpts.map((item) => item.id));
    return { ...scope(item, expected), id: docId, url: item.url, detected_version: null, retrieved_at: date(item.retrieved_at), content_sha256: digest(item.content_sha256), excerpts };
  });
  unique(documents.map((item) => item.id));
  const excerpts = documents.flatMap((item) => item.excerpts.map((item) => item.id)); unique(excerpts);
  const tutorialIds = [...new Set([...content.objectives, ...content.requirements].flatMap((item) => item.tutorial_segment_ids))];
  const docIds = [...new Set(content.requirements.flatMap((item) => item.documentation_excerpt_ids))];
  equalSets(tutorialIds, evidence.map((item) => item.segment_id)); equalSets(docIds, excerpts);
  for (const item of content.requirements) if (item.label === "prerequisite" && !context.learner.allow_prerequisites || item.label === "extension" && !context.learner.allow_extensions) invalid();
  return { ...scope(row, expected), id: id(row.id), context_id: context.id, revision: integer(row.revision, 2_147_483_647), created_at: date(row.created_at), documentation_ids: selection, assignment: { ...expected, draft: { ...expected, ...content }, tutorial_evidence: evidence, documentation_snapshots: documents } };
}
export function draftContent(revision: DraftRevision): AssignmentContent {
  const { tenant_id: _tenant, project_id: _project, ...content } = revision.assignment.draft;
  void _tenant; void _project;
  return parseAssignmentContent(content);
}
