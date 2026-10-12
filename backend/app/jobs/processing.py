import hashlib
import json
import logging
from time import perf_counter
from uuid import UUID

from billiard.exceptions import SoftTimeLimitExceeded

from ..models import EvidenceSegment
from ..local_embeddings import build_embedding_provider, BATCH_SIZE, MAX_SEMANTIC_CHUNKS
from ..embedding_profiles import HASH_SPACE
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
                                    'stage': name, 'attempt': claim['attempt_count']}))
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
        if not stage('parsing', 20):
            return False
        content = repository.artifacts.get(claim['artifact']['object_key'], repository.settings.upload_limit_bytes)
        if hashlib.sha256(content).hexdigest() != claim['artifact']['content_sha256']:
            raise SourceError('artifact_integrity', 'Transcript integrity verification failed; upload a new source.')
        chunks = chunk_transcript(content)
        if not stage('embedding', 50):
            return False
        provider = build_embedding_provider(repository.settings)
        if provider.space_id != HASH_SPACE and len(chunks) > MAX_SEMANTIC_CHUNKS:
            raise SourceError('semantic_transcript_limit', 'Local semantic mode accepts up to 128 chunks. Split this transcript into smaller files.')
        segments = []
        input_tokens = 0
        for offset in range(0, len(chunks), BATCH_SIZE):
            if not stage('embedding', min(85, 50 + int(35 * offset / len(chunks)))):
                return False
            if provider.space_id != HASH_SPACE and perf_counter() - started > 48:
                raise SourceError('job_timeout', 'Local semantic processing exceeded its CPU budget. Retry a smaller transcript.', transient=True)
            batch = chunks[offset:offset + BATCH_SIZE]
            embedded = provider.embed_documents([chunk.text for chunk in batch])
            input_tokens = None if input_tokens is None or embedded.input_tokens is None else input_tokens + embedded.input_tokens
            for index, (chunk, vector) in enumerate(zip(batch, embedded.vectors, strict=True), offset):
                segments.append(EvidenceSegment(
                    id=segment_id(source, generation, chunk, index), tenant_id=tenant, project_id=project, source_id=source,
                    modality='transcript', start_ms=chunk.start_ms, end_ms=chunk.end_ms, generation=generation,
                    text=chunk.text, embedding=vector, embedding_space=provider.space_id, processing_version=f'{PROCESSING_VERSION}:g{generation}',
                ))
        if not stage('indexing', 90):
            return False
        completed = repository.complete(claim, segments, [(chunk.cue_start, chunk.cue_end) for chunk in chunks], provider.name, provider.model,
                                        round((perf_counter() - started) * 1000), embedding_space=provider.space_id,
                                        dimensions=provider.dimensions, model_digest=provider.model_digest, input_tokens=input_tokens)
        if completed:
            LOGGER.info(json.dumps({'event': 'processing_completed', 'job_id': str(job), 'stage': 'ready', 'segment_count': len(segments),
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
