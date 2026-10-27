"""Versioned, fenced text-only indexing of already retained OCR. No native I/O."""
import hashlib
import json
import logging
import math
import struct
from contextlib import nullcontext
from uuid import NAMESPACE_URL, uuid5

from ..embedding_profiles import HASH_SPACE, QWEN_SPACE, QWEN_MODEL, QWEN_DIGEST
from ..sources.contracts import Job, Registration, SourceCommand, SourceError
from ..store import ProjectNotFoundError
from .gallery import VisualGalleryRepository

VERSION = 'visual-ocr-chunks-v1'
MIXED_VERSION = 'visual-evidence-chunks-v2'
LOGGER = logging.getLogger('tutorial_workspace.jobs')


def chunks(tenant, project, source, generation, frames, *, descriptions=None):
    result = []
    if descriptions is not None:
        from .descriptions_client import description_text
        for frame in frames:
            parts = []
            prefix = 'Unreviewed OCR text:\n'
            size = 1200-len(prefix)
            parts.extend(('ocr', offset, prefix+frame['ocr_text'][offset:offset+size])
                         for offset in range(0,len(frame['ocr_text']),size) if frame['ocr_text'][offset:offset+size].strip())
            caption = description_text(descriptions[frame['id']])
            if caption: parts.append(('description',0,caption))
            for kind,offset,text in parts:
                digest = hashlib.sha256(text.encode()).hexdigest()
                identity = f"{tenant}:{project}:{source}:{generation}:{MIXED_VERSION}:{frame['id']}:{kind}:{offset}:{digest}"
                result.append(dict(segment_id=uuid5(NAMESPACE_URL,identity),frame_id=frame['id'],
                    start_ms=frame['timestamp_ms'],text_offset=offset,text=text))
        if len(result)>300 or any(len(item['text'])>1200 for item in result):
            raise SourceError('invalid_visual_index','The mixed visual evidence exceeds its bounded index.',503)
        return result
    for frame in frames:
        for offset in range(0, len(frame['ocr_text']), 1200):
            text = frame['ocr_text'][offset:offset+1200]
            if not text.strip(): continue
            digest = hashlib.sha256(text.encode()).hexdigest()
            identity = f"{tenant}:{project}:{source}:{generation}:{VERSION}:{frame['id']}:{offset}:{digest}"
            result.append(dict(segment_id=uuid5(NAMESPACE_URL, identity), frame_id=frame['id'],
                start_ms=frame['timestamp_ms'], text_offset=offset, text=text))
    if len(result) > 280:
        raise SourceError('invalid_visual_index', 'The retained OCR exceeds the index limit.')
    return result


def provider_identity(provider):
    actual = (provider.space_id, provider.name, provider.model, provider.dimensions, provider.model_digest)
    approved = ((HASH_SPACE, 'local-deterministic', 'signed-hash-embedding-v1', 64, None),
                (QWEN_SPACE, 'ollama-local', QWEN_MODEL, 1024, QWEN_DIGEST))
    if actual not in approved:
        raise SourceError('processing_configuration_changed', 'Restore the approved embedding provider before retrying.', 409)


class VisualIndexRepository:
    def __init__(self, repository):
        self.repository = repository
        self.gallery = VisualGalleryRepository(repository)

    @staticmethod
    def _scope(claim):
        return tuple(claim[k] for k in ('tenant_id', 'project_id', 'source_id', 'id', 'generation'))

    def _publication(self, connection, tenant, project, source, publication, actor):
        row = connection.execute(
            '''SELECT * FROM visual_publications WHERE tenant_id=%s AND project_id=%s
               AND source_id=%s AND job_id=%s AND published_at IS NOT NULL''',
            (tenant, project, source, publication),
        ).fetchone()
        if row is None:
            raise SourceError('visual_not_retained', 'A complete retained gallery is required.', 409)
        _, snapshot = self.gallery._snapshot(connection, row, actor)
        frames = self.gallery._rows(connection, row)
        self.gallery._verify_rows(row, snapshot, frames)
        if len(frames) != len(snapshot.frames):
            raise SourceError('artifact_integrity', 'The retained gallery is incomplete.')
        return row, frames

    def enqueue(self, tenant, project, source, publication, actor, idempotency_key, *, connection=None,
                target_embedding_space=None, continuation=False, description_job=None):
        """Internal command. A new key explicitly requests a new index generation."""
        if continuation and connection is None:
            raise ValueError('Automatic continuations require their parent transaction')
        SourceCommand(idempotency_key=idempotency_key)
        repo = self.repository
        with (repo.store._connect() if connection is None else nullcontext(connection)) as connection:
            state = repo._project(connection, tenant, project, actor)
            current = repo._source(connection, tenant, project, source)
            receipt = connection.execute(
                '''SELECT c.command,j.*,i.publication_job_id,i.description_job_id FROM source_commands c
                   JOIN processing_jobs j ON j.tenant_id=c.tenant_id AND j.project_id=c.project_id AND j.id=c.job_id
                   LEFT JOIN visual_index_runs i ON i.tenant_id=j.tenant_id AND i.project_id=j.project_id AND i.job_id=j.id
                   WHERE c.tenant_id=%s AND c.project_id=%s AND c.source_id=%s AND c.idempotency_key=%s''',
                (tenant, project, source, idempotency_key),
            ).fetchone()
            if receipt:
                if receipt['command'] != 'index_visual' or receipt['publication_job_id'] != publication or receipt['description_job_id'] != description_job:
                    raise SourceError('idempotency_conflict', 'This command key was used for different input.', 409)
                return Registration(source=current, job=Job.model_validate(receipt), deduplicated=True)
            if state['status'] != 'active' and not continuation:
                raise SourceError('project_archived', 'Restore the project before indexing frames.', 409)
            origin, _ = self._publication(connection, tenant, project, source, publication, actor)
            if description_job is not None:
                from .descriptions import DescriptionRepository
                DescriptionRepository(repo).complete_snapshot(connection,tenant,project,source,description_job,publication)
            if connection.execute('SELECT 1 FROM memberships WHERE tenant_id=%s AND user_id=%s FOR KEY SHARE',
                                  (tenant, actor)).fetchone() is None:
                raise ProjectNotFoundError('project not found')
            if current.job is None or current.job.status not in {'succeeded', 'failed', 'cancelled'}:
                raise SourceError('source_busy', 'Wait for or cancel the current source job.', 409)
            generation = current.generation + 1
            connection.execute('DELETE FROM visual_index_chunks WHERE tenant_id=%s AND project_id=%s AND source_id=%s', (tenant, project, source))
            job = repo._new_job(connection, tenant, project, source, actor, generation, 'visual_index',
                                target_embedding_space=target_embedding_space)
            connection.execute(
                '''INSERT INTO visual_index_runs (tenant_id,project_id,source_id,job_id,generation,
                   publication_job_id,publication_generation,processing_version,description_job_id) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
                (tenant, project, source, job.id, generation, publication, origin['generation'], MIXED_VERSION if description_job else VERSION,description_job),
            )
            connection.execute("UPDATE sources SET generation=%s,status='indexing',failure_code=NULL,failure_detail=NULL,updated_at=now() WHERE tenant_id=%s AND project_id=%s AND id=%s",
                               (generation, tenant, project, source))
            connection.execute("INSERT INTO source_commands (tenant_id,project_id,source_id,idempotency_key,command,job_id) VALUES (%s,%s,%s,%s,'index_visual',%s)",
                               (tenant, project, source, idempotency_key, job.id))
            repo.store._record_audit(connection, tenant_id=tenant, project_id=project, actor_user_id=actor, action='source.index_visual')
            return Registration(source=repo._source(connection, tenant, project, source), job=job)

    def _state(self, connection, claim):
        repo = self.repository
        if not repo._fenced(connection, claim): return None
        if connection.execute('SELECT 1 FROM memberships WHERE tenant_id=%s AND user_id=%s FOR KEY SHARE',
                              (claim['tenant_id'], claim['actor_user_id'])).fetchone() is None: return None
        row = connection.execute(
            '''SELECT j.*,i.publication_job_id,i.publication_generation,i.description_job_id,i.processing_version AS parser_version
               FROM processing_jobs j JOIN visual_index_runs i ON i.tenant_id=j.tenant_id AND i.project_id=j.project_id
                 AND i.source_id=j.source_id AND i.job_id=j.id AND i.generation=j.generation
               WHERE j.tenant_id=%s AND j.project_id=%s AND j.source_id=%s AND j.id=%s AND j.generation=%s
                 AND j.job_type='visual_index' AND j.actor_user_id=%s AND j.cancellation_requested_at IS NULL
                 AND j.lease_expires_at>clock_timestamp()''', (*self._scope(claim), claim['actor_user_id']),
        ).fetchone()
        if row is None: return None
        if row['target_embedding_space'] != claim['target_embedding_space']:
            raise SourceError('processing_configuration_changed', 'The pinned embedding space changed.', 409)
        if row['parser_version'] != (MIXED_VERSION if row['description_job_id'] else VERSION):
            raise SourceError('checkpoint_input_changed', 'The OCR parser changed; start a new index generation.', 409)
        publication, frames = self._publication(connection, claim['tenant_id'], claim['project_id'], claim['source_id'], row['publication_job_id'], claim['actor_user_id'])
        if publication['generation'] != row['publication_generation']:
            raise SourceError('artifact_integrity', 'The retained gallery identity changed.')
        descriptions = None
        if row['description_job_id']:
            from .descriptions import DescriptionRepository
            _,descriptions = DescriptionRepository(repo).complete_snapshot(connection,claim['tenant_id'],claim['project_id'],
                claim['source_id'],row['description_job_id'],row['publication_job_id'])
        expected = chunks(claim['tenant_id'], claim['project_id'], claim['source_id'], claim['generation'], frames,descriptions=descriptions)
        manifest = hashlib.sha256(''.join(str(item['segment_id']) for item in expected).encode()).hexdigest()
        if row['chunk_manifest_sha256'] is not None and (row['chunk_manifest_sha256'] != manifest or row['total_segments'] != len(expected)):
            raise SourceError('checkpoint_input_changed', 'The retained OCR changed; start a new index generation.', 409)
        saved = connection.execute(
            'SELECT * FROM visual_index_chunks WHERE tenant_id=%s AND project_id=%s AND source_id=%s AND job_id=%s AND generation=%s ORDER BY ordinal',
            self._scope(claim),
        ).fetchall()
        if len(saved) != row['processed_segments'] or len(saved) > len(expected):
            raise SourceError('invalid_visual_index', 'The private OCR index failed verification.')
        for ordinal, item in enumerate(saved):
            vector = repo.store._parse_vector(item['embedding'])
            if (item['ordinal'] != ordinal or any(item[k] != expected[ordinal][k] for k in expected[ordinal])
                    or item['publication_job_id'] != row['publication_job_id'] or item['embedding_space'] != row['target_embedding_space']
                    or not self._vector_valid(vector, row['target_embedding_space']) or item['embedding_sha256'] != self._vector_digest(vector)):
                raise SourceError('invalid_visual_index', 'The private OCR index failed verification.')
        return row, expected, manifest

    @staticmethod
    def _vector_valid(vector, space):
        dims = 64 if space == HASH_SPACE else 1024 if space == QWEN_SPACE else 0
        return (len(vector) == dims and dims > 0 and all(type(v) in (int, float) and math.isfinite(v) for v in vector)
                and (.999 <= sum(v*v for v in vector) <= 1.001 or space == HASH_SPACE and all(v == 0 for v in vector)))

    @staticmethod
    def _vector_digest(vector):
        # pgvector stores float32; zero sign is not semantically significant.
        return hashlib.sha256(struct.pack(f'!{len(vector)}f', *(v if v else 0. for v in vector))).hexdigest()

    @staticmethod
    def _unexpired(connection, job):
        return connection.execute('SELECT clock_timestamp()<%s AS valid', (job['lease_expires_at'],)).fetchone()['valid']

    def begin(self, claim, provider):
        provider_identity(provider)
        with self.repository.store._connect() as connection:
            state = self._state(connection, claim)
            if state is None: return None
            job, expected, manifest = state
            if job['target_embedding_space'] != provider.space_id:
                raise SourceError('processing_configuration_changed', 'Restore the original embedding mode or start a new index generation.', 409)
            if not expected:
                raise SourceError('visual_ocr_empty', 'No nonblank OCR text was found; inspect the retained frames instead.', 422)
            connection.execute('UPDATE processing_jobs SET chunk_manifest_sha256=%s,total_segments=%s WHERE tenant_id=%s AND project_id=%s AND source_id=%s AND id=%s AND generation=%s',
                               (manifest, len(expected), *self._scope(claim)))
            if not self._unexpired(connection, job):
                connection.rollback(); return None
            return job['processed_segments'], expected

    def save(self, claim, offset, batch):
        with self.repository.store._connect() as connection:
            state = self._state(connection, claim)
            if state is None: return False
            job, expected, _ = state
            if offset != job['processed_segments']: return False
            items = expected[offset:offset+len(batch.vectors)]
            if (job['chunk_manifest_sha256'] is None or not 1 <= len(items) == len(batch.vectors) == min(8, len(expected)-offset)
                    or batch.input_tokens is not None and (type(batch.input_tokens) is not int or not 0 <= batch.input_tokens <= 100000)
                    or any(not self._vector_valid(v, job['target_embedding_space']) for v in batch.vectors)):
                raise SourceError('invalid_embeddings', 'The OCR embedding batch could not be validated.', 503)
            for ordinal, (item, vector) in enumerate(zip(items, batch.vectors, strict=True), offset):
                connection.execute(
                    '''INSERT INTO visual_index_chunks (tenant_id,project_id,source_id,job_id,generation,ordinal,
                       segment_id,frame_id,publication_job_id,start_ms,text_offset,text,embedding_space,embedding,embedding_sha256)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::vector,%s)''',
                    (*self._scope(claim), ordinal, item['segment_id'], item['frame_id'], job['publication_job_id'], item['start_ms'],
                     item['text_offset'], item['text'], job['target_embedding_space'], self.repository.store._vector_literal(vector), self._vector_digest(vector)),
                )
            end = offset + len(items)
            connection.execute('UPDATE processing_jobs SET processed_segments=%s,checkpoint_input_tokens=checkpoint_input_tokens+%s,progress_percent=%s,updated_at=now() WHERE tenant_id=%s AND project_id=%s AND source_id=%s AND id=%s AND generation=%s',
                               (end, batch.input_tokens, 10+80*end//len(expected), *self._scope(claim)))
            if not self._unexpired(connection, job):
                connection.rollback(); return False
        LOGGER.info(json.dumps({'event': 'visual_index_checkpoint', 'job_id': str(claim['id']), 'processed_segments': end, 'total_segments': len(expected)}))
        return True

    def continue_later(self, claim):
        repo = self.repository
        with repo.store._connect() as connection:
            state = self._state(connection, claim)
            if state is None: return False
            job, expected, _ = state
            if not claim['processed_segments'] < job['processed_segments'] < len(expected):
                raise SourceError('checkpoint_no_progress', 'OCR indexing could not advance; free resources and retry.', transient=True)
            repo._finish_attempt(connection, claim['tenant_id'], claim['project_id'], claim['id'], 'checkpointed', None)
            connection.execute("UPDATE processing_jobs SET status='pending',stage='waiting_continuation',continuation_pending=true,available_at=now()+interval '2 seconds',lease_token=NULL,lease_expires_at=NULL,updated_at=now() WHERE tenant_id=%s AND project_id=%s AND source_id=%s AND id=%s AND generation=%s", self._scope(claim))
            repo.enqueue(connection, claim['tenant_id'], claim['project_id'], claim['source_id'], claim['id'], claim['generation'], delay=2)
            if not self._unexpired(connection, job):
                connection.rollback(); return False
        return True

    def finish(self, claim, provider):
        provider_identity(provider)
        repo = self.repository
        with repo.store._connect() as connection:
            state = self._state(connection, claim)
            if state is None: return False
            job, expected, _ = state
            if job['target_embedding_space'] != provider.space_id or not expected or job['processed_segments'] != len(expected) or not job['chunk_manifest_sha256']:
                raise SourceError('checkpoint_incomplete', 'The OCR index is not complete.', 503)
            version = f"{job['parser_version']}:g{claim['generation']}"
            connection.execute(
                '''INSERT INTO processing_versions (tenant_id,project_id,source_id,generation,processing_version,
                   embedding_provider,embedding_model,embedding_dimensions,embedding_space,embedding_model_digest,visual_publication_job_id,visual_description_job_id)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
                (claim['tenant_id'], claim['project_id'], claim['source_id'], claim['generation'], version,
                 provider.name, provider.model, provider.dimensions, provider.space_id, provider.model_digest, job['publication_job_id'],job['description_job_id']),
            )
            connection.execute(
                '''INSERT INTO content_segments (tenant_id,project_id,source_id,id,generation,modality,start_ms,end_ms,
                   text,embedding,embedding_space,processing_version,frame_id,visual_publication_job_id)
                   SELECT tenant_id,project_id,source_id,segment_id,generation,'frame',start_ms,start_ms,text,
                          embedding,embedding_space,%s,frame_id,publication_job_id FROM visual_index_chunks
                   WHERE tenant_id=%s AND project_id=%s AND source_id=%s AND job_id=%s AND generation=%s''',
                (version, *self._scope(claim)),
            )
            repo._activate(connection, claim, provider.name, provider.model, len(expected), sum(len(item['text']) for item in expected), 0,
                embedding_space=provider.space_id, model_digest=provider.model_digest, input_tokens=job['checkpoint_input_tokens'],
                cumulative=True, processing_version=version)
            connection.execute('DELETE FROM visual_index_chunks WHERE tenant_id=%s AND project_id=%s AND source_id=%s AND job_id=%s AND generation=%s', self._scope(claim))
            if not self._unexpired(connection, job):
                connection.rollback(); return False
        LOGGER.info(json.dumps({'event': 'visual_index_completed', 'job_id': str(claim['id']), 'segment_count': len(expected), 'embedding_space': provider.space_id}))
        return True
