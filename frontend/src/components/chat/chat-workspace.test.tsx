import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ChatWorkspace } from "@/components/chat/chat-workspace";
import type { ChatTurn, Conversation } from "@/lib/api/chat-contracts";

const project = "12345678-1234-1234-1234-123456789abc";
const conversation: Conversation = { id: "12345678-1234-1234-1234-123456789abd", project_id: project, title: "Tutorial questions", created_at: "2026-10-02T00:00:00Z" };
const turn: ChatTurn = { id: "12345678-1234-1234-1234-123456789abe", sequence: 1, question: "What is health?", source_ids: [], created_at: conversation.created_at,
  response: { answer: "Quoted health evidence <script>alert(1)</script>", abstained: false, provider: "local-deterministic", model: "extractive",
    citations: [{ segment_id: "12345678-1234-1234-1234-123456789abf", source_id: "12345678-1234-1234-1234-123456789ac0", source_filename: "tutorial.vtt", start_ms: 1000, end_ms: 5000, generation: 1, processing_version: "parser-v1", modality: "transcript" }] } };
function response() {
  return new Response(new ReadableStream({ start(controller) {
    controller.enqueue(new TextEncoder().encode(`event: start\ndata: {}\n\nevent: delta\ndata: {"text":"Quoted evidence"}\n\nevent: complete\ndata: ${JSON.stringify(turn)}\n\n`)); controller.close();
  } }), { headers: { "Content-Type": "text/event-stream" } });
}
afterEach(() => vi.unstubAllGlobals());
describe("project chat", () => {
  it("has labelled empty states and honestly identifies the offline provider", () => {
    render(<ChatWorkspace projectId={project} sources={[]} initialConversations={[]} initialHistory={null} archived={false} />);
    expect(screen.getByLabelText("Question about the tutorial")).toHaveAttribute("maxlength", "2000");
    expect(screen.getByLabelText("Source filter")).toBeVisible();
    expect(screen.getByText(/Offline extractive baseline/)).toBeVisible();
    expect(screen.getByText(/No saved messages yet/)).toBeVisible();
    expect(screen.getByRole("button", { name: "Ask with evidence" })).toBeDisabled();
  });
  it("streams a validated answer, escapes evidence and links to the exact source version", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response()));
    const { container } = render(<ChatWorkspace projectId={project} sources={[]} initialConversations={[conversation]}
      initialHistory={{ conversation, turns: [] }} archived={false} />);
    fireEvent.change(screen.getByLabelText("Question about the tutorial"), { target: { value: "What is health?" } });
    fireEvent.click(screen.getByRole("button", { name: "Ask with evidence" }));
    expect(await screen.findByText(turn.response.answer)).toBeVisible();
    expect(screen.getByRole("link", { name: /tutorial.vtt.*00:01–00:05.*generation 1/ })).toHaveAttribute("href", `/projects/${project}/evidence/${turn.response.citations[0].segment_id}`);
    expect(container.querySelector("script")).toBeNull();
    expect(screen.getByLabelText("Question about the tutorial")).toHaveValue("");
    await waitFor(() => expect(screen.getByLabelText("Question about the tutorial")).toHaveFocus());
  });
  it("retries an unchanged failed delivery with the same key, without claiming it was not saved", async () => {
    const fetcher = vi.fn().mockRejectedValueOnce(new Error("network")).mockResolvedValueOnce(response());
    vi.stubGlobal("fetch", fetcher);
    render(<ChatWorkspace projectId={project} sources={[]} initialConversations={[conversation]} initialHistory={{ conversation, turns: [] }} archived={false} />);
    fireEvent.change(screen.getByLabelText("Question about the tutorial"), { target: { value: "What is health?" } });
    fireEvent.click(screen.getByRole("button", { name: "Ask with evidence" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("may already be saved");
    const firstKey = JSON.parse(fetcher.mock.calls[0][1].body).idempotency_key;
    fireEvent.click(screen.getByRole("button", { name: "Ask with evidence" }));
    await screen.findByText(turn.response.answer);
    expect(JSON.parse(fetcher.mock.calls[1][1].body).idempotency_key).toBe(firstKey);
  });
  it("stops delivery, preserves the draft and offers history recovery", async () => {
    vi.stubGlobal("fetch", vi.fn((_url, init) => new Promise((_resolve, reject) => init.signal.addEventListener("abort", () => reject(new Error("aborted"))))));
    render(<ChatWorkspace projectId={project} sources={[]} initialConversations={[conversation]} initialHistory={{ conversation, turns: [] }} archived={false} />);
    fireEvent.change(screen.getByLabelText("Question about the tutorial"), { target: { value: "health?" } });
    fireEvent.click(screen.getByRole("button", { name: "Ask with evidence" }));
    fireEvent.click(await screen.findByRole("button", { name: "Stop delivery" }));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("Delivery stopped"));
    expect(screen.getByLabelText("Question about the tutorial")).toHaveValue("health?");
    expect(screen.getByRole("button", { name: "Reload history" })).toBeEnabled();
  });
  it("shows persisted limitations and prevents new questions in archived projects", () => {
    const abstained = { ...turn, response: { ...turn.response, answer: "No supporting evidence", abstained: true, citations: [] } };
    render(<ChatWorkspace projectId={project} sources={[]} initialConversations={[conversation]} initialHistory={{ conversation, turns: [abstained] }} archived />);
    expect(screen.getByRole("heading", { name: "Evidence limitation" })).toBeVisible();
    expect(screen.queryByLabelText("Question about the tutorial")).not.toBeInTheDocument();
  });
});
