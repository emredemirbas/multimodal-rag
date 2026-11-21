import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { DraftEditor } from "./draft-editor";
import { activationFixture, draftFixture, draftId } from "./draft-fixtures";
import { context, projectId, deferred, json, documentId } from "./test-fixtures";
const fetchMock = vi.fn();
const path = `/api/projects/${projectId}/curriculum/drafts/${draftId}`;
const label = /I have reviewed saved revision/;
const open = () => render(<DraftEditor initial={draftFixture()} context={context} archived={false} />);
const consent = () => fireEvent.click(screen.getByRole('checkbox',{name:label}));
const activate = () => fireEvent.click(screen.getByRole('button',{name:'Activate saved revision 1'}));
beforeEach(() => {vi.stubGlobal('fetch',fetchMock);fetchMock.mockReset();});
afterEach(() => vi.unstubAllGlobals());
describe('explicit reviewed assignment activation', () => {
  it('does not activate on open, requires explicit review and blocks dirty/history/archive states', () => {
    open(); expect(fetchMock).not.toHaveBeenCalled(); expect(screen.getByRole('button',{name:'Activate saved revision 1'})).toBeDisabled();
    consent(); expect(screen.getByRole('button',{name:'Activate saved revision 1'})).toBeEnabled();
    fireEvent.change(screen.getByLabelText('Title'),{target:{value:'Unreviewed edit'}});
    expect(screen.getByRole('checkbox',{name:label})).not.toBeChecked(); expect(screen.getByRole('button',{name:'Activate saved revision 1'})).toBeDisabled();
  });
  it('pins the saved revision, verifies a live head, and returns a stable version link', async () => {
    fetchMock.mockResolvedValueOnce(json(activationFixture(),201)).mockResolvedValueOnce(json(draftFixture()));
    open(); consent(); activate();
    await screen.findByText('Revision 1 activated. Later draft edits will not change this version.');
    expect(fetchMock.mock.calls[0][0]).toBe(path+'/activate'); expect(fetchMock.mock.calls[0][1].method).toBe('POST');
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toMatchObject({expected_revision:1,consent:'activate_reviewed_revision'});
    expect(screen.getByRole('link',{name:'View activated version'})).toHaveAttribute('href',`/projects/${projectId}/learning/assignments/${activationFixture().id}`);
    expect(screen.getByRole('button',{name:'Activate saved revision 1'})).toBeDisabled();
    expect(screen.getByLabelText('Title')).toHaveValue(draftFixture().assignment.draft.title);
  });
  it('replays an uncertain activation with the same exact body/revision and freezes edits', async () => {
    fetchMock.mockRejectedValueOnce(new Error('Disconnect')).mockResolvedValueOnce(json(activationFixture(),201)).mockResolvedValueOnce(json(draftFixture(2)));
    open(); consent(); activate(); const retry=await screen.findByRole('button',{name:'Check activation delivery'});
    expect(screen.getByLabelText('Title')).toBeDisabled(); expect(screen.getByRole('button',{name:'Save new revision'})).toBeDisabled();
    expect(screen.getByRole('button',{name:'Refresh saved draft'})).toBeDisabled();
    const original=fetchMock.mock.calls[0][1].body; fireEvent.click(retry);
    await screen.findByText('Revision 1 activated. Later draft edits will not change this version.');
    expect(fetchMock.mock.calls[1][1].body).toBe(original); expect(screen.getByText('A newer revision exists. Your edits have not overwritten it.')).toBeVisible();
  });
  it('keeps the draft after a stale-head conflict and requires a new review', async () => {
    fetchMock.mockResolvedValueOnce(json({code:'draft_revision_conflict'},409)); open();consent();activate();
    await screen.findByText('A newer revision exists. Your edits have not overwritten it.');
    expect(screen.queryByRole('link',{name:'View activated version'})).toBeNull();expect(screen.getByRole('checkbox',{name:label})).not.toBeChecked();
  });
  it('does not adopt a forged receipt with different reviewed content', async () => {
    const bad=activationFixture();bad.draft.assignment.draft.title='Changed accepted text';fetchMock.mockResolvedValue(json(bad,201));
    open();consent();activate();await screen.findByRole('button',{name:'Check activation delivery'});
    expect(screen.queryByRole('link',{name:'View activated version'})).toBeNull();expect(screen.getByLabelText('Title')).toHaveValue(draftFixture().assignment.draft.title);
  });
  it('fences a late activation after the whole draft was explicitly deleted', async () => {
    const pending=deferred<Response>();fetchMock.mockImplementation((_url,init)=>init.method==='POST'?pending.promise:Promise.resolve(new Response(null,{status:204})));
    open();consent();activate();fireEvent.click(screen.getByRole('button',{name:'Delete draft'}));
    expect(screen.getByRole('group',{name:'Confirm draft deletion'})).toHaveTextContent('every activated assignment version');
    fireEvent.click(screen.getByRole('button',{name:'Confirm draft deletion'})); await screen.findByText(/This draft is no longer available/);
    await act(async()=>pending.resolve(json(activationFixture(),201)));expect(screen.queryByRole('link',{name:'View activated version'})).toBeNull();expect(fetchMock).toHaveBeenCalledTimes(2);
  });
  it('clears a just-accepted receipt if a dependency removed the current draft', async () => {
    fetchMock.mockResolvedValueOnce(json(activationFixture(),201)).mockResolvedValueOnce(json({code:'curriculum_draft_not_found'},404));
    open();consent();activate();await screen.findByText(/This draft is no longer available/);expect(screen.queryByLabelText('Title')).toBeNull();
  });
  it('checks activation status without sending another confirmation', async () => {
    fetchMock.mockResolvedValueOnce(json({activation:activationFixture()})).mockResolvedValueOnce(json(draftFixture()));open();fireEvent.click(screen.getByRole('button',{name:'Check activation status'}));
    await screen.findByRole('link',{name:'View activated version'});expect(fetchMock.mock.calls[0][0]).toBe(path+'/activation');expect(fetchMock.mock.calls.every((call)=>call[1].method==='GET')).toBe(true);
  });
  it('retains editable text and clears review after a definite validation error', async () => {
    fetchMock.mockResolvedValueOnce(json({code:'invalid_assignment_activation'},422));open();consent();activate();await screen.findByRole('alert');expect(screen.getByLabelText('Title')).toBeEnabled();expect(screen.getByRole('checkbox',{name:label})).not.toBeChecked();
  });
  it('does not duplicate an already confirmed current version and permits a new review only after saving', async () => {
    render(<DraftEditor initial={draftFixture()} context={context} archived={false} initialActivation={activationFixture()} />);
    expect(screen.getByRole('checkbox',{name:label})).toBeDisabled();expect(screen.getByRole('link',{name:'View activated version'})).toBeVisible();
    fireEvent.change(screen.getByLabelText('Title'),{target:{value:'Later wording'}});
    const next=draftFixture(2);next.assignment.draft.title='Later wording';fetchMock.mockResolvedValueOnce(json(next)).mockResolvedValueOnce(json(next));fireEvent.click(screen.getByRole('button',{name:'Save new revision'}));
    await screen.findByText('Revision 2 saved. This is still an assignment draft.');expect(screen.getByRole('checkbox',{name:label})).not.toBeChecked();expect(screen.getByRole('checkbox',{name:label})).toBeEnabled();
    expect(screen.getByRole('link',{name:'View activated version'})).toHaveAttribute('href',`/projects/${projectId}/learning/assignments/${activationFixture().id}`);
  });
  it('never activates historical or archived draft review', async () => {
    const current=draftFixture(2);fetchMock.mockResolvedValueOnce(json(current)).mockResolvedValueOnce(json(draftFixture()));
    const {unmount}=render(<DraftEditor initial={current} context={context} archived={false} />);fireEvent.click(screen.getByText('Revision history'));fireEvent.click(screen.getByRole('button',{name:'View saved revision'}));
    await screen.findByText(/Viewing revision 1, read only/);expect(screen.getByRole('checkbox',{name:label})).toBeDisabled();unmount();render(<DraftEditor initial={draftFixture()} context={context} archived />);expect(screen.getByRole('checkbox',{name:label})).toBeDisabled();
  });
});
describe('read-only activated assignment version',()=>{
  it('refreshes the exact version, with no edit/delete/history/activation controls',async()=>{
    const accepted=activationFixture();fetchMock.mockResolvedValue(json(accepted));render(<DraftEditor initial={accepted.draft} context={context} archived={false} activatedVersion={accepted} />);
    expect(screen.getByLabelText('Title')).toBeDisabled();expect(screen.queryByRole('button',{name:'Delete draft'})).toBeNull();expect(screen.queryByRole('button',{name:'Save new revision'})).toBeNull();expect(screen.queryByRole('checkbox',{name:label})).toBeNull();
    fireEvent.click(screen.getByRole('button',{name:'Refresh activated version'}));await screen.findByText('Activated version checked. Its saved revision is unchanged.');
    expect(fetchMock.mock.calls[0][0]).toBe(`/api/projects/${projectId}/curriculum/assignments/${accepted.id}`);expect(screen.getByLabelText('Title')).toHaveValue(accepted.draft.assignment.draft.title);
  });
  it('clears retained text if an activated version or its dependency disappears',async()=>{
    fetchMock.mockResolvedValue(json({code:'assignment_activation_not_found'},404));const accepted=activationFixture();render(<DraftEditor initial={accepted.draft} context={context} archived activatedVersion={accepted} />);
    act(()=>window.dispatchEvent(new Event('focus')));await screen.findByText(/This activated version is no longer available/);expect(screen.queryByLabelText('Title')).toBeNull();expect(screen.queryByText(/create_app exposes/)).toBeNull();
  });
  it('rejects changed metadata/content on an immutable version refresh',async()=>{
    const accepted=activationFixture(),changed=activationFixture();changed.activated_by=documentId;fetchMock.mockResolvedValue(json(changed));render(<DraftEditor initial={accepted.draft} context={context} archived={false} activatedVersion={accepted} />);
    fireEvent.click(screen.getByRole('button',{name:'Refresh activated version'}));await screen.findByRole('alert');expect(screen.getByLabelText('Title')).toHaveValue(accepted.draft.assignment.draft.title);
  });
  it('fences late responses when navigating to another activated version of the same draft',async()=>{
    const pending=deferred<Response>();fetchMock.mockReturnValue(pending.promise);const first=activationFixture();const {rerender}=render(<DraftEditor initial={first.draft} context={context} archived={false} activatedVersion={first} />);
    act(()=>window.dispatchEvent(new Event('focus')));const second=activationFixture(2);second.id=documentId;second.draft.assignment.draft.title='Second accepted version';rerender(<DraftEditor initial={second.draft} context={context} archived={false} activatedVersion={second} />);
    await act(async()=>pending.resolve(json(first)));await waitFor(()=>expect(screen.getByLabelText('Title')).toHaveValue('Second accepted version'));
  });
});
