; =====================================================================
;  Inno Setup script for bilibili-downloader
;
;  Normally you do not call this file directly - build_installer.bat does,
;  because it also verifies that the payload exists and locates ISCC.exe:
;      build\build_installer.bat
;
;  To compile it by hand:
;      "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" build\installer.iss
;
;  Relative paths are resolved against the folder holding this script
;  (build\), so every reference to a repository-root file starts with "..".
;
;      ..\readme.md, ..\readme.zh.md, ..\CHANGELOG.md, ..\LICENSE
;                                         shipped next to the exe
;      out\bilibili_downloader_standalone_win64     the payload (the folder
;                                                   build, never the onefile
;                                                   exe: it returns the exact
;                                                   exit code 130 on Ctrl+C
;                                                   and starts ~3x faster)
;      out\dist_installer                           the compiled setup .exe
;
;  ChineseSimplified.isl sits next to this file and provides the Simplified
;  Chinese texts; the compiler's own Default.isl provides English.
;
;  ffmpeg is NOT bundled inside the setup (the archive is ~110-200 MB and
;  changes with every upstream release). Instead the [Code] section:
;    1. checks PATH *and* %USERPROFILE%\ffmpeg\bin before installing;
;    2. when it is missing, asks whether to download it, showing the size
;       that ffmpeg_setup.ps1 just read from the live URL (not a guess);
;    3. on "yes", downloads it through a TDownloadWizardPage - a real
;       progress page with speed and a stop button - then unpacks it into
;       %USERPROFILE%\ffmpeg, adds that bin folder to the machine PATH and
;       remembers the entry so the uninstaller removes exactly what it added.
;  Declining is allowed - the app then runs in a degraded mode (it can still
;  download raw streams, but cannot merge/export MP3/embed danmaku).
;
;  Requires Inno Setup 6.5+ (tested with 6.7.3).
;  Keep this file UTF-8: Inno Setup reads .iss as UTF-8 (with or without BOM).
; =====================================================================

#define AppName        "Bilibili Downloader"
#define AppShortName   "bilibili-downloader"
#define AppVersion     "2.0.4"
#define AppPublisher   "zyq1223334444"
#define AppURL         "https://github.com/zyq1223334444/bilibili-downloader"
#define ExeName        "bilibili_downloader.exe"
#define SourceDir      "out\bilibili_downloader_standalone_win64"

[Setup]
; AppId identifies the application for upgrades/uninstall; never change it.
AppId={{6D4D2294-EC09-4BC1-BD6A-73FF4729FE1A}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}/issues
AppUpdatesURL={#AppURL}/releases
VersionInfoVersion={#AppVersion}
DefaultDirName={autopf}\{#AppShortName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
LicenseFile=..\LICENSE
OutputDir=out\dist_installer
OutputBaseFilename=bilibili_downloader_setup_{#AppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
UninstallDisplayIcon={app}\{#ExeName}
UninstallDisplayName={#AppName} {#AppVersion}
ChangesEnvironment=yes
SetupLogging=yes

[Languages]
Name: "chinesesimplified"; MessagesFile: "ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
chinesesimplified.CreateDesktopIcon=创建桌面快捷方式
chinesesimplified.AdditionalIcons=附加图标：
chinesesimplified.ModifyPath=把安装目录加入系统 PATH（可在任意终端直接运行 bilibili_downloader）
chinesesimplified.PathGroup=环境变量：
chinesesimplified.HelpShortcut=命令行帮助
chinesesimplified.FfmpegMissingAsk=没有检测到 ffmpeg。%n%n缺少 ffmpeg 会导致无法使用完整功能：不能合并音视频、导出 MP3，也不能把弹幕放进视频。%n%n是否现在下载并安装到：%n%1%n%n下载大小：%2%n下载源：%3
chinesesimplified.FfmpegSourceTitle=ffmpeg 下载源
chinesesimplified.FfmpegSourceDesc=装好 ffmpeg 才能合并音视频、导出 MP3、把弹幕封进视频。请选择从哪下载。
chinesesimplified.FfmpegSourceSub=（下载途中点“停止”，会再问你要不要换另一个源重新下）
chinesesimplified.FfmpegSourceOfficial=官方源（GitHub 发布页，速度取决于网络）
chinesesimplified.FfmpegSourceMirror=镜像源（ghfast.top 加速，国内通常更快）
chinesesimplified.FfmpegSwitchAsk=已停止下载。改用%1重新开始吗？
chinesesimplified.FfmpegRetryAsk=从%1下载失败：%2%n%n改用%3重试吗？
chinesesimplified.FfmpegPageTitle=正在下载 ffmpeg
chinesesimplified.FfmpegPageDesc=缺少 ffmpeg，正在下载。下载完成后会自动解压并加入 PATH，可随时点“停止下载”；停止后会问你要不要换另一个源。
chinesesimplified.FfmpegFailDetail=ffmpeg 下载或安装失败：%1%n%n也可以稍后运行 bilibili_downloader --install-ffmpeg 重试。
chinesesimplified.FfmpegDone=ffmpeg 已安装到：%n%1%n%n该目录已加入系统 PATH，新开的命令行窗口里可以直接使用 ffmpeg。
chinesesimplified.FfmpegFailed=ffmpeg 自动安装失败（可能是网络不通）。%n%n可以稍后运行 bilibili_downloader --install-ffmpeg 重试，%n或用 winget install Gyan.FFmpeg / choco install ffmpeg 手动安装。
chinesesimplified.FfmpegSkip=已跳过 ffmpeg 安装。%n%n注意：没有 ffmpeg 时只能下载分离的音视频流，无法生成 MP4/MP3、也无法嵌入弹幕。%n稍后可以运行 bilibili_downloader --install-ffmpeg 补装。
english.CreateDesktopIcon=Create a desktop shortcut
english.AdditionalIcons=Additional icons:
english.ModifyPath=Add the install folder to the system PATH (run bilibili_downloader from any terminal)
english.PathGroup=Environment:
english.HelpShortcut=Command-line help
english.FfmpegMissingAsk=ffmpeg was not found.%n%nWithout it the app cannot merge audio/video, export MP3 or embed danmaku.%n%nDownload and install it to:%n%1%n%nDownload size: %2%nSource: %3
english.FfmpegSourceTitle=ffmpeg download source
english.FfmpegSourceDesc=ffmpeg is needed to merge audio/video, export MP3 and embed danmaku. Choose where to download it from.
english.FfmpegSourceSub=(Pressing "Stop" during the download asks whether to retry from the other source.)
english.FfmpegSourceOfficial=Official (GitHub release page; speed depends on your network)
english.FfmpegSourceMirror=Mirror (ghfast.top proxy; usually faster in mainland China)
english.FfmpegSwitchAsk=Download stopped. Restart from %1?
english.FfmpegRetryAsk=Download from %1 failed: %2%n%nRetry from %3?
english.FfmpegPageTitle=Downloading ffmpeg
english.FfmpegPageDesc=ffmpeg is missing, so it is being downloaded. It will be unpacked and added to PATH automatically; you can stop at any time and will then be asked whether to retry from the other source.
english.FfmpegFailDetail=ffmpeg download or installation failed: %1%n%nYou can also run bilibili_downloader --install-ffmpeg later.
english.FfmpegDone=ffmpeg installed to:%n%1%n%nThat folder was added to the system PATH; a new terminal can run ffmpeg directly.
english.FfmpegFailed=Automatic ffmpeg installation failed (probably no network).%n%nRun bilibili_downloader --install-ffmpeg later, or install manually with winget install Gyan.FFmpeg / choco install ffmpeg.
english.FfmpegSkip=ffmpeg installation skipped.%n%nWithout ffmpeg only separate audio/video streams can be downloaded - no MP4/MP3 and no danmaku.%nYou can run bilibili_downloader --install-ffmpeg later.

[Tasks]
Name: "modifypath"; Description: "{cm:ModifyPath}"; GroupDescription: "{cm:PathGroup}"
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\readme.md"; DestDir: "{app}"; DestName: "readme.md"; Flags: ignoreversion
Source: "..\readme.zh.md"; DestDir: "{app}"; DestName: "readme.zh.md"; Flags: ignoreversion
Source: "..\CHANGELOG.md"; DestDir: "{app}"; DestName: "CHANGELOG.md"; Flags: ignoreversion
Source: "..\LICENSE"; DestDir: "{app}"; DestName: "LICENSE"; Flags: ignoreversion
; 只在安装期间用一次，装完删掉，不留在用户的临时目录里
Source: "ffmpeg_setup.ps1"; Flags: dontcopy

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#ExeName}"
Name: "{group}\{cm:HelpShortcut}"; Filename: "{sys}\cmd.exe"; Parameters: "/k ""{app}\{#ExeName}"" --help"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#ExeName}"; Tasks: desktopicon

[Run]
Filename: "{sys}\cmd.exe"; Parameters: "/k ""{app}\{#ExeName}"" --help"; Description: "{cm:HelpShortcut}"; Flags: postinstall nowait skipifsilent unchecked

[Code]
const
  EnvironmentKey = 'SYSTEM\CurrentControlSet\Control\Session Manager\Environment';
  BackupKey      = 'SOFTWARE\{#AppShortName}';
  BackupValue    = 'OriginalPath';

var
  DownloadPage: TDownloadWizardPage;
  FfmpegSourcePage: TInputOptionWizardPage;
  FfmpegSource: string;

{ 下载页用 Inno 6.2+ 自带的 TDownloadWizardPage：它有原生进度条、速度和
  停止按钮，比"后台脚本静默下载 + 一个假进度提示框"可靠得多。
  源选择单独一页（官方 / ghfast.top 镜像），只在真的缺 ffmpeg 时出现。 }
procedure InitializeWizard;
begin
  DownloadPage := CreateDownloadPage(ExpandConstant('{cm:FfmpegPageTitle}'),
                                     ExpandConstant('{cm:FfmpegPageDesc}'), nil);
  DownloadPage.ShowBaseNameInsteadOfUrl := True;

  { 源选择页必须排在 wpReady 之前：真正的下载由 NextButtonClick(wpReady) 触发，
    页面若挂在 wpReady 之后，用户选完源点"安装"时这一步已经过去了。 }
  FfmpegSourcePage := CreateInputOptionPage(wpSelectDir,
    ExpandConstant('{cm:FfmpegSourceTitle}'),
    ExpandConstant('{cm:FfmpegSourceDesc}'),
    ExpandConstant('{cm:FfmpegSourceSub}'), True, False);
  FfmpegSourcePage.Add(ExpandConstant('{cm:FfmpegSourceOfficial}'));
  FfmpegSourcePage.Add(ExpandConstant('{cm:FfmpegSourceMirror}'));
  FfmpegSourcePage.Values[1] := True;   { 默认镜像源：GitHub 直连在国内经常卡在 0 字节 }
end;

{ 把安装目录加进系统 PATH。加之前先把原始值备份进注册表：
  用户的 PATH 可能以 ';' 结尾、也可能含空项（;;），这些退化写法下
  光靠字符串手术无法保证卸载时逐字节还原，所以直接存原值，卸载时精确恢复。 }
procedure EnvAddPath(Path: string);
var
  Paths, UpPaths, UpPath: string;
begin
  if not RegQueryStringValue(HKEY_LOCAL_MACHINE, EnvironmentKey, 'Path', Paths) then
    Paths := '';
  UpPaths := Uppercase(Paths);
  UpPath := Uppercase(Path);
  if (UpPaths = UpPath) or (Pos(';' + UpPath + ';', ';' + UpPaths + ';') > 0) then
    exit;                                    { 已经在 PATH 里，别重复加 }
  if not RegValueExists(HKEY_LOCAL_MACHINE, BackupKey, BackupValue) then
    RegWriteStringValue(HKEY_LOCAL_MACHINE, BackupKey, BackupValue, Paths);
  { 只在确实缺分隔符时才补 ';'，避免自己制造出 ';;' }
  if (Paths <> '') and (Paths[Length(Paths)] <> ';') then
    Paths := Paths + ';';
  Paths := Paths + Path;
  if not RegWriteStringValue(HKEY_LOCAL_MACHINE, EnvironmentKey, 'Path', Paths) then
    MsgBox('无法写入系统 PATH，请手动把以下目录加入 PATH：' + #13#10 + Path, mbError, MB_OK);
end;

procedure EnvRemovePath(Path: string);
var
  Paths, Original, UpPaths, UpPath: string;
  P: Integer;
  Changed: Boolean;
begin
  if not RegQueryStringValue(HKEY_LOCAL_MACHINE, EnvironmentKey, 'Path', Paths) then
    exit;
  UpPaths := Uppercase(Paths);
  UpPath := Uppercase(Path);
  Changed := False;

  { 1) 安装时备份过原值，而且此后没人改过 PATH —— 逐字节还原 }
  if RegQueryStringValue(HKEY_LOCAL_MACHINE, BackupKey, BackupValue, Original) then
    if (Paths = Original + ';' + Path) or (Paths = Original + Path) then
    begin
      Paths := Original;
      Changed := True;
    end;

  { 2) 别人动过 PATH：退化成只摘掉自己那一项 }
  if not Changed then
  begin
    if UpPaths = UpPath then
    begin
      Paths := '';
      Changed := True;
    end
    else if Pos(';' + UpPath + ';', UpPaths) > 0 then        { 夹在中间 }
    begin
      P := Pos(';' + UpPath + ';', UpPaths);
      Delete(Paths, P, Length(Path) + 1);                    { 删 ";Path"，保留后面的 ';' }
      Changed := True;
    end
    else if Pos(UpPath + ';', UpPaths) = 1 then              { 在最开头 }
    begin
      Delete(Paths, 1, Length(Path) + 1);                    { 删 "Path;" }
      Changed := True;
    end
    else if Pos(';' + UpPath, UpPaths) = Length(Paths) - Length(Path) then  { 在最末尾 }
    begin
      Delete(Paths, Length(Paths) - Length(Path), Length(Path) + 1);
      Changed := True;
    end;
  end;

  if Changed then
  begin
    RegWriteStringValue(HKEY_LOCAL_MACHINE, EnvironmentKey, 'Path', Paths);
    RegDeleteValue(HKEY_LOCAL_MACHINE, BackupKey, BackupValue);
  end;
end;

function FfmpegOnPath(): Boolean;
var
  Paths, UserPaths: string;
begin
  Result := False;
  if not RegQueryStringValue(HKEY_LOCAL_MACHINE, EnvironmentKey, 'Path', Paths) then
    Paths := '';
  if RegQueryStringValue(HKEY_CURRENT_USER, 'Environment', 'Path', UserPaths) then
    Paths := Paths + ';' + UserPaths;
  { 当前进程的 PATH 是启动那一刻的快照，装完 ffmpeg 后要新开进程才更新；
    再直接拼上约定的安装目录，避免"刚装完却检测不到" }
  Paths := Paths + ';' + GetEnv('PATH') + ';' + ExpandConstant('{%USERPROFILE}\ffmpeg\bin');
  Result := FileSearch('ffmpeg.exe', Paths) <> '';
end;

{ ffmpeg 已经在 PATH 里、或者静默安装时，源选择页没必要出现 }
function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := (PageID = FfmpegSourcePage.ID) and (FfmpegOnPath() or WizardSilent);
end;

function FormatSize(Bytes: Int64): string;
var
  Tenths: Int64;
begin
  { 四舍五入到 0.1 MB：Inno 的 Format 对浮点支持不稳，自己算更保险 }
  Tenths := (Bytes * 10 + 524288) div 1048576;
  Result := IntToStr(Tenths div 10) + '.' + IntToStr(Tenths mod 10) + ' MB';
end;

function RunSetupScript(const Params: string): Integer;
var
  Code: Integer;
begin
  Result := -1;
  if not Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
              '-NoProfile -ExecutionPolicy Bypass -File "' + ExpandConstant('{tmp}\ffmpeg_setup.ps1') + '" ' + Params,
              '', SW_HIDE, ewWaitUntilTerminated, Code) then
    exit;
  Result := Code;
end;

function ReadFirstLine(const FileName: string): string;
var
  Lines: TArrayOfString;
begin
  Result := '';
  if FileExists(FileName) and LoadStringsFromFile(FileName, Lines) and (Length(Lines) > 0) then
    Result := Trim(Lines[0]);
end;

{ 向下载站点查真实体积：提示里的"大小"必须是当前版本的实际大小，不能写死。
  地址由 ffmpeg_setup.ps1 自己解析（先用 GitHub API 找同名资产，国内快得多；
  解析不到才退回 gyan.dev），所以这里不传 -Url。 }
function OtherSource(const Source: string): string;
begin
  if Source = 'mirror' then
    Result := 'official'
  else
    Result := 'mirror';
end;

function SourceLabel(const Source: string): string;
begin
  if Source = 'mirror' then
    Result := ExpandConstant('{cm:FfmpegSourceMirror}')
  else
    Result := ExpandConstant('{cm:FfmpegSourceOfficial}');
end;
function QueryFfmpegSize(const Source: string): Int64;
var
  SizeFile: string;
begin
  Result := 0;
  SizeFile := ExpandConstant('{tmp}\ffmpeg_size.txt');
  DeleteFile(SizeFile);
  if RunSetupScript('-Mode Size -Source ' + Source + ' -OutFile "' + SizeFile + '"') <> 0 then
    exit;
  Result := StrToInt64Def(ReadFirstLine(SizeFile), 0);
  DeleteFile(SizeFile);
end;

{ 解析当前版本的下载地址（版本号在文件名里，不能写死） }
function ResolveFfmpegUrl(const Source: string): string;
var
  UrlFile: string;
begin
  Result := '';
  UrlFile := ExpandConstant('{tmp}\ffmpeg_url.txt');
  DeleteFile(UrlFile);
  if RunSetupScript('-Mode Url -Source ' + Source + ' -OutFile "' + UrlFile + '"') <> 0 then
    exit;
  Result := ReadFirstLine(UrlFile);
  DeleteFile(UrlFile);
end;

{ 只解压已经下载好的 zip，不再联网 —— 联网那一步交给下载页，用户能看到进度 }
function ExtractFfmpeg(const ZipFile: string): Boolean;
var
  Code: Integer;
  StatusFile, Dest: string;
begin
  Result := False;
  Dest := ExpandConstant('{%USERPROFILE}\ffmpeg');
  StatusFile := ExpandConstant('{tmp}\ffmpeg_install.txt');
  DeleteFile(StatusFile);
  Code := RunSetupScript('-Mode Extract -Zip "' + ZipFile + '" -Dest "' + Dest + '" -OutFile "' + StatusFile + '"');
  if Code = 0 then
    Result := FileExists(Dest + '\bin\ffmpeg.exe');
  DeleteFile(StatusFile);
end;

{ 在"准备安装"页之前处理 ffmpeg：
  · 检测到就直接走；
  · 没检测到先弹窗告知缺失后果、真实大小，问是否安装；
  · 同意后展示下载页（进度条 + 速度 + 停止），下完解压到 ~\ffmpeg，再写 PATH。 }
procedure TryInstallFfmpeg();
var
  Size: Int64;
  SizeText, Url, Zip, BinPath, Err, Other: string;
  Downloaded: Boolean;
begin
  if FfmpegOnPath() then
    exit;

  { 静默安装（/SILENT）不能弹窗，否则自动化部署会永远停在一个没人点的对话框上 }
  if WizardSilent then
  begin
    Log('ffmpeg not found; interactive install skipped in silent mode.');
    exit;
  end;

  { [Files] 里的 dontcopy 文件不会自动落到临时目录，用之前先手动解出来 }
  ExtractTemporaryFile('ffmpeg_setup.ps1');

  if FfmpegSourcePage.Values[1] then
    FfmpegSource := 'mirror'
  else
    FfmpegSource := 'official';

  Size := QueryFfmpegSize(FfmpegSource);
  if Size > 0 then
    SizeText := FormatSize(Size)
  else
    SizeText := '约 114 MB';

  if MsgBox(FmtMessage(ExpandConstant('{cm:FfmpegMissingAsk}'), [ExpandConstant('{%USERPROFILE}\ffmpeg'), SizeText, SourceLabel(FfmpegSource)]),
            mbConfirmation, MB_YESNO) = IDNO then
  begin
    MsgBox(ExpandConstant('{cm:FfmpegSkip}'), mbInformation, MB_OK);
    exit;
  end;

  Zip := ExpandConstant('{tmp}\ffmpeg-essentials.zip');
  while True do
  begin
    Url := ResolveFfmpegUrl(FfmpegSource);
    if Url = '' then
    begin
      MsgBox(ExpandConstant('{cm:FfmpegFailed}'), mbError, MB_OK);
      exit;
    end;

    DeleteFile(Zip);
    DownloadPage.Clear;
    { 第三个参数是期望的 SHA256（空串则不校验内容），不是大小 }
    DownloadPage.Add(Url, 'ffmpeg-essentials.zip', '');
    DownloadPage.Show;
    Downloaded := False;
    try
      try
        DownloadPage.Download;
        Downloaded := True;
      except
        Err := GetExceptionMessage;
        Other := OtherSource(FfmpegSource);
        if DownloadPage.AbortedByUser then
        begin
          { 用户按了"停止"：这就是下载途中的换源入口 }
          if MsgBox(FmtMessage(ExpandConstant('{cm:FfmpegSwitchAsk}'), [SourceLabel(Other)]),
                    mbConfirmation, MB_YESNO) = IDYES then
            FfmpegSource := Other
          else
            exit;
        end
        else
        begin
          if MsgBox(FmtMessage(ExpandConstant('{cm:FfmpegRetryAsk}'), [SourceLabel(FfmpegSource), Err, SourceLabel(Other)]),
                    mbConfirmation, MB_YESNO) = IDYES then
            FfmpegSource := Other
          else
          begin
            MsgBox(FmtMessage(ExpandConstant('{cm:FfmpegFailDetail}'), [Err]), mbError, MB_OK);
            exit;
          end;
        end;
      end;
    finally
      DownloadPage.Hide;
    end;

    if Downloaded then
      Break;
  end;

  if not ExtractFfmpeg(Zip) then
  begin
    MsgBox(ExpandConstant('{cm:FfmpegFailed}'), mbError, MB_OK);
    exit;
  end;

  BinPath := ExpandConstant('{%USERPROFILE}\ffmpeg\bin');
  EnvAddPath(BinPath);
  { 只记下我们自己加的这一条：用户可能本来就有别的 ffmpeg，卸载不能乱删 }
  RegWriteStringValue(HKEY_CURRENT_USER, 'SOFTWARE\{#AppShortName}', 'FfmpegBin', BinPath);
  MsgBox(FmtMessage(ExpandConstant('{cm:FfmpegDone}'), [BinPath]), mbInformation, MB_OK);
end;
{ 点"安装"（Ready 页的下一步）时先把 ffmpeg 处理掉，再进入正式复制文件。
  外层 try 兜底：任何意外都变成一条出错提示，而不是 Inno 的 "Runtime error"。 }
function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if CurPageID <> wpReady then
    exit;
  try
    TryInstallFfmpeg();
  except
    MsgBox(FmtMessage(ExpandConstant('{cm:FfmpegFailDetail}'), [GetExceptionMessage]),
           mbError, MB_OK);
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep <> ssPostInstall then
    exit;

  if WizardIsTaskSelected('modifypath') then
    EnvAddPath(ExpandConstant('{app}'));
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  BinPath: string;
begin
  if CurUninstallStep <> usPostUninstall then
    exit;

  EnvRemovePath(ExpandConstant('{app}'));
  { ffmpeg 的目录和文件保留：用户装过一次可能还要用，只把 PATH 条目摘掉 }
  if RegQueryStringValue(HKEY_CURRENT_USER, 'SOFTWARE\{#AppShortName}', 'FfmpegBin', BinPath) then
  begin
    EnvRemovePath(BinPath);
    RegDeleteValue(HKEY_CURRENT_USER, 'SOFTWARE\{#AppShortName}', 'FfmpegBin');
  end;
end;


