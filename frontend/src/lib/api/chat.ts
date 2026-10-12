import "server-only";
import { requestJson } from "@/lib/api/client";
import { parseAnswerMode, parseRetrievalMode, parseConversations, parseHistory, type Conversation, type History } from "@/lib/api/chat-contracts";

export async function getAnswerMode() {
  return parseAnswerMode(await requestJson('/api/v1/runtime'));
}

export async function getRuntimeConfiguration() {
  const runtime = await requestJson('/api/v1/runtime');
  return { answerMode: parseAnswerMode(runtime), retrievalMode: parseRetrievalMode(runtime) };
}

export function conversationPath(projectId: string): string {
  return `/api/v1/projects/${encodeURIComponent(projectId)}/conversations`;
}
export async function listConversations(projectId: string): Promise<Conversation[]> {
  return parseConversations(await requestJson(conversationPath(projectId)));
}
export async function getHistory(projectId: string, conversationId: string): Promise<History> {
  return parseHistory(await requestJson(`${conversationPath(projectId)}/${encodeURIComponent(conversationId)}`));
}
