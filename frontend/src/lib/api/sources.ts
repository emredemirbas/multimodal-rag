import "server-only";

import { requestJson } from "@/lib/api/client";
import { parsePlaylistItems, parseSourceList, type SourceItem } from "@/lib/api/source-contracts";

export async function listSourceInventory(projectId: string) {
  const payload = await requestJson(`/api/v1/projects/${encodeURIComponent(projectId)}/sources`);
  return { items: parseSourceList(payload), playlist_items: parsePlaylistItems(payload) };
}

export async function listSources(projectId: string): Promise<SourceItem[]> {
  return parseSourceList(await requestJson(`/api/v1/projects/${encodeURIComponent(projectId)}/sources`));
}

export function sourcePath(projectId: string, sourceId?: string): string {
  const path = `/api/v1/projects/${encodeURIComponent(projectId)}/sources`;
  return sourceId ? `${path}/${encodeURIComponent(sourceId)}` : path;
}
