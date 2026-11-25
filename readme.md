> [🇨🇳 中文](readme.zh.md)

# bilibili-downloader

**A Bilibili downloader you can use without memorising flags.** Launch it with no arguments and it opens a GUI;
pass arguments and you get a full CLI with the same capabilities.

It pulls Bilibili's separate DASH video and audio streams, merges them into MP4 (plus MP3) with ffmpeg,
saves danmaku as native XML and ASS, and can either mux the subtitles into an MKV (toggleable track)
or burn them into the picture. Single videos, multi-part videos, collections, live recording and
subtitle merging are all included.

- **Best available quality by default** (8K / 4K / HDR / Dolby Vision, capped by your account), lossless FLAC audio first
- **Multi-thread, resumable, CDN-aware** — up to four streams at once, one progress bar each
- **GUI and CLI are feature-equal**: anything you can click has a flag
- **Never overwrites your files** — atomic writes, interrupted runs never leave half a file

---

## Contents

- [Install](#install)
- [Quick start](#quick-start)
- [GUI](#gui)
- [CLI options](#cli-options)
- [Danmaku](#danmaku)
- [Output layout](#output-layout)
- [SESSDATA credential](#sessdata-credential)
- [Resume and interrupts](#resume-and-interrupts)
- [Building from source](#building-from-source)
- [FAQ](#faq)

## Install

### 1. Installer (Windows, recommended)

Grab `bilibili_downloader_setup_<version>.exe` from [Releases](https://github.com/zyq1223334444/bilibili-downloader/releases):

- Installs to `C:\Program Files\bilibili-downloader` with a Start-menu shortcut, an icon and an uninstaller
- Optionally adds the install directory to `PATH` (on by default); the original value is backed up in the
  registry and restored on uninstall
- **It also installs ffmpeg for you.** Only the `PATH` environment variable counts (machine + user + process).
  If ffmpeg is missing you are asked once, with the real download size (about 114 MB) shown. The download
  window has overall progress, speed, time left, a stop button, and resumes if the connection drops.
  Only `bin` is kept, and `%USERPROFILE%\ffmpeg\bin` is appended to the **user `PATH`** (`HKCU\Environment`)
- Uninstall removes **only the app's own `PATH` entry** and leaves ffmpeg completely alone — files and the
  user `PATH` entry stay, so a reinstall reuses them
- Silent installs (`/VERYSILENT`, `/SILENT`) show no dialogs and download nothing; they just log a line

### 2. Portable (Windows)

| File | Form | Ctrl+C exit code |
|---|---|---|
| `bilibili_downloader.exe` | single file, ~14 MB, self-extracting | `0xC000013A` |
| `bilibili_downloader_standalone_win64.zip` | unzipped folder, starts faster | `130` (same as source) |

```powershell
.\bilibili_downloader.exe BV1xx411c7mD -q 720p --no-mp3
```

> The single-file build wraps the real program in a self-extracting bootstrap. On Ctrl+C the bootstrap exits
> first, so the shell sees `0xC000013A` instead of `130`. The program itself still shuts down cleanly
> (`[中断]`, kept `.part` files, temp dir removed) — only the exit code differs. Use the folder build if a
> script needs to check for 130.

### 3. Linux / macOS

| Platform | Single file | Folder build (recommended) |
|---|---|---|
| Linux x86_64 | `bilibili_downloader_linux_x86_64` | `bilibili_downloader_linux_x86_64.tar.gz` |
| macOS Intel | `bilibili_downloader_macos_x86_64` | `bilibili_downloader_macos_x86_64.tar.gz` |
| macOS Apple Silicon | `bilibili_downloader_macos_arm64` | `bilibili_downloader_macos_arm64.tar.gz` |

```bash
tar -xzf bilibili_downloader_linux_x86_64.tar.gz
./bilibili_downloader_standalone/bilibili_downloader BV1xx411c7mD --single -q 720p
```

These binaries are unsigned; if Gatekeeper blocks the first run, use `xattr -d com.apple.quarantine <file>`
or right-click → Open. The CI builds are CLI-only (the runners have no tcl/tk); build locally on a machine
with `python3-tk` if you want the GUI there.

### 4. From source

```powershell
git clone https://github.com/zyq1223334444/bilibili-downloader.git
cd bilibili-downloader
pip install -r requirements.txt     # requests, tqdm
python bilibili_downloader.py       # no arguments → GUI
```

Python 3.9+, tkinter for the GUI (bundled with the official Windows installer).
**ffmpeg is the only external program you need** — merging, MP3 export and subtitle work all use it.

## Quick start

```powershell
# open the GUI (quality, output, danmaku and credential are all in the window)
python bilibili_downloader.py

# one video → Desktop\<title>\<title>.mp4 and .mp3
python bilibili_downloader.py BV1xx411c7mD

# save danmaku and mux it as an MKV subtitle track (no re-encode, takes seconds)
python bilibili_downloader.py BV1xx411c7mD --danmaku light --danmaku-video soft

# keep more danmaku and burn it in (re-encode, slow, but readable anywhere)
python bilibili_downloader.py BV1xx411c7mD --danmaku full --danmaku-video hard

# only part 2 of a multi-part video; dry run
python bilibili_downloader.py "https://www.bilibili.com/video/BV1xx411c7mD?p=2" --single
python bilibili_downloader.py BV1xx411c7mD --dry-run

# audio only at 192k, into another folder
python bilibili_downloader.py BV1xx411c7mD --audio-only --mp3-bitrate 192 -o D:\videos

# merge subtitles / danmaku into an existing video (saved as a new file)
python bilibili_downloader.py --merge-sub video.mp4 danmaku.xml --sub-mode soft --merge-out D:\output

# the live-recording window (also a button in the GUI)
python bilibili_downloader.py --live
```

On first run, if no credential is found, the tool prints how to get `SESSDATA`, asks once (no echo), verifies it
and stores it in your user environment. **Open a new terminal** and later runs pick it up automatically.

## GUI

A Win11-light, two-column window: input and options on the left, episode preview and log on the right.

| Area | Contents |
|---|---|
| Links | several URLs / BV / av / b23.tv short links; load parts, paste, clear |
| Save to | Desktop by default (OneDrive redirection honoured), browse, open folder |
| Output | quality cap, MP3 bitrate, video+MP3 / video only / MP3 only |
| Danmaku | none / light / full, and not in video / soft (MKV) / burned in |
| Parts | table of index, title, duration; click a row to toggle ☑; the index box accepts `1,3-5,49-234` and stays in sync |
| Advanced | jobs, retries, timeout, reconnect limit, five toggles |
| Credential | terminal-style status card: not read / verifying / valid / expired |
| Bottom | merge subtitles, record live, start, cancel, open folder, help, ffmpeg state |
| Live window | room URL or id, quality, segment length, folder, danmaku level, preview, 10-second test, scheduled capture |
| Merge dialog | video + subtitle + output folder, soft or hard, always a new file |

Closing the main or live window minimises to the tray and keeps recording; the tray menu offers
show / record live / quit. `SESSDATA` only affects the **quality cap**, never download speed.
The window's Help covers the UI; `-h` documents the CLI.

## CLI options

| Option | Default | Meaning |
|---|---|---|
| `inputs` | prompt | URL / `BV` / `av` / `b23.tv`; several allowed |
| `-o, --output` | Desktop | output root |
| `-q, --quality` | `max` | `max 8k 4k 1080p60 1080p+ 1080p 720p60 720p 480p 360p` |
| `--mp3-bitrate` | `320` | `128 / 192 / 256 / 320` |
| `--audio-only` | off | MP3 only, skip the video stream |
| `--no-mp3` | off | MP4 only |
| `--danmaku` | `light` | `none` / `light` / `full` |
| `--danmaku-video` | `none` | `none` / `soft` (MKV track) / `hard` (burned in) |
| `--single` | off | only the linked video, ignore the collection |
| `-j, --jobs` | `4` | concurrent videos (max 4), one progress bar each |
| `--max-reconnects` | `5` | reconnects per stream (`0` disables the check) |
| `--force` | off | re-download even if present |
| `--no-probe` | off | skip CDN probing |
| `--retries` | `2` | retries per node |
| `--timeout` | `15` | network timeout in seconds |
| `--reset-sessdata` | off | ignore the stored credential and ask again |
| `--dry-run` | off | print the plan only |
| `--install-ffmpeg` | off | Windows: download ffmpeg to `~\ffmpeg` and add it to the user `PATH` |
| `--ffmpeg-source` | `auto` | `auto` / `official` / `mirror` (`ghfast.top`, faster in China) |
| `--merge-sub` | — | merge a subtitle/danmaku file into a video; with `--sub-mode soft\|hard` and `--merge-out` |
| `--gui` | off | open the GUI (the default when there are no arguments) |
| `-y, --yes` | off | never prompt |

`--danmaku-video` needs danmaku — combining it with `--danmaku none` is a parameter error, and `--audio-only`
cannot embed subtitles either. Both are rejected up front instead of failing after the download.

Collections and multi-part videos list their parts first: Enter or `y` takes everything, `n` exits, or type
`1,3,5,6-20` (ranges, full-width commas and reversed ranges are all understood). With redirected output or
`-y` nothing is asked, so CI runs unattended.

## Danmaku

**How much is kept**

| Level | What survives | Good for |
|---|---|---|
| `light` (default) | drops code/advanced comments, one per sentence per 5 s, truncates at 60 chars, at most 6 per second, drops when lanes are full | normal viewing; burning in stays readable |
| `full` | every scroll/top/bottom comment, mild overlap rather than dropping | archiving, editing |
| `none` | nothing | video only |

> Only the batch currently visible on the web page is available; popular videos commonly come up 10–20% short
> of the counter. That is Bilibili's limit, not a bug.

**Putting it into the video**

| Mode | What it does | Cost |
|---|---|---|
| `none` | keeps `.danmaku.xml` + `.danmaku.ass` | none |
| `soft` | muxes the ASS as an MKV subtitle track (default, language `chi`) | seconds, no quality loss, toggleable |
| `hard` | re-encodes with libx264 and draws the text into the picture (still `.mp4`) | slow, one generation of loss, readable anywhere |

Font size, line height and lane count are derived from the real video resolution; scrolling, top and bottom
comments share one lane map so they never overlap.

## Output layout

The root is the **Desktop** by default (read from the registry on Windows, OneDrive redirection honoured);
`-o` changes it.

```
Desktop\
├── <video title>\                 # single video
│   ├── <video title>.mp4
│   ├── <video title>.mp3
│   └── <video title>.danmaku.xml / .danmaku.ass
├── <video title>\                 # multi-part (P index keeps the order)
│   ├── P01 <part title>\ …
│   └── P02 <part title>\ …
└── <collection title>\            # collection
    └── <video title>\ …
```

With `--danmaku-video soft` the deliverable is **`.mkv`** (`.mp4` is replaced); with `hard` it stays `.mp4`.

## SESSDATA credential

Lookup order: ① `BILI_SESSDATA` in the process environment → ② the user variable in `HKCU\Environment`
(read straight from the registry so already-open terminals see it) → ③ `sessdata.txt` next to the program
→ ④ `~/.config/bilibili-downloader/sessdata`. If none exists you are asked once.

At startup the credential is checked against the `nav` endpoint: a valid one reports your quality tier, an
expired one says so and explains how to replace it, instead of silently dropping to 480P. To set it manually:

```powershell
setx BILI_SESSDATA "your-sessdata"
```

To obtain it: sign in on the web, press F12, open Application → Cookies → `https://www.bilibili.com`,
copy the value named `SESSDATA`.

> ⚠️ `SESSDATA` is a login credential: never commit it, never share it. If it leaks, sign out of all devices
> in Bilibili's security settings immediately.

## Resume and interrupts

- **Ctrl+C is always safe**: the main thread polls every 0.3 s, tells the workers to stop and exits at once
  (exit code 130). Everything downloaded so far is kept as `.part` / `.m4s` and the next run resumes
- Video and audio go to `<name>.video.m4s.part` / `.audio.m4s.part`; a rerun continues with `Range`
- On success the parts are renamed, merged, exported and deleted; on failure they stay, so a rerun resumes
- A byte count that disagrees with `Content-Length` counts as a failure and is retried; a `416` (local state
  out of sync with the remote) clears the breakpoint and starts over

Status markers: `[跳过]` already present, `[重试]` a node failed this attempt (the line says whether it retries
the node or moves on), `[重连]` speed fell below 30% of its own average for 10 s, `[成功]` recovered,
`[失败]` gave up, `[完成]` the produced file and size, `[弹幕]` captured/kept counts, `[结果]` the batch
summary, `[中断]` you pressed Ctrl+C.

> `[重试]` is **not** a failure — read the end of the line and the `[成功]` / `[失败]` that follows it.

## Building from source

| Artifact | Command |
|---|---|
| Windows single-file exe | `build\build_exe.bat` → `build\out\bilibili_downloader.exe` |
| Windows folder build + zip | `build\build_exe_standalone.bat` |
| Windows installer (Inno Setup 6.5+) | `build\build_installer.bat` |
| Linux / macOS | `bash build/build_unix.sh` (on that platform) |

Requires `pip install -r requirements.txt nuitka zstandard`, plus **MSVC 14.3+** on Windows
(Nuitka cannot use MinGW with Python 3.13+). The parameters that matter:

- `--include-package-data=certifi` — without it the exe starts but every HTTPS request fails to find a CA bundle
- `--windows-console-mode=force` — otherwise you get a GUI-subsystem binary with no stdout
- `--enable-plugin=tk-inter` — bundles the Tcl/Tk runtime, needed for the GUI
- `--windows-icon-from-ico=assets/app.ico` — the program icon, generated from `assets/icon-source.png`
  into a multi-size ICO by `build\make_icon.ps1`

**ffmpeg is never bundled.** The installer's download logic lives in `build/ffmpeg_setup.ps1`:
`-Mode Size` reads the real length with `GET + Range: 0-0`, `-Mode Url` returns the selected source,
`-Mode Download` runs an 8-thread transfer, `-Mode Install` extracts and self-checks. The download window is
hand-drawn with WinForms and opts into Per-Monitor V2 DPI plus GDI text rendering, so text stays crisp at
125% / 150% scaling instead of being stretched into mush.

> Linux / macOS cannot be built on Windows: Nuitka invokes the target platform's own compiler and has no
> cross-compilation. The repo builds them on real runners via GitHub Actions (`.github/workflows/build.yml`).

## FAQ

| Symptom | Explanation |
|---|---|
| `ffmpeg not found` | Install it and put it on `PATH`; on Windows use `--install-ffmpeg` or just run the installer |
| "Install ffmpeg?" prompt | Without it you can still download streams but **cannot merge MP4, export MP3 or embed subtitles** |
| Only 360P/480P | No valid `SESSDATA`, or your account does not have that tier |
| GUI will not start | tkinter is missing; when building add `--enable-plugin=tk-inter` |
| Parts preview is empty | Click "load parts" first; reload after changing links or the "current only" toggle |
| Index box does nothing | It applies on Enter or the apply button; `0`, out-of-range and `abc` report why and keep the old selection |
| Fewer danmaku than the page | The endpoint only exposes the visible batch — see above |
| Burned-in version is slow/large | `hard` re-encodes by design; use `soft` for archiving |
| `该视频没有 DASH 流` | Anime/movie content or a very old upload; normal submissions only |
| `这是番剧/影视内容` | The API returned a `redirect_url`; episodes are unsupported |
| `code=62002 / 62004` | Hidden or under review |
| Progress stalls | A node switch is in progress; read the "node x/y attempt n failed" line |

## Changelog

**2.1.7** removes the black console window the app used to spawn (console-mode is now attach) and cuts the installer stalls — install click, ffmpeg prompt, download window, final "installed" message — down to roughly a second each (one combined info probe, warmed up while the Ready page is shown, and the unpack now happens inside the download window); **2.1.6** re-lays out the installer download window back to the earlier, airier composition (width now driven by the longest line, so the subtitle, the percentage and the stop button are never clipped) and swaps the title-bar icon for the pink Bilibili mark; **2.1.5** fixes the window scaling for good (fonts are no longer multiplied twice, so 200% no longer turns into a smear); **2.1.4** gives the app and the installer an icon and makes that window DPI-aware with GDI text rendering, plus a visible minimum progress width. 2.1.3 restyled that window; 2.1.2 corrected the ffmpeg contract (PATH-only detection, user
`PATH` only, uninstall leaves ffmpeg alone) and fixed the hidden download window; 2.1.1 made the download
8-threaded and stoppable, trimmed subtitle merging to soft/hard with folder output, and defaulted live
recordings to the Desktop; 2.1.0 added live recording, subtitle merging and tray support.

## Legal

For personal study and backing up content you are allowed to access. Respect Bilibili's terms, do not
redistribute copyrighted material and do not use it for bulk scraping.
