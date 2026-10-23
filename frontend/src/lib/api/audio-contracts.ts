import { UUID_PATTERN } from "@/lib/api/identifiers";

export const AUDIO_MAX_BYTES = 20_000_000;
export const AUDIO_WIRE_LIMIT = AUDIO_MAX_BYTES + 16_384;
export interface AudioCapability { enabled: boolean }
export interface AudioReceipt { project_id: string; source_id: string; job_id: string; deduplicated: boolean }

function record(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("Invalid audio response");
  return value as Record<string, unknown>;
}
function id(value: unknown): string {
  if (typeof value !== "string" || !UUID_PATTERN.test(value)) throw new Error("Invalid audio identifier");
  return value;
}
export function parseAudioCapability(value: unknown): AudioCapability {
  const row = record(value);
  if (typeof row.enabled !== "boolean" || row.max_bytes !== AUDIO_MAX_BYTES || row.max_duration_seconds !== 600
      || row.encoding !== "pcm-s16le-16000-mono" || row.processing_ttl_seconds !== 3600) throw new Error("Unverified audio limits");
  return { enabled: row.enabled };
}
export function parseAudioReceipt(value: unknown): AudioReceipt {
  const row = record(value);
  if (typeof row.deduplicated !== "boolean") throw new Error("Invalid audio receipt");
  return { project_id: id(row.project_id), source_id: id(row.source_id), job_id: id(row.job_id), deduplicated: row.deduplicated };
}
