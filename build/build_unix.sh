#!/usr/bin/env bash
# =====================================================================
#  bilibili-downloader -- Linux / macOS build
#
#  Run *inside the target OS* (WSL, a container, a real Mac, CI):
#      bash build/build_unix.sh
#
#  Produces, all inside build/out/dist_unix/:
#      bilibili_downloader                      single file (onefile)
#      bilibili_downloader_<os>_<arch>          the same, renamed for the release
#      bilibili_downloader_standalone/          folder build
#      bilibili_downloader_<os>_<arch>.tar.gz   folder build, packed
#
#  ---------------------------------------------------------------------
#  Directory contract. This script lives in build/ and never writes outside
#  build/out/. It resolves the repository root itself (one level up), so it
#  can be started from any working directory.
#
#      build/         these scripts, installer.iss, the language file
#      build/out/     every artefact and every Nuitka intermediate
#      <repo root>    bilibili_downloader.py, requirements.txt, readme*.md
#
#  ---------------------------------------------------------------------
#  Why there is no cross-compiling
#
#  Nuitka compiles Python to C and then calls the platform's own compiler
#  and linker. A Linux binary must therefore be built on Linux and a macOS
#  binary on macOS; a Windows machine can produce neither. The GitHub
#  Actions workflow in .github/workflows/build.yml covers all three
#  platform/arch combinations on real machines - run it by hand, or push a
#  tag and the binaries are attached to that release automatically.
#
#  Requirements
#      Debian/Ubuntu: sudo apt-get install -y python3-venv python3-dev gcc g++ patchelf ffmpeg
#      macOS:         brew install python@3.13 ffmpeg   (plus the Xcode command line tools)
#      then:          python3 -m venv .venv && .venv/bin/pip install nuitka zstandard requests tqdm
#
#  A virtualenv at <repo root>/.venv is picked up automatically when present.
#  To use one that lives anywhere else, point PY at it explicitly:
#      PY=/root/venv/bin/python bash build/build_unix.sh
#
#  ffmpeg is deliberately NOT bundled - it is a ~100 MB external program and
#  has to be on PATH at runtime, or the merge and the MP3 export cannot run.
# =====================================================================
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"   # .../build
ROOT="$(cd "$HERE/.." && pwd)"                         # repository root
OUT="$HERE/out/dist_unix"
SOURCE="$ROOT/bilibili_downloader.py"

cd "$ROOT"

if [ ! -f "$SOURCE" ]; then
    echo "[ERR] bilibili_downloader.py not found at $SOURCE"
    exit 1
fi

PY="${PY:-python3}"
if [ -x "$ROOT/.venv/bin/python" ]; then
    PY="$ROOT/.venv/bin/python"
fi

# Fail with a readable message instead of letting the checks below mislead.
if ! "$PY" -c 'import nuitka' > /dev/null 2>&1; then
    echo "[ERR] nuitka is not installed for $PY"
    echo "      Run: $PY -m pip install nuitka zstandard"
    exit 1
fi

case "$(uname -s)" in
    Linux)  PLATFORM=linux ;;
    Darwin) PLATFORM=macos ;;
    *) echo "[ERR] unsupported OS: $(uname -s)"; exit 1 ;;
esac
case "$(uname -m)" in
    x86_64|amd64) ARCH=x86_64 ;;
    arm64|aarch64) ARCH=arm64 ;;
    *) ARCH="$(uname -m)" ;;
esac
TAG="${PLATFORM}_${ARCH}"

echo "[*] repo root : $ROOT"
echo "[*] target    : $PLATFORM / $ARCH"
echo "[*] python    : $($PY -V 2>&1)"
echo "[*] nuitka    : $($PY -m nuitka --version 2>&1 | head -1)"

if ! "$PY" -c 'import requests, tqdm, certifi' 2>/dev/null; then
    echo "[ERR] requests / tqdm / certifi missing. Run: pip install -r requirements.txt"
    exit 1
fi

rm -rf "$OUT"
mkdir -p "$OUT"

COMMON=(
    --assume-yes-for-downloads
    --include-package-data=certifi
    --company-name="zyq1223334444"
    --product-name="Bilibili Downloader"
    --product-version=1.0.0
    --file-version=1.0.0
    --file-description="Bilibili video / multi-part / collection downloader (DASH + ffmpeg)"
)

echo "[*] building the single-file (onefile) binary ..."
"$PY" -m nuitka --standalone --onefile \
    "${COMMON[@]}" \
    --output-dir="$OUT" \
    --output-filename=bilibili_downloader \
    "$SOURCE"

echo "[*] building the standalone folder ..."
"$PY" -m nuitka --standalone \
    "${COMMON[@]}" \
    --output-dir="$OUT/standalone" \
    --output-filename=bilibili_downloader \
    "$SOURCE"

STAGE="$OUT/bilibili_downloader_standalone"
rm -rf "$STAGE"
mv "$OUT/standalone/bilibili_downloader.dist" "$STAGE"
rm -rf "$OUT/standalone"

cp "$OUT/bilibili_downloader" "$OUT/bilibili_downloader_${TAG}"
chmod +x "$OUT/bilibili_downloader" "$OUT/bilibili_downloader_${TAG}" "$STAGE/bilibili_downloader"

echo "[*] packing the folder build ..."
tar -C "$OUT" -czf "$OUT/bilibili_downloader_${TAG}.tar.gz" bilibili_downloader_standalone

echo
echo "[OK] artifacts:"
ls -lh "$OUT" | sed 's/^/     /'
echo
echo "     $OUT/bilibili_downloader_${TAG}                 (single file)"
echo "     $OUT/bilibili_downloader_${TAG}.tar.gz          (folder, packed)"
echo
echo "     remember: the binaries still need ffmpeg on PATH at runtime."
