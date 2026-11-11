"use client";

import Link from "next/link";
import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import {
  parseDocumentList, parseDocumentView, parseSavedLearningContext,
  type CatalogPolicy, type DocumentView, type SavedLearningContext,
} from "@/lib/api/curriculum-contracts";
import { isCaptureFailure, LearningRequestError, learningError, learningRequest } from "./client-command";

export interface SavedContextWorkspaceProps {
  context: SavedLearningContext; projectId: string; archived: boolean;
  catalog: CatalogPolicy[]; initialDocuments: DocumentView[];
}
interface CaptureCommand { key: string; state: "uncertain" | "failed" }
interface HiddenDocument { document: DocumentView; checking: boolean }

function SavedContext({ context, projectId, archived, catalog, initialDocuments }: SavedContextWorkspaceProps) {
  const id = useId();
  const scope = { tenant_id: context.tenant_id, project_id: projectId };
  const base = `/api/projects/${projectId}/curriculum`;
  const contextPath = `${base}/contexts/${context.id}`;
  const [documents, setDocuments] = useState(initialDocuments);
  const [selected, setSelected] = useState("");
  const [consent, setConsent] = useState(false), [approvalPending, setApprovalPending] = useState(false);
  const [approvalUncertain, setApprovalUncertain] = useState(false);
  const [unconfirmedPolicy, setUnconfirmedPolicy] = useState<CatalogPolicy | null>(null);
  const [refreshPending, setRefreshPending] = useState(false);
  const [blocked, setBlocked] = useState(archived);
  const [error, setError] = useState(""), [status, setStatus] = useState("");
  const [busyDocuments, setBusyDocuments] = useState<Record<string, string>>({});
  const [commands, setCommands] = useState<Record<string, CaptureCommand>>({});
  const [confirmDocument, setConfirmDocument] = useState<string | null>(null);
  const [hiddenDocuments, setHiddenDocuments] = useState<Record<string, HiddenDocument>>({});
  const [confirmContext, setConfirmContext] = useState(false);
  const [contextState, setContextState] = useState<"live" | "deleting" | "uncertain" | "gone">("live");
  const epoch = useRef(0), alive = useRef(true), contextLive = useRef(true);
  const removed = useRef(new Set<string>()), revisions = useRef(new Map<string, number>());
  const controllers = useRef(new Set<AbortController>()), running = useRef(new Set<string>());
  const approvalKey = useRef<{ policy: CatalogPolicy; key: string } | null>(null);
  const captureKeys = useRef<Record<string, CaptureCommand>>({});
  useEffect(() => { alive.current = true; const pendingControllers = controllers.current; return () => { alive.current = false; for (const controller of pendingControllers) controller.abort(); }; }, []);
  function startController() { const controller = new AbortController(); controllers.current.add(controller); return controller; }
  function current(stamp: number) { return alive.current && contextLive.current && epoch.current === stamp; }
  function currentDocument(stamp: number, documentId: string, revision: number) { return current(stamp) && !removed.current.has(documentId) && (revisions.current.get(documentId) ?? 0) === revision; }
  function markGone() {
    contextLive.current = false; epoch.current++; setContextState("gone"); setDocuments([]); setHiddenDocuments({}); setError(""); setStatus("");
    for (const controller of controllers.current) controller.abort();
  }
  function notice(failure: unknown) {
    if (failure instanceof LearningRequestError && failure.code === "project_archived") setBlocked(true);
    setError(learningError(failure)); setStatus("");
  }
  async function verifyContext(stamp: number, signal: AbortSignal): Promise<boolean> {
    if (!current(stamp)) return false;
    try {
      parseSavedLearningContext(await learningRequest(contextPath, "GET", undefined, signal), scope, context.id);
      return current(stamp);
    } catch (failure) {
      if (!current(stamp)) return false;
      if (failure instanceof LearningRequestError && failure.status === 404) { markGone(); return false; }
      throw failure;
    }
  }
  function adopt(document: DocumentView) {
    if (removed.current.has(document.id)) return;
    revisions.current.set(document.id, (revisions.current.get(document.id) ?? 0) + 1);
    setDocuments((previous) => [...previous.filter((item) => item.id !== document.id), document]);
    if (document.status === "captured" || document.status === "failed") {
      if (document.status === "captured") delete captureKeys.current[document.id];
      else if (captureKeys.current[document.id]) captureKeys.current[document.id] = { ...captureKeys.current[document.id], state: "failed" };
      setCommands({ ...captureKeys.current });
    }
  }
  async function approve(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const policy = approvalUncertain && approvalKey.current ? approvalKey.current.policy : catalog.find((item) => item.id === selected);
    if (!policy || !consent || archived || blocked || !contextLive.current || running.current.has("approval")) return;
    if (!approvalKey.current) approvalKey.current = { policy, key: crypto.randomUUID() };
    setUnconfirmedPolicy(policy);
    const stamp = epoch.current, controller = startController(); running.current.add("approval"); setApprovalPending(true); setError(""); setStatus("");
    try {
      const document = parseDocumentView(await learningRequest(`${contextPath}/documentation`, "POST", { idempotency_key: approvalKey.current.key, catalog_id: policy.id, catalog_sha256: policy.fingerprint, consent: "retrieve_and_retain" }, controller.signal), scope, context.id);
      if (document.policy.fingerprint !== policy.fingerprint || document.policy.id !== policy.id || document.consent !== "retrieve_and_retain") throw new Error("Unmatched approval receipt");
      if (!await verifyContext(stamp, controller.signal)) return;
      adopt(document); setApprovalUncertain(false); setConsent(false); setSelected(""); approvalKey.current = null; setUnconfirmedPolicy(null);
      setStatus("Document approval saved. Capture it separately when you want to retrieve and retain the page.");
    } catch (failure) {
      if (!current(stamp)) return;
      // An approval endpoint 404 may mean the context was removed while the form was open.
      if (failure instanceof LearningRequestError && failure.status === 404) {
        try { if (!await verifyContext(stamp, controller.signal)) return; } catch {}
      }
      notice(failure); setApprovalUncertain(!(failure instanceof LearningRequestError) || failure.status >= 500);
    } finally { controllers.current.delete(controller); if (current(stamp)) { running.current.delete("approval"); setApprovalPending(false); } }
  }
  async function capture(document: DocumentView, retry = false) {
    if (!contextLive.current || removed.current.has(document.id) || archived || blocked || running.current.has(document.id)) return;
    let command = captureKeys.current[document.id];
    if (!command || retry) command = { key: crypto.randomUUID(), state: "uncertain" };
    captureKeys.current[document.id] = command; setCommands({ ...captureKeys.current });
    revisions.current.set(document.id, (revisions.current.get(document.id) ?? 0) + 1);
    const stamp = epoch.current, revision = revisions.current.get(document.id) ?? 0, controller = startController();
    running.current.add(document.id); setBusyDocuments((previous) => ({ ...previous, [document.id]: "Capturing…" })); setError(""); setStatus("");
    try {
      const receipt = parseDocumentView(await learningRequest(`${base}/documentation/${document.id}/capture`, "POST", { idempotency_key: command.key }, controller.signal), scope, context.id, document.id);
      if (!await verifyContext(stamp, controller.signal) || !currentDocument(stamp, document.id, revision)) return;
      if (receipt.status !== "captured" || receipt.policy.fingerprint !== document.policy.fingerprint || receipt.approved_by !== document.approved_by || receipt.approved_at !== document.approved_at) throw new Error("Unmatched capture receipt");
      adopt(receipt); setStatus("Documentation captured. Review the retained text and provenance below.");
    } catch (failure) {
      if (!currentDocument(stamp, document.id, revision)) return;
      try { if (!await verifyContext(stamp, controller.signal) || !currentDocument(stamp, document.id, revision)) return; }
      catch { if (!currentDocument(stamp, document.id, revision)) return; }
      if (isCaptureFailure(failure)) {
        captureKeys.current[document.id] = { key: command.key, state: "failed" };
        setCommands({ ...captureKeys.current });
        setDocuments((previous) => previous.map((item) => item.id === document.id ? { ...item, status: "failed", failure_code: failure.code } : item));
        setError("The capture did not complete. Its command will not run again. Review its status, then choose Retry capture to make a new explicit attempt."); setStatus("");
      } else {
        notice(failure);
      }
    } finally {
      controllers.current.delete(controller); running.current.delete(document.id);
      if (current(stamp)) setBusyDocuments((previous) => { const next = { ...previous }; delete next[document.id]; return next; });
    }
  }
  async function refresh(documentId?: string) {
    const slot = documentId ?? "refresh";
    if (!contextLive.current || running.current.has(slot) || (documentId && removed.current.has(documentId))) return;
    const stamp = epoch.current, revision = documentId ? revisions.current.get(documentId) ?? 0 : 0;
    // Any document mutation after this read starts makes its response stale for that document.
    const versions = new Map(revisions.current);
    const controller = startController(); running.current.add(slot); setError(""); setStatus("");
    if (documentId) setBusyDocuments((previous) => ({ ...previous, [documentId]: "Checking status…" })); else setRefreshPending(true);
    try {
      const value = await learningRequest(documentId ? `${base}/documentation/${documentId}` : `${contextPath}/documentation`, "GET", undefined, controller.signal);
      const receipts = documentId ? [parseDocumentView(value, scope, context.id, documentId)] : parseDocumentList(value, scope, context.id);
      if (!await verifyContext(stamp, controller.signal)) return;
      if (documentId && !currentDocument(stamp, documentId, revision)) return;
      for (const receipt of receipts) if ((revisions.current.get(receipt.id) ?? 0) === (versions.get(receipt.id) ?? 0) && !removed.current.has(receipt.id)) adopt(receipt);
      if (!documentId) {
        const present = new Set(receipts.map((item) => item.id));
        setDocuments((previous) => previous.filter((item) => {
          if (present.has(item.id) || (revisions.current.get(item.id) ?? 0) !== (versions.get(item.id) ?? 0)) return true;
          removed.current.add(item.id); return false;
        }));
      }
      setStatus(documentId ? "Capture status checked. No new page was retrieved." : "Saved approvals refreshed. No page was retrieved.");
    } catch (failure) {
      if (!current(stamp)) return;
      if (failure instanceof LearningRequestError && failure.status === 404) {
        try {
          if (!await verifyContext(stamp, controller.signal)) return;
          if (documentId && currentDocument(stamp, documentId, revision)) { removed.current.add(documentId); setDocuments((previous) => previous.filter((item) => item.id !== documentId)); }
        } catch {}
      }
      notice(failure);
    } finally {
      controllers.current.delete(controller); running.current.delete(slot);
      if (current(stamp)) {
        if (documentId && current(stamp)) setBusyDocuments((previous) => { const next = { ...previous }; delete next[documentId]; return next; });
        else if (!documentId) setRefreshPending(false);
      }
    }
  }
  async function deleteDocument(document: DocumentView) {
    if (!contextLive.current || running.current.has(`delete:${document.id}`)) return;
    const stamp = epoch.current, controller = startController();
    running.current.add(`delete:${document.id}`); removed.current.add(document.id); revisions.current.set(document.id, (revisions.current.get(document.id) ?? 0) + 1);
    setDocuments((previous) => previous.filter((item) => item.id !== document.id)); setBusyDocuments((previous) => { const next = { ...previous }; delete next[document.id]; return next; }); setConfirmDocument(null); setError(""); setStatus("");
    setHiddenDocuments((previous) => ({ ...previous, [document.id]: { document, checking: true } }));
    try {
      try { await learningRequest(`${base}/documentation/${document.id}`, "DELETE", undefined, controller.signal); }
      catch (failure) { if (!(failure instanceof LearningRequestError && failure.status === 404)) throw failure; }
      if (!await verifyContext(stamp, controller.signal)) return;
      setHiddenDocuments((previous) => { const next = { ...previous }; delete next[document.id]; return next; });
      setStatus("Document approval, retained text and capture receipts deleted.");
    } catch {
      if (current(stamp)) {
        setHiddenDocuments((previous) => ({ ...previous, [document.id]: { document, checking: false } }));
        setError("Document deletion could not be confirmed. Its text is hidden. Check deletion or repeat the deletion request.");
      }
    } finally { controllers.current.delete(controller); running.current.delete(`delete:${document.id}`); }
  }
  async function checkDeletion(document: DocumentView) {
    if (!contextLive.current || running.current.has(`delete:${document.id}`)) return;
    const stamp = epoch.current, controller = startController(); running.current.add(`delete:${document.id}`);
    setHiddenDocuments((previous) => ({ ...previous, [document.id]: { document, checking: true } })); setError("");
    try {
      const receipt = parseDocumentView(await learningRequest(`${base}/documentation/${document.id}`, "GET", undefined, controller.signal), scope, context.id, document.id);
      if (!await verifyContext(stamp, controller.signal)) return;
      removed.current.delete(document.id); revisions.current.set(document.id, (revisions.current.get(document.id) ?? 0) + 1); adopt(receipt);
      setHiddenDocuments((previous) => { const next = { ...previous }; delete next[document.id]; return next; });
      setStatus("The document still exists. Review it or request deletion again.");
    } catch (failure) {
      if (!current(stamp)) return;
      if (failure instanceof LearningRequestError && failure.status === 404) {
        try { if (!await verifyContext(stamp, controller.signal)) return; }
        catch (contextFailure) { setHiddenDocuments((previous) => ({ ...previous, [document.id]: { document, checking: false } })); notice(contextFailure); return; }
        setHiddenDocuments((previous) => { const next = { ...previous }; delete next[document.id]; return next; }); setStatus("Document deletion confirmed.");
      } else { setHiddenDocuments((previous) => ({ ...previous, [document.id]: { document, checking: false } })); notice(failure); }
    } finally { controllers.current.delete(controller); running.current.delete(`delete:${document.id}`); }
  }
  async function deleteContext() {
    if (running.current.has("delete-context")) return;
    running.current.add("delete-context"); contextLive.current = false; epoch.current++; setContextState("deleting"); setConfirmContext(false); setError(""); setStatus("");
    for (const active of controllers.current) active.abort();
    const stamp = epoch.current, controller = startController();
    try {
      try { await learningRequest(contextPath, "DELETE", undefined, controller.signal); }
      catch (failure) { if (!(failure instanceof LearningRequestError && failure.status === 404)) throw failure; }
      if (alive.current && epoch.current === stamp) markGone();
    } catch { if (alive.current && epoch.current === stamp) setContextState("uncertain"); }
    finally { controllers.current.delete(controller); running.current.delete("delete-context"); }
  }
  async function checkContextDeletion() {
    if (running.current.has("delete-context")) return;
    running.current.add("delete-context"); const stamp = epoch.current, controller = startController(); setError("");
    try {
      parseSavedLearningContext(await learningRequest(contextPath, "GET", undefined, controller.signal), scope, context.id);
      if (!alive.current || epoch.current !== stamp) return;
      // Reload through the server before showing any possibly stale retained copy.
      setStatus("The context still exists. Reload this page to review its current saved material or repeat deletion.");
    } catch (failure) {
      if (!alive.current || epoch.current !== stamp) return;
      if (failure instanceof LearningRequestError && failure.status === 404) markGone(); else setError(learningError(failure));
    } finally { controllers.current.delete(controller); running.current.delete("delete-context"); }
  }
  if (contextState !== "live") return <section className="stack" aria-label="Saved context status">
    {contextState === "gone" ? <p role="status">This saved context is no longer available. Its source may have been deleted, or the context or project was removed.</p> : contextState === "deleting" ? <p role="status">Deleting the saved context and its retained documentation…</p> : <><p role="alert">Context deletion could not be confirmed. Saved text stays hidden until you check the result.</p><div className="form-actions"><button type="button" className="button button--secondary" onClick={() => void checkContextDeletion()}>Check context deletion</button><button type="button" className="button button--danger" onClick={() => void deleteContext()}>Repeat context deletion</button></div>{status ? <p role="status">{status}</p> : null}{error ? <p role="alert">{error}</p> : null}</>}
    <Link href={`/projects/${projectId}/learning`}>Return to learning material</Link>
  </section>;
  const chosenPolicy = approvalUncertain && unconfirmedPolicy ? unconfirmedPolicy : catalog.find((item) => item.id === selected);
  return <div className="stack">
    <section className="panel stack" aria-labelledby={`${id}-context`}>
      <h2 id={`${id}-context`}>Saved learning context</h2>
      <p>These source versions and preferences are fixed. Create another context to change them. Bookmark this page to return to the saved context.</p>
      <p>Saved {new Date(context.created_at).toLocaleString()}. Assignment generation is not available yet.</p>
      <dl><dt>Programming experience</dt><dd>{context.learner.experience}</dd><dt>Desired difficulty</dt><dd>{context.learner.difficulty}</dd><dt>Output language</dt><dd>{context.learner.language === "en" ? "English" : "Turkish"}</dd><dt>Available effort</dt><dd>{context.learner.available_minutes} minutes</dd><dt>Prerequisite topics</dt><dd>{context.learner.allow_prerequisites ? "Permitted" : "Not permitted"}</dd><dt>Extension topics</dt><dd>{context.learner.allow_extensions ? "Permitted" : "Not permitted"}</dd><dt>External documentation</dt><dd>{context.learner.allow_external_documentation ? "Separate page approval required" : "Not permitted"}</dd></dl>
      <ul>{context.selected_sources.map((source) => <li key={source.source_id}>{source.source_filename} · generation {source.generation} · {source.processing_version}</li>)}</ul><p><Link href={`/projects/${projectId}#workspace-heading`}>Manage tutorial sources</Link></p>
      {archived || blocked ? <p role="status">This project is archived. Read and delete remain available; new approvals and captures require restoring the project.</p> : null}
      {!confirmContext ? <button type="button" className="button button--danger" onClick={() => setConfirmContext(true)}>Delete saved context</button> : <div className="stack" role="group" aria-label="Confirm context deletion"><p>This deletes the saved context, its document approvals and retained copies. Tutorial sources remain in the project.</p><div className="form-actions"><button type="button" className="button button--danger" onClick={() => void deleteContext()}>Confirm context deletion</button><button type="button" className="button button--secondary" onClick={() => setConfirmContext(false)}>Keep context</button></div></div>}
    </section>
    <section className="panel stack" aria-labelledby={`${id}-documentation`}>
      <h2 id={`${id}-documentation`}>Official documentation</h2>
      <p>External pages are separate evidence, not proof that the tutorial covered a topic. Approving a page saves your permission; Capture document is a separate request that retrieves and retains its text. No page is retrieved automatically.</p>
      {!context.learner.allow_external_documentation ? <p>This context permits tutorial material only. Create a new context with official documentation enabled to approve a page.</p> : <form className="stack" aria-label="Approve official documentation" aria-busy={approvalPending} onSubmit={(event) => void approve(event)}>
        <fieldset className="stack" disabled={approvalPending || archived || blocked}><legend>Choose and approve one catalog page</legend>
          <div className="field"><label htmlFor={`${id}-catalog`}>Official page</label><select id={`${id}-catalog`} value={selected} required onChange={(event) => { approvalKey.current = null; setUnconfirmedPolicy(null); setSelected(event.target.value); setConsent(false); setApprovalUncertain(false); setError(""); }}><option value="" disabled>Choose an official page</option>{catalog.map((policy) => <option key={policy.id} value={policy.id}>{policy.title}</option>)}</select></div>
          {chosenPolicy ? <div className="stack"><p><a href={chosenPolicy.url} target="_blank" rel="noreferrer">{chosenPolicy.url}</a></p><p>English · version unknown (unversioned official page) · {chosenPolicy.license_name}</p><p>{chosenPolicy.attribution}</p><details><summary>License and retrieval policy</summary><p>Only this catalog page is approved. The saved text is retained until the document, context, selected source or project is deleted. No crawling or automatic refresh.</p><p><a href={chosenPolicy.license_url} target="_blank" rel="noreferrer">License source</a></p><pre className="documentation-text">{chosenPolicy.license_text}</pre></details></div> : null}
          <label><input type="checkbox" required checked={consent} onChange={(event) => { approvalKey.current = null; setUnconfirmedPolicy(null); setConsent(event.target.checked); setApprovalUncertain(false); }} /> I approve retrieving and retaining this selected page for this context</label>
          <button type="submit" className="button button--primary" disabled={!chosenPolicy || !consent}>{approvalPending ? "Saving approval…" : approvalUncertain ? "Check approval delivery" : "Save document approval"}</button>
        </fieldset>
      </form>}
      <div className="form-actions"><button type="button" className="button button--secondary" disabled={refreshPending || approvalPending || Object.keys(busyDocuments).length > 0} onClick={() => void refresh()}>{refreshPending ? "Refreshing approvals…" : "Refresh saved approvals"}</button></div>
      {approvalUncertain ? <p>Approval delivery is uncertain. Check delivery with the unchanged page and consent to repeat the same approval request.</p> : null}
      {documents.length === 0 ? <p>No retained documentation or approvals are available.</p> : null}
      {documents.map((document) => <article key={document.id} className="panel stack" aria-label={`Document ${document.policy.title}`} aria-busy={Boolean(busyDocuments[document.id])}>
        <h3>{document.policy.title}</h3><p>State: {document.status}. Approved {new Date(document.approved_at).toLocaleString()}.</p>
        <p><a href={document.policy.url} target="_blank" rel="noreferrer">Official source page</a></p><p>{document.policy.attribution} · {document.policy.license_name}</p>
        {document.failure_code ? <p className="field-hint">Capture failure: {document.failure_code}</p> : null}
        {!document.snapshot ? <><p>Only the approving member can capture this document. A capture uses this page and consent; it does not start assignment generation.</p><div className="form-actions">
          <button type="button" className="button button--primary" disabled={archived || blocked || Boolean(busyDocuments[document.id])} onClick={() => void capture(document, commands[document.id]?.state === "failed" || (!commands[document.id] && document.status === "failed"))}>{busyDocuments[document.id] ?? (commands[document.id]?.state === "uncertain" ? "Check capture delivery" : document.status === "capturing" ? "Start another capture" : document.status === "failed" || commands[document.id]?.state === "failed" ? "Retry capture" : "Capture document")}</button>
          <button type="button" className="button button--secondary" disabled={Boolean(busyDocuments[document.id])} onClick={() => void refresh(document.id)}>Check capture status</button>
        </div>{commands[document.id]?.state === "uncertain" ? <p>Delivery is uncertain. Check capture delivery repeats your unchanged request; it can retrieve the page only if that request was not already accepted. Checking status only reads saved state.</p> : null}</> : <div className="stack">
          <p>Retrieved {new Date(document.snapshot.retrieved_at).toLocaleString()} · version {document.snapshot.detected_version ?? "unknown (unversioned page)"}.</p>
          <p>Retained documentation text. It may contain incorrect or misleading instructions; review it as source material.</p>
          {document.snapshot.excerpts.map((excerpt, index) => <section key={excerpt.id} id={`excerpt-${excerpt.id}`} className="stack" aria-label={`Documentation excerpt ${index + 1}`}><h4><a href={`#excerpt-${excerpt.id}`}>Excerpt {index + 1}</a></h4><pre className="documentation-text">{excerpt.text}</pre><details><summary>Excerpt identity</summary><p>{excerpt.id}</p><p className="documentation-hash">SHA-256: {excerpt.content_sha256}</p></details></section>)}
          <details><summary>Capture provenance and license</summary><p>Canonical URL: <a href={document.snapshot.url} target="_blank" rel="noreferrer">{document.snapshot.url}</a></p><p className="documentation-hash">Text SHA-256: {document.snapshot.content_sha256}</p><p className="documentation-hash">HTML SHA-256: {document.raw_sha256}</p><p>HTML bytes: {document.raw_bytes}. The original HTML is not retained.</p><p><a href={document.policy.license_url} target="_blank" rel="noreferrer">{document.policy.license_name} license source</a></p><pre className="documentation-text">{document.policy.license_text}</pre></details>
        </div>}
        {confirmDocument === document.id ? <div className="stack" role="group" aria-label="Confirm document deletion"><p>Delete this approval, its retained text and capture receipts?</p><div className="form-actions"><button type="button" className="button button--danger" onClick={() => void deleteDocument(document)}>Confirm document deletion</button><button type="button" className="button button--secondary" onClick={() => setConfirmDocument(null)}>Keep document</button></div></div> : <button type="button" className="button button--danger" onClick={() => setConfirmDocument(document.id)}>Delete document</button>}
      </article>)}
      {Object.values(hiddenDocuments).map(({ document, checking }) => <div key={document.id} className="stack" aria-label="Unconfirmed document deletion"><p>{checking ? "Checking document deletion…" : "Document deletion is unconfirmed. Its retained text is hidden."}</p><div className="form-actions"><button type="button" className="button button--secondary" disabled={checking} onClick={() => void checkDeletion(document)}>Check document deletion</button><button type="button" className="button button--danger" disabled={checking} onClick={() => void deleteDocument(document)}>Repeat document deletion</button></div></div>)}
    </section>
    {status ? <p role="status" aria-live="polite">{status}</p> : null}{error ? <p role="alert">{error}</p> : null}
  </div>;
}

export function SavedContextWorkspace(props: SavedContextWorkspaceProps) { return <SavedContext key={`${props.context.tenant_id}:${props.projectId}:${props.context.id}`} {...props} />; }
