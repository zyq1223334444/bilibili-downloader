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
;      ..\readme.md, ..\readme.zh.md, ..\LICENSE    shipped next to the exe
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
;  ffmpeg is deliberately NOT bundled (it is a ~100 MB external program).
;  The [Code] section therefore checks PATH after installing and tells the
;  user how to install it when it is missing.
;
;  Requires Inno Setup 6.5+ (tested with 6.7.3).
;  Keep this file UTF-8: Inno Setup reads .iss as UTF-8 (with or without BOM).
; =====================================================================

#define AppName        "Bilibili Downloader"
#define AppShortName   "bilibili-downloader"
#define AppVersion     "1.0.0"
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
chinesesimplified.NoFfmpeg=没有在 PATH 中找到 ffmpeg.exe。%n%n本程序需要 ffmpeg 才能合并音视频并导出 MP3，请先安装它：%n    choco install ffmpeg%n    scoop install ffmpeg%n%n装好后重开一个终端，输入 ffmpeg -version 验证。
english.CreateDesktopIcon=Create a desktop shortcut
english.AdditionalIcons=Additional icons:
english.ModifyPath=Add the install folder to the system PATH (run bilibili_downloader from any terminal)
english.PathGroup=Environment:
english.HelpShortcut=Command-line help
english.NoFfmpeg=ffmpeg.exe was not found on your PATH.%n%nThis tool needs ffmpeg to merge the audio/video streams and export MP3. Install it first:%n    choco install ffmpeg%n    scoop install ffmpeg%n%nThen open a new terminal and check with: ffmpeg -version

[Tasks]
Name: "modifypath"; Description: "{cm:ModifyPath}"; GroupDescription: "{cm:PathGroup}"
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\readme.md"; DestDir: "{app}"; DestName: "readme.md"; Flags: ignoreversion
Source: "..\readme.zh.md"; DestDir: "{app}"; DestName: "readme.zh.md"; Flags: ignoreversion
Source: "..\LICENSE"; DestDir: "{app}"; DestName: "LICENSE"; Flags: ignoreversion

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
  Paths: string;
begin
  Result := False;
  if not RegQueryStringValue(HKEY_LOCAL_MACHINE, EnvironmentKey, 'Path', Paths) then
    Paths := '';
  Paths := Paths + ';' + GetEnv('PATH');
  Result := FileSearch('ffmpeg.exe', Paths) <> '';
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    if WizardIsTaskSelected('modifypath') then
      EnvAddPath(ExpandConstant('{app}'));
    if (not WizardSilent) and (not FfmpegOnPath()) then
      MsgBox(ExpandConstant('{cm:NoFfmpeg}'), mbInformation, MB_OK);
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
    EnvRemovePath(ExpandConstant('{app}'));
end;
