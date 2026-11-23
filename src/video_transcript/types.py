from dataclasses import dataclass
from math import isfinite
from pathlib import Path
from typing import Literal

Platform = Literal["youtube", "facebook", "instagram", "threads", "local"]
Origin = Literal["manual", "automatic", "whisper"]


@dataclass(frozen=True)
class Source:
    platform: Platform
    identifier: str
    url: str | None = None
    path: Path | None = None
    original_url: str | None = None


@dataclass(frozen=True)
class Cue:
    start: float
    end: float
    text: str

    def __post_init__(self):
        if not (isfinite(self.start) and isfinite(self.end) and 0 <= self.start <= self.end):
            raise ValueError("Invalid cue timing")


@dataclass(frozen=True)
class Transcript:
    source: Source
    title: str
    language: str
    origin: Origin
    cues: tuple[Cue, ...]
    model: str | None = None
    original_cues: tuple[Cue, ...] | None = None
    converted_to_traditional: bool = False
    caption_status: str | None = None
