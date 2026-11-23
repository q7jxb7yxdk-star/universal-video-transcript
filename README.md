# Universal Video Transcript Extractor

在 Apple Silicon Mac 擷取影片字幕，或用 MLX Whisper 在本機轉錄。輸出支援 UTF-8 TXT、SRT 和 Obsidian Markdown。無需 API Key 或雲端語音辨識。

## 在 Codex Desktop 使用

工具安裝後，在 Codex Desktop 輸入下列要求，將括號內的內容換成你的網址或附件。

- 「使用 $video-transcript 擷取呢條 YouTube Shorts 嘅字幕，輸出 Obsidian Markdown。（網址）」
- 「使用 $video-transcript 將呢條 Facebook Reel 轉成繁體中文逐字稿。（網址）」
- 「使用 $video-transcript 擷取 Instagram Reel 字幕，輸出 SRT。（網址）」
- 「使用 $video-transcript 將呢條公開 Threads 影片轉成 Markdown。（網址）」
- 「使用 $video-transcript 轉錄我附上嘅 MP4，語言指定廣東話。」
- 「使用 $video-transcript 以高準確度模式重新轉錄。（網址或本機檔案）」

Skill 位於 `~/.agents/skills/video-transcript/`，透過該目錄嘅 `run-tool` 使用本機專案。預設輸出到目前工作目錄嘅 `exports/`，亦可指定 Obsidian vault 內嘅資料夾。Whisper 會額外儲存 `*.original.json`，內容係未經 OpenCC 嘅原語言時間片段。同名結果會加序號。

Markdown 預設顯示時間戳，TXT 可要求加時間戳，SRT 一律保留起止時間。你可以再喺同一個對話要求摘要、攻略整理或根據逐字稿答問題。

## 字幕與平台

| 輸入 | 行為 |
| --- | --- |
| YouTube、Shorts、youtu.be | 先檢查 YouTube Transcript API 及 yt-dlp 人工字幕，再試自動字幕。 |
| Facebook 影片和 Reels | 由 yt-dlp 查詢公開影片及可用字幕，或取得音訊。 |
| Instagram 貼文和 Reels | 由 yt-dlp 嘗試取得公開影片及可用字幕，或取得音訊。 |
| Threads | 由 yt-dlp 嘗試從匿名可存取頁面取得公開媒體。上游仍有 [Threads 擷取器請求](https://github.com/yt-dlp/yt-dlp/issues/7523)。 |
| MP4、MOV、MP3、M4A、WAV | FFmpeg 解碼後交本機 Whisper。 |

平台有現成字幕時直接使用。現成字幕不可用時，工具會嘗試取得音訊或提示改用你有權處理嘅本機檔案。登入、付費以及 DRM 限制會照常生效。平台字幕語言由原有軌道決定。指定語言會優先選同語言軌道，亦會用於 Whisper。指定廣東話可用 `yue`。中文軌道預設經 OpenCC 標準簡轉繁，亦可要求保留原字體。Whisper 可能聽錯廣東話、口音、混合語言或片段邊界。

## 模型

| 模式 | 模型 | 首次下載 |
| --- | --- | --- |
| 快速（預設） | [MLX Whisper Large V3 Turbo](https://huggingface.co/mlx-community/whisper-large-v3-turbo/tree/a4aaeec0636e6fef84abdcbe3544cb2bf7e9f6fb) | 約 1.61 GB |
| 高準確度 | [MLX Whisper Large V3](https://huggingface.co/mlx-community/whisper-large-v3-mlx/tree/49e6aa286ad60c14352c404340ded53710378a11) | 約 3.08 GB |

未有快取時，工具先回傳模型大小同位置，由 Codex 詢問是否下載。已快取模型可離線重用。快取喺 `~/Library/Caches/UniversalVideoTranscript/models/`。工具以大約 10 分鐘嘅 WAV 片段執行長音訊轉錄，合併全片時間戳。音訊及片段只在本機臨時目錄處理，結束後清理。Codex 執行沙盒有機會隱藏 Metal 或禁止平台網絡，遇到時由 Codex 解釋並按權限重試。

## 檢查、更新及還原

- 「檢查 $video-transcript 是否正常。」Codex 會檢查 Python 版本、鎖定依賴、FFmpeg、FFprobe、Node、MLX Metal、CLI、模型快取同 Skill。
- 「檢查 $video-transcript 有咩更新，先畀我睇計劃。」更新工具查詢 PyPI 上嘅 yt-dlp 同 YouTube Transcript API。Codex 顯示指定套件版本及變更，獲批後才安裝。更新會先喺新嘅專案依賴目錄安裝候選版本並執行離線測試。成功後切換 `.deps` 指向，舊依賴目錄可還原。
- 「將 $video-transcript 還原到上一組已驗證嘅依賴。」Codex 會先檢查備份，獲批後測試並還原。若要還原程式碼版本，請指定要回到嘅 Git 版本或請 Codex 檢查本機歷史。

依賴更新及還原只處理專案依賴。已匯出逐字稿同模型快取可跨版本重用。

## 安裝及整合

本機以 Apple Silicon Python 3.15、已有嘅 Homebrew FFmpeg/FFprobe、Node 22 以上及 uv 運作。請喺 Codex 要求安裝或修復工具，Codex 會處理以下內部接口。

- `scripts/install.py` 讀取 `requirements.lock`，將套件裝入此專案嘅版本化依賴目錄，再以 `.deps` 指向目前版本。加 `--with-skill` 會一併安裝使用者 Skill，`--skill-only` 可更新已安裝 Skill。安裝依賴需要 PyPI 網絡。
- `scripts/check.py` 執行本機診斷，`scripts/update.py` 提供 `plan`、`apply` 同 `rollback`。
- `video-transcript` 係其他 Agent、Shortcuts 或 Raycast 可用嘅穩定入口。內部模型及字幕流程在 `video_transcript.engine.extract`，與匯出及 CLI 分開。
- CLI 用 `--help` 列出參數。機器整合時，喺來源前加 `--json --`。JSON 包含 `schema_version`、`ok`、輸出路徑、語言、字幕來源、片段數同錯誤原因。退出碼包括無字幕（3）、影片存取失敗（4）、音訊失敗（5）、辨識失敗（6）、待批准下載（7）、模型失敗（8）、寫入失敗（9）、依賴問題（10）及字幕查詢失敗（11）。

`requirements.lock` 係初始安裝嘅完整版本及 hash。此版本以 Python 3.15.2、FFmpeg 9.0.2、yt-dlp 2026.10.26、YouTube Transcript API 1.2.5、MLX 0.32.4、mlx-whisper 0.4.3 同 OpenCC Python 0.1.7 做離線檢查。pytest 模擬外部字幕、媒體及模型請求，亦用本機合成 WAV 實際驗證 FFmpeg。真實平台及模型推論測試結果另列於 changelog。
