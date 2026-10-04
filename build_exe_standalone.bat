@echo off
rem =====================================================================
rem  Build the *standalone folder* variant of bilibili_downloader and zip it.
rem
rem  Why a second script?  Nuitka's --onefile wraps the real program in a
rem  self-extracting bootstrap (parent process) that starts a child. A console
rem  Ctrl+C is delivered to both, the bootstrap dies first with
rem  0xC000013A (STATUS_CONTROL_C_EXIT), and that is the exit code the shell
rem  sees - the documented "Ctrl+C -> 130" is lost even though the program
rem  itself interrupts cleanly. The standalone build has no bootstrap, so the
rem  exit code is exact (130) and startup does not unpack anything.
rem
rem  Trade-off: the result is a folder, not a single file. Ship both and let
rem  people pick: onefile for convenience, this one for exact exit codes and
rem  faster startup.
rem
rem  Requirements and the reasons behind VSLANG / --include-package-data are
rem  documented in build_exe.bat - read that first.
rem
rem  Keep this file ASCII-only: cmd reads .bat files using the OEM code page.
rem =====================================================================
setlocal
set "HERE=%~dp0"
set "VSLANG=1033"
set "OUTDIR=%HERE%build_standalone"
set "DIST=%OUTDIR%\bilibili_downloader.dist"
set "ZIP=%HERE%bilibili_downloader_standalone_win64.zip"

where python >nul 2>&1
if errorlevel 1 goto no_python

set "SITE="
for /f "delims=" %%i in ('python -c "import sysconfig;print(sysconfig.get_paths()['purelib'])"') do set "SITE=%%i"
if not defined SITE goto no_python
if not exist "%SITE%\requests\__init__.py" goto no_requests
if not exist "%SITE%\certifi\cacert.pem" goto no_certifi
if not exist "%HERE%bilibili_downloader.py" goto no_source

echo [*] Building standalone folder with Nuitka (takes a few minutes)...
python -m nuitka --standalone --msvc=latest ^
    --assume-yes-for-downloads ^
    --output-dir="%OUTDIR%" ^
    --output-filename=bilibili_downloader.exe ^
    --include-package-data=certifi ^
    --windows-console-mode=force ^
    --company-name="zyq1223334444" ^
    --product-name="Bilibili Downloader" ^
    --file-version=1.0.0.0 --product-version=1.0.0.0 ^
    --file-description="Bilibili video / multi-part / collection downloader (DASH + ffmpeg)" ^
    "%HERE%bilibili_downloader.py"
if errorlevel 1 goto build_failed

if not exist "%DIST%\bilibili_downloader.exe" goto no_dist

if exist "%ZIP%" del /f /q "%ZIP%"
echo [*] Zipping "%DIST%" ...
powershell -NoProfile -Command "Compress-Archive -Path '%DIST%\*' -DestinationPath '%ZIP%' -CompressionLevel Optimal -Force"
if errorlevel 1 goto zip_failed

echo.
echo [OK] standalone exe : "%DIST%\bilibili_downloader.exe"
echo [OK] zip for release: "%ZIP%"
exit /b 0

:no_python
echo [ERR] python not found on PATH.
exit /b 1

:no_source
echo [ERR] bilibili_downloader.py not found next to this script.
exit /b 1

:no_requests
echo [ERR] requests not installed. Run: pip install -r requirements.txt
exit /b 1

:no_certifi
echo [ERR] certifi (requests' CA bundle) not found. Run: pip install -r requirements.txt
exit /b 1

:build_failed
echo [ERR] Nuitka build failed. Check that a C compiler (MSVC 14.3+) is installed;
echo       Nuitka cannot use MinGW together with Python 3.13+.
exit /b 1

:no_dist
echo [ERR] Build reported success but "%DIST%\bilibili_downloader.exe" is missing.
exit /b 1

:zip_failed
echo [ERR] Build OK but zipping failed.
exit /b 1
