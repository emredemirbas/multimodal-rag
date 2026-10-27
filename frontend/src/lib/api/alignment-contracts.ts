import { UUID_PATTERN } from "@/lib/api/identifiers";
import { parseAsrOrigin, type AsrOrigin } from "@/lib/api/provenance-contracts";
import { galleryHref, parseVisualGallery, type VisualGallery } from "@/lib/api/visual-contracts";

export interface AlignmentQuery {
  transcript_source_id: string; assert_same_recording: true; offset_ms: number;
  visual_generation?: number; transcript_generation?: number;
}
export interface AlignedSpan { segment_id: string; start_ms: number; end_ms: number; excerpt: string; text_truncated: boolean }
export interface TimelineAlignment {
  method: "retained-pts-in-transcript-spans-v1"; relationship: "user_asserted"; semantics_verified: false;
  offset_ms: number; gallery: VisualGallery;
  transcript: { source_id: string; source_filename: string; generation: number; active_generation: number;
    processing_version: string; asr_origin: AsrOrigin | null };
  matched_frames: number;
  items: { frame_id: string; transcript_time_ms: number; matches: AlignedSpan[]; matches_truncated: boolean }[];
}
type Parameters = Record<string, string | string[] | undefined>;
const PARAMETERS = ["transcript_source_id", "assert_same_recording", "offset_ms", "visual_generation", "transcript_generation"];
function record(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("Invalid alignment response");
  return value as Record<string, unknown>;
}
function integer(value: unknown, min: number, max = 2_147_483_647): number {
  if (typeof value !== "number" || !Number.isSafeInteger(value) || value < min || value > max) throw new Error("Invalid alignment number");
  return value;
}
function text(value: unknown, max: number, empty = false): string {
  if (typeof value !== "string" || (!empty && !value) || value.length > max) throw new Error("Invalid alignment text");
  return value;
}
function id(value: unknown): string {
  const parsed = text(value, 36);
  if (!UUID_PATTERN.test(parsed)) throw new Error("Invalid alignment identifier");
  return parsed;
}
export function parseAlignmentQuery(parameters: Parameters): AlignmentQuery | null {
  const names = Object.keys(parameters).filter((name) => parameters[name] !== undefined);
  if (!names.length) return null;
  if (names.some((name) => !PARAMETERS.includes(name) || typeof parameters[name] !== "string")
      || parameters.assert_same_recording !== "true") throw new Error("Confirm the same recording");
  function generation(name: string): number | undefined {
    const value = parameters[name];
    if (value === undefined) return undefined;
    if (typeof value !== "string" || !/^[1-9]\d{0,9}$/.test(value)) throw new Error("Invalid alignment generation");
    return integer(Number(value), 1);
  }
  const visual_generation = generation("visual_generation"), transcript_generation = generation("transcript_generation");
  if ((visual_generation === undefined) !== (transcript_generation === undefined)) throw new Error("Pin both generations");
  const offset = parameters.offset_ms ?? "0";
  if (typeof offset !== "string" || !/^(?:0|-?[1-9]\d{0,5})$/.test(offset)) throw new Error("Invalid transcript offset");
  return { transcript_source_id: id(parameters.transcript_source_id), assert_same_recording: true,
    offset_ms: integer(Number(offset), -600000, 600000), visual_generation, transcript_generation };
}
export function alignmentParameters(query: AlignmentQuery): URLSearchParams {
  const params = new URLSearchParams({ transcript_source_id: query.transcript_source_id,
    assert_same_recording: String(query.assert_same_recording), offset_ms: String(query.offset_ms) });
  if (query.visual_generation !== undefined) params.set("visual_generation", String(query.visual_generation));
  if (query.transcript_generation !== undefined) params.set("transcript_generation", String(query.transcript_generation));
  parseAlignmentQuery(Object.fromEntries(params));
  return params;
}
export function alignmentHref(project: string, source: string, query?: AlignmentQuery): string {
  const path = `${galleryHref(project, source)}/align`;
  return query ? `${path}?${alignmentParameters(query)}` : path;
}

export function parseTimelineAlignment(value: unknown): TimelineAlignment {
  const row = record(value), gallery = parseVisualGallery(row.gallery), raw = record(row.transcript);
  if (row.method !== "retained-pts-in-transcript-spans-v1" || row.relationship !== "user_asserted"
      || row.semantics_verified !== false || !gallery.origin || !Array.isArray(row.items)
      || row.items.length !== gallery.items.length) throw new Error("Invalid alignment basis");
  const offset_ms = integer(row.offset_ms, -600000, 600000), generation = integer(raw.generation, 1);
  const active_generation = integer(raw.active_generation, generation), asr_origin = parseAsrOrigin(raw.asr_origin);
  if (asr_origin && asr_origin.generation > generation) throw new Error("Invalid transcript origin");
  const transcript = { source_id: id(raw.source_id), source_filename: text(raw.source_filename, 255), generation,
    active_generation, processing_version: text(raw.processing_version, 120), asr_origin };
  if (transcript.source_id.toLowerCase() === gallery.source_id.toLowerCase()) throw new Error("Different sources required");
  const items = row.items.map((value, index) => {
    const item = record(value), point = integer(item.transcript_time_ms, -600000, 1199999);
    if (id(item.frame_id).toLowerCase() !== gallery.items[index].id.toLowerCase()
        || point !== gallery.items[index].timestamp_ms + offset_ms || !Array.isArray(item.matches)
        || item.matches.length > 5 || typeof item.matches_truncated !== "boolean"
        || item.matches_truncated && item.matches.length !== 5) throw new Error("Invalid frame alignment");
    const seen = new Set<string>();
    const matches = item.matches.map((value) => {
      const span = record(value), segment_id = id(span.segment_id), start_ms = integer(span.start_ms, 0), end_ms = integer(span.end_ms, start_ms + 1);
      const excerpt = text(span.excerpt, 8000, true), characters = Array.from(excerpt).length;
      if (typeof span.text_truncated !== "boolean" || characters > 4000 || span.text_truncated && characters !== 4000
          || start_ms > point || point >= end_ms || seen.has(segment_id.toLowerCase())) throw new Error("Invalid aligned span");
      seen.add(segment_id.toLowerCase());
      return { segment_id, start_ms, end_ms, excerpt, text_truncated: span.text_truncated };
    });
    for (let i = 1; i < matches.length; i++) {
      const a = matches[i - 1], b = matches[i];
      if (a.start_ms > b.start_ms || a.start_ms === b.start_ms && (a.end_ms > b.end_ms
          || a.end_ms === b.end_ms && a.segment_id.toLowerCase() > b.segment_id.toLowerCase())) throw new Error("Invalid aligned ordering");
    }
    return { frame_id: gallery.items[index].id, transcript_time_ms: point, matches, matches_truncated: item.matches_truncated };
  });
  const matched_frames = integer(row.matched_frames, 0, 20);
  if (matched_frames !== items.filter((item) => item.matches.length).length) throw new Error("Invalid matched count");
  return { method: row.method, relationship: row.relationship, semantics_verified: false, offset_ms, gallery, transcript, matched_frames, items };
}
