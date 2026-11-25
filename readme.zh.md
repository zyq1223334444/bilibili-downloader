> [🇬🇧 English](readme.md)

# bilibili-downloader

B 站视频 / 分P / 合集下载器：把 DASH 的音、视频分流分别下载，再用 ffmpeg 合并成 MP4、顺带导出 MP3；
还能抓**弹幕**，存成 B 站原生 XML，转一份 ASS，**软字幕封装进 MKV** 或**直接烧进画面**。
**不带任何参数启动就是图形界面**，所有选项都能在窗口里点，命令行功能一个不少。

---

## 功能特性

- **单视频 / 多P（分P）/ 合集一次下全** —— 给一个链接就够，自动展开；`--single` 只下链接指向的那一个。
- **默认取最高可用画质**（8K / 4K / HDR / 杜比视界，以账号权限为准），可用 `-q` 限制上限。
- **音频优先无损**：`dash.flac`（Hi-Res）→ 杜比全景声 → 最高码率，再导出 MP3。
- **同时产出 MP4 与 MP3**：MP4 用 `-c copy -movflags +faststart` 合并（不重新编码、秒级完成、可在线拖进度）。
- **弹幕能存也能看**：`--danmaku light`（精简，去重 + 限流，烧进视频也不糊脸）/ `full`（多，尽量不丢），
  存成 `.danmaku.xml` 与 `.danmaku.ass`；`--danmaku-video soft` 把字幕轨封进 MKV（不重编码、秒级），
  `hard` 直接烧进画面（要重编码，慢，但手机/微信里谁都能看）。
- **直播录制（纯图形界面）**：主界面「录制直播」按钮进入（或 `--live` 直接开这个窗口），默认原画，
  可按接口返回的可用画质切换、录制途中也能切；按分钟分段写盘，**内存只跟缓冲区有关，录多久都不涨**。
  带预览（每 12 秒一张间隔截图）和「试看 10 秒」小片段；填预约链接/房间号就能蹲开播，检测到开播自动录。
  录制时同时抓「精简 / 全部（含礼物、上舰、SC）」两种弹幕，**只单独存成 jsonl + xml + ass**，不嵌进视频。
- **字幕合并单独成功能**：主界面「合并弹幕」按钮，或 `--merge-sub 视频 字幕 --sub-mode soft|hard`；
  只有两种：软字幕出 `.mkv`（可开关）、硬字幕烧进画面（重编码）。输出选的是**文件夹**，
  产物按 `<视频名>.sub.mkv / .sub.mp4` 命名，一律另存，**不覆盖原视频**，长视频全程流式处理。
- **最小化到托盘**：关闭主界面、最小化直播窗口都会收进托盘继续录；托盘右键有「显示主界面 / 录制直播 / 退出」。
- **Win11 风格图形界面**：两栏布局，左=输入与选项、右=分集预览与运行日志；窗口按屏幕比例自适应，
  卡片也会跟着窗口一起伸缩。分集清单可勾选，也能直接输 `1,3-5,49-234`，**勾选与文本双向同步**。
  凭证卡片是终端样式的状态区，按"未读取 / 待校验 / 有效 / 已失效"显示不同界面。
- **默认存到桌面**（Windows 读注册表，认 OneDrive 重定向），`-o` 随时改。
- **多线程下载 + 每线程一条进度条**：合集/多P 时默认 **4 个文件同时下**，终端底部就是 4 行实时状态，
  每行写明**是哪个视频的哪条流**（如 `[11/22] #43 逃离棋盒 · 1080P 视频流`）。进度条按**终端实际宽度**自适应，
  标题按宽度预算截断，保证百分比/大小/速度不被挤掉；输出被重定向时自动改成"每 15 秒一行"。
- **慢速连接自动重连**：某条流的速度掉到**它自身历史平均**（开始到 10 秒前）的 **30% 以下并持续 10 秒**，
  就丢掉连接、换 CDN 节点用 `Range` 续传，进度不丢（默认最多 5 次，`--max-reconnects 0` 关闭）。
  **若按当前速度算出的预计剩余时间不足 10 秒，则保持连接下完**，不做无谓重连。
- **下载很抗折腾**：CDN 节点优选、每节点多次重试 + 退避、HTTP Range 断点续传、大小完整性校验。
- **原子写入**：所有产物先写 `.part`，成功才改名 —— 失败绝不会留下半个文件毁掉旧文件。
- **可重复执行**：已下载的自动跳过；失败的保留 `.m4s` 流文件，重跑即续传而不是从头再来。
- **WBI 接口签名**，签名失败自动回退旧接口。
- **SESSDATA 只问一次**：存进 Windows 用户环境变量，源码里永远不留凭证。
- **目录自动整理**：文件名清洗、Windows 保留名避让、超长路径自动缩短（补短哈希防重名）。
- `--dry-run` 先看计划；退出码规范（`0` 成功 / `1` 有失败 / `2` 参数错误 / `130` 中断）。
- **真正可非交互**：加 `-y` 或把输出重定向后，即使在新机器上没凭证也不会停下提问，CI/批处理可用。
- **跨平台**：Windows / Linux / macOS 同一份源码；Windows 凭证存用户环境变量，其他平台存
  `~/.config/bilibili-downloader/sessdata`（权限 600）。

## 环境要求

| 项目 | 说明 |
|---|---|
| Python | 3.9 及以上（源码版）；图形界面还需要 tkinter（Windows 官方 Python 默认带） |
| 依赖库 | `pip install -r requirements.txt`（requests、tqdm） |
| ffmpeg | 合并音视频、导出 MP3、封装/烧录弹幕都靠它。已在 `PATH` 里就直接用；Windows 上没装时程序会问一次"要不要帮你装到 `~\ffmpeg`"，也可以 `--install-ffmpeg` |

## 安装

### 方式一：安装包（Windows，推荐）

到 [Releases](https://github.com/zyq1223334444/bilibili-downloader/releases) 下载最新的
`bilibili_downloader_setup_<版本>.exe` 双击安装：

- 装到 `C:\Program Files\bilibili-downloader`，带开始菜单快捷方式与**卸载程序**（"设置 → 应用"里也能卸载）
- 可选把安装目录加入系统 `PATH`（默认勾选），之后任意终端直接敲 `bilibili_downloader`；
  改动之前先把系统 `PATH` 的原值备份进注册表，卸载时**按原值还原**（这期间别人也改过 `PATH` 时
  退化成只摘掉自己那一项，所以原值末尾的 `;`、中间的空项 `;;` 都不会被改坏）
- **安装过程会顺手把 ffmpeg 也装上**：只认环境变量 `PATH`（系统 `PATH` + 用户 `PATH` + 进程 `PATH`），
  `ffmpeg.exe` 在里面就用现成的；不在就当作没装，不会去猜 `%USERPROFILE%\ffmpeg` 这类固定目录。
  没找到的话，向导里会先出现一页**"ffmpeg 下载源"**（默认镜像源 `ghfast.top`，国内通常更快；也可以选官方源 GitHub 发布页；
  已有 ffmpeg 时这页自动跳过）；点最后一页的"安装"时再弹窗说明"缺少 ffmpeg 会导致无法使用完整功能
  （不能合并、导出 MP3、嵌弹幕）"，**显示当场查出的真实大小**（约 114 MB）和所选源，默认"是"。
  同意后出现一个**下载页**：有进度条、速度和"停止"，可以随时中止。**下载途中点"停止"会问要不要换另一个源重下**，
  下载失败也会问同样一句，换源后从头重来，不会把半截文件当成功。
  下载完成再解压到 `%USERPROFILE%\ffmpeg`（只留 `bin` 里的 `ffmpeg.exe` 等文件），
  并把 `%USERPROFILE%\ffmpeg\bin` 追加到**用户 `PATH`**（`HKCU\Environment`，不动系统 `PATH`），
  ffmpeg 这条不做备份、卸载时也不还原（程序目录那条才做备份）。
  静默安装（`/VERYSILENT`、`/SILENT`）不弹窗、也不下载，只在日志里记一行，免得无人值守部署永远停在对话框上。
- 卸载时**只删掉程序自己的 `PATH` 条目**，对 ffmpeg 一概不动——`~\ffmpeg` 的文件和它那条 `PATH` 全部原样保留（别的工具可能也在用，重装可直接复用）

### 方式二：免安装（Windows 单文件 / 压缩包）

| 下载 | 形态 | Ctrl+C 退出码 |
|---|---|---|
| `bilibili_downloader.exe` | 单文件（约 14 MB，运行时自解压） | `0xC000013A`（见下方说明） |
| `bilibili_downloader_standalone_win64.zip` | 解压出一个文件夹（启动更快） | **130**，与源码版一致 |

```powershell
.\bilibili_downloader.exe BV1xx411c7mD -q 720p --no-mp3
.\bilibili_downloader.exe --dry-run BV1xx411c7mD
```

> **单文件版的已知差异**：`--onefile` 在真正的程序外还套了一层自解压引导进程。按 Ctrl+C 时控制台事件
> 同时送达两者，引导进程先退出，于是命令行看到的退出码是 `0xC000013A`（显示为 `-1073741510`）而不是 130。
> 程序本身依然正常收尾：打印 `[中断]`、保留 `.part` 断点、不留残余进程、临时目录清理干净——**只有退出码不同**。
> 脚本里要判断 130 的话请用 standalone 版，或把 `0xC000013A` 一并当作"已中断"。

### 方式三：Linux / macOS

| 平台 | 单文件 | 文件夹版（含可执行权限，推荐） |
|---|---|---|
| Linux x86_64 | `bilibili_downloader_linux_x86_64` | `bilibili_downloader_linux_x86_64.tar.gz` |
| macOS Intel | `bilibili_downloader_macos_x86_64` | `bilibili_downloader_macos_x86_64.tar.gz` |
| macOS Apple Silicon | `bilibili_downloader_macos_arm64` | `bilibili_downloader_macos_arm64.tar.gz` |

```bash
tar -xzf bilibili_downloader_linux_x86_64.tar.gz
./bilibili_downloader_standalone/bilibili_downloader BV1xx411c7mD --single -q 720p
```

> macOS 上是**未签名**的二进制，首次运行可能被 Gatekeeper 拦下：
> `xattr -d com.apple.quarantine <文件>`，或右键 → 打开。
> Linux / macOS 的二进制由 GitHub Actions 在**真机**上构建（见 `.github/workflows/build.yml`），
> 因为 Nuitka 把 Python 编译成 C 后要调用目标平台自己的链接器，**不支持交叉编译**。
> 想自己构建：`bash build/build_unix.sh`（Linux 需要 gcc / patchelf）。
> 从 CI 下来的 Linux / macOS 包是**纯命令行**的：构建机没装 Tk，`build_unix.sh` 在 `import tkinter`
> 失败时会静默跳过图形插件，免得整条流水线挂掉。想在这些平台上用图形界面，自己在装了 `python3-tk`
> 的机器上构建即可（界面只用了跨平台的 tkinter 控件）。

三种二进制都由 Nuitka 把 Python **编译成 C 再链接**而成，已内置 Python 运行时与 `requests` / `tqdm`
（Windows 构建还带 tkinter，Linux / macOS 构建是否有界面取决于构建机有没有 tcl/tk），
**唯一还需要的外部程序是 ffmpeg**。Windows 上会先找 `PATH`，找不到就问你要不要自动装到 `~\ffmpeg`
（也可以直接 `--install-ffmpeg`）；Linux / macOS 用包管理器装：`brew install ffmpeg` / `sudo apt install ffmpeg`。

### 方式四：从源码运行

```powershell
git clone https://github.com/zyq1223334444/bilibili-downloader.git
cd bilibili-downloader
pip install -r requirements.txt
python bilibili_downloader.py          # 不带参数 → 图形界面
```

参数、保存结构、凭证读取顺序与二进制版完全一致（"程序目录下的 `sessdata.txt`"对二进制而言就是**它旁边**那个文件）。

## 快速开始

```powershell
# 不带参数 → 打开图形界面（画质/输出/弹幕/凭证都在窗口里选）
python bilibili_downloader.py

# 单个视频 → 桌面\<视频标题>\<视频标题>.mp4 与 .mp3（默认就存桌面）
python bilibili_downloader.py BV1xx411c7mD

# 顺便把弹幕存下来，并封装成 MKV 里的字幕轨（不重编码，很快）
python bilibili_downloader.py BV1xx411c7mD --danmaku light --danmaku-video soft

# 弹幕多抓一些，并直接烧进画面（重编码，慢，但到哪都能看）
python bilibili_downloader.py BV1xx411c7mD --danmaku full --danmaku-video hard

# 多P视频只下第 2 个分P
python bilibili_downloader.py "https://www.bilibili.com/video/BV1xx411c7mD?p=2" --single

# 只看看会下载什么，不真的下
python bilibili_downloader.py BV1xx411c7mD --dry-run

# 限制画质、不要 MP3、换保存目录
python bilibili_downloader.py BV1xx411c7mD -q 720p --no-mp3 -o D:\videos

# 只要音频，码率 192k
python bilibili_downloader.py BV1xx411c7mD --audio-only --mp3-bitrate 192

# 只打开「录制直播」窗口（图形界面；主界面上也有同名按钮）
python bilibili_downloader.py --live

# 把弹幕/字幕单独合并进视频（输出到指定文件夹，产物名 <视频名>.sub.mkv，不覆盖原视频）
python bilibili_downloader.py --merge-sub 视频.mp4 弹幕.xml --sub-mode soft --merge-out D:\output

# 没装 ffmpeg？让它下载 Windows 包并装到 ~\ffmpeg（约 114 MB）
python bilibili_downloader.py --install-ffmpeg

# 国内慢的话指定镜像源（ghfast.top 转发 GitHub 发布页）
python bilibili_downloader.py --install-ffmpeg --ffmpeg-source mirror
```

**首次运行**若没检测到凭证，脚本会打印获取方法并询问一次 `SESSDATA`（输入不回显），
校验通过后自动保存到 Windows 用户环境变量 `BILI_SESSDATA`。之后**新开一个终端窗口**运行即可自动读取。

### 图形界面

不带任何参数（或显式 `--gui`）启动就是 GUI。它是 Win11 浅色风格的两栏窗口：左边输入与选项，
右边分集预览与运行日志；窗口按屏幕比例定大小，卡片随窗口一起伸缩。

| 区域 | 内容 |
|---|---|
| 链接 | 一个或多个视频链接 / BV 号 / av 号 / b23.tv 短链；"读取分集"抓清单，"粘贴"、"清空" |
| 保存到 | 默认桌面（直播窗口读取直播间后默认落到 桌面\<直播间名称>\），可"浏览"换目录，"打开目录"直接进资源管理器 |
| 输出 | 画质上限、MP3 码率、内容三选一（视频+MP3 / 仅视频 / 仅 MP3） |
| 弹幕 | `不下载 / 精简 / 多`，以及 `不放进视频 / 软字幕(MKV) / 烧进画面` |
| 分集预览 | 表格列出编号 / 标题 / 时长，单击一行切换 ☑，另有"全选 / 全不选"；**序号框**可直接写 `1,3-5,49-234`（空格、顿号、中文逗号都认），回车或点"应用序号"生效 |
| 高级 | 并发数、节点重试、超时、重连上限，五个开关（只下当前、已存在重下、关探测、只看计划、重输凭证） |
| 凭证 | 终端样式状态区，按状态换界面（见下），登录后输入框收起成"更换 / 清除" |
| 底部 | 合并弹幕 / 录制直播 / 开始下载 / 取消 / 打开目录 / 帮助 + 状态栏 + ffmpeg 状态（没装时才出现"安装 ffmpeg"按钮） |
| 直播窗口 | 直播间链接或房间号、画质、分段分钟数、保存目录、精简/全部弹幕勾选、保留分段；开始/停止/打开目录；预览 + 试看 10 秒；预约任务表（添加 / 暂停启用 / 删除）与录制日志；关闭即收进托盘继续录 |
| 合并弹窗 | 视频、字幕/弹幕、输出文件夹三栏 + 两种保存方式（软字幕 MKV / 硬字幕），产物另存、不覆盖原视频 |

**分集预览与序号双向同步**：点表格行切换勾选时，序号框自动压成紧凑写法（如 `3-5,49-234`）；
在序号框里写范围后按回车/点"应用序号"，表格勾选立刻跟着变。序号越界、写成 `abc` 之类会提示具体原因
并保持原选择。读取清单只取视频信息，不下载任何内容。

**凭证卡片的状态**（黑色区域像终端，等宽字体 + 彩色提示符）：

| 状态 | 显示 |
|---|---|
| 还没读取到凭证 | `> 游客模式 · 还没读取凭证`，并说明游客画质上限 |
| 读到了、正在校验 | `> 已读取 SESSDATA（来源：环境变量 / 凭证文件 …）` + `正在校验…` |
| 校验通过 | `> 已登录 · 凭证有效`，输入框收起，显示打码后的凭证和"更换 / 清除" |
| 校验失败 | `> 凭证已失效或已过期`，自动清空输入框方便粘新的 |

`SESSDATA` 只影响**画质上限**（填了才有 1080P+ / 4K / 无损音频），**和下载速度无关**。
"保存并校验"会写进 Windows 用户环境变量，并立刻用账号接口校验一次，结果直接显示在状态区里。

窗口"帮助"按钮弹出的是**GUI 专用帮助**（讲界面里每一项是什么意思），末尾固定提示
`使用 -h/--help 查看命令行帮助` —— 那是另一份文档：命令行参数完整列表。

> GUI 里下载在后台线程跑，日志实时刷到下面的框；分集清单由界面自己接管，
> 所以不会出现"堵在终端里等你输入编号"的情况。工作线程启动时会自动补 `-y`，不会卡在提问上。

## 保存结构

默认根目录是**桌面**（Windows 读注册表里的桌面路径，OneDrive 重定向到 `OneDrive\桌面` 也认），
`-o` 可改。下面是默认设定（`--danmaku light --danmaku-video none`）的样子：

```
桌面\
├── <视频标题>\                         # 单视频（两层）
│   ├── <视频标题>.mp4
│   ├── <视频标题>.mp3
│   ├── <视频标题>.danmaku.xml          # 弹幕原文（B 站原生 xml）
│   └── <视频标题>.danmaku.ass          # 转好的 ASS 字幕，播放器可直接挂
├── <视频标题>\                         # 多P视频（三层，P 序号保证顺序）
│   ├── P01 <分P标题>\
│   │   ├── P01 <分P标题>.mp4
│   │   ├── P01 <分P标题>.mp3
│   │   └── P01 <分P标题>.danmaku.xml / .ass
│   └── P02 <分P标题>\……
└── <合集标题>\                         # 合集（三层）
    ├── <视频标题>\
    │   ├── <视频标题>.mp4 / .mp3 / .danmaku.xml / .danmaku.ass
    │   └── <视频标题>\P01 <分P标题>\……  # 合集里又有多P视频时（四层）
```

两处会不一样，其余层数不变：

- `--danmaku-video soft`：成品变成 **`.mkv`**（`.mp4` 被删掉）。MKV 是少数能同时装"可开关的 ASS 字幕轨"
  和 B 站那种"HD/4K"编码的常见容器，换封装不重编码，几秒完成。
- `--danmaku-video hard`：成品还是 `.mp4`，弹幕已经烤进画面，弹幕文件照旧留着。

## 弹幕

### 抓多少：`--danmaku light / full`

| 档位 | 留下什么 | 适合 |
|---|---|---|
| `light`（默认） | 去掉"高级/代码"类弹幕，同一句话 5 秒内只留一条，超过 60 字截断，**每秒最多 6 条**；车道（同一水平线）占满时**直接丢掉那条**，绝不压字 | 想看热闹但不想满屏糊住画面，烧进视频也不挡人脸 |
| `full` | 去掉滚动/顶部/底部之外的类型（代码弹幕等一律丢），其余全留；车道不够时挑最早空出的那条，宁可轻微重叠也不丢 | 留档、做素材、自己后期挑 |
| `none` | 不抓弹幕 | 只要视频 |

> 抓的是**网页端当前能看到的弹幕**（`comment.bilibili.com/{cid}.xml`，两个地址互为兜底）。
> B 站接口自己就有限制：热门视频的 XML 条数常常少于稿件统计的 `danmaku` 数（实测 3791 → 3200）。
> 分段 protobuf 接口（`x/v2/dm/web/seg.so`）实测返回**更少**（1143），所以没有采用，别指望"一条不漏"。

### 放进视频：`--danmaku-video soft / hard`

| 模式 | 做什么 | 代价 |
|---|---|---|
| `none`（默认） | 只留 `.danmaku.xml` 与 `.danmaku.ass` | 无 |
| `soft` | 把 ASS 作为字幕轨封装进 `.mkv`，默认轨、语言标 `chi` | 换封装，秒级，不损失画质；字幕可在播放器里关 |
| `hard` | 用 libx264 重新编码，把弹幕直接画在画面上（`.mp4`） | 慢（按 CPU 跑满算），有一次重编码损失；好处是发到手机/微信谁都能看 |

字幕细节：字号、行高、车道数都按**视频实际分辨率**换算（1080P 下约 40 px 字、每条 8 秒滚完），
滚动/顶部/底部三种弹幕**共用同一套车道**，避免同一条水平线上压字；`\ { }` 会被转成全角，
颜色按 B 站 `p` 字段的十进制 RGB 转成 ASS 的 `&HBBGGRR&`。

## 参数一览

| 参数 | 默认 | 说明 |
|---|---|---|
| `inputs` | 交互输入 | 一个或多个：视频链接 / `BV` 号 / `av` 号 / `b23.tv` 短链 |
| `-o, --output` | 桌面 | 保存根目录（Windows 按注册表取真实桌面，认 OneDrive 重定向） |
| `-q, --quality` | `max` | 画质上限：`max 8k 4k 1080p60 1080p+ 1080p 720p60 720p 480p 360p` |
| `--mp3-bitrate` | `320` | MP3 码率：`128 / 192 / 256 / 320` |
| `--audio-only` | 关 | 只导出 MP3（不下载视频流） |
| `--no-mp3` | 关 | 只保存 MP4 |
| `--danmaku` | `light` | 弹幕：`none` 不下载 / `light` 精简 / `full` 多 |
| `--danmaku-video` | `none` | 弹幕放进视频：`none` / `soft`（MKV 字幕轨）/ `hard`（烧进画面） |
| `--single` | 关 | 只下输入链接指向的那一个视频/分P，忽略合集 |
| `-j, --jobs` | `4` | 并发线程数（最多 4），每个线程一条进度条 |
| `--max-reconnects` | `5` | 单个流因"速度掉到历史平均 30% 以下"而重开连接的次数上限（`0` = 关闭该检测） |
| `--force` | 关 | 已存在也重新下载 |
| `--no-probe` | 关 | 关闭节点优选探测 |
| `--retries` | `2` | 每个节点重试次数 |
| `--timeout` | `15` | 网络超时（秒） |
| `--reset-sessdata` | 关 | 忽略已保存凭证，重新输入（换号或过期时用） |
| `--dry-run` | 关 | 只列出计划，不下载 |
| `--install-ffmpeg` | 关 | 下载 ffmpeg（约 114 MB）到 `~\ffmpeg` 并加入用户 `PATH`（仅 Windows） |
| `--ffmpeg-source` | `auto` | ffmpeg 下载源：`auto`=官方→镜像→gyan 依次回退，`official`=GitHub 官方，`mirror`=ghfast.top 镜像；指定源连不上仍会退到下一个可用地址 |
| `--gui` | 关 | 打开图形界面；不带任何参数运行时默认就是它 |
| `-y, --yes` | 关 | 不询问，直接全部下载（跳过范围选择与凭证重输） |

> `--danmaku-video` 需要弹幕，和 `--danmaku none` 一起用会报参数错误；
> `--audio-only`（不下载视频流）也不能嵌弹幕，同样会直接拒绝，而不是下完才发现没法做。

## 命令行下选择要下载的分集

合集/多P 会先列出编号清单，然后询问要下哪些：

```
共 54 项。回车 / y = 全部下载，n = 不下载，也可只下部分（如 1,3,5,6-20）：
> 1,3,5,6-20
[选择] 已选 20/54 项：1,3,5-6,6-20
```

| 输入 | 效果 |
|---|---|
| 回车、`y`、`yes`、`all` | 全部下载 |
| `n`、`no`、`q` | 不下载，直接退出（退出码 0） |
| `1,3,5,6-20` | 只下这些：支持区间、重复项、空项（`1,,3`）、全角逗号 `1，3`，顺序自动整理 |
| `20-6` | 区间写反也认，等价于 `6-20` |
| 非法输入（如 `abc`、`0`、`99`） | 提示原因后重问，连续 3 次无效则取消 |

选完后回显 `[选择] 已选 N/总数 项：1,3,5-8`；下载时的 `[3/20]` 是"正在下第 3 个"，
行首 `#5` 是**清单里的原始序号**，方便和上面列表对照。

> 非交互场景（输出被重定向、或加了 `-y`）不会询问，直接全部下载 —— 保持脚本/CI 可用。
> 单个视频/单个分P 也不会询问（没什么可选）。
> 图形界面里这套选择由"分集预览"表格接管，规则相同（序号框写法也一样）。

## SESSDATA 凭证

**读取顺序**：① 当前进程的环境变量 `BILI_SESSDATA` → ② **Windows 注册表里的用户环境变量**（直查 `HKCU\Environment`）
→ ③ 程序目录下的 `sessdata.txt`（源码版=脚本所在目录，exe 版=exe 所在目录）→ ④ `~/.config/bilibili-downloader/sessdata`。
都没有就会询问一次；Windows 下保存到用户环境变量（并同步当前进程），其他系统写入配置文件（权限 600）。

> 为什么要直查注册表：Windows 只在**进程启动那一刻**注入环境变量，已经开着的终端（尤其常驻的终端/服务进程）
> 拿到的是旧快照，于是会出现"明明设置成功了，脚本却说没检测到"。直查注册表后，旧终端里运行同样能读到。

**启动时会用 `nav` 接口校验一次凭证**：

| 结果 | 表现 |
|---|---|
| 有效 | 打印 `[凭证] 校验通过（普通账号 / 大会员）`，顺便说明你的画质权限 |
| 失效 | 打印 `[!] 凭证已失效……只能以游客身份下载，一般最高 480P/360P`，并提示怎么换；交互式终端里会问"现在重新输入 SESSDATA？" |
| 网络不可用 | 跳过校验，按原样使用 |

> 以前凭证失效会**静默降级**到 480P，看起来像"脚本坏了"；现在会直接告诉你原因。
> 需要完全非交互（脚本/CI，或输出重定向）时不会提问；加 `-y` 也不会问。
> 图形界面里则是凭证卡片的状态区直接显示结果（见上文"图形界面"）。

手动设置（PowerShell，永久生效）：

```powershell
setx BILI_SESSDATA "你的SESSDATA值"
```

获取方法：浏览器登录 B 站 → 按 `F12` → **Application** → **Cookies** → 选 `https://www.bilibili.com`
→ 复制名为 `SESSDATA` 的值。

查看 / 删除：

```powershell
[Environment]::GetEnvironmentVariable('BILI_SESSDATA','User')          # 查看（会打印明文，注意旁边有没有人）
Remove-ItemProperty -Path 'HKCU:\Environment' -Name 'BILI_SESSDATA'   # 删除
```

> ⚠️ `SESSDATA` 等同于账号登录凭证：不要写进源码、不要提交仓库、不要发给别人。
> 一旦怀疑泄露，立刻到 B 站「设置 → 安全隐私 → 退出所有设备」使旧凭证失效。

## 断点续传与中断

- **随时 Ctrl+C 都安全且立刻生效**：主线程每 0.3 秒检查一次信号，收到就通知下载线程收手并**立即退出**
  （不会等卡住的线程或 ffmpeg），不打印 traceback，退出码固定为 130；已下载的 `.part` / `.m4s` 都会保留，重跑即续传。
- 视频/音频先下载到 `<名字>.video.m4s.part` / `<名字>.audio.m4s.part`；重跑时用 `Range` 从已有字节数继续。
- 成功后改名为 `.m4s` → 合并 → 导出 → **删除**临时流文件。
- 失败时**保留**这些文件，因此重新执行同一条命令是"续传"而不是"从头下载"。
- 实际字节数与 `Content-Length` / `Content-Range` 不一致时判为失败并重试，避免用被截断的文件去合并。
- 若本地残留与远端不一致会返回 `416`，此时自动清除断点重新下载。
- 图形界面里"取消"等价于 Ctrl+C：当前分块下完就停，已完成的部分照常保留。

### 输出里的状态标记

| 标记 | 含义 |
|---|---|
| `[跳过]` | 已有缓存 / 成品已存在，不重复下载 |
| `[重试]` | 某节点某次尝试失败，并说明下一步：**同一节点重试** / **换下一个节点** / **已无可用节点** |
| `[重连]` | 速度掉到自身历史平均的 30% 以下并持续 10 秒：丢掉连接、换节点用 Range 续传（预计剩余不足 10 秒则不动） |
| `[成功]` | 中间失败过、但最终成功（一切顺利时不播报，避免刷屏） |
| `[失败]` | 该项目彻底失败（所有节点都试过），整批退出码变成 1 |
| `[完成]` | 产出的成品文件，带大小（嵌了弹幕会额外标明"含弹幕软字幕"或"弹幕已烧进画面"） |
| `[弹幕]` | 这一项的弹幕抓了多少条、留了多少条；抓失败时只警告，视频照常保存 |
| `[结果]` | 整批统计与失败明细 |
| `[中断]` | 你按了 Ctrl+C（退出码 130） |

网络错误会被压成一行可读文本（不再打印嵌套异常的原始元组）：

```
视频流：[重试] 节点 1/3 第 1 次失败（远程主机强迫关闭了一个现有的连接。（ConnectionResetError 10054））→ 换下一个节点
视频流：[成功] 第 2 个节点第 1 次尝试成功（191.4 MB，用时 42s）
#2 [完成] P02 空月之歌 第一幕 雪浪与苍林之舞（2）.mp4（191.4 MB）
```

> 关键：**看到 `[重试]` 不等于失败** —— 结论看这一行的结尾（换下一个节点 / 已无可用节点）和紧随其后的 `[成功]` / `[失败]`。

## 常见问题

| 现象 | 说明 |
|---|---|
| `未找到 ffmpeg` | 装 ffmpeg 并进 `PATH`；Windows 上直接 `--install-ffmpeg`，或装安装包（它会问一次） |
| 启动时问"要装 ffmpeg 吗" | 检测不到 ffmpeg。不装也能下视频流，但**不能合并成 MP4、不能导出 MP3、不能嵌弹幕**；答 `n` 就只做能做的部分 |
| GUI 打不开 | 源码版需要 tkinter（Windows 官方 Python 自带）；自己编译时脚本已带 `--enable-plugin=tk-inter` |
| GUI 窗口被屏幕截断 | 窗口按屏幕比例定尺寸（1280×720 以下的小屏也放得下）；仍不合适就直接拖拽缩放，卡片会跟着变 |
| 分集预览是空的 | 先点"读取分集"取清单；换了链接或改了"只下当前"要重读一次 |
| 序号框输入了没反应 | 要按回车或点"应用序号"；`0`、越界、`abc` 之类会提示原因并保留原选择 |
| 弹幕条数比网页上少 | B 站 XML 接口本身只给"当前可见"的一批，热门稿件常见少 10%~20%（见上文"弹幕"） |
| 烧弹幕后视频变慢/变大 | `hard` 是重编码，必然如此；只想留档就用 `soft` 或 `--danmaku-video none` |
| 得到的 `.mkv` 拖不进某些软件 | 容器兼容问题，不是文件坏了；PotPlayer/VLC/mpv 都认，B 站自家播放器也认软字幕 |
| 只能下 360P/480P | 没设置有效 `SESSDATA`，或账号本身没有该画质 |
| `该视频没有 DASH 流` | 番剧/影视内容（本工具只支持普通投稿），或极老视频 |
| `这是番剧/影视内容` | 接口返回了 `redirect_url`，ep/番剧不在支持范围内 |
| `code=62002 / 62004` | 稿件不可见 / 审核中 |
| `《…》是付费合集` | 付费合集无法下载 |
| 进度长时间不动 | 换节点中；脚本正在重试+退避，看那一行"节点 x/y 第 n 次失败"即可 |

## 仓库结构

仓库里放的是**程序本身**和**构建它的手段**；构建**产出**的东西全部集中在一个被忽略的目录里，
所以 clone 下来永远是干净的：

```
bilibili_downloader.py      整个程序（单文件）
requirements.txt            运行时依赖（requests、tqdm）
readme.md / readme.zh.md    本文档（英文 / 中文）
CHANGELOG.md                版本变更记录
LICENSE
.github/workflows/build.yml CI：Linux + 两个 macOS 架构
build/                      构建工具（属于仓库内容）
├── build_exe.bat             Windows 单文件 exe
├── build_exe_standalone.bat  Windows 文件夹版 + zip
├── build_installer.bat       Windows 安装包（调用 installer.iss）
├── build_unix.sh             Linux / macOS 二进制
├── installer.iss             Inno Setup 脚本（含 ffmpeg 询问流程）
├── ffmpeg_setup.ps1          安装包里"探测大小 / 下载解压 ffmpeg"的脚本
├── ChineseSimplified.isl     安装包的中文文案
└── out/                      被忽略：全部产物与 Nuitka 中间目录
```

`.gitignore` 只排除 `build/out/` 这类产物；构建脚本本身提交进仓库，clone 之后能自己重新编译。

## 从源码构建（Nuitka）

| 想要什么 | 在哪构建 | 命令 |
|---|---|---|
| Windows 单文件 exe | Windows | `build\build_exe.bat` → `build\out\bilibili_downloader.exe` |
| Windows 文件夹版 | Windows | `build\build_exe_standalone.bat` → 文件夹 + zip，都在 `build\out\` |
| Windows 安装包 | Windows | `build\build_installer.bat`（需要 Inno Setup 6.5+） |
| Linux / macOS 二进制 | **对应平台**（WSL / Mac / CI） | `bash build/build_unix.sh` → `build/out/dist_unix/` |

脚本会自己算出仓库根目录，因此在任何工作目录下都能直接运行，且只往 `build/out/` 里写东西。

环境要求：`pip install -r requirements.txt nuitka zstandard`，Windows 上还需要 **MSVC 14.3+**
（Visual Studio 2022 Build Tools 或更新版本）——Nuitka 在 Python 3.13 及以上**不能用 MinGW**。
四个值得知道的参数（都是实测踩出来的，完整说明在脚本注释里）：

- `VSLANG=1033` —— Nuitka 的 Scons 后端用 `mbcs` 代码页解码 `cl.exe` 输出，中文版 Visual Studio
  会让构建抛 `UnicodeDecodeError`，强制英文消息即可绕过。
- `--include-package-data=certifi` —— `requests` 用 certifi 的 `cacert.pem` 校验 TLS，那是数据文件而非代码。
  没有它 exe 能启动，但每次 HTTPS 请求都会报 *"Could not find a suitable TLS CA certificate bundle"*。
- `--windows-console-mode=force` —— 这是控制台工具，不加这个参数会变成没有 stdout 的 GUI 子系统程序。
- `--enable-plugin=tk-inter` —— 把 Tcl/Tk 运行时和 tcl 数据文件一起打包，否则 GUI 起不来。
  三个构建脚本都会先试 `import tkinter`：Windows 上缺了直接报错退出并说明怎么补，
  `build_unix.sh` 则降级为"只编命令行版"，避免 CI 因为没装 tcl/tk 整条流水线挂掉。

安装包用 **Inno Setup 6.5+** 编译：`winget install --id JRSoftware.InnoSetup -e`。
它在 `[Code]` 里先把系统 `PATH` 原值备份进注册表再修改，卸载时按原值还原（别人改过就只摘掉自己的条目）；
ffmpeg 部分由 `build/ffmpeg_setup.ps1` 完成（`-Mode Size` 只用 `GET + Range: 0-0` 读 `Content-Range` 拿真实大小，
`-Mode Url` 按 `-Source` 返回官方或镜像地址，`-Mode Install` 下载 + 解压 + 自检）。该脚本刻意保持 ASCII-only
（PowerShell 5.1 按 ANSI 读文件）。

**ffmpeg 从不打包进去** —— 它是约 114 MB 的外部程序，运行时按 `PATH` → `%USERPROFILE%\ffmpeg\bin` 查找。
Windows 上程序自己会问要不要装（`--install-ffmpeg` 可跳过询问直接装），安装包也会替用户装一次；
Linux / macOS 得用包管理器单独装。下载地址不是写死的：先用 GitHub API 找到当前版本的同一个
`*essentials_build.zip`（gyan.dev 官方站在国内实测只有 ~30 KB/s，GitHub 上能到 1 MB/s，套 `ghfast.top`
镜像实测 2～3 MB/s）。源可选：`official` 走 GitHub，`mirror` 给地址加 `https://ghfast.top/` 前缀，
`auto` 依次尝试；哪个连不上就换下一个，安装包下载途中点"停止"也会问要不要换源重来。
提示里显示的大小也是当场查出来的真实字节数。

> **为什么 Linux/macOS 不能在 Windows 上编**：Nuitka 把 Python 编译成 C，然后调用**目标平台自己的**
> 编译器/链接器，没有交叉编译。本仓库用 GitHub Actions 在真机上构建 Linux 与两个 macOS 架构，
> 见 `.github/workflows/build.yml`。

## 实现要点（给想读代码的人）

- **DASH 分流**：B 站把高清画面与声音分成两条流，本工具分别下载后用 `-c copy` 只换封装、不重编码，
  所以合并是秒级的；`+faststart` 把索引挪到文件头，网页/播放器可立即拖动进度。
- **WBI 签名**：`w_rid = md5(排序后的查询串 + "&wts=时间戳" + mixin_key)`，`mixin_key` 由
  `nav` 接口返回的 `img_url` / `sub_url` 经 64 项置换表重排得到；签名接口失败自动回退非签名接口。
- **节点优选**：对 `baseUrl` 与所有 `backupUrl` 并发 `HEAD`，谁先回应成功用谁（比延迟，不比带宽）。
- **弹幕**：一次 `GET comment.bilibili.com/{cid}.xml`（备选 `api.bilibili.com/x/v1/dm/list.so?oid={cid}`），
  正则抠 `<d p="时间,模式,字号,颜色,…">正文</d>`。响应偶尔是 gzip/deflate 裸流（`Content-Encoding` 没标对），
  所以自己再按 `\x1f\x8b` / zlib 头兜一次；正文走 `html.unescape` 并清掉控制字符。
  `light` 的去重按 5 秒桶 + 每秒 6 条上限，是为了让烧录版不至于变成一堵字墙。
- **ASS 生成**：`PlayRes` 直接用视频分辨率，字号/行高/车道数都按高度等比换算；三种弹幕共用同一个
  `lanes` 字典记账，避免滚动弹幕和顶部弹幕在同一水平线重叠；颜色从 `p` 字段的十进制 RGB 转 `&HBBGGRR&`，
  `\ { }` 转全角避免被当成 ASS 标签。
- **调用 ffmpeg 的两个坑**：① 烧字幕的滤镜串里写绝对路径时，Windows 盘符的冒号会被当成
  `original_size` 参数分隔符（`ass=C\:/…` 直接失败），所以改成 `cwd=字幕所在目录` + 只给文件名的单引号写法；
  ② 软字幕必须换封装到 MKV（`-c copy -c:s ass`），MP4 里塞 ASS 播放器普遍不认。
- **原子写入**：`os.replace()` 在同一目录内改名在 Windows 与 POSIX 上都是原子操作。
- **Ctrl+C 响应**：主线程用 `futures.wait(timeout=0.3)` **轮询**，而不是 `as_completed` 的无限等待 —— 
  在 Windows 上主线程卡在无限等待里无法处理挂起的信号，表现就是"按了 Ctrl+C 没反应"；确认中断后用
  `os._exit(130)` 立即退出，不再等非守护的下载线程。
- **并发/进度条**：`ThreadPoolExecutor` 最多 4 线程，各线程负责一个视频（其视频流与音频流仍在该线程内串行）；
  进度条用 `tqdm(position=线程槽位)` 堆叠，因此 4 线程就是 4 条互不覆盖的进度条，普通输出统一走 `tqdm.write`；
  playurl 调用加锁串行化并保持 0.5 秒最小间隔；探测另用临时线程池。
- **GUI**：tkinter 没有圆角控件，卡片与按钮用 `Canvas` 自绘（圆角多边形 + 悬停/按下/禁用三态）；
  分集清单用 `ttk.Treeview`，点击行切换 ☑ 与序号框互相同步；凭证校验在后台线程跑，
  结果通过 `queue` 回主线程刷新，避免 tkinter 跨线程崩溃。

## 更新日志

见 [CHANGELOG.md](CHANGELOG.md)。2.1.3 重做了安装包里的 ffmpeg 下载窗口（圆角渐变进度条、剩余时间、扁平停止按钮）；
2.1.2 修正安装包的 ffmpeg 口径：探测只认环境变量 PATH、bin 目录写进用户 PATH、卸载对 ffmpeg 一概不动，下载进度窗不再被 SW_HIDE 藏住；
2.1.1 把安装包的 ffmpeg 下载改成 8 线程（显示总进度 + 总速度，可停止、断线续传），
合并字幕只保留软 / 硬两种并改成选文件夹，直播默认保存到 `桌面\<直播间名称>\`，卸载不再删除 ffmpeg 的 PATH 条目；
2.1.0 新增直播录制（默认原画、途中可切画质、分段写盘、预览、预约开播自动录、双份弹幕单独保存）
和独立字幕合并（软字幕 / 硬字幕，产物另存不覆盖），主界面支持最小化到托盘；
2.0.4 修掉了 2.0.3 安装包里"缺 ffmpeg 时弹 Unclosed constant"的毛病；2.0.3 新增 ffmpeg 下载源可选
（官方 / `ghfast.top` 镜像，装的时候选、下载途中可换）；更早的版本带来了弹幕下载/封装、ffmpeg 自动安装、
默认保存到桌面，以及 Win11 风格图形界面（分集预览 + 序号输入 + 凭证状态区）。

## 合规声明

仅供个人学习与备份自己有权访问的内容。请遵守 B 站用户协议，不要二次传播受版权保护的内容，
也不要用于批量抓取。
