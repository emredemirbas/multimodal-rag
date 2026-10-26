"""Trusted queue coordinator only: no native decoding or public evidence writes."""
import json
import logging

from billiard.exceptions import SoftTimeLimitExceeded

from ..sources.contracts import SourceError
from ..sources.video import VideoRepository
from ..vision.checkpoints import VisualCheckpoints
from ..vision.client import LocalVisualClient, VisualError

LOGGER = logging.getLogger('tutorial_workspace.jobs')


def build_visual_provider(settings):
    return LocalVisualClient(settings.visual_base_url)


def process_video(repository, tenant, project, source, job, generation):
    claim = repository.claim_job(tenant, project, source, job, generation, job_types=('visual',))
    if claim is None:
        return False
    video, checkpoints = VideoRepository(repository), VisualCheckpoints(repository)
    try:
        state = video.checkpoint_state(claim)
        if state is None or not state[1]:
            original = video.read_original(claim)
            if original is None:
                return False
            data, record = original
            provider = build_visual_provider(repository.settings)
            identity = state[0] if state else provider.ready(record['requested_language'])
            if identity.language != record['requested_language']:
                raise SourceError('visual_profile_changed', 'Restore the original video OCR language/profile.', 409)
            cursor = checkpoints.begin(claim, data, identity)
            if cursor is None:
                return False
            if not cursor.result_saved:
                if not repository.stage(claim, 'extracting_visuals', 15):
                    return False
                result = provider.extract(data, expected_identity=identity)
                if not checkpoints.save(claim, result):
                    return False
        prepared = video.prepare(claim)
        if prepared:
            LOGGER.info(json.dumps({'event': 'video_prepared', 'tenant_id': tenant, 'project_id': str(project),
                                   'job_id': str(job), 'generation': generation, 'published': False}))
        return prepared
    except VisualError as error:
        repository.fail(claim, SourceError(error.code, 'The local visual service is busy, unavailable or differs from the pinned profile.',
                                           503, transient=error.transient))
    except SourceError as error:
        repository.fail(claim, error)
    except SoftTimeLimitExceeded:
        repository.fail(claim, SourceError('video_timeout', 'Video processing exceeded its delivery limit; retry is bounded.', transient=True))
    except Exception:
        repository.fail(claim, SourceError('video_processing_unavailable', 'Local video processing is temporarily unavailable.', transient=True))
    return False
