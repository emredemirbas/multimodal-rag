import { UUID_PATTERN } from "@/lib/api/identifiers";

export interface VisualFrame { id: string; ordinal: number; timestamp_ms: number; sample_target_ms: number; width: number; height: number; ocr_text: string }
export interface VisualGallery {
  source_id: string; source_filename: string; generation: number | null; processing_version: string | null;
  published_at: string | null; searchable: false; items: VisualFrame[];
  origin: null | { machine_generated: true; human_reviewed: false; job_id: string; generation: number;
    profile: string; language: "en" | "tr" | "en+tr"; engines: { ffmpeg: string; tesseract: string }; checkpoint_version: string; prepared_at: string };
}
function record(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("Invalid visual response");
  return value as Record<string, unknown>;
}
function text(value: unknown, max: number, empty = false): string {
  if (typeof value !== "string" || (!empty && !value) || value.length > max) throw new Error("Invalid visual text");
  return value;
}
function integer(value: unknown, min: number, max: number): number {
  if (typeof value !== "number" || !Number.isSafeInteger(value) || value < min || value > max) throw new Error("Invalid visual number");
  return value;
}
function id(value: unknown): string {
  const result = text(value, 36);
  if (!UUID_PATTERN.test(result)) throw new Error("Invalid visual identifier");
  return result;
}
function date(value: unknown): string {
  const result = text(value, 64);
  if (!Number.isFinite(Date.parse(result))) throw new Error("Invalid visual date");
  return result;
}
export function galleryHref(project: string, source: string) { return `/projects/${encodeURIComponent(project)}/sources/${encodeURIComponent(source)}/frames`; }
export function frameImageHref(project: string, frame: string) { return `/api/projects/${encodeURIComponent(project)}/frames/${encodeURIComponent(frame)}/image`; }

export function parseVisualGallery(value: unknown): VisualGallery {
  const row = record(value);
  const source_id = id(row.source_id), source_filename = text(row.source_filename, 255);
  if (row.searchable !== false || !Array.isArray(row.items) || row.items.length > 20) throw new Error("Invalid visual gallery");
  if (row.origin === null) {
    if (row.items.length || row.generation !== null || row.processing_version !== null || row.published_at !== null) throw new Error("Incomplete visual gallery");
    return { source_id, source_filename, generation: null, processing_version: null, published_at: null, origin: null, searchable: false, items: [] };
  }
  const raw = record(row.origin), engines = record(raw.engines);
  const profile = text(raw.profile, 80);
  if (raw.machine_generated !== true || raw.human_reviewed !== false || !/^local-visual-v1:[a-f0-9]{64}$/.test(profile)
      || !["en", "tr", "en+tr"].includes(String(raw.language)) || raw.checkpoint_version !== "visual-checkpoint-v1"
      || row.processing_version !== "retained-frames-v1" || row.items.length < 1) throw new Error("Invalid visual provenance");
  const generation = integer(row.generation, 1, 2_147_483_647), originGeneration = integer(raw.generation, 1, generation);
  const seen = new Set<string>();
  let previous = -1, characters = 0;
  const items = row.items.map((value, ordinal) => {
    const frame = record(value), frameId = id(frame.id);
    const timestamp = integer(frame.timestamp_ms, 0, 599999), target = integer(frame.sample_target_ms, 0, timestamp);
    const ocr = text(frame.ocr_text, 32000, true); // JS UTF-16 may use two units per OCR code point.
    characters += Array.from(ocr).length;
    if (integer(frame.ordinal, 0, 19) !== ordinal || timestamp <= previous || timestamp > target + 1000
        || seen.has(frameId.toLowerCase()) || Array.from(ocr).length > 16000 || characters > 320000) throw new Error("Invalid visual manifest");
    previous = timestamp; seen.add(frameId.toLowerCase());
    return { id: frameId, ordinal, timestamp_ms: timestamp, sample_target_ms: target,
      width: integer(frame.width, 1, 960), height: integer(frame.height, 1, 540), ocr_text: ocr };
  });
  return { source_id, source_filename, generation, processing_version: "retained-frames-v1", published_at: date(row.published_at), searchable: false, items,
    origin: { machine_generated: true, human_reviewed: false, job_id: id(raw.job_id), generation: originGeneration, profile,
      language: raw.language as "en" | "tr" | "en+tr", engines: { ffmpeg: text(engines.ffmpeg, 64), tesseract: text(engines.tesseract, 64) },
      checkpoint_version: "visual-checkpoint-v1", prepared_at: date(raw.prepared_at) } };
}
