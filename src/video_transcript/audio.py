"""Normalize the first audio stream with bounded-size WAV segments."""
from pathlib import Path
import shutil
import subprocess
import wave

from .errors import ErrorCode, TranscriptError


def normalize_audio(source: Path, directory: Path, chunk_seconds: int = 600) -> list[Path]:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise TranscriptError(ErrorCode.DEPENDENCY, "找不到 FFmpeg。")
    target = directory / "chunk-%08d.wav"
    command = [
        ffmpeg, "-nostdin", "-hide_banner", "-v", "error", "-n",
        "-protocol_whitelist", "file,pipe", "-i", str(source),
        "-map", "0:a:0", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le",
        "-f", "segment", "-segment_format", "wav", "-reset_timestamps", "1",
        "-segment_time", str(chunk_seconds), str(target),
    ]
    try:
        subprocess.run(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                       stderr=subprocess.PIPE, check=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise TranscriptError(ErrorCode.AUDIO, "FFmpeg 無法讀取音訊，請檢查檔案有冇可解碼嘅音軌。") from exc
    chunks = sorted(directory.glob("chunk-*.wav"))
    if not chunks:
        raise TranscriptError(ErrorCode.AUDIO, "音訊冇可處理嘅片段。")
    return chunks


def read_pcm(path: Path):
    import numpy as np

    with wave.open(str(path), "rb") as stream:
        frame_count = stream.getnframes()
        waveform = np.frombuffer(stream.readframes(frame_count), dtype="<i2").astype(np.float32)
    waveform *= 1 / 32768
    return waveform, frame_count
