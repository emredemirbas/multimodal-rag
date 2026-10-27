import { UUID_PATTERN } from "@/lib/api/source-contracts";
import { parseAsrOrigin, type AsrOrigin } from "@/lib/api/provenance-contracts";
import { parseVisualOrigin, type VisualOrigin } from "@/lib/api/visual-contracts";

export interface Conversation { id: string; project_id: string; title: string; created_at: string }
export interface Citation {
  segment_id: string; source_id: string; source_filename: string; start_ms: number; end_ms: number;
  modality: string; processing_version: string; generation: number;
  asr_origin?: AsrOrigin | null;
  frame_id?: string | null;
  visual_origin?: VisualOrigin | null;
}
export interface ChatTurn {
  id: string; sequence: number; question: string; source_ids: string[]; created_at: string;
  response: { answer: string; abstained: boolean; citations: Citation[]; provider: string; model: string };
}
export interface History { conversation: Conversation; turns: ChatTurn[] }
export interface Evidence extends Citation { text: string }
export type AnswerMode = "extractive" | "ollama" | "unavailable";
export type RetrievalMode = "deterministic-hash-and-lexical" | "local-semantic-and-lexical" | "unavailable";

export function parseRetrievalMode(value: unknown): RetrievalMode {
  const row = record(value);
  if (row.retrieval !== 'deterministic-hash-and-lexical' && row.retrieval !== 'local-semantic-and-lexical') throw new Error('Invalid retrieval mode');
  return row.retrieval;
}

export function parseAnswerMode(value: unknown): AnswerMode {
  const row = record(value);
  if ((row.mode !== "extractive" && row.mode !== "ollama") || row.spend_policy !== "no-paid-provider") throw new Error("Invalid answer mode");
  return row.mode;
}

function record(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("Invalid chat record");
  return value as Record<string, unknown>;
}
function text(value: unknown, max = 12_000): string {
  if (typeof value !== "string" || value.length > max) throw new Error("Invalid chat text");
  return value;
}
function id(value: unknown): string {
  const parsed = text(value, 36);
  if (!UUID_PATTERN.test(parsed)) throw new Error("Invalid chat identifier");
  return parsed;
}
function integer(value: unknown): number {
  if (typeof value !== "number" || !Number.isSafeInteger(value) || value < 0) throw new Error("Invalid chat number");
  return value;
}
export function parseConversation(value: unknown): Conversation {
  const row = record(value);
  return { id: id(row.id), project_id: id(row.project_id), title: text(row.title, 120), created_at: text(row.created_at, 80) };
}
export function parseConversations(value: unknown): Conversation[] {
  const row = record(value);
  if (!Array.isArray(row.items) || row.items.length > 100) throw new Error("Invalid conversations");
  return row.items.map(parseConversation);
}
function citation(value: unknown): Citation {
  const row = record(value);
  const start = integer(row.start_ms), end = integer(row.end_ms);
  const origin = parseAsrOrigin(row.asr_origin);
  const visual = parseVisualOrigin(row.visual_origin), frame = row.frame_id == null ? null : id(row.frame_id);
  if (end < start || end === start && row.modality !== "frame" || integer(row.generation) < 1
      || (origin !== null && origin.generation > integer(row.generation))
      || visual && (row.modality !== "frame" || !frame || origin || visual.generation >= integer(row.generation) || end !== start || start > 599999
        || row.processing_version !== `visual-ocr-chunks-v1:g${row.generation}`)) throw new Error("Invalid evidence provenance");
  return { segment_id: id(row.segment_id), source_id: id(row.source_id), source_filename: text(row.source_filename, 255),
    start_ms: start, end_ms: end, modality: text(row.modality, 30), processing_version: text(row.processing_version, 120), generation: integer(row.generation), asr_origin: origin,
    frame_id: frame, visual_origin: visual };
}
export function parseTurn(value: unknown): ChatTurn {
  const row = record(value), response = record(row.response);
  if (!Array.isArray(response.citations) || response.citations.length > 4 || typeof response.abstained !== "boolean") throw new Error("Invalid answer");
  if (!Array.isArray(row.source_ids) || row.source_ids.length > 20 || integer(row.sequence) < 1) throw new Error("Invalid turn");
  const citations = response.citations.map(citation);
  if ((response.abstained && citations.length) || (!response.abstained && !citations.length)) throw new Error("Invalid answer evidence");
  return { id: id(row.id), sequence: integer(row.sequence), question: text(row.question, 2000), source_ids: row.source_ids.map(id), created_at: text(row.created_at, 80),
    response: { answer: text(response.answer), abstained: response.abstained, citations, provider: text(response.provider, 100), model: text(response.model, 120) } };
}
export function parseHistory(value: unknown): History {
  const row = record(value);
  if (!Array.isArray(row.turns) || row.turns.length > 200) throw new Error("Invalid history");
  return { conversation: parseConversation(row.conversation), turns: row.turns.map(parseTurn) };
}
export function parseEvidence(value: unknown): Evidence {
  const row = record(value);
  return { ...citation(row), text: text(row.text, 2_000_000) };
}
export function timestamp(ms: number): string {
  const seconds = Math.floor(ms / 1000);
  const fraction = ms % 1000;
  return `${Math.floor(seconds / 60).toString().padStart(2, "0")}:${(seconds % 60).toString().padStart(2, "0")}${fraction ? `.${fraction.toString().padStart(3, "0")}` : ""}`;
}
