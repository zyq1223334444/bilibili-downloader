@echo off
rem =====================================================================
rem  bilibili_downloader.exe -- single-file (onefile) Windows build
rem
rem  Run:      build\build_exe.bat
rem  Produces: build\out\bilibili_downloader.exe
rem
rem  ---------------------------------------------------------------------
rem  Directory contract. Nothing is ever written outside build\out\.
rem
rem      build\         these scripts, installer.iss, the language file
rem      build\out\     every artefact and every Nuitka intermediate
rem      <repo root>    bilibili_downloader.py, requirements.txt, readme*.md
rem
rem  The source therefore sits one level above this script: we cd into the
rem  repository root first (Nuitka drops its cache next to the working
rem  directory) and keep every path of our own absolute.
rem
rem  Nuitka compiles Python to C and then calls the platform's own linker,
rem  so a build always happens on the target OS. This script is Windows
rem  only; Linux and macOS are handled by build_unix.sh in this folder.
rem
rem  ---------------------------------------------------------------------
rem  Requirements
rem
rem      pip install -r requirements.txt   (requests, tqdm)
rem      pip install nuitka zstandard
rem
rem      A C compiler: MSVC 14.3+ (Visual Studio 2022 Build Tools or newer).
rem      Nuitka cannot use MinGW together with Python 3.13 or newer - MSVC
rem      only.
rem
rem  Keep this file ASCII-only: cmd reads .bat files with the OEM code page,
rem  so UTF-8 text in here would be parsed as commands.
rem
rem  ---------------------------------------------------------------------
rem  Why these flags (all measured on this machine, not guessed):
rem
rem   VSLANG=1033
rem     Nuitka's Scons backend decodes cl.exe output using the "mbcs" code
rem     page. A localized (Chinese) Visual Studio therefore aborts the build
rem     with "UnicodeDecodeError: 'mbcs' codec can't decode bytes".
rem     Forcing English compiler messages avoids it.
rem
rem   --include-package-data=certifi
rem     requests verifies TLS against certifi's cacert.pem, which is a data
rem     file rather than code. Without it the exe starts fine but every
rem     HTTPS call dies with
rem     "Could not find a suitable TLS CA certificate bundle".
rem
rem   --windows-console-mode=force
rem     This is a console tool that prints progress bars. Without the flag
rem     the exe would be a GUI-subsystem binary with no usable stdout.
rem
rem   ffmpeg is deliberately NOT bundled
rem     It is a ~100 MB external program. The exe finds it through
rem     shutil.which("ffmpeg"), so ffmpeg.exe has to be on PATH
rem     (choco install ffmpeg / scoop install ffmpeg / brew install ffmpeg /
rem     sudo apt install ffmpeg).
rem =====================================================================
setlocal
set "HERE=%~dp0"
cd /d "%HERE%.." || goto no_root
set "ROOT=%CD%"
set "OUT=%HERE%out"
set "VSLANG=1033"

where python >nul 2>&1
if errorlevel 1 goto no_python

if not exist "%ROOT%\bilibili_downloader.py" goto no_source

rem locate site-packages so we can fail early with a useful message
set "SITE="
for /f "delims=" %%i in ('python -c "import sysconfig;print(sysconfig.get_paths()['purelib'])"') do set "SITE=%%i"
if not defined SITE goto no_python

if not exist "%SITE%\requests\__init__.py" goto no_requests
if not exist "%SITE%\tqdm\__init__.py" goto no_tqdm
if not exist "%SITE%\certifi\cacert.pem" goto no_certifi

echo [*] repo root     : %ROOT%
echo [*] output        : %OUT%
echo [*] site-packages : %SITE%
echo [*] Building bilibili_downloader.exe with Nuitka (takes a few minutes) ...
python -m nuitka --standalone --onefile --msvc=latest ^
    --assume-yes-for-downloads ^
    --output-dir="%OUT%\nuitka_onefile" ^
    --output-filename=bilibili_downloader.exe ^
    --include-package-data=certifi ^
    --windows-console-mode=force ^
    --company-name="zyq1223334444" ^
    --product-name="Bilibili Downloader" ^
    --file-version=1.0.0.0 --product-version=1.0.0.0 ^
    --file-description="Bilibili video / multi-part / collection downloader (DASH + ffmpeg)" ^
    "%ROOT%\bilibili_downloader.py"
if errorlevel 1 goto build_failed

copy /y "%OUT%\nuitka_onefile\bilibili_downloader.exe" "%OUT%\bilibili_downloader.exe" >nul
if errorlevel 1 goto copy_failed

echo.
echo [OK] single file: "%OUT%\bilibili_downloader.exe"
echo      (the intermediate folder "%OUT%\nuitka_onefile" can be deleted)
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

:no_tqdm
echo [ERR] tqdm not installed. Run: pip install -r requirements.txt
exit /b 1

:no_certifi
echo [ERR] certifi (requests' CA bundle) not found. Run: pip install -r requirements.txt
exit /b 1

:build_failed
echo [ERR] Nuitka build failed. Check that a C compiler (MSVC 14.3+) is installed;
echo       Nuitka cannot use MinGW together with Python 3.13+.
exit /b 1

:copy_failed
echo [ERR] Build finished but copying the exe into "%OUT%" failed.
exit /b 1
