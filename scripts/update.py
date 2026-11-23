"""Check and update one extractor using staged dependencies and offline tests."""
import argparse
import os
import json
from pathlib import Path
import re
import shutil
import sys
from urllib.request import urlopen

root = Path(__file__).resolve().parents[1]
if __name__ == "__main__" and str(root / "src") not in sys.path:
    launcher = root / "scripts" / "run.py"
    os.execv(sys.executable, [sys.executable, "-I", "-B", str(launcher), "update", *sys.argv[1:]])

from setup_tool import (ACTIVE, PYPI, PYTHON_ARGS, ROOT, SEED, activate, check_host,
                        install_packages, installation_lock, new_candidate, rollback,
                        test_candidate, uv)

PACKAGES = ("yt-dlp", "youtube-transcript-api")


def installed_lock() -> Path:
    lock = ACTIVE / "requirements.lock"
    return lock if lock.is_file() else SEED


def versions(lock: Path) -> dict[str, str]:
    return dict(re.findall(r"^([a-zA-Z0-9_.-]+)==([^\s]+)", lock.read_text(), re.MULTILINE))


def plan():
    installed = versions(installed_lock())
    results = []
    for package in PACKAGES:
        with urlopen(f"https://pypi.org/pypi/{package}/json", timeout=15) as response:
            latest = json.load(response)["info"]["version"]
        results.append({"package": package, "installed": installed[package], "available": latest,
                        "release_history": f"https://pypi.org/project/{package}/#history"})
    print(json.dumps(results, ensure_ascii=False, indent=2))


def apply(package: str, version: str):
    from packaging.version import Version

    target = Version(version)
    if target.is_prerelease or target.is_devrelease:
        raise ValueError("請使用穩定版本。")
    with installation_lock():
        previous = versions(installed_lock())
        if target <= Version(previous[package]):
            raise ValueError("更新版本要高於目前版本。需要還原時請用 rollback。")
        candidate = new_candidate()
        lock = candidate.with_name(f"{candidate.name}.lock")
        try:
            shutil.copyfile(installed_lock(), lock)
            uv("compile", *PYTHON_ARGS, *PYPI, str(ROOT / "pyproject.toml"), "--extra", "test",
               "--generate-hashes", "--upgrade-package", f"{package}=={target}", "--output-file", str(lock))
            chosen = versions(lock)
            allowed = {package, "yt-dlp-ejs"} if package == "yt-dlp" else {package}
            changed = {name for name in previous.keys() | chosen.keys() if previous.get(name) != chosen.get(name)}
            if chosen.get(package) != str(target) or not changed <= allowed:
                raise ValueError(f"套件解析超出已選擇嘅更新範圍 {', '.join(sorted(changed))}。")
            install_packages(candidate, lock)
            test_candidate(candidate)
            activate(candidate)
        except BaseException:
            if ACTIVE.resolve() != candidate:
                shutil.rmtree(candidate)
            raise
        finally:
            lock.unlink(missing_ok=True)
    print(f"已啟用 {package} {target}。上一組依賴可以用 rollback 還原。")


def main():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="action", required=True)
    subparsers.add_parser("plan")
    command = subparsers.add_parser("apply")
    command.add_argument("--package", required=True, choices=PACKAGES)
    command.add_argument("--version", required=True)
    subparsers.add_parser("rollback")
    args = parser.parse_args()
    try:
        check_host()
        if args.action == "plan":
            plan()
        elif args.action == "apply":
            apply(args.package, args.version)
        else:
            with installation_lock():
                rollback()
            print("已測試及還原上一組依賴。")
        return 0
    except Exception as exc:
        print(f"操作失敗（{type(exc).__name__}） {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
