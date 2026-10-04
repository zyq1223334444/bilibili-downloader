#!/usr/bin/env bash
# =====================================================================
#  Build the Linux / macOS binaries for bilibili-downloader with Nuitka.
#
#  Run this *inside* the target OS (WSL, a container, a Mac, CI):
#      bash build_unix.sh
#
#  Nuitka compiles Python to C and then calls the platform's own linker, so
#  there is no cross-compiling: a Linux binary must be built on Linux, a
#  macOS binary on macOS. The GitHub Actions workflow in
#  .github/workflows/build.yml does all three platforms for you.
#
#  Requirements:
#    Debian/Ubuntu:  sudo apt-get install -y python3-venv python3-dev gcc g++ patchelf ffmpeg
#    macOS:          brew install python@3.13 ffmpeg   (Xcode command line tools)
#    then:           python3 -m venv .venv && .venv/bin/pip install nuitka zstandard requests tqdm
#
#  ffmpeg is NOT bundled (external ~100 MB program) and must be on PATH at
#  runtime.
#
#  Produces:
#      dist_unix/bilibili_downloader                       single file (onefile)
#      dist_unix/bilibili_downloader_<os>_<arch>           same, renamed for release
#      dist_unix/bilibili_downloader_standalone/           folder build
#      dist_unix/bilibili_downloader_<os>_<arch>.tar.gz    folder build, packed
# =====================================================================
set -euo pipefail
cd "$(dirname "$0")"

PY="${PY:-python3}"
if [ -x ".venv/bin/python" ]; then
    PY=".venv/bin/python"
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

echo "[*] target : $PLATFORM / $ARCH"
echo "[*] python : $($PY -V 2>&1)"
echo "[*] nuitka : $($PY -m nuitka --version 2>&1 | head -1)"

OUT="dist_unix"
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
    bilibili_downloader.py

echo "[*] building the standalone folder ..."
"$PY" -m nuitka --standalone \
    "${COMMON[@]}" \
    --output-dir="$OUT/standalone" \
    --output-filename=bilibili_downloader \
    bilibili_downloader.py

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
