import math
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .profile import ENGINE, MODEL, PROFILE, PROVIDER, REVISION
from .wav import SLICE_FRAMES, SAMPLE_RATE

Language = Literal["auto", "en", "tr"]


class AsrIdentity(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    provider: Literal[PROVIDER]
    model: Literal[MODEL]
    revision: Literal[REVISION]
    profile: Literal[PROFILE]
    engine: Literal[ENGINE]
    network_policy: Literal["outbound-denied"]


class SpeechSegment(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    start_ms: int = Field(ge=0, le=30_000)
    end_ms: int = Field(gt=0, le=30_000)
    text: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def valid_interval(self):
        if self.end_ms <= self.start_ms or not self.text.strip() or "\x00" in self.text:
            raise ValueError("Invalid speech segment")
        return self


class TranscriptionSlice(AsrIdentity):
    input_frames: int = Field(ge=1, le=SLICE_FRAMES)
    requested_language: Language
    language: str = Field(pattern=r"^[a-z]{2,3}$")
    language_probability: float = Field(ge=0, le=1)
    duration_ms: int = Field(ge=0, le=40_000)
    segments: list[SpeechSegment] = Field(max_length=100)

    @field_validator("language_probability", mode="before")
    @classmethod
    def finite_probability(cls, value):
        if type(value) not in {float, int} or not math.isfinite(value):
            raise ValueError("Invalid language probability")
        return value

    @model_validator(mode="after")
    def valid_timeline(self):
        duration = (self.input_frames * 1000 + SAMPLE_RATE - 1) // SAMPLE_RATE
        previous_end, characters = 0, 0
        for segment in self.segments:
            if segment.start_ms < previous_end or segment.end_ms > duration:
                raise ValueError("Speech evidence lies outside its audio window")
            previous_end = segment.end_ms
            characters += len(segment.text)
        if characters > 16_000 or (self.requested_language != "auto" and self.language != self.requested_language):
            raise ValueError("Invalid speech language or context size")
        return self


class TranscriptionProvider(Protocol):
    """Future media jobs authorize inputs; the provider never receives credentials/IDs."""
    def ready(self) -> AsrIdentity: ...
    def transcribe(self, pcm: bytes, language: Language = "auto") -> TranscriptionSlice: ...
