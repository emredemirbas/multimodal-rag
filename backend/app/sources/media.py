"""Private WAV registration/lifecycle and fenced derived-object adoption."""
import hashlib
import json
from uuid import UUID, uuid4

from pydantic import ValidationError
from psycopg.types.json import Jsonb

from ..artifacts.audio import audio_prefix, retire_audio
from ..artifacts.storage import object_prefix
from ..asr.checkpoints import AsrCheckpoints
from ..asr.contracts import Language
from ..asr.profile import MODEL, PROVIDER
from ..asr.transcript import ASSEMBLY_VERSION
from ..asr.wav import MAX_WAV_BYTES, validate_wav
from ..models import AuthorizationMode
from ..store import ProjectNotFoundError
from .contracts import Job, Registration, SourceCommand, SourceError
from .repository import SourceRepository


class MediaRepository:
    def __init__(self, repository: SourceRepository):
        self.repository = repository

    def _due(self, reservation, tenant, project):
        try:
            with self.repository.store._connect() as connection:
                connection.execute('UPDATE artifact_cleanup SET available_at=now() WHERE id=%s AND tenant_id=%s AND project_id=%s',
                                   (reservation, tenant, project))
        except Exception:
            pass  # The committed fifteen-minute write-ahead reservation survives DB loss.

    @staticmethod
    def _reserve(connection, reservation, tenant, project, actor, prefix):
        connection.execute(
            '''INSERT INTO artifact_cleanup (id,tenant_id,project_id,actor_user_id,object_prefix,available_at)
               VALUES (%s,%s,%s,%s,%s,now()+interval '15 minutes')''',
            (reservation, tenant, project, actor, prefix),
        )

    @staticmethod
    def _reservation(connection, reservation, tenant, project):
        return connection.execute(
            "SELECT id FROM artifact_cleanup WHERE id=%s AND tenant_id=%s AND project_id=%s AND status='pending' FOR UPDATE",
            (reservation, tenant, project),
        ).fetchone()

    def register(self, tenant: str, project: UUID, actor: UUID, *, filename: str, content: bytes,
                 rights: AuthorizationMode, language: Language, idempotency_key: str) -> Registration:
        info = validate_wav(filename, content)
        if not isinstance(rights, AuthorizationMode):
            raise SourceError('rights_required', 'Confirm that you own or are authorized to process the audio.')
        if not isinstance(language, str) or language not in {'auto', 'en', 'tr'}:
            raise SourceError('invalid_asr_language', 'Select automatic, English or Turkish speech recognition.')
        try:
            SourceCommand(idempotency_key=idempotency_key)
        except ValidationError:
            raise SourceError('invalid_idempotency_key', 'Use a valid upload request key.') from None
        digest = hashlib.sha256(content).hexdigest()
        request_hash = hashlib.sha256(json.dumps(['audio-asr-v1', info.filename, digest, rights.value, language]).encode()).hexdigest()
        source, reservation = uuid4(), uuid4()
        prefix = object_prefix(tenant, project, source)
        key = audio_prefix(tenant, project, source, 1) + 'input.wav'
        repo = self.repository
        with repo.store._connect() as connection:
            repo._project(connection, tenant, project, actor)
            self._reserve(connection, reservation, tenant, project, actor, prefix)
        adopted = False
        try:
            with repo.store._connect() as connection:
                if repo._project(connection, tenant, project, actor)['status'] != 'active':
                    raise SourceError('project_archived', 'Restore the project before adding audio.', 409)
                existing = connection.execute(
                    'SELECT id,request_sha256 FROM sources WHERE tenant_id=%s AND project_id=%s AND idempotency_key=%s',
                    (tenant, project, idempotency_key),
                ).fetchone()
                if existing:
                    if existing['request_sha256'] != request_hash:
                        raise SourceError('idempotency_conflict', 'This upload key was already used for different input.', 409)
                    original = connection.execute(
                        '''SELECT * FROM processing_jobs WHERE tenant_id=%s AND project_id=%s AND source_id=%s
                           AND job_type='asr' ORDER BY generation,created_at LIMIT 1''', (tenant, project, existing['id']),
                    ).fetchone()
                    connection.execute('DELETE FROM artifact_cleanup WHERE id=%s AND tenant_id=%s AND project_id=%s', (reservation, tenant, project))
                    adopted = True
                    return Registration(source=repo._source(connection, tenant, project, existing['id']), job=Job.model_validate(original), deduplicated=True)
                if connection.execute('SELECT count(*) AS n FROM sources WHERE tenant_id=%s AND project_id=%s', (tenant, project)).fetchone()['n'] >= 200:
                    raise SourceError('source_limit', 'A project currently supports at most 200 sources.', 429)
                if not self._reservation(connection, reservation, tenant, project):
                    raise SourceError('upload_expired', 'The upload expired; select the file and try again.', 409)
                repo.artifacts.put(key, content)
                # Membership can be revoked independently of the project lock.
                repo._project(connection, tenant, project, actor)
                connection.execute(
                    '''INSERT INTO sources (tenant_id,project_id,id,filename,kind,provider,authorization_mode,status,
                       processing_version,idempotency_key,content_sha256,request_sha256,retention_class,license_mode,metadata)
                       VALUES (%s,%s,%s,%s,'audio','upload',%s,'created',%s,%s,%s,%s,'temporary_audio',%s,%s)''',
                    (tenant, project, source, info.filename, rights.value, ASSEMBLY_VERSION, idempotency_key, digest, request_hash,
                     'user_asserted' if rights == AuthorizationMode.LICENSED_CONTENT else 'not_applicable',
                     Jsonb({'input_kind': 'audio', 'machine_generated': True, 'requested_language': language})),
                )
                job = repo._new_job(connection, tenant, project, source, actor, 1, 'asr')
                connection.execute(
                    '''INSERT INTO audio_inputs (tenant_id,project_id,job_id,source_id,generation,actor_user_id,
                       object_key,content_sha256,byte_count,input_frames,requested_language)
                       VALUES (%s,%s,%s,%s,1,%s,%s,%s,%s,%s,%s)''',
                    (tenant, project, job.id, source, actor, key, digest, len(content), info.frames, language),
                )
                repo.store._record_audit(connection, tenant_id=tenant, project_id=project, actor_user_id=actor, action='source.created')
                connection.execute('DELETE FROM artifact_cleanup WHERE id=%s AND tenant_id=%s AND project_id=%s', (reservation, tenant, project))
                adopted = True
                return Registration(source=repo._source(connection, tenant, project, source), job=job)
        finally:
            if not adopted:
                self._due(reservation, tenant, project)

    def read_original(self, claim: dict) -> tuple[bytes, dict] | None:
        repo = self.repository
        with repo.store._connect() as connection:
            if not repo._fenced(connection, claim):
                return None
            original = connection.execute(
                '''SELECT a.*,s.content_sha256 AS source_sha FROM audio_inputs a JOIN sources s
                   ON s.tenant_id=a.tenant_id AND s.project_id=a.project_id AND s.id=a.source_id
                   WHERE a.tenant_id=%s AND a.project_id=%s AND a.job_id=%s AND a.source_id=%s AND a.generation=%s''',
                AsrCheckpoints._scope(claim),
            ).fetchone()
            if original is None or original['deleted_at'] is not None:
                raise SourceError('audio_reupload_required', 'The original audio is no longer available; upload it again.', 409)
            expected = audio_prefix(claim['tenant_id'], claim['project_id'], claim['source_id'], claim['generation']) + 'input.wav'
            if original['object_key'] != expected or original['content_sha256'] != original['source_sha']:
                raise SourceError('artifact_integrity', 'The original audio record failed integrity verification.')
        content = repo.artifacts.get(expected, MAX_WAV_BYTES)
        if len(content) != original['byte_count'] or hashlib.sha256(content).hexdigest() != original['content_sha256']:
            raise SourceError('artifact_integrity', 'The original audio failed integrity verification.')
        if validate_wav(claim['source'].filename, content).frames != original['input_frames']:
            raise SourceError('artifact_integrity', 'The original audio timeline failed integrity verification.')
        return content, original

    def continue_later(self, claim: dict, previous_window: int) -> bool:
        repo = self.repository
        with repo.store._connect() as connection:
            if not repo._fenced(connection, claim):
                return False
            run = AsrCheckpoints(repo)._run(connection, claim)
            if not previous_window < run['next_window'] < run['window_count']:
                raise SourceError('asr_no_progress', 'Speech processing did not advance; free local resources and retry.', transient=True)
            repo._finish_attempt(connection, claim['tenant_id'], claim['project_id'], claim['id'], 'checkpointed', None)
            connection.execute(
                '''UPDATE processing_jobs SET status='pending',stage='waiting_asr_continuation',continuation_pending=true,
                   available_at=now()+interval '2 seconds',lease_token=NULL,lease_expires_at=NULL,updated_at=now()
                   WHERE tenant_id=%s AND project_id=%s AND id=%s AND source_id=%s AND generation=%s''', AsrCheckpoints._scope(claim),
            )
            repo.enqueue(connection, claim['tenant_id'], claim['project_id'], claim['source_id'], claim['id'], claim['generation'], delay=2)
            return True

    def adopt(self, claim: dict) -> bool:
        repo = self.repository
        tenant, project, job, source, generation = AsrCheckpoints._scope(claim)
        reservation = uuid4()
        prefix = f'{object_prefix(tenant, project, source)}derived/{generation}/{reservation}/'
        key = prefix + 'transcript.vtt'
        with repo.store._connect() as connection:
            if not repo._fenced(connection, claim):
                return False
            self._reserve(connection, reservation, tenant, project, claim['actor_user_id'], prefix)
        adopted = False
        try:
            with repo.store._connect() as connection:
                if not repo._fenced(connection, claim):
                    return False
                derived = AsrCheckpoints(repo)._assemble(connection, claim)
                if len(derived.content) > repo.settings.upload_limit_bytes:
                    raise SourceError('derived_transcript_limit', 'The generated transcript exceeds the configured subtitle limit; provide a shorter corrected transcript.')
                if not self._reservation(connection, reservation, tenant, project):
                    raise SourceError('upload_expired', 'Derived transcript adoption expired; retry processing.', 409, transient=True)
                repo.artifacts.put(key, derived.content)
                if not repo._fenced(connection, claim):
                    return False
                connection.execute(
                    '''INSERT INTO source_artifacts (tenant_id,project_id,source_id,object_key,content_sha256,byte_count,
                       retention_class,asr_job_id) VALUES (%s,%s,%s,%s,%s,%s,'permitted_transcript',%s)''',
                    (tenant, project, source, key, derived.sha256, len(derived.content), job),
                )
                filename = claim['source'].filename.rsplit('.', 1)[0] + '.vtt'
                connection.execute(
                    '''UPDATE sources SET kind='transcript',filename=%s,status='created',retention_class='permitted_transcript',
                       metadata=metadata || %s,updated_at=now() WHERE tenant_id=%s AND project_id=%s AND id=%s''',
                    (filename, Jsonb({'asr_job_id': str(job), 'asr_profile': derived.profile, 'asr_generation': generation,
                                     'assembly_version': derived.assembly_version, 'machine_generated': True}), tenant, project, source),
                )
                connection.execute(
                    '''UPDATE processing_jobs SET status='succeeded',stage='transcribed',progress_percent=100,
                       continuation_pending=false,lease_token=NULL,lease_expires_at=NULL,finished_at=now(),updated_at=now()
                       WHERE tenant_id=%s AND project_id=%s AND id=%s''', (tenant, project, job),
                )
                repo._finish_attempt(connection, tenant, project, job, 'succeeded', None)
                downstream = repo._new_job(connection, tenant, project, source, claim['actor_user_id'], generation)
                connection.execute(
                    '''UPDATE asr_runs SET transcript_job_id=%s,adopted_sha256=%s,completed_at=now()
                       WHERE tenant_id=%s AND project_id=%s AND job_id=%s AND source_id=%s AND generation=%s''',
                    (downstream.id, derived.sha256, *AsrCheckpoints._scope(claim)),
                )
                connection.execute(
                    '''INSERT INTO usage_events (tenant_id,project_id,source_id,job_id,generation,provider,model,input_characters,
                       segment_count,duration_ms,embedding_space,input_audio_frames)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,0,%s,%s,NULL,%s)''',
                    (tenant, project, source, job, generation, PROVIDER, MODEL, derived.segments, derived.model_duration_ms, derived.input_frames),
                )
                retire_audio(connection, tenant, project, source, job)
                connection.execute('DELETE FROM artifact_cleanup WHERE id=%s AND tenant_id=%s AND project_id=%s', (reservation, tenant, project))
                adopted = True
                return True
        finally:
            if not adopted:
                self._due(reservation, tenant, project)


def retire_unusable_audio(repository: SourceRepository) -> int:
    # Global scheduler selects IDs only. Each mutation locks/rechecks full scope.
    with repository.store._connect() as connection:
        due = connection.execute(
            '''SELECT a.tenant_id,a.project_id,a.source_id,a.job_id FROM audio_inputs a
               JOIN processing_jobs j ON j.tenant_id=a.tenant_id AND j.project_id=a.project_id AND j.id=a.job_id
               WHERE a.cleanup_id IS NULL AND (a.expires_at<=now() OR j.status IN ('succeeded','failed','cancelled')
                 OR NOT EXISTS (SELECT 1 FROM memberships m WHERE m.tenant_id=a.tenant_id AND m.user_id=j.actor_user_id))
               ORDER BY a.expires_at LIMIT 50''',
        ).fetchall()
    retired = 0
    for item in due:
        with repository.store._connect() as connection:
            try:
                repository._project(connection, item['tenant_id'], item['project_id'])
            except ProjectNotFoundError:
                continue
            row = connection.execute(
                '''SELECT j.*,a.expires_at<=now() AS expired,
                     NOT EXISTS (SELECT 1 FROM memberships m WHERE m.tenant_id=j.tenant_id AND m.user_id=j.actor_user_id) AS revoked
                   FROM audio_inputs a JOIN processing_jobs j ON j.tenant_id=a.tenant_id AND j.project_id=a.project_id AND j.id=a.job_id
                   WHERE a.tenant_id=%s AND a.project_id=%s AND a.source_id=%s AND a.job_id=%s AND a.cleanup_id IS NULL FOR UPDATE OF j,a''',
                (item['tenant_id'], item['project_id'], item['source_id'], item['job_id']),
            ).fetchone()
            if row is None:
                continue
            terminal = row['status'] in {'succeeded', 'failed', 'cancelled'}
            if not (row['expired'] or row['revoked'] or terminal):
                continue
            if not terminal:
                code = 'authorization_revoked' if row['revoked'] else 'audio_expired'
                repository._finish_attempt(connection, row['tenant_id'], row['project_id'], row['id'], 'failed', code)
                repository._fail_unclaimed(connection, row, code, 'The temporary audio expired or access was revoked; upload it again if authorized.')
            retired += retire_audio(connection, row['tenant_id'], row['project_id'], row['source_id'], row['id'])
            if not terminal:
                retired += 1  # _fail_unclaimed already scheduled its raw cleanup.
    return retired
