@echo off
rem =====================================================================
rem  Rebuild bilibili_downloader.exe with Nuitka (Python -> C -> machine code).
rem
rem  Requirements:
rem    pip install nuitka
rem    pip install -r requirements.txt
rem    A C compiler: MSVC 14.3+ (Visual Studio 2022 Build Tools or newer).
rem    NOTE: Nuitka cannot use MinGW with Python 3.13 or newer - MSVC only.
rem
rem  Keep this file ASCII-only: cmd reads .bat files using the OEM code page,
rem  so UTF-8 text here would be mis-parsed as commands.
rem
rem  Why these flags (all measured on this machine, not guessed):
rem
rem   * VSLANG=1033 - Nuitka's Scons backend decodes cl.exe output with the
rem     "mbcs" code page. On a Chinese-locale Visual Studio that fails with
rem     "UnicodeDecodeError: 'mbcs' codec can't decode bytes ...". Forcing
rem     English compiler messages avoids it.
rem
rem   * --include-package-data=certifi - requests verifies TLS against
rem     certifi's cacert.pem, which is a data file, not code. Without it the
rem     exe starts fine but every HTTPS call dies with
rem     "Could not find a suitable TLS CA certificate bundle".
rem
rem   * --windows-console-mode=force - this is a console tool that prints
rem     progress bars; without it the exe would be a GUI-subsystem binary
rem     with no usable stdout.
rem
rem   * ffmpeg is NOT bundled - it is a ~100 MB external program. The exe
rem     calls it through shutil.which("ffmpeg"), so ffmpeg.exe must be on
rem     PATH (choco install ffmpeg / scoop install ffmpeg).
rem =====================================================================
setlocal
set "HERE=%~dp0"
set "VSLANG=1033"

where python >nul 2>&1
if errorlevel 1 goto no_python

rem locate site-packages so we can fail early with a useful message
set "SITE="
for /f "delims=" %%i in ('python -c "import sysconfig;print(sysconfig.get_paths()['purelib'])"') do set "SITE=%%i"
if not defined SITE goto no_python

if not exist "%SITE%\requests\__init__.py" goto no_requests
if not exist "%SITE%\tqdm\__init__.py" goto no_tqdm
if not exist "%SITE%\certifi\cacert.pem" goto no_certifi
if not exist "%HERE%bilibili_downloader.py" goto no_source

echo [*] site-packages : %SITE%
echo [*] Building bilibili_downloader.exe with Nuitka (takes a few minutes)...
python -m nuitka --standalone --onefile --msvc=latest ^
    --assume-yes-for-downloads ^
    --output-dir="%HERE%build" ^
    --output-filename=bilibili_downloader.exe ^
    --include-package-data=certifi ^
    --windows-console-mode=force ^
    --company-name="zyq1223334444" ^
    --product-name="Bilibili Downloader" ^
    --file-version=1.0.0.0 --product-version=1.0.0.0 ^
    --file-description="Bilibili video / multi-part / collection downloader (DASH + ffmpeg)" ^
    "%HERE%bilibili_downloader.py"
if errorlevel 1 goto build_failed

copy /y "%HERE%build\bilibili_downloader.exe" "%HERE%bilibili_downloader.exe" >nul
if errorlevel 1 goto copy_failed

echo.
echo [OK] bilibili_downloader.exe rebuilt: "%HERE%bilibili_downloader.exe"
echo      (the intermediate folder "%HERE%build" can be deleted)
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
echo [ERR] Build finished but copying the exe failed.
exit /b 1
