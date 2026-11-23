from dataclasses import replace
from pathlib import Path
import re
from urllib.parse import urlsplit

from ..errors import ErrorCode, TranscriptError
from ..types import Source
from . import facebook, instagram, threads, youtube

PARSERS = {
    host: module.parse
    for module in (youtube, facebook, instagram, threads)
    for host in module.HOSTS
}
LOCAL_TYPES = {".mp4", ".mov", ".mp3", ".m4a", ".wav"}


def parse_source(value: str) -> Source:
    if not re.match(r"^[a-z][a-z0-9+.-]*://", value, re.I):
        try:
            path = Path(value).expanduser().resolve(strict=True)
        except (OSError, RuntimeError, ValueError) as exc:
            raise TranscriptError(ErrorCode.INPUT, "找不到本機檔案。") from exc
        if not path.is_file() or path.suffix.lower() not in LOCAL_TYPES:
            raise TranscriptError(ErrorCode.INPUT, "請提供 MP4、MOV、MP3、M4A 或 WAV 檔案。")
        return Source("local", path.stem, path=path)

    if any(character.isspace() or ord(character) < 32 for character in value):
        raise TranscriptError(ErrorCode.INPUT, "網址包含空白或控制字元。")
    try:
        url = urlsplit(value)
        parser = PARSERS.get(url.hostname)
        if (url.scheme not in {"http", "https"} or not parser or url.port is not None
                or url.username is not None or "\\" in value):
            raise ValueError()
        return replace(parser(url), original_url=value)
    except ValueError as exc:
        raise TranscriptError(ErrorCode.INPUT, "請提供支援平台的單一影片或貼文網址。") from exc
