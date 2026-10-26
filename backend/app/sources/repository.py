from __future__ import annotations

import hashlib
import json
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from ..artifacts.storage import ArtifactStore, object_prefix
from ..artifacts.audio import retire_audio
from ..config import Settings
from ..models import AuthorizationMode, EvidenceSegment
from ..postgres import PostgresStore
from ..store import ProjectNotFoundError
from ..embedding_profiles import HASH_SPACE, configured_space
from .chunking import PROCESSING_VERSION, decode_transcript
from .contracts import Cleanup, Job, ManagedSource, Registration, SourceError, SourceList
from .adapters import TranscriptAdapter, YouTubeAdapter
from .playlists import bind_upload, current_item, read_items, store_snapshot


# One statement snapshots source/job/origin/retention together. Only explicit
# projection models below cross the API; no input key, digest or window payload.
SOURCE_DETAILS = '''SELECT s.*, to_jsonb(j) AS job, to_jsonb(ar) AS asr_origin,
    CASE WHEN ai.job_id IS NULL THEN NULL ELSE jsonb_build_object(
        'status', CASE WHEN ai.deleted_at IS NOT NULL THEN 'deleted'
                       WHEN ac.status='failed' THEN 'cleanup_failed'
                       WHEN ai.cleanup_id IS NOT NULL THEN 'cleanup_pending'
                       WHEN ai.expires_at<=now() THEN 'expired' ELSE 'temporary' END,
        'processing_expires_at',ai.expires_at,'cleanup_id',ai.cleanup_id,'deleted_at',ai.deleted_at
    ) END AS audio_retention
    FROM sources s
    LEFT JOIN LATERAL (
        SELECT * FROM processing_jobs WHERE tenant_id=s.tenant_id
        AND project_id=s.project_id AND source_id=s.id
        ORDER BY generation DESC, created_at DESC LIMIT 1
    ) j ON true
    LEFT JOIN source_artifacts a ON a.tenant_id=s.tenant_id AND a.project_id=s.project_id AND a.source_id=s.id
    LEFT JOIN asr_runs ar ON ar.tenant_id=a.tenant_id AND ar.project_id=a.project_id
        AND ar.source_id=a.source_id AND ar.job_id=a.asr_job_id AND ar.completed_at IS NOT NULL
    LEFT JOIN LATERAL (
        SELECT * FROM audio_inputs WHERE tenant_id=s.tenant_id AND project_id=s.project_id AND source_id=s.id
        ORDER BY generation DESC LIMIT 1
    ) ai ON true
    LEFT JOIN artifact_cleanup ac ON ac.tenant_id=ai.tenant_id AND ac.project_id=ai.project_id AND ac.id=ai.cleanup_id
'''


class SourceRepository:
    """PostgreSQL owns state; Redis messages are disposable delivery hints."""

    def __init__(self, store: PostgresStore, artifacts: ArtifactStore, settings: Settings):
        self.store, self.artifacts, self.settings = store, artifacts, settings

    def _project(self, connection, tenant: str, project: UUID, actor: UUID | None = None):
        if actor is not None:
            self.store._require_membership(connection, tenant, actor)
        row = connection.execute(
            'SELECT status FROM projects WHERE tenant_id=%s AND id=%s AND deleted_at IS NULL FOR UPDATE',
            (tenant, project),
        ).fetchone()
        if not row:
            raise ProjectNotFoundError('project not found')
        return row

    def _managed_source(self, row: dict) -> ManagedSource:
        source = ManagedSource.model_validate(row)
        source.reindex_required = (source.kind == 'transcript' and source.active_generation is not None
                                   and source.active_embedding_space != configured_space(self.settings.embedding_provider))
        return source

    def _source(self, connection, tenant: str, project: UUID, source: UUID) -> ManagedSource:
        row = connection.execute(
            SOURCE_DETAILS + ' WHERE s.tenant_id=%s AND s.project_id=%s AND s.id=%s AND s.deleted_at IS NULL',
            (tenant, project, source),
        ).fetchone()
        if row is None:
            raise ProjectNotFoundError('source not found')
        return self._managed_source(row)

    def get_source(self, tenant: str, project: UUID, source: UUID) -> ManagedSource:
        self.store.get_project(tenant, project)
        with self.store._connect() as connection:
            return self._source(connection, tenant, project, source)

    def list_sources(self, tenant: str, project: UUID) -> SourceList:
        self.store.get_project(tenant, project)
        with self.store._connect() as connection:
            rows = connection.execute(
                SOURCE_DETAILS + ''' WHERE s.tenant_id=%s AND s.project_id=%s AND s.deleted_at IS NULL
                   ORDER BY s.created_at DESC, s.id''', (tenant, project),
            ).fetchall()
            return SourceList(items=[self._managed_source(row) for row in rows], playlist_items=read_items(connection, tenant, project))

    def get_job(self, tenant: str, project: UUID, job: UUID) -> Job:
        self.store.get_project(tenant, project)
        with self.store._connect() as connection:
            row = connection.execute('SELECT * FROM processing_jobs WHERE tenant_id=%s AND project_id=%s AND id=%s', (tenant, project, job)).fetchone()
            if not row:
                raise ProjectNotFoundError('job not found')
            return Job.model_validate(row)

    @staticmethod
    def enqueue(connection, tenant: str, project: UUID, source: UUID, job: UUID, generation: int, delay: int = 0):
        connection.execute(
            '''INSERT INTO outbox_events (tenant_id,project_id,id,job_id,source_id,generation,available_at)
               VALUES (%s,%s,%s,%s,%s,%s,now()+make_interval(secs=>%s))
               ON CONFLICT (tenant_id,project_id,job_id) DO UPDATE
               SET sent_at=NULL,lease_token=NULL,lease_expires_at=NULL,available_at=EXCLUDED.available_at''',
            (tenant, project, uuid4(), job, source, generation, delay),
        )

    def _new_job(self, connection, tenant: str, project: UUID, source: UUID, actor: UUID, generation: int, job_type: str = 'transcript') -> Job:
        job_id = uuid4()
        row = connection.execute(
            '''INSERT INTO processing_jobs (tenant_id,project_id,id,source_id,job_type,stage,status,
               idempotency_key,generation,actor_user_id,target_embedding_space)
               VALUES (%s,%s,%s,%s,%s,'queued','pending',%s,%s,%s,%s) RETURNING *''',
            (tenant, project, job_id, source, job_type, f'ingest-{job_id}', generation, actor,
             configured_space(self.settings.embedding_provider) if job_type == 'transcript' else None),
        ).fetchone()
        SourceRepository.enqueue(connection, tenant, project, source, job_id, generation)
        return Job.model_validate(row)

    def register(self, tenant: str, project: UUID, actor: UUID, *, filename: str, content: bytes,
                 rights: AuthorizationMode, idempotency_key: str, playlist_item_id: UUID | None = None) -> Registration:
        if not content or len(content) > self.settings.upload_limit_bytes:
            raise SourceError('upload_too_large', 'Upload a non-empty SRT/VTT file of at most 2 MB.', 413)
        filename = TranscriptAdapter().normalize(filename).title
        decode_transcript(content)
        digest = hashlib.sha256(content).hexdigest()
        hash_input = [filename, digest, rights.value]
        if playlist_item_id is not None:
            hash_input.append(str(playlist_item_id))
        request_hash = hashlib.sha256(json.dumps(hash_input).encode()).hexdigest()
        source_id, reservation = uuid4(), uuid4()
        prefix = object_prefix(tenant, project, source_id)
        key = f'{prefix}1/input'
        # Write-ahead orphan reservation survives rollback/crash after object PUT.
        with self.store._connect() as connection:
            self._project(connection, tenant, project, actor)
            connection.execute(
                '''INSERT INTO artifact_cleanup (id,tenant_id,project_id,actor_user_id,object_prefix,available_at)
                   VALUES (%s,%s,%s,%s,%s,now()+interval '15 minutes')''',
                (reservation, tenant, project, actor, prefix),
            )
        try:
            with self.store._connect() as connection:
                if self._project(connection, tenant, project, actor)['status'] != 'active':
                    raise SourceError('project_archived', 'Restore the project before adding sources.', 409)
                # Project lock serializes same-scope registrations; uniqueness also enforces the key.
                existing = connection.execute(
                    'SELECT id,request_sha256 FROM sources WHERE tenant_id=%s AND project_id=%s AND idempotency_key=%s',
                    (tenant, project, idempotency_key),
                ).fetchone()
                if existing:
                    if existing['request_sha256'] != request_hash:
                        raise SourceError('idempotency_conflict', 'This upload key was already used for different input.', 409)
                    job = connection.execute(
                        '''SELECT * FROM processing_jobs WHERE tenant_id=%s AND project_id=%s AND source_id=%s
                           ORDER BY generation,created_at LIMIT 1''', (tenant, project, existing['id']),
                    ).fetchone()
                    connection.execute('DELETE FROM artifact_cleanup WHERE id=%s AND tenant_id=%s AND project_id=%s', (reservation, tenant, project))
                    return Registration(source=self._source(connection, tenant, project, existing['id']), job=Job.model_validate(job), deduplicated=True)
                item = current_item(connection, tenant, project, playlist_item_id) if playlist_item_id else None
                count = connection.execute('SELECT count(*) AS count FROM sources WHERE tenant_id=%s AND project_id=%s', (tenant, project)).fetchone()['count']
                if count >= 200:
                    raise SourceError('source_limit', 'A project currently supports at most 200 sources.', 429)
                reserved = connection.execute(
                    "SELECT id FROM artifact_cleanup WHERE id=%s AND tenant_id=%s AND project_id=%s AND status='pending' FOR UPDATE",
                    (reservation, tenant, project),
                ).fetchone()
                if not reserved:
                    raise SourceError('upload_expired', 'The upload expired; select the file and try again.', 409)
                # Bounded PUT while holding project/reservation locks closes delete/adoption races.
                self.artifacts.put(key, content)
                connection.execute(
                    '''INSERT INTO sources (tenant_id,project_id,id,filename,authorization_mode,status,
                       processing_version,idempotency_key,content_sha256,request_sha256,retention_class,license_mode)
                       VALUES (%s,%s,%s,%s,%s,'created',%s,%s,%s,%s,'permitted_transcript',%s)''',
                    (tenant, project, source_id, filename, rights.value, PROCESSING_VERSION, idempotency_key,
                     digest, request_hash, 'user_asserted' if rights == AuthorizationMode.LICENSED_CONTENT else 'not_applicable'),
                )
                connection.execute(
                    '''INSERT INTO source_artifacts (tenant_id,project_id,source_id,object_key,content_sha256,byte_count,retention_class)
                       VALUES (%s,%s,%s,%s,%s,%s,'permitted_transcript')''', (tenant, project, source_id, key, digest, len(content)),
                )
                if item:
                    bind_upload(connection, tenant, project, source_id, item)
                job = self._new_job(connection, tenant, project, source_id, actor, 1)
                self.store._record_audit(connection, tenant_id=tenant, project_id=project, actor_user_id=actor, action='source.created')
                connection.execute('DELETE FROM artifact_cleanup WHERE id=%s AND tenant_id=%s AND project_id=%s', (reservation, tenant, project))
                return Registration(source=self._source(connection, tenant, project, source_id), job=job)
        except Exception:
            # If DB is down, the original fifteen-minute reservation remains authoritative.
            try:
                with self.store._connect() as connection:
                    connection.execute('UPDATE artifact_cleanup SET available_at=now() WHERE id=%s AND tenant_id=%s AND project_id=%s', (reservation, tenant, project))
            except Exception:
                pass
            raise

    def command(self, tenant: str, project: UUID, source: UUID, actor: UUID, command: str, key: str) -> Registration:
        with self.store._connect() as connection:
            self._project(connection, tenant, project, actor)
            current = self._source(connection, tenant, project, source)
            if current.job is None:
                raise SourceError('unsupported_source', 'This validation-only source has no retained upload; upload a transcript to use processing controls.', 409)
            receipt = connection.execute(
                'SELECT command,job_id FROM source_commands WHERE tenant_id=%s AND project_id=%s AND source_id=%s AND idempotency_key=%s',
                (tenant, project, source, key),
            ).fetchone()
            if receipt:
                if receipt['command'] != command:
                    raise SourceError('idempotency_conflict', 'This command key was already used for a different action.', 409)
                job = connection.execute('SELECT * FROM processing_jobs WHERE tenant_id=%s AND project_id=%s AND id=%s', (tenant, project, receipt['job_id'])).fetchone()
                return Registration(source=current, job=Job.model_validate(job), deduplicated=True)
            job = current.job
            if command in {'retry', 'reprocess'} and current.kind == 'audio' and job.status in {'failed', 'cancelled', 'succeeded'}:
                raise SourceError('audio_reupload_required', 'The original audio is retired after cancellation or permanent failure; upload it again to transcribe.', 409)
            if command == 'cancel':
                if job.status not in {'pending', 'running', 'retrying', 'cancelled'}:
                    raise SourceError('invalid_state', 'Only unfinished processing can be cancelled.', 409)
                connection.execute(
                    "UPDATE processing_jobs SET status='cancelled',stage='cancelled',continuation_pending=false,cancellation_requested_at=now(),finished_at=now(),updated_at=now(),lease_token=NULL,lease_expires_at=NULL WHERE tenant_id=%s AND project_id=%s AND id=%s",
                    (tenant, project, job.id),
                )
                self._finish_attempt(connection, tenant, project, job.id, 'cancelled', None)
                connection.execute("UPDATE sources SET status='cancelled',updated_at=now() WHERE tenant_id=%s AND project_id=%s AND id=%s", (tenant, project, source))
                retire_audio(connection, tenant, project, source)
            elif command == 'retry':
                if job.status not in {'failed', 'cancelled'}:
                    raise SourceError('invalid_state', 'Only failed or cancelled processing can be retried.', 409)
                if job.max_attempts >= 12:
                    raise SourceError('retry_limit', 'Retry limit reached; upload a new source after correcting the problem.', 429)
                connection.execute(
                    "UPDATE processing_jobs SET status='pending',stage='queued',continuation_pending=false,available_at=now(),max_attempts=max_attempts+3,cancellation_requested_at=NULL,failure_code=NULL,failure_detail=NULL,finished_at=NULL,progress_percent=CASE WHEN total_segments>0 THEN least(85,50+35*processed_segments/total_segments) ELSE 0 END,updated_at=now(),actor_user_id=%s WHERE tenant_id=%s AND project_id=%s AND id=%s",
                    (actor, tenant, project, job.id),
                )
                self.enqueue(connection, tenant, project, source, job.id, job.generation)
                connection.execute("UPDATE sources SET status='created',failure_code=NULL,failure_detail=NULL,updated_at=now() WHERE tenant_id=%s AND project_id=%s AND id=%s", (tenant, project, source))
            elif command == 'reprocess':
                if job.status not in {'succeeded', 'failed', 'cancelled'}:
                    raise SourceError('invalid_state', 'Wait for or cancel the current processing before reprocessing.', 409)
                generation = current.generation + 1
                connection.execute('DELETE FROM embedding_checkpoints WHERE tenant_id=%s AND project_id=%s AND source_id=%s', (tenant, project, source))
                job = self._new_job(connection, tenant, project, source, actor, generation, 'metadata' if current.provider == 'youtube' else 'transcript')
                connection.execute(
                    "UPDATE sources SET generation=%s,status='reprocessing',failure_code=NULL,failure_detail=NULL,updated_at=now() WHERE tenant_id=%s AND project_id=%s AND id=%s",
                    (generation, tenant, project, source),
                )
            else:
                raise ValueError('unsupported source command')
            connection.execute(
                'INSERT INTO source_commands (tenant_id,project_id,source_id,idempotency_key,command,job_id) VALUES (%s,%s,%s,%s,%s,%s)',
                (tenant, project, source, key, command, job.id),
            )
            self.store._record_audit(connection, tenant_id=tenant, project_id=project, actor_user_id=actor, action=f'source.{command}')
            result = self._source(connection, tenant, project, source)
            return Registration(source=result, job=result.job)

    def delete_source(self, tenant: str, project: UUID, source: UUID, actor: UUID) -> Cleanup:
        cleanup_id = uuid4()
        with self.store._connect() as connection:
            self._project(connection, tenant, project, actor)
            self._source(connection, tenant, project, source)
            row = connection.execute(
                'INSERT INTO artifact_cleanup (id,tenant_id,project_id,actor_user_id,object_prefix) VALUES (%s,%s,%s,%s,%s) RETURNING *',
                (cleanup_id, tenant, project, actor, object_prefix(tenant, project, source)),
            ).fetchone()
            connection.execute('DELETE FROM sources WHERE tenant_id=%s AND project_id=%s AND id=%s', (tenant, project, source))
            self.store._record_audit(connection, tenant_id=tenant, project_id=project, actor_user_id=actor, action='source.deleted')
            return Cleanup.model_validate(row)

    def get_cleanup(self, tenant: str, project: UUID, cleanup: UUID, actor: UUID) -> Cleanup:
        # Project may be gone; the ticket is available only to its authenticated initiator.
        with self.store._connect() as connection:
            self.store._require_membership(connection, tenant, actor)
            row = connection.execute(
                'SELECT * FROM artifact_cleanup WHERE tenant_id=%s AND project_id=%s AND id=%s AND actor_user_id=%s',
                (tenant, project, cleanup, actor),
            ).fetchone()
            if not row:
                raise ProjectNotFoundError('cleanup not found')
            return Cleanup.model_validate(row)

    def claim_job(self, tenant: str, project: UUID, source: UUID, job: UUID, generation: int,
                  *, job_types: tuple[str, ...] = ('transcript', 'metadata')) -> dict | None:
        with self.store._connect() as connection:
            try:
                self._project(connection, tenant, project)
                current = self._source(connection, tenant, project, source)
            except ProjectNotFoundError:
                return None
            row = connection.execute(
                '''SELECT * FROM processing_jobs WHERE tenant_id=%s AND project_id=%s AND source_id=%s AND id=%s
                   AND generation=%s AND job_type=ANY(%s) AND status IN ('pending','retrying') AND available_at<=now() FOR UPDATE''',
                (tenant, project, source, job, generation, list(job_types)),
            ).fetchone()
            if not row or current.generation != generation:
                return None
            try:
                self.store._require_membership(connection, tenant, row['actor_user_id'])
            except ProjectNotFoundError:
                self._fail_unclaimed(connection, row, 'authorization_revoked', 'Processing stopped because access was revoked.')
                return None
            if row['attempt_count'] >= row['max_attempts'] and not row['continuation_pending']:
                self._fail_unclaimed(connection, row, 'retry_exhausted', 'Processing attempts exhausted; retry after correcting the problem.')
                return None
            if current.parent_playlist_source_id and row['job_type'] in {'transcript', 'asr'}:
                active = connection.execute(
                    '''SELECT count(*) AS count FROM processing_jobs j JOIN sources s
                       ON s.tenant_id=j.tenant_id AND s.project_id=j.project_id AND s.id=j.source_id
                       WHERE j.tenant_id=%s AND j.project_id=%s AND s.parent_playlist_source_id=%s
                       AND j.job_type IN ('transcript','asr') AND j.status='running' AND j.lease_expires_at>now()''',
                    (tenant, project, current.parent_playlist_source_id),
                ).fetchone()['count']
                if active >= self.settings.playlist_concurrency:
                    connection.execute(
                        "UPDATE processing_jobs SET stage='waiting_capacity',available_at=now()+interval '2 seconds',updated_at=now() WHERE tenant_id=%s AND project_id=%s AND id=%s",
                        (tenant, project, job),
                    )
                    self.enqueue(connection, tenant, project, source, job, generation, delay=2)
                    return None
            token = uuid4()
            claimed = connection.execute(
                '''UPDATE processing_jobs SET status='running',stage='validating',progress_percent=CASE WHEN total_segments>0 THEN greatest(5,progress_percent) ELSE 5 END,
                   attempt_count=attempt_count+CASE WHEN continuation_pending THEN 0 ELSE 1 END,
                   delivery_count=greatest(delivery_count,attempt_count)+1,continuation_pending=false,
                   target_embedding_space=CASE WHEN job_type='transcript' THEN coalesce(target_embedding_space,%s) ELSE NULL END,
                   lease_token=%s,lease_expires_at=now()+make_interval(secs=>%s),
                   started_at=now(),updated_at=now(),failure_code=NULL,failure_detail=NULL
                   WHERE tenant_id=%s AND project_id=%s AND id=%s RETURNING *''',
                (configured_space(self.settings.embedding_provider), token, self.settings.job_lease_seconds, tenant, project, job),
            ).fetchone()
            connection.execute(
                "INSERT INTO processing_attempts (tenant_id,project_id,id,job_id,attempt_number,status) VALUES (%s,%s,%s,%s,%s,'running')",
                (tenant, project, uuid4(), job, claimed['delivery_count']),
            )
            connection.execute("UPDATE sources SET status='validating',updated_at=now() WHERE tenant_id=%s AND project_id=%s AND id=%s", (tenant, project, source))
            artifact = connection.execute('SELECT * FROM source_artifacts WHERE tenant_id=%s AND project_id=%s AND source_id=%s', (tenant, project, source)).fetchone()
            return {**claimed, 'artifact': artifact, 'source': current}

    def register_metadata(self, tenant: str, project: UUID, actor: UUID, *, url: str, rights: AuthorizationMode, idempotency_key: str) -> Registration:
        with self.store._connect() as connection:
            self._project(connection, tenant, project, actor)
        normalized = YouTubeAdapter().normalize(url)
        if not self.settings.youtube_api_key:
            raise SourceError('provider_not_configured', 'Set a server-side YouTube Data API key to import metadata; transcript uploads work without it.', 503)
        request_hash = hashlib.sha256(json.dumps([normalized.kind, normalized.canonical_id, rights.value]).encode()).hexdigest()
        with self.store._connect() as connection:
            if self._project(connection, tenant, project, actor)['status'] != 'active':
                raise SourceError('project_archived', 'Restore this project before adding sources.', 409)
            existing = connection.execute('SELECT id,request_sha256 FROM sources WHERE tenant_id=%s AND project_id=%s AND idempotency_key=%s', (tenant, project, idempotency_key)).fetchone()
            if existing:
                if existing['request_sha256'] != request_hash:
                    raise SourceError('idempotency_conflict', 'This key was already used for different input.', 409)
                current = self._source(connection, tenant, project, existing['id'])
                original = connection.execute('SELECT * FROM processing_jobs WHERE tenant_id=%s AND project_id=%s AND source_id=%s ORDER BY generation,created_at LIMIT 1', (tenant, project, current.id)).fetchone()
                return Registration(source=current, job=Job.model_validate(original), deduplicated=True)
            count = connection.execute('SELECT count(*) AS count FROM sources WHERE tenant_id=%s AND project_id=%s', (tenant, project)).fetchone()['count']
            if count >= 200:
                raise SourceError('source_limit', 'A project currently supports at most 200 sources.', 429)
            source = uuid4()
            connection.execute(
                '''INSERT INTO sources (tenant_id,project_id,id,filename,kind,provider,canonical_external_id,
                   authorization_mode,status,processing_version,idempotency_key,request_sha256,metadata)
                   VALUES (%s,%s,%s,%s,%s,'youtube',%s,%s,'created','youtube-metadata-v1',%s,%s,%s)''',
                (tenant, project, source, normalized.title, normalized.kind, normalized.canonical_id, rights.value, idempotency_key, request_hash, Jsonb(normalized.metadata)),
            )
            job = self._new_job(connection, tenant, project, source, actor, 1, 'metadata')
            self.store._record_audit(connection, tenant_id=tenant, project_id=project, actor_user_id=actor, action='source.created')
            return Registration(source=self._source(connection, tenant, project, source), job=job)

    def complete_metadata(self, claim: dict, metadata: dict, duration_ms: int) -> bool:
        tenant, project, source, job = (claim[key] for key in ('tenant_id', 'project_id', 'source_id', 'id'))
        with self.store._connect() as connection:
            if not self._fenced(connection, claim):
                return False
            if claim['source'].kind == 'youtube_playlist':
                store_snapshot(connection, tenant, project, source, claim['generation'], metadata)
            connection.execute(
                '''INSERT INTO processing_versions (tenant_id,project_id,source_id,generation,processing_version,
                   embedding_provider,embedding_model,embedding_dimensions,embedding_space) VALUES (%s,%s,%s,%s,%s,'none','none',0,NULL)
                   ON CONFLICT DO NOTHING''', (tenant, project, source, claim['generation'], f"youtube-metadata-v1:g{claim['generation']}"),
            )
            connection.execute(
                "UPDATE sources SET filename=%s,status='metadata_ready',metadata=%s,processing_version=%s,failure_code=NULL,failure_detail=NULL,updated_at=now() WHERE tenant_id=%s AND project_id=%s AND id=%s",
                (metadata['title'], Jsonb(metadata), f"youtube-metadata-v1:g{claim['generation']}", tenant, project, source),
            )
            connection.execute(
                "UPDATE processing_jobs SET status='succeeded',stage='metadata_ready',progress_percent=100,lease_token=NULL,lease_expires_at=NULL,finished_at=now(),updated_at=now() WHERE tenant_id=%s AND project_id=%s AND id=%s", (tenant, project, job),
            )
            self._finish_attempt(connection, tenant, project, job, 'succeeded', None)
            connection.execute(
                '''INSERT INTO usage_events (tenant_id,project_id,source_id,job_id,generation,provider,model,input_characters,segment_count,duration_ms,embedding_space)
                   VALUES (%s,%s,%s,%s,%s,'youtube','data-api-v3',0,0,%s,NULL) ON CONFLICT DO NOTHING''',
                (tenant, project, source, job, claim['generation'], duration_ms),
            )
            return True

    def _fenced(self, connection, claim: dict) -> bool:
        tenant, project, source, job = (claim[key] for key in ('tenant_id', 'project_id', 'source_id', 'id'))
        try:
            self._project(connection, tenant, project, claim['actor_user_id'])
        except ProjectNotFoundError:
            return False
        row = connection.execute(
            '''SELECT j.id FROM processing_jobs j JOIN sources s
               ON s.tenant_id=j.tenant_id AND s.project_id=j.project_id AND s.id=j.source_id
               WHERE j.tenant_id=%s AND j.project_id=%s AND j.source_id=%s AND j.id=%s
               AND j.status='running' AND j.lease_token=%s AND j.lease_expires_at>now()
               AND j.generation=%s AND s.generation=j.generation AND s.deleted_at IS NULL
               AND NOT EXISTS (SELECT 1 FROM audio_inputs a WHERE a.tenant_id=j.tenant_id AND a.project_id=j.project_id
                   AND a.job_id=j.id AND a.source_id=j.source_id AND a.generation=j.generation
                   AND (a.cleanup_id IS NOT NULL OR a.expires_at<=now())) FOR UPDATE OF j''',
            (tenant, project, source, job, claim['lease_token'], claim['generation']),
        ).fetchone()
        return row is not None

    def stage(self, claim: dict, stage: str, progress: int) -> bool:
        with self.store._connect() as connection:
            if not self._fenced(connection, claim):
                return False
            connection.execute(
                'UPDATE processing_jobs SET stage=%s,progress_percent=greatest(progress_percent,%s),updated_at=now() WHERE tenant_id=%s AND project_id=%s AND id=%s',
                (stage, progress, claim['tenant_id'], claim['project_id'], claim['id']),
            )
            connection.execute(
                'UPDATE sources SET status=%s,updated_at=now() WHERE tenant_id=%s AND project_id=%s AND id=%s',
                ('indexing' if stage == 'indexing' else 'processing', claim['tenant_id'], claim['project_id'], claim['source_id']),
            )
            return True

    @staticmethod
    def _finish_attempt(connection, tenant: str, project: UUID, job: UUID, status: str, failure: str | None):
        connection.execute(
            '''UPDATE processing_attempts SET status=%s,failure_code=%s,finished_at=now(),
               duration_ms=greatest(0,extract(epoch FROM now()-started_at)*1000)::bigint
               WHERE tenant_id=%s AND project_id=%s AND job_id=%s AND status='running' ''',
            (status, failure, tenant, project, job),
        )

    def _fail_unclaimed(self, connection, claim: dict, code: str, detail: str):
        tenant, project, source, job = (claim[key] for key in ('tenant_id', 'project_id', 'source_id', 'id'))
        connection.execute(
            "UPDATE processing_jobs SET status='failed',stage='failed',continuation_pending=false,failure_code=%s,failure_detail=%s,finished_at=now(),updated_at=now(),lease_token=NULL,lease_expires_at=NULL WHERE tenant_id=%s AND project_id=%s AND id=%s",
            (code, detail, tenant, project, job),
        )
        connection.execute("UPDATE sources SET status='failed',failure_code=%s,failure_detail=%s,updated_at=now() WHERE tenant_id=%s AND project_id=%s AND id=%s", (code, detail, tenant, project, source))
        retire_audio(connection, tenant, project, source, job)

    def fail(self, claim: dict, error: SourceError) -> bool:
        import random
        with self.store._connect() as connection:
            if not self._fenced(connection, claim):
                return False
            self._fail_claim(connection, claim, error, random.randint(0, 3))
            return True

    def _fail_claim(self, connection, claim: dict, error: SourceError, jitter: int):
        tenant, project, source, job = (claim[key] for key in ('tenant_id', 'project_id', 'source_id', 'id'))
        self._finish_attempt(connection, tenant, project, job, 'failed', error.code)
        if error.transient and claim['attempt_count'] < claim['max_attempts']:
            delay = min(60, 2 ** claim['attempt_count']) + jitter
            connection.execute(
                "UPDATE processing_jobs SET status='retrying',stage='waiting_retry',continuation_pending=false,failure_code=%s,failure_detail=%s,lease_token=NULL,lease_expires_at=NULL,available_at=now()+make_interval(secs=>%s),updated_at=now() WHERE tenant_id=%s AND project_id=%s AND id=%s",
                (error.code, error.detail, delay, tenant, project, job),
            )
            self.enqueue(connection, tenant, project, source, job, claim['generation'], delay)
        else:
            self._fail_unclaimed(connection, claim, error.code, error.detail)

    def complete(self, claim: dict, segments: list[EvidenceSegment], provenance: list[tuple[int, int]], provider: str, model: str, duration_ms: int,
                 *, embedding_space: str = HASH_SPACE, dimensions: int = 64, model_digest: str | None = None, input_tokens: int | None = None) -> bool:
        tenant, project, source, job = (claim[key] for key in ('tenant_id', 'project_id', 'source_id', 'id'))
        generation = claim['generation']
        if not segments or any(segment.embedding_space != embedding_space or len(segment.embedding) != dimensions
                               or segment.tenant_id != tenant or segment.project_id != project or segment.source_id != source for segment in segments):
            raise SourceError('invalid_embeddings', 'The indexing evidence could not be validated.', 503)
        with self.store._connect() as connection:
            if not self._fenced(connection, claim):
                return False
            version = f'{PROCESSING_VERSION}:g{generation}'
            connection.execute(
                '''INSERT INTO processing_versions (tenant_id,project_id,source_id,generation,processing_version,
                   embedding_provider,embedding_model,embedding_dimensions,embedding_space,embedding_model_digest)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT DO NOTHING''', (tenant, project, source, generation, version, provider, model, dimensions, embedding_space, model_digest),
            )
            for segment, (cue_start, cue_end) in zip(segments, provenance, strict=True):
                connection.execute(
                    '''INSERT INTO content_segments (tenant_id,project_id,id,source_id,modality,start_ms,end_ms,text,
                       embedding,processing_version,generation,cue_start,cue_end,embedding_space)
                       VALUES (%s,%s,%s,%s,'transcript',%s,%s,%s,%s::vector,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING''',
                    (tenant, project, segment.id, source, segment.start_ms, segment.end_ms, segment.text,
                     self.store._vector_literal(segment.embedding), version, generation, cue_start, cue_end, embedding_space),
                )
            self._activate(connection, claim, provider, model, len(segments), sum(len(segment.text) for segment in segments), duration_ms,
                           embedding_space=embedding_space, model_digest=model_digest, input_tokens=input_tokens)
            return True

    def _activate(self, connection, claim: dict, provider: str, model: str, segment_count: int, characters: int, duration_ms: int,
                  *, embedding_space: str, model_digest: str | None, input_tokens: int | None, cumulative: bool = False):
        tenant, project, source, job = (claim[key] for key in ('tenant_id', 'project_id', 'source_id', 'id'))
        generation, version = claim['generation'], f"{PROCESSING_VERSION}:g{claim['generation']}"
        connection.execute(
            '''UPDATE processing_versions v SET asr_job_id=a.asr_job_id FROM source_artifacts a
               WHERE a.tenant_id=v.tenant_id AND a.project_id=v.project_id AND a.source_id=v.source_id
               AND v.tenant_id=%s AND v.project_id=%s AND v.source_id=%s AND v.generation=%s''',
            (tenant, project, source, generation),
        )
        connection.execute(
            "UPDATE sources SET status='ready',active_generation=%s,active_embedding_space=%s,processing_version=%s,segment_count=%s,failure_code=NULL,failure_detail=NULL,updated_at=now() WHERE tenant_id=%s AND project_id=%s AND id=%s",
            (generation, embedding_space, version, segment_count, tenant, project, source),
        )
        connection.execute(
            "UPDATE processing_jobs SET status='succeeded',stage='ready',progress_percent=100,continuation_pending=false,lease_token=NULL,lease_expires_at=NULL,finished_at=now(),updated_at=now() WHERE tenant_id=%s AND project_id=%s AND id=%s", (tenant, project, job),
        )
        self._finish_attempt(connection, tenant, project, job, 'succeeded', None)
        if cumulative:
            duration_ms = connection.execute('SELECT coalesce(sum(duration_ms),0) AS duration FROM processing_attempts WHERE tenant_id=%s AND project_id=%s AND job_id=%s', (tenant, project, job)).fetchone()['duration']
        connection.execute(
            '''INSERT INTO usage_events (tenant_id,project_id,source_id,job_id,generation,provider,model,input_characters,segment_count,duration_ms,
               embedding_space,model_digest,input_tokens) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING''',
            (tenant, project, source, job, generation, provider, model, characters, segment_count, duration_ms,
             embedding_space,model_digest,input_tokens),
        )

    def recover_leases(self) -> int:
        # Global scheduler enumerates IDs only; every subsequent operation uses full scope.
        with self.store._connect() as connection:
            expired = connection.execute("SELECT tenant_id,project_id,source_id,id FROM processing_jobs WHERE status='running' AND lease_expires_at<now() ORDER BY lease_expires_at LIMIT 50").fetchall()
        recovered = 0
        for item in expired:
            with self.store._connect() as connection:
                try:
                    self._project(connection, item['tenant_id'], item['project_id'])
                except ProjectNotFoundError:
                    continue
                row = connection.execute(
                    "SELECT * FROM processing_jobs WHERE tenant_id=%s AND project_id=%s AND source_id=%s AND id=%s AND status='running' AND lease_expires_at<now() FOR UPDATE",
                    (item['tenant_id'], item['project_id'], item['source_id'], item['id']),
                ).fetchone()
                if row:
                    self._fail_claim(connection, row, SourceError('worker_lost', 'The worker stopped; processing will retry or can be retried manually.', transient=True), 0)
                    recovered += 1
        return recovered

    def render_metrics(self) -> str:
        # Aggregate operational metrics intentionally have system scope and no content/ID labels.
        with self.store._connect() as connection:
            jobs = connection.execute('SELECT status,count(*) AS count FROM processing_jobs GROUP BY status').fetchall()
            attempts = connection.execute('SELECT status,count(*) AS count,coalesce(sum(duration_ms),0) AS duration FROM processing_attempts GROUP BY status').fetchall()
            pending = connection.execute('SELECT count(*) AS count FROM outbox_events WHERE sent_at IS NULL').fetchone()['count']
            cleanup = connection.execute('SELECT status,count(*) AS count FROM artifact_cleanup GROUP BY status').fetchall()
            waiting = connection.execute("SELECT count(*) AS count FROM processing_jobs WHERE stage='waiting_capacity' AND status IN ('pending','retrying')").fetchone()['count']
            continuations = connection.execute("SELECT count(*) AS count FROM processing_jobs WHERE stage='waiting_continuation' AND status='pending'").fetchone()['count']
            checkpoints = connection.execute('SELECT count(*) AS count FROM embedding_checkpoints').fetchone()['count']
            asr = connection.execute(
                '''SELECT coalesce(sum(next_window),0) AS windows,coalesce(sum(completed_frames),0) AS frames,
                          coalesce(sum(model_duration_ms),0) AS duration FROM asr_runs''',
            ).fetchone()
            visual = connection.execute(
                '''SELECT count(*) FILTER (WHERE saved_at IS NULL) AS waiting,
                          count(*) FILTER (WHERE saved_at IS NOT NULL) AS saved,
                          coalesce(sum(saved_frames),0) AS frames,coalesce(sum(image_bytes),0) AS bytes,
                          coalesce(sum(ocr_characters),0) AS characters FROM visual_runs''',
            ).fetchone()
            originals = connection.execute(
                '''SELECT count(*) FILTER (WHERE cleanup_id IS NULL AND expires_at>now()) AS available,
                          count(*) FILTER (WHERE cleanup_id IS NULL AND expires_at<=now()) AS expired,
                          count(*) FILTER (WHERE cleanup_id IS NOT NULL AND deleted_at IS NULL) AS cleanup_pending,
                          count(*) FILTER (WHERE deleted_at IS NOT NULL) AS deleted FROM audio_inputs''',
            ).fetchone()
        lines = ['# TYPE tutorial_processing_jobs gauge', '# TYPE tutorial_retained_processing_attempts gauge',
                 '# TYPE tutorial_retained_attempt_duration_seconds gauge', '# TYPE tutorial_outbox_pending gauge',
                 '# TYPE tutorial_artifact_cleanup gauge', '# TYPE tutorial_embedding_checkpoint_segments gauge',
                 '# TYPE tutorial_embedding_continuations_pending gauge']
        lines.append(f'tutorial_embedding_checkpoint_segments {checkpoints}')
        lines.append(f'tutorial_embedding_continuations_pending {continuations}')
        lines.extend(['# TYPE tutorial_asr_saved_windows gauge', f'tutorial_asr_saved_windows {asr["windows"]}',
                      '# TYPE tutorial_asr_staged_input_frames gauge', f'tutorial_asr_staged_input_frames {asr["frames"]}',
                      '# TYPE tutorial_asr_staged_model_duration_seconds gauge',
                      f'tutorial_asr_staged_model_duration_seconds {float(asr["duration"])/1000}'])
        lines.append('# TYPE tutorial_audio_originals gauge')
        lines.extend(['# TYPE tutorial_visual_runs gauge',
                      f'tutorial_visual_runs{{status="waiting"}} {visual["waiting"]}',
                      f'tutorial_visual_runs{{status="saved"}} {visual["saved"]}',
                      '# TYPE tutorial_visual_checkpoint_frames gauge', f'tutorial_visual_checkpoint_frames {visual["frames"]}',
                      '# TYPE tutorial_visual_checkpoint_image_bytes gauge', f'tutorial_visual_checkpoint_image_bytes {visual["bytes"]}',
                      '# TYPE tutorial_visual_checkpoint_ocr_characters gauge', f'tutorial_visual_checkpoint_ocr_characters {visual["characters"]}'])
        for status in ('available', 'expired', 'cleanup_pending', 'deleted'):
            lines.append(f'tutorial_audio_originals{{status="{status}"}} {originals[status]}')
        for row in jobs:
            lines.append(f'tutorial_processing_jobs{{status="{row["status"]}"}} {row["count"]}')
        for row in attempts:
            lines.append(f'tutorial_retained_processing_attempts{{status="{row["status"]}"}} {row["count"]}')
            lines.append(f'tutorial_retained_attempt_duration_seconds{{status="{row["status"]}"}} {float(row["duration"])/1000}')
        for row in cleanup:
            lines.append(f'tutorial_artifact_cleanup{{status="{row["status"]}"}} {row["count"]}')
        lines.append(f'tutorial_outbox_pending {pending}')
        lines.append('# TYPE tutorial_playlist_jobs_waiting_capacity gauge')
        lines.append(f'tutorial_playlist_jobs_waiting_capacity {waiting}')
        return '\n'.join(lines) + '\n'
