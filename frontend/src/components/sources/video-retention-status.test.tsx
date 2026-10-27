import { act, fireEvent, render, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { VideoRetentionStatus } from './video-retention-status';
import { parseSourceList } from '@/lib/api/source-contracts';
import { projectId } from '../../../test-support/transcript-fixture';
import { audioRetention } from '../../../test-support/media-fixture';
import { retryCleanupAction } from '@/app/actions/sources';
vi.mock('@/app/actions/sources',()=>({retryCleanupAction:vi.fn()}));
it.each(['temporary','expired','cleanup_pending','cleanup_failed','deleted'] as const)('shows honest %s state and only offers failed cleanup retry',status=>{
  const retired=['cleanup_pending','cleanup_failed','deleted'].includes(status);
  const retention={...audioRetention(),status,cleanup_id:retired?projectId:null,deleted_at:status==='deleted'?'2026-10-27T12:00:00Z':null};
  render(<VideoRetentionStatus projectId={projectId} retention={retention} onRefresh={vi.fn()}/>);
  expect(screen.getByRole('region',{name:'Original video retention'})).toBeInTheDocument();
  if(status==='cleanup_failed')expect(screen.getByRole('button',{name:'Retry original video cleanup'})).toBeInTheDocument();
  else expect(screen.queryByRole('button')).not.toBeInTheDocument();
  if(status==='deleted')expect(screen.getByText('Original video deletion confirmed.')).toBeInTheDocument();
  else expect(screen.queryByText('Original video deletion confirmed.')).not.toBeInTheDocument();
});
it('rejects inconsistent or mixed video retention instead of guessing deletion',()=>{
  for(const video_retention of [{...audioRetention(),status:'deleted'}, {...audioRetention(),status:'cleanup_failed'}, {...audioRetention(),processing_expires_at:'invalid'}]) expect(()=>parseSourceList({items:[{video_retention}]})).toThrow();
  expect(()=>parseSourceList({items:[{kind:'audio',video_retention:audioRetention()}]})).toThrow();
});
it('submits the scoped cleanup receipt and refreshes without claiming deletion',async()=>{
  const refresh=vi.fn().mockResolvedValue(undefined);
  vi.mocked(retryCleanupAction).mockResolvedValue({status:'success',version:1,message:'Cleanup retry accepted.'});
  const retention=audioRetention('cleanup_failed');
  render(<VideoRetentionStatus projectId={projectId} retention={retention} onRefresh={refresh}/>);
  await act(async()=>{fireEvent.click(screen.getByRole('button',{name:'Retry original video cleanup'}));});
  const body=vi.mocked(retryCleanupAction).mock.calls[0][1];
  expect(body.get('projectId')).toBe(projectId);expect(body.get('cleanupId')).toBe(retention.cleanup_id);
  expect(refresh).toHaveBeenCalledOnce();expect(screen.getByRole('status')).toHaveTextContent('Physical deletion is not confirmed');
});
