import { UUID_PATTERN } from "@/lib/api/identifiers";
import { parseEvidence } from "@/lib/api/chat-contracts";

export interface LearningScope { tenant_id: string; project_id: string }
export interface LearnerPreferences {
  experience: "beginner" | "intermediate" | "advanced";
  difficulty: "beginner" | "intermediate" | "advanced";
  language: "en" | "tr";
  available_minutes: number;
  allow_prerequisites: boolean;
  allow_extensions: boolean;
  allow_external_documentation: boolean;
}
export interface SourcePin { source_id: string; generation: number; processing_version: string }
export interface BrowserContextCreateBody { idempotency_key: string; selected_sources: SourcePin[]; learner: LearnerPreferences }
export interface SavedLearningContext extends LearningScope {
  id: string; created_at: string; learner: LearnerPreferences;
  selected_sources: (SourcePin & { source_filename: string })[];
}
export interface CatalogPolicy {
  id: string; title: string; url: string; parser_version: string; version_policy: string;
  license_name: string; license_url: string; license_text: string; attribution: string; fingerprint: string;
}
export interface DocumentationExcerpt { id: string; text: string; content_sha256: string }
export interface DocumentationSnapshot extends LearningScope {
  id: string; url: string; retrieved_at: string; detected_version: null;
  content_sha256: string; excerpts: DocumentationExcerpt[];
}
export interface DocumentView extends LearningScope {
  id: string; context_id: string; approved_by: string; approved_at: string;
  consent: "retrieve_and_retain"; policy: CatalogPolicy;
  status: "pending" | "capturing" | "failed" | "captured";
  failure_code: string | null; snapshot: DocumentationSnapshot | null;
  raw_sha256: string | null; raw_bytes: number | null;
}
export interface DocumentApproveBody {
  idempotency_key: string; catalog_id: string; catalog_sha256: string; consent: "retrieve_and_retain";
}
export interface DocumentCaptureBody { idempotency_key: string }

const POLICY_KEYS = ["id", "title", "url", "parser_version", "version_policy", "license_name", "license_url", "license_text", "attribution", "fingerprint"];
const PREFERENCE_KEYS = ["experience", "difficulty", "language", "available_minutes", "allow_prerequisites", "allow_extensions", "allow_external_documentation"];
export const DOCUMENT_FAILURE_CODES = ["documentation_capture_lost", "documentation_fetch_timeout", "documentation_fetch_unavailable", "documentation_fetch_invalid", "documentation_fetch_not_allowed", "documentation_fetch_busy"] as const;
function invalid(): never { throw new TypeError("Invalid learning response"); }
function record(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) return invalid();
  return value as Record<string, unknown>;
}
function fields(value: unknown, keys: readonly string[]): Record<string, unknown> {
  const row = record(value);
  if (Object.keys(row).length !== keys.length || Object.keys(row).some((key) => !keys.includes(key))) invalid();
  return row;
}
function text(value: unknown, max: number): string {
  if (typeof value !== "string" || !value.trim() || Array.from(value).length > max || value.includes("\0") || /[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(?<![\uD800-\uDBFF])[\uDC00-\uDFFF]/u.test(value)) return invalid();
  return value;
}
function identifier(value: unknown): string { const result = text(value, 36); if (!UUID_PATTERN.test(result)) invalid(); return result.toLowerCase(); }
function integer(value: unknown, max: number): number { if (typeof value !== "number" || !Number.isSafeInteger(value) || value < 1 || value > max) return invalid(); return value; }
function digest(value: unknown): string { if (typeof value !== "string" || !/^[a-f0-9]{64}$/.test(value)) return invalid(); return value; }
function date(value: unknown): string {
  const result = text(value, 50), match = /^(\d{4})-(\d\d)-(\d\d)T(\d\d):(\d\d):(\d\d)(?:\.\d{1,6})?(?:Z|[+-](\d\d):(\d\d))$/.exec(result);
  if (!match || !Number.isFinite(Date.parse(result))) return invalid();
  const [, year, month, day, hour, minute, second, offsetHour = "0", offsetMinute = "0"] = match.map(Number);
  const days = [31, year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0) ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  if (year < 1 || month < 1 || month > 12 || day < 1 || day > days[month - 1] || hour > 23 || minute > 59 || second > 59 || Number(offsetHour) > 23 || Number(offsetMinute) > 59) invalid();
  return result;
}
function list(value: unknown, min: number, max: number): unknown[] { if (!Array.isArray(value) || value.length < min || value.length > max) return invalid(); return value; }
function unique(values: string[]): void { if (new Set(values).size !== values.length) invalid(); }
function scope(row: Record<string, unknown>, expected: LearningScope): LearningScope {
  const tenant = text(row.tenant_id, 64), project = identifier(row.project_id);
  if (!/^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$/.test(tenant) || tenant !== expected.tenant_id || project !== identifier(expected.project_id)) invalid();
  return { tenant_id: tenant, project_id: project };
}
export function parseLearnerPreferences(value: unknown): LearnerPreferences {
  const row = fields(value, PREFERENCE_KEYS);
  if (!["beginner", "intermediate", "advanced"].includes(row.experience as string) || !["beginner", "intermediate", "advanced"].includes(row.difficulty as string)
      || !["en", "tr"].includes(row.language as string) || [row.allow_prerequisites, row.allow_extensions, row.allow_external_documentation].some((flag) => typeof flag !== "boolean")) invalid();
  return { experience: row.experience as LearnerPreferences["experience"], difficulty: row.difficulty as LearnerPreferences["difficulty"], language: row.language as LearnerPreferences["language"], available_minutes: integer(row.available_minutes, 10_080), allow_prerequisites: row.allow_prerequisites as boolean, allow_extensions: row.allow_extensions as boolean, allow_external_documentation: row.allow_external_documentation as boolean };
}
function sourcePin(row: Record<string, unknown>): SourcePin { return { source_id: identifier(row.source_id), generation: integer(row.generation, 2_147_483_647), processing_version: text(row.processing_version, 200) }; }
export function parseContextCreate(value: unknown): BrowserContextCreateBody {
  const row = fields(value, ["idempotency_key", "selected_sources", "learner"]);
  const pins = list(row.selected_sources, 1, 20).map((pin) => sourcePin(fields(pin, ["source_id", "generation", "processing_version"])));
  unique(pins.map((pin) => pin.source_id));
  return { idempotency_key: parseCommandKey(row.idempotency_key), selected_sources: pins, learner: parseLearnerPreferences(row.learner) };
}
export function parseCommandKey(value: unknown): string { if (typeof value !== "string" || !/^[a-zA-Z0-9_-]{8,128}$/.test(value)) return invalid(); return value; }
export function parseDocumentApproval(value: unknown): DocumentApproveBody {
  const row = fields(value, ["idempotency_key", "catalog_id", "catalog_sha256", "consent"]);
  if (row.catalog_id !== "fastapi-first-steps-en" || row.consent !== "retrieve_and_retain") invalid();
  return { idempotency_key: parseCommandKey(row.idempotency_key), catalog_id: row.catalog_id, catalog_sha256: digest(row.catalog_sha256), consent: row.consent };
}
export function parseDocumentCapture(value: unknown): DocumentCaptureBody { const row = fields(value, ["idempotency_key"]); return { idempotency_key: parseCommandKey(row.idempotency_key) }; }
export function parseSavedLearningContext(value: unknown, expected: LearningScope, contextId?: string): SavedLearningContext {
  const row = fields(value, ["id", "tenant_id", "project_id", "created_at", "learner", "selected_sources"]);
  const id = identifier(row.id);
  if (contextId && id !== identifier(contextId)) invalid();
  const pins = list(row.selected_sources, 1, 20).map((pin) => { const item = fields(pin, ["source_id", "generation", "processing_version", "source_filename"]); return { ...sourcePin(item), source_filename: text(item.source_filename, 255) }; });
  unique(pins.map((pin) => pin.source_id));
  return { ...scope(row, expected), id, created_at: date(row.created_at), learner: parseLearnerPreferences(row.learner), selected_sources: pins };
}
export function assertContextInput(context: SavedLearningContext, body: BrowserContextCreateBody): void {
  if (JSON.stringify(context.learner) !== JSON.stringify(parseLearnerPreferences(body.learner))) invalid();
  const pins = (values: SourcePin[]) => values.map(({source_id, generation, processing_version}) => ({ source_id, generation, processing_version })).sort((a, b) => a.source_id.localeCompare(b.source_id));
  if (JSON.stringify(pins(context.selected_sources)) !== JSON.stringify(pins(body.selected_sources))) invalid();
}
/** Validate scope and every copied evidence pin, then expose only learner choices/labels. */
export function parseContextReceipt(value: unknown, expected: LearningScope, contextId?: string, input?: BrowserContextCreateBody): SavedLearningContext {
  if (new TextEncoder().encode(JSON.stringify(value)).byteLength > 4_100_000) invalid();
  const row = fields(value, ["id", "tenant_id", "project_id", "created_at", "request", "tutorial_snapshots"]);
  scope(row, expected);
  const request = fields(row.request, ["tenant_id", "project_id", "selected_sources", "learner"]);
  scope(request, expected);
  const pins = list(request.selected_sources, 1, 20).map((value) => { const pin = fields(value, ["tenant_id", "project_id", "source_id", "generation", "processing_version"]); scope(pin, expected); return sourcePin(pin); });
  unique(pins.map((pin) => pin.source_id));
  const snapshots = list(row.tutorial_snapshots, 1, 20);
  if (snapshots.length !== pins.length) invalid();
  let segments = 0, characters = 0;
  const segmentIds: string[] = [], snapshotIds: string[] = [];
  const selected = snapshots.map((value) => {
    const snapshot = fields(value, ["pin", "segments"]), rawPin = fields(snapshot.pin, ["tenant_id", "project_id", "source_id", "generation", "processing_version"]);
    scope(rawPin, expected);
    const pin = sourcePin(rawPin), selected = pins.find((item) => item.source_id === pin.source_id);
    if (!selected || JSON.stringify(pin) !== JSON.stringify(selected)) invalid();
    snapshotIds.push(pin.source_id);
    let filename: string | undefined;
    for (const raw of list(snapshot.segments, 1, 500)) {
      const evidence = parseEvidence(raw);
      if (evidence.source_id.toLowerCase() !== pin.source_id || evidence.generation !== pin.generation || evidence.processing_version !== pin.processing_version) invalid();
      const label = text(evidence.source_filename, 255);
      if (filename !== undefined && filename !== label) invalid();
      filename = label;
      text(evidence.text, 10_000);
      if (!["transcript", "frame"].includes(evidence.modality) || evidence.modality === "frame" && evidence.asr_origin !== null) invalid();
      segmentIds.push(evidence.segment_id.toLowerCase());
      segments += 1; characters += Array.from(evidence.text).length;
      if (segments > 500 || characters > 500_000) invalid();
    }
    return { ...pin, source_filename: filename! };
  });
  unique(snapshotIds); unique(segmentIds);
  const result = parseSavedLearningContext({ id: row.id, tenant_id: row.tenant_id, project_id: row.project_id, created_at: row.created_at, learner: request.learner, selected_sources: selected }, expected, contextId);
  if (input) assertContextInput(result, input);
  return result;
}
function policy(value: unknown): CatalogPolicy {
  const row = fields(value, POLICY_KEYS);
  if (row.id !== "fastapi-first-steps-en" || row.url !== "https://fastapi.tiangolo.com/tutorial/first-steps/" || row.parser_version !== "official-document-html-v1"
      || row.version_policy !== "unversioned; detected_version=unknown" || row.license_name !== "MIT" || row.license_url !== "https://github.com/fastapi/fastapi/blob/master/LICENSE") invalid();
  return { id: row.id, title: text(row.title, 200), url: row.url, parser_version: row.parser_version, version_policy: row.version_policy, license_name: row.license_name, license_url: row.license_url, license_text: text(row.license_text, 12_000), attribution: text(row.attribution, 1000), fingerprint: digest(row.fingerprint) };
}
export function parseDocumentationCatalog(value: unknown): CatalogPolicy[] { const items = list(value, 1, 20).map(policy); unique(items.map((item) => item.id)); return items; }
export function parseDocumentView(value: unknown, expected: LearningScope, contextId?: string, documentId?: string): DocumentView {
  const row = fields(value, ["id", "tenant_id", "project_id", "context_id", "approved_by", "approved_at", "consent", "policy", "status", "failure_code", "snapshot", "raw_sha256", "raw_bytes"]);
  const scoped = scope(row, expected), id = identifier(row.id), context = identifier(row.context_id);
  if (contextId && context !== identifier(contextId) || documentId && id !== identifier(documentId) || row.consent !== "retrieve_and_retain" || !["pending", "capturing", "failed", "captured"].includes(row.status as string)) invalid();
  const approvedAt = date(row.approved_at), documentPolicy = policy(row.policy);
  let snapshot: DocumentationSnapshot | null = null;
  if (row.status === "captured") {
    const saved = fields(row.snapshot, ["id", "tenant_id", "project_id", "url", "retrieved_at", "detected_version", "content_sha256", "excerpts"]);
    scope(saved, expected);
    if (identifier(saved.id) !== id || saved.url !== documentPolicy.url || saved.detected_version !== null || row.failure_code !== null) invalid();
    const retrieved = date(saved.retrieved_at);
    if (Date.parse(retrieved) < Date.parse(approvedAt)) invalid();
    const excerpts = list(saved.excerpts, 1, 20).map((value) => { const item = fields(value, ["id", "text", "content_sha256"]); return { id: identifier(item.id), text: text(item.text, 8000), content_sha256: digest(item.content_sha256) }; });
    unique(excerpts.map((item) => item.id));
    if (new TextEncoder().encode(excerpts.map((item) => item.text).join("")).byteLength > 128_000) invalid();
    snapshot = { ...scoped, id, url: documentPolicy.url, retrieved_at: retrieved, detected_version: null, content_sha256: digest(saved.content_sha256), excerpts };
    digest(row.raw_sha256); integer(row.raw_bytes, 512_000);
  } else if (row.snapshot !== null || row.raw_sha256 !== null || row.raw_bytes !== null) invalid();
  if (row.status === "failed" ? !DOCUMENT_FAILURE_CODES.includes(row.failure_code as typeof DOCUMENT_FAILURE_CODES[number]) : row.failure_code !== null) invalid();
  return { ...scoped, id, context_id: context, approved_by: identifier(row.approved_by), approved_at: approvedAt, consent: "retrieve_and_retain", policy: documentPolicy, status: row.status as DocumentView["status"], failure_code: row.failure_code as string | null, snapshot, raw_sha256: row.raw_sha256 as string | null, raw_bytes: row.raw_bytes as number | null };
}
export function parseDocumentList(value: unknown, expected: LearningScope, contextId: string): DocumentView[] { const items = list(value, 0, 20).map((item) => parseDocumentView(item, expected, contextId)); unique(items.map((item) => item.id)); return items; }
async function sha256(value: string): Promise<string> { const buffer = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value)); return Array.from(new Uint8Array(buffer), (byte) => byte.toString(16).padStart(2, "0")).join(""); }
async function verifyPolicy(item: CatalogPolicy): Promise<void> {
  const data = Object.fromEntries(Object.entries(item).filter(([key]) => key !== "fingerprint").sort(([a], [b]) => a.localeCompare(b)));
  if (await sha256(JSON.stringify(data)) !== item.fingerprint) invalid();
}
export async function verifyCatalogIntegrity(items: CatalogPolicy[]): Promise<CatalogPolicy[]> { await Promise.all(items.map(verifyPolicy)); return items; }
export async function verifyDocumentIntegrity(item: DocumentView): Promise<DocumentView> {
  await verifyPolicy(item.policy);
  if (item.snapshot) {
    for (const excerpt of item.snapshot.excerpts) if (await sha256(excerpt.text) !== excerpt.content_sha256) invalid();
    if (await sha256(item.snapshot.excerpts.map((excerpt) => excerpt.text).join("")) !== item.snapshot.content_sha256) invalid();
  }
  return item;
}

// Shared strict value checks for the adjacent draft boundary.
export { fields as learningFields, text as learningText, identifier as learningId,
  integer as learningInteger, date as learningDate, list as learningList,
  unique as learningUnique, scope as learningScope, digest as learningDigest };
