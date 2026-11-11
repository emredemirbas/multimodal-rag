import { StrictMode } from "react";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { DraftEditor } from "./draft-editor";
import { DraftListWorkspace } from "./draft-list";
import { draftFixture, draftId } from "./draft-fixtures";
import { context, documentId, projectId, json, deferred } from "./test-fixtures";
import { draftContent } from "@/lib/api/draft-contracts";
const path = `/api/projects/${projectId}/curriculum/drafts/${draftId}`;
const fetchMock = vi.fn();
beforeEach(() => { vi.stubGlobal("fetch", fetchMock); fetchMock.mockReset(); });
afterEach(() => { vi.unstubAllGlobals(); });
const open = (archived = false) => render(<DraftEditor initial={draftFixture()} context={context} archived={archived} />);
const changeTitle = (title = "Edited route exercise") => fireEvent.change(screen.getByLabelText("Title"), { target: { value: title } });
function savedRevision(title = "Edited route exercise", revision = 2) { const value = draftFixture(revision); value.assignment.draft.title = title; return value; }
const save = () => fireEvent.click(screen.getByRole("button", { name: "Save new revision" }));
function beginDelete() { fireEvent.click(screen.getByRole("button", { name: "Delete draft" })); fireEvent.click(screen.getByRole("button", { name: "Confirm draft deletion" })); }
describe("draft review and conflict-safe editing", () => {
  it("shows literal pinned evidence, separate labels and progressively disclosed hints", () => {
    open(); expect(fetchMock).not.toHaveBeenCalled();
    expect(screen.getByText("Tutorial covered")).toBeVisible();
    expect(screen.getByText(/create_app exposes GET/)).toHaveTextContent('<script>unsafe()</script>');
    expect(document.querySelector('script')).toBeNull();
    expect(screen.getByText(/00:01–00:04/)).toHaveTextContent('generation 1');
    expect(screen.queryByText('Find the route registration.')).toBeNull();
    fireEvent.click(screen.getByRole('button', {name:'Reveal next hint'}));
    expect(screen.getByLabelText('Hint 1')).toHaveValue('Find the route registration.');
  });
  it("saves a new revision with unchanged structural IDs and selected documents", async () => {
    fetchMock.mockImplementation(async () => json(savedRevision()));
    open(); changeTitle(); save();
    await screen.findByText('Revision 2 saved. This is still an assignment draft.');
    const [target, init] = fetchMock.mock.calls[0]; const body = JSON.parse(init.body);
    expect(target).toBe(path); expect(body.expected_revision).toBe(1); expect(body.documentation_ids).toEqual([]);
    expect(body.content).toEqual({ ...draftContent(draftFixture()), title: 'Edited route exercise' });
    expect(body.content).not.toHaveProperty('tenant_id'); expect(fetchMock.mock.calls[1][1].method).toBe('GET');
    expect(screen.getByRole('button', {name:'Save new revision'})).toBeDisabled();
  });
  it("replays uncertain delivery with the exact frozen body/key", async () => {
    fetchMock.mockRejectedValueOnce(new Error('Disconnect')).mockResolvedValueOnce(json(savedRevision())).mockResolvedValueOnce(json(savedRevision()));
    open(); changeTitle(); save();
    const retry = await screen.findByRole('button', {name:'Check save delivery'});
    expect(screen.getByLabelText('Title')).toBeDisabled();
    const originalBody = fetchMock.mock.calls[0][1].body; fireEvent.click(retry);
    await screen.findByText('Revision 2 saved. This is still an assignment draft.');
    expect(fetchMock.mock.calls[1][1].body).toBe(originalBody); expect(screen.getByLabelText('Title')).toBeEnabled();
  });
  it("preserves conflicting edits until explicit discard/reload", async () => {
    fetchMock.mockResolvedValueOnce(json({code:'draft_revision_conflict'},409)).mockResolvedValueOnce(json(savedRevision('Remote revision')));
    open(); changeTitle('Unsaved local change'); save();
    await screen.findByText('A newer revision exists. Your edits have not overwritten it.');
    expect(screen.getByLabelText('Title')).toHaveValue('Unsaved local change'); expect(screen.getByRole('button', {name:'Save new revision'})).toBeDisabled();
    fireEvent.click(screen.getByRole('button', {name:'Discard edits and load latest'}));
    await waitFor(() => expect(screen.getByLabelText('Title')).toHaveValue('Remote revision'));
  });
  it("checks focus without replacing dirty text and clears content after dependency loss", async () => {
    fetchMock.mockResolvedValueOnce(json(savedRevision('Remote revision'))).mockResolvedValueOnce(json({code:'curriculum_draft_not_found'},404));
    open(); changeTitle('Local edit'); act(() => window.dispatchEvent(new Event('focus')));
    await screen.findByText('A newer revision exists. Your edits have not overwritten it.'); expect(screen.getByLabelText('Title')).toHaveValue('Local edit');
    act(() => window.dispatchEvent(new Event('focus')));
    await screen.findByText(/retained text has been cleared/); expect(screen.queryByLabelText('Title')).toBeNull(); expect(screen.queryByText(/create_app exposes/)).toBeNull();
  });
  it("does not restore a deleted draft from a late successful save", async () => {
    const pending = deferred<Response>();
    fetchMock.mockImplementation((_path, init) => init.method === 'PUT' ? pending.promise : Promise.resolve(new Response(null,{status:204})));
    open(); changeTitle(); save(); beginDelete(); await screen.findByText(/This draft is no longer available/);
    await act(async () => pending.resolve(json(savedRevision())));
    expect(screen.queryByLabelText('Title')).toBeNull(); expect(fetchMock).toHaveBeenCalledTimes(2);
  });
  it("clears text when a saved receipt's live draft has disappeared", async () => {
    fetchMock.mockResolvedValueOnce(json(savedRevision())).mockResolvedValueOnce(json({code:'curriculum_draft_not_found'},404));
    open(); changeTitle(); save(); await screen.findByText(/This draft is no longer available/); expect(screen.queryByLabelText('Title')).toBeNull();
  });
  it("hides uncertain deletion, then reconciles with an authoritative read", async () => {
    fetchMock.mockRejectedValueOnce(new Error('Disconnect')).mockResolvedValueOnce(json(draftFixture()));
    open(); changeTitle('Discarded on deletion'); beginDelete(); await screen.findByText(/Draft deletion could not be confirmed/); expect(screen.queryByText(/create_app exposes/)).toBeNull();
    fireEvent.click(screen.getByRole('button', {name:'Check draft deletion'})); await screen.findByText('The draft still exists. Review it or request deletion again.'); expect(screen.getByLabelText('Title')).toHaveValue('Synthetic route exercise');
  });
  it("reads immutable history without losing unsaved current edits", async () => {
    const current = savedRevision('Current revision'); fetchMock.mockResolvedValueOnce(json(current)).mockResolvedValueOnce(json(draftFixture()));
    render(<DraftEditor initial={current} context={context} archived={false} />); changeTitle('Unsaved current text');
    fireEvent.click(screen.getByText('Revision history')); fireEvent.click(screen.getByRole('button',{name:'View saved revision'}));
    await screen.findByText(/Viewing revision 1, read only/); expect(screen.getByLabelText('Title')).toBeDisabled(); expect(screen.getByLabelText('Title')).toHaveValue('Synthetic route exercise');
    fireEvent.click(screen.getByRole('button',{name:'Return to current draft'})); expect(screen.getByLabelText('Title')).toHaveValue('Unsaved current text'); expect(screen.getByText('Returned to current draft revision 2.')).toBeVisible();
  });
  it("allows archived reading and deletion while editing stays disabled", () => {
    open(true); expect(screen.getByLabelText('Title')).toBeDisabled(); expect(screen.getByRole('button',{name:'Delete draft'})).toBeEnabled();
  });
  it("keeps editable content after a definite validation error", async () => {
    fetchMock.mockResolvedValueOnce(json({code:'invalid_curriculum_draft'},422)); open(); changeTitle(); save(); await screen.findByRole('alert'); expect(screen.getByLabelText('Title')).toHaveValue('Edited route exercise'); expect(screen.getByLabelText('Title')).toBeEnabled();
  });
  it("fences late responses across scope changes under StrictMode", async () => {
    const pending = deferred<Response>(); fetchMock.mockReturnValue(pending.promise);
    const {rerender} = render(<StrictMode><DraftEditor initial={draftFixture()} context={context} archived={false} /></StrictMode>); act(() => window.dispatchEvent(new Event('focus')));
    const other = draftFixture(); other.id = documentId; other.assignment.draft.title = 'Other scoped draft'; rerender(<StrictMode><DraftEditor initial={other} context={context} archived={false} /></StrictMode>);
    await act(async () => pending.resolve(json(savedRevision('Late old draft')))); expect(screen.getByLabelText('Title')).toHaveValue('Other scoped draft'); expect(screen.queryByText(/newer revision exists/)).toBeNull();
  });
});
describe('saved draft discovery', () => {
  it('renders an honest empty state without requesting generation', () => {
    render(<DraftListWorkspace scope={context} contextId={context.id} initial={{items:[],next_after:null}} />); expect(screen.getByText(/No assignment drafts have been saved/)).toBeVisible(); expect(fetchMock).not.toHaveBeenCalled();
  });
  it('pages summaries within fixed scope and clears a deleted context', async () => {
    const {id,tenant_id,project_id,context_id,revision,created_at} = draftFixture(); const item = {id,tenant_id,project_id,context_id,revision,created_at,title:'Stored draft'};
    fetchMock.mockResolvedValueOnce(json({items:[],next_after:null})).mockResolvedValueOnce(json({code:'curriculum_context_not_found'},404));
    render(<DraftListWorkspace scope={context} contextId={context.id} initial={{items:[item],next_after:id}} />); expect(screen.getByRole('link',{name:'Stored draft'})).toHaveAttribute('href',`/projects/${projectId}/learning/drafts/${draftId}`);
    fireEvent.click(screen.getByRole('button',{name:'Next drafts'})); await screen.findByText('No more saved drafts on this page.'); expect(fetchMock.mock.calls[0][0]).toContain(`after=${id}`);
    act(() => window.dispatchEvent(new Event('focus'))); await screen.findByText(/This saved selection is no longer available/); expect(screen.queryByRole('link',{name:'Stored draft'})).toBeNull();
  });
});
