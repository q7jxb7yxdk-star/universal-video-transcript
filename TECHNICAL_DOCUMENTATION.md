# Universal Video Transcript Extractor — Technical Documentation

## System overview

The checkout implements a synchronous Python pipeline for one local file or public video URL per invocation. The CLI selects existing captions when available, otherwise it processes audio with local MLX Whisper. It returns the completed transcript as files and emits a machine-readable result when requested.

| Status | Meaning in this checkout |
| --- | --- |
| **Implemented** | Source is connected to a normal entry point. This covers the extraction, inference, and export paths, plus the optional Codex and maintenance entry points. |
| **Test-covered** | A checked-in pytest test exercises the behavior with fixtures, mocks, or available local tools. See [Testing](#testing) for the covered boundaries. |
| **Verified in this task** | Static documentation checks covered Markdown fences, repository paths and anchors, command and configuration references, credential and personal-path patterns, and Git change scope. |
| **Externally unverified** | This task did not exercise live platform extraction, PyPI installation or updates, Hugging Face downloads, Metal, Whisper weight loading or inference, or Codex discovery and article generation. |
| **Experimental / Inactive** | No separate experimental or inactive runtime mode was identified. The generic Threads extraction attempt is wired into the URL workflow. |
| **Planned / Not implemented** | The [extension ideas](#future-development) describe possible work based on current interfaces. They are recommendations, with no commitment or implementation in this checkout. |

## Architecture

The checkout launcher invokes [scripts/run.py](scripts/run.py) with isolated Python and bytecode writing disabled. The runner supplies the checkout's source, private dependency directory, and scripts on the import path. The setuptools console entry point also calls `video_transcript.cli:main` when installed as a package. The optional Codex Skill's generated launcher delegates transcription to the checkout launcher and maintenance to the runner.

`cli.main` is the command composition root. It parses arguments, calls `engine.extract`, passes the resulting `Transcript` to the exporter, and emits the result. The engine owns source selection, provider lifetimes, the media workspace, and the choice between captions and inference. Provider-specific objects stay in the source adapters. Caption decoding and model inference both return domain cues. The exporter consumes those cues without calling a provider. Dependencies are composed directly in code. The engine accepts a notification callback, and tests substitute dependencies using monkeypatching.

The engine owns a temporary directory for each extraction and closes remote clients through an `ExitStack`. The exporter owns a separate staging directory in the destination. The CLI is synchronous and returns after the selected branch and file writes complete. There is no job queue, polling, partial-result stream, or background worker. Model-download notices go to stderr.

## Project structure

| Path | Responsibilities |
| --- | --- |
| [video-transcript](video-transcript), [scripts/run.py](scripts/run.py) | Shell entry point and Python dispatch for `cli`, `test`, `check`, and `update` |
| [cli.py](src/video_transcript/cli.py), [errors.py](src/video_transcript/errors.py) | Argument parsing, result serialization, stderr messages, and error codes |
| [engine.py](src/video_transcript/engine.py), [types.py](src/video_transcript/types.py) | Extraction orchestration and immutable domain values |
| [sources/](src/video_transcript/sources/) | Host routing, platform-specific URL parsing, and upstream access |
| [captions.py](src/video_transcript/captions.py), [audio.py](src/video_transcript/audio.py), [whisper.py](src/video_transcript/whisper.py) | Caption decoding and ordering, audio normalization, model preparation, and inference |
| [export.py](src/video_transcript/export.py) | Rendering, filename selection, and filesystem publication |
| [scripts/install.py](scripts/install.py), [scripts/setup_tool.py](scripts/setup_tool.py) | Dependency releases, activation, rollback mechanics, and user Skill registration |
| [scripts/check.py](scripts/check.py), [scripts/update.py](scripts/update.py) | Health report and extractor update management |
| [skill/video-transcript/SKILL.md](skill/video-transcript/SKILL.md) | Agent instructions for transcription, article post-processing, and maintenance |
| [tests/](tests/) | Offline pytest tests and local tool integration checks |

## Data flow

### Input and caption extraction

1. `parse_source` resolves an existing local path and checks its file extension, or parses an HTTP(S) URL against a hostname and path allowlist. Each web parser produces a canonical HTTPS URL and a platform-specific ID. The original user-supplied URL is retained for export metadata.
2. For a YouTube URL, `youtube_tracks` lists anonymous transcript tracks first. The engine tries its manual tracks, then probes yt-dlp for media metadata and tracks. It returns a working manual YouTube transcript even if the yt-dlp probe fails. Where the probe succeeds, its title can enrich the result.
3. If the first manual lookup yields nothing usable, the engine tries yt-dlp's manual tracks. It then tries automatic tracks across both sources. Within each candidate group it prefers an exact language tag, then a matching base language, then a track marked original. A preferred language is a ranking hint. Candidates outside that language remain eligible.
4. The YouTube adapter turns upstream snippets directly into cues. yt-dlp exposes inline or remote track payloads, tried in JSON3, WebVTT, then SRT order. Empty or unreadable candidates are skipped while alternatives remain. A selected track supplies the result language and origin. Captions-only mode returns a typed failure when no usable track can be selected.

Facebook, Instagram, and Threads share the yt-dlp backend. Their repository modules validate and normalize URLs. Threads uses yt-dlp's generic path and has no dedicated extractor in the repository. The parser accepts YouTube live-link syntax, while the yt-dlp backend rejects media it identifies as live, upcoming, or post-live.

### Audio and local inference

1. Local sources and `--force-whisper` skip caption lookup. In default URL mode, a failed caption selection can fall back only if the media probe succeeds and exposes an audio or media URL. The engine checks for model weights before downloading the remote media.
2. yt-dlp selects `bestaudio/best` and writes into the workspace. The adapter requires exactly one nonempty completed `media.*` file. FFmpeg reads the first audio stream from the local input or downloaded file and produces mono, 16 kHz, signed 16-bit PCM WAV chunks with a nominal duration of 600 seconds.
3. `whisper.prepare_model` resolves the pinned model snapshot. A missing snapshot requires `--allow-model-download`. Inference checks Metal and loads the cached model with `ModelHolder.get_model` at float16 before processing chunks sequentially. Recognition uses the `transcribe` task and disables conditioning on previous text.
4. `read_pcm` scales signed 16-bit samples to float32 by dividing by 32768. The engine receives timed cues and either the requested Whisper language or a language selected from detected speech coverage. For Whisper results it retains the original cues before optional OpenCC conversion. Chinese base codes `zh`, `cmn`, and `yue` use OpenCC `s2t` when enabled.

### Rendering and persistence

`render` produces UTF-8 TXT, SRT, or Obsidian-compatible Markdown. Markdown includes title and source metadata, language, subtitle origin, and a `## Transcript` section. It escapes markup and collapses a cue's nonempty lines. It inserts a space at a line boundary unless both adjacent characters are full-width or wide under Unicode East Asian width. TXT preserves cue line breaks. SRT emits numbered blocks and ensures at least a 1 ms interval after rounding.

`save` resolves the destination and stages files there. It normalizes the title to NFC, removes control and filename-reserved characters, and caps the stem at 170 UTF-8 bytes. It publishes completed files with hard links, trying the bare stem and then numbered suffixes through `(10000)`. For Whisper it publishes the original-cue sidecar first and removes that sidecar if the transcript link fails. This provides per-file publication and collision protection. The pair still has a visibility window between the two links.

The optional Codex workflow can read the Markdown path and append one `## Article` section after CLI success. The agent owns that edit and article language choice. Local CLI use ends with the transcript and, for Whisper, its sidecar.

## Core components

| Component | Interface and ownership |
| --- | --- |
| `parse_source(value)` | Accepts a string and returns a `Source`. It dispatches to YouTube, Facebook, Instagram, or Threads parsers, or validates a local file. |
| `MediaBackend` | Context-managed yt-dlp client. `probe()` caches metadata for the extraction, `tracks()` provides lazy `Track` fetch callbacks, and `audio()` returns a downloaded path. |
| `youtube_tracks(source, stack)` | Uses a scoped Requests session with YouTube Transcript API to return lazy manual or automatic tracks. |
| `extract(value, ...)` | Returns a provider-independent `Transcript`. Options control the model, language, caption mode, script conversion, download permission, and notice callback. |
| `prepare_model`, `transcribe_audio` | Resolve or prepare an approved model snapshot. Convert ordered local WAV chunks into a language code and timed `Cue` tuple. |
| `render`, `save` | Convert a transcript to text and publish it. `save` returns the transcript path and optional sidecar path. |
| `cli.main(argv)` | Accepts CLI arguments and returns an integer exit status. JSON mode returns versioned result or error metadata. |

## Data models and state

- `Source` contains the platform, identifier, canonical URL or local path, and optional original URL. `Cue` stores text and validates finite seconds with `0 <= start <= end`.
- `Transcript` contains the source, title, language, origin (`manual`, `automatic`, or `whisper`), and ordered cues. Optional state includes the model, pre-conversion cues, a script conversion flag, and caption lookup status. Caption results leave the status unset. Whisper results use `skipped`, `not_found`, or `unavailable`.
- Provider `Track` values contain the origin, language, lazy fetch callback, and original-track flag. Raw yt-dlp metadata and upstream transcript snippets stay behind the adapter boundary.
- CLI JSON uses `schema_version: 1`. Transcription success returns output paths, format, title, platform, source URL, language, origin, model, cue count, conversion flag, and caption status. Model-info success returns model metadata and a cache-presence flag. Failures carry `code`, `message`, and `details`. Whisper sidecar JSON independently uses schema version 1 and stores language, model, and timed segments.
- Persistent runtime state is filesystem-based. It consists of exports, model snapshots, private dependency releases and pointers, and optional Skill registration. The application defines no database, view-state store, Keychain storage, cloud sync, or schema migration. Installed dependency rollback is separate from source and export history.

## Important logic

JSON3 parsing concatenates text fragments, converts milliseconds to seconds, and merges an append event with the immediately preceding cue if the event starts at or before that cue's end. The merged interval ends at the later end time. VTT and SRT parsing recognizes timing lines, removes tags, and decodes entities. Both paths drop empty cue text and sort by start and end time. This is a lightweight parser with no general cue deduplication or overlap resolution.

Whisper adds `prior_frames / 16000` to each chunk-relative timestamp. It clamps segment times to the chunk interval and drops empty text. For auto-detection it sums `max(segment_duration, 0.001)` by the reported language over accepted segments, then selects the language with the greatest coverage. Times are offsets into the media. No calendar, session, or timezone conversion applies. Chunks have no cross-boundary stitching or text deduplication.

Pinned model revisions effectively select distinct cache entries. Cache presence is based on nonempty configuration and weight files at the expected snapshot, without a repository-level checksum or eviction policy. The model loader supplies a separate runtime check. The only per-run metadata cache is `MediaBackend.info`. Repeated CLI calls extract anew. Retry settings and error boundaries are documented below.

## External dependencies

The versions below come from the initial [requirements.lock](requirements.lock). An approved extractor update can change the active release while leaving the seed lockfile intact.

| Dependency | Initial version | Role |
| --- | --- | --- |
| `mlx`, `mlx-metal`, `mlx-whisper` | 0.32.4, 0.32.4, 0.4.3 | Apple Silicon Metal runtime and local speech recognition. `mlx-metal` is resolved by the lockfile. |
| `numpy` | 2.5.5 | PCM arrays for inference |
| `huggingface-hub` | 2.4.0 | Optional first-use download from the configured Hugging Face Hub endpoint |
| `opencc-python-reimplemented` | 0.1.7 | Default Simplified-to-Traditional script conversion for recognized Chinese language codes |
| `yt-dlp[default]`, `yt-dlp-ejs` | 2026.10.26, 0.8.0 | Anonymous media and caption extraction via upstream extractors and local JavaScript support. EJS is resolved by the lockfile. |
| `youtube-transcript-api`, `requests` | 1.2.5, 2.34.2 | YouTube caption lookup through an unofficial client with a scoped HTTP session. Requests is resolved by the lockfile. |
| `pytest`, `packaging` | 9.2.0, 26.3 | Optional test extra included in the installer lock, and version comparison in the update script. Packaging is resolved by the lockfile. |
| `setuptools` | Manifest requires >=77. Seed lock includes 84.2.1. | Python packaging backend. The lock entry does not constrain every isolated packaging build. |

The project uses no official YouTube Data API or Meta Graph API integration. yt-dlp accesses public websites and backend media exposed to anonymous clients. Hugging Face Hub and PyPI are configured service endpoints for model download and package operations respectively.

FFmpeg normalizes audio, FFprobe is checked by setup and diagnostics, and Node.js is available to yt-dlp as a local JavaScript runtime when found. Diagnostics enforce Node.js major version 22 or later. uv handles binary-only resolution and installation. The repository declares no exact version for those system tools. [CHANGELOG.md](CHANGELOG.md) records historical release checks separately from this task.

## Configuration

| Setting | Behavior |
| --- | --- |
| [pyproject.toml](pyproject.toml) | Project version 0.1.0, Python `>=3.15,<3.16`, setuptools build backend, console script, and test extra |
| [requirements.lock](requirements.lock) and `.deps/requirements.lock` | Seed hashes and versions, with a copy or updated lock stored in each managed dependency release |
| `VIDEO_TRANSCRIPT_PYTHON` | Overrides the checkout shell launcher's default Homebrew Python 3.15 executable |
| `VIDEO_TRANSCRIPT_DEPS` | Overrides `.deps` for the Python runner and health report. Used internally for candidate tests. Set it only to a trusted directory. |
| `PATH` | The Python runner prepends Homebrew and standard system paths before the inherited value. |
| CLI flags | `--captions-only` and `--force-whisper` are mutually exclusive. Defaults are automatic selection, `turbo`, automatic language, Markdown, script conversion enabled, and current-directory `exports/`. `--model-info` inspects the cache without initiating a download. |
| Skill registration | `~/.agents/skills/video-transcript/` contains the copied `SKILL.md`, generated `run-tool`, and `project-root`. Registration is tied to one checkout. |

The installer gates the locked setup on native Darwin arm64 and Python 3.15. This repository has no Xcode schemes, configurations, deployment target, entitlements, backend deployment configuration, environment-file template, or application-managed secrets.

| CLI model | Pinned Hub snapshot | Required assets | Approximate download |
| --- | --- | --- | --- |
| `turbo` | `mlx-community/whisper-large-v3-turbo` at `a4aaeec0636e6fef84abdcbe3544cb2bf7e9f6fb` | `config.json`, `weights.safetensors` | 1.61 GB |
| `large-v3` | `mlx-community/whisper-large-v3-mlx` at `49e6aa286ad60c14352c404340ded53710378a11` | `config.json`, `weights.npz` | 3.08 GB |

Downloads use `~/Library/Caches/UniversalVideoTranscript/models/`, a free-space threshold of 1,620,000,000 or 3,090,000,000 bytes respectively, and up to two Hugging Face workers. The test suite stubs the model download and does not prove compatibility of either revision with the local inference runtime.

### Dependency releases

A fresh install uses the root lockfile, passes `--require-hashes` to uv, and stages packages in a `.deps.release-*` directory. Candidate tests use the same isolated runner as regular tests. An advisory exclusive lock serializes maintenance operations. On success, activation replaces `.deps` via a temporary relative symlink and records the previous managed release in `.deps-previous`. Each pointer is replaced atomically. The pair is updated in sequence. Activation refuses to replace an unmanaged active directory or symlink.

```sh
python3.15 -I -B scripts/run.py update plan
python3.15 -I -B scripts/run.py update apply --package yt-dlp --version VERSION
python3.15 -I -B scripts/run.py update rollback
```

`plan` queries PyPI for `yt-dlp` and `youtube-transcript-api`. Replace `VERSION` with an exact, approved stable version newer than the installed one. `apply` recompiles the hash lock and allows version changes only for the selected package, with `yt-dlp-ejs` also allowed when updating yt-dlp. It installs and tests the candidate before activation and removes failed candidates in its error path. `rollback` tests the previous release and switches the pointers, making the former active release the previous one. Install, update, and rollback checks are local tests, while fresh install and candidate resolution need PyPI access.

## Error handling and logging

| Exit | Code | Meaning |
| --- | --- | --- |
| 2 | `INPUT` | Missing or invalid CLI input, source, or applicable recognition language |
| 3 | `NO_CAPTIONS` | No obtainable track in captions-only mode, including a local source |
| 4 | `INACCESSIBLE` | Provider probe or access failure |
| 5 | `AUDIO` | Remote audio unavailable, unusable download, or FFmpeg normalization failure |
| 6 | `TRANSCRIPTION` | Chunk processing failed or inference produced no usable speech |
| 7 | `MODEL_DOWNLOAD_REQUIRED` | Missing snapshot requires an explicit download flag |
| 8 | `MODEL` | Download, cache completeness, disk space, or model load failure |
| 9 | `OUTPUT` | Destination write or filename allocation failed |
| 10 | `DEPENDENCY` | Missing package, missing FFmpeg, or unavailable Metal |
| 11 | `CAPTION_LOOKUP` | Candidate lookup or decoding failed in captions-only mode |

Successful commands exit 0. Normally the CLI prints the output path to stdout and handled errors to stderr. `--json` puts structured results and handled errors on stdout. The engine may report caption status in audio failure details. Provider failures are mapped to user-facing categories by matching error text. An exhausted or invalid subtitle candidate can be followed by another candidate. An inaccessible probe can still terminate the audio fallback. The CLI handles `TranscriptError` and imports that fail, while unexpected exceptions can propagate.

YouTube Transcript API requests default to a 15-second timeout. yt-dlp gets a 15-second socket timeout, one download retry, one fragment retry, and zero extractor retries. There is no application-level backoff, rate limit, or whole-job timeout. FFmpeg has no explicit subprocess timeout. There is no cancellation API, stale-task tracking, or retry of a failed inference chunk. Context managers clean up ordinary error paths. Abrupt termination can leave temporary files or partially published output pairs.

The yt-dlp logger suppresses its own messages. FFmpeg stderr is captured and converted to a short error. Model and inference errors usually include the exception class rather than upstream error text. The health check can include local paths and an MLX exception string. Result payloads and Markdown can contain the original input URL, including its query. The application does not provide a general redaction layer or persistent log.

## Security and privacy

- Source validation rejects unsupported hosts, embedded URL credentials, explicit ports, whitespace or control characters, and backslashes. Provider calls use the normalized HTTPS URL. yt-dlp subtitle subrequests allow HTTP(S) without embedded usernames and cap accepted payloads at 24 MiB. These checks do not establish a network egress or redirect allowlist.
- The YouTube session sets `trust_env = False`. yt-dlp disables browser cookie import, cookie files, netrc, file URLs, plugin search paths, and remote JavaScript components. It rejects known private or account-restricted availability, DRM, and live states through metadata checks. Hugging Face downloads set `token=False`. TLS uses upstream client behavior. There is no application-level certificate pinning.
- Inference sends audio arrays to local MLX. Network use covers remote media and captions, explicitly enabled model downloads, and package maintenance. An agent following the optional article workflow reads transcript content into its own processing context. The Python exporter does not upload transcript content.
- FFmpeg receives argument-list input and restricts permitted protocols to `file,pipe`. Temporary media lives under a process-owned workspace and is cleaned up on ordinary exit. Newly created export directories request mode `0700` and published files are set to `0600`. Existing directory permissions are not tightened. Destination path resolution follows symlinks, while name collisions at the final file are skipped. The application provides no at-rest encryption.
- The CLI has no application authentication, token store, WebView, App Attest, APNs, Keychain integration, or cloud persistence. The project ships no signing or entitlement configuration. These are source-level findings. This documentation task did not verify live transport, OS permissions, or client behavior.

## Testing

Run the checked-in offline suite after installing the checkout dependencies:

```sh
python3.15 -I -B scripts/run.py test
```

The test runner disables pytest plugin autoload and its cache provider. [test_engine.py](tests/test_engine.py) covers URL and local-file validation, manual caption precedence, typed caption failures, cleanup, mocked script conversion, and chunk time offsets with a fake transcriber. [test_cli.py](tests/test_cli.py) covers caption decoding, TXT/SRT/Markdown output, wrapped cue text, duplicate names and symlinks, JSON and exit behavior, mocked provider and model operations, launcher behavior, dependency rollback mechanics, and rejection of unrelated package changes during updates.

The FFmpeg test segments a locally generated WAV, checks frame counts, and confirms the input is preserved. It skips if FFmpeg is missing. The installed-Skill checks run only when registration points to the current checkout. Mocked model assets and upstream responses exercise control flow. They do not establish live endpoints, real weight loading, or recognition quality.

```sh
python3.15 -I -B scripts/run.py check
```

The read-only diagnostic reports versions and locked dependency mismatches, basic caption dependency and OpenCC checks, tool availability, a small Metal computation, model snapshot presence, and CLI and Skill launcher checks. The optional Skill affects the overall health result. A successful model-cache presence check does not load weights.

**Verified in this task** — Documentation was checked against the source, configuration, and working tree. No build, pytest suite, diagnostic, inference, external service request, or deployment was run. The changelog's release verification belongs to earlier work.

## Known limitations and technical debt

- Provider access is best-effort. Rate limits, public-site changes, authentication, geographic restrictions, and generic extraction can prevent access. URL acceptance verifies input shape, while extractor availability and media playback require external validation.
- Fixed-duration audio chunks limit per-chunk sample size, but the full downloaded media and all normalized chunks can coexist on disk. Inference and export collect cues in memory. Chunk boundaries and mixed-language speech can affect continuity and the reported dominant language.
- Compatibility depends on a native Apple Silicon Python 3.15 environment, Metal visibility, binary package availability, and local tools. The shell launcher and runner prefer Homebrew paths. Generated Skill registration embeds the checkout location and maintenance interpreter. A moved checkout needs registration cleanup or replacement before reuse.
- Release updates are limited to the two extractor packages and the permitted EJS companion. Older managed releases and cached weights accumulate until managed outside the application. An existing physical `.deps` directory requires manual handling before switching to managed symlinks.
- Caption parsing is deliberately small. Selection treats language as a preference. It tries provider tracks in groups instead of globally ranking manual tracks, and probe errors can prevent audio fallback. The shared yt-dlp plugin setting is process-wide. Concurrent library embedding has no documented thread-safety contract.

## Design decisions

- Caption-first selection avoids downloading audio and running speech recognition when a usable track already exists. Manual tracks take precedence over machine-generated tracks. Language ranking operates within each candidate group.
- Source adapters translate upstream records into `Track` and `Cue` values so inference, rendering, and clients can share a provider-neutral transcript contract. The CLI remains a small machine-readable integration point.
- Anonymous access and explicit opt-in for missing models make network behavior easier to reason about. The tool returns typed failures for blocked media and missing weights. A cached model and local file can run offline.
- Disk-based chunking bounds the input array size for each inference call at the expense of continuity and temporary disk use. Staged no-overwrite output protects existing files. The original-cue sidecar preserves the pre-conversion Whisper result without requiring another inference pass.

## Future development

The following are **recommended and currently unimplemented**:

- Extend provider support through host parsers and the existing `Track` boundary. Preserve anonymous access, single-source selection, and provider-independent cue types.
- Add opt-in live provider and pinned-model smoke checks alongside the offline tests. Keep network, model downloads, and any costs outside the default suite.
- Improve long-recording handling at the FFmpeg and Whisper boundary with bounded temporary storage, explicit cancellation, and chunk-boundary tests. Preserve source-relative times and pre-conversion cues.
- Strengthen Markdown and sidecar publication in `export.save` if consumers need a transactional pair. Preserve collision handling and local file permissions.
