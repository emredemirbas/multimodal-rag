"""Private bounded selection provenance; no native decoder, pixels or OCR."""
from fractions import Fraction
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .media import MAX_FRAMES, VideoInfo

CHANGE_POLICY = "visual-change1s-d24-p002-anchors4-cap20-gray960x540-temporal-png-v1"
MAX_SCAN_FRAMES = 600
SCAN_INTERVAL_MS = 1000
MAX_WIDTH, MAX_HEIGHT = 160, 90
PIXEL_DELTA = 24
MIN_CHANGED_PPM = 2000
ANCHORS = 4


def selection_indices(stamps, counts, differences, pixels, duration_ms):
    """Shared deterministic ranking, called only after validating the scan."""
    anchors = {min(range(len(stamps)), key=lambda index:
        (abs(stamps[index] - ordinal * (duration_ms - 1) // (ANCHORS - 1)), stamps[index]))
        for ordinal in range(ANCHORS)}
    eligible = [index for index, count in enumerate(counts) if count * 1_000_000 // pixels >= MIN_CHANGED_PPM]
    # Rank the same integer-ppm fraction as the original experiment.
    ranked = sorted(eligible, key=lambda index: (-(counts[index] * 1_000_000 // pixels),
        -differences[index], stamps[index]))
    selected = set(anchors)
    for index in ranked:
        if len(selected) >= MAX_FRAMES:
            break
        selected.add(index)
    return anchors, eligible, selected


class ScanPoint(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    timestamp_ms: int = Field(ge=0, lt=600_000)
    thumbnail_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    changed_pixel_count: int = Field(ge=0, le=MAX_WIDTH * MAX_HEIGHT)
    mean_absolute_difference_ppm: int = Field(ge=0, le=1_000_000)


class ChangeSelection(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    schema_version: Literal["visual-change-selection-v1"] = "visual-change-selection-v1"
    thumbnail_width: int = Field(ge=1, le=MAX_WIDTH)
    thumbnail_height: int = Field(ge=1, le=MAX_HEIGHT)
    samples: list[ScanPoint] = Field(repr=False, min_length=1, max_length=MAX_SCAN_FRAMES)
    selected_timestamps_ms: list[int] = Field(min_length=1, max_length=MAX_FRAMES)

    def validate_video(self, video: VideoInfo):
        """Recheck timeline, feasible scores and ranking in the parent result."""
        if not 1 <= Fraction(video.fps_numerator, video.fps_denominator) <= 60:
            raise ValueError("Unsupported scan frame rate")
        frame_step = (1000 * video.fps_denominator + video.fps_numerator - 1) // video.fps_numerator
        max_gap = SCAN_INTERVAL_MS + frame_step + 1
        stamps = [point.timestamp_ms for point in self.samples]
        if (stamps[0] != 0 or stamps[-1] >= video.duration_ms
                or video.duration_ms - stamps[-1] > max_gap
                or any(not SCAN_INTERVAL_MS - 1 <= after - before <= max_gap
                       for before, after in zip(stamps, stamps[1:]))):
            raise ValueError("Invalid or incomplete scan timeline")
        size = self.thumbnail_width * self.thumbnail_height
        for index, point in enumerate(self.samples):
            changed, mean = point.changed_pixel_count, point.mean_absolute_difference_ppm
            lower = changed * PIXEL_DELTA * 1_000_000 // (size * 255)
            upper = (changed * 255 + (size - changed) * (PIXEL_DELTA - 1)) * 1_000_000 // (size * 255)
            if changed > size or not lower <= mean <= upper or index == 0 and (changed or mean):
                raise ValueError("Inconsistent scan scores")
        _, _, selected = selection_indices(stamps, [point.changed_pixel_count for point in self.samples],
            [point.mean_absolute_difference_ppm for point in self.samples], size, video.duration_ms)
        expected = [stamps[index] for index in sorted(selected)]
        if self.selected_timestamps_ms != expected:
            raise ValueError("Selection does not match the versioned ranking")
        return self
