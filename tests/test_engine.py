from pathlib import Path
import sys
import types

import pytest

from video_transcript import engine, whisper
from video_transcript.errors import ErrorCode, TranscriptError
from video_transcript.sources import parse_source
from video_transcript.sources.providers import Track
from video_transcript.types import Cue, Source, Transcript


@pytest.mark.parametrize(("url", "platform", "identifier"), [
    ("https://youtu.be/abcdefghijk", "youtube", "abcdefghijk"),
    ("https://www.facebook.com/watch/?v=12345", "facebook", "12345"),
    ("https://www.instagram.com/reel/Ab_123/", "instagram", "Ab_123"),
    ("https://www.threads.net/@user/post/Ab123", "threads", "Ab123"),
])
def test_parse_supported_platforms(url, platform, identifier):
    source = parse_source(url)
    assert (source.platform, source.identifier) == (platform, identifier)
    assert source.url.startswith("https://")


@pytest.mark.parametrize("value", [
    "https://youtube.com/watch?v=short", "https://example.com/video",
    "https://user@youtube.com/watch?v=abcdefghijk", "https://youtube.com:443/watch?v=abcdefghijk",
    "https://youtube.com/watch?v=abcdefghijk bad", "ftp://youtu.be/abcdefghijk",
])
def test_parse_invalid_source(value):
    with pytest.raises(TranscriptError) as error:
        parse_source(value)
    assert error.value.code == ErrorCode.INPUT


def test_parse_local_file(tmp_path):
    media = tmp_path / "clip.MP4"
    media.write_bytes(b"media")
    assert parse_source(str(media)) == Source("local", "clip", path=media)
    with pytest.raises(TranscriptError) as error:
        parse_source(str(tmp_path / "missing.mp4"))
    assert error.value.code == ErrorCode.INPUT
    other = tmp_path / "clip.txt"
    other.touch()
    with pytest.raises(TranscriptError) as error:
        parse_source(str(other))
    assert error.value.code == ErrorCode.INPUT


URL = "https://youtu.be/abcdefghijk"
CUES = (Cue(0, 1, "hello"),)


class FakeBackend:
    instances = []
    track_list = []
    track_error = None
    metadata = {"title": "Video", "url": "https://media.invalid/audio"}
    audio_error = None

    def __init__(self, source, directory, **kwargs):
        self.directory = directory
        self.info = None
        self.closed = False
        self.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.closed = True

    def tracks(self):
        if self.track_error:
            raise self.track_error
        self.info = self.metadata
        return self.track_list

    def probe(self):
        return self.metadata

    def audio(self):
        if self.audio_error:
            raise self.audio_error
        return self.directory / "audio.wav"


@pytest.fixture
def backend(monkeypatch):
    FakeBackend.instances = []
    FakeBackend.track_list = []
    FakeBackend.track_error = None
    FakeBackend.metadata = {"title": "Video", "url": "https://media.invalid/audio"}
    FakeBackend.audio_error = None
    monkeypatch.setattr(engine, "MediaBackend", FakeBackend)
    monkeypatch.setattr(engine, "youtube_tracks", lambda *args: [])
    return FakeBackend


def test_manual_tracks_from_both_backends_precede_automatic(backend, monkeypatch):
    calls = []
    def track(name, origin, fail=False):
        def fetch():
            calls.append(name)
            if fail:
                raise ValueError("unavailable")
            return CUES
        return Track(origin, "en", fetch)
    monkeypatch.setattr(engine, "youtube_tracks", lambda *args: [
        track("youtube manual", "manual", True), track("youtube auto", "automatic")])
    backend.track_list = [track("platform manual", "manual"), track("platform auto", "automatic")]
    result = engine.extract(URL, mode="captions")
    assert result.origin == "manual"
    assert calls == ["youtube manual", "platform manual"]
    assert backend.instances[0].closed
    assert not backend.instances[0].directory.exists()


@pytest.mark.parametrize(("condition", "expected"), [
    ("none", ErrorCode.NO_CAPTIONS),
    ("failed", ErrorCode.CAPTION_LOOKUP),
    ("inaccessible", ErrorCode.INACCESSIBLE),
])
def test_caption_failure_categories_and_cleanup(backend, condition, expected):
    if condition == "failed":
        def fail():
            raise ValueError("unreadable")
        backend.track_list = [Track("manual", "en", fail)]
    elif condition == "inaccessible":
        backend.track_error = TranscriptError(ErrorCode.INACCESSIBLE, "unavailable")
    with pytest.raises(TranscriptError) as error:
        engine.extract(URL, mode="captions")
    assert error.value.code == expected
    assert backend.instances[0].closed
    assert not backend.instances[0].directory.exists()


@pytest.mark.parametrize(("caption_failed", "status"), [(False, "not_found"), (True, "unavailable")])
def test_audio_failure_preserves_caption_status(backend, monkeypatch, caption_failed, status):
    if caption_failed:
        monkeypatch.setattr(engine, "youtube_tracks", lambda *args: (_ for _ in ()).throw(ValueError()))
    backend.metadata = {"title": "Video"}
    with pytest.raises(TranscriptError) as error:
        engine.extract(URL)
    assert error.value.code == ErrorCode.AUDIO
    assert error.value.details["caption_status"] == status
    assert backend.instances[0].closed
    assert not backend.instances[0].directory.exists()


def test_whisper_conversion_keeps_original_cues(monkeypatch):
    class Converter:
        def __init__(self, config):
            assert config == "s2t"
        def convert(self, text):
            return text.replace("汉", "漢")
    monkeypatch.setitem(sys.modules, "opencc", types.SimpleNamespace(OpenCC=Converter))
    original = (Cue(0, 1, "汉字"),)
    transcript = Transcript(Source("local", "clip", path=Path("clip.wav")), "clip", "zh", "whisper", original)
    converted = engine._convert(transcript, True)
    assert converted.original_cues == original
    assert converted.cues == (Cue(0, 1, "漢字"),)
    assert converted.converted_to_traditional


def test_transcribe_chunks_offsets_and_selected_language(monkeypatch):
    chunks = [Path("one.wav"), Path("two.wav")]
    samples = {chunks[0]: ("first", 32000), chunks[1]: ("second", 16000)}
    calls = []
    def transcribe(audio, **kwargs):
        calls.append((audio, kwargs))
        return {"language": "en", "segments": [{"start": 0.25, "end": 1.5, "text": " words "}]}
    monkeypatch.setattr(whisper, "_transcriber", lambda model: transcribe)
    monkeypatch.setattr(whisper, "read_pcm", lambda chunk: samples[chunk])
    monkeypatch.setattr(whisper, "whisper_language", lambda language: "ja" if language == "japanese" else language)
    language, cues = whisper.transcribe_audio(chunks, Path("model"), "japanese")
    assert language == "ja"
    assert cues == (Cue(0.25, 1.5, "words"), Cue(2.25, 3.0, "words"))
    assert [call[0] for call in calls] == ["first", "second"]
    assert all(call[1]["language"] == "ja" for call in calls)
