import json
from threading import BoundedSemaphore
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from pydantic import ValidationError

from ..sources.contracts import SourceError
from .contracts import AsrIdentity, Language, TranscriptionSlice
from .profile import MAX_RESPONSE_BYTES
from .wav import MAX_PCM_BYTES


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def checked_asr_url(value: str) -> str:
    try:
        url = urlsplit(value)
        port = url.port
        if (url.scheme != "http" or url.hostname not in {"asr", "localhost", "127.0.0.1", "::1"}
                or url.username is not None or url.password is not None or url.query or url.fragment
                or url.path not in {"", "/"} or not port or not 1024 <= port <= 65535
                or (url.hostname == "asr" and port != 8090)):
            raise ValueError()
    except (TypeError, ValueError):
        raise ValueError("ASR must use the private asr:8090 service or a loopback HTTP endpoint") from None
    return value.rstrip("/")


class LocalAsrProvider:
    """No download, proxy, redirect, tool, history, cloud fallback or internal retry."""
    def __init__(self, base_url: str = "http://asr:8090"):
        self.base_url = checked_asr_url(base_url)
        self.opener = build_opener(ProxyHandler({}), NoRedirects())
        self.capacity = BoundedSemaphore(1)

    def _request(self, path: str, data: bytes | None, timeout: float) -> dict:
        request = Request(self.base_url + path, data=data, headers={"Content-Type": "application/octet-stream", "Accept": "application/json"})
        try:
            with self.opener.open(request, timeout=timeout) as response:
                if response.headers.get_content_type() != "application/json":
                    raise ValueError()
                body = response.read(MAX_RESPONSE_BYTES + 1)
            if len(body) > MAX_RESPONSE_BYTES:
                raise ValueError()
            result = json.loads(body)
            if not isinstance(result, dict):
                raise ValueError()
            return result
        except HTTPError as error:
            try:
                failure = json.loads(error.read(1025))
                code = failure.get("code") if isinstance(failure, dict) else None
            except (OSError, ValueError):
                code = None
            finally:
                error.close()
            if error.code == 503 and code == "local_asr_busy":
                raise SourceError("local_asr_busy", "Local transcription is busy; retry later.", 503, transient=True) from None
            raise SourceError("local_asr_unavailable", "Start the local ASR service with its explicitly installed model.", 503, transient=True) from None
        except (URLError, TimeoutError, OSError):
            raise SourceError("local_asr_unavailable", "Local transcription is unavailable or timed out.", 503, transient=True) from None
        except (ValueError, UnicodeError):
            raise SourceError("invalid_asr_response", "The local transcript response could not be validated.", 503) from None

    def ready(self) -> AsrIdentity:
        try:
            return AsrIdentity.model_validate(self._request("/health/ready", None, 2))
        except ValidationError:
            raise SourceError("asr_model_changed", "Restore the approved local transcription model and profile.", 503) from None

    def transcribe(self, pcm: bytes, language: Language = "auto") -> TranscriptionSlice:
        if not isinstance(pcm, bytes) or not pcm or len(pcm) > MAX_PCM_BYTES or len(pcm) % 2 or language not in {"auto", "en", "tr"}:
            raise SourceError("invalid_audio_slice", "Send at most 30 seconds of 16 kHz mono 16-bit PCM.")
        if not self.capacity.acquire(blocking=False):
            raise SourceError("local_asr_busy", "Local transcription is busy; retry later.", 503, transient=True)
        try:
            self.ready()
            try:
                result = TranscriptionSlice.model_validate(self._request("/transcribe?language=" + language, pcm, 40))
                if result.input_frames != len(pcm) // 2 or result.requested_language != language:
                    raise ValueError()
                return result
            except (ValidationError, ValueError):
                raise SourceError("invalid_asr_response", "The local transcript response could not be validated.", 503) from None
        finally:
            self.capacity.release()
