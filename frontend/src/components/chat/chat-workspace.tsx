"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import Link from "next/link";
import { parseConversation, parseHistory, timestamp, type ChatTurn, type Conversation, type History } from "@/lib/api/chat-contracts";
import type { SourceItem } from "@/lib/api/source-contracts";
import { consumeChatStream } from "@/lib/chat-stream";

interface Props {
  projectId: string; sources: SourceItem[]; initialConversations: Conversation[];
  initialHistory: History | null; archived: boolean; initialError?: string;
}

export function ChatWorkspace({ projectId, sources, initialConversations, initialHistory, archived, initialError = "" }: Props) {
  const [conversations, setConversations] = useState(initialConversations);
  const [conversation, setConversation] = useState<Conversation | null>(initialHistory?.conversation ?? null);
  const [turns, setTurns] = useState<ChatTurn[]>(initialHistory?.turns ?? []);
  const [question, setQuestion] = useState("");
  const [sourceId, setSourceId] = useState("");
  const [pending, setPending] = useState(false);
  const [partial, setPartial] = useState("");
  const [error, setError] = useState(initialError);
  const [status, setStatus] = useState("");
  const requestKey = useRef("");
  const conversationKey = useRef("");
  const controller = useRef<AbortController | null>(null);
  const busy = useRef(false);
  const questionInput = useRef<HTMLTextAreaElement>(null);
  const wasPending = useRef(false);
  const path = `/api/projects/${projectId}/conversations`;
  useEffect(() => () => controller.current?.abort(), []);
  useEffect(() => {
    if (!pending && wasPending.current) questionInput.current?.focus();
    wasPending.current = pending;
  }, [pending]);

  async function history(id: string) {
    if (busy.current) return;
    busy.current = true;
    setPending(true); setError(""); setStatus("Loading saved conversation…");
    const active = new AbortController(); controller.current = active;
    try {
      const response = await fetch(`${path}/${id}`, { cache: "no-store", signal: AbortSignal.any([active.signal, AbortSignal.timeout(10_000)]) });
      if (!response.ok) throw new Error("History unavailable");
      const saved = parseHistory(await response.json());
      if (saved.conversation.project_id !== projectId || saved.conversation.id !== id) throw new Error("Invalid conversation scope");
      setConversation(saved.conversation); setTurns(saved.turns); setPartial("");
      setStatus("Saved conversation loaded.");
    } catch { setError("History could not be loaded. Try again or reload the workspace."); }
    finally { busy.current = false; setPending(false); controller.current = null; }
  }

  function newConversation() {
    if (busy.current) return;
    setConversation(null); setTurns([]); setPartial(""); setError(""); setStatus("New conversation. Each question should be self-contained.");
    requestKey.current = ""; conversationKey.current = "";
    questionInput.current?.focus();
  }

  async function send(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy.current || archived || question.trim().length < 2) return;
    busy.current = true;
    const active = new AbortController(); controller.current = active;
    const signal = AbortSignal.any([active.signal, AbortSignal.timeout(30_000)]);
    setPending(true); setPartial(""); setError(""); setStatus("Finding evidence and delivering the saved answer…");
    requestKey.current ||= crypto.randomUUID();
    try {
      let current = conversation;
      if (!current) {
        conversationKey.current ||= crypto.randomUUID();
        const response = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ title: "Tutorial questions", idempotency_key: conversationKey.current }), signal });
        if (!response.ok) throw new Error("Conversation unavailable");
        current = parseConversation(await response.json());
        if (current.project_id !== projectId) throw new Error("Invalid conversation scope");
        setConversation(current);
        setConversations((previous) => [current!, ...previous.filter((item) => item.id !== current!.id)]);
      }
      const response = await fetch(`${path}/${current.id}/messages`, {
        method: "POST", headers: { "Content-Type": "application/json", "Accept": "text/event-stream" }, signal,
        body: JSON.stringify({ question: question.trim(), source_ids: sourceId ? [sourceId] : [], idempotency_key: requestKey.current }),
      });
      if (!response.ok || !response.body || !response.headers.get("content-type")?.startsWith("text/event-stream")) throw new Error("Answer unavailable");
      const turn = await consumeChatStream(response.body, (chunk) => setPartial((previous) => previous + chunk));
      setTurns((previous) => [...previous.filter((item) => item.id !== turn.id), turn].sort((left, right) => left.sequence - right.sequence));
      setQuestion(""); setPartial(""); requestKey.current = "";
      setStatus(turn.response.abstained ? "No supporting evidence was found. The limitation was saved." : "Answer saved with inspectable source citations.");
    } catch {
      setPartial("");
      setError(active.signal.aborted ? "Delivery stopped. The answer may already be saved. Reload history or resend this unchanged question to replay it." :
        "Delivery could not finish. The answer may already be saved. Reload history or resend this unchanged question; it will not create a duplicate turn.");
      setStatus("");
    } finally {
      busy.current = false; setPending(false); controller.current = null;
      questionInput.current?.focus();
    }
  }

  return <div className="stack">
    <p className="muted">Offline extractive baseline: answers quote your indexed transcripts, not a connected language model. Each question is self-contained; saved history is not model context.</p>
    <div className="chat-controls">
      <label htmlFor="conversation-choice">Saved conversation</label>
      <select id="conversation-choice" value={conversation?.id ?? ""} disabled={pending} onChange={(event) => {
        requestKey.current = "";
        if (event.target.value) void history(event.target.value); else newConversation();
      }}>
        <option value="">New conversation</option>
        {conversations.map((item, index) => <option key={item.id} value={item.id}>{item.title} · {index + 1}</option>)}
      </select>
      <button type="button" className="button button--secondary" onClick={newConversation} disabled={pending}>New conversation</button>
      <button type="button" className="button button--secondary" onClick={() => conversation && void history(conversation.id)} disabled={pending || !conversation}>Reload history</button>
    </div>
    {error ? <p role="alert">{error}</p> : null}
    <p role="status" aria-live="polite">{status}</p>
    {turns.length === 0 ? <p>No saved messages yet. Ask about an indexed transcript to see timestamped evidence.</p> :
      <ol className="chat-turns" aria-label="Conversation history">{turns.map((turn) => <li key={turn.id} className="chat-turn">
        <h3>You</h3><p className="evidence-text">{turn.question}</p>
        <h3>{turn.response.abstained ? "Evidence limitation" : "Tutorial evidence"}</h3>
        <p className="evidence-text">{turn.response.answer}</p>
        <p className="muted">{turn.response.provider} · {turn.response.model}</p>
        {turn.response.citations.length ? <ol aria-label={`Citations for question ${turn.sequence}`}>
          {turn.response.citations.map((citation) => <li key={citation.segment_id}>
            <Link className="citation-link" prefetch={false} href={`/projects/${projectId}/evidence/${citation.segment_id}`}>
              {citation.source_filename} · {timestamp(citation.start_ms)}–{timestamp(citation.end_ms)} · generation {citation.generation}
            </Link>
          </li>)}
        </ol> : null}
      </li>)}</ol>}
    {pending && partial ? <div aria-label="Answer delivery in progress"><p className="evidence-text">{partial}</p><p>Delivery in progress; citations appear after validation completes.</p></div> : null}
    {archived ? <p>Restore this project to ask new questions. Saved evidence remains available.</p> : <form onSubmit={(event) => void send(event)} className="stack">
      <div className="form-field"><label htmlFor="chat-source">Source filter</label>
        <select id="chat-source" disabled={pending} value={sourceId} onChange={(event) => { setSourceId(event.target.value); requestKey.current = ""; }}>
          <option value="">All indexed sources in this project</option>
          {sources.filter((source) => source.active_generation !== null).map((source) => <option value={source.id} key={source.id}>{source.filename}</option>)}
        </select>
      </div>
      <div className="form-field"><label htmlFor="chat-question">Question about the tutorial</label>
        <textarea ref={questionInput} id="chat-question" required minLength={2} maxLength={2000} rows={3} value={question} disabled={pending}
          aria-describedby="chat-question-help" onChange={(event) => { setQuestion(event.target.value); requestKey.current = ""; }} />
        <p id="chat-question-help" className="muted">Up to 2,000 characters. Unsupported questions receive a limitation, not invented tutorial content.</p>
      </div>
      <div className="chat-controls"><button type="submit" className="button" disabled={pending || question.trim().length < 2}>Ask with evidence</button>
        {pending ? <button type="button" className="button button--secondary" onClick={() => controller.current?.abort()}>Stop delivery</button> : null}
      </div>
    </form>}
  </div>;
}
