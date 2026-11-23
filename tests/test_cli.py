"""Offline CLI, filesystem and FFmpeg integration checks."""
from contextlib import ExitStack
import json
import os
from pathlib import Path
import shutil
import subprocess
import wave

import pytest

from video_transcript import cli
from video_transcript.audio import normalize_audio, read_pcm
from video_transcript.captions import decode_captions
from video_transcript.errors import ErrorCode, TranscriptError
from video_transcript.export import render, save
from video_transcript.sources import parse_source
from video_transcript.sources.providers import MediaBackend, youtube_tracks
from video_transcript.types import Cue, Source, Transcript
from video_transcript.whisper import MODELS, prepare_model

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def sample_transcript():
    source = Source("youtube", "dQw4w9WgXcQ", "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                    original_url="https://youtu.be/dQw4w9WgXcQ")
    return Transcript(source, "測試 / 標題", "yue", "whisper",
                      (Cue(0.005, 1.59, "你好\n世界"), Cue(3600, 3600, "第二句")),
                      model="turbo", original_cues=(Cue(0.005, 1.59, "你好\n世界"),),
                      converted_to_traditional=True)


def test_caption_formats():
    assert decode_captions(
        b"WEBVTT\n\n00:02.000 --> 00:02.500\n<i>Second</i>\n\n"
        b"00:00.250 --> 00:01.350\nFirst &amp; line", "vtt"
    ) == (Cue(0.25, 1.35, "First & line"), Cue(2, 2.5, "Second"))
    assert decode_captions(b"1\r\n00:00:01,000 --> 00:00:02,000\r\nText\r\n", "srt") == (
        Cue(1, 2, "Text"),
    )
    data = {"events": [
        {"tStartMs": 800, "dDurationMs": 500, "segs": [{"utf8": "one"}]},
        {"tStartMs": 900, "dDurationMs": 600, "aAppend": 1, "segs": [{"utf8": "two"}]},
        {"tStartMs": 1500, "dDurationMs": 1000},
    ]}
    assert decode_captions(json.dumps(data).encode(), "json3") == (Cue(0.8, 1.5, "one two"),)


def test_exports(sample_transcript, tmp_path):
    assert render(sample_transcript, "txt", False) == "你好\n世界\n第二句\n"
    assert "[01:00:00] 第二句" in render(sample_transcript, "txt", True)
    assert render(sample_transcript, "srt", False) == (
        "1\n00:00:00,005 --> 00:00:01,590\n你好\n世界\n\n"
        "2\n01:00:00,000 --> 01:00:00,001\n第二句\n"
    )
    first, original = save(sample_transcript, tmp_path, "markdown", True)
    second, original_second = save(sample_transcript, tmp_path, "markdown", False)
    assert first.name == "測試 標題.md"
    assert second.name == "測試 標題 (2).md"
    assert "## Transcript" in first.read_text()
    assert "https://youtu.be/dQw4w9WgXcQ" in first.read_text()
    assert "yue（繁體中文）" in first.read_text()
    assert "本機 Whisper（turbo）" in first.read_text()
    assert r"\[00:00\]" in first.read_text()
    assert "[00:00]" not in second.read_text()
    assert json.loads(original.read_text())["segments"][0]["text"] == "你好\n世界"
    assert original != original_second
    assert first.stat().st_mode & 0o777 == 0o600
    assert not list(tmp_path.glob(".video-transcript-*"))


def test_export_does_not_follow_preexisting_symlinks(sample_transcript, tmp_path):
    outside = tmp_path / "existing.md"
    outside.write_text("existing")
    (tmp_path / "測試 標題.md").symlink_to(outside)
    result, raw = save(sample_transcript, tmp_path, "markdown", False)
    assert outside.read_text() == "existing"
    assert result.name == "測試 標題 (2).md"
    assert raw.is_file()
    assert not (tmp_path / "測試 標題.original.json").exists()


def test_cli_result_is_machine_readable(sample_transcript, monkeypatch, tmp_path, capsys):
    def extract(value, **kwargs):
        assert value == "/file with a ' and ;"
        assert kwargs["language"] == "yue"
        assert kwargs["mode"] == "whisper"
        assert kwargs["model"] == "large-v3"
        assert not kwargs["allow_model_download"]
        return sample_transcript

    monkeypatch.setattr(cli, "extract", extract)
    exit_code = cli.main([
        "--json", "--force-whisper", "--model", "large-v3", "--language", "yue",
        "--format", "txt", "--output-dir", str(tmp_path), "--", "/file with a ' and ;",
    ])
    result = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert result["ok"] and result["origin"] == "whisper"
    assert Path(result["path"]).read_text() == "你好\n世界\n第二句\n"
    assert Path(result["original_path"]).is_file()


def test_cli_invalid_option_as_json(capsys):
    assert cli.main(["--json", "--format", "incorrect"]) == ErrorCode.INPUT
    assert json.loads(capsys.readouterr().out)["code"] == "INPUT"


def test_model_requires_approval_and_reuses_cache(monkeypatch, tmp_path):
    import video_transcript.whisper as whisper
    import huggingface_hub

    monkeypatch.setattr(whisper, "cache_root", lambda: tmp_path / "model cache")
    with pytest.raises(TranscriptError) as missing:
        prepare_model("turbo", False)
    assert missing.value.code == ErrorCode.MODEL_DOWNLOAD_REQUIRED
    assert missing.value.details["size"] == "1.61 GB"
    assert not whisper.cache_root().exists()

    monkeypatch.setattr(whisper.shutil, "disk_usage", lambda _: type("Disk", (), {"free": 10**10})())
    calls = []

    def download(**options):
        assert options["token"] is False
        assert options["allow_patterns"] == ["config.json", "weights.safetensors"]
        calls.append(options)
        path = whisper._snapshot(MODELS["turbo"])
        path.mkdir(parents=True)
        for asset in options["allow_patterns"]:
            (path / asset).write_text("fixture")

    monkeypatch.setattr(huggingface_hub, "snapshot_download", download)
    notices = []
    destination = prepare_model("turbo", True, notices.append)
    assert destination == prepare_model("turbo", False)
    assert len(calls) == len(notices) == 1


def _wave(path):
    with wave.open(str(path), "wb") as stream:
        stream.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
        stream.writeframes(b"\0\0" * 32000)


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="FFmpeg unavailable")
def test_actual_ffmpeg_on_local_media_and_chunk_offsets(tmp_path):
    audio = tmp_path / "普通話 \"test\"; (原件).wav"
    _wave(audio)
    original = audio.read_bytes()
    output = tmp_path / "chunks"
    output.mkdir()
    chunks = normalize_audio(audio, output, chunk_seconds=1)
    assert len(chunks) == 2
    assert sum(read_pcm(chunk)[1] for chunk in chunks) == 32000
    assert audio.read_bytes() == original


def test_downloader_probes_and_preserves_subtitle_types(tmp_path, monkeypatch):
    source = parse_source("https://youtu.be/dQw4w9WgXcQ")
    with MediaBackend(source, tmp_path) as backend:
        def fake_probe(url, *, download):
            assert not download and url == source.url
            return {
                "subtitles": {"en": [{"ext": "vtt", "data": "00:00.000 --> 00:01.000\nManual"}]},
                "automatic_captions": {"yue-orig": [
                    {"ext": "json3", "data": "invalid"},
                    {"ext": "vtt", "data": "00:00.000 --> 00:01.000\n自動"},
                ]},
            }

        monkeypatch.setattr(backend.client, "extract_info", fake_probe)
        manual, automatic = backend.tracks()
        assert manual.origin == "manual" and manual.fetch()[0].text == "Manual"
        assert automatic.origin == "automatic" and automatic.fetch()[0].text == "自動"
        assert automatic.language == "yue" and automatic.original


def test_youtube_transcript_api_adapter(monkeypatch):
    import youtube_transcript_api
    from types import SimpleNamespace

    def fake_listing(self, identifier):
        assert identifier == "dQw4w9WgXcQ"
        return [SimpleNamespace(is_generated=True, language_code="en",
                                fetch=lambda: [SimpleNamespace(start=0.5, duration=1.5, text="Words")])]

    monkeypatch.setattr(youtube_transcript_api.YouTubeTranscriptApi, "list", fake_listing)
    with ExitStack() as stack:
        (track,) = youtube_tracks(parse_source("https://youtu.be/dQw4w9WgXcQ"), stack)
        assert track.origin == "automatic"
        assert track.fetch() == (Cue(0.5, 2, "Words"),)


def test_cli_launcher_commutes_between_workspaces(tmp_path):
    env = {**os.environ, "PATH": "/usr/bin:/bin"}
    result = subprocess.run([str(ROOT / "video-transcript"), "--json", "--model-info"],
                            cwd=tmp_path, env=env, capture_output=True, text=True, check=True)
    assert json.loads(result.stdout)["model"] == "turbo"


def test_installed_skill_launcher(tmp_path):
    launcher = Path.home() / ".agents" / "skills" / "video-transcript" / "run-tool"
    registration = launcher.parent / "project-root"
    if not registration.is_file() or registration.read_text().strip() != str(ROOT):
        pytest.skip("User-scope Skill has not been registered for this checkout")
    result = subprocess.run([str(launcher), "transcribe", "--json", "--model-info", "--model", "large-v3"],
                            cwd=tmp_path, text=True, capture_output=True, check=True)
    assert json.loads(result.stdout)["size"] == "3.08 GB"


def test_release_pointer_can_roll_back(tmp_path, monkeypatch):
    import setup_tool

    active = tmp_path / ".deps"
    previous = tmp_path / ".deps-previous"
    first = tmp_path / ".deps.release-01"
    second = tmp_path / ".deps.release-02"
    first.mkdir()
    second.mkdir()
    monkeypatch.setattr(setup_tool, "ROOT", tmp_path)
    monkeypatch.setattr(setup_tool, "ACTIVE", active)
    monkeypatch.setattr(setup_tool, "PREVIOUS", previous)
    checked = []
    monkeypatch.setattr(setup_tool, "test_candidate", checked.append)
    setup_tool.activate(first)
    setup_tool.activate(second)
    assert active.resolve() == second and previous.resolve() == first
    setup_tool.rollback()
    assert checked == [first]
    assert active.resolve() == first and previous.resolve() == second


def test_installed_skill_passes_a_local_file_to_cli(tmp_path):
    launcher = Path.home() / ".agents" / "skills" / "video-transcript" / "run-tool"
    registration = launcher.parent / "project-root"
    if not registration.is_file() or registration.read_text().strip() != str(ROOT):
        pytest.skip("User-scope Skill has not been registered for this checkout")
    media = tmp_path / "廣東話 ' 原聲；.wav"
    _wave(media)
    result = subprocess.run([str(launcher), "transcribe", "--json", "--captions-only", "--", str(media)],
                            cwd=tmp_path, text=True, capture_output=True)
    assert result.returncode == ErrorCode.NO_CAPTIONS
    assert json.loads(result.stdout)["code"] == "NO_CAPTIONS"
    assert media.is_file()


def test_update_refuses_to_change_unrelated_packages(tmp_path, monkeypatch):
    import update

    current = tmp_path / "current.lock"
    current.write_text("yt-dlp==2026.10.26\npytest==9.2.0\n", encoding="utf-8")
    candidate = tmp_path / ".deps.release-candidate"
    candidate.mkdir()
    monkeypatch.setattr(update, "ACTIVE", tmp_path / ".deps")
    monkeypatch.setattr(update, "installed_lock", lambda: current)
    monkeypatch.setattr(update, "installation_lock", ExitStack)
    monkeypatch.setattr(update, "new_candidate", lambda: candidate)

    def fake_compile(*args):
        assert "--upgrade-package" in args
        Path(args[-1]).write_text("yt-dlp==2026.11.23\npytest==9.3.0\n", encoding="utf-8")

    def unexpected_install(*args):
        pytest.fail("An out-of-scope dependency version passed the update guard")

    monkeypatch.setattr(update, "uv", fake_compile)
    monkeypatch.setattr(update, "install_packages", unexpected_install)
    with pytest.raises(ValueError, match="pytest"):
        update.apply("yt-dlp", "2026.11.23")
    assert current.read_text() == "yt-dlp==2026.10.26\npytest==9.2.0\n"
    assert not candidate.exists()
