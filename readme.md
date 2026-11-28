> [🇨🇳 中文](readme.zh.md)

# bilibili-downloader

**A Bilibili downloader you can use without memorising flags — one codebase for Windows, macOS and Linux.**

Start it with no arguments and you get the GUI; pass arguments and you get the full CLI.
DASH audio and video are fetched separately and muxed with ffmpeg into MP4 and MP3; danmaku is captured
as Bilibili XML plus ASS, optionally muxed into MKV as a switchable subtitle track or burned into the picture.
Single videos, multi-part videos, collections, live recording and subtitle merging are all here.

- **Best quality by default** (8K / 4K / HDR / Dolby Vision, capped by your account), lossless audio when available
- **Threads + resume + CDN probing**: four streams in parallel, one progress bar each
- **GUI and CLI are the same code path**: every option in the window has a flag, and neither can drift
- **Three-platform GUI**: the Windows look (rounded light cards, system tray) plus macOS / Linux fonts, icons and DPI
- **Single-instance GUI**: a second double-click brings the existing window forward instead of opening another;
  command-line runs with arguments are never blocked
- **Nothing is overwritten**: atomic writes, no half-finished files

---

## Contents

- [Install](#install)
- [Quick start](#quick-start)
- [GUI](#gui)
- [CLI](#cli)
- [SESSDATA](#sessdata)
- [Output layout](#output-layout)
- [Building from source](#building-from-source)
- [FAQ](#faq)

## Install

### Windows

Use the installer from [Releases](https://github.com/zyq1223334444/bilibili-downloader/releases)
(`bilibili_downloader_setup_<version>.exe`):

- Installs to `C:\Program Files\bilibili-downloader` with Start-menu entry, desktop icon and uninstaller
- Optionally adds the install directory to `PATH`; uninstall removes only its own entry
- Detects ffmpeg (via `PATH` only) and offers to download it once if missing: the download window shows
  total progress, speed and ETA, can be stopped and resumed, keeps only `bin` and appends
  `%USERPROFILE%\ffmpeg\bin` to the **user** `PATH`
- Silent installs (`/VERYSILENT`, `/SILENT`) never prompt and never download

Portable builds:

| File | Shape |
|---|---|
| `bilibili_downloader.exe` | Single file, self-extracting (Ctrl+C exit code is `0xC000013A`) |
| `bilibili_downloader_standalone_win64.zip` | Folder build, faster start, exit code `130` like the source version |

### macOS / Linux

| Platform | Single file | Folder build (recommended) |
|---|---|---|
| Linux x86_64 | `bilibili_downloader_linux_x86_64` | `..._linux_x86_64.tar.gz` |
| macOS Intel | `bilibili_downloader_macos_x86_64` | `..._macos_x86_64.tar.gz` |
| macOS Apple Silicon | `bilibili_downloader_macos_arm64` | `..._macos_arm64.tar.gz` |

```bash
tar -xzf bilibili_downloader_linux_x86_64.tar.gz
./bilibili_downloader_standalone/bilibili_downloader      # GUI
```

macOS binaries are unsigned: right-click → Open on first launch, or
`xattr -d com.apple.quarantine <file>`. Linux needs a display (`DISPLAY` or `WAYLAND_DISPLAY`) and
`python3-tk`; over plain SSH the program tells you to use the CLI and exits cleanly.

### From source (all three platforms)

```bash
git clone https://github.com/zyq1223334444/bilibili-downloader.git
cd bilibili-downloader
python -m pip install -r requirements.txt     # requests, tqdm
python bilibili_downloader.py                 # no arguments → GUI
```

Python 3.9+; the GUI needs tkinter (bundled with the Windows and macOS installers, `python3-tk` on Linux).
**ffmpeg is the only external program** — merging, MP3 export and danmaku embedding need it:

```bash
# Windows: one-click in the GUI, or
bilibili_downloader --install-ffmpeg
# macOS
brew install ffmpeg
# Linux
sudo apt install ffmpeg        # Debian / Ubuntu
sudo dnf install ffmpeg        # Fedora
```

## Quick start

```bash
# GUI (quality, output, danmaku, credentials are all in the window)
bilibili_downloader

# One video → Desktop/<title>/<title>.mp4 and .mp3
bilibili_downloader BV1xx411c7mD

# Keep danmaku as an MKV subtitle track (no re-encode, seconds)
bilibili_downloader BV1xx411c7mD --danmaku light --danmaku-video soft

# More danmaku, burned into the picture (re-encode, slow but universal)
bilibili_downloader BV1xx411c7mD --danmaku full --danmaku-video hard

# Only part 2 of a multi-part video; plan only
bilibili_downloader "https://www.bilibili.com/video/BV1xx411c7mD?p=2" --single
bilibili_downloader BV1xx411c7mD --dry-run

# Audio only (192k) into another directory
bilibili_downloader BV1xx411c7mD --audio-only --mp3-bitrate 192 -o ~/Videos

# Merge subtitles into an existing video (never overwrites it)
bilibili_downloader --merge-sub video.mp4 danmaku.xml --sub-mode soft

# Open the live-recording window directly
bilibili_downloader --live
```

If no credential is found on first run, it prints how to get one and asks once (input is hidden), then
stores it: Windows user environment variable, or `~/.config/bilibili-downloader/sessdata` (0600) elsewhere.

## GUI

Two-column light layout: input and options on the left, episode preview and log on the right; cards stretch
with the window.

| Area | Contents |
|---|---|
| Links | Several URLs / BV / av / b23.tv short links; "Read list", "Paste", "Clear" |
| Save to | Desktop by default (OneDrive redirection honoured on Windows), browse and open-folder buttons |
| Output | Quality cap, MP3 bitrate, video+MP3 / video only / MP3 only |
| Danmaku | None / light / full, and none / soft (MKV) / hard (burned in) |
| Episodes | Index, title, duration; click a row to toggle; the index box syncs both ways (`1,3-5,49-234`) |
| Advanced | Threads, retries, timeout, reconnect cap, single, force, no-probe, dry-run, reset credentials |
| Credentials | Terminal-style status; once valid, only "Replace" and "Clear" remain |
| Log | Live output, plus ffmpeg status and its install button |

Three windows: main, live recording and help. Every window carries the app icon (`.ico` on Windows,
`.png` on macOS / Linux). The Help window and `-h` both describe your current platform — how to install
ffmpeg, where credentials live, what happens when you minimise.

**Minimising**: on Windows the window goes to the system tray (double-click the pink B tray icon or right-click
"Show window" to bring it back; notifications use the same icon). The right-click menu is
"Show window / Record live / Merge danmaku / Quit", and the middle two open only their own window without
raising the main one. macOS / Linux have no tray here, so the button falls back to a normal minimise and the
window never disappears.

## CLI

Full reference: `bilibili_downloader -h` (examples and ffmpeg instructions are generated per platform).

| Flag | Meaning |
|---|---|
| `-o, --output` | Root directory, Desktop by default |
| `-q, --quality` | `max` / `8k` / `4k` / `1080p60` / `1080p+` / `1080p` / `720p60` / `720p` / `480p` / `360p` |
| `--mp3-bitrate` | 128 / 192 / 256 / 320 |
| `--audio-only` / `--no-mp3` | MP3 only / video only |
| `--danmaku` | `none` / `light` (dedupe + rate limit) / `full` |
| `--danmaku-video` | `none` / `soft` (MKV track) / `hard` (burned into MP4) |
| `-j, --jobs` | 1–4 downloads in parallel; `1` is serial with live progress bars |
| `--single` / `--force` / `--dry-run` | Current part only / re-download / plan only |
| `--retries` `--timeout` `--max-reconnects` `--no-probe` | Network tuning |
| `--install-ffmpeg` | Windows only: install to `~/ffmpeg` and add it to the user `PATH` |
| `--merge-sub VIDEO SUB` | Merge subtitles; `--sub-mode soft/hard`, `--merge-out` |
| `--gui` / `--live` | Open the GUI / only the live-recording window |

**Single instance**: launching with no arguments (or `--gui` / `--live`) allows one GUI at a time. A second
launch brings the existing window forward on Windows (and says so elsewhere) instead of opening another.
**Command-line runs with arguments are never blocked**, so batch jobs can start as many as they like.

## SESSDATA

Optional; it raises the quality ceiling, it does not change speed. Without it you are a guest
(usually 480p/720p, no lossless audio).

Lookup order: the `BILI_SESSDATA` environment variable → `sessdata.txt` next to the program →
user config (Windows registry user variable, or `~/.config/bilibili-downloader/sessdata`).

Get it from a logged-in browser: F12 → Application → Cookies → `bilibili.com` → copy `SESSDATA`.
It is a login credential: never commit it, never share it; if it leaks, sign out everywhere on Bilibili.

## Output layout

Desktop by default, with the platform's own path separator:

```
<Desktop>/<title>/<title>.mp4          # .mkv with soft danmaku
<Desktop>/<title>/<title>.mp3
<Desktop>/<title>/<title>.danmaku.xml
<Desktop>/<title>/<title>.danmaku.ass
Multi-part: <Desktop>/<title>/P01 <part title>/P01 <part title>.mp4
Collection: <Desktop>/<collection>/<title>/<title>.mp4
```

Illegal characters are replaced by platform rules (Windows blocks `\ / : * ? " < > |` and device names;
macOS / Linux only `/`). On Windows an over-long path has its deepest component shortened with a short hash.

## Building from source

Windows (Nuitka + MSVC, artefacts in `build/out/`):

```bat
build\build_exe_standalone.bat   :: folder build + zip
build\build_exe.bat              :: single file
build\build_installer.bat        :: installer (Inno Setup 6)
```

Linux / macOS (must run on the target OS — there is no cross-compiling):

```bash
sudo apt-get install -y python3-venv python3-dev python3-tk gcc g++ patchelf
python3 -m venv .venv && .venv/bin/pip install nuitka zstandard requests tqdm
bash build/build_unix.sh          # single file + tar.gz folder build
```

## FAQ

**ffmpeg not found**: `--install-ffmpeg` on Windows, `brew install ffmpeg` on macOS,
`apt/dnf install ffmpeg` on Linux. If it is installed but still missing, check `ffmpeg -version` in a terminal.

**The GUI does not open (Linux)**: usually no display server or no `python3-tk`. Over SSH the program
prints a hint and exits instead of throwing.

**Linux build says `GLIBC_2.38 not found`**: that symbol only exists on 24.04 and newer. The release
binary is now built on ubuntu 22.04 (glibc 2.35 floor), so 22.04 / 24.04 and Debian 12 all run it;
older distributions should run it from source.

**Double-click does nothing**: that is the single-instance guard. On Windows the existing window is raised;
if no window appears, wait a moment (a previous instance may still be shutting down) or end the stray process.

**macOS says the developer cannot be verified**: right-click → Open, or allow it in
System Settings → Privacy & Security.

**Ctrl+C exit code**: `130` for the folder build; the Windows single file wraps a self-extracting bootstrap
that exits first with `0xC000013A`, while the program itself still cleans up and keeps its resume data.

## License

MIT, see [LICENSE](LICENSE). This project only downloads and remuxes content — it does not bypass payments
or membership restrictions.
