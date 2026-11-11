"use client";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { parseDraftList, type DraftList } from "@/lib/api/draft-contracts";
import type { LearningScope } from "@/lib/api/curriculum-contracts";
import { learningRequest, learningError, LearningRequestError } from "./client-command";

export function DraftListWorkspace({ scope, contextId, initial }: { scope: LearningScope; contextId: string; initial: DraftList }) {
  const [page, setPage] = useState(initial), [busy, setBusy] = useState(false), [error, setError] = useState("");
  const [gone, setGone] = useState(false), [cursor, setCursor] = useState<string | undefined>();
  const alive = useRef(true), controller = useRef<AbortController | null>(null);
  const load = useCallback(async (after?: string) => {
    if (controller.current) return;
    const active = new AbortController(); controller.current = active; setBusy(true); setError("");
    try {
      const value = await learningRequest(`/api/projects/${scope.project_id}/curriculum/contexts/${contextId}/drafts${after ? `?after=${after}` : ""}`, "GET", undefined, active.signal);
      const result = parseDraftList(value, scope, contextId, after);
      if (alive.current) { setPage(result); setCursor(after); }
    } catch (failure) {
      if (alive.current) { if (failure instanceof LearningRequestError && failure.status === 404) { setGone(true); setPage({ items: [], next_after: null }); } else setError(learningError(failure)); }
    } finally { controller.current = null; if (alive.current) setBusy(false); }
  }, [scope, contextId]);
  useEffect(() => {
    alive.current = true;
    const focus = () => { void load(); };
    window.addEventListener("focus", focus);
    return () => { alive.current = false; controller.current?.abort(); window.removeEventListener("focus", focus); };
  }, [load]);
  return <section className="panel stack" aria-label="Saved assignment drafts" aria-busy={busy}>
    <h2>Saved assignment drafts</h2>
    <p>Review existing drafts for this fixed selection. Assignment generation and activation are not available yet.</p>
    {gone ? <p role="status">This saved selection is no longer available. Its drafts may have been deleted with a dependency.</p> : <>
      <button className="button button--secondary" disabled={busy} onClick={() => void load()}>Refresh drafts</button>
      {page.items.length ? <ul className="stack">{page.items.map((draft) => <li key={draft.id}>
        <Link href={`/projects/${scope.project_id}/learning/drafts/${draft.id}`}>{draft.title}</Link>
        <p>Revision {draft.revision} · saved {new Date(draft.created_at).toLocaleString()}</p>
      </li>)}</ul> : <p role="status">{cursor ? "No more saved drafts on this page." : "No assignment drafts have been saved for this selection."}</p>}
      {page.next_after ? <button className="button button--secondary" disabled={busy} onClick={() => void load(page.next_after!)}>Next drafts</button> : null}
    </>}
    {busy ? <p role="status">Loading saved drafts…</p> : null}{error ? <p role="alert">{error}</p> : null}
  </section>;
}
