"""Ordinary text embedding task; never constructs a native visual provider."""
from time import perf_counter

from billiard.exceptions import SoftTimeLimitExceeded

from ..local_embeddings import BATCH_SIZE, build_embedding_provider
from ..sources.contracts import SourceError
from ..vision.index import VisualIndexRepository


def index_visual(repository, tenant, project, source, job, generation):
    claim = repository.claim_job(tenant, project, source, job, generation, job_types=('visual_index',))
    if claim is None: return False
    started = perf_counter()
    try:
        provider = build_embedding_provider(repository.settings)
        checkpoints = VisualIndexRepository(repository)
        state = checkpoints.begin(claim, provider)
        if state is None: return False
        offset, chunks = state
        batches = 0
        while offset < len(chunks):
            if batches >= 8 or perf_counter()-started > 48:
                checkpoints.continue_later(claim)
                return False
            # Revalidate after every previous batch and immediately before inference.
            if not repository.stage(claim, 'embedding', 10+80*offset//len(chunks)): return False
            items = chunks[offset:offset+BATCH_SIZE]
            batch = provider.embed_documents([item['text'] for item in items])
            if not checkpoints.save(claim, offset, batch): return False
            offset += len(items)
            batches += 1
        return checkpoints.finish(claim, provider)
    except SourceError as error:
        repository.fail(claim, error)
    except SoftTimeLimitExceeded:
        repository.fail(claim, SourceError('job_timeout', 'OCR indexing exceeded its time limit; free local resources and retry.', transient=True))
    except Exception:
        repository.fail(claim, SourceError('processing_unavailable', 'OCR indexing is temporarily unavailable; retry shortly.', transient=True))
    return False
