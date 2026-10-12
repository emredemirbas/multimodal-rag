import hashlib
import json
import logging
from time import perf_counter
from uuid import UUID

from billiard.exceptions import SoftTimeLimitExceeded

from ..models import EvidenceSegment
from ..local_embeddings import build_embedding_provider, BATCH_SIZE
from ..embedding_profiles import HASH_SPACE, QWEN_SPACE, QWEN_MODEL, QWEN_DIGEST
from .checkpoints import TranscriptCheckpoints, MAX_BATCHES_PER_DELIVERY
from ..sources.chunking import PROCESSING_VERSION, chunk_transcript, segment_id
from ..sources.contracts import SourceError
from ..sources.repository import SourceRepository
from ..sources.adapters import YouTubeAdapter, YouTubeMetadataProvider

LOGGER = logging.getLogger('tutorial_workspace.jobs')


def process_transcript(repository: SourceRepository, tenant: str, project: UUID, source: UUID, job: UUID, generation: int) -> bool:
    claim = repository.claim_job(tenant, project, source, job, generation)
    if claim is None:
        return False
    started = perf_counter()

    def stage(name: str, progress: int) -> bool:
        updated = repository.stage(claim, name, progress)
        if updated:
            LOGGER.info(json.dumps({'event': 'processing_stage', 'tenant_id': tenant, 'project_id': str(project),
                                    'source_id': str(source), 'job_id': str(job), 'generation': generation,
                                    'stage': name, 'attempt': claim['attempt_count'], 'delivery': claim['delivery_count']}))
        return updated

    try:
        if claim['job_type'] == 'metadata':
            if not stage('metadata', 20):
                return False
            normalized = YouTubeAdapter().normalize(claim['source'].metadata['canonical_url'])
            metadata = YouTubeMetadataProvider(repository.settings.youtube_api_key).metadata(normalized)
            return repository.complete_metadata(claim, metadata, round((perf_counter()-started)*1000))
        if not claim['artifact']:
            raise SourceError('missing_artifact', 'The retained transcript is missing; upload the source again.')
        provider = build_embedding_provider(repository.settings)
        if claim['target_embedding_space'] != provider.space_id:
            raise SourceError('processing_configuration_changed', 'Restore the original embedding mode or Reprocess source for a new generation.')
        if provider.space_id != HASH_SPACE and (provider.space_id, provider.name, provider.model, provider.dimensions, provider.model_digest) != (QWEN_SPACE, 'ollama-local', QWEN_MODEL, 1024, QWEN_DIGEST):
            raise SourceError('processing_configuration_changed', 'The embedding profile could not be validated. Restore the approved provider or Reprocess source.')
        if not stage('parsing', max(20, claim['progress_percent'])):
            return False
        content = repository.artifacts.get(claim['artifact']['object_key'], repository.settings.upload_limit_bytes)
        if hashlib.sha256(content).hexdigest() != claim['artifact']['content_sha256']:
            raise SourceError('artifact_integrity', 'Transcript integrity verification failed; upload a new source.')
        chunks = chunk_transcript(content)
        checkpoints = TranscriptCheckpoints(repository) if provider.space_id != HASH_SPACE else None
        start_offset = checkpoints.begin(claim, chunks) if checkpoints else 0
        if start_offset is None:
            return False
        if not stage('embedding', min(85, 50 + 35 * start_offset // len(chunks))):
            return False
        segments = []
        input_tokens = 0
        batches = 0
        for offset in range(start_offset, len(chunks), BATCH_SIZE):
            if not stage('embedding', min(85, 50 + int(35 * offset / len(chunks)))):
                return False
            if checkpoints and (batches >= MAX_BATCHES_PER_DELIVERY or perf_counter() - started > 48):
                if checkpoints.continue_later(claim):
                    LOGGER.info(json.dumps({'event': 'processing_continuation', 'job_id': str(job), 'generation': generation,
                                            'processed_segments': offset, 'total_segments': len(chunks)}))
                return False
            batch = chunks[offset:offset + BATCH_SIZE]
            embedded = provider.embed_documents([chunk.text for chunk in batch])
            input_tokens = None if input_tokens is None or embedded.input_tokens is None else input_tokens + embedded.input_tokens
            batch_segments = []
            for index, (chunk, vector) in enumerate(zip(batch, embedded.vectors, strict=True), offset):
                batch_segments.append(EvidenceSegment(
                    id=segment_id(source, generation, chunk, index), tenant_id=tenant, project_id=project, source_id=source,
                    modality='transcript', start_ms=chunk.start_ms, end_ms=chunk.end_ms, generation=generation,
                    text=chunk.text, embedding=vector, embedding_space=provider.space_id, processing_version=f'{PROCESSING_VERSION}:g{generation}',
                ))
            if checkpoints:
                if not checkpoints.save(claim, offset, batch_segments, [(chunk.cue_start, chunk.cue_end) for chunk in batch], embedded.input_tokens):
                    return False
                LOGGER.info(json.dumps({'event': 'embedding_checkpoint', 'job_id': str(job), 'generation': generation,
                                        'processed_segments': offset + len(batch), 'total_segments': len(chunks)}))
            else:
                segments.extend(batch_segments)
            batches += 1
        if not stage('indexing', 90):
            return False
        completed = checkpoints.finish(claim) if checkpoints else repository.complete(claim, segments, [(chunk.cue_start, chunk.cue_end) for chunk in chunks], provider.name, provider.model,
                                        round((perf_counter() - started) * 1000), embedding_space=provider.space_id,
                                        dimensions=provider.dimensions, model_digest=provider.model_digest, input_tokens=input_tokens)
        if completed:
            LOGGER.info(json.dumps({'event': 'processing_completed', 'job_id': str(job), 'stage': 'ready', 'segment_count': len(chunks),
                                    'embedding_provider': provider.name, 'embedding_model': provider.model, 'embedding_dimensions': provider.dimensions}))
        return completed
    except SourceError as exc:
        repository.fail(claim, exc)
    except SoftTimeLimitExceeded:
        repository.fail(claim, SourceError('job_timeout', 'Processing exceeded its time limit; retry a smaller transcript.', transient=True))
    except Exception:
        # Never store or emit raw parser/provider/SQL exceptions, which may contain input or credentials.
        repository.fail(claim, SourceError('processing_unavailable', 'Processing is temporarily unavailable; retry shortly.', transient=True))
    return False
