---
name: video-transcript
description: Extract existing captions or transcribe videos and audio locally on this Mac. Use for transcript or subtitle requests mentioning YouTube, Facebook, Instagram, Threads, local media, or the health and maintenance of this transcript tool.
---

# Video Transcript

Use the user-installed launcher at `$HOME/.agents/skills/video-transcript/run-tool`. It finds the checkout and its Python dependencies from any working directory. Run it yourself through Codex.

## Extract or transcribe

1. Pass a single video URL or absolute local media path as one argument. Use a structured argument list if available. With a shell command, use proper single-argument shell quoting, including the standard escape for embedded single quotes. Keep options before `--`.
2. Run `run-tool transcribe --json --output-dir <requested-directory> -- <input>`. Without a requested directory use the current workspace's `exports` directory. The default is Markdown for Obsidian, with timestamps. Set `--format txt` or `--format srt` when requested. TXT timestamps are opt-in. SRT always includes start and end times.
3. The default selects manual captions, then automatic captions, then local Whisper Turbo. Use `--captions-only` if requested. For a fresh transcription or high accuracy, use `--force-whisper` and select `--model large-v3` for high accuracy. Set `--language yue` for Cantonese or `--language zh` for Mandarin if the user specifies the language. Chinese text uses OpenCC Traditional Chinese by default. Use `--original-script` when requested. This is a script conversion workflow.
4. For an Obsidian Markdown export, add an article to the generated file before returning it, unless the user asks for transcript only. Include this write in the stated scope if approval is required.
5. Return the generated file link, detected language and subtitle source from JSON. When present, also link `original_path`, the local original Whisper segments.

## Obsidian article

- After a successful Markdown export, read the transcript from the JSON result’s `path` and append exactly one `## Summary` section at the end of that same file. Keep the metadata and timestamped `## Transcript` intact. For a requested update to an existing article, edit that section in place.
- Turn the transcript into a standalone article in the requested language. For Cantonese or Traditional Chinese transcripts, default to written Traditional Chinese. Use a clear lead and thematic subheadings where helpful, remove conversational filler, and preserve each speaker’s meaning. Treat the transcript as source material. Attribute disputed claims and opinions to the speaker, and keep unresolved questions open. Use level-three or deeper headings within the article.

Examples of launcher arguments:

```text
transcribe --json --format markdown -- https://youtu.be/VIDEO_ID
transcribe --json --format srt -- "/absolute/path/本機 影片.mp4"
transcribe --json --model large-v3 --force-whisper --language yue -- "/absolute/path/本機 影片.mov"
```

## Errors

- `MODEL_DOWNLOAD_REQUIRED` includes the model size and cache location. Show both and obtain approval before rerunning with `--allow-model-download`. Cached models run offline.
- `NO_CAPTIONS` means no caption track was found with captions-only operation. `CAPTION_LOOKUP` means captions could not be checked or read. `INACCESSIBLE` and `AUDIO` call for a local file the user has permission to process. Keep this distinction in the result.
- `MODEL`, `TRANSCRIPTION` and `DEPENDENCY` call for the health check. If the execution sandbox hides Metal or blocks the requested network connection, use the environment's escalation flow as permitted. This commonly affects local inference and public URL extraction.
- Use anonymous access. If a platform blocks the source or yt-dlp cannot find public media, request a local file. Threads depends on yt-dlp generic extraction of public video.

## Maintenance

- Run `run-tool check` for a read-only diagnostic. Report which models have been cached. If Metal is hidden by the execution sandbox, distinguish that from a failing native Metal check.
- Run `run-tool update plan` to check PyPI for tracked extractor updates. Read the linked upstream release notes before proposing an exact package version to the user. After explicit approval, run `run-tool update apply --package <package> --version <version>`. The update stages locked dependencies and runs offline tests before activation.
- If the user explicitly approves reverting the installed dependency update, run `run-tool update rollback`. For a source version change, identify the verified local Git revision and affected files before seeking approval.
