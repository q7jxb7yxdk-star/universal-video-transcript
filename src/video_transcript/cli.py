"""The command-line API used by Codex and other local clients."""
import argparse
import json
from pathlib import Path
import sys

from .engine import extract
from .errors import ErrorCode, TranscriptError
from .export import EXTENSIONS, save
from .whisper import MODELS, cache_root, cached_model


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise TranscriptError(ErrorCode.INPUT, message)


def parser():
    command = Parser(prog="video-transcript", description="擷取字幕，或用本機 Whisper 轉錄影片同音訊。")
    command.add_argument("source", nargs="?", help="支援平台嘅影片網址，或本機影片或音訊路徑")
    command.add_argument("--format", choices=EXTENSIONS, default="markdown")
    command.add_argument("--model", choices=MODELS, default="turbo")
    command.add_argument("--language", help="語言代碼或名稱，例如 yue、zh 或 en。預設自動辨識")
    command.add_argument("--timestamps", action=argparse.BooleanOptionalAction, default=None)
    command.add_argument("--output-dir", type=Path, default=Path.cwd() / "exports")
    command.add_argument("--json", action="store_true", help="以 JSON 回傳結果及錯誤")
    command.add_argument("--original-script", action="store_true", help="保留原文字體")
    mode = command.add_mutually_exclusive_group()
    mode.add_argument("--captions-only", action="store_true")
    mode.add_argument("--force-whisper", action="store_true")
    command.add_argument("--allow-model-download", action="store_true", help="授權下載指定嘅 Whisper 權重")
    command.add_argument("--model-info", action="store_true", help="顯示模型大小、位置及快取狀態")
    return command


def _emit(payload, as_json):
    if as_json:
        print(json.dumps({"schema_version": 1, **payload}, ensure_ascii=False))
    elif payload["ok"]:
        if "path" in payload:
            print(payload["path"])
        else:
            print(f'{payload["model"]} · {payload["size"]} · {payload["cache_directory"]}')
    else:
        print(f'{payload["code"]} · {payload["message"]}', file=sys.stderr)


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    json_position = argv.index("--") if "--" in argv else len(argv)
    as_json = "--json" in argv[:json_position]
    try:
        args = parser().parse_args(argv)
        as_json = args.json
        if args.model_info:
            spec = MODELS[args.model]
            _emit({"ok": True, "model": args.model, "repository": spec.repo, "size": spec.size,
                   "cache_directory": str(cache_root()), "cached": cached_model(args.model) is not None}, as_json)
            return 0
        if not args.source:
            raise TranscriptError(ErrorCode.INPUT, "請提供影片網址或本機檔案路徑。")
        mode = "whisper" if args.force_whisper else "captions" if args.captions_only else "auto"
        transcript = extract(args.source, model=args.model, language=args.language, mode=mode,
                             traditional=not args.original_script, allow_model_download=args.allow_model_download,
                             notify=lambda message: print(message, file=sys.stderr, flush=True))
        timestamps = args.timestamps if args.timestamps is not None else args.format != "txt"
        path, original = save(transcript, args.output_dir, args.format, timestamps)
        _emit({
            "ok": True, "path": str(path), "original_path": str(original) if original else None,
            "format": args.format, "title": transcript.title, "platform": transcript.source.platform,
            "source_url": transcript.source.original_url or transcript.source.url, "language": transcript.language,
            "origin": transcript.origin, "model": transcript.model, "segments": len(transcript.cues),
            "converted_to_traditional": transcript.converted_to_traditional,
            "caption_status": transcript.caption_status,
        }, as_json)
        return 0
    except ImportError as exc:
        error = TranscriptError(ErrorCode.DEPENDENCY, f"載入專案依賴失敗（{exc.name or type(exc).__name__}）。")
    except TranscriptError as exc:
        error = exc
    _emit({"ok": False, "code": error.code.name, "message": str(error), "details": error.details}, as_json)
    return int(error.code)


if __name__ == "__main__":
    sys.exit(main())
