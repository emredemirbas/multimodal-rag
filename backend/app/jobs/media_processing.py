"""One bounded speech window per real queue delivery; no model in the API."""
import json
import logging
from uuid import UUID

from billiard.exceptions import SoftTimeLimitExceeded

from ..asr.checkpoints import AsrCheckpoints
from ..asr.client import LocalAsrProvider
from ..asr.wav import SLICE_FRAMES, pcm_slice, validate_wav
from ..sources.contracts import SourceError
from ..sources.media import MediaRepository
from ..sources.repository import SourceRepository

LOGGER = logging.getLogger('tutorial_workspace.jobs')


def build_transcription_provider(settings):
    return LocalAsrProvider(settings.asr_base_url)


def process_audio(repository: SourceRepository, tenant: str, project: UUID, source: UUID, job: UUID, generation: int) -> bool:
    claim = repository.claim_job(tenant, project, source, job, generation, job_types=('asr',))
    if claim is None:
        return False
    media, checkpoints = MediaRepository(repository), AsrCheckpoints(repository)
    try:
        original = media.read_original(claim)
        if original is None:
            return False
        content, record = original
        info = validate_wav(claim['source'].filename, content)
        cursor = checkpoints.begin(claim, info.filename, content, record['requested_language'])
        if cursor is None:
            return False
        if cursor.next_window < cursor.total_windows:
            if not repository.stage(claim, 'transcribing', 10 + 40 * cursor.next_window // cursor.total_windows):
                return False
            result = build_transcription_provider(repository.settings).transcribe(
                pcm_slice(content, info, cursor.next_window * SLICE_FRAMES), record['requested_language'])
            if not checkpoints.save(claim, cursor.next_window, result):
                return False
            if cursor.next_window + 1 < cursor.total_windows:
                media.continue_later(claim, cursor.next_window)
                return False
        if not repository.stage(claim, 'adopting_transcript', 60):
            return False
        adopted = media.adopt(claim)
        if adopted:
            LOGGER.info(json.dumps({'event': 'audio_transcribed', 'job_id': str(job), 'generation': generation,
                                    'windows': cursor.total_windows, 'input_frames': info.frames}))
        return adopted
    except SourceError as error:
        repository.fail(claim, error)
    except SoftTimeLimitExceeded:
        repository.fail(claim, SourceError('audio_timeout', 'Local transcription exceeded its delivery limit; it will retry within bounded attempts.', transient=True))
    except Exception:
        repository.fail(claim, SourceError('audio_processing_unavailable', 'Local transcription is temporarily unavailable.', transient=True))
    return False
