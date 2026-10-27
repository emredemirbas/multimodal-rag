import { UUID_PATTERN } from '@/lib/api/identifiers';
export const VIDEO_MAX_BYTES = 100_000_000;
export const VIDEO_WIRE_LIMIT = VIDEO_MAX_BYTES + 16_384;
export interface VideoCapability { enabled: boolean }
export interface VideoReceipt { project_id: string; source_id: string; job_id: string; deduplicated: boolean }

function record(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('Invalid video response');
  return value as Record<string, unknown>;
}
export function parseVideoCapability(value: unknown): VideoCapability {
  const row = record(value);
  if (typeof row.enabled !== 'boolean' || row.max_bytes !== VIDEO_MAX_BYTES || row.max_duration_seconds !== 600
      || row.encoding !== 'h264-avc1-yuv420p' || row.max_width !== 1920 || row.max_height !== 1080
      || row.max_fps !== 60 || row.max_selected_frames !== 20 || row.processing_ttl_seconds !== 3600
      || !Array.isArray(row.languages) || row.languages.length !== 3
      || row.languages.some((value, index) => value !== ['en', 'tr', 'en+tr'][index])) throw new Error('Unverified video limits');
  return { enabled: row.enabled };
}
export function parseVideoReceipt(value: unknown): VideoReceipt {
  const row = record(value);
  for (const name of ['project_id', 'source_id', 'job_id']) {
    if (typeof row[name] !== 'string' || !UUID_PATTERN.test(row[name] as string)) throw new Error('Invalid video receipt');
  }
  if (typeof row.deduplicated !== 'boolean') throw new Error('Invalid video receipt');
  return { project_id: row.project_id as string, source_id: row.source_id as string,
    job_id: row.job_id as string, deduplicated: row.deduplicated };
}
