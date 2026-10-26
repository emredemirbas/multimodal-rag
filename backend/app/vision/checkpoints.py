"""Private complete-batch snapshots, never a decoder, upload or evidence publisher."""
import base64
from dataclasses import dataclass
import hashlib
import json
import logging

from psycopg.types.json import Jsonb

from ..sources.contracts import SourceError
from ..sources.repository import SourceRepository
from .contracts import VisualIdentity, WireResult, encode_wire
from .local import VisualResult
from .media import validate_mp4

LOGGER = logging.getLogger('tutorial_workspace.jobs')
CHECKPOINT_VERSION = 'visual-checkpoint-v1'


@dataclass(frozen=True)
class VisualCursor:
    result_saved: bool
    saved_frames: int
    image_bytes: int
    ocr_characters: int


def validated_result(value) -> WireResult:
    try:
        if isinstance(value, VisualResult):
            result = WireResult.from_result(value)
        else:
            # Revalidate existing models too; mutable lists must not bypass checks.
            result = WireResult.model_validate(value.model_dump() if isinstance(value, WireResult) else value)
        encode_wire(result)
        return result
    except (ValueError, TypeError, RecursionError):
        raise SourceError('invalid_visual_checkpoint', 'The visual result failed integrity validation.', 503) from None


def result_digest(value: WireResult) -> str:
    return hashlib.sha256(json.dumps(value.model_dump(), sort_keys=True, ensure_ascii=False,
        separators=(',', ':'), allow_nan=False).encode()).hexdigest()


class VisualCheckpoints:
    def __init__(self, repository: SourceRepository):
        self.repository = repository

    @staticmethod
    def _scope(claim):
        return tuple(claim[key] for key in ('tenant_id', 'project_id', 'id', 'source_id', 'generation'))

    def _live(self, connection, claim):
        if not self.repository._fenced(connection, claim):
            return None
        # Protect the initiating membership until commit, not just a pre-read.
        member = connection.execute('SELECT 1 FROM memberships WHERE tenant_id=%s AND user_id=%s FOR KEY SHARE',
                                    (claim['tenant_id'], claim['actor_user_id'])).fetchone()
        if member is None:
            return None
        row = connection.execute(
            '''SELECT s.kind,s.content_sha256,s.authorization_mode,j.job_type,j.actor_user_id,j.lease_expires_at AS lease_until,
                      j.created_at + interval '1 hour' AS expires_at
               FROM processing_jobs j JOIN sources s
               ON s.tenant_id=j.tenant_id AND s.project_id=j.project_id AND s.id=j.source_id
               WHERE j.tenant_id=%s AND j.project_id=%s AND j.id=%s AND j.source_id=%s AND j.generation=%s
               AND j.actor_user_id=%s AND j.lease_expires_at>clock_timestamp()
               AND j.created_at+interval '1 hour'>clock_timestamp() AND j.cancellation_requested_at IS NULL''',
            (*self._scope(claim), claim['actor_user_id']),
        ).fetchone()
        if row is not None and (row['kind'] != 'video' or row['job_type'] != 'visual'):
            raise SourceError('visual_input_changed', 'Use the original video processing job.', 409)
        return row

    def _run(self, connection, claim, live):
        row = connection.execute(
            '''SELECT * FROM visual_runs WHERE tenant_id=%s AND project_id=%s AND job_id=%s
               AND source_id=%s AND generation=%s''', self._scope(claim),
        ).fetchone()
        if row is None:
            raise SourceError('visual_checkpoint_missing', 'Initialize this video generation before saving results.', 409)
        try:
            identity = VisualIdentity.model_validate(row['identity'])
        except ValueError:
            raise SourceError('visual_profile_changed', 'Restore the pinned visual processing profile.', 409) from None
        if row['profile'] != identity.profile or row['checkpoint_version'] != CHECKPOINT_VERSION:
            raise SourceError('visual_profile_changed', 'Restore the pinned visual processing profile.', 409)
        if (row['input_sha256'] != live['content_sha256'] or row['authorization_mode'] != live['authorization_mode']
                or row['actor_user_id'] != live['actor_user_id'] or row['processing_expires_at'] != live['expires_at']):
            raise SourceError('visual_input_changed', 'The original video, authorization or processing eligibility changed.', 409)
        return row

    def begin(self, claim, content: bytes, expected_identity: VisualIdentity | dict) -> VisualCursor | None:
        try:
            validate_mp4(content)
            identity = VisualIdentity.model_validate(expected_identity.model_dump()
                if isinstance(expected_identity, VisualIdentity) else expected_identity)
        except (ValueError, TypeError, RecursionError):
            raise SourceError('invalid_visual_input', 'Use an authorized supported MP4 and a valid pinned OCR profile.') from None
        digest = hashlib.sha256(content).hexdigest()
        with self.repository.store._connect() as connection:
            live = self._live(connection, claim)
            if live is None:
                return None
            if live['content_sha256'] != digest:
                raise SourceError('visual_input_changed', 'The MP4 bytes do not match this video generation.', 409)
            connection.execute(
                '''INSERT INTO visual_runs (tenant_id,project_id,job_id,source_id,generation,actor_user_id,
                   authorization_mode,input_sha256,input_bytes,identity,profile,checkpoint_version,processing_expires_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING''',
                (*self._scope(claim), claim['actor_user_id'], live['authorization_mode'], digest, len(content),
                 Jsonb(identity.model_dump()), identity.profile, CHECKPOINT_VERSION, live['expires_at']),
            )
            run = self._run(connection, claim, live)
            if run['identity'] != identity.model_dump() or run['input_bytes'] != len(content):
                raise SourceError('visual_input_changed', 'Restore the original MP4 and OCR profile for this generation.', 409)
            if self._live(connection, claim) is None:
                connection.rollback()
                return None
            return VisualCursor(run['saved_at'] is not None, run['saved_frames'], run['image_bytes'], run['ocr_characters'])

    def save(self, claim, value: dict | WireResult | VisualResult) -> bool:
        result = validated_result(value)
        with self.repository.store._connect() as connection:
            live = self._live(connection, claim)
            if live is None:
                return False
            run = self._run(connection, claim, live)
            if run['saved_at'] is not None:
                return False
            if result.input_sha256 != run['input_sha256'] or result.identity.model_dump() != run['identity']:
                raise SourceError('visual_input_changed', 'The visual result does not match the pinned input/profile.', 409)
            images = [base64.b64decode(frame.image_base64) for frame in result.frames]
            for ordinal, (frame, image) in enumerate(zip(result.frames, images, strict=True)):
                connection.execute(
                    '''INSERT INTO visual_checkpoint_frames (tenant_id,project_id,job_id,source_id,generation,ordinal,
                       sample_target_ms,timestamp_ms,width,height,image,image_sha256,ocr_text,text_sha256)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
                    (*self._scope(claim), ordinal, frame.sample_target_ms, frame.timestamp_ms, frame.width,
                     frame.height, image, frame.image_sha256, frame.text, hashlib.sha256(frame.text.encode()).hexdigest()),
                )
            image_bytes = sum(map(len, images))
            characters = sum(len(frame.text) for frame in result.frames)
            connection.execute(
                '''UPDATE visual_runs SET video_metadata=%s,candidates=%s,saved_frames=%s,image_bytes=%s,
                   ocr_characters=%s,result_sha256=%s,saved_at=clock_timestamp()
                   WHERE tenant_id=%s AND project_id=%s AND job_id=%s AND source_id=%s AND generation=%s''',
                (Jsonb(result.video.model_dump()), result.candidates, len(result.frames), image_bytes,
                 characters, result_digest(result), *self._scope(claim)),
            )
            connection.execute(
                '''UPDATE processing_jobs SET stage='visual_checkpointed',progress_percent=greatest(progress_percent,60),updated_at=now()
                   WHERE tenant_id=%s AND project_id=%s AND id=%s AND source_id=%s AND generation=%s''', self._scope(claim),
            )
            if self._live(connection, claim) is None:
                connection.rollback()
                return False
        LOGGER.info(json.dumps({'event': 'visual_result_checkpoint', 'tenant_id': claim['tenant_id'],
            'project_id': str(claim['project_id']), 'job_id': str(claim['id']), 'generation': claim['generation'],
            'frames': len(result.frames), 'image_bytes': image_bytes, 'ocr_characters': characters}))
        return True

    def load(self, claim) -> VisualResult | None:
        with self.repository.store._connect() as connection:
            return self._load(connection, claim)

    def _load(self, connection, claim) -> VisualResult | None:
        """Also used by atomic preparation in the caller's fenced transaction."""
        live = self._live(connection, claim)
        if live is None:
            return None
        run = self._run(connection, claim, live)
        if run['saved_at'] is None:
            raise SourceError('visual_checkpoint_incomplete', 'Save a complete visual result before adopting it.', 409)
        result = self._snapshot(connection, self._scope(claim), run)
        if self._live(connection, claim) is None:
            return None
        return result

    def _snapshot(self, connection, scope, run) -> VisualResult:
        """Integrity only; caller must enforce either the live or prepared fence."""
        rows = connection.execute(
            '''SELECT * FROM visual_checkpoint_frames WHERE tenant_id=%s AND project_id=%s AND job_id=%s
               AND source_id=%s AND generation=%s ORDER BY ordinal''', scope,
        ).fetchall()
        if (len(rows) != run['saved_frames'] or [row['ordinal'] for row in rows] != list(range(len(rows)))
                or sum(len(row['image']) for row in rows) != run['image_bytes']
                or sum(len(row['ocr_text']) for row in rows) != run['ocr_characters']
                or any(hashlib.sha256(row['ocr_text'].encode()).hexdigest() != row['text_sha256'] for row in rows)):
            raise SourceError('invalid_visual_checkpoint', 'The saved visual result failed integrity validation.', 503)
        result = validated_result({'input_sha256': run['input_sha256'], 'identity': run['identity'],
            'video': run['video_metadata'], 'candidates': run['candidates'], 'frames': [
                {'sample_target_ms': row['sample_target_ms'], 'timestamp_ms': row['timestamp_ms'],
                 'width': row['width'], 'height': row['height'], 'image_sha256': row['image_sha256'],
                 'image_base64': base64.b64encode(row['image']).decode(), 'text': row['ocr_text']} for row in rows]})
        if result_digest(result) != run['result_sha256']:
            raise SourceError('invalid_visual_checkpoint', 'The saved visual manifest failed integrity validation.', 503)
        return result.result()
