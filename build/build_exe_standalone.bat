@echo off
rem =====================================================================
rem  bilibili_downloader -- standalone *folder* Windows build, zipped
rem
rem  Run:      build\build_exe_standalone.bat
rem  Produces: build\out\bilibili_downloader_standalone_win64\bilibili_downloader.exe
rem            build\out\bilibili_downloader_standalone_win64.zip
rem
rem  ---------------------------------------------------------------------
rem  Why a second script at all?
rem
rem  Nuitka's --onefile wraps the real program in a self-extracting
rem  bootstrap that starts the actual process as a child. A console Ctrl+C
rem  is delivered to both; the bootstrap dies first with 0xC000013A
rem  (STATUS_CONTROL_C_EXIT), and that is the code the parent shell sees.
rem  The documented "Ctrl+C -> 130" is lost, even though the program itself
rem  interrupts cleanly, prints [中断] and keeps its .part resume data.
rem
rem  This build has no bootstrap, so the exit code is exactly 130 and the
rem  startup does not have to unpack anything. Trade-off: the result is a
rem  folder instead of a single file. Ship both and let people choose:
rem  onefile for convenience, this one for exact exit codes and faster start.
rem
rem  ---------------------------------------------------------------------
rem  Layout: we always work from the repository root (one level up) and
rem  write only inside build\out\. See build_exe.bat for the full directory
rem  contract and for the reasons behind the VSLANG / certifi / console-mode
rem  flags - read that one first, they apply here unchanged.
rem
rem  Requires: python, requests, tqdm, certifi, nuitka and MSVC 14.3+.
rem  Keep this file ASCII-only: cmd reads .bat files with the OEM code page.
rem =====================================================================
setlocal
set "HERE=%~dp0"
cd /d "%HERE%.." || goto no_root
set "ROOT=%CD%"
set "OUT=%HERE%out"
set "OUTDIR=%OUT%\nuitka_standalone"
set "DIST=%OUTDIR%\bilibili_downloader.dist"
set "STAGE=%OUT%\bilibili_downloader_standalone_win64"
set "ZIP=%OUT%\bilibili_downloader_standalone_win64.zip"
set "VSLANG=1033"

where python >nul 2>&1
if errorlevel 1 goto no_python

if not exist "%ROOT%\bilibili_downloader.py" goto no_source

set "SITE="
for /f "delims=" %%i in ('python -c "import sysconfig;print(sysconfig.get_paths()['purelib'])"') do set "SITE=%%i"
if not defined SITE goto no_python
if not exist "%SITE%\requests\__init__.py" goto no_requests
if not exist "%SITE%\certifi\cacert.pem" goto no_certifi

echo [*] repo root     : %ROOT%
echo [*] output        : %STAGE%
echo [*] Building the standalone folder with Nuitka (takes a few minutes) ...
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
    "%ROOT%\bilibili_downloader.py"
if errorlevel 1 goto build_failed

if not exist "%DIST%\bilibili_downloader.exe" goto no_dist

rem Stage a properly named top-level folder, otherwise unzipping would
rem scatter 26 loose files (exe + DLLs + pyd) straight into the user's
rem current folder.
if exist "%STAGE%" rmdir /s /q "%STAGE%"
mkdir "%STAGE%"
xcopy /e /i /y /q "%DIST%\*" "%STAGE%\" >nul
if errorlevel 1 goto stage_failed

if exist "%ZIP%" del /f /q "%ZIP%"
echo [*] Zipping "%STAGE%" ...
powershell -NoProfile -Command "Compress-Archive -Path '%STAGE%' -DestinationPath '%ZIP%' -CompressionLevel Optimal -Force"
if errorlevel 1 goto zip_failed

echo.
echo [OK] standalone exe : "%STAGE%\bilibili_downloader.exe"
echo [OK] zip for release: "%ZIP%"  (contains the folder as its root)
exit /b 0

:no_root
echo [ERR] Could not enter the repository root from "%HERE%".
exit /b 1

:no_python
echo [ERR] python not found on PATH.
exit /b 1

:no_source
echo [ERR] bilibili_downloader.py not found at "%ROOT%".
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

:stage_failed
echo [ERR] Could not copy the dist folder into "%STAGE%".
exit /b 1

:zip_failed
echo [ERR] Build OK but zipping failed.
exit /b 1
