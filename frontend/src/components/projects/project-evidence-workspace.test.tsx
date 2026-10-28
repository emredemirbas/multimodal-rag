import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ProjectEvidenceWorkspace } from "@/components/projects/project-evidence-workspace";
import type { ChatTurn, Conversation } from "@/lib/api/chat-contracts";
import type { SourceItem } from "@/lib/api/source-contracts";

vi.mock("@/app/actions/sources", () => ({
  uploadSourceAction: vi.fn(), metadataSourceAction: vi.fn(),
  sourceCommandAction: vi.fn(), retryCleanupAction: vi.fn(),
}));

const projectA = "12345678-1234-1234-1234-123456789abc";
const projectB = "22345678-1234-1234-1234-123456789abc";
const source: SourceItem = {
  id: "12345678-1234-1234-1234-123456789abd", filename: "tutorial.vtt", status: "ready",
  generation: 1, active_generation: 1, segment_count: 1, provider: "upload", failure_code: null,
  job: { id: "12345678-1234-1234-1234-123456789abe", status: "succeeded", stage: "ready",
    progress_percent: 100, attempt_count: 1, max_attempts: 3, failure_code: null },
};
const conversation: Conversation = {
  id: "12345678-1234-1234-1234-123456789abf", project_id: projectA,
  title: "Tutorial questions", created_at: "2026-10-28T00:00:00Z",
};
const turn: ChatTurn = {
  id: "12345678-1234-1234-1234-123456789ac0", sequence: 1,
  question: "Which endpoint checks service health?", source_ids: [source.id],
  created_at: conversation.created_at,
  response: { answer: "Quoted health evidence", abstained: false,
    provider: "local-deterministic", model: "evidence-extractive-v2",
    citations: [{ segment_id: "12345678-1234-1234-1234-123456789ac1", source_id: source.id,
      source_filename: source.filename, start_ms: 1000, end_ms: 22000,
      generation: 1, processing_version: "transcript-chunks-v1:g1", modality: "transcript" }] },
};

function props(initialSources: SourceItem[] = [source], projectId = projectA) {
  return {
    projectId, initialSources, initialPlaylistItems: [], initialConversations: [],
    initialHistory: null, archived: false, chatError: "", sourceError: "",
    answerMode: "extractive" as const, retrievalMode: "deterministic-hash-and-lexical" as const,
    audioCapability: { enabled: false }, videoCapability: { enabled: false },
  };
}

function inventory(items: SourceItem[]) {
  return new Response(JSON.stringify({ items, playlist_items: [] }), { status: 200 });
}

function stream() {
  return new Response(new ReadableStream({ start(controller) {
    controller.enqueue(new TextEncoder().encode(`event: start\ndata: {}\n\nevent: delta\ndata: {"text":"Quoted health evidence"}\n\nevent: complete\ndata: ${JSON.stringify(turn)}\n\n`));
    controller.close();
  } }), { headers: { "Content-Type": "text/event-stream" } });
}

describe("project-scoped live evidence inventory", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    Object.defineProperty(document, "hidden", { configurable: true, value: false });
    vi.stubGlobal("fetch", vi.fn());
  });
  afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); });

  it("adds a newly published source to chat through the existing source poll without reloading", async () => {
    const pending: SourceItem = { ...source, status: "processing", active_generation: null,
      job: { ...source.job!, status: "running", stage: "embedding", progress_percent: 50 } };
    vi.mocked(fetch).mockResolvedValueOnce(inventory([source]));
    render(<ProjectEvidenceWorkspace {...props([pending])} />);
    expect(within(screen.getByLabelText("Source filter")).queryByRole("option", { name: source.filename })).toBeNull();

    await act(async () => { vi.advanceTimersByTime(5000); });

    expect(within(screen.getByLabelText("Source filter")).getByRole("option", { name: source.filename })).toBeVisible();
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(vi.mocked(fetch).mock.calls[0][0]).toBe(`/api/projects/${projectA}/sources`);
    await act(async () => { vi.advanceTimersByTime(15000); });
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it.each(["network", "invalid-source", "invalid-playlist"])("keeps the previous chat inventory after a %s refresh failure", async (failure) => {
    if (failure === "network") vi.mocked(fetch).mockRejectedValueOnce(new Error("private failure"));
    else vi.mocked(fetch).mockResolvedValueOnce(new Response(JSON.stringify(failure === "invalid-source"
      ? { items: [{ id: "invalid" }] }
      : { items: [], playlist_items: [{ id: "invalid" }] })));
    render(<ProjectEvidenceWorkspace {...props()} />);
    fireEvent.change(screen.getByLabelText("Source filter"), { target: { value: source.id } });

    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Refresh sources" })); });

    expect(screen.getByRole("alert")).toHaveTextContent("Sources could not refresh");
    expect(screen.getByLabelText("Source filter")).toHaveValue(source.id);
    expect(within(screen.getByLabelText("Source filter")).getByRole("option", { name: source.filename })).toBeVisible();
    expect(screen.queryByText(/private failure/)).toBeNull();
  });

  it("retains a pending chat draft, old citations and the uncertain replay key across a generation refresh", async () => {
    let failDelivery!: (error: Error) => void;
    const delivery = new Promise<Response>((_resolve, reject) => { failDelivery = reject; });
    vi.mocked(fetch).mockReturnValueOnce(delivery)
      .mockResolvedValueOnce(inventory([{ ...source, generation: 2, active_generation: 2 }]))
      .mockResolvedValueOnce(stream());
    render(<ProjectEvidenceWorkspace {...props()} initialConversations={[conversation]}
      initialHistory={{ conversation, turns: [turn] }} />);
    fireEvent.change(screen.getByLabelText("Source filter"), { target: { value: source.id } });
    fireEvent.change(screen.getByLabelText("Question about the tutorial"), { target: { value: turn.question } });
    act(() => { fireEvent.click(screen.getByRole("button", { name: "Ask with evidence" })); });
    const original = JSON.parse(vi.mocked(fetch).mock.calls[0][1]!.body as string);

    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Refresh sources" })); });

    expect(screen.getByLabelText("Question about the tutorial")).toHaveValue(turn.question);
    expect(screen.getByLabelText("Question about the tutorial")).toBeDisabled();
    expect(screen.getByLabelText("Source filter")).toHaveValue(source.id);
    expect(screen.getByRole("link", { name: /tutorial.vtt.*generation 1/ })).toHaveAttribute(
      "href", `/projects/${projectA}/evidence/${turn.response.citations[0].segment_id}`);
    expect(screen.getByRole("link", { name: "Read transcript" })).toHaveAttribute(
      "href", `/projects/${projectA}/sources/${source.id}/transcript?generation=2&page=1`);

    await act(async () => { failDelivery(new Error("delivery uncertain")); });
    expect(screen.getByRole("alert")).toHaveTextContent("may already be saved");
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Ask with evidence" })); });
    expect(JSON.parse(vi.mocked(fetch).mock.calls[2][1]!.body as string)).toEqual(original);
    expect(screen.getByLabelText("Question about the tutorial")).toHaveValue("");
    expect(screen.getAllByText(turn.response.answer)).toHaveLength(1);
  });

  it("cannot publish a late project-A inventory into project B after navigation", async () => {
    let resolveA!: (response: Response) => void;
    vi.mocked(fetch).mockReturnValueOnce(new Promise<Response>((resolve) => { resolveA = resolve; }));
    const { rerender } = render(<ProjectEvidenceWorkspace {...props()} />);
    fireEvent.change(screen.getByLabelText("Question about the tutorial"), { target: { value: "Project A draft" } });
    act(() => { fireEvent.click(screen.getByRole("button", { name: "Refresh sources" })); });

    const other: SourceItem = { ...source, id: "22345678-1234-1234-1234-123456789abd", filename: "project-b.vtt" };
    rerender(<ProjectEvidenceWorkspace {...props([other], projectB)} />);
    await act(async () => { resolveA(inventory([source])); });

    const options = within(screen.getByLabelText("Source filter"));
    expect(options.getByRole("option", { name: other.filename })).toBeVisible();
    expect(options.queryByRole("option", { name: source.filename })).toBeNull();
    expect(screen.getByLabelText("Question about the tutorial")).toHaveValue("");
    expect(screen.getByRole("link", { name: "Read transcript" })).toHaveAttribute(
      "href", `/projects/${projectB}/sources/${other.id}/transcript?generation=1&page=1`);
  });
});
