"use client";
import Link from "next/link";
import { useCallback, useEffect, useId, useRef, useState, type FormEvent } from "react";
import { draftContent, parseDraftRevision, parseDraftReplace, type AssignmentContent, type DraftReplaceBody, type DraftRevision } from "@/lib/api/draft-contracts";
import type { SavedLearningContext } from "@/lib/api/curriculum-contracts";
import { parseAssignmentActivate, parseAssignmentActivation, type AssignmentActivateBody, type AssignmentActivation } from "@/lib/api/activation-contracts";
import { learningFields } from "@/lib/api/curriculum-contracts";
import { timestamp } from "@/lib/api/chat-contracts";
import { learningError, learningRequest, LearningRequestError } from "./client-command";

interface Props { initial: DraftRevision; context: SavedLearningContext; archived: boolean; initialActivation?: AssignmentActivation | null; activatedVersion?: AssignmentActivation }
function Editor({ initial, context, archived, initialActivation = null, activatedVersion }: Props) {
  const prefix = useId(), scope = { tenant_id: initial.tenant_id, project_id: initial.project_id };
  const draftPath = `/api/projects/${initial.project_id}/curriculum/drafts/${initial.id}`;
  const path = activatedVersion ? `/api/projects/${initial.project_id}/curriculum/assignments/${activatedVersion.id}` : draftPath;
  const [saved, setSaved] = useState<DraftRevision | null>(initial), [edit, setEdit] = useState<AssignmentContent | null>(() => draftContent(initial));
  const [busy, setBusy] = useState(false), [uncertain, setUncertain] = useState(false), [conflict, setConflict] = useState(false);
  const [blocked, setBlocked] = useState(archived), [deletion, setDeletion] = useState<"live" | "uncertain" | "gone">("live");
  const [confirm, setConfirm] = useState(false), [error, setError] = useState(""), [status, setStatus] = useState("");
  const [history, setHistory] = useState<DraftRevision | null>(null), [historyNumber, setHistoryNumber] = useState(1);
  const [shownHints, setShownHints] = useState(0);
  const [activation, setActivation] = useState<AssignmentActivation | null>(initialActivation);
  const [activationConsent, setActivationConsent] = useState(false), [activationUncertain, setActivationUncertain] = useState(false);
  const activationCommand = useRef<{ body: AssignmentActivateBody; reviewed: DraftRevision } | null>(null);
  const alive = useRef(true), serial = useRef(0), active = useRef<AbortController | null>(null);
  const command = useRef<DraftReplaceBody | null>(null), live = useRef(true), busyRef = useRef(false);
  const savedRef = useRef(saved);
  useEffect(() => { savedRef.current = saved; }, [saved]);
  const stop = useCallback(() => { serial.current++; active.current?.abort(); }, []);
  const dirty = saved && edit ? JSON.stringify(edit) !== JSON.stringify(draftContent(saved)) : false;
  function begin() { serial.current++; active.current?.abort(); active.current = new AbortController(); busyRef.current = true; setBusy(true); setError(""); return { stamp: serial.current, signal: active.current.signal }; }
  function current(stamp: number) { return alive.current && serial.current === stamp; }
  function finish(stamp: number) { if (current(stamp)) { active.current = null; busyRef.current = false; setBusy(false); } }
  function clearText() { setSaved(null); setEdit(null); setHistory(null); setShownHints(0); command.current = null; setUncertain(false); setActivation(null); setActivationConsent(false); setActivationUncertain(false); activationCommand.current = null; }
  function missing() { live.current = false; setDeletion("gone"); clearText(); setError(""); setStatus(activatedVersion ? "This activated version is no longer available. Its draft or a dependency may have been deleted." : "This draft is no longer available. It may have been deleted with a selected source, context or document."); }
  function notice(failure: unknown) { if (failure instanceof LearningRequestError && failure.code === "project_archived") setBlocked(true); setError(learningError(failure)); }
  function parse(value: unknown, revision?: number) { return parseDraftRevision(value, scope, context, initial.id, revision); }
  const parseRead = useCallback((value: unknown) => {
    const expected = { tenant_id: initial.tenant_id, project_id: initial.project_id };
    if (!activatedVersion) return parseDraftRevision(value, expected, context, initial.id);
    const received = parseAssignmentActivation(value, expected, context, initial.id, activatedVersion.revision, activatedVersion.id);
    const original = parseAssignmentActivation(activatedVersion, expected, context, initial.id, activatedVersion.revision, activatedVersion.id);
    if (JSON.stringify(received) !== JSON.stringify(original)) throw new Error("Changed activated version");
    return received.draft;
  }, [activatedVersion, context, initial.id, initial.tenant_id, initial.project_id]);
  const checkHead = useCallback(async () => {
    if (!live.current || busyRef.current || !savedRef.current) return;
    const stamp = serial.current, controller = new AbortController(); active.current = controller; busyRef.current = true; setBusy(true);
    try {
      const next = parseRead(await learningRequest(path, "GET", undefined, controller.signal));
      if (alive.current && serial.current === stamp && live.current && savedRef.current && next.revision > savedRef.current.revision) { setConflict(true); setStatus("A newer revision is available. Your unsaved edits have been kept. Discard them explicitly to load the latest revision."); }
    } catch (failure) {
      if (alive.current && serial.current === stamp && live.current) {
        if (failure instanceof LearningRequestError && failure.status === 404) {
          live.current = false; setDeletion("gone"); setSaved(null); setEdit(null); setHistory(null); command.current = null; setUncertain(false); setActivation(null); setActivationConsent(false); setActivationUncertain(false); activationCommand.current = null; setError(""); setStatus(activatedVersion ? "This activated version is no longer available. Its retained text has been cleared." : "This draft is no longer available. Its retained text has been cleared.");
        } else setError(learningError(failure));
      }
    } finally { if (alive.current && serial.current === stamp) { active.current = null; busyRef.current = false; setBusy(false); } }
  }, [parseRead, path, activatedVersion]);
  useEffect(() => {
    alive.current = true;
    const focus = () => { void checkHead(); };
    window.addEventListener("focus", focus);
    return () => { alive.current = false; stop(); window.removeEventListener("focus", focus); };
  }, [checkHead, stop]);
  function adopt(next: DraftRevision) { setSaved(next); setEdit(draftContent(next)); setHistory(null); setShownHints(0); setConflict(false); command.current = null; setUncertain(false); setActivationConsent(false); }
  async function reload() {
    if (busyRef.current || !live.current) return;
    const { stamp, signal } = begin();
    try { const next = parseRead(await learningRequest(path, "GET", undefined, signal)); if (current(stamp)) { adopt(next); setActivationConsent(false); setStatus(activatedVersion ? "Activated version checked. Its saved revision is unchanged." : "Latest saved revision loaded."); } }
    catch (failure) { if (current(stamp)) { if (failure instanceof LearningRequestError && failure.status === 404) missing(); else notice(failure); } }
    finally { finish(stamp); }
  }
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (activatedVersion || activationUncertain || busyRef.current || !live.current || !saved || !edit || blocked || conflict && !uncertain) return;
    try { if (!command.current) command.current = parseDraftReplace({ idempotency_key: crypto.randomUUID(), expected_revision: saved.revision, content: edit, documentation_ids: saved.documentation_ids }); }
    catch { setError("Check the draft fields, required text and estimated effort before saving."); return; }
    const body = command.current, { stamp, signal } = begin(); setStatus("");
    try {
      const receipt = parse(await learningRequest(path, "PUT", body, signal), body.expected_revision + 1);
      if (JSON.stringify(draftContent(receipt)) !== JSON.stringify(body.content) || JSON.stringify(receipt.documentation_ids) !== JSON.stringify(body.documentation_ids)) throw new Error("Unmatched draft receipt");
      if (!current(stamp) || !live.current) return;
      // A replay may return an older accepted revision. Recheck the live head before
      // restoring any text; a deleted dependency must not be resurrected by it.
      const head = parse(await learningRequest(path, "GET", undefined, signal));
      if (!current(stamp)) return;
      if (head.revision < receipt.revision) throw new Error("Stale draft head");
      adopt(receipt);
      if (head.revision > receipt.revision) { setConflict(true); setStatus(`Revision ${receipt.revision} was saved; a newer revision also exists. Load it explicitly before editing again.`); }
      else setStatus(`Revision ${receipt.revision} saved. This is still an assignment draft.`);
    } catch (failure) {
      if (!current(stamp)) return;
      if (failure instanceof LearningRequestError && failure.status === 404) missing();
      else if (failure instanceof LearningRequestError && failure.status < 500) {
        command.current = null; setUncertain(false); if (failure.code === "draft_revision_conflict") setConflict(true); notice(failure);
      } else { setUncertain(true); setError("Save delivery could not be confirmed. Your exact fields and request key are kept. Check save delivery before making another edit."); }
    } finally { finish(stamp); }
  }
  async function activate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (activatedVersion || busyRef.current || !live.current || !saved || !edit) return;
    if (!activationCommand.current) {
      if (blocked || dirty || uncertain || conflict || history || !activationConsent) return;
      activationCommand.current = {
        body: parseAssignmentActivate({ idempotency_key: crypto.randomUUID(), expected_revision: saved.revision, consent: "activate_reviewed_revision" }),
        reviewed: parse(saved, saved.revision),
      };
    }
    const request = activationCommand.current, { stamp, signal } = begin(); setStatus("");
    try {
      const receipt = parseAssignmentActivation(await learningRequest(`${draftPath}/activate`, "POST", request.body, signal), scope, context, initial.id, request.body.expected_revision);
      if (JSON.stringify(receipt.draft) !== JSON.stringify(request.reviewed)) throw new Error("Changed reviewed revision");
      if (!current(stamp) || !live.current) return;
      const head = parse(await learningRequest(draftPath, "GET", undefined, signal));
      if (!current(stamp)) return;
      if (head.revision < receipt.revision) throw new Error("Stale activation head");
      setActivation(receipt); activationCommand.current = null; setActivationUncertain(false); setActivationConsent(false);
      if (head.revision > saved.revision) setConflict(true);
      setStatus(`Revision ${receipt.revision} activated. Later draft edits will not change this version.`);
    } catch (failure) {
      if (!current(stamp)) return;
      if (failure instanceof LearningRequestError && failure.status === 404) missing();
      else if (failure instanceof LearningRequestError && failure.status < 500) {
        activationCommand.current = null; setActivationUncertain(false); setActivationConsent(false);
        if (failure.code === "draft_revision_conflict") setConflict(true);
        notice(failure);
      } else {
        setActivationUncertain(true); setError("Activation delivery could not be confirmed. The reviewed revision and original request are kept. Check activation delivery before editing or confirming another revision.");
      }
    } finally { finish(stamp); }
  }
  async function checkActivation() {
    if (activatedVersion || busyRef.current || !live.current || activationUncertain) return;
    const { stamp, signal } = begin();
    try {
      const state = learningFields(await learningRequest(`${draftPath}/activation`, "GET", undefined, signal), ["activation"]);
      const confirmed = state.activation === null ? null : parseAssignmentActivation(state.activation, scope, context, initial.id);
      const head = parse(await learningRequest(draftPath, "GET", undefined, signal));
      if (!current(stamp)) return;
      if (confirmed && confirmed.revision > head.revision) throw new Error("Stale activation state");
      setActivation(confirmed); if (saved && head.revision > saved.revision) setConflict(true);
      setStatus(confirmed ? `Activated revision ${confirmed.revision} checked.` : "No saved revision has been activated.");
    } catch (failure) { if (current(stamp)) { if (failure instanceof LearningRequestError && failure.status === 404) missing(); else notice(failure); } }
    finally { finish(stamp); }
  }
  async function loadHistory(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (activatedVersion || activationUncertain || busyRef.current || !live.current || !saved) return;
    const { stamp, signal } = begin(); setHistory(null); setShownHints(0); setActivationConsent(false);
    try {
      // Confirm the current draft still exists before reading its immutable past.
      const head = parse(await learningRequest(path, "GET", undefined, signal));
      const next = parse(await learningRequest(`${path}/revisions/${historyNumber}`, "GET", undefined, signal), historyNumber);
      if (current(stamp)) { if (head.revision > saved.revision) setConflict(true); setHistory(next); setStatus(`Viewing saved revision ${next.revision}. It is read only.`); }
    } catch (failure) { if (current(stamp)) { if (failure instanceof LearningRequestError && failure.status === 404) {
      // A missing historical revision alone does not establish draft deletion.
      try { parse(await learningRequest(path, "GET", undefined, signal)); setError("That saved revision is not available."); }
      catch (check) { if (current(stamp)) { if (check instanceof LearningRequestError && check.status === 404) missing(); else notice(check); } }
    } else notice(failure); } }
    finally { finish(stamp); }
  }
  async function remove(checkOnly = false) {
    live.current = false; const { stamp, signal } = begin(); clearText(); setConfirm(false); setDeletion("uncertain"); setStatus("");
    try {
      if (!checkOnly) { try { await learningRequest(path, "DELETE", undefined, signal); } catch (failure) { if (!(failure instanceof LearningRequestError && failure.status === 404)) throw failure; } if (current(stamp)) missing(); }
      else { const next = parse(await learningRequest(path, "GET", undefined, signal)); if (current(stamp)) { live.current = true; setDeletion("live"); adopt(next); setStatus("The draft still exists. Review it or request deletion again."); } }
    } catch (failure) { if (current(stamp)) { if (failure instanceof LearningRequestError && failure.status === 404) missing(); else setError("Draft deletion could not be confirmed. Its text stays hidden until you check deletion."); } }
    finally { finish(stamp); }
  }
  if (deletion !== "live" || !saved || !edit) return <section className="panel stack" aria-label="Draft status">
    {status ? <p role="status">{status}</p> : null}{error ? <p role="alert">{error}</p> : null}
    {deletion === "uncertain" ? <><p>Draft text is hidden while deletion is unconfirmed.</p><div className="form-actions"><button className="button button--secondary" disabled={busy} onClick={() => void remove(true)}>Check draft deletion</button><button className="button button--danger" disabled={busy} onClick={() => void remove()}>Repeat draft deletion</button></div></> : null}
    <Link href={`/projects/${initial.project_id}/learning/contexts/${context.id}`}>Return to saved selection</Link>
  </section>;
  const view = history ?? saved, shown = history ? draftContent(history) : edit;
  const disabled = Boolean(activatedVersion) || busy || blocked || uncertain || activationUncertain || conflict || Boolean(history);
  function change(value: AssignmentContent) { setEdit(value); setActivationConsent(false); setStatus(""); }
  function field(label: string, value: string, set: (text: string) => void, max = 4000) {
    const fieldId = `${prefix}-${label.replace(/[^a-z0-9]/gi, "-")}`;
    return <div className="field" key={label}><label htmlFor={fieldId}>{label}</label><textarea id={fieldId} value={value} required maxLength={max} rows={3} onChange={(event) => set(event.target.value)} /></div>;
  }
  const links = (tutorial: string[], docs: string[] = []) => <ul>{tutorial.map((id) => <li key={id}><a href={`#tutorial-${id}`}>Tutorial evidence {view.assignment.tutorial_evidence.findIndex((item) => item.segment_id === id) + 1}</a></li>)}{docs.map((id) => <li key={id}><a href={`#draft-excerpt-${id}`}>External documentation excerpt</a></li>)}</ul>;
  return <div className="stack stack--large">
    <section className="panel stack" aria-label="Draft revision controls">
      <h2>{activatedVersion ? "Activated assignment" : "Assignment draft"} · revision {saved.revision}</h2><p>Saved {new Date(saved.created_at).toLocaleString()}. Structural checks are not semantic or model-quality approval.</p>
      {activatedVersion ? <p>Activated {new Date(activatedVersion.activated_at).toLocaleString()}. This accepted version is read only. Corrections require reviewing and activating another saved draft revision.</p> : null}
      {blocked && !activatedVersion ? <p role="status">This project is archived. Read and delete remain available; restore the project before editing.</p> : null}
      {conflict ? <p role="alert">A newer revision exists. Your edits have not overwritten it.</p> : null}
      {uncertain ? <p role="status">Save delivery is uncertain. Fields are locked so the original request can be replayed unchanged.</p> : null}
      <div className="form-actions"><button className="button button--secondary" disabled={busy || uncertain || activationUncertain} onClick={() => void reload()}>{activatedVersion ? "Refresh activated version" : dirty || conflict ? "Discard edits and load latest" : "Refresh saved draft"}</button>{!activatedVersion ? <button className="button button--danger" onClick={() => setConfirm(true)}>Delete draft</button> : null}</div>
      {confirm ? <div role="group" aria-label="Confirm draft deletion"><p>Delete this draft, all its saved revisions and every activated assignment version? Tutorial sources and document approvals remain.</p><div className="form-actions"><button className="button button--danger" onClick={() => void remove()}>Confirm draft deletion</button><button className="button button--secondary" onClick={() => setConfirm(false)}>Keep draft</button></div></div> : null}
      {!activatedVersion ? <details><summary>Revision history</summary><form className="stack" onSubmit={(event) => void loadHistory(event)}><label htmlFor={`${prefix}-revision`}>Saved revision</label><input id={`${prefix}-revision`} type="number" min={1} max={saved.revision} value={historyNumber} onChange={(event) => setHistoryNumber(Number(event.target.value))} required /><button className="button button--secondary" disabled={busy || uncertain || activationUncertain}>View saved revision</button></form></details> : null}
      {history ? <><p role="status">Viewing revision {history.revision}, read only. Your unsaved current edits are kept.</p><button className="button button--secondary" onClick={() => { setHistory(null); setShownHints(0); setStatus(`Returned to current draft revision ${saved.revision}.`); }}>Return to current draft</button></> : null}
    </section>
    {!activatedVersion ? <section className="panel stack" aria-label="Activate reviewed assignment">
      <h2>Activate a reviewed revision</h2>
      <p>Activation fixes the saved wording, requirements and evidence for this revision. It records your acceptance, not an independent quality assessment. Later edits do not change it. Deleting this draft or a dependency removes its activated versions too.</p>
      {activation ? <p>Confirmed activated revision: {activation.revision}. <Link href={`/projects/${initial.project_id}/learning/assignments/${activation.id}`}>View activated version</Link></p> : <p>No activated revision has been confirmed.</p>}
      <button className="button button--secondary" disabled={busy || activationUncertain} onClick={() => void checkActivation()}>Check activation status</button>
      {dirty ? <p>Save your edits before reviewing and activating the saved revision.</p> : null}
      {history ? <p>Historical revisions are read only. Return to the current saved draft to activate it.</p> : null}
      <form className="stack" onSubmit={(event) => void activate(event)}>
        <label><input type="checkbox" checked={activationConsent} disabled={busy || blocked || dirty || uncertain || activationUncertain || conflict || Boolean(history) || activation?.revision === saved.revision} onChange={(event) => setActivationConsent(event.target.checked)} /> I have reviewed saved revision {saved.revision} and accept its requirements and evidence</label>
        <button className="button button--primary" type="submit" disabled={busy || !activationUncertain && (blocked || dirty || uncertain || conflict || Boolean(history) || !activationConsent || activation?.revision === saved.revision)}>{busy ? "Checking saved state…" : activationUncertain ? "Check activation delivery" : `Activate saved revision ${saved.revision}`}</button>
      </form>
      {activationUncertain ? <p role="status">Activation is uncertain. The confirmation will replay the original reviewed revision unchanged.</p> : null}
    </section> : null}
    <form className="panel stack" aria-label={activatedVersion ? "Activated assignment content" : "Edit assignment draft"} aria-busy={busy} onSubmit={(event) => void save(event)}>
      <p>{activatedVersion ? "The accepted wording and evidence belong to this fixed version." : "Edit wording and estimated effort. Requirement labels, structural links, source versions and selected documents stay fixed in this editor."}</p>
      <fieldset className="stack" disabled={disabled}><legend>{history ? `Saved revision ${history.revision}` : "Draft content"}</legend>
        {field("Title", shown.title, (title) => change({ ...edit, title }), 200)}
        {field("Scenario", shown.scenario, (scenario) => change({ ...edit, scenario }))}
        <div className="field"><label htmlFor={`${prefix}-effort`}>Estimated effort (minutes)</label><input id={`${prefix}-effort`} type="number" min={1} max={context.learner.available_minutes} required value={shown.estimated_minutes} onChange={(event) => change({ ...edit, estimated_minutes: Number(event.target.value) })} /></div>
        <h3>Learning objectives</h3>{shown.objectives.map((item, i) => <div className="stack" key={item.id}>{field(`Objective ${i + 1}`, item.description, (description) => change({ ...edit, objectives: edit.objectives.map((row, at) => at === i ? { ...row, description } : row) }))}{links(item.tutorial_segment_ids)}</div>)}
        <h3>Requirements</h3>{shown.requirements.map((item, i) => <div className="stack" key={item.id}><p>{item.label === "covered" ? "Tutorial covered" : item.label === "prerequisite" ? "Prerequisite (external)" : "Extension (external)"}</p>{field(`Requirement ${i + 1}`, item.description, (description) => change({ ...edit, requirements: edit.requirements.map((row, at) => at === i ? { ...row, description } : row) }))}<p>Learning objectives: {item.objective_ids.map((key) => shown.objectives.findIndex((row) => row.id === key) + 1).join(", ")}</p>{links(item.tutorial_segment_ids, item.documentation_excerpt_ids)}</div>)}
        <h3>Constraints</h3>{shown.constraints.length ? shown.constraints.map((item, i) => field(`Constraint ${i + 1}`, item, (value) => change({ ...edit, constraints: edit.constraints.map((row, at) => at === i ? value : row) }))) : <p>No additional constraints.</p>}
        <h3>Deliverables</h3>{shown.deliverables.map((item, i) => field(`Deliverable ${i + 1}`, item, (value) => change({ ...edit, deliverables: edit.deliverables.map((row, at) => at === i ? value : row) })))}
        <h3>Acceptance criteria</h3>{shown.acceptance_criteria.map((item, i) => <div key={item.id}>{field(`Acceptance criterion ${i + 1}`, item.description, (description) => change({ ...edit, acceptance_criteria: edit.acceptance_criteria.map((row, at) => at === i ? { ...row, description } : row) }))}<p>Requirements: {item.requirement_ids.map((key) => shown.requirements.findIndex((row) => row.id === key) + 1).join(", ")}</p></div>) }
        <h3>Rubric</h3>{shown.rubric.map((item, i) => <div key={item.id}>{field(`Rubric criterion ${i + 1}`, item.description, (description) => change({ ...edit, rubric: edit.rubric.map((row, at) => at === i ? { ...row, description } : row) }))}<p>Acceptance criteria: {item.acceptance_criterion_ids.map((key) => shown.acceptance_criteria.findIndex((row) => row.id === key) + 1).join(", ")}</p></div>) }
      </fieldset>
      {!history && !activatedVersion ? <button className="button button--primary" type="submit" disabled={busy || blocked || activationUncertain || conflict && !uncertain || !dirty && !uncertain}>{busy ? "Checking save…" : uncertain ? "Check save delivery" : "Save new revision"}</button> : null}
    </form>
    <section className="panel stack" aria-label="Progressive draft hints"><h2>Progressive hints</h2><p>Reveal the next hint when you need help.</p>{shown.hints.slice(0, shownHints).map((item, i) => <div key={item.id}><fieldset disabled={disabled}>{field(`Hint ${i + 1}`, item.text, (text) => change({ ...edit, hints: edit.hints.map((row, at) => at === i ? { ...row, text } : row) }))}</fieldset></div>)}{shownHints < shown.hints.length ? <button className="button button--secondary" onClick={() => setShownHints((value) => value + 1)}>Reveal next hint</button> : <p>No further hints.</p>}</section>
    <section className="panel stack" aria-label="Pinned draft evidence"><h2>Pinned evidence</h2><p>Evidence is retained source material. Wording edits do not establish that a claim is supported.</p>
      {view.assignment.tutorial_evidence.map((item, i) => <article id={`tutorial-${item.segment_id}`} key={item.segment_id} className="stack"><h3>Tutorial evidence {i + 1}: {item.source_filename}</h3><p>{timestamp(item.start_ms)}–{timestamp(item.end_ms)} · generation {item.generation} · {item.processing_version}</p><p>{item.modality === "frame" ? "Retained frame text; machine interpretation may be inaccurate." : item.asr_origin ? "Machine transcription; review for transcription errors." : "Transcript text"}</p><pre className="documentation-text">{item.text}</pre><details><summary>Stable evidence identity</summary><p>{item.segment_id}</p><p>Source: {item.source_id}</p></details></article>)}
      {view.assignment.documentation_snapshots.map((document) => <article key={document.id} className="stack"><h3>External documentation</h3><p><a href={document.url} target="_blank" rel="noreferrer">Official source page</a> · retrieved {new Date(document.retrieved_at).toLocaleString()} · version unknown</p>{document.excerpts.map((excerpt) => <section key={excerpt.id} id={`draft-excerpt-${excerpt.id}`}><pre className="documentation-text">{excerpt.text}</pre><details><summary>Excerpt identity and hash</summary><p>{excerpt.id}</p><p className="documentation-hash">{excerpt.content_sha256}</p></details></section>)}</article>)}
      <p>{saved.documentation_ids.length} selected document(s) retained by this revision, including any uncited selections. Historical selections remain dependencies.</p>
      <Link href={`/projects/${initial.project_id}/learning/contexts/${context.id}`}>Inspect saved selection, document approvals and licenses</Link>
    </section>
    {busy ? <p role="status">Checking saved draft…</p> : null}{status ? <p role="status" aria-live="polite">{status}</p> : null}{error ? <p role="alert">{error}</p> : null}
  </div>;
}
export function DraftEditor(props: Props) { return <Editor key={`${props.initial.tenant_id}:${props.initial.project_id}:${props.initial.id}:${props.activatedVersion?.id ?? "draft"}`} {...props} />; }
