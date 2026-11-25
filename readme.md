> [🇨🇳 中文](readme.zh.md)

# bilibili-downloader

A downloader for Bilibili videos, multi-part videos and collections: DASH audio and video are fetched
separately, then muxed into MP4 with ffmpeg and exported to MP3. It can also grab **danmaku** (on-screen
comments), save them as Bilibili's native XML plus a ready-to-use ASS, and either **mux them into MKV as a
soft subtitle track** or **burn them into the picture**. **Started with no arguments it opens a Win11-style GUI**;
every command-line switch is still there.

---

## Features

- **Single video / multi-part / collection in one go** — one link is enough, the rest is expanded automatically;
  `--single` limits it to the item the link points at.
- **Highest quality by default** (8K / 4K / HDR / Dolby Vision, limited by your account), `-q` caps it.
- **Lossless audio first**: `dash.flac` (Hi-Res) → Dolby Atmos → highest bitrate, then MP3 export.
- **MP4 and MP3 together**: the MP4 is muxed with `-c copy -movflags +faststart` (no re-encode, done in seconds,
  seekable while downloading).
- **Danmaku you can keep and watch**: `--danmaku light` (deduplicated and rate-limited so a burned-in copy stays
  readable) or `full` (keep as much as possible), written as `.danmaku.xml` and `.danmaku.ass`;
  `--danmaku-video soft` muxes the track into MKV (no re-encode, seconds), `hard` burns it into the frame
  (re-encode, slow, but readable anywhere including phones and chat apps).
- **Live recording, GUI only** (output defaults to Desktop\<room title>\): the "录制直播" button on the main window (or `--live` to open that window straight
  away). Original quality (`qn=10000`) by default, switchable mid-recording from the qualities the room actually
  offers; written in segments so **memory stays flat no matter how long the stream runs**. Built-in preview
  (a snapshot every 12 s) and a 10-second sample clip; paste a scheduled-live link or room id and it polls until
  the room goes live, then starts recording on its own. While recording it captures **both** the light and the
  full danmaku stream (gifts / guard purchases / SC included) and **saves them separately only** as
  `.jsonl` + `.xml` + `.ass` — nothing is burned into the video.
- **Subtitle merging as its own feature**: the "合并弹幕" button, or
  `--merge-sub VIDEO SUB --sub-mode soft|hard`. Soft muxes a switchable subtitle track into an `.mkv`
  (`-c copy`), hard burns it into the frame. The output field is a **folder**; files are named
  `<video>.sub.mkv / .sub.mp4` and always written as a new file — **the source video is never overwritten** —
  and long videos are processed as a stream.
- **Minimize to tray**: closing the main window or minimizing the live window keeps the recorder running from the
  tray; the tray menu offers show / record live / quit.
- **Win11-style GUI**: two columns, inputs and options on the left, episode plan and log on the right; it sizes
  itself to the screen and the cards stretch with the window. Episodes can be ticked in the table or typed as
  `1,3-5,49-234`, and **the checkboxes and the text box stay in sync both ways**. The credential card is a
  terminal-style status block that changes with the state (nothing read / checking / valid / expired).
- **Saves to the Desktop by default** (read from the registry, OneDrive redirection included); `-o` overrides it.
- **Parallel downloads, one progress bar per thread** — up to 4 videos at once by default; the bottom lines are a
  live status table, each naming **which video and which stream** it is (e.g. `[11/22] #43 逃离棋盒 · 1080P 视频流`).
  Bars adapt to the **actual terminal width** and titles are clipped to a width budget, so percentage/size/speed
  are never squeezed out. Redirected output becomes one line every 15 s.
- **Automatic reconnect on a slow connection**: when a stream's speed falls below **30 % of its own historical
  average** (from the start up to 10 s ago) for **10 s**, the connection is dropped and the download resumes on
  another CDN node via `Range`, losing no progress (5 times by default, `--max-reconnects 0` disables it).
  **If the estimated remaining time at the current speed is under 10 s, the connection is kept.**
- **Robust downloading** — CDN node pre-selection, per-node retries with backoff, HTTP Range resume, size checks.
- **Atomic writes** — everything goes to a `.part` file and is renamed on success, so a failure never leaves a
  half-written file behind.
- **Idempotent** — finished items are skipped; failed ones keep their `.m4s` streams so a re-run resumes.
- **WBI request signing** with automatic fallback to the legacy endpoint.
- **SESSDATA is asked once** and stored in a Windows user environment variable (never in the source).
- **Tidy output tree** — sanitized names, Windows reserved names, MAX_PATH protection via shortening + hash.
- `--dry-run` preview; meaningful exit codes (`0` ok / `1` failure / `2` bad args / `130` interrupted).
- **Genuinely non-interactive** — with `-y` or redirected output it never stops to ask, even on a fresh machine.
- **Cross-platform**: one source for Windows / Linux / macOS; on Windows the credential lives in the user
  environment, elsewhere in `~/.config/bilibili-downloader/sessdata` (mode 600).

## Requirements

| Item | Notes |
|---|---|
| Python | 3.9+ (source install); the GUI also needs tkinter (bundled with the official Windows build) |
| Dependencies | `pip install -r requirements.txt` (requests, tqdm) |
| ffmpeg | Needed for muxing, MP3 export and danmaku embedding. Used from `PATH` if present; on Windows the program offers to install it to `~\ffmpeg` (or run `--install-ffmpeg`) |

## Installation

### 1. Installer (Windows, recommended)

Download the latest `bilibili_downloader_setup_<version>.exe` from
[Releases](https://github.com/zyq1223334444/bilibili-downloader/releases) and run it:

- Installs to `C:\Program Files\bilibili-downloader` with a Start-menu shortcut and an **uninstaller**
  (also listed under "Settings → Apps").
- Optionally adds the install directory to the system `PATH` (checked by default), so `bilibili_downloader`
  works from any terminal; the original `PATH` is backed up in the registry before any change and the uninstaller
  **restores it exactly** (if something else modified `PATH` in the meantime, it degrades to removing only its own
  entry, so a `;;` or trailing `;` in the original value is never mangled).
- **The installer also takes care of ffmpeg**: it checks the process `PATH`, the system `PATH`, the user `PATH`
  and `%USERPROFILE%\ffmpeg\bin`. If none has it, a **"ffmpeg download source" page** appears earlier in the wizard
  (mirror `ghfast.top` by default — usually much faster in mainland China — or the official GitHub release; the page is skipped
  when ffmpeg is already present); pressing "Install" on the last page then shows a dialog explaining that "without
  ffmpeg the full feature set is unavailable (no muxing, no MP3, no danmaku embedding)", **the real download size**
  (queried live, about 114 MB) and the chosen source, defaulting to "Yes". On approval a **download page** appears
  with a progress bar, speed and a "Stop" button. **Pressing "Stop" during the transfer asks whether to restart
  from the other source**, and so does a failed download — a switch always restarts from scratch, so a truncated
  file is never treated as success. Once it finishes the
  archive is extracted to `%USERPROFILE%\ffmpeg` (keeping only the files in `bin`), then
  `%USERPROFILE%\ffmpeg\bin` is appended to the **system** `PATH` (the installer already runs as administrator) and
  that one entry is remembered in `HKCU\SOFTWARE\bilibili-downloader`. A silent install (`/VERYSILENT`, `/SILENT`)
  never prompts and never downloads — it only writes a log line, so unattended deployment cannot hang on a dialog.
- Uninstalling removes only the `PATH` entry it added and **keeps the files in `~\ffmpeg`** (other tools may use
  them, and a reinstall can reuse them).

### 2. Portable (Windows single file / folder)

| Download | Form | Ctrl+C exit code |
|---|---|---|
| `bilibili_downloader.exe` | single file (~14 MB, self-extracting at start) | `0xC000013A` (see below) |
| `bilibili_downloader_standalone_win64.zip` | extracts to a folder (starts faster) | **130**, same as the source build |

```powershell
.\bilibili_downloader.exe BV1xx411c7mD -q 720p --no-mp3
.\bilibili_downloader.exe --dry-run BV1xx411c7mD
```

> **Known difference of the single-file build**: `--onefile` wraps the real program in a self-extracting
> bootstrap process. On Ctrl+C the console event reaches both, the bootstrap exits first, so the shell sees
> `0xC000013A` (displayed as `-1073741510`) instead of 130. The program itself still shuts down cleanly:
> it prints `[中断]`, keeps the `.part` files, leaves no stray processes and cleans its temp directory —
> **only the exit code differs**. If your script checks for 130, use the folder build or treat `0xC000013A`
> as "interrupted" too.

### 3. Linux / macOS

| Platform | Single file | Folder build (keeps the executable bit, recommended) |
|---|---|---|
| Linux x86_64 | `bilibili_downloader_linux_x86_64` | `bilibili_downloader_linux_x86_64.tar.gz` |
| macOS Intel | `bilibili_downloader_macos_x86_64` | `bilibili_downloader_macos_x86_64.tar.gz` |
| macOS Apple Silicon | `bilibili_downloader_macos_arm64` | `bilibili_downloader_macos_arm64.tar.gz` |

```bash
tar -xzf bilibili_downloader_linux_x86_64.tar.gz
./bilibili_downloader_standalone/bilibili_downloader BV1xx411c7mD --single -q 720p
```

> The macOS binaries are **unsigned**, so Gatekeeper may block the first run:
> `xattr -d com.apple.quarantine <file>`, or right-click → Open.
> Linux / macOS binaries are built on **real machines** by GitHub Actions (`.github/workflows/build.yml`),
> because Nuitka compiles Python to C and calls the target platform's own linker — there is no cross-compiling.
> To build yourself: `bash build/build_unix.sh` (Linux needs gcc / patchelf).
> The Linux / macOS packages from CI are **command-line only**: the runners have no Tk, and `build_unix.sh`
> silently skips the GUI plugin when `import tkinter` fails so the pipeline does not break. Build it yourself
> on a machine with `python3-tk` and the GUI is included (it uses only portable tkinter widgets).

All binaries are Nuitka builds (Python compiled to C and linked), bundling the Python runtime plus
`requests` / `tqdm` (the Windows build also carries tkinter; whether a Linux / macOS build has the GUI depends on
whether tcl/tk was present when it was built). **The only external program still needed is ffmpeg**: on Windows the binary looks
in `PATH` first and offers to install to `~\ffmpeg` if missing (`--install-ffmpeg` skips the question);
on Linux / macOS install it with your package manager (`brew install ffmpeg` / `sudo apt install ffmpeg`).

### 4. From source

```powershell
git clone https://github.com/zyq1223334444/bilibili-downloader.git
cd bilibili-downloader
pip install -r requirements.txt
python bilibili_downloader.py          # no arguments -> GUI
```

Arguments, output layout and the credential lookup order are identical to the binary builds (for a binary,
"the `sessdata.txt` next to the program" means next to the executable).

## Quick start

```powershell
# no arguments -> GUI (quality / output / danmaku / credential all chosen in the window)
python bilibili_downloader.py

# one video -> Desktop\<title>\<title>.mp4 and .mp3 (Desktop is the default root)
python bilibili_downloader.py BV1xx411c7mD

# also save the danmaku and mux it into MKV as a subtitle track (no re-encode, fast)
python bilibili_downloader.py BV1xx411c7mD --danmaku light --danmaku-video soft

# keep more danmaku and burn it into the picture (re-encode, slow, readable anywhere)
python bilibili_downloader.py BV1xx411c7mD --danmaku full --danmaku-video hard

# only part 2 of a multi-part video
python bilibili_downloader.py "https://www.bilibili.com/video/BV1xx411c7mD?p=2" --single

# show the plan without downloading
python bilibili_downloader.py BV1xx411c7mD --dry-run

# cap quality, skip MP3, different output directory
python bilibili_downloader.py BV1xx411c7mD -q 720p --no-mp3 -o D:\videos

# audio only, 192k
python bilibili_downloader.py BV1xx411c7mD --audio-only --mp3-bitrate 192

# open only the live-recording window (GUI; the main window has the same button)
python bilibili_downloader.py --live

# merge danmaku/subtitles into a video (writes <video>.sub.mkv into that folder, never touches the source)
python bilibili_downloader.py --merge-sub video.mp4 danmaku.xml --sub-mode soft --merge-out D:\output

# no ffmpeg? download the Windows build to ~\ffmpeg (about 114 MB)
python bilibili_downloader.py --install-ffmpeg

# slow from GitHub? use the mirror (ghfast.top proxies the same release)
python bilibili_downloader.py --install-ffmpeg --ffmpeg-source mirror
```

**On the first run**, if no credential is found, the script prints how to get one and asks for `SESSDATA` once
(input is hidden); once verified it is stored in the Windows user environment variable `BILI_SESSDATA`.
Open a **new terminal** afterwards and it is picked up automatically.

### The GUI

Start it with no arguments (or `--gui`). It is a light Win11-style two-column window: inputs and options on the
left, episode plan and log on the right; the size follows the screen and the cards stretch with the window.

| Area | Contents |
|---|---|
| Links | one or more video links / `BV` / `av` / `b23.tv` short links; "Read plan", "Paste", "Clear" |
| Save to | Desktop by default; "Browse" to change it, "Open folder" to jump into Explorer |
| Output | quality cap, MP3 bitrate, three-way choice (video + MP3 / video only / MP3 only) |
| Danmaku | `none / light / full`, and `keep out / soft subtitle (MKV) / burn into picture` |
| Episodes | table of index / title / duration; click a row to toggle ☑, plus "Select all / none"; the **index box** accepts `1,3-5,49-234` (spaces, `、` and full-width commas work too) — Enter or "Apply index" |
| Advanced | jobs, retries per node, timeout, reconnect cap, five checkboxes (single item, force, no probing, dry run, reset credential) |
| Credential | terminal-style status block that changes with the state (below); once signed in the entry collapses into "Replace / Clear" |
| Bottom | Start / Cancel / Open folder / Help + status line + ffmpeg state ("Install ffmpeg" only appears when it is missing) |

**Episodes and the index box stay in sync both ways**: clicking a row re-compresses the text into `3-5,49-234`;
typing a range and pressing Enter (or "Apply index") re-checks the table. Out-of-range values or `abc` produce a
message with the reason and keep the previous selection. Reading the plan only fetches metadata, nothing is downloaded.

**Credential states** (the black block is terminal-like: monospace font, coloured prompt):

| State | Display |
|---|---|
| Nothing read yet | `> 游客模式 · 还没读取凭证` plus the guest quality ceiling |
| Read, verifying | `> 已读取 SESSDATA（来源：环境变量 / 凭证文件 …）` + `正在校验…` |
| Verified | `> 已登录 · 凭证有效`, entry hidden, masked credential and "Replace / Clear" |
| Rejected | `> 凭证已失效或已过期`, entry cleared so a new value can be pasted |

`SESSDATA` only raises the **quality ceiling** (1080P+ / 4K / lossless audio need it); **it has nothing to do
with download speed**. "Save and verify" writes it to the Windows user environment and checks it against the
account API immediately, showing the result in the status block.

The "Help" button opens the **GUI-specific** help (what each control means); its last line always reads
`使用 -h/--help 查看命令行帮助` — the command-line reference is a separate document.

> Downloads run on a worker thread and stream their log into the pane; the episode plan is handled inside the
> window, so it never waits for input that can only be typed into a terminal. The worker adds `-y` on its own,
> so it cannot block on a question either.

## Output layout

The default root is the **Desktop** (read from the registry on Windows, so OneDrive's `OneDrive\Desktop`
redirection is honoured); `-o` overrides it. This is the default setup (`--danmaku light --danmaku-video none`):

```
Desktop\
├── <title>\                            # single video (two levels)
│   ├── <title>.mp4
│   ├── <title>.mp3
│   ├── <title>.danmaku.xml             # raw danmaku (Bilibili's own XML)
│   └── <title>.danmaku.ass             # converted ASS, any player can load it
├── <title>\                            # multi-part video (three levels, P index keeps the order)
│   ├── P01 <part title>\
│   │   ├── P01 <part title>.mp4
│   │   ├── P01 <part title>.mp3
│   │   └── P01 <part title>.danmaku.xml / .ass
│   └── P02 <part title>\……
└── <collection title>\                 # collection (three levels)
    ├── <video title>\
    │   ├── <video title>.mp4 / .mp3 / .danmaku.xml / .danmaku.ass
    │   └── <video title>\P01 <part title>\……   # four levels when a collection item is itself multi-part
```

Two things change, the depth stays the same otherwise:

- `--danmaku-video soft`: the result becomes **`.mkv`** (the `.mp4` is removed). MKV is one of the few common
  containers that can carry a toggleable ASS subtitle track together with Bilibili's HD/4K codecs; remuxing
  needs no re-encode and takes seconds.
- `--danmaku-video hard`: the result stays `.mp4` with the danmaku baked into the picture; the danmaku files
  are still kept.

## Danmaku

### How many: `--danmaku light / full`

| Mode | What is kept | Good for |
|---|---|---|
| `light` (default) | Drops advanced/code comments; the same sentence is kept once per 5 s; longer than 60 chars is truncated; **at most 6 per second**; when every lane is busy that comment is **dropped** rather than overlapping | Watching without a wall of text, and burning in without covering faces |
| `full` | Drops everything except scrolling/top/bottom types (code comments always go); the rest is kept, and when lanes run out the earliest free one is reused, allowing slight overlap | Archiving, editing, picking later |
| `none` | No danmaku | Video only |

> What is fetched is what the **web player currently shows** (`comment.bilibili.com/{cid}.xml`, with a second
> endpoint as fallback). Bilibili itself limits this: the XML often has fewer comments than the video's `danmaku`
> counter (measured 3791 → 3200). The segmented protobuf endpoint (`x/v2/dm/web/seg.so`) returned **fewer**
> (1143) in testing, so it is not used — do not expect "not a single one missing".

### Into the video: `--danmaku-video soft / hard`

| Mode | What it does | Cost |
|---|---|---|
| `none` (default) | Only `.danmaku.xml` and `.danmaku.ass` | None |
| `soft` | Muxes the ASS as a subtitle track into `.mkv`, default track, language `chi` | Remux only, seconds, no quality loss; can be switched off in the player |
| `hard` | Re-encodes with libx264 and paints the comments into the frames (`.mp4`) | Slow (CPU-bound), one generation of quality loss; readable on phones and in chat apps |

Subtitle details: font size, line height and lane count are derived from the **real video resolution**
(about 40 px text and 8 s per scrolling comment at 1080P); scrolling, top and bottom comments **share one lane
map** so they never overlap on the same line; `\ { }` become full-width characters, and colours are converted
from the decimal RGB in Bilibili's `p` field to ASS `&HBBGGRR&`.

## Command-line options

| Option | Default | Meaning |
|---|---|---|
| `inputs` | interactive | One or more: video link / `BV` id / `av` id / `b23.tv` short link |
| `-o, --output` | Desktop | Output root (real Desktop from the registry on Windows, OneDrive aware) |
| `-q, --quality` | `max` | Quality cap: `max 8k 4k 1080p60 1080p+ 1080p 720p60 720p 480p 360p` |
| `--mp3-bitrate` | `320` | MP3 bitrate: `128 / 192 / 256 / 320` |
| `--audio-only` | off | MP3 only (no video stream downloaded) |
| `--no-mp3` | off | MP4 only |
| `--danmaku` | `light` | Danmaku: `none` / `light` (trimmed) / `full` (keep more) |
| `--danmaku-video` | `none` | Danmaku in the video: `none` / `soft` (MKV subtitle track) / `hard` (burned in) |
| `--single` | off | Only the item the link points at, ignore collections |
| `-j, --jobs` | `4` | Parallel workers (max 4), one progress bar each |
| `--max-reconnects` | `5` | How many times a stream may reconnect after dropping below 30 % of its historical average (`0` disables the check) |
| `--force` | off | Re-download even if the file exists |
| `--no-probe` | off | Skip CDN node probing |
| `--retries` | `2` | Attempts per node |
| `--timeout` | `15` | Network timeout (seconds) |
| `--reset-sessdata` | off | Ignore the stored credential and ask again (new account or expired) |
| `--dry-run` | off | List the plan only |
| `--install-ffmpeg` | off | Download ffmpeg (~114 MB) to `~\ffmpeg` and add it to the user `PATH` (Windows only) |
| `--ffmpeg-source` | `auto` | Where to fetch ffmpeg from: `auto` = official → mirror → gyan.dev, `official` = GitHub release, `mirror` = the `ghfast.top` proxy; a chosen source still falls back to the next reachable address |
| `--gui` | off | Open the GUI; running with no arguments does the same |
| `-y, --yes` | off | Never ask: download everything (skips range selection and credential prompts) |

> `--danmaku-video` needs danmaku, so combining it with `--danmaku none` is rejected as a bad argument;
> `--audio-only` (no video stream) cannot embed danmaku either, and is rejected up front instead of failing later.

## Choosing items on the command line

Multi-item plans are listed with numbers, then you are asked what to fetch:

```
共 54 项。回车 / y = 全部下载，n = 不下载，也可只下部分（如 1,3,5,6-20）：
> 1,3,5,6-20
[选择] 已选 20/54 项：1,3,5-6,6-20
```

| Input | Effect |
|---|---|
| Enter, `y`, `yes`, `all` | Download everything |
| `n`, `no`, `q` | Download nothing, exit (code 0) |
| `1,3,5,6-20` | Only these: ranges, duplicates, empty items (`1,,3`) and full-width commas (`1，3`) are accepted; order is normalised |
| `20-6` | A reversed range is accepted, same as `6-20` |
| Invalid (`abc`, `0`, `99`) | The reason is printed and you are asked again; three invalid answers cancel |

Afterwards it echoes `[选择] 已选 N/总数 项：1,3,5-8`; during downloads `[3/20]` means "third item in progress"
while the leading `#5` is the **original index in the list**, so it can be matched against the listing above.

> Non-interactive runs (redirected output, or `-y`) never ask and download everything, keeping scripts/CI usable.
> A single video or a single part never asks either (there is nothing to choose).
> In the GUI this selection is handled by the episode table, with exactly the same syntax in the index box.

## SESSDATA credential

**Lookup order**: ① the `BILI_SESSDATA` environment variable of the current process → ② the **Windows user
environment variable** (read directly from `HKCU\Environment`) → ③ `sessdata.txt` next to the program (next to
the script for source runs, next to the exe for binaries) → ④ `~/.config/bilibili-downloader/sessdata`.
If none is found it asks once; on Windows the value is saved to the user environment (and the current process),
elsewhere to the config file (mode 600).

> Why the registry is read directly: Windows injects environment variables only **when a process starts**, so
> already-open terminals (especially long-running shells and services) hold a stale snapshot — which used to look
> like "it is set, but the script says it is not found". Reading the registry fixes that.

**The credential is verified once against the `nav` endpoint at startup**:

| Result | Behaviour |
|---|---|
| Valid | Prints `[凭证] 校验通过（普通账号 / 大会员）` and your quality limits |
| Expired | Prints `[!] 凭证已失效……只能以游客身份下载，一般最高 480P/360P` and how to replace it; an interactive terminal also offers to re-enter it now |
| Network down | Verification skipped, the value is used as-is |

> Previously an expired credential silently downgraded to 480P, which looked like "the tool is broken"; now the
> reason is printed. Fully non-interactive runs (scripts/CI or redirected output) never ask, and neither does `-y`.
> In the GUI the same result is shown in the credential card's status block (see "The GUI").

Manual setup (PowerShell, permanent):

```powershell
setx BILI_SESSDATA "<your SESSDATA>"
```

How to get it: sign in on the Bilibili website → press `F12` → **Application** → **Cookies** → pick
`https://www.bilibili.com` → copy the value named `SESSDATA`.

Read / delete:

```powershell
[Environment]::GetEnvironmentVariable('BILI_SESSDATA','User')          # read (prints it in clear text)
Remove-ItemProperty -Path 'HKCU:\Environment' -Name 'BILI_SESSDATA'   # delete
```

> ⚠️ `SESSDATA` is equivalent to your account login: never put it in source code, never commit it, never share it.
> If it leaks, use Bilibili's "Settings → Security & Privacy → Sign out of all devices" immediately.

## Resume and interruption

- **Ctrl+C is safe and immediate**: the main thread polls every 0.3 s, tells the download threads to stop and
  **exits at once** (it does not wait for stuck threads or ffmpeg), without a traceback, with exit code 130;
  the `.part` / `.m4s` files are kept and a re-run resumes.
- Video/audio are first written to `<name>.video.m4s.part` / `<name>.audio.m4s.part`; a re-run continues with
  `Range` from the existing byte count.
- On success they become `.m4s` → muxed → exported → the temporary streams are **deleted**.
- On failure they are **kept**, so running the same command again resumes instead of starting over.
- If the byte count does not match `Content-Length` / `Content-Range`, the attempt fails and is retried, so a
  truncated file is never muxed.
- A `416` caused by a local/remote mismatch clears the resume state and downloads again from scratch.
- In the GUI, "Cancel" behaves like Ctrl+C: the current chunk finishes, the completed parts stay.

### Status markers

| Marker | Meaning |
|---|---|
| `[跳过]` | Cache or output already exists, skipped |
| `[重试]` | One attempt on one node failed, with the next step: **retry this node** / **switch node** / **no nodes left** |
| `[重连]` | Speed fell below 30 % of the historical average for 10 s: drop the connection, resume via `Range` on another node (kept if the ETA is under 10 s) |
| `[成功]` | Recovered after failures (not printed when everything went smoothly, to avoid noise) |
| `[失败]` | The item failed for good (all nodes tried); the batch exit code becomes 1 |
| `[完成]` | A produced file with its size (danmaku embeds are called out as "含弹幕软字幕" / "弹幕已烧进画面") |
| `[弹幕]` | How many comments were fetched and kept; a failure here only warns, the video is still saved |
| `[结果]` | Batch summary and failure details |
| `[中断]` | Ctrl+C (exit code 130) |

Network errors are collapsed into one readable line instead of a raw nested exception:

```
视频流：[重试] 节点 1/3 第 1 次失败（远程主机强迫关闭了一个现有的连接。（ConnectionResetError 10054））→ 换下一个节点
视频流：[成功] 第 2 个节点第 1 次尝试成功（191.4 MB，用时 42s）
#2 [完成] P02 空月之歌 第一幕 雪浪与苍林之舞（2）.mp4（191.4 MB）
```

> Key point: **a `[重试]` line is not a failure** — read the end of the line (switch node / no nodes left) and
> the `[成功]` / `[失败]` line that follows.

## FAQ

| Symptom | Explanation |
|---|---|
| `未找到 ffmpeg` | Install ffmpeg and put it on `PATH`; on Windows use `--install-ffmpeg` or the installer (it asks once) |
| "Install ffmpeg?" at startup | No ffmpeg found. Without it you can still fetch streams but **cannot mux to MP4, export MP3 or embed danmaku**; answer `n` to do only what is possible |
| GUI does not open | The source build needs tkinter (bundled with the official Windows Python); the build scripts pass `--enable-plugin=tk-inter` |
| GUI window is cut off | It is sized as a fraction of the screen (fits even 1280×720); if it still does not fit, resize it — the cards follow |
| Episode table is empty | Click "Read plan" first; re-read after changing the link or the "single item" switch |
| Typing in the index box does nothing | Press Enter or click "Apply index"; `0`, out-of-range values and `abc` show a reason and keep the old selection |
| Fewer comments than on the website | Bilibili's XML only returns the currently visible batch; popular videos are often 10–20 % short (see "Danmaku") |
| Burned-in video is slower/larger | `hard` re-encodes by design; use `soft` or `--danmaku-video none` for archiving |
| Some apps reject the `.mkv` | A container compatibility issue, not a broken file; PotPlayer/VLC/mpv and Bilibili's own player handle soft subtitles |
| Only 360P/480P available | No valid `SESSDATA`, or your account lacks the quality |
| `该视频没有 DASH 流` | Anime/movie content (only regular submissions are supported) or a very old video |
| `这是番剧/影视内容` | The API returned a `redirect_url`; episodes are out of scope |
| `code=62002 / 62004` | Video unavailable / under review |
| `《…》是付费合集` | Paid collections cannot be downloaded |
| Progress stalls for a long time | Switching nodes: retries with backoff, watch the "节点 x/y 第 n 次失败" line |

## Repository layout

The repository contains **the program** and **the means to build it**; every build **artifact** goes into one
ignored directory, so a fresh clone is always clean:

```
bilibili_downloader.py      the whole program (single file)
requirements.txt            runtime dependencies (requests, tqdm)
readme.md / readme.zh.md    this document (English / Chinese)
CHANGELOG.md                release notes
LICENSE
.github/workflows/build.yml CI: Linux + two macOS architectures
build/                      build tooling (part of the repository)
├── build_exe.bat             Windows single-file exe
├── build_exe_standalone.bat  Windows folder build + zip
├── build_installer.bat       Windows installer (calls installer.iss)
├── build_unix.sh             Linux / macOS binaries
├── installer.iss             Inno Setup script (including the ffmpeg prompt)
├── ffmpeg_setup.ps1          probes the size / downloads and extracts ffmpeg for the installer
├── ChineseSimplified.isl     Simplified Chinese strings for the installer
└── out/                      ignored: all artifacts and Nuitka intermediates
```

`.gitignore` only excludes products such as `build/out/`; the build scripts are committed, so anyone can rebuild.

## Building from source (Nuitka)

| Want | Build on | Command |
|---|---|---|
| Windows single-file exe | Windows | `build\build_exe.bat` → `build\out\bilibili_downloader.exe` |
| Windows folder build | Windows | `build\build_exe_standalone.bat` → folder + zip in `build\out\` |
| Windows installer | Windows | `build\build_installer.bat` (needs Inno Setup 6.5+) |
| Linux / macOS binaries | **the target platform** (WSL / Mac / CI) | `bash build/build_unix.sh` → `build/out/dist_unix/` |

The scripts locate the repository root themselves, so they can be run from any working directory and only ever
write into `build/out/`.

Requirements: `pip install -r requirements.txt nuitka zstandard`, plus **MSVC 14.3+** on Windows
(Visual Studio 2022 Build Tools or newer) — Nuitka **cannot use MinGW** with Python 3.13+.
Four flags worth knowing (all learned the hard way; the scripts explain them):

- `VSLANG=1033` — Nuitka's Scons backend decodes `cl.exe` output with the `mbcs` code page; a localized
  (Chinese) Visual Studio makes the build die with `UnicodeDecodeError`, forcing English messages avoids it.
- `--include-package-data=certifi` — `requests` verifies TLS against certifi's `cacert.pem`, a data file rather
  than code. Without it the exe starts but every HTTPS call fails with
  *"Could not find a suitable TLS CA certificate bundle"*.
- `--windows-console-mode=force` — this is a console tool; without the flag it becomes a GUI-subsystem binary
  with no usable stdout.
- `--enable-plugin=tk-inter` — ships the Tcl/Tk runtime and tcl data files, otherwise the GUI cannot start.
  All three Windows scripts first try `import tkinter`: if it is missing they stop with instructions,
  while `build_unix.sh` degrades to a command-line-only build so CI does not break on machines without tcl/tk.

The installer is compiled with **Inno Setup 6.5+**: `winget install --id JRSoftware.InnoSetup -e`.
Its `[Code]` section backs up the original system `PATH` into the registry before modifying it and restores it
byte-for-byte on uninstall; the ffmpeg part is done by `build/ffmpeg_setup.ps1`
(`-Mode Size` reads the real size via `GET + Range: 0-0` and `Content-Range`, `-Mode Url` returns the official or
mirrored address for `-Source`, `-Mode Install` downloads, extracts and self-tests). That script is deliberately
ASCII-only (PowerShell 5.1 reads it as ANSI).

**ffmpeg is never bundled** — it is an external ~114 MB program, looked up in `PATH` then
`%USERPROFILE%\ffmpeg\bin`. On Windows the program itself offers to install it (`--install-ffmpeg` skips the
question) and the installer does it once for the user; on Linux / macOS install it from your package manager.
The download URL is not hard-coded: the GitHub API is used to find the current `*essentials_build.zip`
(gyan.dev measured ~30 KB/s from China, GitHub 1 MB/s+, the `ghfast.top` mirror 2–3 MB/s). The source is
selectable: `official` goes to GitHub, `mirror` prefixes `https://ghfast.top/`, `auto` tries them in turn,
and any unreachable address simply hands over to the next one — pressing "Stop" in the installer offers the
same switch. The size shown in the prompt is the real byte count queried at that moment.

> **Why Linux/macOS cannot be built on Windows**: Nuitka compiles Python to C and then invokes the **target
> platform's** compiler and linker — there is no cross-compiling. GitHub Actions builds Linux and both macOS
> architectures on real machines, see `.github/workflows/build.yml`.

## Implementation notes (for readers of the code)

- **DASH split**: Bilibili serves HD video and audio as two streams; both are downloaded and muxed with
  `-c copy`, so it is a container change rather than a re-encode and takes seconds. `+faststart` moves the index
  to the front so playback can seek immediately.
- **WBI signing**: `w_rid = md5(sorted query + "&wts=<timestamp>" + mixin_key)`, where `mixin_key` comes from the
  `img_url` / `sub_url` returned by `nav`, permuted through a 64-entry table; a failed signed call falls back to
  the legacy endpoint.
- **Node selection**: concurrent `HEAD` requests to `baseUrl` and every `backupUrl`, first success wins
  (latency, not bandwidth).
- **Danmaku**: one `GET comment.bilibili.com/{cid}.xml` (fallback `api.bilibili.com/x/v1/dm/list.so?oid={cid}`),
  extracting `<d p="time,mode,size,color,…">text</d>`. Responses are occasionally raw gzip/deflate with a wrong
  `Content-Encoding`, so `\x1f\x8b` / zlib headers are checked as well; text goes through `html.unescape` and
  control characters are stripped. `light` deduplicates per 5 s bucket and caps 6 per second so a burned-in copy
  does not become a wall of text.
- **ASS generation**: `PlayRes` is the real video resolution; font size, line height and lane count scale with
  the height; all three comment types share one `lanes` map so scrolling and top comments never overlap; colours
  are converted from decimal RGB in the `p` field to `&HBBGGRR&`, and `\ { }` become full-width.
- **Two ffmpeg pitfalls**: ① an absolute path in the `ass=` filter breaks on Windows because the drive colon is
  parsed as the `original_size` separator (`ass=C\:/…` fails), so the subtitle directory is passed as `cwd` and
  only the file name is quoted; ② soft subtitles must be remuxed into MKV (`-c copy -c:s ass`), because players
  generally ignore ASS inside MP4.
- **Atomic writes**: `os.replace()` within the same directory is atomic on both Windows and POSIX.
- **Ctrl+C handling**: the main thread **polls** with `futures.wait(timeout=0.3)` instead of blocking in
  `as_completed` — on Windows a main thread stuck in an unbounded wait cannot process pending signals, which
  looks like "Ctrl+C does nothing"; after confirming the interruption it exits with `os._exit(130)` without
  waiting for non-daemon download threads.
- **Concurrency / progress bars**: `ThreadPoolExecutor` with at most 4 workers, one video per worker (its video
  and audio streams are still sequential inside that worker); bars are stacked with `tqdm(position=slot)` so four
  threads produce four non-overlapping bars, and ordinary output goes through `tqdm.write`; `playurl` calls are
  serialized behind a lock with a 0.5 s minimum interval, and probing uses a separate temporary pool.
- **GUI**: tkinter has no rounded widgets, so cards and buttons are drawn on `Canvas` (rounded polygon plus
  hover/pressed/disabled states); the episode list is a `ttk.Treeview` where clicking a row toggles ☑ and stays
  in sync with the index box; credential verification runs on a worker thread and results return through a
  `queue` to the main thread, so tkinter is never touched from another thread.

## Changelog

See [CHANGELOG.md](CHANGELOG.md). 2.1.1 downloads ffmpeg with 8 threads in the installer (total progress + total
speed, stoppable, resumes after a dropped connection), keeps only soft / hard subtitle merging and picks a folder
for output, defaults live recordings to `Desktop\<room title>\`, and no longer removes the ffmpeg PATH entry on
uninstall; 2.1.0 adds live recording (original quality by default, switchable mid-recording, segmented writes,
preview, scheduled rooms that record themselves, and both danmaku streams saved separately)
plus subtitle merging as its own feature (soft-MKV / burned-in, always a new file), and lets the window
minimize to the tray; 2.0.4 fixes the "Unclosed constant" error that 2.0.3 raised in the installer when ffmpeg was
missing; 2.0.3 adds a selectable ffmpeg download source (official GitHub release or the `ghfast.top` mirror, chosen
during setup and switchable mid-download); earlier releases brought danmaku download and embedding, automatic ffmpeg
installation, Desktop as the default output root, and the Win11-style GUI (episode preview, index input and
credential status block).

## Legal

For personal study and backing up content you are allowed to access. Respect Bilibili's terms of service,
do not redistribute copyrighted material and do not use it for bulk scraping.
