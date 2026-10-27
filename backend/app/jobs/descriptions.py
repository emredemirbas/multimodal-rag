"""One local image per delivery, durable result before continuation/index handoff."""
from billiard.exceptions import SoftTimeLimitExceeded
from ..sources.contracts import SourceError
from ..vision.descriptions import DescriptionRepository
from ..vision.descriptions_client import DescriptionIdentity, LocalDescriptionProvider
from ..vision.gallery import VisualGalleryRepository


def describe_frames(repository,tenant,project,source,job,generation):
    claim = repository.claim_job(tenant,project,source,job,generation,job_types=('visual_describe',))
    if claim is None: return False
    try:
        checkpoints = DescriptionRepository(repository)
        state = checkpoints.next(claim)
        if state is None: return False
        run,frames,offset = state
        if offset == len(frames): return checkpoints.advance(claim)
        provider = LocalDescriptionProvider(repository.settings.ollama_base_url,run['model_digest'])
        if run['identity'] is None:
            identity = provider.ready()
            if checkpoints.next(claim,identity) is None: return False
        else: identity = DescriptionIdentity.model_validate(run['identity'])
        frame = frames[offset]
        if not repository.stage(claim,'describing_frames',10+offset*80//len(frames)): return False
        image = VisualGalleryRepository(repository).image(tenant,project,frame['id'],claim['actor_user_id'])
        # Object/model I/O never holds a project lock; fence again before and after.
        if checkpoints.next(claim) is None: return False
        result = provider.describe(image,frame['width'],frame['height'],identity)
        if not checkpoints.save(claim,offset,result): return False
        return checkpoints.advance(claim)
    except SourceError as error: repository.fail(claim,error)
    except SoftTimeLimitExceeded:
        repository.fail(claim,SourceError('job_timeout','Local frame description exceeded its time budget; free resources and retry.',503,transient=True))
    except Exception:
        repository.fail(claim,SourceError('processing_unavailable','Local description processing is unavailable; retry shortly.',503,transient=True))
    return False
