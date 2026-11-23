"""Read public subtitle tracks and normalize timings."""
import html
import json
import re

from .types import Cue

TIMING = re.compile(r"(?m)^([\d:]+[.,]\d{3})[ \t]+-->[ \t]+([\d:]+[.,]\d{3})[^\n]*\n")
SUPPORTED_FORMATS = ("json3", "vtt", "srt")


def seconds(value: str) -> float:
    result = 0.0
    for part in value.replace(",", ".").split(":"):
        result = result * 60 + float(part)
    return result


def ordered(cues) -> tuple[Cue, ...]:
    return tuple(sorted((cue for cue in cues if cue.text.strip()), key=lambda cue: (cue.start, cue.end)))


def decode_captions(data: bytes, extension: str) -> tuple[Cue, ...]:
    source = data.decode("utf-8-sig")
    if extension == "json3":
        return _json3(source)
    if extension not in {"vtt", "srt"}:
        raise ValueError("Unsupported subtitle format")
    source = source.replace("\r\n", "\n").replace("\r", "\n")
    cues = []
    for block in re.split(r"\n[ \t]*\n", source):
        if block.startswith(("NOTE", "STYLE", "REGION")):
            continue
        timing = TIMING.search(block)
        if timing:
            text = html.unescape(re.sub(r"<[^>]+>", "", block[timing.end():])).strip()
            cues.append(Cue(seconds(timing[1]), seconds(timing[2]), text))
    return ordered(cues)


def _json3(source: str) -> tuple[Cue, ...]:
    events = json.loads(source)["events"]
    cues = []
    for event in events:
        fragments = event.get("segs")
        if not fragments:
            continue
        text = "".join(fragment.get("utf8", "") for fragment in fragments).strip()
        if not text:
            continue
        start = event["tStartMs"] / 1000
        duration = event.get("dDurationMs", 0) / 1000
        end = start + duration
        if event.get("aAppend") and cues and start <= cues[-1].end:
            previous = cues.pop()
            cues.append(Cue(previous.start, max(previous.end, end), f"{previous.text} {text}"))
        else:
            cues.append(Cue(start, end, text))
    return ordered(cues)
