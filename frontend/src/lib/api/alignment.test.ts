import { beforeEach, describe, expect, it, vi } from "vitest";
import { getAlignment } from "@/lib/api/alignment";
import { requestJson } from "@/lib/api/client";
import { alignmentFixture, transcriptId } from "../../../test-support/alignment-fixture";
import { projectId, sourceId } from "../../../test-support/visual-fixture";
vi.mock("@/lib/api/client", () => ({ requestJson: vi.fn() }));
const query = { transcript_source_id: transcriptId, assert_same_recording: true as const, offset_ms: 0,
  visual_generation: 2, transcript_generation: 1 };
describe("server-only alignment reader", () => {
  beforeEach(() => { vi.mocked(requestJson).mockReset(); });
  it("uses only the authenticated scoped route and explicit generation/offset parameters", async () => {
    vi.mocked(requestJson).mockResolvedValue(alignmentFixture());
    expect((await getAlignment(projectId, sourceId, query)).matched_frames).toBe(1);
    expect(requestJson).toHaveBeenCalledWith(`/api/v1/projects/${projectId}/sources/${sourceId}/alignment?transcript_source_id=${transcriptId}&assert_same_recording=true&offset_ms=0&visual_generation=2&transcript_generation=1`);
  });
  it.each(["source", "transcript", "offset", "visual_generation", "transcript_generation"])("rejects misbound %s even if the payload is otherwise valid", async (kind) => {
    const value = alignmentFixture();
    if (kind === "source") value.gallery.source_id = projectId;
    if (kind === "transcript") value.transcript.source_id = projectId;
    if (kind === "offset") { value.offset_ms = 1; value.items[0].transcript_time_ms += 1; }
    if (kind === "visual_generation") value.gallery.generation = 3;
    if (kind === "transcript_generation") { value.transcript.generation = 2; value.transcript.active_generation = 2; }
    vi.mocked(requestJson).mockResolvedValue(value);
    await expect(getAlignment(projectId, sourceId, query)).rejects.toMatchObject({ code: "invalid_api_response" });
  });
});
