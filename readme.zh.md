> [🇬🇧 English](readme.md)

# bilibili-downloader

**一个不用记参数也能用的 B 站下载器，Windows / macOS / Linux 三套系统同一份代码。**

双击就是图形界面，带参数就是完整的命令行工具。DASH 音视频分流下载 → ffmpeg 合并成 MP4 / MP3，
顺手抓弹幕存成 XML 与 ASS，需要时封成 MKV 字幕轨（可开关）或直接烧进画面。
单视频、分P、合集、直播录制、字幕合并，全都在里面。

- **默认最高画质**（8K / 4K / HDR / 杜比视界，上限取决于账号权限），音频优先无损
- **多线程 + 断点续传 + CDN 优选**，四条流并行，每条一条独立进度条
- **界面与命令行功能对等**：窗口里能选的，命令行都有对应参数，走的是同一条代码路径
- **三平台界面**：Windows 圆角浅色窗口 + 系统托盘，macOS / Linux 同一套界面（字体、图标、DPI 各自适配）
- **界面单实例**：重复双击只会把已有窗口拉到前台，不会开出第二个；带参数的命令行不受限制
- **产物永远另存**：不覆盖原视频，原子写入，失败不留半个文件

---

## 目录

- [安装](#安装)
- [快速开始](#快速开始)
- [图形界面](#图形界面)
- [命令行](#命令行)
- [SESSDATA 凭证](#sessdata-凭证)
- [保存结构](#保存结构)
- [从源码构建](#从源码构建)
- [常见问题](#常见问题)

## 安装

### Windows

推荐安装包（[Releases](https://github.com/zyq1223334444/bilibili-downloader/releases) 里的
`bilibili_downloader_setup_<版本>.exe`）：

- 装到 `C:\Program Files\bilibili-downloader`，带开始菜单、桌面图标与卸载程序
- 可选把安装目录加入 `PATH`；卸载只删自己那一条
- 安装过程检测 ffmpeg（只看 `PATH`），没有就问一次要不要下载；下载窗口有总进度、速度、剩余时间，
  可随时停止、断了自己续传，装完只留 `bin` 并把 `%USERPROFILE%\ffmpeg\bin` 写进用户 `PATH`
- 静默安装（`/VERYSILENT`、`/SILENT`）不弹窗、不下载

免安装：

| 文件 | 形态 |
|---|---|
| `bilibili_downloader.exe` | 单文件，运行时自解压（Ctrl+C 退出码是 `0xC000013A`） |
| `bilibili_downloader_standalone_win64.zip` | 解压出文件夹，启动更快，退出码 `130` 与源码版一致 |

### macOS / Linux

到 Releases 下载对应包：

| 平台 | 单文件 | 文件夹版（推荐） |
|---|---|---|
| Linux x86_64 | `bilibili_downloader_linux_x86_64` | `..._linux_x86_64.tar.gz` |
| macOS Intel | `bilibili_downloader_macos_x86_64` | `..._macos_x86_64.tar.gz` |
| macOS Apple Silicon | `bilibili_downloader_macos_arm64` | `..._macos_arm64.tar.gz` |

```bash
tar -xzf bilibili_downloader_linux_x86_64.tar.gz
./bilibili_downloader_standalone/bilibili_downloader      # 图形界面
```

macOS 上是未签名二进制：首次被拦时右键 → 打开，或 `xattr -d com.apple.quarantine <文件>`。
Linux 需要图形环境（`DISPLAY` 或 `WAYLAND_DISPLAY`）和 `python3-tk` 运行库；纯 SSH 下会自动提示改用命令行。

### 从源码跑（三平台通用）

```bash
git clone https://github.com/zyq1223334444/bilibili-downloader.git
cd bilibili-downloader
python -m pip install -r requirements.txt     # requests、tqdm
python bilibili_downloader.py                 # 不带参数 → 图形界面
```

Python 3.9+；图形界面需要 tkinter（Windows 官方 Python 自带，Linux 装 `python3-tk`，macOS 自带）。
**唯一的外部程序是 ffmpeg**：合并、导 MP3、嵌弹幕都靠它。

```bash
# Windows：界面里可一键装，或命令行
bilibili_downloader --install-ffmpeg
# macOS
brew install ffmpeg
# Linux
sudo apt install ffmpeg        # Debian / Ubuntu
sudo dnf install ffmpeg        # Fedora
```

## 快速开始

```bash
# 图形界面（画质 / 输出 / 弹幕 / 凭证都在窗口里选）
bilibili_downloader

# 单个视频 → 桌面/<视频标题>/<视频标题>.mp4 与 .mp3
bilibili_downloader BV1xx411c7mD

# 存弹幕并封成 MKV 字幕轨（不重编码，几秒）
bilibili_downloader BV1xx411c7mD --danmaku light --danmaku-video soft

# 多抓弹幕、烧进画面（要重编码，慢但哪都能看）
bilibili_downloader BV1xx411c7mD --danmaku full --danmaku-video hard

# 多P 只下第 2 个分P；只看计划
bilibili_downloader "https://www.bilibili.com/video/BV1xx411c7mD?p=2" --single
bilibili_downloader BV1xx411c7mD --dry-run

# 只要音频（192k），换保存目录
bilibili_downloader BV1xx411c7mD --audio-only --mp3-bitrate 192 -o ~/Videos

# 把字幕 / 弹幕合并进已有视频（产物另存）
bilibili_downloader --merge-sub video.mp4 danmaku.xml --sub-mode soft

# 直接打开直播录制窗口
bilibili_downloader --live
```

首次运行若没读到凭证，会打印获取方法并问一次 `SESSDATA`（不回显），校验通过后保存：
Windows 写用户环境变量，macOS / Linux 写 `~/.config/bilibili-downloader/sessdata`（0600）。

## 图形界面

浅色圆角两栏窗口：左边输入与选项，右边分集预览与日志，卡片随窗口伸缩。

| 区域 | 内容 |
|---|---|
| 链接 | 多个链接 / BV / av / b23.tv 短链；「读取分集」「粘贴」「清空」 |
| 保存到 | 默认桌面（Windows 认得 OneDrive 重定向），可浏览、可一键打开目录 |
| 输出 | 画质上限、MP3 码率、内容三选一（视频+MP3 / 仅视频 / 仅 MP3） |
| 弹幕 | 不下载 / 精简 / 多；以及 不进视频 / 软字幕(MKV) / 烧进画面 |
| 分集预览 | 列出编号、标题、时长，点行切换勾选；序号框写 `1,3-5,49-234`，与勾选双向同步 |
| 高级选项 | 并发、重试、超时、重连上限、只下当前、强制重下、关闭探测、只看计划、重输凭证 |
| 凭证 | 像终端一样显示状态；读到有效凭证后只留「更换 / 清除」 |
| 运行日志 | 实时滚动；ffmpeg 状态与安装入口也在这一行 |

三个窗口：主界面、「录制直播」、「帮助」。每个窗口都用应用自己的图标（Windows 是 `.ico`，
macOS / Linux 用 `.png`）。底部「帮助」写的是当前系统的实际操作方式，命令行 `-h` 同样按平台拼。

**最小化行为**：Windows 收进系统托盘（双击托盘图标或右键「显示主界面」唤回，托盘图标是粉色 B 标，
通知气泡也是）。右键菜单是「显示主界面 / 录制直播 / 合并弹幕 / 退出」，后两项只打开各自窗口，
不会把主界面一起弹出来。macOS / Linux 没有托盘能力，按钮退化为普通最小化，窗口不会消失。

## 命令行

完整参数：`bilibili_downloader -h`（帮助里的示例和 ffmpeg 安装方式都按当前平台生成）。

常用：

| 参数 | 说明 |
|---|---|
| `-o, --output` | 保存根目录，默认桌面 |
| `-q, --quality` | 最高画质上限：`max` / `8k` / `4k` / `1080p60` / `1080p+` / `1080p` / `720p60` / `720p` / `480p` / `360p` |
| `--mp3-bitrate` | 128 / 192 / 256 / 320 |
| `--audio-only` / `--no-mp3` | 只导 MP3 / 只存视频 |
| `--danmaku` | `none` / `light`（去重限流）/ `full` |
| `--danmaku-video` | `none` / `soft`（MKV 字幕轨）/ `hard`（烧进 MP4） |
| `-j, --jobs` | 并发 1–4；`1` 为串行并显示实时进度条 |
| `--single` / `--force` / `--dry-run` | 只下当前分P / 已存在也重下 / 只看计划 |
| `--retries` `--timeout` `--max-reconnects` `--no-probe` | 网络与节点调参 |
| `--install-ffmpeg` | 仅 Windows：装到 `~/ffmpeg` 并写用户 `PATH` |
| `--merge-sub VIDEO SUB` | 把字幕合并进视频，`--sub-mode soft/hard`、`--merge-out` 控制产物 |
| `--gui` / `--live` | 打开界面 / 只打开直播录制窗口 |

**单实例规则**：不带参数（或 `--gui`、`--live`）启动时，只允许一个界面实例。再次启动会提示并把已有窗口
拉到前台（Windows 能精确找窗口，其他系统只提示），不会有两个界面。**带参数的命令行调用完全不受限**，
批处理里并发起十个下载任务是正常用法。

## SESSDATA 凭证

可选，决定的是**画质上限**，不是速度。不填就是游客（通常最高 480P/720P，没有无损音频）。

读取顺序：`BILI_SESSDATA` 环境变量 → 程序目录 `sessdata.txt` → 用户配置
（Windows 注册表用户变量 / macOS、Linux `~/.config/bilibili-downloader/sessdata`）。

获取：浏览器登录 B 站 → F12 → Application → Cookies → `bilibili.com` → 复制 `SESSDATA`。
它等同账号登录凭证，不要写进源码、不要提交仓库、不要发给别人；怀疑泄露就去 B 站「退出所有设备」。

## 保存结构

默认保存到桌面，路径分隔符随系统：

```
<桌面>/<视频标题>/<视频标题>.mp4          # 软字幕模式是 .mkv
<桌面>/<视频标题>/<视频标题>.mp3
<桌面>/<视频标题>/<视频标题>.danmaku.xml
<桌面>/<视频标题>/<视频标题>.danmaku.ass
多P：<桌面>/<视频标题>/P01 <分P标题>/P01 <分P标题>.mp4
合集：<桌面>/<合集标题>/<视频标题>/<视频标题>.mp4
```

文件名里的非法字符按平台规则替换（Windows 禁 `\ / : * ? " < > |` 与设备名，macOS / Linux 只禁 `/`），
Windows 整条路径过长时自动缩短最深的一节并补短哈希防重名。

## 从源码构建

Windows（Nuitka + MSVC，产物在 `build/out/`）：

```bat
build\build_exe_standalone.bat   :: 文件夹版 + zip
build\build_exe.bat              :: 单文件版
build\build_installer.bat        :: 安装包（Inno Setup 6）
```

Linux / macOS（在目标系统上跑，交叉编译不了）：

```bash
sudo apt-get install -y python3-venv python3-dev python3-tk gcc g++ patchelf
python3 -m venv .venv && .venv/bin/pip install nuitka zstandard requests tqdm
bash build/build_unix.sh          # 产出单文件 + tar.gz 文件夹版
```

## 常见问题

**没找到 ffmpeg**：Windows 用 `--install-ffmpeg` 或界面里的「安装 ffmpeg」；macOS `brew install ffmpeg`；
Linux `apt/dnf install ffmpeg`。装完仍是找不到，先确认终端里 `ffmpeg -version` 能跑。

**界面打不开（Linux）**：多半是没有图形环境或没装 `python3-tk`。纯 SSH 下程序会直接提示改用命令行。

**Linux 版报 `GLIBC_2.38 not found`**：这是 24.04 之后才有的符号。release 里的 Linux 版改在
ubuntu 22.04 上构建（glibc 2.35 起），Ubuntu 22.04 / 24.04、Debian 12 都能跑；比这更老的发行版
请直接用源码运行。

**重复双击没反应**：这是单实例在起作用。Windows 会把已有窗口拉到前台；如果没有窗口（比如上次异常退出
留下残留），等几秒再试，或在任务管理器里结束残留进程。

**macOS 提示无法验证开发者**：右键应用 → 打开，或「系统设置 → 隐私与安全性」放行。

**Ctrl+C 退出码**：文件夹版是 `130`；Windows 单文件版外面套了自解压引导进程，退出码是 `0xC000013A`，
程序本身照常收尾、保留断点。

## 许可

MIT，见 [LICENSE](LICENSE)。本项目只做下载与转封装，不提供任何绕过付费 / 会员的内容。
