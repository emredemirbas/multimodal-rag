export interface ProcessingJob {
  id: string;
  status: "pending" | "running" | "retrying" | "succeeded" | "failed" | "cancelled";
  stage: string;
  progress_percent: number;
  attempt_count: number;
  max_attempts: number;
  delivery_count?: number;
  processed_segments?: number;
  total_segments?: number;
  failure_code: string | null;
}

export interface SourceItem {
  id: string;
  filename: string;
  status: string;
  generation: number;
  active_generation: number | null;
  segment_count: number;
  provider: string;
  job: ProcessingJob | null;
  failure_code: string | null;
  kind?: string;
  playlist_truncated?: boolean;
  active_embedding_space?: string | null;
  reindex_required?: boolean;
}

export interface PlaylistItem {
  id: string;
  playlist_source_id: string;
  generation: number;
  position: number;
  video_id: string;
  title: string;
  transcript_source_id: string | null;
}

export interface CleanupTicket {
  id: string;
  project_id: string;
  status: "pending" | "running" | "completed" | "failed";
}

export const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const JOB_STATES = ["pending", "running", "retrying", "succeeded", "failed", "cancelled"];

function record(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("Invalid source response");
  return value as Record<string, unknown>;
}

function string(value: unknown): string {
  if (typeof value !== "string") throw new Error("Invalid source string");
  return value;
}

function identifier(value: unknown): string {
  const parsed = string(value);
  if (!UUID_PATTERN.test(parsed)) throw new Error("Invalid source identifier");
  return parsed;
}

function integer(value: unknown): number {
  if (typeof value !== "number" || !Number.isSafeInteger(value) || value < 0) throw new Error("Invalid source count");
  return value;
}

function playlistTruncated(source: Record<string, unknown>): boolean {
  if (source.playlist_truncated !== undefined) {
    if (typeof source.playlist_truncated !== "boolean") throw new Error("Invalid playlist truncation");
    return source.playlist_truncated;
  }
  const flag = source.metadata === undefined ? undefined : record(source.metadata).truncated;
  if (flag !== undefined && typeof flag !== "boolean") throw new Error("Invalid playlist truncation");
  return flag === true;
}

export function parseSourceList(value: unknown): SourceItem[] {
  const payload = record(value);
  if (!Array.isArray(payload.items)) throw new Error("Invalid source list");
  return payload.items.map((item) => {
    const source = record(item);
    if (source.reindex_required !== undefined && typeof source.reindex_required !== 'boolean') throw new Error('Invalid reindex state');
    const rawJob = source.job === null ? null : record(source.job);
    if (rawJob && (!JOB_STATES.includes(string(rawJob.status)) || integer(rawJob.progress_percent) > 100)) throw new Error("Invalid processing state");
    const processed = rawJob?.processed_segments === undefined ? 0 : integer(rawJob.processed_segments);
    const total = rawJob?.total_segments === undefined ? 0 : integer(rawJob.total_segments);
    if (processed > total || total > 10_000) throw new Error('Invalid checkpoint progress');
    const job: ProcessingJob | null = rawJob ? {
      id: identifier(rawJob.id), status: rawJob.status as ProcessingJob["status"], stage: string(rawJob.stage),
      progress_percent: integer(rawJob.progress_percent), attempt_count: integer(rawJob.attempt_count),
      max_attempts: integer(rawJob.max_attempts), failure_code: rawJob.failure_code === null ? null : string(rawJob.failure_code),
      processed_segments: processed, total_segments: total,
      delivery_count: rawJob.delivery_count === undefined ? 0 : integer(rawJob.delivery_count),
    } : null;
    return {
      id: identifier(source.id), filename: string(source.filename), status: string(source.status),
      generation: integer(source.generation), active_generation: source.active_generation === null ? null : integer(source.active_generation),
      segment_count: integer(source.segment_count), provider: string(source.provider), job,
      failure_code: source.failure_code === null ? null : string(source.failure_code),
      ...(source.kind === undefined ? {} : { kind: string(source.kind) }),
      playlist_truncated: playlistTruncated(source),
      active_embedding_space: source.active_embedding_space == null ? null : string(source.active_embedding_space),
      reindex_required: source.reindex_required === true,
    };
  });
}

export function parsePlaylistItems(value: unknown): PlaylistItem[] {
  const payload = record(value);
  if (payload.playlist_items === undefined) return [];
  if (!Array.isArray(payload.playlist_items) || payload.playlist_items.length > 20_000) throw new Error("Invalid playlist items");
  const seen = new Set<string>();
  return payload.playlist_items.map((raw) => {
    const item = record(raw);
    const id = identifier(item.id);
    const video = string(item.video_id);
    const title = string(item.title);
    const generation = integer(item.generation);
    const position = integer(item.position);
    if (seen.has(id) || !/^[a-zA-Z0-9_-]{11}$/.test(video) || !title || title.length > 255 || generation < 1 || position > 1_000_000) throw new Error("Invalid playlist item");
    seen.add(id);
    return { id, playlist_source_id: identifier(item.playlist_source_id), generation, position, video_id: video, title,
      transcript_source_id: item.transcript_source_id === null ? null : identifier(item.transcript_source_id) };
  });
}

export function parseCleanup(value: unknown): CleanupTicket {
  const ticket = record(value);
  const status = string(ticket.status);
  if (!["pending", "running", "completed", "failed"].includes(status)) throw new Error("Invalid cleanup state");
  return { id: identifier(ticket.id), project_id: identifier(ticket.project_id), status: status as CleanupTicket["status"] };
}

export function isProcessing(source: SourceItem): boolean {
  return source.job !== null && ["pending", "running", "retrying"].includes(source.job.status);
}
