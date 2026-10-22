"""Private durable windows. This component never calls a model or publishes text."""
from dataclasses import dataclass
import hashlib
import json
import logging

from psycopg.types.json import Jsonb

from ..sources.contracts import SourceError
from ..sources.repository import SourceRepository
from .contracts import Language, TranscriptionSlice
from .profile import identity
from .transcript import ASSEMBLY_VERSION, DerivedTranscript, assemble_vtt, result_digest, validated_slice
from .wav import SLICE_FRAMES, validate_wav

LOGGER = logging.getLogger('tutorial_workspace.jobs')


@dataclass(frozen=True)
class AsrCursor:
    next_window: int
    total_windows: int
    completed_frames: int
    input_frames: int


class AsrCheckpoints:
    def __init__(self, repository: SourceRepository):
        self.repository = repository

    @staticmethod
    def _scope(claim):
        return tuple(claim[key] for key in ('tenant_id', 'project_id', 'id', 'source_id', 'generation'))

    def _run(self, connection, claim):
        row = connection.execute(
            '''SELECT r.*,s.content_sha256 AS original_sha256,s.kind,j.job_type
               FROM asr_runs r JOIN processing_jobs j
               ON j.tenant_id=r.tenant_id AND j.project_id=r.project_id AND j.id=r.job_id
               AND j.source_id=r.source_id AND j.generation=r.generation
               JOIN sources s ON s.tenant_id=r.tenant_id AND s.project_id=r.project_id AND s.id=r.source_id
               WHERE r.tenant_id=%s AND r.project_id=%s AND r.job_id=%s AND r.source_id=%s AND r.generation=%s''',
            self._scope(claim),
        ).fetchone()
        if row is None:
            raise SourceError('asr_checkpoint_missing', 'Initialize this audio generation before saving results.', 409)
        if row['kind'] != 'audio' or row['job_type'] != 'asr' or row['original_sha256'] != row['input_sha256']:
            raise SourceError('asr_input_changed', 'The audio input no longer matches this processing generation.', 409)
        if row['assembly_version'] != ASSEMBLY_VERSION or any(row[key] != value for key, value in identity().items()):
            raise SourceError('asr_profile_changed', 'Restore the original speech model and assembly profile.', 409)
        return row

    def begin(self, claim: dict, filename: str, content: bytes, language: Language) -> AsrCursor | None:
        info = validate_wav(filename, content)
        if not isinstance(language, str) or language not in {'auto', 'en', 'tr'}:
            raise SourceError('invalid_asr_language', 'Select automatic, English or Turkish speech recognition.')
        digest = hashlib.sha256(content).hexdigest()
        with self.repository.store._connect() as connection:
            if not self.repository._fenced(connection, claim):
                return None
            source = connection.execute(
                '''SELECT s.content_sha256,s.kind,j.job_type FROM sources s JOIN processing_jobs j
                   ON j.tenant_id=s.tenant_id AND j.project_id=s.project_id AND j.source_id=s.id
                   WHERE j.tenant_id=%s AND j.project_id=%s AND j.id=%s AND j.source_id=%s AND j.generation=%s''',
                self._scope(claim),
            ).fetchone()
            if source['kind'] != 'audio' or source['job_type'] != 'asr' or source['content_sha256'] != digest:
                raise SourceError('asr_input_changed', 'The audio input does not match this processing generation.', 409)
            values = identity()
            connection.execute(
                '''INSERT INTO asr_runs (tenant_id,project_id,job_id,source_id,generation,input_sha256,input_frames,
                   requested_language,provider,model,revision,profile,engine,network_policy,assembly_version)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING''',
                (*self._scope(claim), digest, info.frames, language, values['provider'], values['model'], values['revision'],
                 values['profile'], values['engine'], values['network_policy'], ASSEMBLY_VERSION),
            )
            run = self._run(connection, claim)
            if (run['input_sha256'], run['input_frames'], run['requested_language']) != (digest, info.frames, language):
                raise SourceError('asr_input_changed', 'Restore the original audio and language for this generation.', 409)
            return AsrCursor(run['next_window'], run['window_count'], run['completed_frames'], run['input_frames'])

    def save(self, claim: dict, ordinal: int, value: dict | TranscriptionSlice) -> bool:
        if type(ordinal) is not int or not 0 <= ordinal < 20:
            raise SourceError('invalid_asr_window', 'Select a valid audio window.')
        result = validated_slice(value)
        with self.repository.store._connect() as connection:
            if not self.repository._fenced(connection, claim):
                return False
            run = self._run(connection, claim)
            if ordinal != run['next_window'] or ordinal >= run['window_count']:
                return False
            if (result.input_frames != min(SLICE_FRAMES, run['input_frames'] - ordinal * SLICE_FRAMES)
                    or result.requested_language != run['requested_language']):
                raise SourceError('invalid_asr_checkpoint', 'The speech result does not match its audio window.', 503)
            connection.execute(
                '''INSERT INTO asr_windows (tenant_id,project_id,job_id,source_id,generation,ordinal,input_frames,result,result_sha256)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
                (*self._scope(claim), ordinal, result.input_frames, Jsonb(result.model_dump(mode='json')), result_digest(result)),
            )
            connection.execute(
                '''UPDATE asr_runs SET next_window=next_window+1,completed_frames=completed_frames+%s,
                   model_duration_ms=model_duration_ms+%s,segment_count=segment_count+%s,updated_at=now()
                   WHERE tenant_id=%s AND project_id=%s AND job_id=%s AND source_id=%s AND generation=%s''',
                (result.input_frames, result.duration_ms, len(result.segments), *self._scope(claim)),
            )
        LOGGER.info(json.dumps({'event': 'asr_window_checkpoint', 'job_id': str(claim['id']),
                                'generation': claim['generation'], 'saved_windows': ordinal + 1,
                                'input_frames': result.input_frames, 'segments': len(result.segments),
                                'model_duration_ms': result.duration_ms, 'profile': result.profile}))
        return True

    def assemble(self, claim: dict) -> DerivedTranscript | None:
        with self.repository.store._connect() as connection:
            if not self.repository._fenced(connection, claim):
                return None
            return self._assemble(connection, claim)

    def _assemble(self, connection, claim: dict) -> DerivedTranscript:
        """Caller already holds the live project/job fence in this transaction."""
        run = self._run(connection, claim)
        rows = connection.execute(
            '''SELECT * FROM asr_windows WHERE tenant_id=%s AND project_id=%s AND job_id=%s
               AND source_id=%s AND generation=%s ORDER BY ordinal''', self._scope(claim),
        ).fetchall()
        if (run['next_window'] != run['window_count'] or run['completed_frames'] != run['input_frames']
                or len(rows) != run['window_count']):
            raise SourceError('asr_checkpoint_incomplete', 'All audio windows must be saved before assembling a transcript.', 409)
        results = []
        for ordinal, row in enumerate(rows):
            result = validated_slice(row['result'])
            if (row['ordinal'] != ordinal or result_digest(result) != row['result_sha256']
                    or row['input_frames'] != result.input_frames or result.requested_language != run['requested_language']):
                raise SourceError('invalid_asr_checkpoint', 'The saved speech results failed integrity verification.', 503)
            results.append(result)
        derived = assemble_vtt(results, run['input_frames'])
        if derived.segments != run['segment_count'] or derived.model_duration_ms != run['model_duration_ms']:
            raise SourceError('invalid_asr_checkpoint', 'The saved speech usage failed integrity verification.', 503)
        return derived
