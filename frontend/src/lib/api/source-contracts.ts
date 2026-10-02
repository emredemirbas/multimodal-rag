export interface ProcessingJob {
  id: string;
  status: "pending" | "running" | "retrying" | "succeeded" | "failed" | "cancelled";
  stage: string;
  progress_percent: number;
  attempt_count: number;
  max_attempts: number;
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

export function parseSourceList(value: unknown): SourceItem[] {
  const payload = record(value);
  if (!Array.isArray(payload.items)) throw new Error("Invalid source list");
  return payload.items.map((item) => {
    const source = record(item);
    const rawJob = source.job === null ? null : record(source.job);
    if (rawJob && (!JOB_STATES.includes(string(rawJob.status)) || integer(rawJob.progress_percent) > 100)) throw new Error("Invalid processing state");
    const job: ProcessingJob | null = rawJob ? {
      id: identifier(rawJob.id), status: rawJob.status as ProcessingJob["status"], stage: string(rawJob.stage),
      progress_percent: integer(rawJob.progress_percent), attempt_count: integer(rawJob.attempt_count),
      max_attempts: integer(rawJob.max_attempts), failure_code: rawJob.failure_code === null ? null : string(rawJob.failure_code),
    } : null;
    return {
      id: identifier(source.id), filename: string(source.filename), status: string(source.status),
      generation: integer(source.generation), active_generation: source.active_generation === null ? null : integer(source.active_generation),
      segment_count: integer(source.segment_count), provider: string(source.provider), job,
      failure_code: source.failure_code === null ? null : string(source.failure_code),
    };
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
