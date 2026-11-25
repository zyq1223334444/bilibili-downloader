> [🇬🇧 English](readme.md)

# bilibili-downloader

**一个不用记参数也能用的 B 站下载器。** 不带参数启动就是图形界面；带上参数就是完整的命令行工具。

把 B 站的音、视频流分别拉下来，用 ffmpeg 合并成 MP4 和 MP3；顺手抓弹幕，存成 B 站原生 XML 和 ASS，
需要的话封印成 MKV 的字幕轨（可开关）或者干脆烧进画面。单视频、分P、合集、直播录制、字幕合并都在里面。

- **默认最高画质**（8K / 4K / HDR / 杜比视界，上限取决于账号权限），音频优先无损 FLAC
- **多线程 + 断点续传 + CDN 优选**，四条流并行下载，每条都有独立进度条
- **GUI 与 CLI 功能对等**：窗口里能点的，命令行一样有参数
- **产物永远另存**：不覆盖原视频，原子写入，失败不会留下半个文件

---

## 目录

- [安装](#安装)
- [快速开始](#快速开始)
- [图形界面](#图形界面)
- [命令行参数](#命令行参数)
- [弹幕](#弹幕)
- [保存结构](#保存结构)
- [SESSDATA 凭证](#sessdata-凭证)
- [断点续传与中断](#断点续传与中断)
- [从源码构建](#从源码构建)
- [常见问题](#常见问题)
- [仓库结构](#仓库结构)

## 安装

### 一、安装包（Windows，推荐）

到 [Releases](https://github.com/zyq1223334444/bilibili-downloader/releases) 下载
`bilibili_downloader_setup_<版本>.exe`：

- 装到 `C:\Program Files\bilibili-downloader`，带开始菜单快捷方式、桌面图标与卸载程序
- 可选把安装目录加入 `PATH`（默认勾选）；改之前先把原值备份进注册表，卸载时按原值还原
- **安装过程会帮你装 ffmpeg**：只认环境变量 `PATH`（系统 + 用户 + 进程），找不到才问一次要不要下载，
  显示的是当场查出来的真实大小（约 114 MB）。下载窗口里有总进度、总速度、剩余时间，可随时停止、
  断了会自己续传。装完只留 `bin`，并把 `%USERPROFILE%\ffmpeg\bin` 追加到**用户 `PATH`**（`HKCU\Environment`）
- 卸载**只删程序自己的 `PATH` 条目**，对 ffmpeg 一概不动——文件在、用户 `PATH` 里的那条也在，重装可直接复用
- 静默安装（`/VERYSILENT`、`/SILENT`）不弹窗、不下载，只在日志里留一行

### 二、免安装（Windows）

| 文件 | 形态 | Ctrl+C 退出码 |
|---|---|---|
| `bilibili_downloader.exe` | 单文件，约 14 MB，运行时自解压 | `0xC000013A` |
| `bilibili_downloader_standalone_win64.zip` | 解压出一个文件夹，启动更快 | `130`（与源码版一致） |

```powershell
.\bilibili_downloader.exe BV1xx411c7mD -q 720p --no-mp3
```

> 单文件版外面还套了一层自解压引导进程，Ctrl+C 时它会先退出，于是退出码是 `0xC000013A`
> 而不是 `130`。程序本身照常收尾（打印 `[中断]`、保留断点、清理临时目录）。脚本里要判断 130 就用文件夹版。

### 三、Linux / macOS

| 平台 | 单文件 | 文件夹版（推荐） |
|---|---|---|
| Linux x86_64 | `bilibili_downloader_linux_x86_64` | `bilibili_downloader_linux_x86_64.tar.gz` |
| macOS Intel | `bilibili_downloader_macos_x86_64` | `bilibili_downloader_macos_x86_64.tar.gz` |
| macOS Apple Silicon | `bilibili_downloader_macos_arm64` | `bilibili_downloader_macos_arm64.tar.gz` |

```bash
tar -xzf bilibili_downloader_linux_x86_64.tar.gz
./bilibili_downloader_standalone/bilibili_downloader BV1xx411c7mD --single -q 720p
```

macOS 上是未签名的二进制，首次运行被拦就 `xattr -d com.apple.quarantine <文件>` 或右键 → 打开。
CI 产出的 Linux / macOS 包是纯命令行版（构建机没装 tcl/tk），要有界面就自己在装了 `python3-tk` 的机器上编。

### 四、从源码跑

```powershell
git clone https://github.com/zyq1223334444/bilibili-downloader.git
cd bilibili-downloader
pip install -r requirements.txt     # requests、tqdm
python bilibili_downloader.py       # 不带参数 → 图形界面
```

要求 Python 3.9+，图形界面需要 tkinter（Windows 官方 Python 自带）。
**唯一的额外外部程序是 ffmpeg**：合并、导 MP3、嵌弹幕都靠它。

## 快速开始

```powershell
# 打开图形界面（画质 / 输出 / 弹幕 / 凭证都在窗口里选）
python bilibili_downloader.py

# 单个视频 → 桌面\<视频标题>\<视频标题>.mp4 与 .mp3
python bilibili_downloader.py BV1xx411c7mD

# 存弹幕并封成 MKV 字幕轨（不重编码，几秒）
python bilibili_downloader.py BV1xx411c7mD --danmaku light --danmaku-video soft

# 多抓弹幕、直接烧进画面（要重编码，慢但哪都能看）
python bilibili_downloader.py BV1xx411c7mD --danmaku full --danmaku-video hard

# 多P 只下第 2 个分P；只看计划不下载
python bilibili_downloader.py "https://www.bilibili.com/video/BV1xx411c7mD?p=2" --single
python bilibili_downloader.py BV1xx411c7mD --dry-run

# 只要音频（192k），换保存目录
python bilibili_downloader.py BV1xx411c7mD --audio-only --mp3-bitrate 192 -o D:\videos

# 把弹幕 / 字幕合并进已有视频（产物另存，不覆盖原文件）
python bilibili_downloader.py --merge-sub 视频.mp4 弹幕.xml --sub-mode soft --merge-out D:\output

# 直播录制窗口（主界面上也有同名按钮）
python bilibili_downloader.py --live
```

**首次运行**若没读到凭证，会打印获取方法并问一次 `SESSDATA`（不回显），校验通过后存进用户环境变量，
**新开一个终端**再跑就能自动读取。

## 图形界面

Win11 浅色风格两栏窗口：左边输入与选项，右边分集预览与日志；卡片随窗口伸缩。

| 区域 | 内容 |
|---|---|
| 链接 | 多个视频链接 / BV / av / b23.tv 短链；「读取分集」「粘贴」「清空」 |
| 保存到 | 默认桌面（认得 OneDrive 重定向），可浏览、可一键打开目录 |
| 输出 | 画质上限、MP3 码率、内容三选一（视频+MP3 / 仅视频 / 仅 MP3） |
| 弹幕 | 不下载 / 精简 / 多；以及 不进视频 / 软字幕(MKV) / 烧进画面 |
| 分集预览 | 表格列出编号、标题、时长，点行切换 ☑；序号框可直接写 `1,3-5,49-234`，与勾选双向同步 |
| 高级 | 并发数、节点重试、超时、重连上限、五个开关 |
| 凭证 | 终端样式状态区：未读取 / 校验中 / 有效 / 已失效，四种界面各不一样 |
| 底部 | 合并弹幕 / 录制直播 / 开始下载 / 取消 / 打开目录 / 帮助，外加 ffmpeg 状态 |
| 直播窗口 | 房间链接或号、画质、分段分钟、保存目录、弹幕档位、预览与试看 10 秒、预约开播自动录 |
| 合并弹窗 | 视频 + 字幕/弹幕 + 输出文件夹，软字幕或硬字幕，产物另存 |

关闭主界面或直播窗口会收进托盘继续录，托盘右键可「显示主界面 / 录制直播 / 退出」。
`SESSDATA` 只影响**画质上限**，和下载速度无关。窗口「帮助」讲的是界面用法，`-h` 才是命令行参数。

## 命令行参数

| 参数 | 默认 | 说明 |
|---|---|---|
| `inputs` | 交互输入 | 视频链接 / `BV` 号 / `av` 号 / `b23.tv` 短链，可多个 |
| `-o, --output` | 桌面 | 保存根目录 |
| `-q, --quality` | `max` | `max 8k 4k 1080p60 1080p+ 1080p 720p60 720p 480p 360p` |
| `--mp3-bitrate` | `320` | `128 / 192 / 256 / 320` |
| `--audio-only` | 关 | 只导 MP3，不下载视频流 |
| `--no-mp3` | 关 | 只保存 MP4 |
| `--danmaku` | `light` | `none` / `light` / `full` |
| `--danmaku-video` | `none` | `none` / `soft`（MKV 字幕轨）/ `hard`（烧进画面） |
| `--single` | 关 | 只下链接指向的那一个，忽略合集 |
| `-j, --jobs` | `4` | 并发线程数（上限 4），每线程一条进度条 |
| `--max-reconnects` | `5` | 单条流的重连上限（`0` 关闭该检测） |
| `--force` | 关 | 已存在也重下 |
| `--no-probe` | 关 | 关闭节点优选探测 |
| `--retries` | `2` | 每节点重试次数 |
| `--timeout` | `15` | 网络超时（秒） |
| `--reset-sessdata` | 关 | 忽略已存凭证重新输入 |
| `--dry-run` | 关 | 只列计划，不下载 |
| `--install-ffmpeg` | 关 | Windows 下下载 ffmpeg 到 `~\ffmpeg` 并写用户 `PATH` |
| `--ffmpeg-source` | `auto` | `auto` / `official` / `mirror`（`ghfast.top` 镜像，国内更快） |
| `--merge-sub` | — | 把字幕/弹幕合并进视频，配合 `--sub-mode soft\|hard`、`--merge-out` |
| `--gui` | 关 | 打开图形界面（不带参数时默认如此） |
| `-y, --yes` | 关 | 全程不询问 |

`--danmaku-video` 需要弹幕，和 `--danmaku none` 同用会报参数错误；`--audio-only` 也不能嵌弹幕——
都是提前拒绝，不会下完才发现做不了。

合集 / 多P 会先列清单再问要下哪些：回车或 `y` 全下，`n` 退出，也可以写 `1,3,5,6-20`
（认区间、认全角逗号、写反了自动纠正）。输出被重定向或加了 `-y` 时不问，直接全下，CI 可用。

## 弹幕

**抓多少**

| 档位 | 留下什么 | 适合 |
|---|---|---|
| `light`（默认） | 去掉高级/代码弹幕，同句 5 秒内只留一条，超 60 字截断，每秒最多 6 条，车道满了就丢 | 正常观看、烧进视频也不糊脸 |
| `full` | 滚动/顶部/底部全留，车道不够宁可轻微重叠 | 留档、二次剪辑 |
| `none` | 不抓 | 只要视频 |

> 抓的是网页端当前可见的那一批（热门视频常见比稿件统计少 10%~20%），B 站接口本身就不给全。

**放进视频**

| 模式 | 做什么 | 代价 |
|---|---|---|
| `none` | 只留 `.danmaku.xml` + `.danmaku.ass` | 无 |
| `soft` | ASS 封装成 MKV 字幕轨（默认轨、语言 `chi`） | 秒级，不损失画质，播放器可关 |
| `hard` | libx264 重编码，弹幕画进画面（仍是 `.mp4`） | 慢，有一次画质损失，换来手机/微信谁都能看 |

字号、行高、车道数都按视频实际分辨率换算；滚动/顶部/底部共用一套车道，避免压字。

## 保存结构

默认根目录是**桌面**（Windows 读注册表，认 OneDrive 重定向），`-o` 可改。

```
桌面\
├── <视频标题>\                       # 单视频
│   ├── <视频标题>.mp4
│   ├── <视频标题>.mp3
│   └── <视频标题>.danmaku.xml / .danmaku.ass
├── <视频标题>\                       # 多P（P 序号保证顺序）
│   ├── P01 <分P标题>\ …
│   └── P02 <分P标题>\ …
└── <合集标题>\                       # 合集
    └── <视频标题>\ …
```

`--danmaku-video soft` 时成品是 **`.mkv`**（`.mp4` 被替换），`hard` 时仍是 `.mp4`。

## SESSDATA 凭证

读取顺序：① 进程环境变量 `BILI_SESSDATA` → ② `HKCU\Environment` 里的用户变量（直查注册表，老终端也读得到）
→ ③ 程序旁边的 `sessdata.txt` → ④ `~/.config/bilibili-downloader/sessdata`。都没有就询问一次。

启动时会用 `nav` 接口校验：有效会说明你的画质权限；失效会直说"只能游客下载，一般最高 480P"并提示换号，
不再静默降级。手动设置：

```powershell
setx BILI_SESSDATA "你的SESSDATA值"
```

获取：浏览器登录 B 站 → F12 → Application → Cookies → `https://www.bilibili.com` → 复制 `SESSDATA`。

> ⚠️ `SESSDATA` 等同于登录凭证：别写进源码、别提交仓库、别发给别人。怀疑泄露就立刻去「安全隐私 → 退出所有设备」。

## 断点续传与中断

- **随时 Ctrl+C 都安全**：主线程 0.3 秒轮询信号，收到就通知线程收手并立即退出（退出码 130），
  已下的 `.part` / `.m4s` 全部保留，重跑即续传
- 视频、音频先落 `<名字>.video.m4s.part` / `.audio.m4s.part`，重跑用 `Range` 从已有字节继续
- 成功后改名 `.m4s` → 合并 → 导出 → 删临时流文件；失败则保留，所以重跑是"续传"不是"从头"
- 字节数与 `Content-Length` 不符判失败并重试；本地与远端不一致返回 `416` 时自动清断点重下

输出里的状态标记：`[跳过]` 已有、`[重试]` 该节点这次失败（后面会写下一步换不换节点）、
`[重连]` 速度掉到自历史均值 30% 以下持续 10 秒、`[成功]` 中途失败过但成了、`[失败]` 彻底失败、
`[完成]` 成品与大小、`[弹幕]` 抓到多少留多少、`[结果]` 整批统计、`[中断]` 你按了 Ctrl+C。

> 看到 `[重试]` **不等于失败**，看这行结尾和紧随其后的 `[成功]` / `[失败]`。

## 从源码构建

| 产物 | 命令 |
|---|---|
| Windows 单文件 exe | `build\build_exe.bat` → `build\out\bilibili_downloader.exe` |
| Windows 文件夹版 + zip | `build\build_exe_standalone.bat` |
| Windows 安装包（Inno Setup 6.5+） | `build\build_installer.bat` |
| Linux / macOS | `bash build/build_unix.sh`（必须在对应平台） |

需要 `pip install -r requirements.txt nuitka zstandard`，Windows 还要 **MSVC 14.3+**
（Python 3.13 以上的 Nuitka 不能用 MinGW）。几个关键参数：

- `--include-package-data=certifi` —— 少了它 exe 能启动，但每次 HTTPS 都报找不到 CA 证书
- `--windows-console-mode=force` —— 否则变成没有 stdout 的 GUI 子系统程序
- `--enable-plugin=tk-inter` —— 把 Tcl/Tk 运行时打包进去，不然 GUI 起不来
- `--windows-icon-from-ico=assets/app.ico` —— 程序图标；图标由 `build\make_icon.ps1` 从
  `assets/icon-source.png` 生成多尺寸 ICO

**ffmpeg 从不打包**。安装器里的下载逻辑在 `build/ffmpeg_setup.ps1`：
`-Mode Size` 用 `GET + Range: 0-0` 读真实大小，`-Mode Url` 按源返回地址，`-Mode Download` 开 8 线程下载，
`-Mode Install` 解压 + 自检。下载窗口是 WinForms 自绘：Per-Monitor V2 DPI + GDI 文本渲染，125% / 150% 缩放下
字也是清楚的，不会糊成一团。

> Linux / macOS 不能在 Windows 上编：Nuitka 要调用目标平台自己的编译器，没有交叉编译。
> 仓库用 GitHub Actions 在真机上构建，见 `.github/workflows/build.yml`。

## 常见问题

| 现象 | 说明 |
|---|---|
| `未找到 ffmpeg` | 装好并进 `PATH`；Windows 可 `--install-ffmpeg`，或直接装安装包 |
| 问"要装 ffmpeg 吗" | 不装也能下流，但**不能合并 MP4、不能导 MP3、不能嵌弹幕** |
| 只能下 360P/480P | 没有有效 `SESSDATA`，或账号本身没这画质 |
| GUI 打不开 | 源码版要 tkinter；自己编译时加 `--enable-plugin=tk-inter` |
| 分集预览是空的 | 先点「读取分集」；换了链接或改了「只下当前」要重读 |
| 序号框写了没反应 | 要回车或点「应用序号」；`0`、越界、`abc` 会给原因并保留原选择 |
| 弹幕比网页少 | 接口只给当前可见的一批，见上文 |
| 烧弹幕后变慢变大 | `hard` 是重编码，必然如此；留档用 `soft` |
| `该视频没有 DASH 流` | 番剧/影视，或极老的稿件，本工具只支持普通投稿 |
| `这是番剧/影视内容` | 接口返回了 `redirect_url`，ep 不在支持范围 |
| `code=62002 / 62004` | 稿件不可见 / 审核中 |
| 进度长时间不动 | 正在换节点重试，看那行"节点 x/y 第 n 次失败" |

## 仓库结构

```
bilibili_downloader.py      整个程序（单文件）
requirements.txt            运行时依赖
readme.md / readme.zh.md    英文 / 中文文档
CHANGELOG.md                版本变更
assets/                     图标源图与 app.ico
build/
├── build_exe.bat           单文件 exe
├── build_exe_standalone.bat 文件夹版 + zip
├── build_installer.bat     安装包
├── build_unix.sh           Linux / macOS
├── installer.iss           Inno Setup 脚本
├── ffmpeg_setup.ps1        安装包里的 ffmpeg 探测 / 下载 / 安装
├── make_icon.ps1           PNG → 多尺寸 ICO
└── out/                    被忽略：全部产物与中间目录
```

## 更新日志

见 [CHANGELOG.md](CHANGELOG.md)。**2.1.4** 给程序和安装包做了图标，安装包的 ffmpeg 下载窗口加了
Per-Monitor V2 DPI 与 GDI 文字渲染（125%/150% 缩放下不再糊），进度条最小宽度也调到看得见；
2.1.3 重做下载窗口视觉（圆角渐变条、剩余时间、扁平停止按钮）；
2.1.2 修正 ffmpeg 口径（只认 `PATH`、只写用户 `PATH`、卸载不动 ffmpeg），并修掉下载窗被隐藏的问题；
2.1.1 下载改 8 线程可停止可续传，字幕合并只留软/硬、输出选文件夹，直播默认落桌面；
2.1.0 新增直播录制与字幕合并、托盘常驻。

## 合规声明

仅供个人学习与备份自己有权访问的内容。请遵守 B 站用户协议，不要二次传播受版权保护的内容，也不要批量抓取。
