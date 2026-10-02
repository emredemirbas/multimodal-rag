import { beforeEach, describe, expect, it, vi } from "vitest";

import { metadataSourceAction, sourceCommandAction, uploadSourceAction } from "@/app/actions/sources";
import { requestJson } from "@/lib/api/client";
import { INITIAL_SOURCE_ACTION } from "@/lib/source-action-state";

vi.mock("next/cache", () => ({ revalidatePath: vi.fn() }));
vi.mock("@/lib/api/client", () => ({ requestJson: vi.fn() }));
vi.mock("@/lib/api/sources", () => ({ sourcePath: (project: string, source?: string) => `/api/v1/projects/${project}/sources${source ? `/${source}` : ""}` }));
const projectId = "12345678-1234-1234-1234-123456789abc";
const sourceId = "12345678-1234-1234-1234-123456789abd";

function form() {
  const data = new FormData();
  data.set("projectId", projectId);
  data.set("sourceId", sourceId);
  data.set("authorization_mode", "owner_upload");
  data.set("idempotency_key", "stable-client-command-key");
  return data;
}

describe("server-only source actions", () => {
  beforeEach(() => { vi.mocked(requestJson).mockReset(); });
  it("sends bounded multipart uploads with the same client key", async () => {
    const data = form();
    data.set("file", new File(["WEBVTT"], "tutorial.vtt", { type: "text/vtt" }));
    vi.mocked(requestJson).mockResolvedValue({});
    expect((await uploadSourceAction(INITIAL_SOURCE_ACTION, data)).status).toBe("success");
    const call = vi.mocked(requestJson).mock.calls[0];
    expect(call[0]).toBe(`/api/v1/projects/${projectId}/sources/uploads`);
    expect((call[1]?.body as FormData).get("idempotency_key")).toBe("stable-client-command-key");
  });
  it("rejects uploads without rights before making an upstream request", async () => {
    const data = form();
    data.delete("authorization_mode");
    expect((await uploadSourceAction(INITIAL_SOURCE_ACTION, data)).status).toBe("error");
    expect(requestJson).not.toHaveBeenCalled();
  });
  it("returns a tracked cleanup ticket instead of claiming object deletion is complete", async () => {
    const data = form();
    data.set("command", "delete");
    vi.mocked(requestJson).mockResolvedValue({ id: sourceId, project_id: projectId, status: "pending" });
    const result = await sourceCommandAction(INITIAL_SOURCE_ACTION, data);
    expect(result.status).toBe("success");
    expect(result.cleanup?.status).toBe("pending");
    expect(result.message).toMatch(/cleanup is scheduled/);
    expect(requestJson).toHaveBeenCalledWith(`/api/v1/projects/${projectId}/sources/${sourceId}`, { method: "DELETE" });
  });
  it("metadata registration carries rights and idempotency but no browser credential", async () => {
    const data = form();
    data.set("url", "https://youtu.be/abcdefghijk");
    vi.mocked(requestJson).mockResolvedValue({});
    expect((await metadataSourceAction(INITIAL_SOURCE_ACTION, data)).status).toBe("success");
    const payload = JSON.parse(vi.mocked(requestJson).mock.calls[0][1]?.body as string);
    expect(payload.authorization_mode).toBe("owner_upload");
    expect(payload.idempotency_key).toBe("stable-client-command-key");
    expect(payload).not.toHaveProperty("token");
  });
});
