"""Load only this checkout and its private dependency directory."""
import os
from pathlib import Path
import runpy
import sys

ROOT = Path(__file__).resolve().parents[1]
PATHS = "/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"
os.environ["PATH"] = PATHS + ":" + os.environ.get("PATH", "")
deps = Path(os.environ.get("VIDEO_TRANSCRIPT_DEPS", ROOT / ".deps")).resolve()
sys.path[:0] = [str(ROOT / "src"), str(deps), str(ROOT / "scripts")]

if __name__ == "__main__":
    command = sys.argv.pop(1)
    if command == "cli":
        from video_transcript.cli import main

        sys.exit(main())
    if command == "test":
        from pytest import main

        os.environ["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
        sys.exit(main(["-p", "no:cacheprovider", str(ROOT / "tests"), *sys.argv[1:]]))
    if command in {"check", "update"}:
        runpy.run_path(str(ROOT / "scripts" / f"{command}.py"), run_name="__main__")
    else:
        raise SystemExit(f"Unknown project command: {command}")
