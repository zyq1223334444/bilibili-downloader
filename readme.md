> [🇨🇳 中文](readme.zh.md)

# bilibili-downloader

A Bilibili video / multi-part / collection downloader — DASH streams are fetched separately, then merged with ffmpeg.

---

## Features

- **Single video / multi-part (分P) / collection (合集)** — one link is enough; collections and multi-part videos are expanded automatically.
- **Best available quality** by default (8K / 4K / HDR / Dolby Vision, limited by your account), capped with `-q`.
- **Audio picks Hi-Res lossless first** (`dash.flac`) → Dolby → highest bitrate.
- **Outputs MP4 + MP3** — MP4 is merged with `-c copy -movflags +faststart` (no re-encode, instant), MP3 is encoded at 320 kbps (configurable).
- **Parallel downloads, one progress bar per thread** — up to 4 videos at once by default, and the bottom 4 lines are a live status table, each naming **which video and which stream** it is (e.g. `[11/22] #43 逃离棋盒 · 1080P 视频流`). Per-item title lines are suppressed in this mode, so the log only keeps `[完成] / [失败] / [跳过]`. The bar adapts to the **actual terminal width** (wider window → longer bar) and the title is clipped to a width budget — the `k/N` head is dropped first on very narrow windows — so percentage/size/speed are never squeezed out. When the output is redirected the bars become a line every 15 s.
- **Automatic reconnect on a slow connection**: when a stream's speed falls below **30 % of its own
  historical average** (from the start of the download up to 10 s ago) for **10 s**, that connection
  is dropped and the download resumes on another CDN node via `Range`, losing no progress (at most 5
  times by default; `--max-reconnects 0` disables it). **If the estimated remaining time at the
  current speed is under 10 s, the connection is kept** and the file simply finishes.
- **Robust downloading** — CDN node pre-selection, per-node retries with backoff, resume via HTTP Range, and size verification.
- **Atomic writes** — everything is written to a `.part` file and renamed on success, so a failure never leaves a half-written file behind.
- **Idempotent** — already-downloaded videos are skipped; failed ones keep their `.m4s` streams so a re-run resumes instead of starting over.
- **WBI request signing** with automatic fallback to the legacy endpoint.
- **SESSDATA is asked for once** and stored in a Windows user environment variable (never in the source).
- **Tidy output tree** — sanitized names, Windows-reserved-name handling, and MAX_PATH protection via shortening + hash suffix.
- `--dry-run` preview, meaningful exit codes (`0` ok / `1` failure / `2` bad args / `130` interrupted).
- **Genuinely non-interactive** — with `-y` or redirected output it never stops to ask, **even on a fresh
  machine that has no credential** (the old code called `getpass`, which opens `/dev/tty` directly, so
  redirecting stdin did not help and CI/batch jobs hung forever).
- **Cross-platform** — one source tree for Windows / Linux / macOS; the credential is stored in a Windows
  user environment variable there and in `~/.config/bilibili-downloader/sessdata` (mode 600) elsewhere.

## Requirements

| Item | Notes |
|---|---|
| Python | 3.9 or newer |
| Dependencies | `pip install -r requirements.txt` (requests, tqdm) |
| ffmpeg | must be on `PATH` — `choco install ffmpeg`, `scoop install ffmpeg`, `brew install ffmpeg`, `sudo apt install ffmpeg` |

### Option 1: installer (Windows, recommended)

Download **`bilibili_downloader_setup_1.0.0.exe`** from
[Releases](https://github.com/zyq1223334444/bilibili-downloader/releases) and run it:

- installs to `C:\Program Files\bilibili-downloader` with Start Menu shortcuts and a **proper uninstaller**
  (it also shows up in Settings -> Apps)
- optionally adds the install folder to the system `PATH` (checked by default) so `bilibili_downloader`
  works from any terminal; the uninstaller **restores `PATH` byte-for-byte** (the original value is
  backed up in the registry before the edit)
- checks for ffmpeg on `PATH` when it finishes and tells you how to install it if it is missing

### Option 2: no installation (Windows single file / zip)

| Download | Shape | Startup (measured) | Exit code on Ctrl+C |
|---|---|---|---|
| `bilibili_downloader.exe` | single file (~11 MB) | ≈0.9 s (unpacks on every run) | `0xC000013A` (see below) |
| `bilibili_downloader_standalone_win64.zip` | unzip into a folder | ≈0.3 s | **130**, same as the script |

```powershell
.\bilibili_downloader.exe BV1xx411c7mD -q 720p --no-mp3
.\bilibili_downloader.exe --dry-run BV1xx411c7mD
```

> **Known difference in the single-file build**: `--onefile` wraps the real program in a self-extracting
> bootstrap process. A console Ctrl+C reaches both, the bootstrap exits first, and the shell therefore sees
> `0xC000013A` (`-1073741510`) instead of 130. The program itself still shuts down cleanly: it prints
> `[中断]`, keeps the `.part` resume data, leaves no stray process and cleans up its temp folder — only the
> exit code differs. Use the standalone build if a script has to test for 130.

### Option 3: Linux / macOS

| Platform | Single file | Folder build (keeps the exec bit, recommended) |
|---|---|---|
| Linux x86_64 | `bilibili_downloader_linux_x86_64` | `bilibili_downloader_linux_x86_64.tar.gz` |
| macOS Intel | `bilibili_downloader_macos_x86_64` | `bilibili_downloader_macos_x86_64.tar.gz` |
| macOS Apple Silicon | `bilibili_downloader_macos_arm64` | `bilibili_downloader_macos_arm64.tar.gz` |

```bash
tar -xzf bilibili_downloader_linux_x86_64.tar.gz
./bilibili_downloader_standalone/bilibili_downloader BV1xx411c7mD --single -q 720p
```

> The macOS binaries are **unsigned**, so Gatekeeper may block the first run:
> `xattr -d com.apple.quarantine <file>`, or right-click -> Open.
> The Linux and macOS binaries are built on **real machines** by GitHub Actions
> (see `.github/workflows/build.yml`), because Nuitka compiles Python to C and then calls the target
> platform's own linker — there is no cross-compiling. To build them yourself: `bash build/build_unix.sh`
> (needs gcc / patchelf on Linux).

All three shapes are produced by compiling the Python to C and linking it with Nuitka, so the Python
runtime and `requests` / `tqdm` are bundled — **ffmpeg is still required** and must be on `PATH`
(`choco install ffmpeg` / `brew install ffmpeg` / `sudo apt install ffmpeg`).

Options, output layout and credential lookup order are identical to the script version; for the binaries,
"`sessdata.txt` next to the program" means next to the executable.

## Quick start

```powershell
pip install -r requirements.txt

# single video (saved next to nothing else: .\bili_downloads\<title>\<title>.mp4 + .mp3)
python bilibili_downloader.py BV1xx411c7mD

# one specific part of a multi-part video only
python bilibili_downloader.py "https://www.bilibili.com/video/BV1xx411c7mD?p=2" --single

# see what would be downloaded, without downloading
python bilibili_downloader.py BV1xx411c7mD --dry-run

# cap quality, skip the MP3 export, custom output root
python bilibili_downloader.py BV1xx411c7mD -q 720p --no-mp3 -o D:\videos

# audio only, different bitrate
python bilibili_downloader.py BV1xx411c7mD --audio-only --mp3-bitrate 192
```

On first run, if no credential is found, the script prints instructions and asks for your `SESSDATA`
(input is hidden). It is verified against the API, then saved to the Windows user environment
variable `BILI_SESSDATA` — open a new terminal and later runs pick it up automatically.

### Choosing which items to download

Multi-item plans are listed with numbers, then you are asked what to fetch:

```
共 54 项。回车 / y = 全部下载，n = 不下载，也可只下部分（如 1,3,5,6-20）：
> 1,3,5,6-20
[选择] 已选 20/54 项：1,3,5-6,6-20
```

| Input | Effect |
|---|---|
| Enter, `y`, `yes`, `all` | download everything |
| `n`, `no`, `q` | download nothing, exit 0 |
| `1,3,5,6-20` | only these — ranges, duplicates, empty items (`1,,3`) and full-width commas are fine |
| `20-6` | reversed ranges are normalised to `6-20` |
| anything invalid (`abc`, `0`, `99`) | the reason is printed and you are asked again; 3 invalid tries cancels |

The selection is echoed as `[选择] 已选 N/total 项：…`; during the run `[3/20]` is the position in
your selection while the leading `#5` is the **original number in the plan listing**.

> Non-interactive runs (redirected output, or `-y`) skip the question and download everything, so
> scripts and CI keep working. A single video/part never asks.

## Output layout

```
bili_downloads\
├── <video title>\                         # single-part video
│   ├── <video title>.mp4
│   └── <video title>.mp3
├── <video title>\                         # multi-part video
│   ├── P01 <part title>\
│   │   ├── P01 <part title>.mp4
│   │   └── P01 <part title>.mp3
│   └── P02 <part title>\...
└── <collection title>\                    # collection (合集)
    ├── <video title>\
    │   ├── <video title>.mp4
    │   └── <video title>.mp3
    └── <video title>\P01 <part title>\...  # a multi-part video inside a collection
```

## Options

| Option | Default | Description |
|---|---|---|
| `inputs` | prompt | One or more links / `BV` ids / `av` ids / `b23.tv` short links |
| `-o, --output` | `./bili_downloads` | Output root directory |
| `-q, --quality` | `max` | Quality cap: `max 8k 4k 1080p60 1080p+ 1080p 720p60 720p 480p 360p` |
| `--mp3-bitrate` | `320` | `128 / 192 / 256 / 320` kbps |
| `--audio-only` | off | Export MP3 only (video stream is not downloaded) |
| `--no-mp3` | off | Save MP4 only |
| `--single` | off | Only the linked video/part; ignore its collection |
| `-j, --jobs` | `4` | Concurrent downloads, max 4 (one progress bar per thread) |
| `--max-reconnects` | `5` | Max reconnects per stream when its speed falls below 30 % of its own average (`0` disables the check) |
| `--force` | off | Re-download even if the output already exists |
| `--no-probe` | off | Skip CDN node probing |
| `--retries` | `2` | Attempts per node |
| `--timeout` | `15` | Network timeout (seconds) |
| `--reset-sessdata` | off | Ignore the stored credential and ask again |
| `--dry-run` | off | Print the plan and exit |
| `-y, --yes` | off | Never ask; download everything (skips the range prompt and credential re-entry) |

## SESSDATA

Lookup order: **① the process environment variable `BILI_SESSDATA`** → **② the Windows user
environment variable, read straight from `HKCU\Environment`** → **③ `sessdata.txt` next to the program**
(the script folder, or the folder holding the exe)
→ **④ `~/.config/bilibili-downloader/sessdata`**. If none is found you are asked once; on
Windows the answer is stored in the user environment variable (and applied to the current process),
elsewhere in the config file with mode `600`.

> Why read the registry directly: Windows injects environment variables only when a process starts,
> so a terminal (or long-running service) that was already open keeps a stale snapshot — which looks
> like "I set it, but the script says it is missing". Reading the registry makes old shells work too.

The credential is **verified once at startup** through the `nav` endpoint:

| Result | Behaviour |
|---|---|
| valid | prints `[凭证] 校验通过（普通账号 / 大会员）` and tells you the account's quality tier |
| expired | prints `[!] 凭证已失效…` — downloads will be guest-tier (typically 480P/360P) — and offers to re-enter it right away in an interactive terminal (one line, no tutorial) |
| network down | the check is skipped and the stored value is used as-is |

> An expired credential used to degrade to 480P silently, which looked like "the script is broken";
> now the reason is stated. Add `-y`, or run with redirected output, to stay fully non-interactive.

Set it manually (PowerShell, persistent):

```powershell
setx BILI_SESSDATA "your-sessdata-value"
```

How to obtain it: sign in to Bilibili in a browser → `F12` → **Application** → **Cookies** →
`https://www.bilibili.com` → copy the value of `SESSDATA`.

> ⚠️ `SESSDATA` is a login credential. Never commit it, never paste it into source code, never share
> it. If it may have leaked, sign out everywhere: Bilibili → Settings → Security & Privacy →
> "Sign out of all devices".

## Resume & failure behaviour

- **Ctrl+C is always safe and immediate**: the main thread polls the futures every 0.3 s, then tells
  the workers to stop and exits at once (it never waits for a stuck thread or ffmpeg). No traceback,
  exit code `130`, and everything already downloaded (`.part` / `.m4s`) is kept so a re-run resumes.
- Streams are downloaded to `<name>.video.m4s.part` / `<name>.audio.m4s.part`; a re-run resumes from
  the existing byte count using `Range`.
- On success the stream files are renamed to `.m4s`, merged, and deleted.
- On failure they are **kept**, so re-running the same command continues instead of starting over.
- A file whose size does not match `Content-Length` / `Content-Range` is treated as failed and retried.
- `416 Range Not Satisfiable` (stale local `.part`) clears the breakpoint and retries cleanly.

### Status markers in the output

| Marker | Meaning |
|---|---|
| `[跳过]` | already cached / already finished, not downloaded again |
| `[重试]` | one attempt failed, plus what happens next: retry same node / switch node / no node left |
| `[重连]` | speed dropped below 30% of its own historical average for 10 s: the connection is dropped and the download resumes on another node via Range (skipped when the ETA is under 10 s) |
| `[成功]` | it failed earlier but ultimately succeeded (silent on the happy path) |
| `[失败]` | the item failed for good (all nodes tried); the run exits with 1 |
| `[完成]` | a produced file, with its size |
| `[结果]` | batch summary and failure details |
| `[中断]` | you pressed Ctrl+C (exit 130) |

Network errors are collapsed into one readable line instead of the raw nested-exception tuple:

```
视频流：[重试] 节点 1/3 第 1 次失败（远程主机强迫关闭了一个现有的连接。（ConnectionResetError 10054））→ 换下一个节点
视频流：[成功] 第 2 个节点第 1 次尝试成功（191.4 MB，用时 42s）
#2 [完成] P02 ….mp4（191.4 MB）
```

> Seeing `[重试]` does **not** mean failure — read the end of that line and the `[成功]` / `[失败]`
> line that follows.

## FAQ

| Symptom | Explanation |
|---|---|
| `未找到 ffmpeg` | Install ffmpeg and make sure it is on `PATH` |
| Only 360P/480P available | No valid `SESSDATA`, or the account lacks the quality |
| `该视频没有 DASH 流` | Bangumi/movie content (only UGC is supported), or a very old video |
| `这是番剧/影视内容` | `redirect_url` present — ep/bangumi downloads are out of scope |
| `code=62002/62004` | Video invisible / under review |
| `《…》是付费合集` | Paid collections cannot be downloaded |
| Download looks stalled | Nodes can be slow; probing, retries and backoff are handling it — check the per-node lines |

## Repository layout

The repository holds the program and the means to build it. Everything a build *produces* lives in one
ignored folder, so a checkout stays clean:

```
bilibili_downloader.py      the whole program (single file)
requirements.txt            runtime dependencies (requests, tqdm)
readme.md / readme.zh.md    these documents
LICENSE
.github/workflows/build.yml CI: Linux + both macOS architectures
build/                      build tooling - part of the repository
├── build_exe.bat             Windows single-file exe
├── build_exe_standalone.bat  Windows folder build + zip
├── build_installer.bat       Windows installer (calls installer.iss)
├── build_unix.sh             Linux / macOS binaries
├── installer.iss             Inno Setup script
├── ChineseSimplified.isl     Simplified Chinese texts for the installer
└── out/                      ignored: every artefact and Nuitka intermediate
```

`build/out/` is the only thing `.gitignore` excludes here. The scripts themselves are tracked, so anyone
can rebuild the binaries from a checkout.

## Building from source (Nuitka)

| What you want | Where to build it | Command |
|---|---|---|
| Windows single-file exe | Windows | `build\build_exe.bat` → `build\out\bilibili_downloader.exe` |
| Windows folder build | Windows | `build\build_exe_standalone.bat` → folder + zip in `build\out\` |
| Windows installer | Windows | `build\build_installer.bat` (needs Inno Setup 6.5+) |
| Linux / macOS binaries | **the target platform** (WSL / Mac / CI) | `bash build/build_unix.sh` → `build/out/dist_unix/` |

The scripts resolve the repository root themselves, so they can be started from any working directory.
They only ever write inside `build/out/`.

Requirements: `pip install -r requirements.txt nuitka zstandard`, plus **MSVC 14.3+** on Windows
(Visual Studio 2022 Build Tools or newer) — Nuitka **cannot use MinGW with Python 3.13+**.
The three flags worth knowing about, all measured rather than guessed (the scripts carry the full story):

- `VSLANG=1033` — Nuitka's Scons backend decodes `cl.exe` output with the `mbcs` code page, so a
  localized (Chinese) Visual Studio aborts the build with `UnicodeDecodeError`.
- `--include-package-data=certifi` — `requests` verifies TLS against certifi's `cacert.pem`, which is a
  data file. Without it the exe starts fine but every HTTPS call dies with
  *"Could not find a suitable TLS CA certificate bundle"*.
- `--windows-console-mode=force` — this is a console tool; without the flag the exe would be a
  GUI-subsystem binary with no usable stdout.

The installer is compiled with **Inno Setup 6.5+**: `winget install --id JRSoftware.InnoSetup -e`.
Its `[Code]` section backs the original system `PATH` up in the registry before editing it and restores
it byte-for-byte on uninstall, and it warns you at the end of the installation when ffmpeg is missing
from `PATH`.

**ffmpeg is never bundled** — it is a ~100 MB external program, found at runtime through
`shutil.which("ffmpeg")`, so it has to be installed separately on every platform.

> **Why Linux/macOS cannot be built on Windows**: Nuitka compiles Python to C and then calls the
> **target platform's own** compiler and linker — there is no cross-compiling. GitHub Actions builds
> Linux and both macOS architectures on real machines; see `.github/workflows/build.yml`.

## Implementation notes

- **DASH**: Bilibili splits high-quality video and audio into separate streams; both are downloaded
  and merged with `-c copy`, which only rewrites the container (no quality loss, seconds instead of
  minutes). `+faststart` moves the MP4 index to the front for instant seeking.
- **WBI signing**: `md5(sorted_query + "&wts=…" + mixin_key)`; the mixin key is derived from
  `nav`'s image/sub keys through a 64-entry permutation table. Non-signed requests fall back to
  `/x/player/playurl`.
- **Node probing**: a concurrent `HEAD` to every `baseUrl`/`backupUrl`; the first to answer wins
  (latency, not throughput).
- **Ctrl+C responsiveness**: the main thread polls with `futures.wait(timeout=0.3)` instead of
  `as_completed`'s unbounded wait — on Windows a thread blocked in an unbounded wait cannot process
  the pending signal, which looks like "Ctrl+C does nothing". After confirming the interrupt it calls
  `os._exit(130)`, so it never waits for non-daemon download threads.
- **Concurrency & bars**: a `ThreadPoolExecutor` with at most 4 workers, one video per worker (video
  and audio streams stay sequential inside a worker). Each worker owns a fixed `tqdm` `position`
  slot, giving 4 independent stacked bars; all other output goes through `tqdm.write` so it clears
  and redraws those lines instead of corrupting them. playurl calls are lock-serialised with a 0.5 s
  minimum interval; node probing uses its own short-lived pool.
- **Atomic writes**: `os.replace()` in the same directory makes the final rename atomic on Windows
  and POSIX alike, so a failure never leaves a half-written file in place of a good one.

## Legal

For personal study and backup of content you are entitled to access. Respect Bilibili's terms of
service; do not redistribute copyrighted material and do not use it for bulk scraping.
