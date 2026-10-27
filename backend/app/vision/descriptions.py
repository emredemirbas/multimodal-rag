"""Scoped complete description snapshots; native work happens outside DB locks."""
import hashlib
import json
import logging
from uuid import UUID

from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field

from ..embedding_profiles import configured_space,HASH_SPACE,QWEN_SPACE
from ..provenance import DescriptionOrigin
from ..sources.contracts import Job, Registration, SourceCommand, SourceError
from ..store import ProjectNotFoundError
from .descriptions_client import DescriptionIdentity, FrameDescription, PROMPT
from .gallery import VisualGalleryRepository

LOGGER = logging.getLogger('tutorial_workspace.jobs')


def digest(value):
    return hashlib.sha256(json.dumps(value.model_dump(mode='json'), sort_keys=True, ensure_ascii=False,
        separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def origin(run):
    identity = DescriptionIdentity.model_validate(run['identity'])
    return DescriptionOrigin(job_id=run['job_id'], generation=run['generation'], provider=identity.provider,
        model=identity.model, model_digest=identity.model_digest, engine=identity.engine,
        prompt_version=identity.prompt_version, completed_at=run['completed_at'])


class DescribedFrame(BaseModel):
    frame_id: UUID
    description: FrameDescription


class DescriptionView(BaseModel):
    source_id: UUID
    enabled: bool
    latest_job: Job | None = None
    index_job: Job | None = None
    origin: DescriptionOrigin | None = None
    gallery_generation: int | None = None
    index_generation: int | None = None
    items: list[DescribedFrame] = Field(default_factory=list, max_length=20)


class DescriptionRepository:
    def __init__(self, repository):
        self.repository = repository

    @staticmethod
    def scope(claim):
        return tuple(claim[k] for k in ('tenant_id', 'project_id', 'source_id', 'id', 'generation'))

    def enqueue(self, tenant, project, source, actor, key):
        SourceCommand(idempotency_key=key)
        repo = self.repository
        if not repo.settings.frame_descriptions_enabled:
            raise SourceError('frame_descriptions_disabled', 'Explicit local vision model setup and operator opt-in are required.', 503)
        with repo.store._connect() as connection:
            state = repo._project(connection, tenant, project, actor)
            current = repo._source(connection, tenant, project, source)
            receipt = connection.execute('SELECT command,job_id FROM source_commands WHERE tenant_id=%s AND project_id=%s AND source_id=%s AND idempotency_key=%s',
                (tenant, project, source, key)).fetchone()
            if receipt:
                if receipt['command'] != 'describe_visual': raise SourceError('idempotency_conflict', 'This key was used for another action.', 409)
                job = connection.execute('SELECT * FROM processing_jobs WHERE tenant_id=%s AND project_id=%s AND source_id=%s AND id=%s',
                    (tenant, project, source, receipt['job_id'])).fetchone()
                return Registration(source=current, job=Job.model_validate(job), deduplicated=True)
            if state['status'] != 'active': raise SourceError('project_archived', 'Restore the project before describing frames.', 409)
            if current.kind != 'video' or current.job is None or current.job.status not in {'succeeded', 'failed', 'cancelled'}:
                raise SourceError('source_busy', 'Use a complete retained video gallery with no unfinished source job.', 409)
            gallery = VisualGalleryRepository(repo).read_snapshot(connection, tenant, project, source, actor)
            if gallery.origin is None: raise SourceError('visual_not_retained', 'A complete retained gallery is required.', 409)
            publication = connection.execute('SELECT job_id FROM visual_publications WHERE tenant_id=%s AND project_id=%s AND source_id=%s AND generation=%s AND published_at IS NOT NULL',
                (tenant, project, source, gallery.generation)).fetchone()
            from .index import VisualIndexRepository
            VisualIndexRepository(repo)._publication(connection,tenant,project,source,publication['job_id'],actor)
            if connection.execute('SELECT 1 FROM memberships WHERE tenant_id=%s AND user_id=%s FOR KEY SHARE',(tenant,actor)).fetchone() is None:
                raise ProjectNotFoundError('project not found')
            job = repo._new_job(connection, tenant, project, source, actor, current.generation+1, 'visual_describe')
            connection.execute('''INSERT INTO visual_description_runs (tenant_id,project_id,source_id,job_id,generation,actor_user_id,
                publication_job_id,publication_generation,model_digest,prompt_version,target_embedding_space)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''', (tenant, project, source, job.id, job.generation, actor,
                publication['job_id'], gallery.generation, repo.settings.vision_model_digest, PROMPT, configured_space(repo.settings.embedding_provider)))
            connection.execute("UPDATE sources SET generation=%s,status='processing',failure_code=NULL,failure_detail=NULL,updated_at=now() WHERE tenant_id=%s AND project_id=%s AND id=%s", (job.generation, tenant, project, source))
            connection.execute('UPDATE processing_jobs SET total_segments=%s WHERE tenant_id=%s AND project_id=%s AND id=%s', (len(gallery.items), tenant, project, job.id))
            connection.execute("INSERT INTO source_commands VALUES (%s,%s,%s,%s,'describe_visual',%s)", (tenant, project, source, key, job.id))
            repo.store._record_audit(connection, tenant_id=tenant, project_id=project, actor_user_id=actor, action='source.describe_visual')
            return Registration(source=repo._source(connection, tenant, project, source), job=job)

    def complete_snapshot(self, connection, tenant, project, source, job, publication=None):
        run = connection.execute('SELECT * FROM visual_description_runs WHERE tenant_id=%s AND project_id=%s AND source_id=%s AND job_id=%s',
            (tenant, project, source, job)).fetchone()
        if not run or run['completed_at'] is None or publication is not None and run['publication_job_id'] != publication:
            raise SourceError('descriptions_not_ready', 'A complete description snapshot for this gallery is required.', 409)
        _, frames = self._frames(connection, run)
        saved = self._saved(connection, run, frames)
        if len(saved) != len(frames): raise SourceError('invalid_visual_description', 'The complete description snapshot is inconsistent.', 503)
        return run, {item['frame_id']: FrameDescription.model_validate(item['description']) for item in saved}

    def _frames(self, connection, run):
        from .index import VisualIndexRepository
        publication, frames = VisualIndexRepository(self.repository)._publication(connection, run['tenant_id'], run['project_id'],
            run['source_id'], run['publication_job_id'], None)
        if (publication['generation'] != run['publication_generation'] or run['prompt_version'] != PROMPT
                or run['target_embedding_space'] not in {HASH_SPACE,QWEN_SPACE}):
            raise SourceError('invalid_visual_description', 'The pinned frame description inputs changed.', 503)
        return publication, frames

    def _saved(self, connection, run, frames):
        rows = connection.execute('SELECT * FROM visual_descriptions WHERE tenant_id=%s AND project_id=%s AND source_id=%s AND job_id=%s AND generation=%s ORDER BY ordinal',
            tuple(run[k] for k in ('tenant_id','project_id','source_id','job_id','generation'))).fetchall()
        if len(rows) > len(frames): raise SourceError('invalid_visual_description', 'Invalid description checkpoint.', 503)
        if run['identity'] is not None:
            try: identity = DescriptionIdentity.model_validate(run['identity'])
            except ValueError: raise SourceError('invalid_visual_description','Invalid pinned description identity.',503) from None
            if identity.model_digest != run['model_digest'] or identity.prompt_version != run['prompt_version'] or digest(identity)!=run['identity_sha256']:
                raise SourceError('vision_model_changed', 'The pinned description identity changed.', 503)
        elif rows: raise SourceError('invalid_visual_description', 'Missing pinned description identity.', 503)
        for ordinal, row in enumerate(rows):
            try: value = FrameDescription.model_validate(row['description'])
            except ValueError: raise SourceError('invalid_visual_description','Invalid saved description structure.',503) from None
            if (row['ordinal'] != ordinal or row['frame_id'] != frames[ordinal]['id']
                    or row['publication_job_id'] != run['publication_job_id'] or row['image_sha256'] != frames[ordinal]['image_sha256']
                    or row['description_sha256'] != digest(value)):
                raise SourceError('invalid_visual_description', 'The description checkpoint failed verification.', 503)
        return rows

    def state(self, connection, claim):
        repo = self.repository
        if not repo._fenced(connection, claim): return None
        if connection.execute('SELECT 1 FROM memberships WHERE tenant_id=%s AND user_id=%s FOR KEY SHARE', (claim['tenant_id'], claim['actor_user_id'])).fetchone() is None: return None
        run = connection.execute('''SELECT d.*,j.lease_expires_at,j.processed_segments,j.cancellation_requested_at FROM visual_description_runs d
            JOIN processing_jobs j ON j.tenant_id=d.tenant_id AND j.project_id=d.project_id AND j.source_id=d.source_id AND j.id=d.job_id AND j.generation=d.generation
            WHERE d.tenant_id=%s AND d.project_id=%s AND d.source_id=%s AND d.job_id=%s AND d.generation=%s
              AND j.job_type='visual_describe' AND j.actor_user_id=d.actor_user_id AND d.actor_user_id=%s
              AND j.cancellation_requested_at IS NULL AND j.lease_expires_at>clock_timestamp()''', (*self.scope(claim), claim['actor_user_id'])).fetchone()
        if run is None: return None
        _, frames = self._frames(connection, run)
        rows = self._saved(connection, run, frames)
        if run['completed_at'] is not None or len(rows) != run['processed_segments']:
            raise SourceError('invalid_visual_description', 'The description progress is inconsistent.', 503)
        return run, frames, rows

    def next(self, claim, identity=None):
        with self.repository.store._connect() as connection:
            state = self.state(connection, claim)
            if state is None: return None
            run, frames, rows = state
            if identity is not None:
                identity = DescriptionIdentity.model_validate(identity.model_dump())
                if identity.model_digest != run['model_digest'] or run['identity'] is not None and identity.model_dump() != run['identity']:
                    raise SourceError('vision_model_changed', 'Restore the originally pinned vision identity before retrying.', 503)
                connection.execute('UPDATE visual_description_runs SET identity=%s,identity_sha256=%s WHERE tenant_id=%s AND project_id=%s AND source_id=%s AND job_id=%s AND generation=%s',
                    (Jsonb(identity.model_dump()),digest(identity), *self.scope(claim)))
                run['identity'] = identity.model_dump()
                if not connection.execute('SELECT clock_timestamp()<%s AS ok',(run['lease_expires_at'],)).fetchone()['ok']:
                    connection.rollback(); return None
            return run, frames, len(rows)

    def save(self, claim, offset, result):
        repo = self.repository
        value = FrameDescription.model_validate(result.description.model_dump())
        identity = DescriptionIdentity.model_validate(result.identity.model_dump())
        if (type(result.duration_ms) is not int or not 0 <= result.duration_ms <= 210000
                or any(v is not None and (type(v) is not int or not 0 <= v <= 100000) for v in (result.input_tokens,result.output_tokens))):
            raise SourceError('invalid_visual_description', 'Invalid local description usage metadata.', 503)
        with repo.store._connect() as connection:
            state = self.state(connection, claim)
            if state is None: return False
            run, frames, rows = state
            if offset != len(rows) or offset >= len(frames): return False
            if run['identity'] != identity.model_dump(): raise SourceError('vision_model_changed', 'The original vision identity changed.', 503)
            frame = frames[offset]
            if result.input_sha256 != frame['image_sha256']:
                raise SourceError('invalid_visual_description','The description is not bound to these exact frame bytes.',503)
            connection.execute('''INSERT INTO visual_descriptions (tenant_id,project_id,source_id,job_id,generation,frame_id,publication_job_id,
                ordinal,image_sha256,description,description_sha256,input_tokens,output_tokens,duration_ms)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''', (*self.scope(claim),frame['id'],run['publication_job_id'],offset,
                frame['image_sha256'],Jsonb(value.model_dump()),digest(value),result.input_tokens,result.output_tokens,result.duration_ms))
            connection.execute('UPDATE processing_jobs SET processed_segments=%s,progress_percent=%s WHERE tenant_id=%s AND project_id=%s AND source_id=%s AND id=%s AND generation=%s',
                (offset+1,10+(offset+1)*80//len(frames),*self.scope(claim)))
            if not connection.execute('SELECT clock_timestamp()<%s AS ok', (run['lease_expires_at'],)).fetchone()['ok']:
                connection.rollback(); return False
        LOGGER.info(json.dumps({'event':'frame_description_checkpoint','job_id':str(claim['id']),'saved_frames':offset+1}))
        return True

    def advance(self, claim):
        repo = self.repository
        with repo.store._connect() as connection:
            state = self.state(connection, claim)
            if state is None: return False
            run, frames, rows = state
            if not rows or len(rows)<len(frames) and len(rows) <= claim['processed_segments']:
                raise SourceError('checkpoint_no_progress', 'The description job made no progress.', 503, transient=True)
            done = len(rows) == len(frames)
            repo._finish_attempt(connection, claim['tenant_id'], claim['project_id'], claim['id'], 'succeeded' if done else 'checkpointed', None)
            if done:
                connection.execute('UPDATE visual_description_runs SET completed_at=clock_timestamp() WHERE tenant_id=%s AND project_id=%s AND source_id=%s AND job_id=%s AND generation=%s', self.scope(claim))
                connection.execute("UPDATE processing_jobs SET status='succeeded',stage='descriptions_ready',progress_percent=100,finished_at=now(),lease_token=NULL,lease_expires_at=NULL,updated_at=now() WHERE tenant_id=%s AND project_id=%s AND source_id=%s AND id=%s AND generation=%s", self.scope(claim))
                tokens = lambda key: sum(row[key] for row in rows) if all(row[key] is not None for row in rows) else None
                connection.execute('''INSERT INTO usage_events (tenant_id,project_id,source_id,job_id,generation,provider,model,
                    input_characters,segment_count,duration_ms,embedding_space,model_digest,prompt_version,input_tokens,output_tokens,input_image_count,input_image_bytes)
                    VALUES (%s,%s,%s,%s,%s,'ollama-local','qwen3.5:4b',0,0,%s,NULL,%s,%s,%s,%s,%s,%s)''',
                    (*self.scope(claim),sum(row['duration_ms'] for row in rows),run['model_digest'],PROMPT,tokens('input_tokens'),tokens('output_tokens'),len(rows),sum(frame['byte_count'] for frame in frames)))
                from .index import VisualIndexRepository
                item = VisualIndexRepository(repo).enqueue(claim['tenant_id'],claim['project_id'],claim['source_id'],run['publication_job_id'],
                    claim['actor_user_id'],f'description-{claim["id"]}-index-v2',connection=connection,continuation=True,
                    target_embedding_space=run['target_embedding_space'],description_job=claim['id'])
                connection.execute('UPDATE visual_description_runs SET index_job_id=%s,index_generation=%s WHERE tenant_id=%s AND project_id=%s AND source_id=%s AND job_id=%s AND generation=%s', (item.job.id,item.job.generation,*self.scope(claim)))
            else:
                connection.execute("UPDATE processing_jobs SET status='pending',stage='waiting_description_continuation',continuation_pending=true,available_at=now()+interval '2 seconds',lease_token=NULL,lease_expires_at=NULL,updated_at=now() WHERE tenant_id=%s AND project_id=%s AND source_id=%s AND id=%s AND generation=%s", self.scope(claim))
                repo.enqueue(connection,claim['tenant_id'],claim['project_id'],claim['source_id'],claim['id'],claim['generation'],delay=2)
            if not connection.execute('SELECT clock_timestamp()<%s AS ok',(run['lease_expires_at'],)).fetchone()['ok']:
                connection.rollback(); return False
        LOGGER.info(json.dumps({'event':'frame_description_completed' if done else 'frame_description_continuation',
            'job_id':str(claim['id']),'saved_frames':len(rows),'index_queued':done}))
        return done

    def read(self, tenant, project, source, actor):
        repo = self.repository
        with repo.store._connect() as connection:
            connection.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            gallery = VisualGalleryRepository(repo).read_snapshot(connection,tenant,project,source,actor)
            latest = connection.execute('''SELECT j.* FROM processing_jobs j JOIN visual_description_runs d ON d.tenant_id=j.tenant_id AND d.project_id=j.project_id AND d.source_id=j.source_id AND d.job_id=j.id
                WHERE j.tenant_id=%s AND j.project_id=%s AND j.source_id=%s ORDER BY j.generation DESC LIMIT 1''',(tenant,project,source)).fetchone()
            completed = connection.execute('''SELECT * FROM visual_description_runs WHERE tenant_id=%s AND project_id=%s AND source_id=%s
                AND publication_generation=%s AND completed_at IS NOT NULL ORDER BY generation DESC LIMIT 1''',(tenant,project,source,gallery.generation)).fetchone()
            values = {}
            if completed:
                run, captions = self.complete_snapshot(connection,tenant,project,source,completed['job_id'])
                indexed = connection.execute('SELECT * FROM processing_jobs WHERE tenant_id=%s AND project_id=%s AND source_id=%s AND id=%s',
                    (tenant,project,source,run['index_job_id'])).fetchone()
                values = dict(origin=origin(run),gallery_generation=run['publication_generation'],index_generation=run['index_generation'],
                    index_job=Job.model_validate(indexed) if indexed else None,
                    items=[{'frame_id':str(frame.id),'description':captions[frame.id].model_dump()} for frame in gallery.items])
            return DescriptionView(source_id=str(source),enabled=repo.settings.frame_descriptions_enabled,
                latest_job=Job.model_validate(latest) if latest else None,**values)
