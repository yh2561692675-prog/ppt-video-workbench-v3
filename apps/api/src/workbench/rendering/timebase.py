from __future__ import annotations

from dataclasses import dataclass


def us_to_frame_floor(value_us: int, fps: int) -> int:
    if value_us < 0 or fps <= 0:
        raise ValueError("时间和 FPS 必须为正数或零")
    return (value_us * fps) // 1_000_000


def us_to_frame_ceil(value_us: int, fps: int) -> int:
    if value_us < 0 or fps <= 0:
        raise ValueError("时间和 FPS 必须为正数或零")
    return (value_us * fps + 999_999) // 1_000_000


def frame_to_us(frame: int, fps: int) -> int:
    if frame < 0 or fps <= 0:
        raise ValueError("帧和 FPS 必须为正数或零")
    return (frame * 1_000_000) // fps


@dataclass(frozen=True)
class FrameRange:
    start: int
    end: int

    def __post_init__(self) -> None:
        if self.start < 0 or self.end <= self.start:
            raise ValueError("帧范围必须满足 0 <= start < end")

    @property
    def duration(self) -> int:
        return self.end - self.start


def us_range_to_frames(start_us: int, end_us: int, fps: int) -> FrameRange:
    if end_us <= start_us:
        raise ValueError("时间范围必须满足 end > start")
    start = us_to_frame_floor(start_us, fps)
    # Ranges are half-open.  Treat the final microsecond as belonging to the
    # previous frame so a range ending exactly on a frame boundary does not
    # acquire an extra frame from floating-point rounding.
    end = max(start + 1, us_to_frame_ceil(end_us - 1, fps))
    return FrameRange(start, end)


def duration_to_frames(duration_us: int, fps: int) -> int:
    if duration_us < 0 or fps <= 0:
        raise ValueError("时长和 FPS 必须为正数或零")
    return max(1, us_to_frame_ceil(duration_us, fps))
