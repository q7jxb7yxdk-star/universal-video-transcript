"""UTF-8 text, SubRip, and Obsidian-compatible Markdown."""
from dataclasses import asdict
import html
import json
import os
from pathlib import Path
import re
from tempfile import TemporaryDirectory
import unicodedata

from .errors import ErrorCode, TranscriptError
from .types import Transcript

EXTENSIONS = {"txt": "txt", "srt": "srt", "markdown": "md"}
PLATFORMS = {"youtube": "YouTube", "facebook": "Facebook", "instagram": "Instagram",
             "threads": "Threads", "local": "本機檔案"}
ORIGINS = {"manual": "人工字幕", "automatic": "平台自動字幕", "whisper": "本機 Whisper"}


def _clock(milliseconds: int, *, subrip: bool = False) -> str:
    seconds, fraction = divmod(milliseconds, 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if subrip:
        return f"{hours:02}:{minutes:02}:{seconds:02},{fraction:03}"
    short = f"{minutes:02}:{seconds:02}"
    return f"{hours:02}:{short}" if hours else short


def _markdown(value: str) -> str:
    escaped = html.escape(value, quote=False)
    return re.sub(r"([\\`*_{}\[\]()#!|~+\-])", r"\\\1", escaped)


def render(transcript: Transcript, format: str, timestamps: bool) -> str:
    if format == "srt":
        blocks = []
        for i, cue in enumerate(transcript.cues, 1):
            start_ms = round(cue.start * 1000)
            end_ms = max(start_ms + 1, round(cue.end * 1000))
            timing = f"{_clock(start_ms, subrip=True)} --> {_clock(end_ms, subrip=True)}"
            text = "\n".join(line for line in cue.text.splitlines() if line.strip())
            blocks.append(f"{i}\n{timing}\n{text}")
        return "\n\n".join(blocks) + "\n"
    if format not in EXTENSIONS:
        raise TranscriptError(ErrorCode.INPUT, "不支援指定輸出格式。")

    markdown = format == "markdown"
    lines = []
    for cue in transcript.cues:
        start = f"[{_clock(int(cue.start * 1000))}] " if timestamps else ""
        text = cue.text
        if markdown:
            text = "  \n".join(_markdown(line) for line in text.splitlines() if line.strip())
            # A leading timestamp can look like a reference link beside square brackets.
            start = _markdown(start)
        lines.append(start + text)
    if not markdown:
        return "\n".join(lines) + "\n"

    title = " ".join(transcript.title.split())
    location = transcript.source.original_url or transcript.source.url
    language = transcript.language
    if transcript.converted_to_traditional:
        language += "（繁體中文）"
    origin = ORIGINS[transcript.origin]
    if transcript.model:
        origin += f"（{transcript.model}）"
    header = [
        f"# {_markdown(title)}",
        "",
        f"來源：{PLATFORMS[transcript.source.platform]}  ",
    ]
    if location:
        header.append(f"網址：{_markdown(location)}  ")
    header.extend([f"語言：{_markdown(language)}  ", f"字幕來源：{origin}", "", "## Transcript", ""])
    return "\n".join(header) + "\n" + "\n\n".join(lines) + "\n"


def _safe_stem(value: str) -> str:
    value = unicodedata.normalize("NFC", value)
    value = "".join(char if not unicodedata.category(char).startswith("C") else " " for char in value)
    value = re.sub(r'[<>:"/\\|?*]+', " ", value)
    value = " ".join(value.split()).strip(". ")
    return value.encode("utf-8")[:170].decode("utf-8", errors="ignore").strip(". ") or "transcript"


def _original_json(transcript: Transcript) -> str:
    data = {
        "schema_version": 1,
        "language": transcript.language,
        "model": transcript.model,
        "segments": [asdict(cue) for cue in transcript.original_cues or ()],
    }
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def save(transcript: Transcript, directory: Path, format: str, timestamps: bool):
    output = render(transcript, format, timestamps)
    stem = _safe_stem(transcript.title)
    original = transcript.original_cues is not None
    try:
        directory = directory.expanduser().resolve()
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        with TemporaryDirectory(prefix=".video-transcript-", dir=directory) as staging:
            source = Path(staging) / "transcript"
            source.write_text(output, encoding="utf-8")
            source.chmod(0o600)
            raw = Path(staging) / "original"
            if original:
                raw.write_text(_original_json(transcript), encoding="utf-8")
                raw.chmod(0o600)

            for number in range(1, 10_001):
                basename = stem if number == 1 else f"{stem} ({number})"
                path = directory / f"{basename}.{EXTENSIONS[format]}"
                raw_path = directory / f"{basename}.original.json" if original else None
                created = False
                try:
                    if raw_path:
                        os.link(raw, raw_path)
                        created = True
                    os.link(source, path)
                except OSError as exc:
                    if created:
                        raw_path.unlink()
                    if isinstance(exc, FileExistsError):
                        continue
                    raise
                return path, raw_path
    except OSError as exc:
        raise TranscriptError(ErrorCode.OUTPUT, f"未能寫入輸出目錄（{type(exc).__name__}）。") from exc
    raise TranscriptError(ErrorCode.OUTPUT, "未能產生未使用嘅字幕檔名。")
