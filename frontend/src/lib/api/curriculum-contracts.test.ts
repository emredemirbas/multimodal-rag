import { createHash, webcrypto } from "node:crypto";
import { beforeAll, describe, expect, it, vi } from "vitest";
import {
  assertContextInput, parseContextCreate, parseContextReceipt, parseDocumentApproval,
  parseDocumentList, parseDocumentView, parseDocumentationCatalog, parseSavedLearningContext,
  verifyCatalogIntegrity, verifyDocumentIntegrity,
} from "@/lib/api/curriculum-contracts";

const project = "10000000-0000-0000-0000-000000000001", context = "20000000-0000-0000-0000-000000000001", source = "30000000-0000-0000-0000-000000000001", document = "40000000-0000-0000-0000-000000000001";
const scope = { tenant_id: "local-test", project_id: project };
const preferences = { experience: "intermediate", difficulty: "beginner", language: "tr", available_minutes: 60, allow_prerequisites: false, allow_extensions: false, allow_external_documentation: true };
const pin = { source_id: source, generation: 1, processing_version: "transcript-chunks-v1:g1" };
const hash = (text: string) => createHash("sha256").update(text).digest("hex");
function policy() {
  const item = { id: "fastapi-first-steps-en", title: "FastAPI — First Steps (English)", url: "https://fastapi.tiangolo.com/tutorial/first-steps/", parser_version: "official-document-html-v1", version_policy: "unversioned; detected_version=unknown", license_name: "MIT", license_url: "https://github.com/fastapi/fastapi/blob/master/LICENSE", license_text: "MIT synthetic retained notice", attribution: "Synthetic test attribution" };
  return { ...item, fingerprint: hash(JSON.stringify(Object.fromEntries(Object.entries(item).sort(([a], [b]) => a.localeCompare(b))))) };
}
function receipt() {
  return { ...scope, id: context, created_at: "2026-11-11T10:00:00Z", request: { ...scope, learner: { ...preferences }, selected_sources: [{ ...scope, ...pin }] }, tutorial_snapshots: [{ pin: { ...scope, ...pin }, segments: [{ segment_id: "50000000-0000-0000-0000-000000000001", ...pin, source_filename: "synthetic.vtt", start_ms: 0, end_ms: 1000, text: "Untrusted tutorial text stays on the server", modality: "transcript", asr_origin: null, frame_id: null, visual_origin: null }] }] };
}
function captured() {
  const text = "from fastapi import FastAPI\napp = FastAPI()";
  return { ...scope, id: document, context_id: context, approved_by: "60000000-0000-0000-0000-000000000001", approved_at: "2026-11-11T10:00:00Z", consent: "retrieve_and_retain", policy: policy(), status: "captured", failure_code: null,
    snapshot: { ...scope, id: document, url: policy().url, retrieved_at: "2026-11-11T10:00:01+00:00", detected_version: null, content_sha256: hash(text), excerpts: [{ id: "70000000-0000-0000-0000-000000000001", text, content_sha256: hash(text) }] }, raw_sha256: hash("synthetic html"), raw_bytes: 120 };
}
beforeAll(() => { vi.stubGlobal("crypto", webcrypto); });

describe("strict learner-owned commands", () => {
  const body = () => ({ idempotency_key: "save-context-001", selected_sources: [{ ...pin }], learner: { ...preferences } });
  it("requires every explicit choice and preserves exact pins", () => {
    expect(parseContextCreate(body())).toEqual(body());
    for (const change of [{ ...body(), tenant_id: scope.tenant_id }, { ...body(), selected_sources: [] }, { ...body(), selected_sources: [pin, pin] }, { ...body(), learner: { ...preferences, allow_extensions: "false" } }, { ...body(), learner: { ...preferences, available_minutes: 60.5 } }, { ...body(), learner: { ...preferences, language: "de" } }, { ...body(), selected_sources: [{ ...pin, generation: "1" }] }]) expect(() => parseContextCreate(change)).toThrow();
    const missing = body(); delete (missing.learner as Partial<typeof preferences>).allow_prerequisites;
    expect(() => parseContextCreate(missing)).toThrow();
  });
  it("never accepts arbitrary document URLs or implied consent", () => {
    const approval = { idempotency_key: "approve-document-001", catalog_id: "fastapi-first-steps-en", catalog_sha256: policy().fingerprint, consent: "retrieve_and_retain" };
    expect(parseDocumentApproval(approval)).toEqual(approval);
    for (const change of [{ ...approval, url: "http://127.0.0.1" }, { ...approval, consent: true }, { ...approval, catalog_id: "arbitrary-page" }, { ...approval, catalog_sha256: "0".repeat(63) }]) expect(() => parseDocumentApproval(change)).toThrow();
  });
  it("projects full evidence to safe context labels and exact preferences", () => {
    const parsed = parseContextReceipt(receipt(), scope, context, parseContextCreate(body()));
    expect(parsed.selected_sources).toEqual([{ ...pin, source_filename: "synthetic.vtt" }]);
    expect(parsed.learner).toEqual(preferences);
    expect(JSON.stringify(parsed)).not.toMatch(/Untrusted tutorial|tutorial_snapshots|segment_id/);
    expect(parseSavedLearningContext(parsed, scope, context)).toEqual(parsed);
    expect(() => assertContextInput(parsed, parseContextCreate({ ...body(), learner: { ...preferences, language: "en" } }))).toThrow();
  });
  it("rejects mismatched scope, identities, snapshots, pins and evidence labels", () => {
    const changes: ((item: ReturnType<typeof receipt>) => void)[] = [
      (item) => { item.tenant_id = "other"; }, (item) => { item.request.project_id = context; },
      (item) => { item.tutorial_snapshots[0].pin.generation = 2; },
      (item) => { item.tutorial_snapshots[0].segments[0].generation = 2; },
      (item) => { item.tutorial_snapshots.push(item.tutorial_snapshots[0]); },
      (item) => { item.tutorial_snapshots[0].segments.push(item.tutorial_snapshots[0].segments[0]); },
      (item) => { item.tutorial_snapshots[0].segments[0].text = "x".repeat(10_001); },
    ];
    for (const change of changes) { const item = receipt(); change(item); expect(() => parseContextReceipt(item, scope, context)).toThrow(); }
    expect(() => parseContextReceipt(receipt(), scope, document)).toThrow();
  });
});

describe("documentation identity, license and integrity", () => {
  it("retains the full approved policy and verifies catalog fingerprints", async () => {
    const parsed = parseDocumentationCatalog([policy()]);
    expect(parsed[0].license_text).toBe(policy().license_text);
    expect(await verifyCatalogIntegrity(parsed)).toEqual(parsed);
    await expect(verifyCatalogIntegrity([{ ...parsed[0], license_text: "changed notice" }])).rejects.toThrow();
    expect(() => parseDocumentationCatalog([policy(), policy()])).toThrow();
    expect(() => parseDocumentationCatalog([{ ...policy(), url: "https://fastapi.tiangolo.com/elsewhere/" }])).toThrow();
  });
  it("verifies individual and full-text hashes and preserves unknown version", async () => {
    const parsed = parseDocumentView(captured(), scope, context, document);
    expect(await verifyDocumentIntegrity(parsed)).toEqual(parsed);
    expect(parsed.snapshot?.detected_version).toBeNull();
    const wrongText = captured(); wrongText.snapshot.excerpts[0].text = "different";
    await expect(verifyDocumentIntegrity(parseDocumentView(wrongText, scope))).rejects.toThrow();
    const wrongFullHash = captured(); wrongFullHash.snapshot.content_sha256 = "a".repeat(64);
    await expect(verifyDocumentIntegrity(parseDocumentView(wrongFullHash, scope))).rejects.toThrow();
  });
  it("rejects contradictory states and foreign or malformed snapshot metadata", () => {
    const item = captured();
    const changes = [
      { ...item, project_id: context }, { ...item, context_id: document }, { ...item, id: context },
      { ...item, status: "pending" }, { ...item, failure_code: "unsafe upstream text" }, { ...item, raw_bytes: 512_001 },
      { ...item, snapshot: { ...item.snapshot, id: context } }, { ...item, snapshot: { ...item.snapshot, tenant_id: "other" } },
      { ...item, snapshot: { ...item.snapshot, detected_version: "invented" } }, { ...item, snapshot: { ...item.snapshot, retrieved_at: "2026-11-11T10:00:01" } },
      { ...item, snapshot: { ...item.snapshot, retrieved_at: "2027-02-30T10:00:01Z" } },
      { ...item, snapshot: { ...item.snapshot, retrieved_at: "2026-11-10T10:00:01Z" } },
      { ...item, snapshot: { ...item.snapshot, excerpts: [item.snapshot.excerpts[0], item.snapshot.excerpts[0]] } },
    ];
    for (const changed of changes) expect(() => parseDocumentView(changed, scope, context, document)).toThrow();
    expect(() => parseDocumentList([item, item], scope, context)).toThrow();
  });
  it("applies UTF-8 limits, accepting Unicode text without truncation", () => {
    const item = captured(), excerpt = item.snapshot.excerpts[0];
    const excerpts = Array.from({length: 17}, (_, index) => ({ ...excerpt, id: `${index.toString(16).padStart(8, "0")}-0000-0000-0000-000000000001`, text: "ü".repeat(4000) }));
    expect(() => parseDocumentView({ ...item, snapshot: { ...item.snapshot, excerpts } }, scope)).toThrow();
    expect(parseDocumentView({ ...item, snapshot: { ...item.snapshot, excerpts: excerpts.slice(0, 16) } }, scope).snapshot?.excerpts).toHaveLength(16);
  });
});
