import { beforeEach, describe, expect, it, vi } from "vitest";
import { requestJson } from "@/lib/api/client";
import { getTranscript } from "@/lib/api/transcripts";
import { projectId, sourceId, transcriptFixture } from "../../../test-support/transcript-fixture";

vi.mock("@/lib/api/client", () => ({ requestJson: vi.fn() }));

describe("server-only transcript reader", () => {
  beforeEach(() => { vi.mocked(requestJson).mockReset(); });
  it("uses the scoped authenticated API path with an immutable generation", async () => {
    vi.mocked(requestJson).mockResolvedValue(transcriptFixture(2));
    expect((await getTranscript(projectId, sourceId, { generation: 1, page: 2 })).items).toHaveLength(3);
    expect(requestJson).toHaveBeenCalledWith(`/api/v1/projects/${projectId}/sources/${sourceId}/transcript?page=2&generation=1`);
  });
  it("rejects a different source, page or requested generation at the server boundary", async () => {
    const original = transcriptFixture();
    for (const payload of [
      { ...original, source_id: projectId, items: original.items.map((item) => ({ ...item, source_id: projectId })) },
      transcriptFixture(2),
      { ...original, generation: 2, active_generation: 2, items: original.items.map((item) => ({ ...item, generation: 2 })) },
    ]) {
      vi.mocked(requestJson).mockResolvedValue(payload);
      await expect(getTranscript(projectId, sourceId, { generation: 1, page: 1 })).rejects.toMatchObject({ code: "invalid_api_response" });
    }
  });
});
