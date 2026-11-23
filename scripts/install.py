"""Install into this checkout and optionally register the user-scope Skill."""
import argparse
from pathlib import Path
import shutil
import shlex
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from setup_tool import (ACTIVE, ROOT, SEED, SKILL, activate, check_host, install_packages,
                        installation_lock, new_candidate, test_candidate)


def install_skill():
    content = ROOT / "skill" / "video-transcript" / "SKILL.md"
    if SKILL.exists() or SKILL.is_symlink():
        registered = SKILL / "project-root"
        if SKILL.is_symlink() or not registered.is_file() or registered.read_text().strip() != str(ROOT):
            raise ValueError(f"已存在其他同名 Skill，已保留 {SKILL}。")
    SKILL.mkdir(parents=True, exist_ok=True, mode=0o700)
    (SKILL / "project-root").write_text(str(ROOT) + "\n", encoding="utf-8")
    quote = shlex.quote
    launcher = (
        "#!/bin/sh\nset -eu\n"
        "command=${1:?transcribe, check, or update required}\nshift\n"
        "case \"$command\" in\n"
        f"  transcribe) exec {quote(str(ROOT / 'video-transcript'))} \"$@\" ;;\n"
        f"  check|update) exec {quote(sys.executable)} -I -B "
        f"{quote(str(ROOT / 'scripts' / 'run.py'))} \"$command\" \"$@\" ;;\n"
        "  *) exit 2 ;;\nesac\n"
    )
    entry = SKILL / "run-tool"
    entry.write_text(launcher, encoding="utf-8")
    entry.chmod(0o700)
    shutil.copyfile(content, SKILL / "SKILL.md")
    print(f"Skill 已安裝到 {SKILL}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skill-only", action="store_true")
    parser.add_argument("--with-skill", action="store_true")
    args = parser.parse_args()
    try:
        check_host()
        if not args.skill_only:
            with installation_lock():
                if ACTIVE.exists():
                    print(f"沿用現有依賴 {ACTIVE.resolve()}")
                else:
                    candidate = new_candidate()
                    try:
                        install_packages(candidate, SEED)
                        test_candidate(candidate)
                        activate(candidate)
                    except Exception:
                        shutil.rmtree(candidate)
                        raise
                    print(f"已安裝依賴至 {ACTIVE}")
        if args.skill_only or args.with_skill:
            if not ACTIVE.is_dir():
                raise ValueError("請先安裝專案依賴。")
            install_skill()
        return 0
    except Exception as exc:
        print(f"安裝失敗（{type(exc).__name__}） {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
