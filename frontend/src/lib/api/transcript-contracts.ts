import { parseEvidence, type Evidence } from "@/lib/api/chat-contracts";
import { UUID_PATTERN } from "@/lib/api/source-contracts";

export interface TranscriptQuery { generation?: number; page: number }
export interface TranscriptPage {
  source_id: string;
  source_filename: string;
  source_kind: string;
  source_status: string;
  generation: number | null;
  active_generation: number | null;
  processing_version: string | null;
  page: number;
  page_size: number;
  total_segments: number;
  total_pages: number;
  items: Evidence[];
}

function integer(value: unknown, minimum = 0, maximum = 2_147_483_647): number {
  if (typeof value !== "number" || !Number.isSafeInteger(value) || value < minimum || value > maximum) throw new Error("Invalid transcript number");
  return value;
}
function text(value: unknown, maximum: number): string {
  if (typeof value !== "string" || !value || value.length > maximum) throw new Error("Invalid transcript text");
  return value;
}

export function parseTranscriptQuery(query: { generation?: string | string[]; page?: string | string[] }): TranscriptQuery {
  function parameter(value: string | string[] | undefined, maximum: number): number | undefined {
    if (value === undefined) return undefined;
    if (typeof value !== "string" || !/^[1-9]\d{0,9}$/.test(value)) throw new Error("Invalid transcript parameter");
    return integer(Number(value), 1, maximum);
  }
  const generation = parameter(query.generation, 2_147_483_647);
  const page = parameter(query.page, 2_000) ?? 1;
  if (page > 1 && generation === undefined) throw new Error("Transcript pages require a generation");
  return { generation, page };
}

export function transcriptHref(projectId: string, sourceId: string, generation?: number | null, page = 1): string {
  const path = `/projects/${encodeURIComponent(projectId)}/sources/${encodeURIComponent(sourceId)}/transcript`;
  if (generation == null) return path;
  return `${path}?generation=${generation}&page=${page}`;
}

export function parseTranscriptPage(value: unknown): TranscriptPage {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("Invalid transcript response");
  const row = value as Record<string, unknown>;
  const source = text(row.source_id, 36);
  if (!UUID_PATTERN.test(source) || !Array.isArray(row.items) || row.items.length > 50) throw new Error("Invalid transcript segments");
  const filename = text(row.source_filename, 255);
  const generation = row.generation === null ? null : integer(row.generation, 1);
  const active = row.active_generation === null ? null : integer(row.active_generation, 1);
  const version = row.processing_version === null ? null : text(row.processing_version, 120);
  const total = integer(row.total_segments, 0, 100_000);
  const pages = integer(row.total_pages, 0, 2_000);
  const page = integer(row.page, 1, Math.max(1, pages));
  if (row.page_size !== 50 || pages !== Math.ceil(total / 50) || row.items.length !== Math.min(50, Math.max(0, total - (page - 1) * 50))
      || (generation !== null && (active === null || generation > active)) || (generation === null && active !== null)
      || (total > 0 && (generation === null || version === null))) throw new Error("Invalid transcript pagination");
  const seen = new Set<string>();
  let characters = 0;
  const items = row.items.map((item) => {
    const evidence = parseEvidence(item);
    const id = evidence.segment_id.toLowerCase();
    characters += evidence.text.length;
    if (evidence.source_id.toLowerCase() !== source.toLowerCase() || evidence.source_filename !== filename || evidence.generation !== generation
        || evidence.processing_version !== version || evidence.modality !== "transcript" || seen.has(id) || characters > 2_000_000) throw new Error("Invalid transcript provenance");
    seen.add(id);
    return evidence;
  });
  for (let index = 1; index < items.length; index++) {
    const previous = items[index - 1], current = items[index];
    if (previous.start_ms > current.start_ms || (previous.start_ms === current.start_ms && (previous.end_ms > current.end_ms
        || (previous.end_ms === current.end_ms && previous.segment_id.toLowerCase() > current.segment_id.toLowerCase())))) throw new Error("Invalid transcript ordering");
  }
  return { source_id: source, source_filename: filename, source_kind: text(row.source_kind, 30), source_status: text(row.source_status, 30),
    generation, active_generation: active, processing_version: version, page, page_size: 50, total_segments: total, total_pages: pages, items };
}
