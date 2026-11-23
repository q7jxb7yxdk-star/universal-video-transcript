"""Select a caption track or fall back to local speech recognition."""
from collections.abc import Callable
from contextlib import ExitStack
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from .audio import normalize_audio
from .errors import ErrorCode, TranscriptError
from .sources import parse_source
from .sources.providers import MediaBackend, Track, youtube_tracks
from .types import Transcript
from .whisper import MODELS, normalize_language, prepare_model, transcribe_audio

CHINESE = {"zh", "cmn", "yue"}
LANGUAGE_NAMES = {"english": "en", "japanese": "ja", "korean": "ko", "french": "fr", "spanish": "es"}


def _convert(transcript: Transcript, traditional: bool) -> Transcript:
    code = transcript.language.lower().split("-")[0]
    if transcript.origin == "whisper":
        transcript = replace(transcript, original_cues=transcript.cues)
    if not traditional or code not in CHINESE:
        return transcript
    try:
        from opencc import OpenCC
    except ImportError as exc:
        raise TranscriptError(ErrorCode.DEPENDENCY, "找不到 OpenCC，請執行健康檢查。") from exc
    converter = OpenCC("s2t")
    cues = tuple(replace(cue, text=converter.convert(cue.text)) for cue in transcript.cues)
    return replace(transcript, cues=cues, converted_to_traditional=True)


def _rank(track: Track, preferred: str | None):
    language = track.language.lower()
    base = language.split("-")[0]
    target = preferred.split("-")[0] if preferred else None
    return (language != preferred, base != target, not track.original)


def _best_track(tracks: list[Track], origin: str, preferred: str | None):
    failed = False
    for track in sorted((track for track in tracks if track.origin == origin), key=lambda t: _rank(t, preferred)):
        try:
            cues = track.fetch()
        except Exception:
            failed = True
            continue
        if cues:
            return (track, cues), failed
        failed = True
    return None, failed


def extract(value: str, *, model: str = "turbo", language: str | None = None,
            mode: str = "auto", traditional: bool = True, allow_model_download: bool = False,
            notify: Callable[[str], None] = print) -> Transcript:
    if model not in MODELS or mode not in {"auto", "captions", "whisper"}:
        raise TranscriptError(ErrorCode.INPUT, "模型或擷取模式無效。")
    source = parse_source(value)
    if mode == "captions" and source.path:
        raise TranscriptError(ErrorCode.NO_CAPTIONS, "本機檔案使用 Whisper 模式。")
    language = normalize_language(language)
    title = source.identifier
    caption_status = "skipped"
    with TemporaryDirectory(prefix="video-transcript-") as temp, ExitStack() as stack:
        directory = Path(temp)
        backend = None
        if source.url:
            backend = stack.enter_context(MediaBackend(source, directory, audio_only=mode == "whisper"))
            probe_error = None
            caption_failed = False
            selected = None
            if mode != "whisper":
                youtube = []
                if source.platform == "youtube":
                    try:
                        youtube = youtube_tracks(source, stack)
                    except Exception:
                        caption_failed = True
                preferred = LANGUAGE_NAMES.get(language, language)
                selected, failed = _best_track(youtube, "manual", preferred)
                caption_failed |= failed
                platform_tracks = []
                try:
                    platform_tracks = backend.tracks()
                except TranscriptError as exc:
                    probe_error = exc
                if not selected:
                    selected, failed = _best_track(platform_tracks, "manual", preferred)
                    caption_failed |= failed
                if not selected:
                    # Try the original auto-caption track before any other fallback.
                    selected, failed = _best_track(youtube + platform_tracks, "automatic", preferred)
                    caption_failed |= failed
                if selected:
                    track, cues = selected
                    if backend.info:
                        title = backend.info.get("title") or title
                    return _convert(Transcript(source, title, track.language, track.origin, cues), traditional)
                caption_status = "unavailable" if caption_failed or probe_error else "not_found"
                if mode == "captions":
                    if probe_error:
                        raise probe_error
                    if caption_failed:
                        raise TranscriptError(ErrorCode.CAPTION_LOOKUP, "未能讀取字幕，可能係平台限制或字幕格式不相容。")
                    raise TranscriptError(ErrorCode.NO_CAPTIONS, "冇可取得嘅人工或自動字幕。")
            if probe_error:
                raise probe_error
            metadata = backend.probe()
            title = metadata.get("title") or title
            if not metadata.get("url"):
                raise TranscriptError(ErrorCode.AUDIO, "影片可查閱，但平台未提供可下載嘅音訊。請改用本機檔案。",
                                      caption_status=caption_status)
        model_dir = prepare_model(model, allow_model_download, notify)
        try:
            media = backend.audio() if backend else source.path
            chunks = normalize_audio(media, directory)
        except TranscriptError as exc:
            exc.details.setdefault("caption_status", caption_status)
            raise
        detected_language, raw = transcribe_audio(chunks, model_dir, language)
    transcript = Transcript(source, title, detected_language, "whisper", raw, model=model,
                            caption_status=caption_status)
    return _convert(transcript, traditional)
