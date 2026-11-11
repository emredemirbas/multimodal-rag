"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import { parseSavedLearningContext, type BrowserContextCreateBody, type LearnerPreferences } from "@/lib/api/curriculum-contracts";
import type { SourceItem } from "@/lib/api/source-contracts";
import { LearningRequestError, learningError, learningRequest } from "./client-command";

export interface LearningContextFormProps { projectId: string; tenantId: string; sources: SourceItem[]; archived: boolean }

function ContextForm({ projectId, tenantId, sources, archived }: LearningContextFormProps) {
  const id = useId(), router = useRouter();
  const [selected, setSelected] = useState<string[]>([]);
  const [experience, setExperience] = useState("");
  const [difficulty, setDifficulty] = useState("");
  const [language, setLanguage] = useState("");
  const [minutes, setMinutes] = useState("");
  const [prerequisites, setPrerequisites] = useState(false);
  const [extensions, setExtensions] = useState(false);
  const [documentation, setDocumentation] = useState(false);
  const [pending, setPending] = useState(false), [error, setError] = useState("");
  const [blocked, setBlocked] = useState(archived), [uncertain, setUncertain] = useState(false);
  const [savedId, setSavedId] = useState<string | null>(null);
  const active = useRef<AbortController | null>(null), alive = useRef(true), busy = useRef(false);
  const command = useRef<{ body: Omit<BrowserContextCreateBody, "idempotency_key">; key: string } | null>(null);
  useEffect(() => { alive.current = true; return () => { alive.current = false; active.current?.abort(); }; }, []);
  const eligible = sources.filter((source) => source.active_generation !== null && source.active_generation > 0 && source.segment_count > 0 && Boolean(source.processing_version?.trim()));
  const eligibleIds = new Set(eligible.map((source) => source.id));
  const missing = selected.some((sourceId) => !eligibleIds.has(sourceId));
  const valid = selected.length > 0 && selected.length <= 20 && !missing && Boolean(experience && difficulty && language) && /^\d+$/.test(minutes) && Number(minutes) >= 1 && Number(minutes) <= 10080;
  function edit() { command.current = null; setUncertain(false); setError(""); setSavedId(null); }
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy.current || (!valid && !(uncertain && command.current)) || blocked || archived) return;
    const body: Omit<BrowserContextCreateBody, "idempotency_key"> = uncertain && command.current ? command.current.body : {
      selected_sources: selected.slice().sort().map((sourceId) => { const source = eligible.find((item) => item.id === sourceId)!; return { source_id: source.id, generation: source.active_generation!, processing_version: source.processing_version! }; }),
      learner: { experience: experience as LearnerPreferences["experience"], difficulty: difficulty as LearnerPreferences["difficulty"], language: language as LearnerPreferences["language"], available_minutes: Number(minutes), allow_prerequisites: prerequisites, allow_extensions: extensions, allow_external_documentation: documentation },
    };
    if (!command.current) command.current = { body, key: crypto.randomUUID() };
    const controller = new AbortController(); active.current = controller; busy.current = true; setPending(true); setError("");
    try {
      const receipt = parseSavedLearningContext(await learningRequest(`/api/projects/${projectId}/curriculum/contexts`, "POST", { ...body, idempotency_key: command.current.key }, controller.signal), { tenant_id: tenantId, project_id: projectId });
      const returnedPins = receipt.selected_sources.map(({ source_id, generation, processing_version }) => ({ source_id, generation, processing_version })).sort((a, b) => a.source_id.localeCompare(b.source_id));
      if (JSON.stringify(returnedPins) !== JSON.stringify(body.selected_sources) || JSON.stringify(receipt.learner) !== JSON.stringify(body.learner)) throw new Error("Unmatched context receipt");
      if (!alive.current) return;
      setUncertain(false); setSavedId(receipt.id);
      router.push(`/projects/${projectId}/learning/contexts/${receipt.id}`);
    } catch (failure) {
      if (!alive.current) return;
      if (failure instanceof LearningRequestError && failure.code === "project_archived") setBlocked(true);
      setError(learningError(failure)); setUncertain(!(failure instanceof LearningRequestError) || failure.status >= 500);
    } finally { if (alive.current) { setPending(false); busy.current = false; } }
  }
  return <section className="stack" aria-labelledby={`${id}-heading`}>
    <h2 id={`${id}-heading`}>Save a learning context</h2>
    <p>Choose published tutorial text and your preferences. Saving keeps those source versions together for review. Assignment generation is not available yet.</p>
    {(archived || blocked) ? <p role="status">This project is archived. Saved material can still be read or deleted; restore the project to create a context.</p> : null}
    <form aria-label="Save learning context" className="stack" onSubmit={(event) => void save(event)} aria-busy={pending}>
      <fieldset disabled={pending || blocked || archived} className="stack">
        <legend>Tutorial sources (choose 1–20)</legend>
        {eligible.length ? eligible.map((source) => <label key={source.id} htmlFor={`${id}-${source.id}`}><input id={`${id}-${source.id}`} type="checkbox" checked={selected.includes(source.id)} disabled={selected.length >= 20 && !selected.includes(source.id)} onChange={(event) => { edit(); setSelected((current) => event.target.checked ? [...current, source.id] : current.filter((item) => item !== source.id)); }} /> {source.filename} · published generation {source.active_generation}<span className="field-hint"> · {source.processing_version}</span></label>) : <p>No published text is available. Upload and process an authorized transcript in the project first.</p>}
        {selected.length >= 20 ? <p role="status">The maximum of 20 sources is selected. Deselect one to choose another.</p> : null}
        {missing ? <p role="alert">A selected source is no longer available. Refresh the page and choose its current version.</p> : null}
        <div className="field"><label htmlFor={`${id}-experience`}>Programming experience</label><select id={`${id}-experience`} required value={experience} onChange={(event) => { edit(); setExperience(event.target.value); }}><option value="" disabled>Choose experience</option><option value="beginner">Beginner</option><option value="intermediate">Intermediate</option><option value="advanced">Advanced</option></select></div>
        <div className="field"><label htmlFor={`${id}-difficulty`}>Desired difficulty</label><select id={`${id}-difficulty`} required value={difficulty} onChange={(event) => { edit(); setDifficulty(event.target.value); }}><option value="" disabled>Choose difficulty</option><option value="beginner">Beginner</option><option value="intermediate">Intermediate</option><option value="advanced">Advanced</option></select></div>
        <div className="field"><label htmlFor={`${id}-language`}>Output language</label><select id={`${id}-language`} required value={language} onChange={(event) => { edit(); setLanguage(event.target.value); }}><option value="" disabled>Choose language</option><option value="en">English</option><option value="tr">Turkish</option></select></div>
        <div className="field"><label htmlFor={`${id}-minutes`}>Available effort in minutes</label><input id={`${id}-minutes`} type="number" inputMode="numeric" min={1} max={10080} required value={minutes} onChange={(event) => { edit(); setMinutes(event.target.value); }} /><p className="field-hint">Choose 1–10,080 minutes of effort. This does not set a deadline.</p></div>
        <fieldset className="stack"><legend>Optional material</legend><p>Tutorial-only is the default. These choices record permission for a future assignment; external documentation still needs separate approval for each page.</p>
          <label><input type="checkbox" checked={prerequisites} onChange={(event) => { edit(); setPrerequisites(event.target.checked); }} /> Allow prerequisite topics</label>
          <label><input type="checkbox" checked={extensions} onChange={(event) => { edit(); setExtensions(event.target.checked); }} /> Allow extension topics</label>
          <label><input type="checkbox" checked={documentation} onChange={(event) => { edit(); setDocumentation(event.target.checked); }} /> Allow separately approved official documentation</label>
        </fieldset>
        <button type="submit" className="button button--primary" disabled={!valid && !uncertain}>{pending ? "Saving context…" : uncertain ? "Check context delivery" : "Save context"}</button>
      </fieldset>
    </form>
    {pending ? <p role="status">Saving the selected sources and preferences…</p> : null}
    {error ? <p role="alert">{error}{uncertain ? " Checking delivery repeats your unchanged request." : ""}</p> : null}
    {savedId ? <p role="status">Context saved. <Link href={`/projects/${projectId}/learning/contexts/${savedId}`}>Open saved context</Link>. Bookmark that page to return to it.</p> : null}
  </section>;
}

export function LearningContextForm(props: LearningContextFormProps) { return <ContextForm key={`${props.tenantId}:${props.projectId}`} {...props} />; }
