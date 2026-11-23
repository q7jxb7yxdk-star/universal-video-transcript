"""Prepare validated dependency directories and switch them atomically."""
from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
from tempfile import mkdtemp
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
ACTIVE = ROOT / ".deps"
PREVIOUS = ROOT / ".deps-previous"
SEED = ROOT / "requirements.lock"
SKILL = Path.home() / ".agents" / "skills" / "video-transcript"
UV_ARGS = ["--no-config", "--no-cache", "pip"]
PYPI = ["--default-index", "https://pypi.org/simple"]
PYTHON_ARGS = ["--python", sys.executable, "--no-python-downloads", "--only-binary", ":all:"]


def uv(*args):
    executable = shutil.which("uv") or "/opt/homebrew/bin/uv"
    subprocess.run([executable, *UV_ARGS, *args], cwd=ROOT, check=True)


def check_host():
    if sys.version_info[:2] != (3, 15) or sys.platform != "darwin" or platform.machine() != "arm64":
        raise ValueError("此鎖定檔需要原生 Apple Silicon macOS Python 3.15。")
    missing = [tool for tool in ("ffmpeg", "ffprobe", "node", "uv")
               if not shutil.which(tool) and not (Path("/opt/homebrew/bin") / tool).is_file()]
    if missing:
        raise ValueError(f"缺少本機工具 {', '.join(missing)}。請先喺 Codex 核准及安裝。")


def install_packages(candidate: Path, lock: Path):
    uv("install", *PYTHON_ARGS, *PYPI, "--require-hashes", "--target", str(candidate), "-r", str(lock))
    shutil.copyfile(lock, candidate / "requirements.lock")


def test_candidate(candidate: Path):
    env = {**os.environ, "VIDEO_TRANSCRIPT_DEPS": str(candidate)}
    subprocess.run([sys.executable, "-I", "-B", str(ROOT / "scripts" / "run.py"), "test"],
                   cwd=ROOT, env=env, check=True)


def new_candidate() -> Path:
    return Path(mkdtemp(prefix=".deps.release-", dir=ROOT))


@contextmanager
def installation_lock():
    with (ROOT / ".deps-install.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def _set_pointer(link: Path, destination: Path):
    temporary = ROOT / f".deps.link-{uuid4().hex}"
    temporary.symlink_to(destination.name, target_is_directory=True)
    try:
        temporary.replace(link)
    finally:
        temporary.unlink(missing_ok=True)


def _release(path: Path) -> bool:
    return path.parent == ROOT and path.name.startswith(".deps.release-") and path.is_dir()


def activate(candidate: Path):
    if not _release(candidate):
        raise ValueError("候選版本唔係本專案嘅依賴目錄。")
    if ACTIVE.is_symlink():
        current = ACTIVE.resolve()
        if not _release(current):
            raise ValueError("現有 .deps 指向非受管理目錄，已保留。")
        if candidate == current:
            return
        _set_pointer(PREVIOUS, current)
        _set_pointer(ACTIVE, candidate)
        return
    if ACTIVE.exists():
        raise ValueError("現有 .deps 係實體目錄，請保留並完成一次遷移。")
    _set_pointer(ACTIVE, candidate)


def rollback():
    if not PREVIOUS.is_symlink():
        raise ValueError("搵唔到可還原嘅上一組依賴。")
    candidate = PREVIOUS.resolve()
    if not _release(candidate):
        raise ValueError("備份指向非受管理目錄。")
    test_candidate(candidate)
    activate(candidate)
