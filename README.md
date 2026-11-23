# Universal Video Transcript Extractor

A Python CLI for extracting existing video captions or transcribing audio on an Apple Silicon Mac with MLX Whisper. Use it to turn a public video link or a local recording into a timestamped note for Obsidian, plain text, or a SubRip subtitle file.

## Features

- **Implemented** — The default URL workflow tries manual captions, then automatic captions, then local Whisper if the video and audio are accessible. Choose `--captions-only` to skip audio download and speech recognition, or `--force-whisper` for fresh transcription.
- **Implemented** — Local MP4, MOV, MP3, M4A, and WAV files go directly to Whisper. The default model is `turbo`. Choose `large-v3` for the larger model or specify a language such as Cantonese (`yue`) or Mandarin (`zh`).
- **Implemented** — Markdown includes timestamps by default, TXT timestamps are opt-in, and SRT always includes both start and end times. Chinese-language cues use OpenCC Simplified-to-Traditional conversion by default. Whisper also writes a `.original.json` file containing its cues before script conversion.
- **Externally unverified** — The URL adapters attempt anonymous access to YouTube videos and Shorts, Facebook videos and Reels, Instagram posts and Reels, and Threads posts. Threads relies on yt-dlp's generic extraction path. A recognized URL can still fail to yield usable captions or media.
- **Optional** — The user-installed Codex Skill invokes the same CLI. Its instructions also ask Codex to append an article to Markdown exports unless the user requests a transcript only. That post-processing depends on the agent.

## Requirements

| Requirement | Repository evidence |
| --- | --- |
| Native Apple Silicon macOS with Metal for local inference | The installer requires Darwin on `arm64`, and the inference path checks for Metal. The repository declares no minimum macOS version, SDK, or device target. |
| Python 3.15.x | [pyproject.toml](pyproject.toml) declares `>=3.15,<3.16`. The installer checks for Python 3.15. |
| uv, FFmpeg, FFprobe, and Node.js | The installer checks that all four tools are present. The health check requires Node.js 22 or later and reports FFmpeg and FFprobe versions. The repository pins no version of uv, FFmpeg, or FFprobe. |
| Python packages | [requirements.lock](requirements.lock) pins the initial dependency set with hashes, including MLX 0.32.4, mlx-whisper 0.4.3, yt-dlp 2026.10.26, and pytest 9.2.0. The [technical documentation](TECHNICAL_DOCUMENTATION.md#external-dependencies) lists the remaining direct dependencies. |

The CLI uses anonymous access for remote media and model downloads. Setup does not require an API key, account, certificate, or environment file.

## Installation

From the root of a checkout, with native Python 3.15 and the tools above available:

```sh
python3.15 -B scripts/install.py
```

The installer uses uv to install binary packages from the hash-locked dependency set into a checkout-local release directory. It tests a fresh candidate before pointing `.deps` at it and reuses an existing `.deps` installation. Initial installation requires PyPI access.

Use `--with-skill` to also install the optional Codex integration under `~/.agents/skills/video-transcript/`. Use `--skill-only` to refresh that registration after checkout dependencies are available. The Skill launcher records the checkout location, so register it again if the checkout moves and the old registration has been addressed.

The shell launcher defaults to Homebrew's Apple Silicon Python path. For another native Python 3.15 installation, set `VIDEO_TRANSCRIPT_PYTHON` to the executable path. The separately generated Skill launcher uses the installer interpreter for its maintenance commands.

## Run

From the checkout root:

```sh
./video-transcript --help
./video-transcript --json --model-info
./video-transcript --json --language yue -- "./recording.wav"
./video-transcript --json --captions-only --format srt -- "https://youtu.be/VIDEO_ID"
```

Replace `./recording.wav` with an existing file and `VIDEO_ID` with a real video ID. The local example runs offline with dependencies and the selected model already installed. A public URL needs network access even when the model is cached. The CLI handles one source per invocation and has no demo mode.

When the model is missing, the CLI returns `MODEL_DOWNLOAD_REQUIRED`. After approving the download, rerun the command with `--allow-model-download` before `--`. The advertised download sizes are approximately 1.61 GB for `turbo` and 3.08 GB for `large-v3`. Models are reused from `~/Library/Caches/UniversalVideoTranscript/models/`.

Outputs default to `exports/` under the working directory. Use `--output-dir` to choose another directory, such as a folder in an Obsidian vault. Existing filenames are preserved by adding a numeric suffix. With `--json`, use `path` and `original_path` to locate the output files. Use `--original-script` to disable script conversion.

With the optional Codex Skill registered, ask Codex to use `$video-transcript` for an attached recording or a public video URL and specify the desired format. Other local clients can call the repository launcher directly.

## Project structure

| Path | Responsibility |
| --- | --- |
| [video-transcript](video-transcript) and [scripts/](scripts/) | Checkout launcher, dependency installation, diagnostics, updates, and test runner |
| [src/video_transcript/](src/video_transcript/) | CLI, source routing, caption selection, local inference, and file export |
| [skill/video-transcript/](skill/video-transcript/) | Optional Codex workflow instructions |
| [tests/](tests/) | Offline pytest coverage with mocked upstream calls and a local FFmpeg integration test |

## Development

```sh
python3.15 -I -B scripts/run.py test
python3.15 -I -B scripts/run.py check
```

The test command uses installed checkout dependencies. The FFmpeg integration test skips when FFmpeg is unavailable, and installed Skill tests can skip when the Skill is unregistered for this checkout. The diagnostic checks tools, locked package versions, basic Metal computation, model cache presence, and Skill registration. Its overall result includes the optional Skill checks. It does not test live providers or load model weights. See the [testing and validation record](TECHNICAL_DOCUMENTATION.md#testing).

The repository has no configured lint, formatter, type-check, CI, or standalone application build command. Setuptools packaging and the installed console entry point are declared in [pyproject.toml](pyproject.toml). [Maintenance](TECHNICAL_DOCUMENTATION.md#configuration) covers dependency updates and rollback.

## Known limitations

Public sources may be blocked by provider changes, region, rate limits, authentication, or media availability. Use a permitted local copy when anonymous extraction fails. Live and upcoming media, DRM-restricted media, and multi-item extraction are outside the supported yt-dlp path. Recognition quality varies with accents, mixed languages, and audio chunk boundaries. OpenCC changes script only. The current checkout provides a local CLI and an optional Codex integration. Metal visibility and network access depend on the execution environment.

## License

This repository contains no project-wide license declaration or license file. Third-party packages and model weights have their own upstream licensing terms.
