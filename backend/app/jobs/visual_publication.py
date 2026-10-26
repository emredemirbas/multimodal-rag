"""Trusted copying/inspection preparation only, never decoding or index activation."""
from billiard.exceptions import SoftTimeLimitExceeded

from ..sources.contracts import SourceError
from ..vision.gallery import VisualGalleryRepository


def publish_visual(repository, tenant, project, source, job, generation):
    claim = repository.claim_job(tenant, project, source, job, generation, job_types=('visual_publish',))
    if claim is None: return False
    try:
        return VisualGalleryRepository(repository).adopt_next(claim)
    except SourceError as error:
        repository.fail(claim, error)
    except SoftTimeLimitExceeded:
        repository.fail(claim, SourceError('visual_adoption_timeout', 'Frame preparation exceeded its delivery limit; retry is bounded.', transient=True))
    except Exception:
        repository.fail(claim, SourceError('visual_adoption_unavailable', 'Frame preparation is temporarily unavailable.', transient=True))
    return False
