"use server";

import { revalidatePath } from "next/cache";

import { requestJson } from "@/lib/api/client";
import { parseCleanup, UUID_PATTERN } from "@/lib/api/source-contracts";
import { sourcePath } from "@/lib/api/sources";
import { ApiError, publicErrorMessage } from "@/lib/api/errors";
import type { SourceActionState } from "@/lib/source-action-state";

const RIGHTS = ["owner_upload", "authorized_upload", "licensed_content"];

function checkedString(form: FormData, name: string): string {
  const value = form.get(name);
  if (typeof value !== "string") throw new ApiError({ status: 422, code: "validation_error" });
  return value;
}

function projectId(form: FormData): string {
  const id = checkedString(form, "projectId");
  if (!UUID_PATTERN.test(id)) throw new ApiError({ status: 422, code: "validation_error" });
  return id;
}

function key(form: FormData): string {
  const value = checkedString(form, "idempotency_key");
  if (!/^[a-zA-Z0-9_-]{8,128}$/.test(value)) throw new ApiError({ status: 422, code: "validation_error" });
  return value;
}

export async function uploadSourceAction(previous: SourceActionState, form: FormData): Promise<SourceActionState> {
  try {
    const id = projectId(form);
    const rights = checkedString(form, "authorization_mode");
    if (!RIGHTS.includes(rights)) throw new ApiError({ status: 422, code: "rights_required" });
    const file = form.get("file");
    if (!(file instanceof File) || !file.name.toLowerCase().match(/\.(srt|vtt)$/)) throw new ApiError({ status: 422, code: "unsupported_file" });
    if (file.size === 0 || file.size > 2_000_000) throw new ApiError({ status: 413, code: "upload_too_large" });
    const upload = new FormData();
    upload.set("file", file);
    upload.set("authorization_mode", rights);
    upload.set("idempotency_key", key(form));
    const item = form.get("playlist_item_id");
    if (item !== null && item !== "") {
      if (typeof item !== "string" || !UUID_PATTERN.test(item)) throw new ApiError({ status: 422, code: "validation_error" });
      upload.set("playlist_item_id", item);
    }
    await requestJson(`${sourcePath(id)}/uploads`, { method: "POST", body: upload });
    revalidatePath(`/projects/${id}`);
    return { status: "success", message: "Transcript uploaded. Processing continues in the background.", version: previous.version + 1 };
  } catch (error) {
    return { status: "error", message: publicErrorMessage(error), version: previous.version + 1 };
  }
}

export async function metadataSourceAction(previous: SourceActionState, form: FormData): Promise<SourceActionState> {
  try {
    const id = projectId(form);
    const rights = checkedString(form, "authorization_mode");
    if (!RIGHTS.includes(rights)) throw new ApiError({ status: 422, code: "rights_required" });
    await requestJson(sourcePath(id), { method: "POST", body: JSON.stringify({ url: checkedString(form, "url"), authorization_mode: rights, idempotency_key: key(form) }) });
    revalidatePath(`/projects/${id}`);
    return { status: "success", message: "Metadata import queued. An authorized transcript is still required for indexing.", version: previous.version + 1 };
  } catch (error) {
    return { status: "error", message: publicErrorMessage(error), version: previous.version + 1 };
  }
}

export async function sourceCommandAction(previous: SourceActionState, form: FormData): Promise<SourceActionState> {
  try {
    const id = projectId(form);
    const source = checkedString(form, "sourceId");
    const command = checkedString(form, "command");
    if (!UUID_PATTERN.test(source) || !["retry", "cancel", "reprocess", "delete"].includes(command)) throw new ApiError({ status: 422, code: "validation_error" });
    const payload = command === "delete"
      ? await requestJson(sourcePath(id, source), { method: "DELETE" })
      : await requestJson(`${sourcePath(id, source)}/${command}`, { method: "POST", body: JSON.stringify({ idempotency_key: key(form) }) });
    revalidatePath(`/projects/${id}`);
    return { status: "success", message: command === "delete" ? "Source removed. Retained file cleanup is scheduled." : `Processing ${command} accepted.`,
             version: previous.version + 1, ...(command === "delete" ? { cleanup: parseCleanup(payload) } : {}) };
  } catch (error) {
    return { status: "error", message: publicErrorMessage(error), version: previous.version + 1 };
  }
}

export async function retryCleanupAction(previous: SourceActionState, form: FormData): Promise<SourceActionState> {
  try {
    const id = projectId(form);
    const cleanup = checkedString(form, "cleanupId");
    if (!UUID_PATTERN.test(cleanup)) throw new ApiError({ status: 422, code: "validation_error" });
    const ticket = parseCleanup(await requestJson(`/api/v1/projects/${id}/cleanup/${cleanup}/retry`, { method: "POST" }));
    return { status: "success", message: "File cleanup retry accepted.", cleanup: ticket, version: previous.version + 1 };
  } catch (error) {
    return { status: "error", message: publicErrorMessage(error), version: previous.version + 1 };
  }
}
