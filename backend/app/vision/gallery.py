"""Orphan-safe retained PNG adoption; gallery publication is not index activation."""
import hashlib
import logging
import json
import re
from contextlib import nullcontext
from uuid import NAMESPACE_URL, uuid4, uuid5

from ..artifacts.storage import object_prefix
from ..models import AuthorizationMode
from ..sources.contracts import Job, Registration, SourceCommand, SourceError
from ..sources.media import MediaRepository
from ..store import ProjectNotFoundError
from .checkpoints import CHECKPOINT_VERSION, VisualCheckpoints
from .contracts import VisualIdentity, checked_png
from .gallery_contracts import RetainedFrame, VisualGallery, VisualOrigin

VERSION = 'retained-frames-v1'
LOGGER = logging.getLogger('tutorial_workspace.jobs')


def frame_id(tenant, project, source, origin_job, ordinal, frame):
    digest = hashlib.sha256(frame.text.encode()).hexdigest()
    return uuid5(NAMESPACE_URL, f'{tenant}:{project}:{source}:{origin_job}:{VERSION}:{ordinal}:{frame.timestamp_ms}:{frame.image_sha256}:{digest}')


class VisualGalleryRepository:
    def __init__(self, repository):
        self.repository = repository
        self.reservations = MediaRepository(repository)

    @staticmethod
    def _prepared(connection, tenant, project, source, visual_job, actor):
        row = connection.execute(
            '''SELECT v.*,s.content_sha256 AS source_sha,s.authorization_mode AS source_rights,s.kind,
                      j.status AS origin_status,j.job_type AS origin_type,j.actor_user_id AS origin_actor
               FROM visual_runs v JOIN sources s ON s.tenant_id=v.tenant_id AND s.project_id=v.project_id AND s.id=v.source_id
               JOIN processing_jobs j ON j.tenant_id=v.tenant_id AND j.project_id=v.project_id AND j.id=v.job_id
               WHERE v.tenant_id=%s AND v.project_id=%s AND v.source_id=%s AND v.job_id=%s''',
            (tenant, project, source, visual_job),
        ).fetchone()
        if (row is None or row['prepared_at'] is None or row['origin_status'] != 'succeeded'
                or row['origin_type'] != 'visual' or row['kind'] != 'video'
                or row['origin_actor'] != row['actor_user_id']
                or (actor is not None and row['actor_user_id'] != actor)):
            raise SourceError('visual_not_prepared', 'A complete authorized prepared video result is required.', 409)
        try:
            identity = VisualIdentity.model_validate(row['identity'])
            AuthorizationMode(row['authorization_mode'])
        except ValueError:
            raise SourceError('visual_profile_changed', 'The prepared visual identity could not be verified.', 409) from None
        if (row['profile'] != identity.profile or row['checkpoint_version'] != CHECKPOINT_VERSION
                or row['input_sha256'] != row['source_sha'] or row['authorization_mode'] != row['source_rights']):
            raise SourceError('visual_input_changed', 'The prepared video or processing identity changed.', 409)
        return row, identity

    def enqueue(self, tenant, project, source, visual_job, actor, idempotency_key, *, connection=None, continuation=False):
        """Internal command; an automatic continuation joins its parent's transaction."""
        if continuation and connection is None:
            raise ValueError('Automatic continuations require their parent transaction')
        SourceCommand(idempotency_key=idempotency_key)
        repo = self.repository
        with (repo.store._connect() if connection is None else nullcontext(connection)) as connection:
            state = repo._project(connection, tenant, project, actor)
            current = repo._source(connection, tenant, project, source)
            receipt = connection.execute(
                'SELECT command,job_id FROM source_commands WHERE tenant_id=%s AND project_id=%s AND source_id=%s AND idempotency_key=%s',
                (tenant, project, source, idempotency_key),
            ).fetchone()
            if receipt:
                publication = connection.execute(
                    'SELECT visual_job_id FROM visual_publications WHERE tenant_id=%s AND project_id=%s AND source_id=%s AND job_id=%s',
                    (tenant, project, source, receipt['job_id']),
                ).fetchone()
                if receipt['command'] != 'publish_visual' or not publication or publication['visual_job_id'] != visual_job:
                    raise SourceError('idempotency_conflict', 'This command key was used for different input.', 409)
                job = connection.execute('SELECT * FROM processing_jobs WHERE tenant_id=%s AND project_id=%s AND id=%s',
                                        (tenant, project, receipt['job_id'])).fetchone()
                return Registration(source=current, job=Job.model_validate(job), deduplicated=True)
            if state['status'] != 'active' and not continuation:
                raise SourceError('project_archived', 'Restore the project before preparing selected frames.', 409)
            run, _ = self._prepared(connection, tenant, project, source, visual_job, actor)
            if connection.execute('SELECT 1 FROM memberships WHERE tenant_id=%s AND user_id=%s FOR KEY SHARE',
                                  (tenant, actor)).fetchone() is None:
                raise ProjectNotFoundError('project not found')
            existing = connection.execute(
                'SELECT j.* FROM visual_publications p JOIN processing_jobs j ON j.tenant_id=p.tenant_id AND j.project_id=p.project_id AND j.id=p.job_id WHERE p.tenant_id=%s AND p.project_id=%s AND p.source_id=%s AND p.visual_job_id=%s',
                (tenant, project, source, visual_job),
            ).fetchone()
            if existing:
                job = Job.model_validate(existing)
            else:
                if current.job is None or current.job.status not in {'succeeded', 'failed', 'cancelled'}:
                    raise SourceError('source_busy', 'Wait for or cancel the current source job.', 409)
                generation = current.generation + 1
                job = repo._new_job(connection, tenant, project, source, actor, generation, 'visual_publish')
                connection.execute(
                    '''INSERT INTO visual_publications (tenant_id,project_id,source_id,job_id,generation,visual_job_id,
                       visual_generation,result_sha256,processing_version) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
                    (tenant, project, source, job.id, generation, visual_job, run['generation'], run['result_sha256'], VERSION),
                )
                connection.execute("UPDATE sources SET generation=%s,status='processing',failure_code=NULL,failure_detail=NULL,updated_at=now() WHERE tenant_id=%s AND project_id=%s AND id=%s",
                                   (generation, tenant, project, source))
            connection.execute("INSERT INTO source_commands (tenant_id,project_id,source_id,idempotency_key,command,job_id) VALUES (%s,%s,%s,%s,'publish_visual',%s)",
                               (tenant, project, source, idempotency_key, job.id))
            return Registration(source=repo._source(connection, tenant, project, source), job=job, deduplicated=existing is not None)

    def _live(self, connection, claim, *, lock_member=False):
        repo = self.repository
        if not repo._fenced(connection, claim): return None
        member = connection.execute('SELECT 1 FROM memberships WHERE tenant_id=%s AND user_id=%s' + (' FOR KEY SHARE' if lock_member else ''),
                                    (claim['tenant_id'], claim['actor_user_id'])).fetchone()
        row = connection.execute(
            '''SELECT p.*,j.lease_expires_at FROM visual_publications p JOIN processing_jobs j
               ON j.tenant_id=p.tenant_id AND j.project_id=p.project_id AND j.id=p.job_id
               WHERE p.tenant_id=%s AND p.project_id=%s AND p.source_id=%s AND p.job_id=%s AND p.generation=%s
               AND j.actor_user_id=%s AND j.job_type='visual_publish' AND j.cancellation_requested_at IS NULL
               AND j.lease_expires_at>clock_timestamp() AND p.published_at IS NULL''',
            (*self._scope(claim), claim['actor_user_id']),
        ).fetchone()
        return row if member else None

    @staticmethod
    def _scope(claim):
        return tuple(claim[k] for k in ('tenant_id', 'project_id', 'source_id', 'id', 'generation'))

    def _snapshot(self, connection, publication, actor):
        scope = tuple(publication[k] for k in ('tenant_id', 'project_id', 'source_id', 'visual_job_id'))
        run, _ = self._prepared(connection, *scope, actor)
        if (publication['processing_version'] != VERSION or run['result_sha256'] != publication['result_sha256']
                or run['generation'] != publication['visual_generation']):
            raise SourceError('invalid_visual_checkpoint', 'The prepared result no longer matches this publication.')
        snapshot = VisualCheckpoints(self.repository)._snapshot(connection,
            (*scope[:2], scope[3], scope[2], run['generation']), run)
        return run, snapshot

    def _rows(self, connection, publication):
        return connection.execute(
            'SELECT * FROM retained_visual_frames WHERE tenant_id=%s AND project_id=%s AND source_id=%s AND job_id=%s AND generation=%s ORDER BY ordinal',
            tuple(publication[k] for k in ('tenant_id', 'project_id', 'source_id', 'job_id', 'generation')),
        ).fetchall()

    @staticmethod
    def _key_prefix(publication):
        return object_prefix(publication['tenant_id'], publication['project_id'], publication['source_id']) + f"visual/{publication['job_id']}/"

    def _verify_rows(self, publication, snapshot, rows):
        if len(rows) > len(snapshot.frames):
            raise SourceError('artifact_integrity', 'The selected-frame manifest failed verification.')
        for ordinal, row in enumerate(rows):
            frame = snapshot.frames[ordinal]
            expected = frame_id(publication['tenant_id'], publication['project_id'], publication['source_id'], publication['visual_job_id'], ordinal, frame)
            suffix = row['object_key'].removeprefix(self._key_prefix(publication))
            if (row['ordinal'] != ordinal or row['id'] != expected or row['timestamp_ms'] != frame.timestamp_ms
                    or row['sample_target_ms'] != frame.sample_target_ms or row['width'] != frame.width or row['height'] != frame.height
                    or row['byte_count'] != len(frame.image) or row['image_sha256'] != frame.image_sha256
                    or row['ocr_text'] != frame.text or row['text_sha256'] != hashlib.sha256(frame.text.encode()).hexdigest()
                    or not row['object_key'].startswith(self._key_prefix(publication))
                    or not re.fullmatch(r'[a-f0-9]{32}/frame\.png', suffix)):
                raise SourceError('artifact_integrity', 'The selected-frame manifest failed verification.')

    def adopt_next(self, claim):
        """One bounded PUT per delivery; return True only when the gallery is complete."""
        repo = self.repository
        tenant, project, source, job, generation = self._scope(claim)
        reservation, adopted = uuid4(), False
        prefix = self._key_prefix({'tenant_id': tenant, 'project_id': project, 'source_id': source, 'job_id': job}) + uuid4().hex + '/'
        with repo.store._connect() as connection:
            if self._live(connection, claim) is None: return False
            self.reservations._reserve(connection, reservation, tenant, project, claim['actor_user_id'], prefix)
        try:
            with repo.store._connect() as connection:
                publication = self._live(connection, claim)
                if publication is None: return False
                _, snapshot = self._snapshot(connection, publication, claim['actor_user_id'])
                rows = self._rows(connection, publication)
                self._verify_rows(publication, snapshot, rows)
                if len(rows) < len(snapshot.frames):
                    if not self.reservations._reservation(connection, reservation, tenant, project):
                        raise SourceError('upload_expired', 'The frame reservation expired; retry.', transient=True)
                    ordinal, frame = len(rows), snapshot.frames[len(rows)]
                    key = prefix + 'frame.png'
                    repo.artifacts.put(key, frame.image)
                    if self._live(connection, claim, lock_member=True) is None:
                        connection.rollback()
                        return False
                    connection.execute(
                        '''INSERT INTO retained_visual_frames (tenant_id,project_id,source_id,job_id,generation,id,ordinal,
                           timestamp_ms,sample_target_ms,width,height,object_key,byte_count,image_sha256,ocr_text,text_sha256)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
                        (*self._scope(claim), frame_id(tenant, project, source, publication['visual_job_id'], ordinal, frame), ordinal,
                         frame.timestamp_ms, frame.sample_target_ms, frame.width, frame.height, key, len(frame.image),
                         frame.image_sha256, frame.text, hashlib.sha256(frame.text.encode()).hexdigest()),
                    )
                rows = self._rows(connection, publication)
                self._verify_rows(publication, snapshot, rows)
                if self._live(connection, claim, lock_member=True) is None:
                    connection.rollback()
                    return False
                complete = len(rows) == len(snapshot.frames)
                next_job = None
                if complete:
                    connection.execute('UPDATE visual_publications SET published_at=clock_timestamp() WHERE tenant_id=%s AND project_id=%s AND source_id=%s AND job_id=%s AND generation=%s', self._scope(claim))
                    connection.execute("UPDATE processing_jobs SET status='succeeded',stage='frames_retained',progress_percent=100,continuation_pending=false,lease_token=NULL,lease_expires_at=NULL,finished_at=now(),updated_at=now() WHERE tenant_id=%s AND project_id=%s AND source_id=%s AND id=%s AND generation=%s", self._scope(claim))
                    connection.execute("UPDATE sources SET status='metadata_ready',frame_count=%s,retention_class='permitted_visual',updated_at=now() WHERE tenant_id=%s AND project_id=%s AND id=%s", (len(rows), tenant, project, source))
                    repo._finish_attempt(connection, tenant, project, job, 'succeeded', None)
                    # Local import avoids the index -> gallery dependency cycle.
                    from .workflow import after_publication
                    next_job = after_publication(repo, connection, claim)
                else:
                    repo._finish_attempt(connection, tenant, project, job, 'checkpointed', None)
                    connection.execute("UPDATE processing_jobs SET status='pending',stage='waiting_visual_continuation',progress_percent=%s,continuation_pending=true,available_at=now()+interval '2 seconds',lease_token=NULL,lease_expires_at=NULL,updated_at=now() WHERE tenant_id=%s AND project_id=%s AND source_id=%s AND id=%s AND generation=%s", (10 + len(rows)*80//len(snapshot.frames), *self._scope(claim)))
                    repo.enqueue(connection, tenant, project, source, job, generation, delay=2)
                connection.execute('DELETE FROM artifact_cleanup WHERE tenant_id=%s AND project_id=%s AND id=%s', (tenant, project, reservation))
                if not connection.execute('SELECT clock_timestamp()<%s AS valid', (publication['lease_expires_at'],)).fetchone()['valid']:
                    connection.rollback()
                    return False
            adopted = True
            LOGGER.info(json.dumps({'event': 'visual_frame_adopted', 'tenant_id': tenant, 'project_id': str(project),
                'job_id': str(job), 'retained_frames': len(rows), 'gallery_complete': complete,
                'index_queued': complete and next_job is not None}))
            return complete
        finally:
            if not adopted: self.reservations._due(reservation, tenant, project)

    def _read_scope(self, connection, tenant, project, source, actor):
        self.repository.store._require_membership(connection, tenant, actor)
        row = connection.execute(
            '''SELECT s.filename,s.active_generation,s.active_embedding_space FROM sources s JOIN projects p ON p.tenant_id=s.tenant_id AND p.id=s.project_id
               WHERE s.tenant_id=%s AND s.project_id=%s AND s.id=%s AND s.deleted_at IS NULL AND p.deleted_at IS NULL''',
            (tenant, project, source),
        ).fetchone()
        if row is None: raise ProjectNotFoundError('source not found')
        return row

    def gallery(self, tenant, project, source, actor):
        with self.repository.store._connect() as connection:
            connection.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            current = self._read_scope(connection, tenant, project, source, actor)
            publication = connection.execute(
                'SELECT * FROM visual_publications WHERE tenant_id=%s AND project_id=%s AND source_id=%s AND published_at IS NOT NULL ORDER BY generation DESC LIMIT 1',
                (tenant, project, source),
            ).fetchone()
            if publication is None: return VisualGallery(source_id=source, source_filename=current['filename'])
            run, snapshot = self._snapshot(connection, publication, None)
            rows = self._rows(connection, publication)
            self._verify_rows(publication, snapshot, rows)
            if len(rows) != len(snapshot.frames): raise SourceError('artifact_integrity', 'The selected-frame gallery is incomplete.')
            identity = VisualIdentity.model_validate(snapshot.identity)
            indexed = connection.execute(
                '''SELECT 1 FROM processing_versions WHERE tenant_id=%s AND project_id=%s AND source_id=%s
                   AND generation=%s AND visual_publication_job_id=%s''',
                (tenant, project, source, current['active_generation'], publication['job_id']),
            ).fetchone() is not None
            return VisualGallery(source_id=source, source_filename=current['filename'], generation=publication['generation'],
                processing_version=VERSION, published_at=publication['published_at'],
                searchable=indexed, active_index_generation=current['active_generation'] if indexed else None,
                active_embedding_space=current['active_embedding_space'] if indexed else None,
                origin=VisualOrigin(job_id=run['job_id'], generation=run['generation'], profile=identity.profile,
                    language=identity.language, engines=identity.engines.model_dump(), checkpoint_version=run['checkpoint_version'], prepared_at=run['prepared_at']),
                items=[RetainedFrame.model_validate(row) for row in rows])

    def image(self, tenant, project, frame, actor):
        def read():
            with self.repository.store._connect() as connection:
                self.repository.store._require_membership(connection, tenant, actor)
                row = connection.execute(
                    '''SELECT f.* FROM retained_visual_frames f JOIN visual_publications p
                       ON p.tenant_id=f.tenant_id AND p.project_id=f.project_id AND p.job_id=f.job_id
                       WHERE f.tenant_id=%s AND f.project_id=%s AND f.id=%s AND p.published_at IS NOT NULL''',
                    (tenant, project, frame),
                ).fetchone()
                if row is None: raise ProjectNotFoundError('frame not found')
                self._read_scope(connection, tenant, project, row['source_id'], actor)
                expected_prefix = self._key_prefix(row)
                if not row['object_key'].startswith(expected_prefix) or not re.fullmatch(r'[a-f0-9]{32}/frame\.png', row['object_key'][len(expected_prefix):]):
                    raise SourceError('artifact_integrity', 'The frame object reference failed verification.')
                return row
        row = read()
        # Verify the complete immutable manifest before any object key is fetched.
        gallery = self.gallery(tenant, project, row['source_id'], actor)
        if frame not in {item.id for item in gallery.items}: raise ProjectNotFoundError('frame not found')
        data = self.repository.artifacts.get(row['object_key'], 600000)
        try:
            checked_png(data, row['width'], row['height'])
            valid = (isinstance(data, bytes) and len(data) == row['byte_count']
                     and hashlib.sha256(data).hexdigest() == row['image_sha256'])
        except (ValueError, TypeError): valid = False
        if not valid: raise SourceError('artifact_integrity', 'The retained PNG failed verification.')
        if read() != row: raise ProjectNotFoundError('frame changed')
        return data
