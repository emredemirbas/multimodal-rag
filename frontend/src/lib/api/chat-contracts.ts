import { UUID_PATTERN } from "@/lib/api/source-contracts";

export interface Conversation { id: string; project_id: string; title: string; created_at: string }
export interface Citation {
  segment_id: string; source_id: string; source_filename: string; start_ms: number; end_ms: number;
  modality: string; processing_version: string; generation: number;
}
export interface ChatTurn {
  id: string; sequence: number; question: string; source_ids: string[]; created_at: string;
  response: { answer: string; abstained: boolean; citations: Citation[]; provider: string; model: string };
}
export interface History { conversation: Conversation; turns: ChatTurn[] }
export interface Evidence extends Citation { text: string }

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
  if (end <= start || integer(row.generation) < 1) throw new Error("Invalid evidence provenance");
  return { segment_id: id(row.segment_id), source_id: id(row.source_id), source_filename: text(row.source_filename, 255),
    start_ms: start, end_ms: end, modality: text(row.modality, 30), processing_version: text(row.processing_version, 120), generation: integer(row.generation) };
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
