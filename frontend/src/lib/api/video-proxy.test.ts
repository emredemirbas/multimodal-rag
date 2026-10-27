// @vitest-environment node
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { POST } from '@/app/api/projects/[projectId]/sources/video/route';
import { videoRegistrationReceipt, videoRequestBody } from '@/lib/api/video-proxy';
import { parseVideoCapability, VIDEO_WIRE_LIMIT } from '@/lib/api/video-contracts';
import { getVideoCapability } from '@/lib/api/video';
import { requestJson } from '@/lib/api/client';
import { ApiError } from '@/lib/api/errors';
import { projectId, sourceId } from '../../../test-support/transcript-fixture';
import { audioRetention } from '../../../test-support/media-fixture';
vi.mock('server-only', () => ({}));
vi.mock('@/lib/api/video', () => ({ getVideoCapability: vi.fn() }));
vi.mock('@/lib/api/client', () => ({ requestJson: vi.fn() }));
const jobId = '62345678-1234-1234-1234-123456789abc';
const source = { id: sourceId, project_id: projectId, filename: 'owned.mp4', provider: 'upload', kind: 'video', authorization_mode:'owner_upload',
  status: 'created', generation: 1, active_generation: null, segment_count: 0, failure_code: null, video_retention:audioRetention(),
  metadata:{input_kind:'video',requested_language:'en',visual_quality_approval:'not_established'},
  job:{id:jobId,status:'pending',stage:'queued',progress_percent:0,attempt_count:0,max_attempts:3,failure_code:null} };
const registered = { source, job:{id:jobId,source_id:sourceId,job_type:'visual',generation:1},deduplicated:false };
function form() {
  const data=new FormData(); data.set('file',new File(['explicit fixture, API validates MP4'], 'owned.mp4',{type:'video/mp4'}));
  data.set('authorization_mode','owner_upload');data.set('language','en');data.set('idempotency_key','stable-video-key');data.set('retention_acknowledged','accepted');
  return data;
}
function request(body:BodyInit=form(),origin='http://localhost:3000') {
  return new Request(`http://0.0.0.0:3000/api/projects/${projectId}/sources/video`,{method:'POST',body,headers:{Host:'localhost:3000',Origin:origin}});
}
function post(req:Request,project=projectId) {return POST(req,{params:Promise.resolve({projectId:project})});}
describe('bounded standalone video BFF',()=>{
  beforeEach(()=>{vi.mocked(getVideoCapability).mockReset().mockResolvedValue({enabled:true});vi.mocked(requestJson).mockReset().mockResolvedValue(registered);});
  it('verifies every fixed media/retention/language limit',()=>{
    const capability={enabled:true,max_bytes:100_000_000,max_duration_seconds:600,encoding:'h264-avc1-yuv420p',max_width:1920,max_height:1080,max_fps:60,max_selected_frames:20,languages:['en','tr','en+tr'],processing_ttl_seconds:3600};
    expect(parseVideoCapability(capability)).toEqual({enabled:true});
    for(const patch of [{enabled:'true'},{max_bytes:200_000_000},{encoding:'hevc'},{max_duration_seconds:601},{max_width:3840},{max_height:2160},{max_fps:120},{max_selected_frames:21},{languages:['auto']},{languages:['en,tr,en+tr']},{processing_ttl_seconds:0}]) expect(()=>parseVideoCapability({...capability,...patch})).toThrow();
  });
  it('rejects origin/ID/disabled capability before reading the body',async()=>{
    expect((await post(request(),'../bad')).status).toBe(404);
    expect((await post(request(form(),'http://attacker.example'))).status).toBe(403);
    const missing=request();missing.headers.delete('origin');expect((await post(missing)).status).toBe(403);
    expect(getVideoCapability).not.toHaveBeenCalled();
    vi.mocked(getVideoCapability).mockResolvedValueOnce({enabled:false});const req=request();expect((await post(req)).status).toBe(503);expect(req.bodyUsed).toBe(false);
    vi.mocked(getVideoCapability).mockRejectedValueOnce(new Error('PRIVATE_HOST'));const unavailable=await post(request());expect(unavailable.status).toBe(502);expect(await unavailable.text()).not.toContain('PRIVATE_HOST');
    expect(requestJson).not.toHaveBeenCalled();
  });
  it('forwards only explicit fields/key and returns only safe scoped receipt IDs',async()=>{
    const response=await post(request(),projectId.toUpperCase());expect(response.status).toBe(202);expect(response.headers.get('cache-control')).toBe('no-store');
    expect(await response.json()).toEqual({project_id:projectId,source_id:sourceId,job_id:jobId,deduplicated:false});
    const [path,options]=vi.mocked(requestJson).mock.calls[0];expect(path).toBe(`/api/v1/projects/${projectId}/sources/video`);
    expect((options?.body as FormData).get('idempotency_key')).toBe('stable-video-key');
  });
  it('rejects malformed type/parts/rights/language/ack/playlist before forwarding',async()=>{
    for(const [key,value] of [['authorization_mode',''],['language','auto'],['retention_acknowledged','no'],['idempotency_key','x'],['playlist_item_id',sourceId],['url','https://evil.example']]) {const data=form();data.set(key,value);expect((await post(request(data))).status).toBe(422);}
    const duplicate=form();duplicate.append('language','tr');expect((await post(request(duplicate))).status).toBe(422);
    const wrong=form();wrong.set('file',new File(['x'],'owned.wav',{type:'audio/wav'}));expect((await post(request(wrong))).status).toBe(422);
    const empty=form();empty.set('file',new File([],'empty.mp4',{type:'video/mp4'}));expect((await post(request(empty))).status).toBe(413);
    expect((await post(request('not multipart'))).status).toBe(415);expect(requestJson).not.toHaveBeenCalled();
  });
  it('bounds actual bytes with a false length, before copying or parsing the file',async()=>{
    let cancelled=false;
    const body=new ReadableStream<Uint8Array>({start(c){c.enqueue(new Uint8Array(VIDEO_WIRE_LIMIT+1));},cancel(){cancelled=true;}});
    const req=new Request('http://localhost',{method:'POST',body,headers:{'Content-Type':'multipart/form-data; boundary=fixture','Content-Length':'1'},duplex:'half'} as RequestInit);
    await expect(videoRequestBody(req)).rejects.toMatchObject({status:413,code:'video_too_large'});expect(cancelled).toBe(true);
  });
  it('bounds part count even with boundaries split across wire chunks',async()=>{
    const wire=Buffer.from('--fixture'.repeat(7));let cancelled=false;
    const body=new ReadableStream<Uint8Array>({start(c){for(const byte of wire)c.enqueue(new Uint8Array([byte]));},cancel(){cancelled=true;}});
    const req=new Request('http://localhost',{method:'POST',body,headers:{'Content-Type':'multipart/form-data; boundary=fixture'},duplex:'half'} as RequestInit);
    await expect(videoRequestBody(req)).rejects.toMatchObject({code:'invalid_video_form'});expect(cancelled).toBe(true);
  });
  it('times out unfinished input and cancels its reader',async()=>{
    let cancelled=false;const body=new ReadableStream<Uint8Array>({cancel(){cancelled=true;}});
    const req=new Request('http://localhost',{method:'POST',body,headers:{'Content-Type':'multipart/form-data; boundary=fixture'},duplex:'half'} as RequestInit);
    await expect(videoRequestBody(req,1)).rejects.toMatchObject({status:408,code:'video_upload_timeout'});expect(cancelled).toBe(true);
  });
  it('rejects concurrent deliveries before consuming the second body and releases on error',async()=>{
    let release!:(value:unknown)=>void;vi.mocked(requestJson).mockImplementationOnce(()=>new Promise(resolve=>{release=resolve;}));
    const first=post(request());await vi.waitFor(()=>expect(requestJson).toHaveBeenCalledOnce());
    const second=request();expect((await post(second)).status).toBe(429);expect(second.bodyUsed).toBe(false);
    release({broken:true});const failed=await first;expect(failed.status).toBe(502);expect(await failed.text()).toContain('same request key');expect((await post(request())).status).toBe(202);
  });
  it('checks scope, original job, rights/language, retention, mixed origin and duplicate history',()=>{
    const data=form();expect(videoRegistrationReceipt(registered,projectId,data).source_id).toBe(sourceId);
    for(const patch of [{project_id:sourceId},{kind:'transcript'},{filename:'different.mp4'},{authorization_mode:'licensed_content'},{video_retention:null},{audio_retention:audioRetention()},{metadata:{...source.metadata,requested_language:'tr'}}]) expect(()=>videoRegistrationReceipt({...registered,source:{...source,...patch}},projectId,data)).toThrow(ApiError);
    for(const patch of [{source_id:jobId},{job_type:'visual_index'},{generation:2},{project_id:sourceId}]) expect(()=>videoRegistrationReceipt({...registered,job:{...registered.job,...patch}},projectId,data)).toThrow(ApiError);
    expect(videoRegistrationReceipt({...registered,deduplicated:true,source:{...source,generation:3,status:'ready',active_generation:3}},projectId,data).job_id).toBe(jobId);
  });
});
