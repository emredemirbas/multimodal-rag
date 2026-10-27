import { UUID_PATTERN } from "@/lib/api/identifiers";

export interface AsrOrigin {
  machine_generated: true;
  job_id: string;
  generation: number;
  provider: string;
  model: string;
  revision: string;
  profile: string;
  engine: string;
  requested_language: "auto" | "en" | "tr";
  assembly_version: string;
  completed_at: string;
}

export interface AudioRetention {
  status: "temporary" | "expired" | "cleanup_pending" | "cleanup_failed" | "deleted";
  processing_expires_at: string;
  cleanup_id: string | null;
  deleted_at: string | null;
}
export type VideoRetention = AudioRetention;
export const parseVideoRetention = (value: unknown): VideoRetention | null => parseAudioRetention(value);

function record(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("Invalid media provenance");
  return value as Record<string, unknown>;
}
function text(value: unknown, maximum: number): string {
  if (typeof value !== "string" || !value.trim() || value.length > maximum) throw new Error("Invalid media provenance text");
  return value;
}
function identifier(value: unknown): string {
  const result = text(value, 36);
  if (!UUID_PATTERN.test(result)) throw new Error("Invalid media provenance identifier");
  return result.toLowerCase();
}
function date(value: unknown): string {
  const result = text(value, 80);
  if (!/^\d{4}-\d{2}-\d{2}T.*(?:Z|[+-]\d{2}:\d{2})$/.test(result) || Number.isNaN(Date.parse(result))) throw new Error("Invalid media provenance date");
  return result;
}

// Missing fields are compatible with older API responses, not proof of human review.
export function parseAsrOrigin(value: unknown): AsrOrigin | null {
  if (value == null) return null;
  const row = record(value);
  if (row.machine_generated !== true || typeof row.generation !== "number" || !Number.isSafeInteger(row.generation)
      || row.generation < 1 || row.generation > 2_147_483_647 || (row.requested_language !== "auto" && row.requested_language !== "en" && row.requested_language !== "tr")) throw new Error("Invalid ASR origin");
  return { machine_generated: true, job_id: identifier(row.job_id), generation: row.generation,
    provider: text(row.provider, 64), model: text(row.model, 128), revision: text(row.revision, 128),
    profile: text(row.profile, 200), engine: text(row.engine, 128), requested_language: row.requested_language as AsrOrigin["requested_language"],
    assembly_version: text(row.assembly_version, 120), completed_at: date(row.completed_at) };
}

export function parseAudioRetention(value: unknown): AudioRetention | null {
  if (value == null) return null;
  const row = record(value);
  if (typeof row.status !== "string" || !["temporary", "expired", "cleanup_pending", "cleanup_failed", "deleted"].includes(row.status)) throw new Error("Invalid audio retention status");
  const cleanup = row.cleanup_id === null ? null : identifier(row.cleanup_id);
  const deleted = row.deleted_at === null ? null : date(row.deleted_at);
  const retired = ["cleanup_pending", "cleanup_failed", "deleted"].includes(row.status);
  if (retired !== (cleanup !== null) || (row.status === "deleted") !== (deleted !== null)) throw new Error("Inconsistent audio retention status");
  return { status: row.status as AudioRetention["status"], processing_expires_at: date(row.processing_expires_at), cleanup_id: cleanup, deleted_at: deleted };
}
