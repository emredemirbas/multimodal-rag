"""Configured public boundary, not native readiness or quality certification."""
from typing import Literal
from pydantic import BaseModel


class VideoCapability(BaseModel):
    enabled: bool
    max_bytes: Literal[100_000_000] = 100_000_000
    max_duration_seconds: Literal[600] = 600
    encoding: Literal['h264-avc1-yuv420p'] = 'h264-avc1-yuv420p'
    max_width: Literal[1920] = 1920
    max_height: Literal[1080] = 1080
    max_fps: Literal[60] = 60
    max_selected_frames: Literal[20] = 20
    languages: tuple[Literal['en'], Literal['tr'], Literal['en+tr']] = ('en', 'tr', 'en+tr')
    processing_ttl_seconds: Literal[3600] = 3600


VIDEO_FORM_FIELDS = {'file', 'authorization_mode', 'language', 'idempotency_key', 'retention_acknowledged'}
