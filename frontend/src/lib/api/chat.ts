import "server-only";
import { requestJson } from "@/lib/api/client";
import { parseConversations, parseHistory, type Conversation, type History } from "@/lib/api/chat-contracts";

export function conversationPath(projectId: string): string {
  return `/api/v1/projects/${encodeURIComponent(projectId)}/conversations`;
}
export async function listConversations(projectId: string): Promise<Conversation[]> {
  return parseConversations(await requestJson(conversationPath(projectId)));
}
export async function getHistory(projectId: string, conversationId: string): Promise<History> {
  return parseHistory(await requestJson(`${conversationPath(projectId)}/${encodeURIComponent(conversationId)}`));
}
