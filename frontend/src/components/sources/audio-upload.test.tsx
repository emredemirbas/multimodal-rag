import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { AudioUpload } from './audio-upload';
import { AUDIO_MAX_BYTES } from '@/lib/api/audio-contracts';

const project = '12345678-1234-1234-1234-123456789abc';
const receipt = { project_id: project, source_id: '12345678-1234-1234-1234-123456789abd',
  job_id: '12345678-1234-1234-1234-123456789abe', deduplicated: false };
const file = new File(['RIFF-test'], 'owned.wav', { type: 'audio/wav' });

function completeForm() {
  fireEvent.change(screen.getByLabelText('WAV recording'), { target: { files: [file] } });
  fireEvent.change(screen.getByLabelText('Audio ownership / permission'), { target: { value: 'owner_upload' } });
  fireEvent.change(screen.getByLabelText('Speech language'), { target: { value: 'en' } });
  fireEvent.click(screen.getByRole('checkbox'));
}
const submit = () => fireEvent.submit(screen.getByRole('form', { name: 'Upload authorized WAV' }));
const key = () => (document.querySelector('input[name="idempotency_key"]') as HTMLInputElement).value;

describe('experimental authorized WAV form', () => {
  beforeEach(() => vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => receipt })));
  afterEach(() => vi.unstubAllGlobals());

  it('requires explicit rights and retention consent, describes limits and never promises accuracy', () => {
    render(<AudioUpload projectId={project} onCompleted={vi.fn()} />);
    expect(screen.getByLabelText('Audio ownership / permission')).toBeRequired();
    expect(screen.getByRole('checkbox')).not.toBeChecked();
    expect(screen.getByRole('checkbox')).toBeRequired();
    expect(screen.getByText(/20 MB \/ 10 minutes/)).toBeVisible();
    expect(screen.getByText(/including queue waiting/)).toHaveTextContent('outages can delay physical deletion');
    expect(screen.getByText(/not human-reviewed/)).toBeVisible();
    expect(screen.getByRole('button', { name: 'Transcribe authorized WAV' })).toBeDisabled();
    const oversized = new File(['x'], 'large.wav', { type: 'audio/wav' });
    Object.defineProperty(oversized, 'size', { value: AUDIO_MAX_BYTES + 1 });
    fireEvent.change(screen.getByLabelText('WAV recording'), { target: { files: [oversized] } });
    expect(screen.getByRole('alert')).toHaveTextContent('at most 20 MB');
    submit();
    expect(fetch).not.toHaveBeenCalled();
  });

  it('accepts only a verified scoped receipt, refreshes and resets the accepted draft', async () => {
    const refresh = vi.fn().mockResolvedValue(undefined);
    render(<AudioUpload projectId={project} onCompleted={refresh} />);
    completeForm(); const acceptedKey = key();
    submit();
    await waitFor(() => expect(refresh).toHaveBeenCalledTimes(1));
    const [url, options] = vi.mocked(fetch).mock.calls[0];
    expect(url).toBe(`/api/projects/${project}/sources/audio`);
    const body = options!.body as FormData;
    expect(body.get('idempotency_key')).toBe(acceptedKey);
    expect(body.get('authorization_mode')).toBe('owner_upload');
    expect(body.get('language')).toBe('en');
    expect(body.get('retention_acknowledged')).toBe('accepted');
    expect(screen.getByRole('status')).toHaveTextContent('Audio accepted');
    expect(key()).toBe('');
    expect(screen.getByRole('checkbox')).not.toBeChecked();
    expect(screen.getByRole('button', { name: 'Transcribe authorized WAV' })).toBeDisabled();
  });

  it('retains the same key and draft after uncertain transport failure, then reconciles a duplicate', async () => {
    vi.mocked(fetch).mockRejectedValueOnce(new Error('private internal upstream secret'));
    const refresh = vi.fn().mockResolvedValue(undefined);
    render(<AudioUpload projectId={project} onCompleted={refresh} />);
    completeForm(); const original = key(); submit();
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('may already be queued'));
    expect(screen.queryByText(/private internal/)).not.toBeInTheDocument();
    expect(key()).toBe(original);
    expect(screen.getByRole('checkbox')).toBeChecked();
    vi.mocked(fetch).mockResolvedValueOnce({ ok: true, json: async () => ({ ...receipt, deduplicated: true }) } as Response);
    submit();
    await waitFor(() => expect(refresh).toHaveBeenCalledTimes(1));
    expect((vi.mocked(fetch).mock.calls[1][1]!.body as FormData).get('idempotency_key')).toBe(original);
    expect(screen.getByRole('status')).toHaveTextContent('already accepted');
  });

  it('stops delivery without claiming job cancellation or changing the recovery key', async () => {
    vi.mocked(fetch).mockImplementation((_url, options) => new Promise((_resolve, reject) => {
      options!.signal!.addEventListener('abort', () => reject(new Error('aborted')), { once: true });
    }));
    render(<AudioUpload projectId={project} onCompleted={vi.fn()} />);
    completeForm(); const original = key(); submit();
    expect(screen.getByRole('form')).toHaveAttribute('aria-busy', 'true');
    expect(screen.getByRole('button', { name: 'Uploading WAV…' })).toBeDisabled();
    await act(async () => fireEvent.click(screen.getByRole('button', { name: 'Stop upload delivery' })));
    expect(screen.getByRole('alert')).toHaveTextContent('may already be queued');
    expect(key()).toBe(original);
    expect(screen.getByRole('form')).toHaveAttribute('aria-busy', 'false');
  });

  it.each([{}, { ...receipt, project_id: receipt.source_id }])('never treats an invalid or foreign receipt as accepted', async (value) => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: true, json: async () => value } as Response);
    const refresh = vi.fn();
    render(<AudioUpload projectId={project} onCompleted={refresh} />);
    completeForm(); const original = key(); submit();
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('could not be confirmed'));
    expect(refresh).not.toHaveBeenCalled();
    expect(key()).toBe(original);
    expect(screen.getByRole('status')).toBeEmptyDOMElement();
  });

  it('keeps acceptance distinct from a failed source refresh', async () => {
    render(<AudioUpload projectId={project} onCompleted={vi.fn().mockRejectedValue(new Error('private'))} />);
    completeForm(); submit();
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Audio accepted, but'));
    expect(screen.getByRole('status')).toHaveTextContent('Audio accepted');
    expect(key()).toBe('');
  });
});
