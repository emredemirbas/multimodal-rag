import type { AsrOrigin, AudioRetention } from "../src/lib/api/provenance-contracts";

export const asrOrigin: AsrOrigin = {
  machine_generated: true, job_id: "42345678-1234-1234-1234-123456789abc", generation: 1,
  provider: "faster-whisper-local", model: "whisper-base", revision: "a80717a3a48b1b28aa687bca146cb7301feae1b1",
  profile: "local-whisper-base-v1:345860e60bc3a7b6f4930e6473ff42cff8ad987f4471d5c2ae0e970cd532e6eb",
  engine: "faster-whisper:1.2.1/ctranslate2:4.8.2", requested_language: "en",
  assembly_version: "asr-vtt-v1", completed_at: "2026-10-23T12:01:00+00:00",
};
export function audioRetention(status: AudioRetention["status"] = "temporary"): AudioRetention {
  return { status, processing_expires_at: "2026-10-23T13:00:00+00:00",
    cleanup_id: status === "temporary" || status === "expired" ? null : "52345678-1234-1234-1234-123456789abc",
    deleted_at: status === "deleted" ? "2026-10-23T12:02:00+00:00" : null };
}
