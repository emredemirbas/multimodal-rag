import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { VideoUpload } from './video-upload';
import { projectId, sourceId } from '../../../test-support/transcript-fixture';
afterEach(()=>vi.unstubAllGlobals());
function fill() {
  fireEvent.change(screen.getByLabelText('MP4 video'),{target:{files:[new File(['fixture'],'owned.mp4',{type:'video/mp4'})]}});
  fireEvent.change(screen.getByLabelText('Video ownership / permission'),{target:{value:'owner_upload'}});
  fireEvent.change(screen.getByLabelText('Frame text language'),{target:{value:'en'}});
  fireEvent.click(screen.getByRole('checkbox'));
}
it('explains exact local scope/retention and renders accessible consent controls',()=>{
  render(<VideoUpload projectId={projectId} onCompleted={vi.fn()}/>);
  expect(screen.getByRole('form',{name:'Upload authorized MP4'})).toHaveAttribute('aria-busy','false');
  expect(screen.getByRole('button',{name:'Process authorized MP4'})).toBeDisabled();
  expect(screen.getByText(/Audio is ignored, not transcribed/)).toBeInTheDocument();
  expect(screen.getByText(/Expiry is not proof of physical deletion/)).toBeInTheDocument();
  expect(screen.getByRole('checkbox')).toBeRequired();
  expect(screen.getByLabelText('Frame text language')).toHaveValue('');
});
it('rejects unsupported/empty files without a network request',()=>{
  const fetch=vi.fn();vi.stubGlobal('fetch',fetch);render(<VideoUpload projectId={projectId} onCompleted={vi.fn()}/>);
  fireEvent.change(screen.getByLabelText('MP4 video'),{target:{files:[new File([],'empty.mp4')]}});
  expect(screen.getByRole('alert')).toHaveTextContent('non-empty MP4');expect(fetch).not.toHaveBeenCalled();
});
it('preserves file and key on uncertain delivery, then resets only on a scoped receipt',async()=>{
  const keys:string[]=[];const refresh=vi.fn().mockResolvedValue(undefined);
  const fetch=vi.fn().mockImplementation(async(_url,options)=>{keys.push((options.body as FormData).get('idempotency_key') as string);if(keys.length===1)throw new Error('network');return new Response(JSON.stringify({project_id:projectId,source_id:sourceId,job_id:sourceId,deduplicated:true}));});
  vi.stubGlobal('fetch',fetch);render(<VideoUpload projectId={projectId} onCompleted={refresh}/>);fill();
  fireEvent.submit(screen.getByRole('form'));await screen.findByRole('alert');expect(screen.getByRole('alert')).toHaveTextContent('same request key');
  fireEvent.submit(screen.getByRole('form'));await waitFor(()=>expect(refresh).toHaveBeenCalledOnce());
  expect(keys[1]).toBe(keys[0]);expect(screen.getByRole('button',{name:'Process authorized MP4'})).toBeDisabled();
  expect(screen.getByText(/This video was already accepted/)).toBeInTheDocument();
});
it('stops delivery without claiming the job was cancelled and prevents double submit',async()=>{
  const fetch=vi.fn().mockImplementation((_url,options)=>new Promise((_resolve,reject)=>options.signal.addEventListener('abort',()=>reject(new Error('abort')))));
  vi.stubGlobal('fetch',fetch);render(<VideoUpload projectId={projectId} onCompleted={vi.fn()}/>);fill();
  const form=screen.getByRole('form');fireEvent.submit(form);fireEvent.submit(form);expect(fetch).toHaveBeenCalledOnce();
  expect(form).toHaveAttribute('aria-busy','true');fireEvent.click(screen.getByRole('button',{name:'Stop video upload delivery'}));
  expect(await screen.findByRole('alert')).toHaveTextContent('It may already be queued');
  expect(form).toHaveAttribute('aria-busy','false');
});
it('keeps the draft on a foreign receipt and reports accepted-but-refresh-failed separately',async()=>{
  const fetch=vi.fn().mockResolvedValueOnce(new Response(JSON.stringify({project_id:sourceId,source_id:sourceId,job_id:sourceId,deduplicated:false})))
    .mockResolvedValueOnce(new Response(JSON.stringify({project_id:projectId,source_id:sourceId,job_id:sourceId,deduplicated:false})));
  vi.stubGlobal('fetch',fetch);render(<VideoUpload projectId={projectId} onCompleted={vi.fn().mockRejectedValue(new Error('refresh'))}/>);fill();
  fireEvent.submit(screen.getByRole('form'));expect(await screen.findByRole('alert')).toHaveTextContent('could not be confirmed');
  fireEvent.submit(screen.getByRole('form'));await waitFor(()=>expect(screen.getByRole('alert')).toHaveTextContent('Video accepted, but'));
});
