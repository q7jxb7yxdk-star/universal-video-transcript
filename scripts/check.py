"""Read-only checks for the runtime, tools, model cache, and Codex Skill."""
import importlib.metadata
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    launcher = ROOT / "scripts" / "run.py"
    os.execv(sys.executable, [sys.executable, "-I", "-B", str(launcher), "check", *sys.argv[1:]])

from video_transcript.whisper import MODELS, cache_root, cached_model

SKILL = Path.home() / ".agents" / "skills" / "video-transcript"


def command_version(*command):
    result = subprocess.run(command, capture_output=True, text=True, timeout=20, check=True)
    return result.stdout.splitlines()[0]


def report():
    import platform

    checks = []
    deps = Path(os.environ.get("VIDEO_TRANSCRIPT_DEPS", ROOT / ".deps")).resolve()
    seed = deps / "requirements.lock"
    if not seed.is_file():
        seed = ROOT / "requirements.lock"
    expected = dict(re.findall(r"^([a-zA-Z0-9_.-]+)==([^\s]+)", seed.read_text(), re.MULTILINE))
    actual = {re.sub(r"[-_.]+", "-", dist.name.lower()): dist.version
              for dist in importlib.metadata.distributions(path=[str(deps)])}
    missing = {name: version for name, version in expected.items() if actual.get(name) != version}

    checks.append({"name": "python", "ok": sys.version_info[:2] == (3, 15) and platform.machine() == "arm64",
                   "version": platform.python_version(), "arch": platform.machine()})
    checks.append({"name": "dependencies", "ok": not missing, "directory": str(deps),
                   "versions": actual, "missing_or_mismatched": missing})

    for tool, flag in (("ffmpeg", "-version"), ("ffprobe", "-version"), ("node", "--version")):
        try:
            version = command_version(tool, flag)
            compatible = tool != "node" or int(version.lstrip("v").split(".")[0]) >= 22
            checks.append({"name": tool, "ok": compatible, "version": version, "path": shutil.which(tool)})
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            checks.append({"name": tool, "ok": False, "error": type(exc).__name__})

    try:
        from yt_dlp.version import __version__ as yt_version
        import yt_dlp_ejs
        from youtube_transcript_api import YouTubeTranscriptApi
        from opencc import OpenCC

        checks.append({"name": "caption_dependencies",
                       "ok": callable(YouTubeTranscriptApi().list) and OpenCC("s2t").convert("简体") == "簡體",
                       "yt_dlp": yt_version, "ejs": getattr(yt_dlp_ejs, "__version__", actual.get("yt-dlp-ejs"))})
    except Exception as exc:
        checks.append({"name": "caption_dependencies", "ok": False, "error": type(exc).__name__})

    try:
        import mlx.core as mx
        from mlx_whisper import transcribe

        available = mx.metal.is_available()
        computed = available and (mx.array([2, 3]) + 1).tolist() == [3, 4]
        checks.append({"name": "mlx_whisper", "ok": computed and callable(transcribe),
                       "version": actual.get("mlx-whisper"), "mlx": actual.get("mlx"),
                       "device": str(mx.default_device())})
    except Exception as exc:
        checks.append({"name": "mlx_whisper", "ok": False, "error": str(exc)})

    cli = [str(ROOT / "video-transcript"), "--json", "--model-info"]
    for name, invocation in (("cli", cli), ("skill_launcher", [str(SKILL / "run-tool"), "transcribe", *cli[1:]])):
        try:
            result = json.loads(command_version(*invocation))
            checks.append({"name": name, "ok": result["ok"] and result["model"] == "turbo"})
        except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
            checks.append({"name": name, "ok": False, "error": type(exc).__name__})

    try:
        same_source = (SKILL / "SKILL.md").read_bytes() == (ROOT / "skill" / "video-transcript" / "SKILL.md").read_bytes()
        registration = (SKILL / "project-root").read_text().strip() == str(ROOT)
        skill = same_source and registration
    except OSError:
        skill = False
    checks.append({"name": "skill_files", "ok": skill, "path": str(SKILL)})
    models = {name: {"cached": cached_model(name) is not None, "download_size": model.size}
              for name, model in MODELS.items()}
    return {"ok": all(check["ok"] for check in checks), "checks": checks,
            "model_cache": str(cache_root()), "models": models}


if __name__ == "__main__":
    result = report()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result["ok"] else 1)
