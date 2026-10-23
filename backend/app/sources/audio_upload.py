"""Public configuration contract; availability is not native-model readiness."""
from typing import Literal

from pydantic import BaseModel


class AudioCapability(BaseModel):
    enabled: bool
    max_bytes: Literal[20_000_000] = 20_000_000
    max_duration_seconds: Literal[600] = 600
    encoding: Literal['pcm-s16le-16000-mono'] = 'pcm-s16le-16000-mono'
    processing_ttl_seconds: Literal[3600] = 3600


AUDIO_FORM_FIELDS = {'file', 'authorization_mode', 'language', 'idempotency_key', 'retention_acknowledged'}
