"""Pinned Hugging Face weights and local-only MLX inference."""
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
import shutil

from .audio import read_pcm
from .captions import ordered
from .errors import ErrorCode, TranscriptError
from .types import Cue


@dataclass(frozen=True)
class Model:
    repo: str
    revision: str
    weights: str
    size: str
    disk_bytes: int


MODELS = {
    "turbo": Model("mlx-community/whisper-large-v3-turbo",
                   "a4aaeec0636e6fef84abdcbe3544cb2bf7e9f6fb",
                   "weights.safetensors", "1.61 GB", 1_620_000_000),
    "large-v3": Model("mlx-community/whisper-large-v3-mlx",
                      "49e6aa286ad60c14352c404340ded53710378a11",
                      "weights.npz", "3.08 GB", 3_090_000_000),
}

LANGUAGE_ALIASES = {
    "cantonese": "yue", "廣東話": "yue", "粵語": "yue",
    "mandarin": "zh", "普通話": "zh", "中文": "zh", "chinese": "zh",
    "英文": "en", "日文": "ja", "韓文": "ko",
}


def cache_root() -> Path:
    return Path.home() / "Library" / "Caches" / "UniversalVideoTranscript" / "models"


def _snapshot(model: Model) -> Path:
    return cache_root() / ("models--" + model.repo.replace("/", "--")) / "snapshots" / model.revision


def cached_model(name: str) -> Path | None:
    model = MODELS[name]
    path = _snapshot(model)
    try:
        if all((path / item).stat().st_size > 0 for item in ("config.json", model.weights)):
            return path
    except OSError:
        pass
    return None


def prepare_model(name: str, allow_download: bool, notify: Callable[[str], None] = print) -> Path:
    previous = cached_model(name)
    if previous:
        return previous
    model = MODELS[name]
    root = cache_root()
    details = {"model": name, "repository": model.repo, "size": model.size, "cache_directory": str(root)}
    message = f"Whisper {name} 模型約 {model.size}，快取位置為 {root}。"
    if not allow_download:
        raise TranscriptError(ErrorCode.MODEL_DOWNLOAD_REQUIRED, message + " 請先確認下載。", **details)
    notify(message)
    try:
        from huggingface_hub import snapshot_download

        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        if shutil.disk_usage(root).free < model.disk_bytes:
            raise OSError("Not enough disk space")
        snapshot_download(repo_id=model.repo, revision=model.revision, cache_dir=root,
                          endpoint="https://huggingface.co", allow_patterns=["config.json", model.weights],
                          token=False, max_workers=2)
    except Exception as exc:
        reason = "磁碟空間不足。" if str(exc) == "Not enough disk space" else f"模型下載失敗（{type(exc).__name__}）。"
        raise TranscriptError(ErrorCode.MODEL, reason, **details) from exc
    result = cached_model(name)
    if result is None:
        raise TranscriptError(ErrorCode.MODEL, "模型下載後未找到完整嘅權重或設定檔。", **details)
    return result


def normalize_language(language: str | None) -> str | None:
    if not language:
        return None
    normalized = language.strip().lower().replace("_", "-")
    return LANGUAGE_ALIASES.get(normalized, normalized) if normalized not in {"", "auto"} else None


def whisper_language(language: str | None) -> str | None:
    if language is None:
        return None
    from mlx_whisper.tokenizer import LANGUAGES, TO_LANGUAGE_CODE

    tag = language.split("-")[0]
    code = tag if tag in LANGUAGES else TO_LANGUAGE_CODE.get(language)
    if code is None:
        raise TranscriptError(ErrorCode.INPUT, "Whisper 無法使用指定語言，請提供語言代碼或名稱。")
    return code


def _transcriber(model: Path):
    try:
        from mlx_whisper import transcribe
        from mlx_whisper.transcribe import ModelHolder
        import mlx.core as mx
    except ImportError as exc:
        if "metal" in str(exc).lower():
            raise TranscriptError(ErrorCode.DEPENDENCY, "目前執行環境無法存取 Metal，請執行健康檢查。") from exc
        raise TranscriptError(ErrorCode.DEPENDENCY, "載入 mlx-whisper 或 MLX 失敗，請執行健康檢查。") from exc
    if not mx.metal.is_available():
        raise TranscriptError(ErrorCode.DEPENDENCY, "MLX 無法使用 Apple Silicon Metal GPU。")
    try:
        ModelHolder.get_model(str(model), mx.float16)
    except Exception as exc:
        raise TranscriptError(ErrorCode.MODEL, f"載入 Whisper 模型失敗（{type(exc).__name__}）。") from exc
    return transcribe


def transcribe_audio(chunks: list[Path], model: Path, language: str | None) -> tuple[str, tuple[Cue, ...]]:
    transcribe = _transcriber(model)
    language = whisper_language(language)
    frame_offset = 0
    cues = []
    coverage = Counter()
    for chunk in chunks:
        try:
            samples, frames = read_pcm(chunk)
            if not frames:
                continue
            start_at = frame_offset / 16000
            duration = frames / 16000
            frame_offset += frames
            # The audio never leaves the process. MLX accepts an in-memory PCM array.
            result = transcribe(samples, path_or_hf_repo=str(model), language=language,
                                task="transcribe", verbose=None, condition_on_previous_text=False)
            for segment in result["segments"]:
                start = max(0, min(float(segment["start"]), duration))
                end = max(start, min(float(segment["end"]), duration))
                cue = Cue(start_at + start, start_at + end, segment["text"].strip())
                if cue.text:
                    cues.append(cue)
                    coverage[result["language"]] += max(end - start, 0.001)
        except Exception as exc:
            raise TranscriptError(ErrorCode.TRANSCRIPTION,
                                  f"Whisper 辨識音訊失敗（片段 {chunk.stem}，{type(exc).__name__}）。") from exc
    if not cues:
        raise TranscriptError(ErrorCode.TRANSCRIPTION, "Whisper 未能辨識出可用嘅語音。")
    return language or coverage.most_common(1)[0][0], ordered(cues)
