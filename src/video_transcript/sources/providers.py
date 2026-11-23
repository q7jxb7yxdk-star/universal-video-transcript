"""Caption and media access using anonymous upstream clients."""
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
import re
import shutil
from urllib.parse import urlsplit

from ..captions import SUPPORTED_FORMATS, decode_captions, ordered
from ..errors import ErrorCode, TranscriptError
from ..types import Cue, Origin, Source

CAPTION_LIMIT = 24 * 1024 * 1024
RESTRICTED = {"private", "premium_only", "subscriber_only", "needs_auth"}


@dataclass(frozen=True)
class Track:
    origin: Origin
    language: str
    fetch: Callable[[], tuple[Cue, ...]]
    original: bool = False


def _access_error(source: Source, error: Exception) -> TranscriptError:
    message = str(error).lower()
    reasons = (
        (("login", "log in", "sign in", "cookies", "private", "members-only", "subscriber"),
         "平台要求登入，或影片只對指定用戶開放。"),
        (("live or upcoming",), "直播或未開始嘅影片暫時無法處理。"),
        (("drm", "encrypted"), "影片有 DRM 或加密保護。"),
        (("unsupported url", "no video", "no media"), "擷取器未能喺貼文找到可公開取得嘅影片。"),
        (("removed", "unavailable", "404"), "影片已移除、地區受限，或目前無法存取。"),
        (("403", "429", "blocked", "rate limit"), "平台拒絕或限制存取。"),
        (("timed out", "timeout", "connection", "certificate", "network"), "連線或平台回應失敗。"),
    )
    explanation = next((reason for keys, reason in reasons if any(key in message for key in keys)),
                       "平台未能提供可用嘅影片資料。")
    return TranscriptError(ErrorCode.INACCESSIBLE, f"{explanation} 請提供你有權處理嘅本機檔案。",
                           platform=source.platform)


def youtube_tracks(source: Source, stack) -> list[Track]:
    from requests import Session
    from youtube_transcript_api import NoTranscriptFound, TranscriptsDisabled, YouTubeTranscriptApi

    class TimedSession(Session):
        def request(self, *args, **kwargs):
            kwargs.setdefault("timeout", 15)
            return super().request(*args, **kwargs)

    def fetch(item):
        return ordered(Cue(row.start, row.start + row.duration, row.text) for row in item.fetch())

    session = stack.enter_context(TimedSession())
    session.trust_env = False
    try:
        transcripts = YouTubeTranscriptApi(http_client=session).list(source.identifier)
    except (NoTranscriptFound, TranscriptsDisabled):
        return []
    return [
        Track("automatic" if item.is_generated else "manual", item.language_code,
              lambda item=item: fetch(item))
        for item in transcripts
    ]



class QuietLogger:
    def debug(self, message):
        pass

    def warning(self, message):
        pass

    def error(self, message):
        pass


class MediaBackend:
    def __init__(self, source: Source, directory: Path, *, audio_only: bool = False):
        from yt_dlp import YoutubeDL
        from yt_dlp.globals import plugin_dirs

        self.source = source
        self.directory = directory
        self.info = None
        self.rejection = None
        node = shutil.which("node")
        options = {
            "quiet": True,
            "noprogress": True,
            "logger": QuietLogger(),
            "no_warnings": True,
            "noplaylist": True,
            "playlistend": 2,
            "cachedir": False,
            "cookiefile": None,
            "cookiesfrombrowser": None,
            "usenetrc": False,
            "allowed_extractors": ["default"],
            "enable_file_urls": False,
            "allow_unplayable_formats": False,
            "remote_components": set(),
            "js_runtimes": {"node": {"path": node}} if node else {},
            "extractor_args": {"youtube": {"skip": ["translated_subs"]}},
            "socket_timeout": 15,
            "retries": 1,
            "fragment_retries": 1,
            "extractor_retries": 0,
            "format": "bestaudio/best",
            "ignore_no_formats_error": not audio_only,
            "outtmpl": {"default": str(directory / "media.%(ext)s")},
            "match_filter": self._match,
        }
        # yt-dlp stores plugin search paths on the package, not on the downloader.
        plugin_dirs.value = []
        self.client = YoutubeDL(options)

    def _match(self, info, *, incomplete=False):
        if info.get("availability") in RESTRICTED:
            self.rejection = "Private video or login required"
        elif info.get("has_drm") is True:
            self.rejection = "DRM-protected media"
        elif info.get("is_live") or info.get("live_status") in {"is_upcoming", "post_live"}:
            self.rejection = "Live or upcoming videos are unsupported"
        else:
            return None
        return self.rejection

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.client.close()

    def probe(self):
        if self.info is None:
            from yt_dlp.utils import DownloadError

            try:
                info = self.client.extract_info(self.source.url, download=False)
                if not info:
                    raise ValueError(self.rejection or "Unavailable media")
                if "entries" in info:
                    entries = [entry for entry in info["entries"] if entry]
                    if len(entries) != 1:
                        raise ValueError("No video or multiple media entries")
                    info = entries[0]
                rejection = self._match(info)
                if rejection:
                    raise ValueError(rejection)
            except (DownloadError, ValueError) as exc:
                raise _access_error(self.source, exc) from exc
            self.info = info
        return self.info

    def tracks(self) -> list[Track]:
        info = self.probe()
        tracks = []
        for origin, key in (("manual", "subtitles"), ("automatic", "automatic_captions")):
            for language, formats in (info.get(key) or {}).items():
                if not re.fullmatch(r"[A-Za-z0-9-]{2,40}", language) or language == "live_chat":
                    continue
                candidates = [
                    item
                    for extension in SUPPORTED_FORMATS
                    for item in formats
                    if item.get("ext") == extension and (item.get("url") or item.get("data"))
                ]
                tracks.append(
                    Track(origin, language.removesuffix("-orig"),
                          lambda candidates=candidates: self._fetch_track(candidates),
                          language.endswith("-orig"))
                )
        return tracks

    def _fetch_track(self, candidates) -> tuple[Cue, ...]:
        from yt_dlp.networking import Request
        from yt_dlp.networking.exceptions import RequestError

        for item in candidates:
            try:
                if item.get("data"):
                    content = item["data"].encode("utf-8")
                else:
                    url = urlsplit(item["url"])
                    if url.scheme not in {"http", "https"} or url.username is not None:
                        continue
                    request = Request(item["url"], headers=item.get("http_headers"))
                    with self.client.urlopen(request) as response:
                        content = response.read(CAPTION_LIMIT + 1)
                if len(content) <= CAPTION_LIMIT:
                    cues = decode_captions(content, item["ext"])
                    if cues:
                        return cues
            except (RequestError, OSError, ValueError, TypeError, KeyError):
                continue
        raise ValueError("Caption payload unavailable or unsupported")

    def audio(self) -> Path:
        from yt_dlp.utils import DownloadError

        info = self.probe()
        if not info.get("url"):
            raise TranscriptError(ErrorCode.AUDIO, "平台未有提供可下載嘅音訊，請改用本機檔案。")
        try:
            self.client.process_info(info.copy())
        except DownloadError as exc:
            raise TranscriptError(ErrorCode.AUDIO, "下載音訊失敗，請改用本機檔案。") from exc
        files = [path for path in self.directory.glob("media.*")
                 if path.is_file() and path.suffix not in {".part", ".ytdl"}]
        if len(files) != 1 or files[0].stat().st_size == 0:
            raise TranscriptError(ErrorCode.AUDIO, "下載後找不到可用嘅音訊，請改用本機檔案。")
        return files[0]
