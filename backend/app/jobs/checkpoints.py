"""Private, fenced semantic batches. Only complete generations become evidence."""
import hashlib
import math
from typing import TYPE_CHECKING

from ..embedding_profiles import QWEN_SPACE, QWEN_DIGEST, QWEN_MODEL
from ..models import EvidenceSegment
from ..sources.chunking import PROCESSING_VERSION, segment_id
from ..sources.contracts import SourceError

if TYPE_CHECKING:
    from ..sources.repository import SourceRepository

MAX_BATCHES_PER_DELIVERY = 8


class TranscriptCheckpoints:
    def __init__(self, repository: 'SourceRepository'):
        self.repository = repository

    @staticmethod
    def _scope(claim):
        return tuple(claim[key] for key in ('tenant_id', 'project_id', 'source_id', 'id', 'generation'))

    def _job(self, connection, claim):
        return connection.execute(
            'SELECT * FROM processing_jobs WHERE tenant_id=%s AND project_id=%s AND source_id=%s AND id=%s AND generation=%s',
            self._scope(claim),
        ).fetchone()

    def begin(self, claim: dict, chunks) -> int | None:
        manifest = hashlib.sha256(''.join(str(segment_id(claim['source_id'], claim['generation'], chunk, i))
                                          for i, chunk in enumerate(chunks)).encode()).hexdigest()
        with self.repository.store._connect() as connection:
            if not self.repository._fenced(connection, claim):
                return None
            job = self._job(connection, claim)
            if job['target_embedding_space'] != QWEN_SPACE:
                raise SourceError('processing_configuration_changed', 'Restore the original embedding mode or Reprocess source for a new generation.')
            if job['chunk_manifest_sha256'] is not None and (job['chunk_manifest_sha256'] != manifest or job['total_segments'] != len(chunks)):
                raise SourceError('checkpoint_input_changed', 'Transcript processing changed. Reprocess source to start a new generation.')
            connection.execute(
                'UPDATE processing_jobs SET chunk_manifest_sha256=%s,total_segments=%s WHERE tenant_id=%s AND project_id=%s AND source_id=%s AND id=%s AND generation=%s',
                (manifest, len(chunks), *self._scope(claim)),
            )
            return job['processed_segments']

    def save(self, claim: dict, offset: int, segments: list[EvidenceSegment], provenance: list[tuple[int, int]], input_tokens: int | None) -> bool:
        if (not 1 <= len(segments) <= 8 or len(provenance) != len(segments)
                or input_tokens is not None and (type(input_tokens) is not int or not 0 <= input_tokens <= 100_000)
                or any(segment.tenant_id != claim['tenant_id'] or segment.project_id != claim['project_id']
                       or segment.source_id != claim['source_id'] or segment.generation != claim['generation']
                       or segment.embedding_space != QWEN_SPACE or len(segment.embedding) != 1024
                       or not 1 <= len(segment.text) <= 1200
                       or segment.processing_version != f"{PROCESSING_VERSION}:g{claim['generation']}"
                       or any(not math.isfinite(value) for value in segment.embedding)
                       or not .999 <= sum(value * value for value in segment.embedding) <= 1.001 for segment in segments)):
            raise SourceError('invalid_embeddings', 'The checkpoint evidence could not be validated.', 503)
        with self.repository.store._connect() as connection:
            if not self.repository._fenced(connection, claim):
                return False
            job = self._job(connection, claim)
            if job['processed_segments'] != offset or job['target_embedding_space'] != QWEN_SPACE or offset + len(segments) > job['total_segments']:
                return False
            for ordinal, (segment, (cue_start, cue_end)) in enumerate(zip(segments, provenance, strict=True), offset):
                connection.execute(
                    '''INSERT INTO embedding_checkpoints (tenant_id,project_id,source_id,job_id,generation,ordinal,
                       segment_id,start_ms,end_ms,text,cue_start,cue_end,processing_version,embedding_space,embedding)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::vector)''',
                    (*self._scope(claim), ordinal, segment.id, segment.start_ms, segment.end_ms, segment.text,
                     cue_start, cue_end, segment.processing_version, segment.embedding_space,
                     self.repository.store._vector_literal(segment.embedding)),
                )
            end = offset + len(segments)
            connection.execute(
                '''UPDATE processing_jobs SET processed_segments=%s,progress_percent=%s,
                   checkpoint_input_tokens=checkpoint_input_tokens+%s,updated_at=now()
                   WHERE tenant_id=%s AND project_id=%s AND source_id=%s AND id=%s AND generation=%s''',
                (end, min(85, 50 + 35 * end // job['total_segments']), input_tokens, *self._scope(claim)),
            )
            return True

    def continue_later(self, claim: dict) -> bool:
        with self.repository.store._connect() as connection:
            if not self.repository._fenced(connection, claim):
                return False
            job = self._job(connection, claim)
            if not claim['processed_segments'] < job['processed_segments'] < job['total_segments']:
                raise SourceError('checkpoint_no_progress', 'Processing could not advance. Free local resources and retry.', transient=True)
            self.repository._finish_attempt(connection, claim['tenant_id'], claim['project_id'], claim['id'], 'checkpointed', None)
            connection.execute(
                '''UPDATE processing_jobs SET status='pending',stage='waiting_continuation',continuation_pending=true,
                   available_at=now()+interval '2 seconds',lease_token=NULL,lease_expires_at=NULL,updated_at=now()
                   WHERE tenant_id=%s AND project_id=%s AND source_id=%s AND id=%s AND generation=%s''', self._scope(claim),
            )
            self.repository.enqueue(connection, claim['tenant_id'], claim['project_id'], claim['source_id'], claim['id'], claim['generation'], delay=2)
            return True

    def finish(self, claim: dict) -> bool:
        with self.repository.store._connect() as connection:
            if not self.repository._fenced(connection, claim):
                return False
            job = self._job(connection, claim)
            totals = connection.execute(
                '''SELECT count(*) AS count,min(ordinal) AS first,max(ordinal) AS last,sum(length(text)) AS characters,
                          string_agg(segment_id::text,'' ORDER BY ordinal) AS ids
                   FROM embedding_checkpoints WHERE tenant_id=%s AND project_id=%s AND source_id=%s AND job_id=%s AND generation=%s''',
                self._scope(claim),
            ).fetchone()
            if (not job['chunk_manifest_sha256'] or job['target_embedding_space'] != QWEN_SPACE or job['total_segments'] == 0
                    or job['processed_segments'] != job['total_segments'] or totals['count'] != job['total_segments']
                    or totals['first'] != 0 or totals['last'] != job['total_segments'] - 1
                    or hashlib.sha256((totals['ids'] or '').encode()).hexdigest() != job['chunk_manifest_sha256']):
                raise SourceError('checkpoint_incomplete', 'The index is incomplete. Retry processing before using this generation.', 503)
            version = f"{PROCESSING_VERSION}:g{claim['generation']}"
            connection.execute(
                '''INSERT INTO processing_versions (tenant_id,project_id,source_id,generation,processing_version,
                   embedding_provider,embedding_model,embedding_dimensions,embedding_space,embedding_model_digest)
                   VALUES (%s,%s,%s,%s,%s,'ollama-local',%s,1024,%s,%s)''',
                (claim['tenant_id'], claim['project_id'], claim['source_id'], claim['generation'], version, QWEN_MODEL, QWEN_SPACE, QWEN_DIGEST),
            )
            connection.execute(
                '''INSERT INTO content_segments (tenant_id,project_id,source_id,id,generation,modality,start_ms,end_ms,
                   text,embedding,embedding_space,processing_version,cue_start,cue_end)
                   SELECT tenant_id,project_id,source_id,segment_id,generation,'transcript',start_ms,end_ms,text,
                          embedding,embedding_space,processing_version,cue_start,cue_end FROM embedding_checkpoints
                   WHERE tenant_id=%s AND project_id=%s AND source_id=%s AND job_id=%s AND generation=%s''', self._scope(claim),
            )
            self.repository._activate(connection, claim, 'ollama-local', QWEN_MODEL, totals['count'], totals['characters'], 0,
                                      embedding_space=QWEN_SPACE, model_digest=QWEN_DIGEST, input_tokens=job['checkpoint_input_tokens'], cumulative=True)
            connection.execute('DELETE FROM embedding_checkpoints WHERE tenant_id=%s AND project_id=%s AND source_id=%s AND job_id=%s AND generation=%s', self._scope(claim))
            return True
