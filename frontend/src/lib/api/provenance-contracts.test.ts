import { describe, expect, it } from "vitest";
import { parseAsrOrigin, parseAudioRetention } from "@/lib/api/provenance-contracts";
import { parseSourceList } from "@/lib/api/source-contracts";
import { parseEvidence, parseTurn } from "@/lib/api/chat-contracts";
import { parseTranscriptPage } from "@/lib/api/transcript-contracts";
import { asrOrigin, audioRetention } from "../../../test-support/media-fixture";
import { transcriptFixture, sourceId } from "../../../test-support/transcript-fixture";

describe("typed media provenance", () => {
  it("accepts legacy absence without asserting human review and drops internal fields", () => {
    expect(parseAsrOrigin(undefined)).toBeNull();
    expect(parseAudioRetention(null)).toBeNull();
    expect(parseAsrOrigin({ ...asrOrigin, input_sha256: "private", object_key: "private", result: "private" })).toEqual(asrOrigin);
  });
  it("rejects invalid identity, false machine labels, oversized metadata and coercible types", () => {
    for (const patch of [{ job_id: "../../other" }, { generation: 0 }, { generation: true }, { generation: "1" }, { generation: 2_147_483_648 },
      { machine_generated: false }, { machine_generated: "true" }, { requested_language: "de" }, { requested_language: ["en"] },
      { provider: "" }, { profile: "x".repeat(201) }, { engine: {} }, { completed_at: "tomorrow" }, { completed_at: "2026-10-23" }]) {
      expect(() => parseAsrOrigin({ ...asrOrigin, ...patch })).toThrow();
    }
    expect(() => parseAsrOrigin([])).toThrow();
  });
  it("separates original expiry and retirement from confirmed deletion", () => {
    for (const status of ["temporary", "expired", "cleanup_pending", "cleanup_failed", "deleted"] as const) {
      expect(parseAudioRetention(audioRetention(status))).toEqual(audioRetention(status));
    }
    for (const patch of [{ status: "completed" }, { status: ["temporary"] }, { deleted_at: asrOrigin.completed_at },
      { cleanup_id: asrOrigin.job_id }, { processing_expires_at: "bad" }]) {
      expect(() => parseAudioRetention({ ...audioRetention(), ...patch })).toThrow();
    }
    expect(() => parseAudioRetention({ ...audioRetention("deleted"), deleted_at: null })).toThrow();
    expect(() => parseAudioRetention({ ...audioRetention("cleanup_failed"), cleanup_id: null })).toThrow();
    expect(() => parseAudioRetention({ ...audioRetention("cleanup_pending"), deleted_at: asrOrigin.completed_at })).toThrow();
  });
  it("preserves source origin and cleanup state through both BFF parsing passes", () => {
    const source = { id: sourceId, filename: "owned.vtt", status: "ready", generation: 2, active_generation: 2,
      segment_count: 1, provider: "upload", job: null, failure_code: null, asr_origin: asrOrigin, audio_retention: audioRetention("cleanup_failed") };
    const parsed = parseSourceList({ items: [source] });
    expect(parsed[0].asr_origin).toEqual(asrOrigin);
    expect(parsed[0].audio_retention).toEqual(audioRetention("cleanup_failed"));
    expect(parseSourceList({ items: parsed })).toEqual(parsed);
    expect(() => parseSourceList({ items: [{ ...source, asr_origin: { ...asrOrigin, machine_generated: false } }] })).toThrow();
  });
  it("carries pinned origins in citations, history and evidence but rejects a future ASR generation", () => {
    const evidence = { ...transcriptFixture().items[0], generation: 2, asr_origin: asrOrigin };
    expect(parseEvidence(evidence).asr_origin).toEqual(asrOrigin);
    const turn = { id: sourceId, sequence: 1, question: "What is health?", source_ids: [], created_at: asrOrigin.completed_at,
      response: { answer: "GET /health", abstained: false, citations: [evidence], provider: "local", model: "extractive" } };
    expect(parseTurn(turn).response.citations[0].asr_origin).toEqual(asrOrigin);
    expect(() => parseEvidence({ ...evidence, asr_origin: { ...asrOrigin, generation: 3 } })).toThrow();
  });
  it("rejects mixed page/segment model origins and never assigns a published origin to unfinished text", () => {
    const fixture = transcriptFixture();
    const generated = { ...fixture, asr_origin: asrOrigin, items: fixture.items.map((item) => ({ ...item, asr_origin: asrOrigin })) };
    expect(parseTranscriptPage(generated).asr_origin).toEqual(asrOrigin);
    for (const origin of [null, { ...asrOrigin, job_id: sourceId }, { ...asrOrigin, profile: "different-model-profile" }]) {
      expect(() => parseTranscriptPage({ ...generated, items: [{ ...generated.items[0], asr_origin: origin }, ...generated.items.slice(1)] })).toThrow();
    }
    expect(() => parseTranscriptPage({ ...generated, generation: null, active_generation: null, processing_version: null,
      items: [], total_segments: 0, total_pages: 0 })).toThrow();
  });
});
