"""Private authorized MP4 registration, raw lifecycle and atomic prepared result."""
import hashlib
import json
import logging
import unicodedata
from uuid import uuid4

from pydantic import ValidationError
from psycopg.types.json import Jsonb

from ..artifacts.storage import object_prefix
from ..artifacts.video import retire_video, video_prefix
from ..models import AuthorizationMode
from ..store import ProjectNotFoundError
from ..vision.checkpoints import CHECKPOINT_VERSION, VisualCheckpoints
from ..vision.contracts import VisualIdentity
from ..vision.media import MAX_VIDEO_BYTES, validate_mp4
from ..vision import workflow
from .contracts import Job, Registration, SourceCommand, SourceError
from .media import MediaRepository

LOGGER = logging.getLogger('tutorial_workspace.jobs')


class VideoRepository:
    def __init__(self, repository):
        self.repository = repository
        self.reservations = MediaRepository(repository)  # Existing write-ahead cleanup primitives only.

    def register(self, tenant, project, actor, *, filename, content, rights, language, idempotency_key, auto_process=False):
        if type(auto_process) is not bool:
            raise SourceError('invalid_video_workflow', 'Select an explicit video processing mode.')
        try:
            validate_mp4(content)
            name = filename.rsplit('/', 1)[-1].rsplit('\\', 1)[-1]
            if (not 1 <= len(name) <= 255 or not name.lower().endswith('.mp4')
                    or any(unicodedata.category(c) in {'Cc', 'Cs'} for c in name)):
                raise ValueError()
            SourceCommand(idempotency_key=idempotency_key)
        except (ValueError, AttributeError, TypeError):
            raise SourceError('invalid_video_input', 'Use an authorized supported MP4 of at most 100 MB and a valid request key.') from None
        if not isinstance(rights, AuthorizationMode):
            raise SourceError('rights_required', 'Confirm permission to process the video and retain selected frames/OCR.')
        if not isinstance(language, str) or language not in {'en', 'tr', 'en+tr'}:
            raise SourceError('invalid_visual_language', 'Select English, Turkish or experimental combined OCR.')
        digest = hashlib.sha256(content).hexdigest()
        request_fields = ['video-visual-v1', name, digest, rights.value, language]
        if auto_process: request_fields.append(workflow.VERSION)
        request_hash = hashlib.sha256(json.dumps(request_fields).encode()).hexdigest()
        source, reservation = uuid4(), uuid4()
        repo, reservations = self.repository, self.reservations
        key = video_prefix(tenant, project, source, 1) + 'input.mp4'
        with repo.store._connect() as connection:
            repo._project(connection, tenant, project, actor)
            reservations._reserve(connection, reservation, tenant, project, actor, object_prefix(tenant, project, source))
        adopted = False
        try:
            with repo.store._connect() as connection:
                if repo._project(connection, tenant, project, actor)['status'] != 'active':
                    raise SourceError('project_archived', 'Restore the project before adding video.', 409)
                existing = connection.execute(
                    'SELECT id,request_sha256 FROM sources WHERE tenant_id=%s AND project_id=%s AND idempotency_key=%s',
                    (tenant, project, idempotency_key),
                ).fetchone()
                if existing:
                    if existing['request_sha256'] != request_hash:
                        raise SourceError('idempotency_conflict', 'This request key was already used for different input.', 409)
                    original = connection.execute(
                        '''SELECT * FROM processing_jobs WHERE tenant_id=%s AND project_id=%s AND source_id=%s
                           AND job_type='visual' ORDER BY generation,created_at LIMIT 1''', (tenant, project, existing['id']),
                    ).fetchone()
                    if original is None:
                        raise SourceError('invalid_video_state', 'The original video job is unavailable.', 409)
                    connection.execute('DELETE FROM artifact_cleanup WHERE tenant_id=%s AND project_id=%s AND id=%s',
                                       (tenant, project, reservation))
                    adopted = True
                    return Registration(source=repo._source(connection, tenant, project, existing['id']),
                                        job=Job.model_validate(original), deduplicated=True)
                if connection.execute('SELECT count(*) AS n FROM sources WHERE tenant_id=%s AND project_id=%s',
                                      (tenant, project)).fetchone()['n'] >= 200:
                    raise SourceError('source_limit', 'A project currently supports at most 200 sources.', 429)
                if not reservations._reservation(connection, reservation, tenant, project):
                    raise SourceError('upload_expired', 'The upload reservation expired; try again.', 409)
                repo.artifacts.put(key, content)
                repo._project(connection, tenant, project, actor)
                if connection.execute('SELECT 1 FROM memberships WHERE tenant_id=%s AND user_id=%s FOR KEY SHARE',
                                      (tenant, actor)).fetchone() is None:
                    raise ProjectNotFoundError('project not found')
                connection.execute(
                    '''INSERT INTO sources (tenant_id,project_id,id,filename,kind,provider,authorization_mode,status,
                       processing_version,idempotency_key,content_sha256,request_sha256,retention_class,license_mode,metadata)
                       VALUES (%s,%s,%s,%s,'video','upload',%s,'created',%s,%s,%s,%s,'temporary_video',%s,%s)''',
                    (tenant, project, source, name, rights.value, CHECKPOINT_VERSION, idempotency_key, digest, request_hash,
                     'user_asserted' if rights == AuthorizationMode.LICENSED_CONTENT else 'not_applicable',
                     Jsonb({'input_kind': 'video', 'machine_generated': True, 'requested_language': language,
                            'visual_quality_approval': 'not_established'})),
                )
                job = repo._new_job(connection, tenant, project, source, actor, 1, 'visual')
                connection.execute(
                    '''INSERT INTO video_inputs (tenant_id,project_id,job_id,source_id,generation,actor_user_id,
                       object_key,content_sha256,byte_count,requested_language,expires_at)
                       SELECT tenant_id,project_id,id,source_id,generation,actor_user_id,%s,%s,%s,%s,created_at+interval '1 hour'
                       FROM processing_jobs WHERE tenant_id=%s AND project_id=%s AND id=%s AND source_id=%s AND generation=1''',
                    (key, digest, len(content), language, tenant, project, job.id, source),
                )
                if auto_process:
                    workflow.register(repo, connection, tenant, project, source, job, actor)
                repo.store._record_audit(connection, tenant_id=tenant, project_id=project, actor_user_id=actor, action='source.created')
                connection.execute('DELETE FROM artifact_cleanup WHERE tenant_id=%s AND project_id=%s AND id=%s',
                                   (tenant, project, reservation))
                adopted = True
                return Registration(source=repo._source(connection, tenant, project, source), job=job)
        finally:
            if not adopted:
                reservations._due(reservation, tenant, project)

    def read_original(self, claim):
        repo = self.repository
        with repo.store._connect() as connection:
            if VisualCheckpoints(repo)._live(connection, claim) is None:
                return None
            original = connection.execute(
                '''SELECT v.*,s.content_sha256 AS source_sha,s.kind,j.job_type,j.actor_user_id AS job_actor
                   FROM video_inputs v JOIN sources s
                   ON s.tenant_id=v.tenant_id AND s.project_id=v.project_id AND s.id=v.source_id
                   JOIN processing_jobs j ON j.tenant_id=v.tenant_id AND j.project_id=v.project_id AND j.id=v.job_id
                   WHERE v.tenant_id=%s AND v.project_id=%s AND v.job_id=%s AND v.source_id=%s AND v.generation=%s''',
                VisualCheckpoints._scope(claim),
            ).fetchone()
            if original is None or original['deleted_at'] is not None:
                raise SourceError('video_reupload_required', 'The original video is no longer available; upload it again.', 409)
            expected = video_prefix(claim['tenant_id'], claim['project_id'], claim['source_id'], claim['generation']) + 'input.mp4'
            if (original['object_key'] != expected or original['content_sha256'] != original['source_sha']
                    or original['kind'] != 'video' or original['job_type'] != 'visual'
                    or original['actor_user_id'] != claim['actor_user_id'] or original['job_actor'] != claim['actor_user_id']):
                raise SourceError('artifact_integrity', 'The original video record failed integrity verification.')
        data = repo.artifacts.get(expected, MAX_VIDEO_BYTES)
        if (not isinstance(data, bytes) or len(data) != original['byte_count']
                or hashlib.sha256(data).hexdigest() != original['content_sha256']):
            raise SourceError('artifact_integrity', 'The original video failed integrity verification.')
        try:
            validate_mp4(data)
        except ValueError:
            raise SourceError('artifact_integrity', 'The stored video container failed integrity verification.') from None
        with repo.store._connect() as connection:
            if VisualCheckpoints(repo)._live(connection, claim) is None:
                return None
        return data, original

    def checkpoint_state(self, claim):
        with self.repository.store._connect() as connection:
            checkpoints = VisualCheckpoints(self.repository)
            live = checkpoints._live(connection, claim)
            if live is None:
                return None
            row = connection.execute(
                '''SELECT identity FROM visual_runs WHERE tenant_id=%s AND project_id=%s AND job_id=%s
                   AND source_id=%s AND generation=%s''', VisualCheckpoints._scope(claim),
            ).fetchone()
            if row is None:
                return None
            try:
                run = checkpoints._run(connection, claim, live)
                return VisualIdentity.model_validate(run['identity']), run['saved_at'] is not None
            except ValidationError:
                raise SourceError('visual_profile_changed', 'Restore the pinned OCR profile or upload again.', 409) from None

    def prepare(self, claim):
        repo, checkpoints = self.repository, VisualCheckpoints(self.repository)
        tenant, project, job, source, generation = checkpoints._scope(claim)
        with repo.store._connect() as connection:
            live = checkpoints._live(connection, claim)
            if live is None:
                return False
            snapshot = checkpoints._load(connection, claim)
            if snapshot is None:
                return False
            run = checkpoints._run(connection, claim, live)
            if run['prepared_at'] is not None:
                raise SourceError('invalid_video_state', 'This visual result was already prepared.', 409)
            original = connection.execute(
                '''SELECT byte_count,requested_language,object_key,content_sha256,deleted_at FROM video_inputs WHERE tenant_id=%s AND project_id=%s AND job_id=%s
                   AND source_id=%s AND generation=%s AND actor_user_id=%s AND cleanup_id IS NULL
                   AND expires_at= %s''', (*checkpoints._scope(claim), claim['actor_user_id'], live['expires_at']),
            ).fetchone()
            if (original is None or original['byte_count'] != run['input_bytes']
                    or original['requested_language'] != snapshot.identity['language']
                    or original['deleted_at'] is not None or original['content_sha256'] != run['input_sha256']
                    or original['object_key'] != video_prefix(tenant, project, source, generation) + 'input.mp4'):
                raise SourceError('artifact_integrity', 'The prepared video input failed integrity verification.')
            repo._finish_attempt(connection, tenant, project, job, 'succeeded', None)
            duration = connection.execute(
                '''SELECT coalesce(sum(duration_ms),0)::bigint AS duration FROM processing_attempts
                   WHERE tenant_id=%s AND project_id=%s AND job_id=%s''', (tenant, project, job),
            ).fetchone()['duration']
            connection.execute(
                '''INSERT INTO usage_events (tenant_id,project_id,source_id,job_id,generation,provider,model,
                   input_characters,segment_count,duration_ms,embedding_space,input_video_bytes,selected_frame_count)
                   VALUES (%s,%s,%s,%s,%s,'local-ffmpeg-tesseract',%s,%s,0,%s,NULL,%s,%s)''',
                (tenant, project, source, job, generation, run['profile'], run['ocr_characters'], duration,
                 run['input_bytes'], len(snapshot.frames)),
            )
            connection.execute(
                '''UPDATE visual_runs SET prepared_at=clock_timestamp() WHERE tenant_id=%s AND project_id=%s
                   AND job_id=%s AND source_id=%s AND generation=%s''', checkpoints._scope(claim),
            )
            connection.execute(
                '''UPDATE sources SET status='metadata_ready',retention_class='permitted_visual_staging',metadata=metadata || %s,
                   updated_at=now() WHERE tenant_id=%s AND project_id=%s AND id=%s''',
                (Jsonb({'visual_prepared': True, 'visual_job_id': str(job), 'visual_profile': run['profile']}), tenant, project, source),
            )
            connection.execute(
                '''UPDATE processing_jobs SET status='succeeded',stage='visual_prepared',progress_percent=100,
                   lease_token=NULL,lease_expires_at=NULL,finished_at=now(),updated_at=now()
                   WHERE tenant_id=%s AND project_id=%s AND id=%s''', (tenant, project, job),
            )
            retire_video(connection, tenant, project, source, job)
            next_job = workflow.after_preparation(repo, connection, claim)
            if not connection.execute('SELECT clock_timestamp()<least(%s,%s) AS valid',
                                      (live['lease_until'], live['expires_at'])).fetchone()['valid']:
                connection.rollback()
                return False
        if next_job is not None:
            LOGGER.info(json.dumps({'event': 'video_gallery_queued', 'tenant_id': tenant,
                'project_id': str(project), 'job_id': str(job), 'next_job_id': str(next_job.id)}))
        return True


def retire_unusable_video(repository):
    with repository.store._connect() as connection:
        due = connection.execute(
            '''SELECT v.tenant_id,v.project_id,v.source_id,v.job_id FROM video_inputs v
               JOIN processing_jobs j ON j.tenant_id=v.tenant_id AND j.project_id=v.project_id AND j.id=v.job_id
               WHERE v.cleanup_id IS NULL AND (v.expires_at<=clock_timestamp() OR j.status IN ('succeeded','failed','cancelled')
                 OR NOT EXISTS (SELECT 1 FROM memberships m WHERE m.tenant_id=v.tenant_id AND m.user_id=j.actor_user_id))
               ORDER BY v.expires_at LIMIT 50''',
        ).fetchall()
    retired = 0
    for item in due:
        with repository.store._connect() as connection:
            try:
                repository._project(connection, item['tenant_id'], item['project_id'])
            except ProjectNotFoundError:
                continue
            row = connection.execute(
                '''SELECT j.*,v.expires_at<=clock_timestamp() AS expired,
                     NOT EXISTS (SELECT 1 FROM memberships m WHERE m.tenant_id=j.tenant_id AND m.user_id=j.actor_user_id) AS revoked
                   FROM video_inputs v JOIN processing_jobs j
                   ON j.tenant_id=v.tenant_id AND j.project_id=v.project_id AND j.id=v.job_id
                   WHERE v.tenant_id=%s AND v.project_id=%s AND v.source_id=%s AND v.job_id=%s
                   AND v.cleanup_id IS NULL FOR UPDATE OF j,v''',
                (item['tenant_id'], item['project_id'], item['source_id'], item['job_id']),
            ).fetchone()
            if row is None:
                continue
            terminal = row['status'] in {'succeeded', 'failed', 'cancelled'}
            if not (row['expired'] or row['revoked'] or terminal):
                continue
            if not terminal:
                code = 'authorization_revoked' if row['revoked'] else 'video_expired'
                repository._finish_attempt(connection, row['tenant_id'], row['project_id'], row['id'], 'failed', code)
                repository._fail_unclaimed(connection, row, code, 'The temporary video expired or access was revoked; upload again if authorized.')
                retired += 1
            else:
                retired += retire_video(connection, row['tenant_id'], row['project_id'], row['source_id'], row['id'])
    return retired
