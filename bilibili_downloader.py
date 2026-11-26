#!/usr/bin/env python3
r"""
B 站视频 / 分P / 合集 下载器（DASH 分流下载 + ffmpeg 合并），Windows / macOS / Linux 同一份代码

依赖：
    pip install -r requirements.txt        # requests, tqdm
    另需 ffmpeg（合并音视频、导出 MP3、封装或烧录弹幕）：
        Windows      下载安装包时自带安装流程，或 bilibili_downloader --install-ffmpeg
        macOS        brew install ffmpeg
        Linux        sudo apt install ffmpeg  /  sudo dnf install ffmpeg

登录凭证（可选，决定画质上限：1080P+ / 4K / 8K / 无损音频）：
    读取顺序：① 环境变量 BILI_SESSDATA  ② 程序目录下的 sessdata.txt
              ③ 用户配置目录（Windows 注册表用户变量 / macOS、Linux 的
                 ~/.config/bilibili-downloader/sessdata）
    都没有时会**交互式询问一次**（输入不回显），校验通过后按当前系统的方式保存：
    Windows 写用户环境变量（并直查注册表，旧终端窗口也能读到），
    macOS / Linux 写用户配置文件（0600）。
    更换账号或凭证过期：加 --reset-sessdata 重新输入。
    手动设置：Windows  setx BILI_SESSDATA "..."     macOS / Linux  export BILI_SESSDATA=...
    获取方法：浏览器登录 B 站 → F12 → Application → Cookies → bilibili.com → 复制 SESSDATA
    ⚠️ SESSDATA 等同账号登录凭证：不要写进源码、不要提交仓库、不要发给别人。
       一旦怀疑泄露，立刻到 B 站「设置 → 安全隐私 → 退出所有设备」使旧凭证失效。

保存结构（默认保存到桌面，路径分隔符按系统走）：
    单视频      桌面/<视频标题>/<视频标题>.mp4 / .mp3
    多P视频     桌面/<视频标题>/P01 <分P标题>/P01 <分P标题>.mp4 / .mp3
    合集        桌面/<合集标题>/<视频标题>/<视频标题>.mp4 / .mp3
    合集内的多P 桌面/<合集标题>/<视频标题>/P01 <分P标题>/P01 <分P标题>.mp4
    弹幕        与视频同目录：<名字>.danmaku.xml（原始弹幕）/ <名字>.danmaku.ass（可直接挂载）

    把弹幕放进视频：--danmaku-video soft → <名字>.mkv（字幕轨，可开关）；hard → <名字>.mp4（烧进画面）

图形界面：
    不带参数运行（或加 --gui）打开图形界面，所有选项都在界面上，底部有「帮助」按钮。
    图形界面同一时间只允许一个实例；带参数的命令行调用不受此限制，可以并发跑。

用法：
    python bilibili_downloader.py                                   # 打开图形界面
    python bilibili_downloader.py BV1xx411c7mD
    python bilibili_downloader.py "https://www.bilibili.com/video/BV1xx411c7mD?p=2" --single
    python bilibili_downloader.py BV1xx411c7mD --dry-run          # 只看将要下载什么
    python bilibili_downloader.py BV1xx411c7mD -q 720p --no-mp3
    python bilibili_downloader.py BV1xx411c7mD -j 4                # 4 个文件同时下（默认）
    python bilibili_downloader.py BV1xx411c7mD -j 1                # 串行，显示实时进度条
    python bilibili_downloader.py BV1xx411c7mD --danmaku full --danmaku-video soft
    python bilibili_downloader.py --install-ffmpeg                 # 仅 Windows：装到 ~/ffmpeg 并加进 PATH
    python bilibili_downloader.py --install-ffmpeg --ffmpeg-source mirror   # 走 ghfast.top 镜像
      源可选 auto（默认，官方→镜像→gyan 依次回退）/ official / mirror
"""

from __future__ import annotations

import argparse
import base64
import getpass
import gzip
import hashlib
import html
import json
import os
import socket
import ssl
import struct
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
import zipfile
import zlib
from collections import deque
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, as_completed
from concurrent.futures import wait as futures_wait
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Callable, Iterable, Sequence

try:  # 依赖缺失时给出人话提示，而不是一堆 traceback
    import requests
    from requests.adapters import HTTPAdapter
    from tqdm import tqdm
    from urllib3.util.retry import Retry
except ImportError as exc:  # pragma: no cover
    sys.exit(f"缺少依赖：{exc}\n请先执行：pip install -r requirements.txt")

# ================= 常量 =================

API_VIEW = "https://api.bilibili.com/x/web-interface/view"
API_VIEW_WBI = "https://api.bilibili.com/x/web-interface/wbi/view"
API_PLAYURL = "https://api.bilibili.com/x/player/playurl"
API_PLAYURL_WBI = "https://api.bilibili.com/x/player/wbi/playurl"
API_NAV = "https://api.bilibili.com/x/web-interface/nav"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

APP_DIR = Path(__file__).resolve().parent

# ================= 平台 =================
#
# 三套系统共用一份逻辑，差异只在这里收口：字体名、图标格式、配置目录、
# 打开文件夹的方式、单实例锁。别的地方一律只问 IS_WIN / IS_MAC / IS_LINUX，
# 不要再散落 os.name == "nt" 的临时判断——那种判断漏掉一处，就是"Windows 修好了、
# 换个系统又坏"的老毛病。

IS_WIN = os.name == "nt"
IS_MAC = sys.platform == "darwin"
IS_LINUX = not IS_WIN and not IS_MAC
PLATFORM_NAME = "Windows" if IS_WIN else ("macOS" if IS_MAC else "Linux")

# 中文字体：三套系统各有各的默认字体名，写死一个在别的系统上会退回点阵字体
GUI_FONT_FAMILY = (
    "Microsoft YaHei UI" if IS_WIN else ("PingFang SC" if IS_MAC else "Noto Sans CJK SC")
)
MONO_FONT_FAMILY = "Consolas" if IS_WIN else ("Menlo" if IS_MAC else "DejaVu Sans Mono")
GUI_FONT_FALLBACK = "Arial" if IS_WIN else ("Helvetica Neue" if IS_MAC else "DejaVu Sans")


def user_config_dir() -> Path:
    """用户配置目录：Windows 用 %APPDATA%，macOS / Linux 用 ~/.config。

    程序目录在 Program Files / /usr 下通常不可写，配置和凭证都得落到这里，
    否则预约任务、直播设置会在下次启动时静默丢失。
    """
    if IS_WIN:
        base = os.environ.get("APPDATA") or str(Path.home())
        return Path(base) / "bilibili-downloader"
    return Path.home() / ".config" / "bilibili-downloader"


def app_icon_path() -> Path | None:
    """程序图标：Windows 用 .ico（Tk 与 Shell 都认），macOS / Linux 用 .png。

    源码运行时在仓库 assets/ 里，打包后跟着 exe / app 放在一起。
    """
    names = ("app.ico", "app.png") if IS_WIN else ("app.png", "app.ico")
    for base in (APP_DIR, Path(sys.argv[0]).resolve().parent):
        for name in names:
            icon = base / "assets" / name
            if icon.is_file():
                return icon
    return None


_icon_cache: dict[int, object] = {}


def apply_window_icon(win) -> None:
    """给窗口换图标。

    Windows 走 iconbitmap(.ico)；macOS / Linux 的 Tk 不认 .ico，必须用
    iconphoto + PhotoImage(.png)。PhotoImage 会被 GC 回收导致图标消失，
    所以挂在窗口对象上留一份引用。图标缺失或 Tk 不支持时静默跳过。
    """
    icon = app_icon_path()
    if icon is None:
        return
    try:
        if IS_WIN:
            win.iconbitmap(str(icon))
            return
        import tkinter as tk

        key = id(win)
        photo = _icon_cache.get(key)
        if photo is None:
            photo = tk.PhotoImage(file=str(icon))
            _icon_cache[key] = photo
        win.iconphoto(True, photo)
        win._bd_icon = photo                    # 防 GC
    except Exception:
        pass


def app_hicon(size: int = 0) -> int:
    """把 assets/app.ico 载成 HICON（仅 Windows 托盘用）。

    托盘的隐藏窗口类和 Shell_NotifyIcon 的 hIcon 都不走 Tk，必须自己载；
    size=0 表示按当前 DPI 取小图标尺寸。其他系统没有这个概念，返回 0。
    """
    if not IS_WIN:
        return 0
    if size in _hicon_cache:
        return _hicon_cache[size]
    hicon = 0
    icon = app_icon_path()
    if icon is not None:
        try:
            import ctypes
            from ctypes import wintypes

            user32 = ctypes.windll.user32
            user32.LoadImageW.restype = wintypes.HICON
            user32.LoadImageW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR,
                                          wintypes.UINT, ctypes.c_int, ctypes.c_int,
                                          wintypes.UINT]
            px = size or user32.GetSystemMetrics(49)      # SM_CXSMICON
            hicon = int(user32.LoadImageW(None, str(icon), 1, px, px, 0x10) or 0)
        except Exception:
            hicon = 0
    _hicon_cache[size] = hicon
    return hicon


_hicon_cache: dict[int, int] = {}


def open_path(path) -> None:
    """用系统默认程序打开文件或文件夹（三平台统一入口）。"""
    target = str(path)
    if IS_WIN:
        os.startfile(target)                     # type: ignore[attr-defined]
    elif IS_MAC:
        subprocess.Popen(["open", target])
    else:
        subprocess.Popen(["xdg-open", target])


def _single_instance_handle():
    """跨平台单实例锁：拿到锁返回句柄，已有实例在跑返回 None。

    Windows 用命名互斥体（Local\\ 作用域，只在本登录会话内互斥）；
    macOS / Linux 用 flock 锁一个用户配置目录下的文件——进程退出时系统自动释放，
    不会留下"上次崩溃了所以永远打不开"的死锁。
    """
    try:
        if IS_WIN:
            import ctypes
            from ctypes import wintypes

            # 必须 use_last_error=True：windll 不保证 GetLastError 是本次调用的结果，
            # 读到上一条无关错误就会出现"明明没人开却提示已经在运行"。
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.CreateMutexW.restype = wintypes.HANDLE
            kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
            handle = kernel32.CreateMutexW(None, False, "Local\\BilibiliDownloaderGui")
            if not handle:
                return object()                  # 拿不到互斥体就别拦住用户
            # ERROR_ALREADY_EXISTS = 183：说明别的进程已经创建并持有它
            if ctypes.get_last_error() == 183:
                kernel32.CloseHandle(handle)
                return None
            return handle

        import fcntl

        path = user_config_dir() / "gui.lock"
        path.parent.mkdir(parents=True, exist_ok=True)
        handle = open(path, "a+")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            handle.close()
            return None
        return handle
    except Exception:
        return object()                          # 锁不可用时宁可放行，也不要打不开界面


def _focus_existing_window(title: str) -> bool:
    """已经有一个界面实例时，尽力把它拉到前台（Windows 能精确找窗口，其他系统只提示）。"""
    if not IS_WIN:
        return False
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        hwnd = user32.FindWindowW(None, title)
        if not hwnd:
            return False
        user32.ShowWindow(hwnd, 9)               # SW_RESTORE
        user32.SetForegroundWindow(hwnd)
        return True
    except Exception:
        return False

# WBI 签名用的混淆表（来自 B 站 web 端实现，顺序不可改）
MIXIN_KEY_ENC_TAB = (
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49,
    33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40,
    61, 26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62,
    11, 36, 20, 34, 44, 52,
)

# 画质 id（B 站返回值）→ 人话
QUALITY_NAMES = {
    127: "8K 超高清", 126: "杜比视界", 125: "HDR 真彩", 120: "4K 超清",
    116: "1080P60", 112: "1080P+", 80: "1080P 高清", 74: "720P60",
    64: "720P 高清", 32: "480P 清晰", 16: "360P 流畅",
}

# --quality 可选值 → 允许的最高画质 id
QUALITY_LIMITS = {
    "max": 127, "8k": 127, "4k": 120, "1080p60": 116, "1080p+": 112,
    "1080p": 80, "720p60": 74, "720p": 64, "480p": 32, "360p": 16,
}

# DASH 音频流 id：30251 = Hi-Res 无损，30250 = 杜比全景声
AUDIO_LOSSLESS_IDS = {30251}

WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}

CHUNK_SIZE = 256 * 1024
NAME_LIMIT = 60          # 单个目录/文件名最长字符数

# ---- 慢速连接检测：速度掉到"自身历史平均"的 30% 以下并持续 10 秒 → 丢掉连接、重开一条续传 ----
SLOW_CHECK_INTERVAL = 0.5          # 采样/判定的间隔（秒）
SLOW_CUR_WINDOW = 6.0              # "当前速度"的统计窗口（秒）
SLOW_REF_LAG = 10.0                # 参考速度 = 从开始到（此刻 - 该值）的平均速度
SLOW_RATIO = 0.30                  # 当前速度低于参考速度的该比例即视为变慢
SLOW_HOLD = 10.0                   # 变慢需持续这么久才动手
SLOW_MIN_ELAPSED = 20.0            # 至少已下载这么久才开始判定（参考滞后 + 持续时长）
SLOW_MIN_REF = 256 * 1024          # 参考速度低于此值说明本来就慢，重连也没意义
SLOW_MIN_ETA = 10.0                # 预计剩余时间小于该值（秒）就继续下，别重连
DEFAULT_MAX_RECONNECTS = 5         # 单个流最多因"变慢"重开几次连接
PATH_LIMIT = 235 if IS_WIN else 3800   # Windows MAX_PATH 留余量；POSIX 整条路径上限约 4096
PART_SUFFIX = ".part"

ENV_NAME = "BILI_SESSDATA"

# ---- 弹幕 ----
# 两个地址都返回同一份 XML：comment.bilibili.com 更快，api 版作为备用。
# 分段 protobuf 接口（x/v2/dm/web/seg.so）实测返回的条数反而更少（游客只拿到一小部分），
# 所以这里只用 XML，一次请求拿到该稿件当前可见的全部弹幕。
DANMAKU_XML_URLS = (
    "https://comment.bilibili.com/{cid}.xml",
    "https://api.bilibili.com/x/v1/dm/list.so?oid={cid}",
)
DANMAKU_LIGHT_MAX_CHARS = 60      # 精简：超长弹幕截断到这个长度
DANMAKU_LIGHT_PER_SECOND = 6      # 精简：每秒最多保留几条，避免满屏
DANMAKU_LIGHT_DEDUPE_WINDOW = 5.0 # 精简：同一句话在该窗口内只留一次
DANMAKU_SCROLL_SECONDS = 8.0      # 滚动弹幕横穿屏幕的时间
DANMAKU_FIXED_SECONDS = 5.0       # 顶部/底部弹幕停留时间

# ---- ffmpeg 自动安装（只用于 Windows）----
FFMPEG_ZIP_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
FFMPEG_RELEASE_API = "https://api.github.com/repos/GyanD/codexffmpeg/releases/latest"
FFMPEG_MIRROR_PREFIX = "https://ghfast.top/"   # GitHub 加速镜像（国内实测最快）
FFMPEG_FALLBACK_MB = 114          # 查不到远端大小时的兜底提示值（essentials 约 114 MB）
FFMPEG_SOURCES = ("auto", "official", "mirror")
FFMPEG_SOURCE = "auto"            # 由 --ffmpeg-source / GUI 设置；auto = 官方 → 镜像 → gyan.dev


def _app_dir() -> Path:
    """程序所在目录：源码运行时是脚本目录，打包成 exe 后是 exe 所在目录。

    单文件打包（Nuitka onefile / PyInstaller）会把 __file__ 指向每次运行都不同的
    临时解包目录，如果直接拿它拼 sessdata.txt，用户放在 exe 旁边的凭证文件永远读不到。
    """
    if getattr(sys, "frozen", False) or "__compiled__" in globals():
        try:
            return Path(sys.argv[0]).resolve().parent
        except OSError:
            pass
    return Path(__file__).resolve().parent


def desktop_dir() -> Path:
    """用户桌面目录。

    Windows 上不能直接写 ~/Desktop：开了 OneDrive 备份的机器，桌面被挪走，
    下载完用户在自己的桌面上根本看不到。macOS / Linux 直接按 XDG 习惯找，
    找不到就退回主目录。
    """
    if IS_WIN:
        try:
            import winreg

            key = r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as handle:
                value, _ = winreg.QueryValueEx(handle, "Desktop")
            resolved = Path(os.path.expandvars(str(value)))
            if resolved.is_dir():
                return resolved
        except OSError:
            pass
    desktop = Path.home() / "Desktop"
    return desktop if desktop.is_dir() else Path.home()


def default_output() -> Path:
    """默认保存根目录：桌面。"""
    return desktop_dir()


SESSDATA_FILE = _app_dir() / "sessdata.txt"
SESSDATA_HOME_FILE = user_config_dir() / "sessdata"


class DownloadError(RuntimeError):
    """本项目所有可预期的错误（网络、接口、ffmpeg、文件系统）。"""


class Aborted(Exception):
    """用户中断（Ctrl+C）：下载线程看到它就地收手，不计入失败。"""


class SlowConnection(RuntimeError):
    """连接速度长期远低于自身历史平均：应当丢掉这条连接、重开一条续传。"""


# 中断标志：Ctrl+C 时置位，下载循环每收到一块数据就检查一次，因此能秒级停下
_ABORT = threading.Event()

# GUI 注册的选择回调：有它时代替终端里的 input()（主线程弹窗，工作线程等结果）
_SELECTION_CALLBACK: Callable[[int, Sequence["Item"]], list[int] | None] | None = None

# 单实例锁句柄：必须活到进程退出（局部变量被回收时锁就没了）
_INSTANCE_HANDLE: list[object] = []

# 接口调用串行化 + 最小间隔，避免多线程同时打接口触发风控
_API_LOCK = threading.Lock()
_API_MIN_INTERVAL = 0.5
_last_api_call = 0.0


def _throttle_api() -> None:
    global _last_api_call
    with _API_LOCK:
        wait = _API_MIN_INTERVAL - (time.time() - _last_api_call)
        if wait > 0:
            time.sleep(wait)
        _last_api_call = time.time()


def request_abort() -> None:
    """请求停止下载（Ctrl+C 时由主线程调用）。"""
    _ABORT.set()


def _abortable_sleep(seconds: float) -> None:
    """可被 Ctrl+C 立即打断的等待：_ABORT 一旦置位就马上返回（而不是傻等）。"""
    if _ABORT.wait(seconds):
        raise Aborted("已取消")


def _hard_exit(code: int) -> None:
    """立即结束进程，不再等待下载线程。

    被打断时工作线程可能正卡在 socket 读、重试退避或 ffmpeg 上；如果等它们收尾，
    Ctrl+C 就会变成几秒到几十秒的"没反应"。下载产物都是 .part + 可续传的，
    直接退出是安全的（下次运行会接着下）。测试里会替换这个函数。
    """
    try:
        sys.stdout.flush()
        sys.stderr.flush()
    except Exception:
        pass
    os._exit(code)


# ---- 多线程进度条：每个下载线程固定占用一条进度条（position），4 线程 = 4 条 ----
_SLOT_LOCK = threading.Lock()
_SLOT_COUNTER = 0
_SLOT_LOCAL = threading.local()
_bars_active = threading.Event()


def _reset_progress() -> None:
    global _SLOT_COUNTER
    _SLOT_COUNTER = 0
    _bars_active.clear()


def _claim_bar_slot() -> int:
    """给当前线程分配固定的进度条位置：同线程复用，不同线程互不冲突。"""
    global _SLOT_COUNTER
    slot = getattr(_SLOT_LOCAL, "slot", None)
    if slot is None:
        with _SLOT_LOCK:
            slot = _SLOT_COUNTER
            _SLOT_COUNTER += 1
        _SLOT_LOCAL.slot = slot
    return slot


def emit(message: str = "", *, err: bool = False) -> None:
    """统一输出。

    进度条激活时必须走 tqdm.write：它会先清掉自己那几行、写完再重画，
    否则普通 print 会把进度条踩花。
    """
    stream = sys.stderr if err else sys.stdout
    if _bars_active.is_set():
        tqdm.write(message, file=stream)
    else:
        print(message, file=stream)


# ================= 小工具 =================


def _setup_console() -> None:
    """Windows 控制台默认 GBK：遇到装不下的字符降级替换，别让脚本崩掉。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")  # type: ignore[union-attr]
        except (AttributeError, ValueError, OSError):
            pass


def clean_name(name: str, limit: int = NAME_LIMIT) -> str:
    """清洗成合法文件名。

    Windows 的非法字符集合是 `\\ / : * ? " < > |` 加控制字符，还额外禁掉
    CON/PRN 这类设备名；macOS / Linux 只禁 `/` 和 NUL（冒号在 HFS+ 上曾经
    有问题，现在也一并换掉，省得同一个视频在两个系统上名字不一样）。
    """
    if IS_WIN:
        name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", str(name))
    else:
        name = re.sub(r"[/:\x00-\x1f]", "_", str(name))
    name = re.sub(r"\s+", " ", name).strip(" .")
    if len(name) > limit:
        name = name[:limit].rstrip(" .")
    if not name:
        return "untitled"
    if IS_WIN and name.split(".")[0].upper() in WINDOWS_RESERVED:
        name = "_" + name
    return name


def fit_path(path: Path, limit: int = PATH_LIMIT) -> Path:
    """整条路径过长时，从最深的组件开始缩短（补短哈希防重名）。

    Windows 是 MAX_PATH 260 的硬限制；macOS / Linux 单条路径能到 4096、
    单个组件 255 字节，正常不会触发，这个函数在那边基本是直通。
    """
    if len(str(path)) <= limit:
        return path

    parts = list(path.parts)
    suffix = path.suffix
    for index in range(len(parts) - 1, 0, -1):        # 不动盘符/根目录
        over = len(str(Path(*parts))) - limit
        if over <= 0:
            break
        piece = parts[index]
        digest = hashlib.md5(piece.encode("utf-8")).hexdigest()[:6]
        if index == len(parts) - 1 and suffix:
            base = piece[: -len(suffix)]
            candidate = f"{base[:max(6, len(base) - over - 7)]}_{digest}{suffix}"
        else:
            candidate = f"{piece[:max(4, len(piece) - over - 7)]}_{digest}"
        if len(candidate) < len(piece):               # 只接受确实变短的
            parts[index] = candidate
    return Path(*parts)


def host_of(url: str) -> str:
    try:
        return urllib.parse.urlparse(url).netloc or url
    except ValueError:
        return url


def human_size(num: int) -> str:
    value = float(num)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"


def _clip(text: str, limit: int) -> str:
    """截断过长的显示文本（进度条描述等），避免撑爆行宽。"""
    text = str(text)
    if len(text) <= limit:
        return text
    if limit <= 1:
        return "…"[: max(0, limit)]
    return text[: limit - 1] + "…"


_NESTED_ERROR = re.compile(r"(\w*Error)\((-?\d+),\s*'([^']*)'")


def short_error(exc: BaseException, limit: int = 150) -> str:
    """把异常压成一行可读文本。

    requests 的网络异常常把嵌套异常塞进 args，例如
    "Connection broken: ConnectionResetError(10054, '远程主机强迫关闭了一个现有的连接。', None, 10054, None)"，
    这里收拾成"远程主机强迫关闭了一个现有的连接。（ConnectionResetError 10054）"。
    """
    args = getattr(exc, "args", None) or ()
    text = str(args[0]) if args and str(args[0]).strip() else str(exc)
    text = " ".join(text.split())

    nested = _NESTED_ERROR.search(text)
    if nested:
        text = f"{nested.group(3)}（{nested.group(1)} {nested.group(2)}）"

    if not text:
        text = type(exc).__name__
    if len(text) > limit:
        text = text[: limit - 1] + "…"
    return text


# ================= HTTP 会话 =================


def build_headers(sessdata: str = "") -> dict:
    headers = {
        "User-Agent": USER_AGENT,
        "Referer": "https://www.bilibili.com/",
        "Origin": "https://www.bilibili.com",
        "Accept-Language": "zh-CN,zh;q=0.9",
    }
    if sessdata:
        headers["Cookie"] = f"SESSDATA={sessdata}"
    return headers


def build_session() -> requests.Session:
    """带自动重试的会话（对 429/5xx 指数退避）。"""
    session = requests.Session()
    retry = Retry(
        total=3, connect=3, read=3, backoff_factor=0.6,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET", "HEAD"}),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_maxsize=16)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


# ================= SESSDATA 凭证 =================


_sessdata_origin = ""


def _windows_user_env(name: str | None = None) -> str:
    """直接读注册表里的「用户环境变量」。

    已经打开的终端、常驻服务进程持有的是启动时的环境副本，os.environ 里可能
    读不到刚设置的变量（Windows 只在进程启动时注入环境变量），所以这里直查注册表兜底。
    """
    if not IS_WIN:
        return ""
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            value, _ = winreg.QueryValueEx(key, name or ENV_NAME)
        return str(value).strip()
    except OSError:
        return ""


def sessdata_origin() -> str:
    """最近一次 load_sessdata() 命中的来源（用于日志）。"""
    return _sessdata_origin


def load_sessdata() -> str:
    """按「进程环境变量 → 用户环境变量(注册表) → sessdata.txt → 用户配置」读取凭证。"""
    global _sessdata_origin

    value = os.environ.get(ENV_NAME, "").strip()
    if value:
        _sessdata_origin = "环境变量"
        return value

    value = _windows_user_env()
    if value:
        _sessdata_origin = "用户环境变量"
        return value

    for path in (SESSDATA_FILE, SESSDATA_HOME_FILE):
        try:
            if path.is_file():
                found = path.read_text(encoding="utf-8").strip()
                if found:
                    _sessdata_origin = f"凭证文件 {path.name}"
                    return found
        except OSError:
            continue

    _sessdata_origin = ""
    return ""


def _vip_label_text(raw) -> str:
    """取会员标签的可读文字。

    老版 nav 接口的 vip_label 是字符串；新版是对象（含 text / img_label_uri_* 等字段）。
    这里统一取文字，避免把整个对象打印给用户。
    """
    if isinstance(raw, dict):
        raw = raw.get("text")
    return str(raw or "").strip()


def probe_account(session: requests.Session, headers: dict, timeout: float) -> dict:
    """查询凭证的登录/会员状态。

    返回 {"login": bool, "vip": bool, "vip_label": str}；
    网络异常或接口不可用时返回空字典（表示"无法判断"，不要当成未登录）。
    """
    try:
        resp = session.get(API_NAV, headers=headers, timeout=timeout)
        data = (resp.json() or {}).get("data") or {}
    except Exception:
        return {}
    if not data:                     # 响应体异常时不要误判成"未登录"
        return {}
    return {
        "login": bool(data.get("isLogin")),
        "vip": bool(data.get("vipStatus") or data.get("vipType")),
        "vip_label": _vip_label_text(data.get("vip_label")),
    }


def check_sessdata(session: requests.Session, headers: dict,
                   timeout: float) -> bool | None:
    """用 nav 接口校验凭证：True/False 为校验结果，None 表示无法判断（网络问题）。"""
    info = probe_account(session, headers, timeout)
    return None if not info else bool(info["login"])


def _broadcast_env_change() -> None:
    """best-effort：通知资源管理器环境变量已变更。"""
    if not IS_WIN:
        return
    try:
        import ctypes

        ctypes.windll.user32.SendMessageTimeoutW(
            0xFFFF, 0x001A, 0, "Environment", 0x0002, 5000, None
        )
    except Exception:
        pass


def save_sessdata(value: str) -> str:
    """持久化凭证，返回给用户看的说明。

    Windows：写入用户环境变量（REG_SZ，不会被 % 展开）；
    其他系统：写入 ~/.config/bilibili-downloader/sessdata（权限 600）。
    """
    value = (value or "").strip()
    if not value:
        return "未保存（空值）"

    if IS_WIN:
        try:
            import winreg

            with winreg.CreateKeyEx(
                winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_SET_VALUE
            ) as key:
                winreg.SetValueEx(key, ENV_NAME, 0, winreg.REG_SZ, value)
            _broadcast_env_change()
            os.environ[ENV_NAME] = value          # 让当前进程也立刻一致
            return f"Windows 用户环境变量 {ENV_NAME}"
        except OSError as exc:
            return f"写入环境变量失败（{exc}）"

    try:
        SESSDATA_HOME_FILE.parent.mkdir(parents=True, exist_ok=True)
        SESSDATA_HOME_FILE.write_text(value, encoding="utf-8")
        SESSDATA_HOME_FILE.chmod(0o600)
        return str(SESSDATA_HOME_FILE)
    except OSError as exc:
        return f"写入配置文件失败（{exc}）"


def prompt_sessdata(session: requests.Session, timeout: float, *,
                    expired: bool = False) -> str:
    """交互式询问 SESSDATA（不回显），校验后保存；留空表示使用游客模式。

    expired=True 用于「已有凭证但校验失效」的场景：只给一行极简提示，不重复新手教程。
    """
    if expired:
        label = "粘贴新的 SESSDATA（留空跳过，用游客模式）："
    else:
        print("\n未检测到 SESSDATA，进入凭证设置：")
        print("  · 无凭证只能拿到较低画质（一般 480P/720P），也没有无损音频。")
        print("  · 获取方法：浏览器登录 B 站 → F12 → Application → Cookies")
        print("              → 选中 https://www.bilibili.com → 复制名为 SESSDATA 的值")
        print("  · 输入不会回显（粘贴后直接回车）；它只保存在本机，请勿外传。")
        label = "SESSDATA（留空跳过）："

    try:
        value = getpass.getpass(label).strip()
    except Exception:
        # getpass 在非终端上可能直接抛异常（它优先打开 /dev/tty）；退回普通 input
        try:
            value = input(label).strip()
        except EOFError:
            print("\n（当前没有可用的输入来源，改用游客模式）")
            return ""

    if not value:
        print("已跳过，使用游客模式。\n")
        return ""

    info = probe_account(session, build_headers(value), timeout)
    if info.get("login"):
        print(f"[OK] 凭证校验通过（{'大会员' if info.get('vip') else '普通账号'}）")
    elif info:
        print("[!] 校验显示未登录：可能已过期或复制不完整；仍会保存，"
              "之后可用 --reset-sessdata 重设")
    else:
        print("（无法联网校验，按原样保存）")

    where = save_sessdata(value)
    print(f"已保存到：{where}（下次运行自动读取）")
    print()
    return value


def _is_interactive(args: argparse.Namespace) -> bool:
    """只有真正的交互式终端才提问：输出被重定向、或加了 -y/--yes，都不问。"""
    if getattr(args, "yes", False):
        return False
    try:
        return bool(sys.stdin.isatty() and sys.stdout.isatty())
    except (AttributeError, ValueError):
        return False


def ensure_credential(session: requests.Session,
                      args: argparse.Namespace) -> tuple[str, dict]:
    """拿到可用凭证：读取 → 校验 → 失效则明确告警并可直接重输。返回 (sessdata, headers)。"""
    sessdata = "" if args.reset_sessdata else load_sessdata()

    if sessdata:
        print(f"[凭证] 已从{sessdata_origin()}读取 SESSDATA")
        info = probe_account(session, build_headers(sessdata), args.timeout)
        if info.get("login"):
            role = info.get("vip_label") or ("大会员" if info.get("vip") else "普通账号")
            print(f"[凭证] 校验通过（{role}）")
        elif info:
            if _is_interactive(args):
                print("[!] 凭证已失效：现在只能以游客身份下载，一般最高 480P/360P。")
                try:
                    answer = input("现在重新输入 SESSDATA？[Y/n] ").strip().lower()
                except EOFError:
                    answer = "n"
                if answer not in {"n", "no"}:
                    sessdata = prompt_sessdata(session, args.timeout, expired=True)
            else:
                print("[!] 凭证已失效（接口返回未登录）：现在只能以游客身份下载，"
                      "一般最高 480P/360P，也没有无损音频。")
                print("    换新凭证：加 --reset-sessdata 重新输入，或在浏览器重新登录后重跑。")
        else:
            print("[凭证] 网络不可用，跳过校验")

    if not sessdata:
        # 非交互场景（-y、输出被重定向、CI/批处理）绝不能在这里提问：
        # getpass 会直接打开 /dev/tty，重定向 stdin 也拦不住，进程会永久挂住。
        if _is_interactive(args):
            sessdata = prompt_sessdata(session, args.timeout)
        else:
            print("[提示] 未检测到 SESSDATA；当前是非交互模式（-y 或输出被重定向），"
                  "不提问，直接以游客身份下载（通常最高 480P/720P，也没有无损音频）。")
            print("    想要更高画质：先设好凭证（环境变量 BILI_SESSDATA，"
                  "或程序目录下的 sessdata.txt）再重跑。")

    headers = build_headers(sessdata)
    if not sessdata:
        print("[提示] 游客模式：通常最高 480P/720P，且拿不到无损音频。")
    return sessdata, headers


# ================= WBI 签名 =================

_mixin_key_cache: dict = {"key": "", "at": 0.0}


def derive_mixin_key(img_key: str, sub_key: str) -> str:
    """按混淆表从 img_key+sub_key 推出 32 位 mixin_key。"""
    merged = img_key + sub_key
    return "".join(merged[i] for i in MIXIN_KEY_ENC_TAB if i < len(merged))[:32]


def _url_stem(url: str) -> str:
    tail = url.rsplit("/", 1)[-1]
    return tail.split(".")[0]


def fetch_mixin_key(session: requests.Session, headers: dict, timeout: float,
                    force: bool = False) -> str:
    """从 nav 接口取 wbi 密钥（未登录也会返回，因此不看 code）。"""
    now = time.time()
    if not force and _mixin_key_cache["key"] and now - _mixin_key_cache["at"] < 1800:
        return _mixin_key_cache["key"]
    resp = session.get(API_NAV, headers=headers, timeout=timeout)
    resp.raise_for_status()
    data = (resp.json() or {}).get("data") or {}
    wbi = data.get("wbi_img") or {}
    img_url, sub_url = wbi.get("img_url") or "", wbi.get("sub_url") or ""
    if not img_url or not sub_url:
        raise DownloadError("无法获取 WBI 签名密钥（nav 接口未返回 wbi_img）")
    key = derive_mixin_key(_url_stem(img_url), _url_stem(sub_url))
    _mixin_key_cache.update(key=key, at=now)
    return key


def wbi_query(params: dict, mixin_key: str, wts: int | None = None) -> str:
    """拼出带 wts 与 w_rid 的查询串（w_rid = md5(查询串 + mixin_key)）。"""
    clean = {
        k: "".join(ch for ch in str(v) if ch not in "!'()*")
        for k, v in params.items()
    }
    query = "&".join(
        f"{urllib.parse.quote(k, safe='')}={urllib.parse.quote(v, safe='')}"
        for k, v in sorted(clean.items())
    )
    stamp = int(time.time() if wts is None else wts)
    query = f"{query}&wts={stamp}" if query else f"wts={stamp}"
    digest = hashlib.md5(f"{query}{mixin_key}".encode()).hexdigest()
    return f"{query}&w_rid={digest}"


# ================= B 站 API =================


def api_get(session: requests.Session, api: str, params: dict, headers: dict,
            timeout: float, mixin_key: str | None = None) -> dict:
    """调用接口并返回 data；业务错误码统一抛 DownloadError。"""
    if mixin_key:
        url = f"{api}?{wbi_query(params, mixin_key)}"
        resp = session.get(url, headers=headers, timeout=timeout)
    else:
        resp = session.get(api, params=params, headers=headers, timeout=timeout)
    resp.raise_for_status()
    payload = resp.json() or {}
    code = payload.get("code", 0)
    if code != 0:
        raise DownloadError(f"{payload.get('message') or '接口返回错误'}（code={code}）")
    return payload.get("data") or {}


def fetch_view(session: requests.Session, headers: dict, timeout: float,
               bvid: str | None = None, aid: int | None = None) -> dict:
    """取视频详细信息（含 pages 分P / ugc_season 合集）。"""
    params = {"bvid": bvid} if bvid else {"aid": aid}
    return api_get(session, API_VIEW, params, headers, timeout)


def fetch_streams(session: requests.Session, headers: dict, timeout: float,
                  bvid: str, cid: int) -> dict:
    """取 DASH 流地址：优先带 WBI 签名的接口，失败回退旧接口。"""
    params = {
        "bvid": bvid, "cid": cid,
        "qn": 127,        # 请求最高画质（实际以返回为准）
        "fnver": 0,
        "fnval": 4048,    # 一次要齐 DASH/4K/HDR/8K/杜比 等全部特性
        "fourk": 1,
    }
    try:
        key = fetch_mixin_key(session, headers, timeout)
        data = api_get(session, API_PLAYURL_WBI, params, headers, timeout, mixin_key=key)
    except DownloadError as exc:
        emit(f"[重试] WBI 签名接口未成功（{short_error(exc)}），改用旧接口重试")
        data = api_get(session, API_PLAYURL, params, headers, timeout)
    dash = data.get("dash")
    if not dash:
        raise DownloadError("该视频没有 DASH 流（可能是番剧/老视频，或需要登录）")
    return dash


def resolve_input(session: requests.Session, headers: dict, timeout: float,
                  raw: str) -> tuple[str, int | None]:
    """把任意输入（链接 / BV 号 / av 号 / b23.tv 短链）解析成 (bvid, 分P序号)。"""
    text = (raw or "").strip()
    if not text:
        raise DownloadError("输入为空")

    page = None
    m = re.search(r"[?&]p=(\d+)", text)
    if m:
        page = max(1, int(m.group(1)))

    m = re.search(r"(BV[0-9A-Za-z]{10})", text)
    if m:
        return m.group(1), page

    m = re.fullmatch(r"av(\d+)", text, re.IGNORECASE)
    if m:
        data = fetch_view(session, headers, timeout, aid=int(m.group(1)))
        return data.get("bvid") or "", page

    if text.lower().startswith(("http://", "https://")):
        resp = session.get(text, headers=headers, timeout=timeout, allow_redirects=True)
        for candidate in (resp.url or "", (resp.text or "")[:200000]):
            m = re.search(r"(BV[0-9A-Za-z]{10})", candidate)
            if m:
                return m.group(1), page

    raise DownloadError(f"无法识别的输入：{raw}")


# ================= 下载计划 =================


@dataclass
class Item:
    """一个最小下载单位：某个视频的某一个分P（或单P视频本身）。"""

    bvid: str
    cid: int
    label: str            # 显示与命名用（已清洗）
    out_dir: Path         # 成品所在目录
    quality_hint: str = ""
    aid: int = 0          # 分段弹幕接口要 pid，这里预留（XML 接口只用 cid）
    duration: int = 0     # 秒；用于报告与后续可能的按段取弹幕

    @property
    def mp4(self) -> Path:
        return fit_path(self.out_dir / f"{self.label}.mp4")

    @property
    def mp3(self) -> Path:
        return fit_path(self.out_dir / f"{self.label}.mp3")

    @property
    def mkv(self) -> Path:
        """弹幕做成软字幕时的成品（ASS 字幕轨只有 MKV 能完整承载）。"""
        return fit_path(self.out_dir / f"{self.label}.mkv")

    @property
    def danmaku_xml(self) -> Path:
        return fit_path(self.out_dir / f"{self.label}.danmaku.xml")

    @property
    def danmaku_ass(self) -> Path:
        return fit_path(self.out_dir / f"{self.label}.danmaku.ass")

    @property
    def video_m4s(self) -> Path:
        return self.out_dir / f"{self.label}.video.m4s"

    @property
    def audio_m4s(self) -> Path:
        return self.out_dir / f"{self.label}.audio.m4s"


def _pages_of(entry: dict) -> list[dict]:
    return [p for p in (entry.get("pages") or []) if p.get("cid")]


def build_plan(session: requests.Session, headers: dict, inputs: Sequence[str], *,
               root: Path, single: bool = False, timeout: float = 15.0,
               log: Callable[[str], None] = print) -> list[Item]:
    """把输入链接展开成下载清单（自动展开合集 / 多P）。"""
    items: list[Item] = []
    seen: set[tuple[str, int]] = set()

    def add(bvid: str, cid: int, label: str, out_dir: Path,
            aid: int = 0, duration: int = 0) -> None:
        if not bvid or not cid:
            return
        if (bvid, cid) in seen:
            return
        seen.add((bvid, cid))
        items.append(Item(bvid=bvid, cid=cid, label=label, out_dir=out_dir,
                          aid=int(aid or 0), duration=int(duration or 0)))

    for raw in inputs:
        bvid, page = resolve_input(session, headers, timeout, raw)
        if not bvid:
            raise DownloadError(f"{raw}：没有解析出 BV 号")
        data = fetch_view(session, headers, timeout, bvid=bvid)

        if data.get("redirect_url"):
            raise DownloadError(
                f"{bvid} 是番剧/影视内容（{data.get('redirect_url')}），"
                "本工具只支持普通投稿（UGC）"
            )

        title = clean_name(data.get("title") or bvid)
        pages = _pages_of(data)
        season = data.get("ugc_season")

        # ---- 合集：bili_downloads\<合集名>\<视频名>\... ----
        if season and not single:
            season_title = clean_name(season.get("title") or "合集")
            if season.get("is_pay_season"):
                raise DownloadError(f"《{season_title}》是付费合集，无法下载")
            episodes: list[dict] = []
            for section in season.get("sections") or []:
                episodes.extend(section.get("episodes") or section.get("archives") or [])
            log(f"  合集《{season_title}》：{len(episodes)} 个视频")
            for ep in episodes:
                ep_bvid = ep.get("bvid") or ""
                ep_pages = _pages_of(ep)
                ep_aid = int(ep.get("aid") or (ep.get("arc") or {}).get("aid") or 0)
                ep_title = clean_name(
                    ep.get("title") or (ep.get("arc") or {}).get("title") or ep_bvid
                )
                if len(ep_pages) > 1:
                    for p in ep_pages:
                        label = clean_name(f"P{int(p.get('page', 1)):02d} {p.get('part') or ''}")
                        add(ep_bvid, int(p["cid"]), label,
                            root / season_title / ep_title / label,
                            ep_aid, p.get("duration") or 0)
                else:
                    cid = int(ep.get("cid") or (ep_pages[0]["cid"] if ep_pages else 0))
                    duration = ep.get("duration") or (ep_pages[0].get("duration") if ep_pages else 0)
                    add(ep_bvid, cid, ep_title, root / season_title / ep_title,
                        ep_aid, duration or 0)
            continue

        # ---- 多P：bili_downloads\<视频标题>\<Pxx 分P标题>\... ----
        if len(pages) > 1:
            selected = pages
            if single and page and page <= len(pages):
                selected = [pages[page - 1]]
            for p in selected:
                label = clean_name(f"P{int(p.get('page', 1)):02d} {p.get('part') or ''}")
                add(bvid, int(p["cid"]), label, root / title / label,
                    data.get("aid") or 0, p.get("duration") or 0)
            continue

        # ---- 单视频：bili_downloads\<视频标题>\<视频标题>.mp4 ----
        if single and page and page > 1 and not pages:
            raise DownloadError(f"{bvid}：该视频没有第 {page} 个分P")
        cid = int(pages[0]["cid"]) if pages else int(data.get("cid") or 0)
        if not cid:
            raise DownloadError(f"{bvid}：接口没有返回 cid，无法下载")
        label = title if not (single and page) else clean_name(f"P{page:02d} {title}")
        add(bvid, cid, label, root / title if not (single and page) else root / title / label,
            data.get("aid") or 0, data.get("duration") or 0)

    return items


# ================= 下载实现 =================


def collect_urls(stream: dict) -> list[str]:
    """主地址 + 所有备份地址，去重。"""
    urls: list[str] = []
    if stream.get("baseUrl"):
        urls.append(stream["baseUrl"])
    for extra in stream.get("backupUrl") or []:
        if extra and extra not in urls:
            urls.append(extra)
    return urls


def probe_first_ok(session: requests.Session, urls: list[str], headers: dict,
                   timeout: float) -> str | None:
    """并发 HEAD 探测，返回最先响应的可用节点（不是测速，只比谁先回应）。"""
    def probe(url: str) -> str:
        resp = session.head(url, headers=headers, timeout=timeout, allow_redirects=True)
        if resp.status_code >= 400:
            raise DownloadError(f"HTTP {resp.status_code}")
        return url

    with ThreadPoolExecutor(max_workers=max(1, len(urls))) as pool:
        futures = [pool.submit(probe, url) for url in urls]
        try:
            for future in as_completed(futures):
                try:
                    return future.result()
                except Exception:
                    continue
        finally:
            for future in futures:
                future.cancel()
    return None


def _expected_total(resp: requests.Response, already: int) -> int:
    """从响应头推断文件总大小（0 表示无法判断）。"""
    content_range = resp.headers.get("Content-Range") or ""
    if "/" in content_range:
        tail = content_range.rsplit("/", 1)[1].strip()
        if tail.isdigit():
            return int(tail)
    length = resp.headers.get("Content-Length") or ""
    if length.isdigit():
        return already + int(length)
    return 0


class SpeedWatchdog:
    """速度看门狗：速度掉到"自身历史平均"的 30% 以下并持续 10 秒，就判定这条连接已废。

    - 参考速度 = 从开始下载到（当前时刻 - SLOW_REF_LAG）的平均速度；
    - 当前速度 = 最近 SLOW_CUR_WINDOW 秒的平均速度；
    - 例外：若按当前速度算出的**预计剩余时间小于 SLOW_MIN_ETA（10 秒）**，
      说明马上就下完了，保持这条连接继续下，不重连；
    - 本来就慢（参考速度低于 SLOW_MIN_REF）时不判定；
    - 时间由调用方传入（now），因此可以脱离真实时钟做单元测试。
    """

    def __init__(self, started_at: float, start_bytes: int, total: int, *,
                 check_interval: float | None = None, cur_window: float | None = None,
                 ref_lag: float | None = None, ratio: float | None = None,
                 hold: float | None = None, min_elapsed: float | None = None,
                 min_ref: int | None = None, min_eta: float | None = None) -> None:
        self.started_at = started_at
        self.start_bytes = start_bytes
        self.total = total
        self.check_interval = SLOW_CHECK_INTERVAL if check_interval is None else check_interval
        self.cur_window = SLOW_CUR_WINDOW if cur_window is None else cur_window
        self.ref_lag = SLOW_REF_LAG if ref_lag is None else ref_lag
        self.ratio = SLOW_RATIO if ratio is None else ratio
        self.hold = SLOW_HOLD if hold is None else hold
        self.min_elapsed = SLOW_MIN_ELAPSED if min_elapsed is None else min_elapsed
        self.min_ref = SLOW_MIN_REF if min_ref is None else min_ref
        self.min_eta = SLOW_MIN_ETA if min_eta is None else min_eta
        self._samples: deque[tuple[float, int]] = deque()
        self._slow_since: float | None = None
        self._last_check = started_at
        self._max_gap = 0.0            # 观察到的最长采样间隔（连接越慢间隔越大）

    def due(self, now: float) -> bool:
        """是否到了该判定的时刻（约每 check_interval 秒一次）。"""
        return now - self._last_check >= self.check_interval

    def sample(self, now: float, done: int) -> str | None:
        """喂一个采样点；返回"变慢"的原因（给用户看）或 None。"""
        self._last_check = now
        if self._samples:
            self._max_gap = max(self._max_gap, now - self._samples[-1][0])
        self._samples.append((now, done))
        # 保留足够长的历史：既要覆盖 ref_lag，也要容纳一次"采样间隔"（慢连接可能几十秒一块），
        # 否则算参考速度时需要的那个老采样点会被裁掉，看门狗就永远不会触发。
        keep_from = (now - max(self.ref_lag, self.cur_window)
                     - self._max_gap - 1.0)
        while len(self._samples) > 2 and self._samples[0][0] < keep_from:
            self._samples.popleft()

        if now - self.started_at < self.min_elapsed:
            return None

        ref_t, ref_bytes = self.started_at, self.start_bytes
        for stamp, amount in self._samples:          # 取 (now - ref_lag) 之前最后一个采样
            if stamp <= now - self.ref_lag:
                ref_t, ref_bytes = stamp, amount
            else:
                break
        ref_elapsed = ref_t - self.started_at
        if ref_elapsed <= 0 or ref_bytes <= self.start_bytes:
            return None
        ref_speed = (ref_bytes - self.start_bytes) / ref_elapsed
        if ref_speed < self.min_ref:
            self._slow_since = None                  # 本来就慢，不折腾
            return None

        # 当前速度 = 最近一段"至少覆盖 min_span 秒"的采样区间（取尽可能新的那个采样点）：
        # 采样密时约等于最近 1 秒的速度，采样稀（连接慢、一块要等很久）时自然退化成
        # "上一块到这一块"的平均速度 —— 否则当前速度会跨过整段快速期，永远判不出变慢。
        min_span = min(1.0, self.cur_window)
        cur_t, cur_bytes = None, None
        for stamp, amount in reversed(self._samples):
            if now - stamp >= min_span:
                cur_t, cur_bytes = stamp, amount
                break
        if cur_t is None or now - cur_t <= 0:
            return None
        cur_speed = max(0.0, (done - cur_bytes) / (now - cur_t))

        if cur_speed >= self.ratio * ref_speed:
            self._slow_since = None                  # 恢复正常，重新计时
            return None

        # 例外：按当前速度估算马上就下完了（剩余时间 < SLOW_MIN_ETA），就保持连接继续下
        if self.total:
            remaining = max(0, self.total - done)
            eta = remaining / cur_speed if cur_speed > 0 else float("inf")
            if eta < self.min_eta:
                return None

        if self._slow_since is None:
            self._slow_since = now
            return None
        held = now - self._slow_since
        if held < self.hold:
            return None
        eta_text = ""
        if self.total and cur_speed > 0:
            eta_text = f"，按此速度还需 {(self.total - done) / cur_speed:.0f} 秒"
        return (f"速度只有 {human_size(int(cur_speed))}/s，"
                f"是此前平均 {human_size(int(ref_speed))}/s 的 "
                f"{cur_speed / ref_speed * 100:.0f}%，已持续 {held:.0f} 秒{eta_text}")


def download_to_file(session: requests.Session, url: str, dest: Path, desc: str,
                     headers: dict, timeout: float, *,
                     bar_position: int | None = None, prefix: str = "",
                     bar_desc: str | None = None, slow_check: bool = True) -> None:
    """下载 url 到 dest：写 <dest>.part，支持断点续传 + 完整性校验，成功后原子改名。

    bar_position 为进度条位置（多线程时每个线程一个，互不覆盖）；
    为 None 表示不放进度条，改为每 15 秒打一行进度（输出被重定向时用）。
    bar_desc 可覆盖进度条标题（用来写清"这是哪个视频的哪条流"）。
    slow_check 打开速度看门狗：速度长期掉到历史平均的 30% 以下会抛 SlowConnection。
    """
    part = dest.with_name(dest.name + PART_SUFFIX)
    already = part.stat().st_size if part.exists() else 0

    request_headers = dict(headers)
    request_headers["Accept-Encoding"] = "identity"   # 防止压缩破坏续传
    if already:
        request_headers["Range"] = f"bytes={already}-"

    with session.get(url, headers=request_headers, stream=True, timeout=timeout) as resp:
        if already and resp.status_code == 416:
            part.unlink(missing_ok=True)
            raise DownloadError("服务器拒绝续传（416），已清除断点，请重试")
        resp.raise_for_status()
        resuming = already > 0 and resp.status_code == 206
        if not resuming:
            already = 0
        total = _expected_total(resp, already)

        mode = "ab" if resuming else "wb"
        done = already
        last_report = time.time()
        watchdog = (SpeedWatchdog(time.time(), already, total)
                    if slow_check and total else None)
        with open(part, mode) as fh, tqdm(
            total=total or None, initial=already, unit="B", unit_scale=True,
            unit_divisor=1024, desc=bar_desc or f"{prefix}{desc}", leave=False,
            position=bar_position or 0, disable=bar_position is None,
            file=sys.stdout,
        ) as bar:
            quiet = bool(getattr(bar, "disable", True))    # 进度条被禁用（输出被重定向）
            for chunk in resp.iter_content(CHUNK_SIZE):
                if _ABORT.is_set():
                    raise Aborted(f"{desc}：已取消")
                if chunk:
                    fh.write(chunk)
                    done += len(chunk)
                    bar.update(len(chunk))
                    if quiet and time.time() - last_report >= 15:
                        last_report = time.time()
                        percent = f"{done * 100 // total}%" if total else "?"
                        amount = (f"{human_size(done)}/{human_size(total)}"
                                  if total else human_size(done))
                        emit(f"{prefix}{desc} {percent} {amount}")
                now = time.time()
                if watchdog is not None and watchdog.due(now):
                    reason = watchdog.sample(now, done)
                    if reason:
                        raise SlowConnection(reason)

    size = part.stat().st_size
    if total and size != total:
        raise DownloadError(f"下载不完整：期望 {human_size(total)}，实际 {human_size(size)}")
    if size == 0:
        raise DownloadError("下载结果为空文件")
    part.replace(dest)


def download_stream(session: requests.Session, stream: dict, dest: Path, desc: str, *,
                    headers: dict, retries: int = 2, timeout: float = 15.0,
                    use_probe: bool = True, bar_position: int | None = None,
                    prefix: str = "", bar_desc: str | None = None,
                    max_reconnects: int = DEFAULT_MAX_RECONNECTS) -> None:
    """多节点 + 多次重试 + 退避，任一节点成功即返回。

    输出带明确状态：[跳过] 已有缓存 / [重试] 某节点某次失败 / [重连] 速度变慢换连接 /
    [成功] 最终成功，这样即使中间失败过，也能一眼看出最后到底成没成。
    max_reconnects 为"因速度变慢而重开连接"的上限（0 = 关闭该检测）。
    """
    if _ABORT.is_set():
        raise Aborted(f"{desc}：已取消")
    if dest.exists() and dest.stat().st_size > 0:
        emit(f"{prefix}{desc}：[跳过] 已有缓存 {human_size(dest.stat().st_size)}，不重复下载")
        return

    urls = collect_urls(stream)
    if not urls:
        raise DownloadError(f"{desc}：没有可用的下载地址")

    if use_probe and len(urls) > 1:
        try:
            fast = probe_first_ok(session, urls, headers, timeout)
            if fast:
                urls = [fast] + [u for u in urls if u != fast]
                emit(f"{prefix}{desc}：已优选节点 {host_of(fast)}（候选 {len(urls)} 个）")
            else:
                emit(f"{prefix}{desc}：[!] {len(urls)} 个候选节点都没通过探测，按原顺序尝试")
        except Exception as exc:
            emit(f"{prefix}{desc}：[!] 节点优选失败（{short_error(exc)}），按原顺序尝试")

    last_error: Exception | None = None
    had_failure = False
    reconnects = 0
    node_index = 0
    attempt = 0            # 当前节点第几次尝试
    fails_here = 0         # 当前节点连续失败次数（用于退避）
    while True:
        attempt += 1
        started = time.time()
        try:
            download_to_file(session, urls[node_index], dest, desc, headers, timeout,
                             bar_position=bar_position, prefix=prefix, bar_desc=bar_desc,
                             slow_check=max_reconnects > 0)
        except (Aborted, KeyboardInterrupt):
            raise
        except SlowConnection as exc:
            if reconnects >= max_reconnects:
                raise DownloadError(
                    f"{desc}：[失败] 速度反复变慢，已重开 {reconnects} 次连接仍无改善（{exc}）")
            reconnects += 1
            node_index = (node_index + 1) % len(urls)   # 换一条连接（顺便换 CDN）再续传
            attempt = 0                                 # 重连不消耗失败重试次数
            fails_here = 0
            emit(f"{prefix}{desc}：[重连] {exc}；已丢掉这条连接，"
                 f"换节点 {node_index + 1}/{len(urls)} 续传（第 {reconnects}/{max_reconnects} 次）")
            _abortable_sleep(0.5)
            continue
        except Exception as exc:
            last_error = exc
            had_failure = True
            fails_here += 1
            more_nodes = node_index + 1 < len(urls)
            if fails_here < retries:
                action = "同一节点重试"
            else:
                action = "换下一个节点" if more_nodes else "已无可用节点"
            emit(f"{prefix}{desc}：[重试] 节点 {node_index + 1}/{len(urls)} "
                 f"第 {fails_here} 次失败（{short_error(exc)}）→ {action}")
            if fails_here >= retries:
                if not more_nodes:
                    break
                node_index += 1
                fails_here = 0
                attempt = 0
            _abortable_sleep(min(1.5 * fails_here if fails_here else 1.5, 6.0))
            continue
        else:
            size = dest.stat().st_size if dest.exists() else 0
            if had_failure or reconnects:   # 只有折腾过才播报，正常情况不刷屏
                emit(f"{prefix}{desc}：[成功] 第 {node_index + 1} 个节点第 {attempt} 次尝试成功"
                     f"（{human_size(size)}，用时 {time.time() - started:.0f}s）")
            return

    raise DownloadError(f"{desc}：[失败] {len(urls)} 个节点全部尝试失败，"
                        f"最后一次错误：{short_error(last_error) if last_error else '未知'}")


# ================= ffmpeg =================


def ffmpeg_bin_name() -> str:
    return "ffmpeg.exe" if IS_WIN else "ffmpeg"


def ffmpeg_local_bin() -> Path:
    """本地 ffmpeg 目录：~/ffmpeg/bin（Windows 安装包与 --install-ffmpeg 装这里）。"""
    return Path.home() / "ffmpeg" / "bin"


@lru_cache(maxsize=1)
def find_ffmpeg() -> str:
    """找 ffmpeg：先看 PATH，再看本地安装目录，最后按平台给出安装命令。

    macOS 的 Homebrew（Apple Silicon / Intel）和 Linux 的 snap、/usr/local/bin
    不一定都在 PATH 里，所以额外补几处常见路径，省得"装好了却找不到"。
    """
    exe = shutil.which("ffmpeg")
    if not exe:
        # 安装包 / --install-ffmpeg 会把 ffmpeg 放在 ~/ffmpeg/bin，但 PATH 要新开进程才生效；
        # 这里再直接找一遍，省得用户重启终端才发现"明明装好了却找不到"。
        local = ffmpeg_local_bin() / ffmpeg_bin_name()
        if local.is_file():
            exe = str(local)
    if not exe and not IS_WIN:
        for folder in ("/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", "/snap/bin"):
            candidate = Path(folder) / "ffmpeg"
            if candidate.is_file() and os.access(candidate, os.X_OK):
                exe = str(candidate)
                break
    if not exe:
        hint = {
            "Windows": "bilibili_downloader --install-ffmpeg（自动装到 ~\\ffmpeg 并加进 PATH）\n"
                       "             或 choco install ffmpeg / scoop install ffmpeg",
            "macOS": "brew install ffmpeg",
            "Linux": "sudo apt install ffmpeg（Debian/Ubuntu）/ sudo dnf install ffmpeg（Fedora）",
        }[PLATFORM_NAME]
        raise DownloadError(
            "未找到 ffmpeg，缺少它无法合并音视频、导出 MP3、烧录弹幕\n"
            f"    {PLATFORM_NAME}: {hint}"
        )
    return exe


def ffmpeg_available() -> str:
    """ffmpeg 可用时返回路径，不可用时返回空串（给 GUI/启动提示用，不抛异常）。"""
    try:
        return find_ffmpeg()
    except DownloadError:
        return ""


def remote_file_size(url: str, timeout: float = 15.0) -> int:
    """HEAD 拿远端文件的实际字节数；拿不到返回 0。

    提示里的"大小"必须是真的，不能写死：发布地址会随版本变化。
    """
    try:
        resp = requests.head(url, headers={"User-Agent": USER_AGENT},
                             timeout=timeout, allow_redirects=True)
        length = (resp.headers.get("Content-Length") or "").strip()
        return int(length) if length.isdigit() else 0
    except Exception:
        return 0


def _download_with_progress(url: str, dest: Path, *, label: str,
                            total: int = 0) -> None:
    """下载到文件，每 10% 播报一次（GUI/CLI 都能看到进度，且能被取消）。"""
    with requests.get(url, headers={"User-Agent": USER_AGENT}, stream=True,
                      timeout=(15.0, 60.0)) as resp:
        resp.raise_for_status()
        total = total or int(resp.headers.get("Content-Length") or 0)
        done = 0
        last_pct = -10
        with open(dest, "wb") as fh:
            for chunk in resp.iter_content(CHUNK_SIZE):
                if _ABORT.is_set():
                    raise Aborted("已取消")
                if not chunk:
                    continue
                fh.write(chunk)
                done += len(chunk)
                pct = int(done * 100 / total) if total else 0
                if pct >= last_pct + 10:
                    last_pct = pct
                    amount = (f"{human_size(done)}/{human_size(total)}"
                              if total else human_size(done))
                    emit(f"[{label}] 已下载 {pct}%（{amount}）")


def _add_user_path(directory: Path) -> bool:
    """把目录追加到用户 PATH（幂等，大小写不敏感）。

    Windows 写 HKCU\\Environment（并广播 WM_SETTINGCHANGE，新的终端才知道）；
    macOS / Linux 不擅自改 shell 启动脚本——用户的 .zshrc / .bashrc 各有各的写法，
    硬改很容易改坏，所以只保证当前进程能用，长期生效在 README 里给命令。
    """
    if not IS_WIN:
        entry = str(Path(directory).resolve())
        parts = os.environ.get("PATH", "").split(os.pathsep)
        if entry not in parts:
            os.environ["PATH"] = os.environ.get("PATH", "") + os.pathsep + entry
        return False
    entry = str(Path(directory).resolve())
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0,
                            winreg.KEY_READ | winreg.KEY_SET_VALUE) as key:
            try:
                current, _ = winreg.QueryValueEx(key, "Path")
            except OSError:
                current = ""
            current = str(current or "")
            existing = [part.strip().lower() for part in current.split(";")]
            if entry.lower() not in existing:
                merged = (current + ";" + entry
                          if current and not current.endswith(";") else current + entry)
                winreg.SetValueEx(key, "Path", 0, winreg.REG_EXPAND_SZ, merged)
    except OSError:
        return False

    _broadcast_env_change()
    os.environ["PATH"] = os.environ.get("PATH", "") + ";" + entry
    return True


def _github_asset(timeout: float = 20.0) -> tuple[str, int]:
    """通过 GitHub API 拿到当前 essentials 包地址和字节数，失败返回空串。"""
    try:
        resp = requests.get(FFMPEG_RELEASE_API, headers={"User-Agent": USER_AGENT},
                            timeout=timeout)
        resp.raise_for_status()
        for asset in (resp.json().get("assets") or []):
            name = str(asset.get("name") or "")
            url = str(asset.get("browser_download_url") or "")
            if url and name.endswith("essentials_build.zip"):
                return url, int(asset.get("size") or 0)
    except Exception:
        pass
    return "", 0


def _mirror_url(url: str) -> str:
    """GitHub 地址套一层镜像；非 GitHub 地址原样返回。"""
    if url.startswith("https://github.com/"):
        return FFMPEG_MIRROR_PREFIX + url
    return url


@lru_cache(maxsize=8)
def resolve_ffmpeg_archive(source: str = "auto", timeout: float = 20.0) -> tuple[str, int]:
    """返回 (下载地址, 字节数)。

    gyan.dev 是官方发布页，但国内实测只有 ~30 KB/s（114 MB 要一个多小时）；同一个包放在
    GitHub Releases 上能跑到 1 MB/s 以上，走 ghfast.top 镜像还能到 2～3 MB/s。所以先用
    GitHub API 解析出当前的 `*essentials_build.zip`（名字带版本号，不能写死），
    source=mirror 时给地址套镜像，API 失败再退回 gyan.dev 的固定地址。
    """
    url, size = _github_asset(timeout)
    if url:
        if source == "mirror":
            url = _mirror_url(url)
        return url, size
    return FFMPEG_ZIP_URL, remote_file_size(FFMPEG_ZIP_URL)


def ffmpeg_archive_candidates(source: str) -> list[tuple[str, int]]:
    """按所选源排出候选地址：auto 官方 → 镜像 → gyan.dev，其余只走指定源再兜底。"""
    official, size = _github_asset()
    if not official:                      # API 不通：只剩 gyan.dev，镜像无从谈起
        official = FFMPEG_ZIP_URL
        size = 0
    mirror = _mirror_url(official)
    if source == "mirror":
        order = [mirror, official]
    elif source == "official":
        order = [official]
    else:
        order = [official, mirror]
    urls = [(url, size if url in (official, mirror) else 0) for url in order]
    if FFMPEG_ZIP_URL not in [url for url, _ in urls]:
        urls.append((FFMPEG_ZIP_URL, 0))
    seen, out = set(), []
    for url, length in urls:
        if url not in seen:
            seen.add(url)
            out.append((url, length))
    return out


def _download_ffmpeg_archive(dest: Path, size: int, source: str | None = None) -> None:
    """按所选源依次尝试；一个地址没连上就换下一个（auto 会把官方、镜像、gyan 都试一遍）。

    下载途中用户点"停止"（GUI/CLI 的 Aborted）不算地址问题，直接抛出去，不再试别的源。
    """
    source = source or FFMPEG_SOURCE
    candidates = ffmpeg_archive_candidates(source)
    labels = {"auto": "自动", "official": "官方源", "mirror": "镜像源"}
    last: Exception | None = None
    for index, (url, length) in enumerate(candidates):
        try:
            _download_with_progress(url, dest, label="ffmpeg",
                                    total=length or (size if index == 0 else 0))
            return
        except Aborted:
            raise
        except Exception as exc:
            last = exc
            if index + 1 < len(candidates):
                emit(f"[ffmpeg] {labels.get(source, source)}：这个地址没连上"
                     f"（{short_error(exc, 120)}），换下一个再试")
    raise DownloadError(f"ffmpeg 下载失败：{short_error(last)}")


def install_ffmpeg(target: Path | None = None, source: str | None = None) -> str:
    """下载 ffmpeg 到 ~/ffmpeg 并加入用户 PATH（仅 Windows）。

    用 gyan.dev 的 essentials 构建：libmp3lame / libx264 / libass 都在里面，
    体积又比 gpl 全家桶小一半。下载源由 source 决定（auto / official / mirror），
    和安装包里的选择页走同一份包，两边行为一致。

    macOS / Linux 不做"自动下载二进制"：那边的包管理器已经把 ffmpeg 管得很好，
    硬塞一份到 ~/ffmpeg 反而会和系统版本打架，所以这里只给出对应命令。
    """
    if not IS_WIN:
        raise DownloadError(
            f"{PLATFORM_NAME} 请用系统包管理器安装 ffmpeg：\n"
            "    macOS: brew install ffmpeg\n"
            "    Linux: sudo apt install ffmpeg（Debian/Ubuntu）"
            " / sudo dnf install ffmpeg（Fedora）"
        )

    source = source or FFMPEG_SOURCE
    source_label = {"auto": "自动选择", "official": "官方源", "mirror": "镜像源"}.get(source, source)
    root = (target or Path.home() / "ffmpeg").expanduser()
    bin_dir = root / "bin"
    exe_path = bin_dir / "ffmpeg.exe"
    if exe_path.is_file():
        _add_user_path(bin_dir)
        find_ffmpeg.cache_clear()
        return f"已存在：{exe_path}（已确保在用户 PATH 中）"

    _, size = resolve_ffmpeg_archive("official" if source != "mirror" else "mirror")
    shown = human_size(size) if size else f"约 {FFMPEG_FALLBACK_MB} MB"
    emit(f"[ffmpeg] 开始下载（{shown}，{source_label}）→ {bin_dir}")

    work = Path(tempfile.mkdtemp(prefix="bili_ffmpeg_"))
    try:
        archive = work / "ffmpeg.zip"
        _download_ffmpeg_archive(archive, size, source)

        extract = work / "unzip"
        with zipfile.ZipFile(archive) as zf:
            names = zf.namelist()
            member = next((name for name in names
                           if name.replace("\\", "/").lower().endswith("/bin/ffmpeg.exe")), None)
            if not member:
                raise DownloadError("压缩包里没有 bin\\ffmpeg.exe，下载内容可能不对")
            prefix = member.rsplit("/bin/", 1)[0] + "/bin/"
            for name in names:
                if name.startswith(prefix):
                    zf.extract(name, extract)

        source_bin = extract.joinpath(*prefix.strip("/").split("/"))
        bin_dir.mkdir(parents=True, exist_ok=True)
        for entry in source_bin.iterdir():
            if entry.is_file():
                shutil.copy2(entry, bin_dir / entry.name)
    finally:
        shutil.rmtree(work, ignore_errors=True)

    _add_user_path(bin_dir)
    find_ffmpeg.cache_clear()

    version = ""
    try:
        proc = subprocess.run([str(exe_path), "-version"], capture_output=True,
                              text=True, encoding="utf-8", errors="replace", timeout=20)
        version = (proc.stdout or "").splitlines()[0].strip()
    except Exception:
        pass
    return f"已安装到 {bin_dir}" + (f"（{version}）" if version else "")


def run_ffmpeg(args: list, err_msg: str, *, cwd: Path | None = None) -> None:
    cmd = [find_ffmpeg(), "-hide_banner", "-loglevel", "error", "-nostdin", "-y", *args]
    proc = subprocess.run(
        cmd, stdin=subprocess.DEVNULL, capture_output=True,
        text=True, encoding="utf-8", errors="replace",
        cwd=str(cwd) if cwd else None,
    )
    if proc.returncode != 0:
        raise DownloadError(f"{err_msg}：{(proc.stderr or '').strip()[:800]}")


def _ffmpeg_to_file(args: list, dest: Path, err_msg: str, *,
                     cwd: Path | None = None) -> None:
    """跑 ffmpeg 写 <dest>.part，成功再原子改名，失败不留半成品。"""
    tmp = dest.with_name(f"{dest.stem}{PART_SUFFIX}{dest.suffix}")
    try:
        run_ffmpeg([*args, str(tmp)], err_msg, cwd=cwd)
        if not tmp.exists() or tmp.stat().st_size == 0:
            raise DownloadError(f"{err_msg}：输出为空")
        tmp.replace(dest)
    except BaseException:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def merge_av(video_m4s: Path, audio_m4s: Path, out_mp4: Path) -> None:
    """-c copy 直接封装（不重新编码，秒级完成），并把索引前置便于在线播放。"""
    _ffmpeg_to_file(
        ["-i", str(video_m4s), "-i", str(audio_m4s),
         "-c", "copy", "-movflags", "+faststart"],
        out_mp4, "合并音视频失败",
    )


def export_mp3(audio_m4s: Path, out_mp3: Path, bitrate: str) -> None:
    _ffmpeg_to_file(
        ["-i", str(audio_m4s), "-vn", "-c:a", "libmp3lame", "-b:a", f"{bitrate}k"],
        out_mp3, "导出 MP3 失败",
    )


def mux_danmaku(video: Path, ass: Path, out_mkv: Path) -> None:
    """把 ASS 作为字幕轨封装进 MKV：不重新编码，秒级完成，播放器里可开关。"""
    _ffmpeg_to_file(
        ["-i", str(video), "-i", str(ass),
         "-map", "0:v:0", "-map", "0:a:0", "-map", "1:0",
         "-c:v", "copy", "-c:a", "copy", "-c:s", "ass",
         "-metadata:s:s:0", "language=chi",
         "-disposition:s:0", "default"],
        out_mkv, "封装弹幕字幕失败",
    )


def _filter_literal(path: Path) -> str:
    """放进单引号里交给滤镜解析器。

    Windows 盘符的冒号在滤镜语法里是分隔符，绝对路径怎么写都要转义，很容易出错；
    直接以文件所在目录为工作目录、只传文件名，就不存在冒号问题（中文、空格由单引号兜住）。
    """
    return "'" + str(path.name).replace("\\", "/").replace("'", "\\'") + "'"


def burn_danmaku(video: Path, ass: Path, out_mp4: Path, *, crf: str = "20") -> None:
    """把 ASS 烧进画面：重新编码（慢、体积大），但任何播放器、任何设备都看得见。"""
    _ffmpeg_to_file(
        ["-i", str(video), "-vf", f"ass={_filter_literal(ass)}",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", crf,
         "-pix_fmt", "yuv420p", "-c:a", "copy", "-movflags", "+faststart"],
        out_mp4, "烧录弹幕失败", cwd=ass.parent,
    )


# ================= 选流 =================


def pick_video(dash: dict, max_id: int) -> dict:
    streams = [s for s in (dash.get("video") or []) if s.get("baseUrl")]
    if not streams:
        raise DownloadError("没有可用的视频流")
    for stream in sorted(streams, key=lambda s: s.get("id", 0), reverse=True):
        if stream.get("id", 0) <= max_id:
            return stream
    return min(streams, key=lambda s: s.get("id", 0))   # 请求的清晰度都没有，退回最低


def pick_audio(dash: dict) -> dict:
    candidates: list[dict] = [s for s in (dash.get("audio") or []) if s.get("baseUrl")]

    flac = (dash.get("flac") or {}).get("audio")
    if isinstance(flac, dict) and flac.get("baseUrl"):
        candidates.append(flac)

    dolby = (dash.get("dolby") or {}).get("audio")
    if isinstance(dolby, dict) and dolby.get("baseUrl"):
        candidates.append(dolby)
    elif isinstance(dolby, list):
        candidates.extend(s for s in dolby if s.get("baseUrl"))

    if not candidates:
        raise DownloadError("没有可用的音频流")
    lossless = [s for s in candidates if s.get("id") in AUDIO_LOSSLESS_IDS]
    pool = lossless or candidates
    return max(pool, key=lambda s: s.get("bandwidth", 0))


# ================= 弹幕 =================

# <d p="时间,模式,字号,颜色,时间戳,池,用户ID,弹幕ID">正文</d>
# 正文里会出现 &amp; &lt; 之类的实体，必须反转义后再写进 ASS。
_DANMAKU_ITEM = re.compile(r'<d\s+p="([^"]*)"\s*>(.*?)</d>', re.S)
_DANMAKU_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _maybe_decompress(data: bytes) -> bytes:
    """B 站弹幕接口有时不带 Content-Encoding 却塞了压缩数据，这里兜一层。"""
    if data[:2] == b"\x1f\x8b":
        try:
            return gzip.decompress(data)
        except OSError:
            return data
    try:
        inflated = zlib.decompress(data)
        if b"<i>" in inflated or b"<d " in inflated:
            return inflated
    except zlib.error:
        pass
    return data


def parse_danmaku_xml(raw: bytes | str) -> list[dict]:
    """把弹幕 XML 解析成 [{time, mode, size, color, text}]（时间单位为秒）。"""
    text = raw.decode("utf-8", "replace") if isinstance(raw, (bytes, bytearray)) else str(raw)
    lines: list[dict] = []
    for match in _DANMAKU_ITEM.finditer(text):
        fields = match.group(1).split(",")
        if len(fields) < 8:            # 字段不全的行直接丢掉，别让一行脏数据毁掉整份弹幕
            continue
        try:
            stamp = float(fields[0])
            mode = int(float(fields[1]))
            size = int(float(fields[2]))
            color = int(float(fields[3]))
        except ValueError:
            continue
        content = html.unescape(match.group(2))
        content = _DANMAKU_CTRL.sub("", content).replace("\r", " ").replace("\n", " ").strip()
        if not content:
            continue
        lines.append({"time": max(0.0, stamp), "mode": mode,
                      "size": size or 25, "color": color & 0xFFFFFF,
                      "text": content})
    return lines


def fetch_danmaku_xml(session: requests.Session, headers: dict, timeout: float,
                      cid: int) -> str:
    """取某个分P的全部可见弹幕（XML 文本）。两个地址互为备份。"""
    last_error: Exception | None = None
    for template in DANMAKU_XML_URLS:
        url = template.format(cid=cid)
        try:
            resp = session.get(url, headers=headers, timeout=timeout)
            if resp.status_code != 200:
                raise DownloadError(f"HTTP {resp.status_code}")
            data = _maybe_decompress(resp.content)
            text = data.decode("utf-8", "replace")
            if "<d " not in text and "<i>" not in text:
                raise DownloadError("返回的不是弹幕 XML（可能被风控，或接口已改格式）")
            return text
        except Exception as exc:         # 换下一个地址再试
            last_error = exc
    raise DownloadError(f"获取弹幕失败：{short_error(last_error) if last_error else '未知错误'}")


def filter_danmaku(lines: list[dict], mode: str) -> list[dict]:
    """按"精简 / 多"筛一遍弹幕。

    精简（light）：去掉同一句话的刷屏重复、去掉逆向弹幕、超长截断、每秒限量，
                   体积小、ASS 不卡、看着不吵；
    多（full）    ：保留所有能渲染的类型（1-6），不去重不限流。
    两种模式都会跳过 7（高级）/ 8（代码）弹幕 —— 那两种是 JSON/脚本，用 ASS 还原不了。
    """
    kept: list[dict] = []
    seen: set[tuple[int, str, int]] = set()
    per_second: dict[int, int] = {}

    for line in lines:
        mode_id = int(line["mode"])
        if mode_id in (7, 8):
            continue
        content = str(line["text"])
        if mode == "light":
            if mode_id == 6:             # 逆向弹幕字体是反的，精简模式直接不要
                continue
            content = content[:DANMAKU_LIGHT_MAX_CHARS]
            bucket = int(line["time"] // DANMAKU_LIGHT_DEDUPE_WINDOW)
            key = (mode_id, content, bucket)
            if key in seen:              # 同一时间窗里重复的刷屏弹幕只留一条
                continue
            seen.add(key)
            second = int(line["time"])
            if per_second.get(second, 0) >= DANMAKU_LIGHT_PER_SECOND:
                continue
            per_second[second] = per_second.get(second, 0) + 1
        kept.append({**line, "mode": mode_id, "text": content})

    kept.sort(key=lambda item: item["time"])
    return kept


def danmaku_to_xml(lines: Sequence[dict], cid: int) -> str:
    """按原格式写回 XML（方便别的播放器/工具直接用）。"""
    parts = ['<?xml version="1.0" encoding="UTF-8"?><i>',
             f"<chatid>{int(cid)}</chatid>"]
    for line in lines:
        body = html.escape(str(line["text"]), quote=False)
        parts.append(
            f'<d p="{line["time"]:.3f},{line["mode"]},{line["size"]},'
            f'{line["color"]},0,0,0,0">{body}</d>'
        )
    parts.append("</i>")
    return "".join(parts)


def _ass_time(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    hours = int(seconds // 3600)
    minutes = int(seconds % 3600 // 60)
    return f"{hours}:{minutes:02d}:{seconds % 60:05.2f}"


def _ass_color(rgb: int) -> str:
    """0xRRGGBB → ASS 的 &HBBGGRR&。"""
    red, green, blue = (rgb >> 16) & 0xFF, (rgb >> 8) & 0xFF, rgb & 0xFF
    return f"&H00{blue:02X}{green:02X}{red:02X}&"


def _ass_escape(text: str) -> str:
    """{} 是 ASS 的样式块、\\ 是控制符，正文里出现都会让字幕炸掉。"""
    return (text.replace("\\", "＼").replace("{", "｛").replace("}", "｝")
            .replace("\r", " ").replace("\n", " "))


def _text_width(text: str, font_size: int) -> float:
    """估算文字宽度：中文按 1 个字宽，ASCII 按 0.55 个字宽（偏保守，宁可不重叠）。"""
    units = sum(0.55 if ord(ch) < 128 else 1.0 for ch in text)
    return units * font_size


class _AssLanes:
    """弹幕 → ASS 事件的"车道"分配器（点播弹幕和直播弹幕共用一套规则）。

    滚动 / 顶部 / 底部共用同一组车道（每条车道记下一次可用的时刻）：
    三类弹幕如果各用一套车道表，就会在同一个纵坐标上互相压字，这是最容易被吐槽的画面。
    strict=True（精简档）时车道占满就丢掉这一条，宁可少几条也不压字；
    strict=False（多档）时挑最早空出来的车道，宁可轻微重叠也不丢弹幕。

    直播是边录边收弹幕的，可能一录就是十几个小时、上百万条，不能像点播那样先攒成
    一个大列表再渲染；这个类逐条吐事件，调用方可以直接往文件里写，内存只跟车道数有关。
    """

    def __init__(self, width: int, height: int, strict: bool = False) -> None:
        self.width = max(320, int(width or 1920))
        self.height = max(240, int(height or 1080))
        self.strict = strict
        self.base_size = max(12, round(self.height / 720 * 25))   # 25 号字在 720p，按比例放大
        self.lane_height = max(16, round(self.height / 1080 * 46))
        self.lane_count = max(1, int(self.height * 0.9 // self.lane_height))
        self.top_pad = max(4, round(self.height * 0.02))
        self.lanes: dict[int, float] = {}       # 车道号（从上往下数）→ 最早可复用的时刻

    def _pick_lane(self, now: float, from_bottom: bool = False) -> int | None:
        order = range(self.lane_count - 1, -1, -1) if from_bottom else range(self.lane_count)
        for index in order:
            if self.lanes.get(index, 0.0) <= now:
                return index
        if self.strict:
            return None                         # 精简档：没位置就不放，画面干净优先
        return min(range(self.lane_count), key=lambda index: self.lanes.get(index, 0.0))

    def event(self, line: dict) -> str | None:
        """把一条弹幕转成一行 Dialogue；放不下（精简档车位满）时返回 None。"""
        width, height = self.width, self.height
        mode_id = int(line["mode"])
        start = float(line["time"])
        font_size = max(10, round(int(line["size"]) * height / 720))
        style = (f"\\fs{font_size}\\c{_ass_color(int(line['color']))}")
        body = _ass_escape(str(line["text"]))

        if mode_id in (1, 2, 3, 6):
            text_w = _text_width(str(line["text"]), font_size)
            duration = DANMAKU_SCROLL_SECONDS
            lane = self._pick_lane(start)
            if lane is None:
                return None
            y = self.top_pad + lane * self.lane_height
            if mode_id == 6:                     # 逆向：从左往右
                x1, x2 = -text_w, width
            else:                                # 常规：从右往左
                x1, x2 = width, -text_w
            speed = (width + text_w) / duration   # 横向速度（像素/秒）
            if self.strict:
                # 精简档：这条车道等整条弹幕滚完再复用。只按"尾巴离开右边缘"算的话，
                # 后进的长弹幕会追上先进去的短弹幕，屏幕上就是两行字叠在一起。
                self.lanes[lane] = start + duration
            else:
                # 多档：尾巴离开出发侧边缘就允许下一条进，密度优先
                travel = max(8, round(self.base_size * 0.8)) + text_w
                self.lanes[lane] = start + max(0.0, min(duration, travel / max(speed, 1.0)))
            return (
                f"Dialogue: 0,{_ass_time(start)},{_ass_time(start + duration)},Danmaku,,0,0,0,,"
                f"{{\\an7\\move({x1:.0f},{y:.0f},{x2:.0f},{y:.0f}){style}}}{body}"
            )
        if mode_id in (4, 5):
            lane = self._pick_lane(start, from_bottom=(mode_id == 4))
            if lane is None:
                return None
            self.lanes[lane] = start + DANMAKU_FIXED_SECONDS
            if mode_id == 5:                     # 顶部：坐标按上边算
                y = self.top_pad + lane * self.lane_height + font_size / 2
            else:                                # 底部：同一条车道从下往上数
                y = (height - self.top_pad
                     - (self.lane_count - 1 - lane) * self.lane_height - font_size / 2)
            return (
                f"Dialogue: 0,{_ass_time(start)},{_ass_time(start + DANMAKU_FIXED_SECONDS)},"
                f"Danmaku,,0,0,0,,{{\\an5\\pos({width / 2:.0f},{y:.0f}){style}}}{body}"
            )
        return None


def _ass_header(width: int, height: int, title: str, base_size: int) -> str:
    return "\n".join([
        "[Script Info]",
        "; 由 bilibili-downloader 生成" + (f"：{title}" if title else ""),
        "ScriptType: v4.00+",
        f"PlayResX: {width}",
        f"PlayResY: {height}",
        "WrapStyle: 2",
        "ScaledBorderAndShadow: yes",
        "YCbCr Matrix: TV.601",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Danmaku,Microsoft YaHei,{base_size},&H00FFFFFF,&H00FFFFFF,&H00000000,"
        "&H64000000,0,0,0,0,100,100,0,0,1,2,1,7,0,0,0,1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]) + "\n"


def build_danmaku_ass(lines: Sequence[dict], width: int, height: int,
                      title: str = "", *, strict: bool = False) -> str:
    """把弹幕渲染成 ASS（点播用；直播用下面的 write_danmaku_ass 边读边写）。"""
    lanes = _AssLanes(width, height, strict)
    events = [event for event in (lanes.event(line) for line in lines) if event]
    return (_ass_header(lanes.width, lanes.height, title, lanes.base_size)
            + "\n".join(events) + ("\n" if events else ""))


def write_danmaku_ass(lines: Iterable[dict], dest: Path, width: int, height: int,
                      title: str = "", *, strict: bool = False) -> int:
    """流式写 ASS：逐条落盘，内存占用只跟车道数有关（长直播几十万条弹幕也不炸）。"""
    lanes = _AssLanes(width, height, strict)
    dest.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with open(dest, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(_ass_header(lanes.width, lanes.height, title, lanes.base_size))
        for line in lines:
            event = lanes.event(line)
            if event:
                handle.write(event + "\n")
                count += 1
    return count


def _write_text_atomic(path: Path, text: str) -> None:
    """先写 .part 再改名：中断时不会留下半份弹幕文件。"""
    part = path.with_name(path.name + PART_SUFFIX)
    part.write_text(text, encoding="utf-8")
    part.replace(path)


# ================= 直播录制 =================
#
# 直播和点播是两套东西：点播有确定的长度、DASH 分片，直播只有一条一直往下吐的 FLV。
# 所以这里不复用 download_stream，而是走"流式读 → 按时间轮转分段 → 结束时 -c copy 拼一条"：
# 整个过程中内存里只有一块读缓冲，录十几个小时也不会把机器拖死，中途断电最多丢最后一段。
#
# 弹幕走 WebSocket：手写握手 + 帧解析 + B 站协议包解析（zlib 用标准库），不引入第三方依赖。
# 边收边写 JSONL，停止后再流式转成 XML / ASS，精简和全部两种模式各出一套。

LIVE_INFO_API = "https://api.live.bilibili.com/room/v1/Room/get_info"
LIVE_PLAY_API = "https://api.live.bilibili.com/xlive/web-room/v2/index/getRoomPlayInfo"
LIVE_DANMU_API = "https://api.live.bilibili.com/xlive/web-room/v1/index/getDanmuInfo"
LIVE_HOME = "https://live.bilibili.com/"
LIVE_CONFIG_NAME = "live_record.json"
LIVE_DEFAULT_QN = 10000                 # 原画（默认最高画质）
LIVE_READ_CHUNK = 256 * 1024            # 单次写入的分块大小，和点播一致
LIVE_QN_DESC = {30000: "杜比", 20000: "4K", 15000: "2K", 10000: "原画",
                400: "蓝光", 250: "超清", 150: "高清", 80: "流畅"}
LIVE_SEGMENT_MINUTES = 10               # 默认 10 分钟一段
LIVE_POLL_SECONDS = 60                  # 预约任务轮询间隔
LIVE_WS_HOST_FALLBACK = "broadcastlv.chat.bilibili.com"


def live_headers(headers: dict) -> dict:
    """直播接口和点播接口的 Referer/Origin 不一样，直接改副本，别污染下载用的头。"""
    copy = dict(headers)
    copy["Referer"] = LIVE_HOME
    copy["Origin"] = LIVE_HOME.rstrip("/")
    return copy


def parse_live_room_id(text: str) -> int:
    """从直播间链接 / 预约页链接 / 纯房间号里认出房间号。

    预约链接的形态很多（live.bilibili.com/123、活动页 ?room_id=123、带一堆参数的分享链接），
    这里按"最像房间号的那个数字"依次兜底；实在认不出来就让人直接填房间号。
    """
    raw = (text or "").strip()
    if not raw:
        raise DownloadError("请填写直播间链接或房间号")
    if raw.isdigit():
        return int(raw)
    for pattern in (
        r"live\.bilibili\.com/(?:h5/)?(\d{3,})",
        r"(?:room_?id|roomid|rid)=(\d{3,})",
        r"/(\d{5,})(?:[/?#]|$)",
    ):
        match = re.search(pattern, raw, re.I)
        if match:
            return int(match.group(1))
    digits = re.findall(r"\d{4,}", raw)
    if len(digits) == 1:
        return int(digits[0])
    raise DownloadError("没能从链接里认出直播间号，请直接填房间号（例如 6 或 7734200）")


def live_room_info(session: requests.Session, headers: dict, room_id: int,
                   timeout: float = 10.0) -> dict:
    data = api_get(session, LIVE_INFO_API, {"room_id": int(room_id)},
                   live_headers(headers), timeout)
    return {
        "ref_id": int(room_id),
        "room_id": int(data.get("room_id") or room_id),
        "short_id": int(data.get("short_id") or 0),
        "title": str(data.get("title") or ""),
        "uname": str(data.get("uname") or ""),
        "live_status": int(data.get("live_status") or 0),
        "online": int(data.get("online") or 0),
        "cover": str(data.get("user_cover") or data.get("cover") or ""),
        "area": "/".join(x for x in (data.get("parent_area_name"),
                                     data.get("area_name")) if x),
        "live_time": str(data.get("live_time") or ""),
    }


def live_play_info(session: requests.Session, headers: dict, room_id: int,
                   qn: int = LIVE_DEFAULT_QN, timeout: float = 10.0) -> dict:
    """取一路可用直播流：优先 FLV/AVC（分段拼接兼容性最好），HLS 兜底。"""
    params = {
        "room_id": int(room_id), "protocol": "0,1", "format": "0,1,2", "codec": "0,1",
        "qn": int(qn), "platform": "web", "ptype": 8, "dolby": 5, "panorama": 1,
    }
    data = api_get(session, LIVE_PLAY_API, params, live_headers(headers), timeout)
    play = ((data.get("playurl_info") or {}).get("playurl")) or {}
    candidates: list[dict] = []
    for stream in play.get("stream") or []:
        proto = str(stream.get("protocol_name") or "")
        for fmt in stream.get("format") or []:
            fmt_name = str(fmt.get("format_name") or "")
            for codec in fmt.get("codec") or []:
                codec_name = str(codec.get("codec_name") or "")
                base_url = str(codec.get("base_url") or "")
                urls = [f"{info.get('host', '')}{base_url}{info.get('extra', '')}"
                        for info in (codec.get("url_info") or []) if info.get("host")]
                if not urls:
                    continue
                # 越小越优先：http_stream/flv/avc → 0；hls/ts/hevc 会排到后面
                rank = ((0 if proto == "http_stream" else 2)
                        + (0 if fmt_name == "flv" else 1)
                        + (0 if codec_name == "avc" else 1))
                candidates.append({
                    "rank": rank, "urls": urls, "protocol": proto, "format": fmt_name,
                    "codec": codec_name, "qn": int(codec.get("current_qn") or qn),
                    "accept_qn": [int(x) for x in (codec.get("accept_qn") or [])],
                })
    if not candidates:
        raise DownloadError("这个直播间当前没有可用的播放地址（可能没开播，或需要登录）")
    best = min(candidates, key=lambda item: item["rank"])
    desc = []
    for item in play.get("g_qn_desc") or []:
        try:
            desc.append((int(item.get("qn")), str(item.get("desc") or "")))
        except (TypeError, ValueError):
            continue
    best["qn_desc"] = desc
    if not best["accept_qn"]:
        best["accept_qn"] = [item[0] for item in desc]
    return best


def live_quality_choices(play: dict) -> list[tuple[int, str]]:
    """可切换的画质清单（按返回的 accept_qn 和 g_qn_desc 配对，从高到低）。"""
    desc = dict(play.get("qn_desc") or {})
    choices = []
    for qn in sorted(set(play.get("accept_qn") or []), reverse=True):
        choices.append((qn, desc.get(qn) or LIVE_QN_DESC.get(qn) or str(qn)))
    return choices


def live_snapshot(session: requests.Session, headers: dict, room_id: int, qn: int,
                  dest: Path, timeout: float = 20.0) -> Path:
    """抓一帧做预览：ffmpeg 直接从流里读一帧，不需要下载整段，也不占内存。"""
    play = live_play_info(session, headers, room_id, qn, timeout=10.0)
    errors: list[str] = []
    tmp = dest.with_name(dest.stem + ".part.png")
    for url in play["urls"][:3]:
        try:
            # Tk 的 PhotoImage 只认 PNG/GIF，这里必须输出真 PNG（image2 默认会按后缀写 JPEG）
            run_ffmpeg(["-i", url, "-frames:v", "1", "-c:v", "png", "-f", "image2",
                        "-update", "1", str(tmp)],
                       "抓取直播预览失败")
            if tmp.exists() and tmp.stat().st_size > 0:
                tmp.replace(dest)
                return dest
            raise DownloadError("预览输出为空")
        except Exception as exc:
            errors.append(short_error(exc))
    raise DownloadError(errors[-1] if errors else "抓取直播预览失败")


def live_sample_clip(session: requests.Session, headers: dict, room_id: int, qn: int,
                     dest: Path, seconds: int = 10) -> Path:
    """试看：录一小段（默认 10 秒）直接 -c copy，几乎不花时间，用系统播放器打开。"""
    play = live_play_info(session, headers, room_id, qn, timeout=10.0)
    last: Exception | None = None
    for url in play["urls"][:3]:
        try:
            run_ffmpeg(["-i", url, "-t", str(int(seconds)), "-c", "copy", str(dest)],
                       "录制试看片段失败")
            if dest.exists() and dest.stat().st_size > 0:
                return dest
            raise DownloadError("试看片段为空")
        except Exception as exc:
            last = exc
    raise DownloadError(short_error(last) if last else "录制试看片段失败")


def probe_media_size(video: Path) -> tuple[int, int]:
    """取视频分辨率给弹幕排版用；取不到就按 1920×1080（ASS 会按 PlayRes 缩放）。"""
    try:
        ffmpeg = find_ffmpeg()
        probe = Path(ffmpeg).with_name("ffprobe.exe" if IS_WIN else "ffprobe")
        if probe.is_file():
            proc = subprocess.run(
                [str(probe), "-v", "error", "-select_streams", "v:0",
                 "-show_entries", "stream=width,height", "-of", "csv=s=x:p=0", str(video)],
                stdin=subprocess.DEVNULL, capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=30,
            )
            first = (proc.stdout or "").strip().splitlines()
            if first and "x" in first[0]:
                width, height = first[0].split("x")[:2]
                return int(width), int(height)
    except Exception:
        pass
    return 1920, 1080


# ---- 直播配置（和 sessdata.txt 一样放在程序目录，便携、不写注册表）----

_LIVE_CONFIG_CACHE: Path | None = None


def live_config_path() -> Path:
    """直播配置（画质、分段、预约任务）该写到哪。

    程序目录可写时（源码运行、绿色版、装在自己目录里的单文件版）就留在程序旁边，
    方便整目录拷走；装到 Program Files / /usr / /Applications 这类只读位置时，
    退到用户配置目录（%APPDATA% 或 ~/.config），否则配置会静默写失败、
    预约任务下次启动就丢。
    """
    global _LIVE_CONFIG_CACHE
    if _LIVE_CONFIG_CACHE is not None:
        return _LIVE_CONFIG_CACHE
    app_dir = _app_dir()
    app_file = app_dir / LIVE_CONFIG_NAME
    try:
        probe = app_dir / ".write_test"
        probe.write_text("", encoding="utf-8")
        probe.unlink()
        _LIVE_CONFIG_CACHE = app_file
        return app_file
    except OSError:
        base = user_config_dir()
        try:
            base.mkdir(parents=True, exist_ok=True)
        except OSError:
            _LIVE_CONFIG_CACHE = app_file
            return app_file
        _LIVE_CONFIG_CACHE = base / LIVE_CONFIG_NAME
        return _LIVE_CONFIG_CACHE


def load_live_config() -> dict:
    defaults = {
        "qn": LIVE_DEFAULT_QN,
        "segment_minutes": LIVE_SEGMENT_MINUTES,
        "danmaku_light": True,
        "danmaku_full": True,
        "keep_segments": False,
        "output": str(default_output()),
        "poll_seconds": LIVE_POLL_SECONDS,
        "tasks": [],
    }
    for candidate in (live_config_path(), _app_dir() / LIVE_CONFIG_NAME):
        try:
            raw = json.loads(candidate.read_text("utf-8"))
            break
        except Exception:
            continue
    else:
        return defaults
    config = dict(defaults)
    for key in defaults:
        if key in raw:
            config[key] = raw[key]
    tasks = []
    for task in raw.get("tasks") or []:
        try:
            room_id = int(task.get("room_id") or 0)
        except (TypeError, ValueError):
            continue
        tasks.append({
            "link": str(task.get("link") or ""),
            "room_id": room_id,
            "note": str(task.get("note") or ""),
            "enabled": bool(task.get("enabled", True)),
        })
    config["tasks"] = tasks
    return config


def save_live_config(config: dict) -> None:
    _write_text_atomic(live_config_path(),
                       json.dumps(config, ensure_ascii=False, indent=2))


# ---- 直播弹幕：手写 WebSocket ----

def _ws_frame(payload: bytes) -> bytes:
    """客户端 → 服务端的单帧（固定 FIN + 文本帧，客户端发的帧必须带掩码）。"""
    header = bytearray([0x81])
    length = len(payload)
    if length < 126:
        header.append(0x80 | length)
    elif length < 65536:
        header.append(0x80 | 126)
        header += struct.pack(">H", length)
    else:
        header.append(0x80 | 127)
        header += struct.pack(">Q", length)
    mask = os.urandom(4)
    header += mask
    return bytes(header) + bytes(b ^ mask[i % 4] for i, b in enumerate(payload))


def _ws_parse(buffer: bytes) -> tuple[list[tuple[int, bytes]], bytes]:
    """把收到的字节切成 WebSocket 帧；不完整的尾巴原样返回，等下一批数据。"""
    frames: list[tuple[int, bytes]] = []
    while True:
        if len(buffer) < 2:
            break
        opcode = buffer[0] & 0x0F
        length = buffer[1] & 0x7F
        offset = 2
        if length == 126:
            if len(buffer) < 4:
                break
            length = struct.unpack(">H", buffer[2:4])[0]
            offset = 4
        elif length == 127:
            if len(buffer) < 10:
                break
            length = struct.unpack(">Q", buffer[2:10])[0]
            offset = 10
        if len(buffer) < offset + length:
            break
        frames.append((opcode, buffer[offset:offset + length]))
        buffer = buffer[offset + length:]
    return frames, buffer


def _bili_packet(op: int, body: bytes) -> bytes:
    """B 站协议包头：总长 / 头长 16 / 版本 1 / 操作码 / 序号。"""
    return struct.pack(">IHHII", 16 + len(body), 16, 1, op, 1) + body


def _bili_decode(payload: bytes) -> list[dict]:
    """解一个 B 站协议包：ver=2 是 zlib 压的多包；ver=1 的普通消息是一整段 JSON。"""
    if len(payload) < 16:
        return []
    total, header_len, version, _op = struct.unpack(">IHHI", payload[:12])
    body = payload[header_len:total] if 0 < total <= len(payload) else payload[header_len:]
    if version == 2:
        try:
            body = zlib.decompress(body)
        except zlib.error:
            return []
    elif version == 3:
        # brotli：为了不带第三方依赖，握手时固定要 protover=2（zlib），这里正常不会出现
        return []
    try:
        whole = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        whole = None
    if isinstance(whole, dict):
        return [whole]
    messages: list[dict] = []
    offset = 0
    while offset + 16 <= len(body):
        try:
            size, head, ver, op = struct.unpack(">IHHI", body[offset:offset + 12])
        except struct.error:
            break
        if size <= 0 or offset + size > len(body):
            break
        chunk = body[offset:offset + size]
        offset += size
        if ver in (2, 3) and op == 5:
            messages.extend(_bili_decode(chunk))      # 嵌套压缩包，递归解
            continue
        try:
            data = json.loads(chunk[head:])
        except (ValueError, UnicodeDecodeError):
            continue
        if isinstance(data, dict):
            messages.append(data)
    return messages


def _live_message_entry(message: dict, seconds: float) -> dict | None:
    """把一条直播消息压成统一结构；精简档只留普通弹幕，全部档另有礼物/上舰/SC。"""
    cmd = str(message.get("cmd") or "")
    text = ""
    kind = "danmaku"
    color = 0xFFFFFF
    size = 25
    mode_id = 1
    user = ""
    try:
        if cmd.startswith("DANMU_MSG"):
            info = message.get("info") or []
            text = str(info[1] or "")
            meta = info[0] or []
            mode_id = int(meta[1] or 1)
            size = int(meta[2] or 25)
            color = int(meta[3] or 0xFFFFFF) & 0xFFFFFF
            user = str((info[2] or [0, ""])[1] or "")
        elif cmd == "SEND_GIFT":
            data = message.get("data") or {}
            kind = "extra"
            text = f"【礼物】{data.get('uname') or ''} 送出 {data.get('giftName') or ''} ×{data.get('num') or 1}"
            color = 0xFFD700
        elif cmd == "SUPER_CHAT_MESSAGE":
            data = message.get("data") or {}
            kind = "extra"
            text = f"【醒目留言】{(data.get('user_info') or {}).get('uname') or ''}：{data.get('message') or ''}"
            color = 0x00A1FF
        elif cmd == "GUARD_BUY":
            data = message.get("data") or {}
            kind = "extra"
            text = f"【上舰】{data.get('username') or ''} 开通了 {data.get('gift_name') or '大航海'}"
            color = 0xFF6699
        elif cmd == "INTERACT_WORD":
            data = message.get("data") or {}
            kind = "extra"
            action = {1: "进入直播间", 2: "关注了主播", 3: "分享了直播间"}.get(
                int(data.get("msg_type") or 1), "进入直播间")
            text = f"【互动】{data.get('uname') or ''} {action}"
        else:
            return None
    except (IndexError, TypeError, ValueError):
        return None
    text = _DANMAKU_CTRL.sub("", text).replace("\r", " ").replace("\n", " ").strip()
    if not text:
        return None
    return {"t": round(max(0.0, seconds), 3), "cmd": cmd, "kind": kind, "text": text,
            "mode": mode_id, "size": size, "color": color, "user": user}


class _LiveDanmakuClient(threading.Thread):
    """一条常驻的弹幕连接：断线自动重连，消息写 JSONL（一条一行，边收边落盘）。"""

    def __init__(self, session: requests.Session, headers: dict, room_id: int,
                 jsonl_path: Path, started_at: float, log: Callable[[str], None]) -> None:
        super().__init__(name="live-danmaku", daemon=True)
        self.session = session
        self.headers = live_headers(headers)
        self.room_id = int(room_id)
        self.jsonl_path = jsonl_path
        self.started_at = started_at
        self.log = log
        self.count = 0
        self.handles: list = []
        self._stop = threading.Event()
        self._sock: socket.socket | None = None
        self._buvid = ""
        self._uid = 0
        self._token = ""
        self._host = LIVE_WS_HOST_FALLBACK

    def stop(self) -> None:
        self._stop.set()
        try:
            if self._sock:
                self._sock.close()
        except OSError:
            pass

    def _prepare(self) -> None:
        if not self._buvid:
            try:
                self.session.get("https://www.bilibili.com/", headers=self.headers, timeout=10)
            except Exception:
                pass
            self._buvid = next((c.value for c in self.session.cookies if c.name == "buvid3"), "")
        if not self._uid:
            try:
                data = api_get(self.session, API_NAV, {}, self.headers, 10.0)
                self._uid = int(data.get("mid") or 0)
            except Exception:
                self._uid = 0
        # 弹幕 token 必须 WBI 签名，且 roomid 要和取 token 时用的 id 一致，否则握手即被踢
        key = fetch_mixin_key(self.session, self.headers, 10.0)
        data = api_get(self.session, LIVE_DANMU_API, {"id": self.room_id},
                       self.headers, 10.0, mixin_key=key)
        self._token = str(data.get("token") or "")
        hosts = [str(item.get("host") or "") for item in data.get("host_list") or []]
        self._host = next((x for x in hosts if "broadcast" in x), hosts[0] if hosts else "") or \
            LIVE_WS_HOST_FALLBACK

    def _connect(self) -> socket.socket:
        host = self._host
        sock = socket.create_connection((host, 443), timeout=15)
        sock = ssl.create_default_context().wrap_socket(sock, server_hostname=host)
        cookie = "; ".join(f"{c.name}={c.value}" for c in self.session.cookies)
        key = base64.b64encode(os.urandom(16)).decode()
        request = (
            f"GET /sub HTTP/1.1\r\nHost: {host}\r\nUpgrade: websocket\r\n"
            f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n"
            f"Origin: {LIVE_HOME.rstrip('/')}\r\nCookie: {cookie}\r\n"
            f"User-Agent: {USER_AGENT}\r\n\r\n"
        )
        sock.sendall(request.encode())
        response = b""
        while b"\r\n\r\n" not in response:
            data = sock.recv(4096)
            if not data:
                raise DownloadError("弹幕连接被关闭")
            response += data
            if len(response) > 8192:
                break
        if b" 101 " not in response.split(b"\r\n")[0]:
            raise DownloadError(f"弹幕握手失败：{response.split(b'\r\n')[0][:80]!r}")
        return sock

    def _session_once(self) -> None:
        self._prepare()
        sock = self._connect()
        self._sock = sock
        auth = {
            "uid": self._uid, "roomid": self.room_id, "protover": 2,
            "platform": "web", "type": 2, "key": self._token,
        }
        if self._buvid:
            auth["buvid"] = self._buvid
        sock.sendall(_ws_frame(_bili_packet(7, json.dumps(auth).encode())))
        sock.settimeout(2.5)
        self.log("[弹幕] 已连接，开始接收（精简 / 全部两套都会存）")
        buffer = b""
        last_beat = time.monotonic()
        last_flush = time.monotonic()

        def flush() -> None:
            nonlocal last_flush
            for handle in self.handles:
                try:
                    handle.flush()
                except Exception:
                    pass
            last_flush = time.monotonic()

        try:
            while not self._stop.is_set():
                if time.monotonic() - last_beat >= 25:
                    try:
                        sock.sendall(_ws_frame(_bili_packet(2, b"[object Object]")))
                    except OSError:
                        break
                    last_beat = time.monotonic()
                try:
                    chunk = sock.recv(65536)
                except socket.timeout:
                    if time.monotonic() - last_flush >= 2:
                        flush()
                    continue
                if not chunk:
                    break
                buffer += chunk
                frames, buffer = _ws_parse(buffer)
                for opcode, payload in frames:
                    if opcode == 0x8:
                        raise DownloadError("弹幕连接被服务端关闭")
                    if opcode not in (0x1, 0x2):
                        continue
                    for message in _bili_decode(payload):
                        entry = _live_message_entry(message, time.monotonic() - self.started_at)
                        if not entry:
                            continue
                        line = json.dumps(entry, ensure_ascii=False)
                        for handle in self.handles:
                            handle.write(line + "\n")
                        self.count += 1
                if time.monotonic() - last_flush >= 2:
                    flush()
        finally:
            try:
                sock.close()
            except OSError:
                pass
            self._sock = None

    def run(self) -> None:
        self.jsonl_path.parent.mkdir(parents=True, exist_ok=True)
        # 追加模式：断线重连不覆盖之前已经收到的弹幕
        handle = open(self.jsonl_path, "a", encoding="utf-8")
        self.handles = [handle]
        try:
            while not self._stop.is_set():
                try:
                    self._session_once()
                except Exception as exc:
                    if self._stop.is_set():
                        break
                    self.log(f"[弹幕] 连接中断（{short_error(exc)}），3 秒后重连")
                if self._stop.wait(3):
                    break
        finally:
            try:
                handle.close()
            except Exception:
                pass


def _live_danmaku_lines(jsonl: Path, mode: str, duration: float) -> Iterable[dict]:
    """流式读 JSONL → 弹幕行；精简档做去重限流，全部档把礼物/SC 也当滚动弹幕渲染。"""
    seen: dict[int, set] = {}
    current_second = -1
    current_count = 0
    with open(jsonl, "r", encoding="utf-8") as handle:
        for raw in handle:
            try:
                item = json.loads(raw)
            except ValueError:
                continue
            stamp = float(item.get("t") or 0.0)
            if duration > 0:
                stamp = min(stamp, duration)
            text = _DANMAKU_CTRL.sub("", str(item.get("text") or "")).strip()
            if not text:
                continue
            if item.get("kind") != "danmaku":
                if mode != "full":
                    continue
                yield {"time": max(0.0, stamp), "mode": 1, "size": 25,
                       "color": int(item.get("color") or 0xFFFFFF), "text": text}
                continue
            mode_id = int(item.get("mode") or 1)
            if mode_id in (7, 8):
                continue
            if mode == "light":
                if mode_id == 6:
                    continue
                text = text[:DANMAKU_LIGHT_MAX_CHARS]
                bucket = int(stamp // DANMAKU_LIGHT_DEDUPE_WINDOW)
                for old in [key for key in seen if key < bucket - 1]:
                    seen.pop(old, None)
                group = seen.setdefault(bucket, set())
                key = (mode_id, text)
                if key in group:
                    continue
                group.add(key)
                second = int(stamp)
                if second != current_second:
                    current_second, current_count = second, 0
                if current_count >= DANMAKU_LIGHT_PER_SECOND:
                    continue
                current_count += 1
            yield {"time": max(0.0, stamp), "mode": mode_id,
                   "size": int(item.get("size") or 25),
                   "color": int(item.get("color") or 0xFFFFFF), "text": text}


def _write_danmaku_xml(lines: Iterable[dict], dest: Path, cid: int) -> int:
    dest.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with open(dest, "w", encoding="utf-8", newline="\n") as handle:
        handle.write('<?xml version="1.0" encoding="UTF-8"?><i>')
        handle.write(f"<chatid>{int(cid)}</chatid>")
        for line in lines:
            body = html.escape(str(line["text"]), quote=False)
            handle.write(f'<d p="{line["time"]:.3f},{line["mode"]},{line["size"]},'
                         f'{line["color"]},0,0,0,0">{body}</d>')
            count += 1
        handle.write("</i>")
    return count


class LiveRecorder:
    """一次直播录制：录制线程 + 弹幕线程 + 结束时的拼接 / 弹幕导出。

    内存模型：录制只持有一块读缓冲（256 KB）直接落盘；结束时用 ffmpeg concat -c copy 拼段，
    ffmpeg 自己也是流式读写的，所以录 10 小时和录 10 分钟占的内存一样。
    画质中途切换 = 关掉当前段、用新 qn 重开一段：各段参数不同就直接拼会失败，
    这时按画质分组分别封装成 MP4，绝不把几个小时的直播偷偷重编码一遍。
    """

    def __init__(self, session: requests.Session, headers: dict, room: dict, *,
                 out_dir: Path, qn: int = LIVE_DEFAULT_QN,
                 segment_minutes: int = LIVE_SEGMENT_MINUTES,
                 danmaku_light: bool = True, danmaku_full: bool = True,
                 keep_segments: bool = False,
                 log: Callable[[str], None] = emit,
                 auto_stop_offline: bool = True) -> None:
        self.session = session
        self.headers = headers
        self.room = room
        self.out_dir = Path(out_dir).expanduser()
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self._want_qn = int(qn)
        self._qn_now = int(qn)
        self.segment_seconds = max(60, int(segment_minutes) * 60)
        self.danmaku_light = bool(danmaku_light)
        self.danmaku_full = bool(danmaku_full)
        self.keep_segments = bool(keep_segments)
        self.log = log
        self.auto_stop_offline = bool(auto_stop_offline)
        stamp = time.strftime("%Y%m%d_%H%M%S")
        self.base = self.out_dir / f"{clean_name(room.get('title') or '直播')}_{stamp}_live"
        self.jsonl = self.base.with_name(f"{self.base.name}.danmaku.jsonl")
        self.segments: list[dict] = []
        self.total_bytes = 0
        self.started_at = 0.0
        self.finished_at = 0.0
        self.failures = 0
        self._stop = threading.Event()
        self._switch = threading.Event()
        self._thread: threading.Thread | None = None
        self._danmaku: _LiveDanmakuClient | None = None
        self._lock = threading.Lock()

    # ---- 状态 ----

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    @property
    def duration(self) -> float:
        if not self.started_at:
            return 0.0
        end = self.finished_at or time.monotonic()
        return max(0.0, end - self.started_at)

    def qn_label(self, qn: int | None = None) -> str:
        value = int(self._qn_now if qn is None else qn)
        return LIVE_QN_DESC.get(value, str(value))

    # ---- 生命周期 ----

    def start(self) -> None:
        self.started_at = time.monotonic()
        self._thread = threading.Thread(target=self._run, name="live-record", daemon=True)
        self._thread.start()
        if self.danmaku_light or self.danmaku_full:
            self._danmaku = _LiveDanmakuClient(
                self.session, self.headers, self.room["ref_id"], self.jsonl,
                self.started_at, self.log,
            )
            self._danmaku.start()

    def stop(self) -> None:
        self._stop.set()

    def switch_quality(self, qn: int) -> None:
        if int(qn) == self._want_qn and not self._switch.is_set():
            return
        self._want_qn = int(qn)
        self._switch.set()
        self.log(f"[直播] 画质切换为 {self.qn_label(qn)}（当前分段收尾后生效）")

    def wait(self, timeout: float | None = None) -> bool:
        if self._thread:
            self._thread.join(timeout)
        return not self.running

    def finish(self) -> dict:
        """停线程 → 导出弹幕 → 拼段。返回产物信息（失败也返回，由调用方展示）。"""
        self._stop.set()
        if self._thread:
            self._thread.join(20)
        if self._danmaku:
            self._danmaku.stop()
            self._danmaku.join(5)
        self.finished_at = time.monotonic()
        duration = self.duration
        result = {
            "base": self.base, "duration": duration, "bytes": self.total_bytes,
            "segments": [item["path"] for item in self.segments],
            "videos": [], "danmaku": {}, "error": "",
        }
        if self.jsonl.exists() and self.jsonl.stat().st_size > 0:
            width, height = probe_media_size(self.segments[0]["path"]) if self.segments else (1920, 1080)
            for mode, enabled in (("light", self.danmaku_light), ("full", self.danmaku_full)):
                if not enabled:
                    continue
                try:
                    xml = self.base.with_name(f"{self.base.name}.danmaku.{mode}.xml")
                    ass = self.base.with_name(f"{self.base.name}.danmaku.{mode}.ass")
                    xml_count = _write_danmaku_xml(
                        _live_danmaku_lines(self.jsonl, mode, duration), xml, self.room["room_id"])
                    ass_count = write_danmaku_ass(
                        _live_danmaku_lines(self.jsonl, mode, duration), ass, width, height,
                        str(self.room.get("title") or ""), strict=(mode == "light"))
                    result["danmaku"][mode] = {"xml": xml, "ass": ass, "count": xml_count,
                                               "ass_count": ass_count}
                except Exception as exc:
                    self.log(f"[弹幕] 导出{mode}失败：{short_error(exc)}")
        if self.segments:
            result["videos"] = self._merge_segments(result)
        return result

    # ---- 录制 ----

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                play = live_play_info(self.session, self.headers, self.room["ref_id"], self._want_qn)
                self._qn_now = int(play["qn"])
                self._stream(play)
                self.failures = 0
            except Aborted:
                break
            except Exception as exc:
                if self._stop.is_set():
                    break
                self.failures += 1
                self.log(f"[直播] 录制中断：{short_error(exc)}，2 秒后重连")
                if self._stop.wait(2):
                    break
                if self.auto_stop_offline and self.failures >= 2 and self._looks_offline():
                    self.log("[直播] 直播间已下播，自动结束录制")
                    break

    def _looks_offline(self) -> bool:
        try:
            return live_room_info(self.session, self.headers, self.room["ref_id"])["live_status"] != 1
        except Exception:
            return False

    def _open_segment(self) -> tuple[Path, object]:
        with self._lock:
            index = len(self.segments) + 1
            path = self.base.with_name(f"{self.base.name}_{index:04d}.flv")
            handle = open(path, "ab", buffering=0)
            self.segments.append({"path": path, "qn": self._qn_now})
        return path, handle

    def _stream(self, play: dict) -> None:
        last_error: Exception | None = None
        for url in play["urls"][:4]:
            if self._stop.is_set() or self._switch.is_set():
                return
            resp = None
            try:
                resp = self.session.get(url, headers=live_headers(self.headers),
                                        stream=True, timeout=(10, 35))
                if resp.status_code != 200:
                    raise DownloadError(f"HTTP {resp.status_code}")
                path, handle = self._open_segment()
                self.log(f"[直播] 录制中：{path.name}（{self.qn_label()} / {play['codec'].upper()}）")
                started = time.monotonic()
                try:
                    for chunk in resp.iter_content(LIVE_READ_CHUNK):
                        if self._stop.is_set() or self._switch.is_set():
                            break
                        if not chunk:
                            continue
                        handle.write(chunk)
                        self.total_bytes += len(chunk)
                        if time.monotonic() - started >= self.segment_seconds:
                            break
                finally:
                    handle.close()
                if self._switch.is_set():
                    self._switch.clear()
                return
            except Exception as exc:
                last_error = exc
                if self._stop.is_set():
                    return
                self.log(f"[直播] 这条流断开（{short_error(exc)}），换节点重试")
            finally:
                try:
                    if resp is not None:
                        resp.close()
                except Exception:
                    pass
        if last_error is not None:
            raise last_error

    # ---- 结束处理 ----

    def _concat(self, segments: list[dict], out: Path, err_msg: str) -> None:
        list_file = self.base.with_name(f"{self.base.name}.concat.txt")
        lines = []
        for item in segments:
            value = item["path"].as_posix().replace("'", "'\\''")
            lines.append(f"file '{value}'")
        list_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
        try:
            run_ffmpeg(["-f", "concat", "-safe", "0", "-i", str(list_file),
                        "-c", "copy", str(out)], err_msg)
            if not out.exists() or out.stat().st_size == 0:
                raise DownloadError(f"{err_msg}：输出为空")
        finally:
            try:
                list_file.unlink()
            except OSError:
                pass

    def _merge_segments(self, result: dict) -> list[Path]:
        out = self.base.with_name(f"{self.base.name}.mp4")
        try:
            self._concat(self.segments, out, "拼接直播分段失败")
            if not self.keep_segments:
                for item in self.segments:
                    try:
                        item["path"].unlink()
                    except OSError:
                        pass
            return [out]
        except Exception as exc:
            self.log(f"[直播] 合成一条失败（{short_error(exc)}），改按画质分段保存，不重编码")
        groups: list[list[dict]] = []
        for item in self.segments:
            if groups and groups[-1][-1]["qn"] == item["qn"]:
                groups[-1].append(item)
            else:
                groups.append([item])
        videos: list[Path] = []
        for index, group in enumerate(groups, 1):
            path = self.base.with_name(
                f"{self.base.name}.part{index}_{self.qn_label(group[0]['qn'])}.mp4")
            try:
                self._concat(group, path, "拼接直播分段失败")
                videos.append(path)
            except Exception as exc:
                self.log(f"[直播] 第 {index} 段封装失败：{short_error(exc)}（原 .flv 分段已保留）")
                result["error"] = "部分分段未能封装，已保留原始 .flv"
        if videos and not self.keep_segments and not result["error"]:
            for item in self.segments:
                try:
                    item["path"].unlink()
                except OSError:
                    pass
        return videos


class LiveScheduler(threading.Thread):
    """预约任务：按房间轮询 live_status，开播就回调（只回调一次，下播后重新武装）。"""

    def __init__(self, session: requests.Session, headers: dict,
                 tasks: Sequence[dict], on_live: Callable[[dict, dict], None],
                 log: Callable[[str], None] = emit, interval: int = LIVE_POLL_SECONDS) -> None:
        super().__init__(name="live-scheduler", daemon=True)
        self.session = session
        self.headers = headers
        self.tasks: list[dict] = [dict(item) for item in tasks]
        self.on_live = on_live
        self.log = log
        self.interval = max(20, int(interval))
        self._stop = threading.Event()
        self._armed: set[int] = set()
        self._lock = threading.Lock()

    def stop(self) -> None:
        self._stop.set()

    def set_tasks(self, tasks: Sequence[dict]) -> None:
        with self._lock:
            self.tasks = [dict(item) for item in tasks]

    def poll_once(self) -> None:
        with self._lock:
            tasks = [dict(item) for item in self.tasks]
        for task in tasks:
            if not task.get("enabled", True):
                continue
            room_id = int(task.get("room_id") or 0)
            if not room_id:
                continue
            try:
                info = live_room_info(self.session, self.headers, room_id, timeout=8.0)
            except Exception:
                continue
            if info["live_status"] != 1:
                self._armed.discard(room_id)
                continue
            if room_id in self._armed:
                continue
            self._armed.add(room_id)
            self.log(f"[预约] {info.get('uname') or room_id} 开播了：{info.get('title') or ''}")
            try:
                self.on_live(info, task)
            except Exception as exc:
                self.log(f"[预约] 自动录制启动失败：{short_error(exc)}")

    def run(self) -> None:
        while not self._stop.is_set():
            try:
                self.poll_once()
            except Exception as exc:
                self.log(f"[预约] 轮询出错：{short_error(exc)}")
            if self._stop.wait(self.interval):
                break


# ---- 字幕合并（独立功能：GUI 按钮 + 命令行）----

def merge_subtitle(video: Path, subtitle: Path, mode: str, out: Path | None = None) -> Path:
    """把字幕合进视频，产物另存，绝不覆盖原视频。

    mode：
        soft —— 封成 MKV（一条字幕轨，可开关，不重新编码）；
        hard —— 烧进画面（重新编码，慢，但任何播放器都看得见）。

    out 是“输出文件夹”：留空时产物放在原视频旁边；也可以直接给一个文件名（命令行兼容）。
    """
    video = Path(video).expanduser()
    subtitle = Path(subtitle).expanduser()
    if not video.is_file():
        raise DownloadError(f"视频不存在：{video}")
    if not subtitle.is_file():
        raise DownloadError(f"字幕文件不存在：{subtitle}")
    mode = (mode or "soft").lower()
    if mode not in {"soft", "hard"}:
        raise DownloadError("保存方式只能是 soft / hard")

    temp_dir: Path | None = None
    try:
        ass = subtitle
        if subtitle.suffix.lower() in {".xml", ".json"}:
            # 弹幕 XML / JSON 先转成 ASS；转好的文件放在临时目录，不污染用户目录
            temp_dir = Path(tempfile.mkdtemp(prefix="bd_sub_"))
            ass = temp_dir / "subtitle.ass"
            lines = parse_danmaku_xml(subtitle.read_bytes())
            if not lines:
                raise DownloadError("这个弹幕文件里没有可用的弹幕")
            width, height = probe_media_size(video)
            write_danmaku_ass(lines, ass, width, height, video.stem, strict=False)

        default_name = video.stem + (".sub.mkv" if mode == "soft" else ".sub.mp4")
        if out:
            target = Path(out).expanduser()
            # 给的是文件夹就按默认名放进去；直接给文件名（老命令行用法）则原样使用
            dest = target if (target.suffix and not target.is_dir()) else target / default_name
        else:
            dest = video.with_name(default_name)
        if dest.resolve() == video.resolve():
            raise DownloadError("输出文件不能和原视频同名（会覆盖原视频）")
        dest.parent.mkdir(parents=True, exist_ok=True)

        if mode == "soft":
            _ffmpeg_to_file(
                ["-i", str(video), "-i", str(ass), "-map", "0", "-map", "1",
                 "-c", "copy", "-c:s", "ass", "-metadata:s:s:0", "language=chi",
                 "-disposition:s:0", "default"],
                dest, "封装字幕失败")
            return dest

        burn_danmaku(video, ass, dest)
        return dest
    finally:
        if temp_dir is not None:
            shutil.rmtree(temp_dir, ignore_errors=True)


# ---- 系统托盘（仅 Windows；零依赖，用 ctypes 直接调 Shell_NotifyIcon）----

class _TrayIcon:
    """最小化到托盘：图标 + 右键菜单（显示主界面 / 录制直播 / 退出）。

    Tk 没有托盘 API，pystray 又要多带 Pillow，安装包会胖一圈；这里用 ctypes 起一个隐藏窗口
    接 Shell_NotifyIcon 的消息，回调统一丢回 Tk 主线程的队列里处理。
    """

    WM_TRAY = 0x0400 + 102          # WM_APP + 102
    WM_CLOSE = 0x0010

    def __init__(self, tooltip: str, post: Callable[[str], None]) -> None:
        self.tooltip = (tooltip or "B 站下载器")[:120]
        self.post = post
        self._thread: threading.Thread | None = None
        self._hwnd = 0
        self._proc = None
        self._nid = None

    def available(self) -> bool:
        return IS_WIN

    def start(self) -> None:
        if not self.available() or self._thread:
            return
        self._thread = threading.Thread(target=self._run, name="tray", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._hwnd:
            try:
                import ctypes
                ctypes.windll.user32.PostMessageW(self._hwnd, self.WM_CLOSE, 0, 0)
            except Exception:
                pass
        self._hwnd = 0

    def notify(self, title: str, message: str) -> None:
        """气泡提示（NIM_MODIFY + NIF_INFO）。失败就算了，不影响主流程。"""
        if not self._nid:
            return
        try:
            import ctypes
            from ctypes import wintypes

            class NOTIFYICONDATAW(ctypes.Structure):
                _fields_ = [
                    ("cbSize", wintypes.DWORD), ("hWnd", wintypes.HWND), ("uID", wintypes.UINT),
                    ("uFlags", wintypes.UINT), ("uCallbackMessage", wintypes.UINT),
                    ("hIcon", wintypes.HICON), ("szTip", wintypes.WCHAR * 128),
                    ("dwState", wintypes.DWORD), ("dwStateMask", wintypes.DWORD),
                    ("szInfo", wintypes.WCHAR * 256), ("uVersion", wintypes.UINT),
                    ("szInfoTitle", wintypes.WCHAR * 64), ("dwInfoFlags", wintypes.DWORD),
                    ("guidItem", wintypes.BYTE * 16), ("hBalloonIcon", wintypes.HICON),
                ]

            nid = NOTIFYICONDATAW.from_buffer_copy(self._nid)
            nid.uFlags = 0x10 | 0x2 | 0x1          # NIF_INFO | NIF_ICON | NIF_MESSAGE
            nid.hIcon = app_hicon() or nid.hIcon
            nid.szInfo = message[:250]
            nid.szInfoTitle = title[:60]
            nid.dwInfoFlags = 0x4                   # NIIF_USER：气泡用我们自己的图标
            nid.hBalloonIcon = app_hicon(32) or nid.hIcon
            ctypes.windll.shell32.Shell_NotifyIconW(1, ctypes.byref(nid))
        except Exception:
            pass

    def _popup(self, hwnd) -> None:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        user32.CreatePopupMenu.restype = wintypes.HMENU
        user32.AppendMenuW.argtypes = [wintypes.HMENU, wintypes.UINT,
                                       ctypes.c_size_t, wintypes.LPCWSTR]
        user32.AppendMenuW.restype = ctypes.c_int
        user32.TrackPopupMenu.argtypes = [wintypes.HMENU, wintypes.UINT, ctypes.c_int,
                                          ctypes.c_int, ctypes.c_int, wintypes.HWND,
                                          ctypes.c_void_p]
        user32.TrackPopupMenu.restype = ctypes.c_int
        user32.DestroyMenu.argtypes = [wintypes.HMENU]
        menu = user32.CreatePopupMenu()
        user32.AppendMenuW(menu, 0x0000, 1, "显示主界面")
        user32.AppendMenuW(menu, 0x0000, 2, "录制直播")
        user32.AppendMenuW(menu, 0x0800, 0, None)
        user32.AppendMenuW(menu, 0x0000, 3, "退出")
        user32.SetForegroundWindow(hwnd)
        point = ctypes.wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(point))
        command = user32.TrackPopupMenu(menu, 0x0002 | 0x0020 | 0x0100,
                                        point.x, point.y, 0, hwnd, None)
        user32.PostMessageW(hwnd, 0x0000, 0, 0)
        user32.DestroyMenu(menu)
        if command == 1:
            self.post("show")
        elif command == 2:
            self.post("live")
        elif command == 3:
            self.post("quit")

    def _run(self) -> None:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        shell32 = ctypes.windll.shell32
        IDI_APPLICATION = ctypes.cast(ctypes.c_void_p(32512), wintypes.LPCWSTR)

        # 64 位下必须显式声明签名：默认按 32 位 int 处理，句柄 / lParam 会被截断
        user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT,
                                          wintypes.WPARAM, wintypes.LPARAM]
        user32.DefWindowProcW.restype = ctypes.c_ssize_t
        user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR,
                                           wintypes.DWORD, ctypes.c_int, ctypes.c_int,
                                           ctypes.c_int, ctypes.c_int, wintypes.HWND,
                                           wintypes.HANDLE, wintypes.HINSTANCE,
                                           ctypes.c_void_p]
        user32.CreateWindowExW.restype = wintypes.HWND
        user32.RegisterClassW.argtypes = [ctypes.c_void_p]
        user32.RegisterClassW.restype = ctypes.c_ushort
        user32.LoadIconW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR]
        user32.LoadIconW.restype = wintypes.HICON
        user32.DestroyWindow.argtypes = [wintypes.HWND]
        user32.PostQuitMessage.argtypes = [ctypes.c_int]
        user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND,
                                       wintypes.UINT, wintypes.UINT]
        user32.GetMessageW.restype = ctypes.c_int
        user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
        user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
        user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT,
                                        wintypes.WPARAM, wintypes.LPARAM]
        user32.SetForegroundWindow.argtypes = [wintypes.HWND]
        shell32.Shell_NotifyIconW.argtypes = [wintypes.DWORD, ctypes.c_void_p]
        shell32.Shell_NotifyIconW.restype = ctypes.c_int

        class NOTIFYICONDATAW(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.DWORD), ("hWnd", wintypes.HWND), ("uID", wintypes.UINT),
                ("uFlags", wintypes.UINT), ("uCallbackMessage", wintypes.UINT),
                ("hIcon", wintypes.HICON), ("szTip", wintypes.WCHAR * 128),
                ("dwState", wintypes.DWORD), ("dwStateMask", wintypes.DWORD),
                ("szInfo", wintypes.WCHAR * 256), ("uVersion", wintypes.UINT),
                ("szInfoTitle", wintypes.WCHAR * 64), ("dwInfoFlags", wintypes.DWORD),
                ("guidItem", wintypes.BYTE * 16), ("hBalloonIcon", wintypes.HICON),
            ]

        WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT,
                                     wintypes.WPARAM, wintypes.LPARAM)

        class WNDCLASSW(ctypes.Structure):
            _fields_ = [
                ("style", wintypes.UINT), ("lpfnWndProc", WNDPROC),
                ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
                ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HICON),
                ("hCursor", wintypes.HANDLE), ("hbrBackground", wintypes.HBRUSH),
                ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR),
            ]

        @WNDPROC
        def proc(hwnd, message, wparam, lparam):
            if message == self.WM_TRAY:
                if int(lparam) == 0x0203:              # WM_LBUTTONDBLCLK
                    self.post("show")
                elif int(lparam) == 0x0205:            # WM_RBUTTONUP
                    self._popup(hwnd)
            elif message == self.WM_CLOSE:
                user32.DestroyWindow(hwnd)
                user32.PostQuitMessage(0)
                return 0
            return user32.DefWindowProcW(hwnd, message, wparam, lparam)

        self._proc = proc
        instance = kernel32.GetModuleHandleW(None)
        window_class = WNDCLASSW()
        window_class.lpfnWndProc = proc
        window_class.hInstance = instance
        window_class.hIcon = app_hicon(32) or user32.LoadIconW(None, IDI_APPLICATION)
        window_class.lpszClassName = f"BiliDownloaderTray_{os.getpid()}"
        if not user32.RegisterClassW(ctypes.byref(window_class)):
            return
        hwnd = user32.CreateWindowExW(0, window_class.lpszClassName, "BiliDownloaderTray",
                                      0, 0, 0, 0, 0, None, None, instance, None)
        if not hwnd:
            return
        self._hwnd = hwnd
        nid = NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        nid.hWnd = hwnd
        nid.uID = 1
        nid.uFlags = 0x1 | 0x2 | 0x4                       # MESSAGE | ICON | TIP
        nid.uCallbackMessage = self.WM_TRAY
        nid.hIcon = app_hicon() or user32.LoadIconW(None, IDI_APPLICATION)
        nid.szTip = self.tooltip
        self._nid = bytes(nid)
        shell32.Shell_NotifyIconW(0, ctypes.byref(nid))     # NIM_ADD

        message = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(message))
            user32.DispatchMessageW(ctypes.byref(message))
        shell32.Shell_NotifyIconW(2, ctypes.byref(nid))     # NIM_DELETE


# ================= 单个视频的处理流程 =================


@dataclass
class Stats:
    ok: int = 0
    skipped: int = 0
    failed: int = 0
    bytes_done: int = 0
    errors: list[tuple[str, str]] = field(default_factory=list)


def already_done(item: Item, want_mp4: bool, want_mp3: bool, *,
                 want_danmaku: bool = False, danmaku_video: str = "none") -> bool:
    """成品是否已经齐了。

    soft 模式的成品是 .mkv（mp4 被删掉了），所以判断"视频在不在"要按模式选文件，
    否则每次都以为没下过，白重下几百 MB。
    """
    def good(path: Path) -> bool:
        return path.exists() and path.stat().st_size > 0

    video_path = item.mkv if danmaku_video == "soft" else item.mp4
    if want_mp4 and not good(video_path):
        return False
    if want_mp3 and not good(item.mp3):
        return False
    if want_danmaku and not (good(item.danmaku_xml) and good(item.danmaku_ass)):
        return False
    return True


def process_item(session: requests.Session, item: Item, *, headers: dict,
                 stream_getter: Callable[[Item], dict], timeout: float = 15.0,
                 retries: int = 2, use_probe: bool = True,
                 want_mp4: bool = True, want_mp3: bool = True,
                 mp3_bitrate: str = "320", max_quality: int = 127,
                 force: bool = False, tag: str = "",
                 bar_position: int | None = None, bar_prefix: str = "",
                 quiet: bool = False,
                 max_reconnects: int = DEFAULT_MAX_RECONNECTS,
                 danmaku: str = "none", danmaku_video: str = "none") -> int:
    """下载并生成成品，返回新增文件的总字节数。

    已存在抛 FileExistsError（不算失败）；失败抛 DownloadError；被打断抛 Aborted。
    tag 用于多线程模式下标记输出行属于哪一项；bar_position 是该线程的进度条位置；
    bar_prefix 非空时进度条标题会带上"哪个视频的哪条流"；quiet 表示不要打印逐项标题行。
    danmaku 取 none/light/full；danmaku_video 取 none/soft/hard。
    """
    if _ABORT.is_set():
        raise Aborted("已取消")

    want_danmaku = danmaku in ("light", "full")
    if not force and already_done(item, want_mp4, want_mp3,
                                  want_danmaku=want_danmaku,
                                  danmaku_video=danmaku_video):
        emit(f"{tag}[跳过] 成品已存在（{item.out_dir.name}），不重新下载")
        raise FileExistsError("已存在")

    item.out_dir.mkdir(parents=True, exist_ok=True)
    dash = stream_getter(item)
    video = pick_video(dash, max_quality)
    audio = pick_audio(dash)
    picked = int(video.get("id", 0))
    quality = QUALITY_NAMES.get(picked, f"未知({picked})")
    if max_quality < 127 and picked < max_quality:
        quality += f"（低于请求上限 {QUALITY_NAMES.get(max_quality, max_quality)}）"
    elif picked <= 32:
        quality += "（游客或权限受限，通常是凭证失效/非大会员）"
    if not quiet:
        emit(f"{tag}画质 {quality}   音频 {audio.get('id')} "
             f"{int(audio.get('bandwidth', 0) / 1000)} kbps")

    # 进度条标题：并行模式下直接写出"哪个视频的哪条流"，省掉逐项标题行
    quality_short = quality.split(" ")[0]
    video_bar = f"{bar_prefix}{quality_short} 视频流" if bar_prefix else None
    audio_bar = f"{bar_prefix}音频流" if bar_prefix else None

    # 画面尺寸决定 ASS 的坐标系和字号；播放地址里就有，不必再探测
    frame_w = int(video.get("width") or 1920)
    frame_h = int(video.get("height") or 1080)

    def good(path: Path) -> bool:
        return path.exists() and path.stat().st_size > 0

    # 上次已经把 MP4 合好了、这次只是补弹幕（或补 MP3）时，不要再下一遍几百 MB 的流。
    # hard 模式例外：无法判断这个 mp4 是不是已经烧过弹幕，宁可重新合一次。
    reuse_video = (want_mp4 and not force and good(item.mp4)
                   and danmaku_video in ("none", "soft"))
    need_video_stream = want_mp4 and not reuse_video
    need_audio_stream = (not reuse_video) or (want_mp3 and not good(item.mp3))

    written = 0
    ok = False
    try:
        if need_video_stream:
            download_stream(session, video, item.video_m4s, "视频流",
                            headers=headers, retries=retries, timeout=timeout,
                            use_probe=use_probe, bar_position=bar_position,
                            prefix=tag, bar_desc=video_bar, max_reconnects=max_reconnects)
        if need_audio_stream:
            download_stream(session, audio, item.audio_m4s, "音频流",
                            headers=headers, retries=retries, timeout=timeout,
                            use_probe=use_probe, bar_position=bar_position,
                            prefix=tag, bar_desc=audio_bar, max_reconnects=max_reconnects)

        # ---- 弹幕：先拿 XML，再按"精简/多"筛，写成 XML + ASS ----
        danmaku_ready = False
        if want_danmaku or (want_mp4 and danmaku_video != "none"):
            try:
                raw_xml = fetch_danmaku_xml(session, headers, timeout, item.cid)
                all_lines = parse_danmaku_xml(raw_xml)
                chosen = filter_danmaku(all_lines, "full" if danmaku == "full" else "light")
                _write_text_atomic(item.danmaku_xml, danmaku_to_xml(chosen, item.cid))
                _write_text_atomic(item.danmaku_ass,
                                   build_danmaku_ass(chosen, frame_w, frame_h, item.label,
                                                     strict=(danmaku != "full")))
                danmaku_ready = True
                written += (item.danmaku_xml.stat().st_size
                            + item.danmaku_ass.stat().st_size)
                mode_text = "多" if danmaku == "full" else "精简"
                emit(f"{tag}[弹幕] {len(chosen)}/{len(all_lines)} 条（{mode_text}）"
                     f" → {item.danmaku_ass.name}")
            except Aborted:
                raise
            except Exception as exc:
                if danmaku_video != "none":
                    raise DownloadError(
                        f"弹幕获取失败，无法生成带弹幕的视频：{short_error(exc)}")
                emit(f"{tag}[弹幕] 获取失败（{short_error(exc)}），视频照常保存", err=True)

        if want_mp4:
            if need_video_stream:
                merge_av(item.video_m4s, item.audio_m4s, item.mp4)
            video_out = item.mp4
            if danmaku_ready and danmaku_video == "soft":
                mux_danmaku(item.mp4, item.danmaku_ass, item.mkv)
                try:
                    item.mp4.unlink()          # 成品只留带字幕轨的 MKV，不留重复的视频
                except OSError:
                    pass
                video_out = item.mkv
            elif danmaku_ready and danmaku_video == "hard":
                burn_danmaku(item.mp4, item.danmaku_ass, item.mp4)
                video_out = item.mp4
            written += video_out.stat().st_size
            note = "（含弹幕软字幕）" if danmaku_video == "soft" and danmaku_ready else (
                "（弹幕已烧进画面）" if danmaku_video == "hard" and danmaku_ready else "")
            emit(f"{tag}[完成] {video_out.name}（{human_size(video_out.stat().st_size)}）{note}")

        if want_mp3:
            export_mp3(item.audio_m4s, item.mp3, mp3_bitrate)
            written += item.mp3.stat().st_size
            emit(f"{tag}[完成] {item.mp3.name}（{human_size(item.mp3.stat().st_size)}）")
        ok = True
        return written
    finally:
        if ok:   # 成功才清理中间流文件；失败则保留，方便下次续传
            for temp in (item.video_m4s, item.audio_m4s):
                try:
                    temp.unlink(missing_ok=True)
                except OSError:
                    pass



# ================= 下载范围选择 =================


def parse_selection(text: str, total: int) -> list[int] | None:
    """解析"要下载哪些序号"。

    y / yes / all / 空      → 全部（1..total）
    n / no / q / quit       → None（不下载）
    其余按逗号分隔的序号或区间解析，如 "1,3,5,6-20"；
    重复、空项（"1,,3"）、空格、全角逗号都会自动忽略。
    解析失败抛 ValueError（调用方负责提示重输）。
    """
    raw = (text or "").strip().lower()
    if raw in {"", "y", "yes", "all", "a"}:
        return list(range(1, total + 1))
    if raw in {"n", "no", "q", "quit", "exit"}:
        return None

    picked: set[int] = set()
    for token in raw.replace("，", ",").replace("－", "-").split(","):
        token = token.strip()
        if not token:
            continue
        if "-" in token:
            left, _, right = token.partition("-")
            left, right = left.strip(), right.strip()
            if not (left.isdigit() and right.isdigit()):
                raise ValueError(f"看不懂的区间“{token}”，应形如 6-20")
            start, end = int(left), int(right)
            if start > end:
                start, end = end, start
            if start < 1 or end > total:
                raise ValueError(f"区间 {start}-{end} 超出范围 1-{total}")
            picked.update(range(start, end + 1))
        else:
            if not token.isdigit():
                raise ValueError(f"看不懂的序号“{token}”，只能是数字或区间")
            number = int(token)
            if not 1 <= number <= total:
                raise ValueError(f"序号 {number} 超出范围 1-{total}")
            picked.add(number)
    return sorted(picked)


def compact_ranges(numbers: Sequence[int]) -> str:
    """把 [1,2,3,5,6,9] 压成 "1-3,5-6,9"（回显用）。"""
    parts: list[str] = []
    start: int | None = None
    prev: int | None = None
    for number in sorted(numbers):
        if start is None:
            start = prev = number
        elif prev is not None and number == prev + 1:
            prev = number
        else:
            parts.append(f"{start}" if start == prev else f"{start}-{prev}")
            start = prev = number
    if start is not None:
        parts.append(f"{start}" if start == prev else f"{start}-{prev}")
    return ",".join(parts)


def ask_selection(total: int, attempts: int = 3) -> list[int] | None:
    """交互式挑选要下载的序号：返回序号列表；None 表示不下载。"""
    print(f"\n共 {total} 项。回车 / y = 全部下载，n = 不下载，"
          f"也可只下部分（如 1,3,5,6-20）：")
    while attempts > 0:
        try:
            raw = input("> ").strip()
        except EOFError:                     # 输入被关闭：按"全部"继续
            return list(range(1, total + 1))
        try:
            picked = parse_selection(raw, total)
        except ValueError as exc:
            attempts -= 1
            print(f"[!] {exc}" + ("" if attempts else "（多次无效输入，已取消）"))
            continue
        if picked is None:
            return None
        if not picked:
            print("[!] 没有选中任何项目，请重新输入")
            continue
        return picked
    return None


# ================= 命令行 =================


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """命令行参数。

    帮助文本按平台拼：ffmpeg 怎么装、凭证存哪儿、界面能不能开，三套系统答案不一样，
    写死一份等于让另外两个系统的用户自己猜。
    """
    if IS_WIN:
        ffmpeg_help = ("安装 ffmpeg 到 ~/ffmpeg 并写入用户 PATH（仅 Windows；"
                       "macOS / Linux 请用包管理器）")
        examples = (
            "示例：\n"
            "  bilibili_downloader                       打开图形界面\n"
            "  bilibili_downloader BV1xx411c7mD          下载单个视频\n"
            "  bilibili_downloader BV1xx411c7mD --single 只下当前分P\n"
            "  bilibili_downloader BV1xx411c7mD --dry-run\n"
            "  bilibili_downloader BV1xx411c7mD -q 720p --no-mp3\n"
            "  bilibili_downloader BV1xx411c7mD --danmaku full --danmaku-video soft\n"
            "  bilibili_downloader --install-ffmpeg --ffmpeg-source mirror\n"
        )
    else:
        pkg = "brew install ffmpeg" if IS_MAC else "sudo apt install ffmpeg"
        ffmpeg_help = f"自动安装 ffmpeg（仅 Windows；{PLATFORM_NAME} 用 {pkg}）"
        examples = (
            "示例：\n"
            "  bilibili_downloader                       打开图形界面\n"
            "  bilibili_downloader BV1xx411c7mD          下载单个视频\n"
            "  bilibili_downloader BV1xx411c7mD --single 只下当前分P\n"
            "  bilibili_downloader BV1xx411c7mD --dry-run\n"
            "  bilibili_downloader BV1xx411c7mD -q 720p --no-mp3\n"
            "  bilibili_downloader BV1xx411c7mD --danmaku full --danmaku-video soft\n"
            f"  {pkg}" + ("" if IS_MAC else "   # 先装 ffmpeg") + "\n"
        )
    class _HelpFormatter(argparse.RawDescriptionHelpFormatter,
                         argparse.ArgumentDefaultsHelpFormatter):
        """保留 epilog 里的换行（示例要一行一条，不能被 argparse 压成一段）。"""

    parser = argparse.ArgumentParser(
        description=(f"B 站视频 / 分P / 合集下载器（DASH 分流 + ffmpeg 合并 + 弹幕）"
                     f" · 当前系统 {PLATFORM_NAME}"),
        epilog=examples + "图形界面同一时间只跑一个实例；带参数的命令行调用不受限制，可并发。",
        formatter_class=_HelpFormatter,
    )
    parser.add_argument("inputs", nargs="*",
                        help="视频链接 / BV 号 / av 号，可给多个；不填则交互式输入")
    parser.add_argument("-o", "--output", default=str(default_output()),
                        help="保存根目录（默认桌面）")
    parser.add_argument("-q", "--quality", default="max",
                        choices=sorted(QUALITY_LIMITS), help="允许的最高画质")
    parser.add_argument("--mp3-bitrate", default="320", choices=["128", "192", "256", "320"],
                        help="导出 MP3 的码率 kbps")
    parser.add_argument("--audio-only", action="store_true", help="只导出 MP3（不下载视频流）")
    parser.add_argument("--no-mp3", action="store_true", help="只保存 MP4")
    parser.add_argument("--danmaku", default="light", choices=["none", "light", "full"],
                        help="下载弹幕：none 不下载 / light 精简（去重限流）/ full 多（保留全部可用类型）")
    parser.add_argument("--danmaku-video", default="none", choices=["none", "soft", "hard"],
                        help="把弹幕放进视频：none 不嵌入 / soft 封成 MKV 软字幕（快，可开关）"
                             " / hard 烧进 MP4 画面（重新编码，慢但哪都能看）")
    parser.add_argument("--single", action="store_true",
                        help="只下载输入链接指向的那一个视频/分P（忽略合集）")
    parser.add_argument("--force", action="store_true", help="已存在也重新下载")
    parser.add_argument("--reset-sessdata", action="store_true",
                        help="忽略已保存的凭证，重新交互式输入")
    parser.add_argument("-j", "--jobs", type=int, default=4, choices=(1, 2, 3, 4),
                        help="并发下载线程数（最多 4；1 = 串行并显示实时进度条）")
    parser.add_argument("--max-reconnects", type=int, default=DEFAULT_MAX_RECONNECTS,
                        metavar="N",
                        help="单个流因“速度掉到历史平均 30%% 以下”而重开连接的次数上限（0 = 关闭）")
    parser.add_argument("--no-probe", action="store_true", help="关闭节点优选探测")
    parser.add_argument("--retries", type=int, default=2, help="每个节点重试次数")
    parser.add_argument("--timeout", type=float, default=15.0, help="网络超时（秒）")
    parser.add_argument("--dry-run", action="store_true", help="只列出计划，不下载")
    parser.add_argument("--install-ffmpeg", action="store_true", help=ffmpeg_help)
    parser.add_argument("--ffmpeg-source", choices=FFMPEG_SOURCES, default="auto",
                        help="ffmpeg 下载源：auto=官方→镜像→gyan 依次回退（默认），"
                             "official=只走 GitHub 官方，mirror=走 ghfast.top 镜像")
    parser.add_argument("--gui", action="store_true",
                        help="打开图形界面（不带任何参数运行时默认就是图形界面）")
    parser.add_argument("--live", action="store_true",
                        help="直接打开「录制直播」窗口（图形界面功能，命令行不录制直播）")
    parser.add_argument("--merge-sub", nargs=2, metavar=("VIDEO", "SUB"),
                        help="把字幕 / 弹幕合并进视频，产物另存，不覆盖原视频")
    parser.add_argument("--sub-mode", choices=("soft", "hard"), default="soft",
                        help="字幕保存方式：soft=软字幕（封装 MKV，可开关），"
                             "hard=硬字幕（烧进画面，重新编码）")
    parser.add_argument("--merge-out", default="",
                        help="输出文件夹（留空=与原视频同目录），产物按 <视频名>.sub.mkv / .sub.mp4 命名")
    parser.add_argument("-y", "--yes", action="store_true", help="不询问，直接开始")
    args = parser.parse_args(argv)

    if args.audio_only and args.no_mp3:
        parser.error("--audio-only 与 --no-mp3 不能同时使用")
    if args.retries < 1:
        parser.error("--retries 至少为 1")
    if args.timeout <= 0:
        parser.error("--timeout 必须大于 0")
    if args.danmaku_video != "none":
        if args.danmaku == "none":
            parser.error("--danmaku-video 需要同时下载弹幕：去掉 --danmaku none")
        if args.audio_only:
            parser.error("--danmaku-video 需要视频流：--audio-only 模式下无法把弹幕放进视频")
    return args


def _cancelled() -> int:
    """Ctrl+C 的收尾：一句人话 + 退出码 130，绝不打 traceback。"""
    print("\n[中断] 已取消；已下载的部分会保留，重新运行可续传。")
    return 130


def _handle_missing_ffmpeg(args: argparse.Namespace) -> None:
    """没有 ffmpeg 时先打招呼：能装就当场问一句，不能装就给出可复制的命令。

    以前只在合并那一步报错，用户已经下完几百 MB 的流才发现白干；
    现在一开始就说清楚"没有它会缺哪些功能"，Windows 上复用 --install-ffmpeg 的逻辑，
    macOS / Linux 直接给出包管理器命令（不再白跑一次网络探测）。
    """
    if args.dry_run:
        return                                  # 只看计划，不需要 ffmpeg
    print("[!] 没有检测到 ffmpeg。缺少它无法合并音视频、导出 MP3，也无法把弹幕放进视频"
          "（下载只会留下分离的 .m4s 流文件）。")
    if not IS_WIN:
        hint = ("brew install ffmpeg" if IS_MAC else
                "sudo apt install ffmpeg（Debian/Ubuntu）/ sudo dnf install ffmpeg（Fedora）")
        print(f"    请先安装：{hint}")
        return

    _, size = resolve_ffmpeg_archive()
    shown = human_size(size) if size else f"约 {FFMPEG_FALLBACK_MB} MB"
    if not _is_interactive(args):
        print(f"    可运行 bilibili_downloader --install-ffmpeg 自动安装到 ~/ffmpeg"
              f"（大小：{shown}），或手动安装后重跑。")
        return

    try:
        answer = input(f"    现在下载安装到 ~/ffmpeg（大小：{shown}）？[Y/n] ").strip().lower()
    except EOFError:
        answer = "n"
    if answer in {"n", "no"}:
        print("    已跳过；合并/导出会在最后一步失败，装好 ffmpeg 后再跑即可。")
        return
    try:
        print(install_ffmpeg())
    except DownloadError as exc:
        print(f"[失败] {short_error(exc)}")


def main(argv: Sequence[str] | None = None) -> int:
    """入口：不带参数 → 图形界面；带参数 → 命令行流程（一个功能都没少）。

    图形界面加了单实例互斥：同一时间只允许一个界面（Windows 用命名互斥体，
    macOS / Linux 用 flock），避免两个实例抢同一个直播录制任务、写坏配置文件。
    **带参数的命令行调用不受限制**——批处理里一次起十个下载任务是完全正常的用法。
    """
    raw = list(sys.argv[1:] if argv is None else argv)
    gui_only = (not raw) or raw == ["--gui"]
    gui_live = bool(raw) and all(item in ("--live", "--gui") for item in raw) and "--live" in raw
    if gui_only or gui_live:
        handle = _single_instance_handle()
        if handle is None:
            if _focus_existing_window("B 站视频下载器"):
                print("[提示] 已经有一个界面在运行，已为你切回那个窗口。")
            else:
                print("[提示] 已经有一个界面在运行；请先关掉它，或从托盘图标唤回。")
            return 0
        _INSTANCE_HANDLE.append(handle)      # 句柄要活到进程结束，不能提前释放
        return run_gui(start_live=gui_live)
    try:
        return _main_impl(raw)
    except KeyboardInterrupt:
        return _cancelled()
    except Exception as exc:              # 兜底：不让用户看到 traceback
        print(f"\n[失败] {short_error(exc, limit=300)}", file=sys.stderr)
        return 1


def _main_impl(argv: Sequence[str] | None = None) -> int:
    global FFMPEG_SOURCE
    _setup_console()
    args = parse_args(argv)
    FFMPEG_SOURCE = args.ffmpeg_source      # 命令行选定的 ffmpeg 源，后续安装都用它

    if args.install_ffmpeg:              # 独立动作：装完就结束，不进入下载流程
        try:
            print(install_ffmpeg())
            print("    新开的终端里可以直接使用 ffmpeg（当前进程也已生效）。")
            return 0
        except DownloadError as exc:
            print(f"[失败] {short_error(exc, limit=300)}")
            return 1

    if not ffmpeg_available():
        _handle_missing_ffmpeg(args)

    if args.merge_sub:                   # 独立动作：合并字幕进视频，做完就结束
        video, subtitle = args.merge_sub
        try:
            output = Path(args.merge_out).expanduser() if args.merge_out else None
            result = merge_subtitle(Path(video), Path(subtitle), args.sub_mode, output)
            print(f"[完成] 已保存到：{result}")
            return 0
        except DownloadError as exc:
            print(f"[失败] {short_error(exc, limit=300)}")
            return 1

    session = build_session()
    sessdata, headers = ensure_credential(session, args)

    inputs = [x for x in (args.inputs or []) if x.strip()]
    if not inputs:
        if not _is_interactive(args):
            print("[失败] 没有给出要下载的链接/BV 号，且当前是非交互模式（-y 或输出被重定向）。")
            print("    用法：bilibili_downloader <链接或BV号> [选项]，"
                  "例如 bilibili_downloader BV1xx411c7mD --single")
            return 2
        try:
            raw = input("请输入 B 站视频链接 / BV 号（多个用空格分隔）：")
        except EOFError:
            print("没有收到输入")
            return 2
        inputs = [x for x in raw.split() if x.strip()]
    if not inputs:
        print("输入不能为空")
        return 2

    root = Path(args.output).expanduser()
    want_mp4 = not args.audio_only
    want_mp3 = not args.no_mp3

    print("正在获取视频信息…")
    try:
        items = build_plan(session, headers, inputs, root=root,
                           single=args.single, timeout=args.timeout)
    except KeyboardInterrupt:
        print("\n已取消")
        return 130
    except DownloadError as exc:
        print(f"[失败] {short_error(exc, limit=300)}")
        return 1

    if not items:
        print("[!] 没有找到可下载的内容")
        return 1

    print(f"\n计划下载 {len(items)} 项 → {root.resolve()}")
    for index, item in enumerate(items, 1):
        try:
            shown = item.out_dir.relative_to(root)
        except ValueError:
            shown = item.out_dir
        print(f"  {index:>3}. {shown}{os.sep}{item.label}")

    if args.dry_run:
        print("\n（--dry-run：未下载）")
        return 0

    if len(items) > 1 and (_SELECTION_CALLBACK is not None or _is_interactive(args)):
        if _SELECTION_CALLBACK is not None:
            picked = _SELECTION_CALLBACK(len(items), items)
        else:
            picked = ask_selection(len(items))
        if picked is None:
            print("已取消")
            return 0
        if len(picked) < len(items):
            print(f"[选择] 已选 {len(picked)}/{len(items)} 项：{compact_ranges(picked)}")
            selected = [(i, items[i - 1]) for i in picked]
        else:
            selected = list(enumerate(items, 1))
    else:
        selected = list(enumerate(items, 1))

    total = len(selected)

    stats = Stats()
    started = time.time()
    _ABORT.clear()                       # 允许同一进程内重复调用 main()
    _reset_progress()

    workers = max(1, min(args.jobs, total))
    # 终端里每个下载线程一条进度条（4 线程 = 4 条堆叠）；输出被重定向时退回"每 15 秒一行"
    use_bars = bool(getattr(sys.stdout, "isatty", lambda: False)())
    quiet = use_bars and workers > 1   # 并行+进度条：底部 4 行就是实时表，不再逐项刷标题
    if use_bars:
        _bars_active.set()

    def stream_getter(item: Item) -> dict:
        _throttle_api()                  # 接口调用串行 + 最小间隔，避免触发风控
        return fetch_streams(session, headers, args.timeout, item.bvid, item.cid)

    # 进度条标题会和"百分比/大小/速度/剩余时间"抢同一行宽度：按终端宽度给标题算预算，
    # 宽终端显示更长的标题，窄终端收短标题（并先丢掉最不重要的"第几个/共几个"），
    # 把宽度尽量留给进度条本身，避免计数和速度被挤掉。
    term_cols = shutil.get_terminal_size((100, 24)).columns
    head_cols = 22 if term_cols >= 84 else 12
    label_budget = max(6, min(24, term_cols - head_cols - 70))

    def work(position: int, origin: int, item: Item) -> int:
        tag = f"#{origin} "              # 用清单里的原始序号，方便对照上面那份列表
        if not quiet:
            emit(f"\n[{position}/{total}] {item.label}")
        slot = _claim_bar_slot() if use_bars else None
        if quiet:
            head = (f"[{position}/{total}] #{origin} " if term_cols >= 84
                    else f"#{origin} ")
            bar_prefix = f"{head}{_clip(item.label, label_budget)} · "
        else:
            bar_prefix = ""
        return process_item(
            session, item, headers=headers, stream_getter=stream_getter,
            timeout=args.timeout, retries=args.retries,
            use_probe=not args.no_probe, want_mp4=want_mp4, want_mp3=want_mp3,
            mp3_bitrate=args.mp3_bitrate,
            max_quality=QUALITY_LIMITS[args.quality], force=args.force,
            tag=tag, bar_position=slot, bar_prefix=bar_prefix, quiet=quiet,
            max_reconnects=args.max_reconnects,
            danmaku=args.danmaku, danmaku_video=args.danmaku_video,
        )

    emit(f"\n开始下载（{workers} 个线程）…")

    aborted = False
    aborting = False                     # 已被 Ctrl+C 打断：收尾时绝不再等下载线程
    pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="dl")
    futures = {pool.submit(work, position, origin, item): (origin, item)
               for position, (origin, item) in enumerate(selected, 1)}
    try:
        # 用"带超时的轮询"而不是 as_completed 的无限等待：主线程每 0.3 秒都会回到
        # 字节码层处理挂起的信号，否则在 Windows 上卡在无限等待里会收不到 Ctrl+C。
        pending = set(futures)
        while pending:
            done, pending = futures_wait(pending, timeout=0.3)
            for future in done:
                origin, item = futures[future]
                try:
                    stats.bytes_done += future.result()
                    stats.ok += 1
                except FileExistsError:
                    stats.skipped += 1
                except Aborted:
                    aborted = True       # 用户中断：不计入失败
                except Exception as exc:  # 单个文件失败不影响整批
                    stats.failed += 1
                    stats.errors.append((item.label, short_error(exc, limit=400)))
                    emit(f"#{origin} [失败] {short_error(exc)}", err=True)
    except KeyboardInterrupt:
        request_abort()
        aborting = True
        emit("\n[中断] 已停止下载；已下载的 .part/.m4s 会保留，重跑即续传。", err=True)
        pool.shutdown(wait=False, cancel_futures=True)
        _hard_exit(130)                  # 不再等下载线程，直接退出（不返回）
    finally:
        pool.shutdown(wait=not aborting, cancel_futures=True)
    _bars_active.clear()                 # 收工后再用普通输出打总结

    elapsed = time.time() - started
    emit(f"\n[结果] 成功 {stats.ok} / 跳过 {stats.skipped} / 失败 {stats.failed}"
         f"，新增 {human_size(stats.bytes_done)}，用时 {elapsed:.1f} 秒")
    if stats.errors:
        emit("[结果] 失败明细：")
        for label, reason in stats.errors[:20]:
            emit(f"  - {label}：{reason}")
        if len(stats.errors) > 20:
            emit(f"  …另有 {len(stats.errors) - 20} 项，详见上方日志")
    emit(f"保存目录：{root.resolve()}")
    if aborted:
        emit("[中断] 已停止；已下载的 .part/.m4s 会保留，重跑即续传。")
        return 130
    return 1 if stats.failed else 0


# ================= 图形界面 =================
#
# 界面只负责"收集参数"，真正的下载、弹幕、ffmpeg 全部复用 _main_impl：
# 两套入口共用一条代码路径，命令行有任何改动界面自动跟上，不会出现
# "界面上能选、命令行不认" 这种两套逻辑各写一半的老问题。

GUI_QUALITY = {
    "最高（跟随账号权限）": "max",
    "8K": "8k",
    "4K": "4k",
    "1080P60": "1080p60",
    "1080P+": "1080p+",
    "1080P": "1080p",
    "720P60": "720p60",
    "720P": "720p",
    "480P": "480p",
    "360P": "360p",
}
GUI_DANMAKU = {
    "不下载": "none",
    "精简（去重限流，推荐）": "light",
    "多（保留全部可用类型）": "full",
}
GUI_EMBED = {
    "不嵌入": "none",
    "软字幕（MKV，秒级完成）": "soft",
    "硬字幕（烧进画面，重新编码）": "hard",
}

GUI_HELP_TEXT = """B 站视频下载器 · 图形界面帮助

【基本用法】
1. 把视频链接、BV 号或 av 号粘到左上角的输入框，多个用空格或换行分隔。
   支持普通投稿、多 P（分 P）视频和合集；b23.tv 短链也能识别。
2. 点"读取分集"，右侧列出这次要下载的清单（每一项对应一个视频文件夹），
   在清单里勾选要下载的分集；"全选 / 全不选"一键操作，单击任意一行也能切换勾选。
   也可以在"序号"框里直接写（例如 1,3-5,49-234），回车或点"应用"就按这个范围勾选；
   反过来勾选变化时，这个框会自动同步成紧凑写法。
3. 选好保存位置、画质和弹幕等选项，按"开始下载"。
   下载日志在右下角"运行日志"里滚动显示。

【分集预览】
· 读取清单只取视频信息，不会下载任何内容；换了链接或改了"只下当前"之类的开关要重读一次。
· 勾选结果与最终计划一致时，"开始下载"就按勾选的那些项下；对不上（例如换了链接）
  会弹一个对话框让你再选一次，避免下错东西。
· 一项都没勾就点开始，会提示先勾选。
· 序号框支持逗号、空格、顿号和区间：1,3,5-20；勾选与文本双向同步，改哪边另一边都跟着变。
· 时长取自接口，多 P / 合集里个别条目可能显示 00:00。

【下载选项】
· 画质：默认"最高（跟随账号权限）"。没登录一般只有 480P/720P；
  登录且是大会员才能拿到 1080P+ / 4K / 8K / HDR。
· MP3 码率：128 / 192 / 256 / 320 kbps，只在导出 MP3 时生效。
· 输出内容：
    视频 + MP3 —— 默认，两个都留；
    仅视频    —— 等同 --no-mp3；
    仅 MP3    —— 等同 --audio-only（不下载视频流）。
· 弹幕：
    不下载 —— 不取弹幕；
    精简   —— 去掉同一句话的刷屏重复、跳过逆向弹幕、超长截断、每秒限量，
             车道占满时直接丢掉那条，绝不压字；
    多     —— 保留全部能渲染的类型（滚动/顶部/底部/逆向），不去重不限流，
             车道不够时宁可轻微重叠也不丢。
  弹幕会存成两个文件：<名字>.danmaku.xml（原始）和 <名字>.danmaku.ass（可直接挂载）。
· 弹幕进视频：
    不嵌入 —— 视频保持 MP4，弹幕只作为旁边的文件；
    软字幕 —— 封成 MKV，弹幕是一条字幕轨，播放器里可以开关，不重新编码、几秒完成；
    硬字幕 —— 把弹幕烧进画面，重新编码（慢、体积变大），但任何播放器/手机都看得见。
  注：高级弹幕（模式 7）和代码弹幕（模式 8）无法用 ASS 还原，两种模式都会跳过。

【高级选项】
· 并发线程：1~4。4 个视频同时下（每个线程一条进度条）。
· 每个节点重试次数：同一条流在同一个 CDN 节点失败几次才换节点。
· 网络超时：单次请求的秒数，网络差可以调到 30。
· 重连上限：速度掉到自身历史平均 30% 以下并持续 10 秒时，丢掉连接换节点续传的次数；
  0 表示关闭该检测。
· 只下当前视频 / 分P：等同 --single，输入链接指向哪个就只下哪个，忽略合集。
· 已存在也重新下载：等同 --force。
· 关闭节点优选探测：等同 --no-probe，省一次并发 HEAD。
· 只看计划不下载：等同 --dry-run，只列出会下载哪些项目。
· 重新输入凭证：等同 --reset-sessdata，忽略已保存的 SESSDATA 重新输入。

【凭证 SESSDATA】
可选，决定的是"画质上限"，不是速度：不填就是游客，通常最高 480P/720P、没有无损音频；
填了才能按账号权限拿 1080P+ / 4K / 8K / HDR 和 Hi-Res。
点"保存并校验"会按当前系统的方式保存——Windows 写用户环境变量，macOS / Linux 写
~/.config/bilibili-downloader/sessdata（权限 600），并立刻用账号接口校验一次，
以后所有终端和新开的程序都能自动读取（输入框可以留空）。
卡片里的黑色区域像终端一样显示当前状态：游客模式（没读到凭证）/ 已读取待校验 /
已登录有效 / 凭证已失效（下载会自动回退游客画质）。
已经读到有效凭证时，输入框会收起，改成"更换 / 清除"两个按钮。
获取方法：浏览器登录 B 站 → F12 → Application → Cookies → bilibili.com → 复制 SESSDATA。
它等同账号登录凭证，不要发给别人；怀疑泄露就去 B 站"退出所有设备"。

【ffmpeg】
合并音视频、导出 MP3、给视频加弹幕都依赖 ffmpeg。窗口里会显示是否已找到；
没有时点"安装 ffmpeg"：Windows 会先把实际大小告诉你，再让你选下载源
（官方源 / ghfast.top 镜像源），装到 ~/ffmpeg 并加入用户 PATH；首选源连不上会自动换另一个。
macOS / Linux 不做自动下载，点这个按钮会给出对应的 brew / apt / dnf 命令。
也可以命令行运行 bilibili_downloader --install-ffmpeg（仅 Windows）。

【保存结构】
默认保存到桌面：<桌面>/<视频标题>/<视频标题>.mp4（软字幕模式则是 .mkv）、.mp3、
.danmaku.xml、.danmaku.ass；多 P 和合集会多一层目录，规则与命令行完全一致。
路径分隔符随系统（Windows 是反斜杠，macOS / Linux 是斜杠），文件名里不合法的字符会自动替换。

【界面没有的东西】
本界面覆盖了全部下载选项；脚本/批处理场景请用命令行。
同一时间只允许一个界面实例（再次双击会提醒你已经开着）；带参数的命令行调用不受限制。

使用 -h/--help 查看命令行帮助"""


def gui_help_text() -> str:
    """图形界面帮助正文：通用部分 + 当前系统专属的一段。

    帮助里最容易被漏掉的就是"这段话只说 Windows"——macOS / Linux 用户照着找环境变量、
    照着重启资源管理器，只会更糊涂。所以平台相关的几行单独拼在末尾。
    """
    if IS_WIN:
        extra = (
            "\n【当前系统：Windows】\n"
            "· 控制台默认 GBK，日志里的特殊字符会降级成 ?，不影响下载。\n"
            "· 最小化到托盘后，双击托盘图标或右键「显示主界面」都能把窗口叫回来。\n"
            "· 凭证保存在用户环境变量 BILI_SESSDATA（命令行 setx 也能改）。\n"
            "· ffmpeg 可以在界面里一键下载安装，装到 ~/ffmpeg 并写入用户 PATH。\n"
        )
    elif IS_MAC:
        extra = (
            "\n【当前系统：macOS】\n"
            "· 关闭窗口等于退出；想让后台继续跑，用「最小化到托盘」旁边的系统黄点最小化。\n"
            "· 凭证保存在 ~/.config/bilibili-downloader/sessdata（权限 600）。\n"
            "· ffmpeg 用 Homebrew 安装：brew install ffmpeg。\n"
            "· 首次运行若提示“无法验证开发者”，右键应用 → 打开，或在"
            "「系统设置 → 隐私与安全性」里放行。\n"
        )
    else:
        extra = (
            "\n【当前系统：Linux】\n"
            "· 托盘图标取决于桌面环境（GNOME 需要 AppIndicator 扩展）；没有托盘时"
            "「最小化到托盘」按钮退化为普通最小化。\n"
            "· 凭证保存在 ~/.config/bilibili-downloader/sessdata（权限 600）。\n"
            "· ffmpeg 用包管理器安装：sudo apt install ffmpeg / sudo dnf install ffmpeg。\n"
            "· 无图形环境（纯 SSH）时请直接用命令行，界面会提示 tkinter 不可用。\n"
        )
    return GUI_HELP_TEXT + extra


class _GuiStream:
    """把 print / tqdm 的输出塞进队列。

    tkinter 控件只能在主线程改，而 _main_impl 跑在工作线程里，所以这里只入队，
    由主线程的定时器搬运到日志框。
    """

    def __init__(self, put: Callable[[str], None]) -> None:
        self._put = put

    def write(self, text: str) -> None:
        if text:
            self._put(str(text))

    def flush(self) -> None:
        pass

    def isatty(self) -> bool:
        return False

    def fileno(self) -> int:
        raise OSError("图形界面没有 stdout 文件描述符")


def _fmt_duration(seconds) -> str:
    total = max(0, int(seconds or 0))
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes:02d}:{secs:02d}"


def _enable_dpi_awareness() -> None:
    """在创建任何窗口之前声明 DPI 感知，避免 150% 缩放下整窗被虚拟化后超出屏幕。

    不开这个开关时 Windows 会把进程按 96dpi 虚拟化，Tk 以为自己是 1588 逻辑像素宽，
    实际只映射到 1073 物理像素，右边和底部的控件就被切掉了。
    """
    if not IS_WIN:
        return
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        # PER_MONITOR_AWARE_V2 = -4；失败说明进程已经设置过，忽略即可
        try:
            user32.SetProcessDpiAwarenessContext.argtypes = [wintypes.HANDLE]
            user32.SetProcessDpiAwarenessContext.restype = wintypes.BOOL
            if user32.SetProcessDpiAwarenessContext(wintypes.HANDLE(-4)):
                return
        except Exception:
            pass
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
            return
        except Exception:
            pass
        user32.SetProcessDPIAware()
    except Exception:
        pass


_enable_dpi_awareness()


def run_gui(start_live: bool = False) -> int:
    """不带参数运行时的图形界面（浅色圆角风格 + 分集预览）。

    界面只负责"收集参数"和"挑要下哪几集"，真正的下载、弹幕、ffmpeg 仍然走 _main_impl；
    分集清单用 build_plan 预先取一次，勾选结果通过 _SELECTION_CALLBACK 原样交回去，
    所以不会出现"界面一套逻辑、命令行另一套"的问题。

    三套系统共用这一份界面：字体名、图标格式、托盘能力在平台段里定，
    这里只根据 IS_WIN / IS_MAC / IS_LINUX 决定"能不能开、藏到哪里"。
    start_live=True 时（--live 启动参数）只把「录制直播」窗口打开，主界面收起来。
    """
    try:
        import queue
        import tkinter as tk
        from tkinter import filedialog, messagebox, ttk
        import tkinter.font as tkfont
    except Exception as exc:                     # 没有 tkinter（精简版 Python / 无显示环境）
        print(f"[!] 图形界面不可用（tkinter 加载失败：{short_error(exc)}）", file=sys.stderr)
        print("    命令行功能不受影响：bilibili_downloader -h", file=sys.stderr)
        return 2

    if IS_LINUX and not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        # 纯 SSH / 无头服务器：Tk 连不上显示服务，再往下走只会抛 "no display name"
        print("[!] 当前没有图形环境（DISPLAY / WAYLAND_DISPLAY 都没有设置）", file=sys.stderr)
        print("    纯命令行用法：bilibili_downloader <链接> -o <目录>", file=sys.stderr)
        return 2

    if IS_WIN:                          # 高分屏下别让界面糊成一片
        try:
            import ctypes

            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass

    global _SELECTION_CALLBACK

    # ---- 缩放 ----
    # Tk 的字体按“点”算，会跟着系统缩放变大，但控件的宽高、间距全是像素，
    # 于是 150% 下文字变大、盒子没变，按钮上的字就被切掉。这里把界面尺寸
    # 统一折算成“逻辑像素”：字体改用负值（负数=像素），几何数字全部过 px()，
    # 这样任何缩放比例下“字 / 盒子 / 间距”都按同一比例放大。
    root = tk.Tk()
    SCALE = root.winfo_fpixels("1i") / 96.0

    def px(value: float) -> int:
        """96 dpi 下的逻辑尺寸 → 当前缩放下的物理像素。"""
        return max(1, int(round(value * SCALE)))

    def make_combo(parent, variable, values):
        """按最长选项的实际像素宽度做下拉框。

        ttk.Combobox 的 width 单位是"字符"（一个汉字算两个），而且放进 grid
        里会被列宽挤压成"只剩一个箭头"。这里把它装进一个固定宽度的容器里，
        再让下拉框填满容器，宽度就完全由文字实测值决定，不受列宽影响。
        """
        measure = tkfont.Font(root=root, font=body_font)
        width = max(measure.measure(str(v)) for v in values) + px(34)
        holder = tk.Frame(parent, bg=GUI_CARD, width=width, height=px(34))
        holder.grid_propagate(False)
        box = ttk.Combobox(holder, textvariable=variable, values=values, state="readonly")
        box.pack(fill="both", expand=True)
        return holder

    body_font = (GUI_FONT_FAMILY, -px(14))
    small_font = (GUI_FONT_FAMILY, -px(12))
    bold_font = (GUI_FONT_FAMILY, -px(14), "bold")
    title_font = (GUI_FONT_FAMILY, -px(24), "bold")
    mono_font = (MONO_FONT_FAMILY, -px(12))

    # ---- 浅色圆角小部件：tkinter 没有圆角，这里自己画（配色沿用 Win11，三平台一致）----

    GUI_BG = "#F3F3F3"          # 窗口底色（Win11 浅色模式的"云母"近似色）
    GUI_CARD = "#FFFFFF"        # 卡片
    GUI_BORDER = "#E3E3E3"      # 卡片描边
    GUI_TEXT = "#1B1B1B"
    GUI_SUB = "#6A6A6A"
    GUI_ACCENT = "#0067C0"      # Win11 强调色
    GUI_ACCENT_HOVER = "#1976D2"
    GUI_ACCENT_PRESS = "#005394"
    GUI_SELECT = "#E5F1FB"      # 列表选中底色


    def _round_polygon(canvas, x1, y1, x2, y2, radius, **kwargs):
        """用平滑多边形凑出圆角矩形（ttk 没有圆角，只能画）。"""
        r = max(0, min(radius, (x2 - x1) // 2, (y2 - y1) // 2))
        points = [
            x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
            x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
            x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
        ]
        return canvas.create_polygon(points, smooth=True, **kwargs)


    class _RoundedButton(tk.Canvas):
        """Win11 手感按钮：圆角、悬停变浅、按下变深、禁用变灰。"""

        KINDS = {
            # 常态、悬停、按下、禁用、文字色、描边
            "accent": (GUI_ACCENT, GUI_ACCENT_HOVER, GUI_ACCENT_PRESS, "#B7D3EA", "#FFFFFF", GUI_ACCENT),
            "secondary": ("#FFFFFF", "#F5F5F5", "#EBEBEB", "#F7F7F7", GUI_TEXT, "#DCDCDC"),
            "ghost": (GUI_BG, "#EAEAEA", "#DFDFDF", "#F2F2F2", "#444444", GUI_BG),
        }

        def __init__(self, master, text, command=None, kind="secondary", width=None,
                     height=32, radius=6, font=None, enabled=True):
            fill, hover, press, disabled, fg, outline = self.KINDS[kind]
            self._font = font or small_font
            import tkinter.font as tkfont
            measure = tkfont.Font(font=self._font)
            # 宽度按文字实测值算（中文字符比等宽估算宽得多，写死会切字），
            # 显式给的 width 也当作最小宽度，缩放后仍保证文字完整。
            need = measure.measure(text) + px(30)
            h = px(height)
            # 竖向也要留够行高，否则高 DPI 下上下被切
            h = max(h, measure.metrics("linespace") + px(12))
            w = max(px(width) if width else need, need) if width else need
            super().__init__(master, width=w, height=h, bg=master["bg"],
                             highlightthickness=0, bd=0, takefocus=0)
            self._colors = (fill, hover, press, disabled, fg, outline)
            self._command = command
            self._enabled = enabled
            self._hover = False
            self._press = False
            self._text = text
            self._radius = px(radius)
            self._redraw()
            self.bind("<Enter>", self._on_enter)
            self.bind("<Leave>", self._on_leave)
            self.bind("<ButtonPress-1>", self._on_press)
            self.bind("<ButtonRelease-1>", self._on_release)
            self.configure(cursor="hand2" if enabled else "arrow")

        # -- 内部 --
        def _redraw(self) -> None:
            self.delete("all")
            fill, hover, press, disabled, fg, outline = self._colors
            if not self._enabled:
                bg, fg_now = disabled, "#FFFFFF" if self._colors[0] == GUI_ACCENT else "#9A9A9A"
            elif self._press:
                bg, fg_now = press, fg
            elif self._hover:
                bg, fg_now = hover, fg
            else:
                bg, fg_now = fill, fg
            w = int(self["width"])
            h = int(self["height"])
            _round_polygon(self, 1, 1, w - 1, h - 1, self._radius, fill=bg,
                           outline=outline, width=1)
            self.create_text(w / 2, h / 2, text=self._text, fill=fg_now, font=self._font)

        def _on_enter(self, _event=None):
            self._hover = True
            if self._enabled:
                self._redraw()

        def _on_leave(self, _event=None):
            self._hover = False
            self._press = False
            self._redraw()

        def _on_press(self, _event=None):
            if self._enabled:
                self._press = True
                self._redraw()

        def _on_release(self, _event=None):
            was = self._press
            self._press = False
            self._redraw()
            if was and self._enabled and self._command:
                self._command()

        # -- 对外 --
        def set_enabled(self, enabled: bool) -> None:
            self._enabled = bool(enabled)
            self.configure(cursor="hand2" if enabled else "arrow")
            self._redraw()


    class _Card(tk.Canvas):
        """白色圆角卡片，内容放在 .body 里（body 就是普通的 tk.Frame）。"""

        def __init__(self, master, height=150, radius=10, padding=14):
            super().__init__(master, height=px(height), bg=master["bg"],
                             highlightthickness=0, bd=0)
            self._radius = px(radius)
            self._padding = px(padding)
            self.body = tk.Frame(self, bg=GUI_CARD)
            self._window = self.create_window(self._padding, self._padding,
                                              anchor="nw", window=self.body)
            self.bind("<Configure>", self._on_resize)

        def fit(self):
            """把画布尺寸收到内容实际需要的大小（tk 画布默认宽度会撑爆布局）。

            高度只保留内容需要的部分：多出来的空白交给 grid 的行权重去分配，
            否则高缩放下几张卡片的最小高度相加就会超过屏幕，底部按钮被切掉。
            """
            self.body.update_idletasks()
            width = self.body.winfo_reqwidth() + self._padding * 2
            height = self.body.winfo_reqheight() + self._padding * 2
            self.configure(width=max(width, px(240)), height=height)

        def _on_resize(self, _event=None):
            w = max(2, self.winfo_width())
            h = max(2, self.winfo_height())
            self.delete("card")
            _round_polygon(self, 1, 1, w - 1, h - 1, self._radius, fill=GUI_CARD,
                           outline=GUI_BORDER, width=1, tags="card")
            self.tag_lower("card")
            pad = self._padding
            self.itemconfigure(self._window, width=max(1, w - pad * 2),
                               height=max(1, h - pad * 2))

    root.title("B 站视频下载器")
    apply_window_icon(root)
    root.configure(bg=GUI_BG)
    root.minsize(px(980), px(660))
    screen_w, screen_h = root.winfo_screenwidth(), root.winfo_screenheight()
    width = min(px(1240), max(px(980), screen_w - px(160)))
    height = min(px(900), max(px(700), screen_h - px(120)))
    root.geometry(f"{width}x{height}+{(screen_w - width) // 2}+{max(24, (screen_h - height) // 3)}")
    try:
        root.option_add("*Font", body_font)
    except Exception:
        pass

    style = ttk.Style(root)
    try:
        style.theme_use("clam")                  # clam 才允许自定义配色
    except Exception:
        pass
    style.configure(".", background=GUI_BG, foreground=GUI_TEXT, font=body_font)
    style.configure("TCombobox", fieldbackground="#FFFFFF", background="#FFFFFF",
                    foreground=GUI_TEXT, bordercolor=GUI_BORDER, arrowcolor=GUI_TEXT,
                    padding=(px(8), px(5)))
    style.map("TCombobox", fieldbackground=[("readonly", "#FFFFFF")],
              bordercolor=[("focus", GUI_ACCENT)])
    style.configure("TCheckbutton", background=GUI_CARD, foreground=GUI_TEXT,
                    focuscolor=GUI_CARD, font=small_font)
    style.map("TCheckbutton", background=[("active", GUI_CARD)])
    style.configure("Adv.TCheckbutton", background=GUI_BG, foreground=GUI_SUB,
                    focuscolor=GUI_BG, font=small_font)
    style.map("Adv.TCheckbutton", background=[("active", GUI_BG)])
    style.configure("TRadiobutton", background=GUI_CARD, foreground=GUI_TEXT,
                    focuscolor=GUI_CARD, font=small_font)
    style.map("TRadiobutton", background=[("active", GUI_CARD)])
    style.configure("TSpinbox", fieldbackground="#FFFFFF", background="#FFFFFF",
                    foreground=GUI_TEXT, bordercolor=GUI_BORDER, arrowcolor=GUI_TEXT,
                    padding=(px(6), px(3)))
    style.configure("Win.Treeview", background="#FFFFFF", fieldbackground="#FFFFFF",
                    foreground=GUI_TEXT, borderwidth=0, rowheight=px(32),
                    font=small_font)
    style.configure("Win.Treeview.Heading", background="#FFFFFF", foreground=GUI_SUB,
                    relief="flat", font=(GUI_FONT_FAMILY, -px(12), "bold"),
                    padding=(px(6), px(5)))
    style.map("Win.Treeview", background=[("selected", GUI_SELECT)],
              foreground=[("selected", GUI_TEXT)])
    style.configure("Win.Horizontal.TProgressbar", troughcolor="#E9E9E9",
                    background=GUI_ACCENT, bordercolor="#E9E9E9",
                    lightcolor=GUI_ACCENT, darkcolor=GUI_ACCENT, thickness=px(5))
    style.configure("Win.Vertical.TScrollbar", background="#F0F0F0",
                    troughcolor="#FFFFFF", bordercolor="#FFFFFF", arrowcolor=GUI_SUB,
                    width=px(14))

    # ---------------- 顶部标题 ----------------
    header = tk.Frame(root, bg=GUI_BG)
    header.pack(fill="x", padx=px(18), pady=(px(12), px(6)))
    tk.Label(header, text="B 站视频下载器", font=title_font, bg=GUI_BG,
             fg=GUI_TEXT).pack(side="left")
    tk.Label(header, text="DASH 音视频 · 弹幕 · MKV 软字幕 / 烧录", font=small_font,
             bg=GUI_BG, fg=GUI_SUB).pack(side="left", padx=(px(12), 0), pady=(px(7), 0))

    # ---------------- 主体两栏 ----------------
    main = tk.Frame(root, bg=GUI_BG)
    # 先不 pack：底部按钮条要先占住窗口底部，否则窗口一矮就被挤出屏幕
    main.columnconfigure(0, weight=5)
    main.columnconfigure(1, weight=4)
    main.rowconfigure(0, weight=1)

    left_wrap = tk.Frame(main, bg=GUI_BG)
    left_wrap.grid(row=0, column=0, sticky="nsew", padx=(0, px(10)))
    left_wrap.rowconfigure(0, weight=1)
    left_wrap.columnconfigure(0, weight=1)
    left_canvas = tk.Canvas(left_wrap, bg=GUI_BG, highlightthickness=0, bd=0, height=1)
    left_bar = ttk.Scrollbar(left_wrap, orient="vertical", command=left_canvas.yview,
                             style="Win.Vertical.TScrollbar")
    left_canvas.configure(yscrollcommand=left_bar.set)
    left_canvas.grid(row=0, column=0, sticky="nsew")
    left = tk.Frame(left_canvas, bg=GUI_BG)
    left_window = left_canvas.create_window(0, 0, anchor="nw", window=left)
    left_canvas.bind("<Configure>", lambda event: left_canvas.itemconfigure(left_window, width=event.width))

    def auto_left_bar() -> None:
        """左栏内容比视口高时才出现滚动条（高缩放下高级选项展开就是这种情况）。"""
        try:
            if left.winfo_reqheight() > left_canvas.winfo_height() + 1:
                left_bar.grid(row=0, column=1, sticky="ns")
            else:
                left_bar.grid_remove()
                left_canvas.yview_moveto(0)
        except tk.TclError:
            pass

    left.bind("<Configure>", lambda event: (left_canvas.configure(scrollregion=left_canvas.bbox("all")),
                                            auto_left_bar()))

    def left_wheel(event):
        """滚轮落在左栏任意控件上时滚动左栏（高缩放下需要滑动才能看到凭证卡片）。

        三套系统的滚轮事件不一样：Windows / macOS 走 <MouseWheel>（delta 有正负、
        macOS 是触摸板惯性小数值），Linux X11 走 <Button-4>/<Button-5>，没有 delta。
        所以这里把"向上滚"统一成 +1，事件绑定时各自换算好再进来。
        """
        step = getattr(event, "_bd_step", 0)
        if not step:
            step = 1 if event.delta > 0 else -1
        widget = root.winfo_containing(event.x_root, event.y_root)
        inside = False
        while widget is not None:
            if widget is left or widget is left_canvas:
                inside = True
                break
            widget = getattr(widget, "master", None)
        if not inside:
            return None
        left_canvas.yview_scroll(-step, "units")
        return "break"

    root.bind_all("<MouseWheel>", left_wheel, add="+")
    if IS_LINUX:                     # X11 的滚轮是按键事件，不补上就滚不动
        def wheel_button(event, step):
            event._bd_step = step
            return left_wheel(event)

        root.bind_all("<Button-4>", lambda e: wheel_button(e, 1), add="+")
        root.bind_all("<Button-5>", lambda e: wheel_button(e, -1), add="+")
    right = tk.Frame(main, bg=GUI_BG)
    right.grid(row=0, column=1, sticky="nsew")

    # ---------------- 链接 ----------------
    left.columnconfigure(0, weight=1)
    left.rowconfigure(0, weight=3)          # 链接卡片吃掉多余高度
    left.rowconfigure(1, weight=2)
    left.rowconfigure(2, weight=0)
    left.rowconfigure(3, weight=0)
    left.rowconfigure(4, weight=0)

    link_card = _Card(left, height=168)
    link_card.grid(row=0, column=0, sticky="nsew", pady=(0, px(10)))
    lb = link_card.body
    lb_head = tk.Frame(lb, bg=GUI_CARD)
    lb_head.pack(fill="x", pady=(0, px(6)))
    tk.Label(lb_head, text="视频链接 / BV 号 / av 号", font=bold_font, bg=GUI_CARD,
             fg=GUI_TEXT).pack(side="left")
    tk.Label(lb_head, text="普通投稿 / 多 P / 合集",
             font=small_font, bg=GUI_CARD, fg=GUI_SUB).pack(side="left", padx=(px(8), 0), pady=(px(3), 0))
    url_text = tk.Text(lb, width=1, height=2, wrap="word", font=mono_font, relief="flat",
                       bg="#FAFAFA", fg=GUI_TEXT, insertbackground=GUI_TEXT,
                       highlightthickness=1, highlightbackground=GUI_BORDER,
                       highlightcolor=GUI_ACCENT)
    url_text.pack(fill="both", expand=True)

    link_row = tk.Frame(lb, bg=GUI_CARD)
    link_row.pack(fill="x", pady=(px(10), 0))
    read_btn = _RoundedButton(link_row, "读取分集", kind="accent", command=lambda: read_plan())
    read_btn.pack(side="left")
    _RoundedButton(link_row, "粘贴", kind="ghost", width=64,
                   command=lambda: paste_link()).pack(side="left", padx=(px(6), 0))
    _RoundedButton(link_row, "清空", kind="ghost", width=64,
                   command=lambda: url_text.delete("1.0", "end")).pack(side="left", padx=(px(6), 0))
    tk.Label(link_row, text="先读清单再勾选", font=small_font,
             bg=GUI_CARD, fg=GUI_SUB).pack(side="left", padx=(px(10), 0))

    # ---------------- 下载选项 ----------------
    opt_card = _Card(left, height=210)
    opt_card.grid(row=1, column=0, sticky="nsew", pady=(0, px(10)))
    ob = opt_card.body
    ob.columnconfigure(1, weight=1)

    tk.Label(ob, text="保存到", font=bold_font, bg=GUI_CARD, fg=GUI_TEXT).grid(
        row=0, column=0, sticky="w", pady=(0, px(8)))
    out_var = tk.StringVar(value=str(default_output()))
    out_row = tk.Frame(ob, bg=GUI_CARD)
    out_row.grid(row=0, column=1, columnspan=5, sticky="ew", pady=(0, px(8)))
    tk.Entry(out_row, textvariable=out_var, font=small_font, relief="flat",
             bg="#FAFAFA", fg=GUI_TEXT, insertbackground=GUI_TEXT,
             highlightthickness=1, highlightbackground=GUI_BORDER,
             highlightcolor=GUI_ACCENT).pack(side="left", fill="x", expand=True, padx=(px(8), px(8)))
    _RoundedButton(out_row, "打开", kind="ghost", width=58, height=28,
                   command=lambda: open_folder(out_var.get())).pack(side="right")
    _RoundedButton(out_row, "浏览", kind="ghost", width=58, height=28,
                   command=lambda: browse_dir()).pack(side="right", padx=(0, px(6)))

    tk.Label(ob, text="画质", font=bold_font, bg=GUI_CARD, fg=GUI_TEXT).grid(
        row=1, column=0, sticky="w")
    quality_var = tk.StringVar(value="最高（跟随账号权限）")
    # 下拉框不再"拉伸填满"：列被挤压时它连自己需要的宽度都保不住，
    # 于是只显示一个箭头、文字被切掉。改成按内容宽度、左对齐。
    quality_box = make_combo(ob, quality_var, list(GUI_QUALITY))
    quality_box.grid(row=1, column=1, columnspan=5, sticky="w",
                     padx=(px(8), 0), pady=(px(8), 0))
    tk.Label(ob, text="MP3 码率", font=bold_font, bg=GUI_CARD, fg=GUI_TEXT).grid(
        row=2, column=0, sticky="w", pady=(px(8), 0))
    bitrate_var = tk.StringVar(value="320")
    make_combo(ob, bitrate_var, ["128", "192", "256", "320"]).grid(
        row=2, column=1, columnspan=5, sticky="w", padx=(px(8), 0), pady=(px(8), 0))

    tk.Label(ob, text="输出", font=bold_font, bg=GUI_CARD, fg=GUI_TEXT).grid(
        row=3, column=0, sticky="w", pady=(px(10), 0))
    mode_var = tk.StringVar(value="both")
    mode_row = tk.Frame(ob, bg=GUI_CARD)
    mode_row.grid(row=3, column=1, columnspan=5, sticky="w", pady=(px(10), 0))
    for text, value in (("视频 + MP3", "both"), ("仅视频", "video"), ("仅 MP3", "audio")):
        ttk.Radiobutton(mode_row, text=text, value=value, variable=mode_var,
                        style="TRadiobutton").pack(side="left", padx=(0, px(16)))

    tk.Label(ob, text="弹幕", font=bold_font, bg=GUI_CARD, fg=GUI_TEXT).grid(
        row=4, column=0, sticky="w", pady=(px(10), 0))
    danmaku_var = tk.StringVar(value="精简（去重限流，推荐）")
    make_combo(ob, danmaku_var, list(GUI_DANMAKU)).grid(
        row=4, column=1, columnspan=5, sticky="w", padx=(px(8), 0), pady=(px(10), 0))
    tk.Label(ob, text="放进视频", font=bold_font, bg=GUI_CARD, fg=GUI_TEXT).grid(
        row=5, column=0, sticky="w", pady=(px(10), 0))
    embed_var = tk.StringVar(value="不嵌入")
    make_combo(ob, embed_var, list(GUI_EMBED)).grid(
        row=5, column=1, columnspan=5, sticky="w", padx=(px(8), 0), pady=(px(10), 0))

    # ---------------- 凭证（终端风格，按状态切换界面） ----------------
    cred_card = _Card(left, height=104)
    cred_card.grid(row=2, column=0, sticky="nsew", pady=(0, px(10)))
    cb = cred_card.body
    cb.columnconfigure(0, weight=1)

    cb_head = tk.Frame(cb, bg=GUI_CARD)
    cb_head.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, px(6)))
    tk.Label(cb_head, text="登录凭证 SESSDATA（可选）", font=bold_font, bg=GUI_CARD,
             fg=GUI_TEXT).pack(side="left")
    tk.Label(cb_head, text="只影响画质上限，与速度无关",
             font=small_font, bg=GUI_CARD, fg=GUI_SUB).pack(side="left", padx=(px(8), 0), pady=(px(3), 0))

    # 像终端一样的状态窗：未读取 / 待校验 / 有效 / 已失效 各显示不同内容
    console = tk.Text(cb, height=2, width=1, wrap="word", relief="flat", font=mono_font,
                      bg="#1E1E1E", fg="#D4D4D4", padx=px(10), pady=px(6),
                      highlightthickness=0, bd=0, state="disabled")
    console.grid(row=1, column=0, columnspan=2, sticky="ew")
    console.tag_configure("ok", foreground="#6DD58C")
    console.tag_configure("warn", foreground="#E2C07A")
    console.tag_configure("err", foreground="#F07B6B")
    console.tag_configure("dim", foreground="#9A9A9A")

    cred = {"value": "", "state": "none", "source": ""}

    input_row = tk.Frame(cb, bg=GUI_CARD)
    input_row.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(px(8), 0))
    input_row.columnconfigure(0, weight=1)
    sess_var = tk.StringVar()
    sess_entry = tk.Entry(input_row, textvariable=sess_var, show="•", font=small_font,
                          relief="flat", bg="#FAFAFA", fg=GUI_TEXT, insertbackground=GUI_TEXT,
                          highlightthickness=1, highlightbackground=GUI_BORDER,
                          highlightcolor=GUI_ACCENT)
    sess_entry.grid(row=0, column=0, sticky="ew")
    _RoundedButton(input_row, "保存并校验", kind="ghost", width=86, height=28,
                   command=lambda: save_cred()).grid(row=0, column=1, padx=(px(8), 0))

    manage_row = tk.Frame(cb, bg=GUI_CARD)
    manage_row.columnconfigure(0, weight=1)
    mask_label = tk.Label(manage_row, text="", font=mono_font, bg=GUI_CARD,
                          fg=GUI_TEXT, anchor="w")
    mask_label.grid(row=0, column=0, sticky="w")
    _RoundedButton(manage_row, "更换", kind="ghost", width=58, height=28,
                   command=lambda: show_entry()).grid(row=0, column=1, padx=(px(8), 0))
    _RoundedButton(manage_row, "清除", kind="ghost", width=58, height=28,
                   command=lambda: clear_cred()).grid(row=0, column=2, padx=(px(8), 0))

    # ---------------- 高级选项（默认收起） ----------------
    adv_state = tk.BooleanVar(value=False)
    adv_toggle = ttk.Checkbutton(left, text="高级选项（并发、重试、超时、探测、强制重下…）",
                                 variable=adv_state, style="Adv.TCheckbutton",
                                 command=lambda: toggle_adv())
    adv_toggle.grid(row=3, column=0, sticky="w", pady=(0, px(6)))
    adv_card = _Card(left, height=150)
    # 先不显示，勾上才 grid（见 toggle_adv）

    ab = adv_card.body
    ab.columnconfigure(1, weight=1)
    ab.columnconfigure(3, weight=1)
    jobs_var = tk.IntVar(value=4)
    retries_var = tk.IntVar(value=2)
    timeout_var = tk.DoubleVar(value=15.0)
    reconn_var = tk.IntVar(value=DEFAULT_MAX_RECONNECTS)

    tk.Label(ab, text="并发线程", font=bold_font, bg=GUI_CARD, fg=GUI_TEXT).grid(
        row=0, column=0, sticky="w")
    ttk.Spinbox(ab, from_=1, to=4, textvariable=jobs_var, width=5).grid(
        row=0, column=1, sticky="w", padx=(px(8), px(16)))
    tk.Label(ab, text="节点重试", font=bold_font, bg=GUI_CARD, fg=GUI_TEXT).grid(
        row=0, column=2, sticky="w")
    ttk.Spinbox(ab, from_=1, to=10, textvariable=retries_var, width=5).grid(
        row=0, column=3, sticky="w", padx=(px(8), 0))

    tk.Label(ab, text="超时（秒）", font=bold_font, bg=GUI_CARD, fg=GUI_TEXT).grid(
        row=1, column=0, sticky="w", pady=(px(8), 0))
    ttk.Spinbox(ab, from_=1, to=180, increment=1, textvariable=timeout_var, width=5).grid(
        row=1, column=1, sticky="w", padx=(px(8), px(16)), pady=(px(8), 0))
    tk.Label(ab, text="重连上限", font=bold_font, bg=GUI_CARD, fg=GUI_TEXT).grid(
        row=1, column=2, sticky="w", pady=(px(8), 0))
    ttk.Spinbox(ab, from_=0, to=30, textvariable=reconn_var, width=5).grid(
        row=1, column=3, sticky="w", padx=(px(8), 0), pady=(px(8), 0))

    single_var = tk.BooleanVar(value=False)
    force_var = tk.BooleanVar(value=False)
    no_probe_var = tk.BooleanVar(value=False)
    dry_var = tk.BooleanVar(value=False)
    reset_var = tk.BooleanVar(value=False)

    checks = tk.Frame(ab, bg=GUI_CARD)
    checks.grid(row=2, column=0, columnspan=4, sticky="w", pady=(px(10), 0))
    for index, (text, variable) in enumerate((
        ("只下当前视频 / 分P", single_var),
        ("已存在也重新下载", force_var),
        ("关闭节点优选探测", no_probe_var),
        ("只看计划不下载", dry_var),
        ("重新输入凭证", reset_var),
    )):
        ttk.Checkbutton(checks, text=text, variable=variable,
                        style="TCheckbutton").grid(row=index // 3, column=index % 3,
                                                   sticky="w", padx=(0, px(16)), pady=px(1))

    def toggle_adv() -> None:
        if adv_state.get():
            adv_card.grid(row=4, column=0, sticky="nsew", pady=(0, px(10)))
        else:
            adv_card.grid_remove()

    # ---------------- 分集预览 ----------------
    right.columnconfigure(0, weight=1)
    right.rowconfigure(0, weight=3)
    right.rowconfigure(1, weight=2)

    preview_card = _Card(right, height=250)
    preview_card.grid(row=0, column=0, sticky="nsew", pady=(0, px(10)))
    pb = preview_card.body
    pb.rowconfigure(2, weight=1)
    pb.columnconfigure(0, weight=1)

    head = tk.Frame(pb, bg=GUI_CARD)
    head.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, px(8)))
    tk.Label(head, text="分集预览", font=bold_font, bg=GUI_CARD, fg=GUI_TEXT).pack(side="left")
    count_var = tk.StringVar(value="还没有读取清单")
    tk.Label(head, textvariable=count_var, font=small_font, bg=GUI_CARD,
             fg=GUI_SUB).pack(side="left", padx=(px(10), 0))
    _RoundedButton(head, "全不选", kind="secondary", width=64, height=26,
                   command=lambda: set_all(False)).pack(side="right", padx=(px(6), 0))
    _RoundedButton(head, "全选", kind="secondary", width=58, height=26,
                   command=lambda: set_all(True)).pack(side="right")
    _RoundedButton(head, "应用序号", kind="secondary", width=76, height=26,
                   command=lambda: apply_pick_text()).pack(side="right", padx=(0, px(8)))

    pick_row = tk.Frame(pb, bg=GUI_CARD)
    pick_row.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, px(8)))
    tk.Label(pick_row, text="序号", font=bold_font, bg=GUI_CARD, fg=GUI_TEXT).pack(side="left")
    pick_var = tk.StringVar()
    pick_entry = tk.Entry(pick_row, textvariable=pick_var, font=mono_font, relief="flat",
                          bg="#FAFAFA", fg=GUI_TEXT, insertbackground=GUI_TEXT,
                          highlightthickness=1, highlightbackground=GUI_BORDER,
                          highlightcolor=GUI_ACCENT)
    pick_entry.pack(side="left", fill="x", expand=True, padx=(px(8), px(8)))
    tk.Label(pick_row, text="1,3-5", font=small_font,
             bg=GUI_CARD, fg=GUI_SUB).pack(side="right")

    columns = ("chosen", "index", "title", "duration")
    tree = ttk.Treeview(pb, columns=columns, show="headings", style="Win.Treeview",
                        selectmode="browse", height=6)
    tree.heading("chosen", text="选")
    tree.heading("index", text="#")
    tree.heading("title", text="标题")
    tree.heading("duration", text="时长")
    tree.column("chosen", width=px(38), anchor="center", stretch=False)
    tree.column("index", width=px(46), anchor="center", stretch=False)
    tree.column("title", width=px(300), anchor="w", stretch=True)
    tree.column("duration", width=px(70), anchor="center", stretch=False)
    tree.grid(row=2, column=0, sticky="nsew")
    tree_bar = ttk.Scrollbar(pb, orient="vertical", command=tree.yview,
                             style="Win.Vertical.TScrollbar")
    tree.configure(yscrollcommand=tree_bar.set)
    tree_bar.grid(row=2, column=1, sticky="ns")

    # ---------------- 运行日志 ----------------
    log_card = _Card(right, height=170)
    log_card.grid(row=1, column=0, sticky="nsew")
    logb = log_card.body
    logb.rowconfigure(1, weight=1)
    logb.columnconfigure(0, weight=1)
    tk.Label(logb, text="运行日志", font=bold_font, bg=GUI_CARD, fg=GUI_TEXT).grid(
        row=0, column=0, columnspan=2, sticky="w", pady=(0, px(6)))
    log_text = tk.Text(logb, width=1, height=6, wrap="word", state="disabled", relief="flat",
                       font=mono_font, bg="#FAFAFA", fg="#333333",
                       highlightthickness=1, highlightbackground=GUI_BORDER)
    log_text.grid(row=1, column=0, sticky="nsew")
    log_bar = ttk.Scrollbar(logb, orient="vertical", command=log_text.yview,
                            style="Win.Vertical.TScrollbar")
    log_text.configure(yscrollcommand=log_bar.set)
    log_bar.grid(row=1, column=1, sticky="ns")

    # ---------------- 直播录制 / 字幕合并 ----------------
    #
    # 直播是纯 GUI 功能（命令行只有 --merge-sub 这种独立动作）；
    # 默认原画、可切画质、预览、预约开播自动录、弹幕单独存，全部收在这个窗口里。

    live_cfg = load_live_config()
    start_live_only = bool(start_live)
    live_state: dict = {"win": None, "rec": None, "room": None, "session": None,
                        "headers": None, "preview_busy": False, "preview_auto": False, "auto_start": None}

    def live_http() -> tuple[requests.Session, dict]:
        if live_state["session"] is None:
            live_state["session"] = build_session()
            live_state["headers"] = live_headers(build_headers(load_sessdata()))
        return live_state["session"], live_state["headers"]

    def live_save(**updates) -> None:
        live_cfg.update(updates)
        try:
            save_live_config(live_cfg)
        except Exception:
            pass

    def open_live_window() -> None:
        existing = live_state.get("win")
        if existing is not None and existing.winfo_exists():
            existing.deiconify()
            existing.state("normal")
            existing.lift()
            existing.focus_force()
            return

        win = tk.Toplevel(root)
        live_state["win"] = win
        win.title("录制直播 - Bilibili Downloader")
        apply_window_icon(win)
        win.configure(bg=GUI_BG)
        live_w = min(px(1060), screen_w - px(24))
        live_h = min(px(740), screen_h - px(120))
        win.geometry(f"{live_w}x{live_h}"
                     f"+{max(px(8), (screen_w - live_w) // 2)}"
                     f"+{max(px(6), (screen_h - live_h) // 2 - px(28))}")
        win.minsize(min(px(880), screen_w - px(24)), min(px(620), screen_h - px(60)))

        quality = {"map": {}, "choices": []}
        qn_var = tk.StringVar()
        seg_var = tk.StringVar(value=str(live_cfg.get("segment_minutes") or LIVE_SEGMENT_MINUTES))
        out_var_live = tk.StringVar(value=str(live_cfg.get("output") or default_output()))
        room_var = tk.StringVar(value=str(live_cfg.get("last_link") or ""))
        task_var = tk.StringVar()
        light_var = tk.BooleanVar(value=bool(live_cfg.get("danmaku_light", True)))
        full_var = tk.BooleanVar(value=bool(live_cfg.get("danmaku_full", True)))
        keep_var = tk.BooleanVar(value=bool(live_cfg.get("keep_segments", False)))
        status_var_live = tk.StringVar(value="未读取房间")
        info_var = tk.StringVar(value="填直播间链接或房间号后点「读取」")

        def make_panel(parent, title: str, expand: bool = False) -> tk.Frame:
            outer = tk.Frame(parent, bg=GUI_CARD, highlightbackground=GUI_BORDER,
                             highlightthickness=1)
            if expand:
                outer.pack(fill="both", expand=True, pady=(0, px(6)))
            else:
                outer.pack(fill="x", pady=(0, px(6)))
            head = tk.Frame(outer, bg=GUI_CARD)
            head.pack(fill="x", padx=px(12), pady=(px(8), 0))
            tk.Label(head, text=title, font=bold_font, bg=GUI_CARD,
                     fg=GUI_TEXT).pack(side="left")
            inner = tk.Frame(outer, bg=GUI_CARD)
            inner.pack(fill="both", expand=True, padx=px(12), pady=(px(6), px(10)))
            return inner

        def append_live_log(text: str) -> None:
            try:
                live_log.configure(state="normal")
                live_log.insert("end", text + ("\n" if not text.endswith("\n") else ""))
                live_log.see("end")
                live_log.configure(state="disabled")
            except Exception:
                pass

        def current_qn() -> int:
            return int(quality["map"].get(qn_var.get(), LIVE_DEFAULT_QN))

        def set_quality_choices(choices: list[tuple[int, str]]) -> None:
            quality["map"] = {f"{desc}（{qn}）": qn for qn, desc in choices}
            quality["choices"] = list(choices)
            values = list(quality["map"].keys())
            qn_combo.configure(values=values)
            want = int(live_cfg.get("qn") or LIVE_DEFAULT_QN)
            label = next((key for key, value in quality["map"].items() if value == want), None)
            if label is None and values:
                label = values[0]
            if label:
                qn_var.set(label)

        # ---- 顶部 ----
        head = tk.Frame(win, bg=GUI_BG)
        head.pack(fill="x", padx=px(16), pady=(px(10), px(6)))
        tk.Label(head, text="录制直播", font=title_font, bg=GUI_BG,
                 fg=GUI_TEXT).pack(side="left")
        tk.Label(head, text="默认原画 · 中途可切画质 · 弹幕单独保存 · 预约开播自动录",
                 font=small_font, bg=GUI_BG, fg=GUI_SUB).pack(side="left", padx=px(12))

        body = tk.Frame(win, bg=GUI_BG)
        body.pack(fill="both", expand=True, padx=px(16), pady=(0, px(6)))
        body.columnconfigure(0, weight=3)
        body.columnconfigure(1, weight=2)
        body.rowconfigure(0, weight=1)
        left = tk.Frame(body, bg=GUI_BG)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, px(10)))
        right = tk.Frame(body, bg=GUI_BG)
        right.grid(row=0, column=1, sticky="nsew")

        # ---- 直播间 ----
        room_panel = make_panel(left, "直播间")
        room_row = tk.Frame(room_panel, bg=GUI_CARD)
        room_row.pack(fill="x")
        tk.Label(room_row, text="链接 / 房间号", font=small_font, bg=GUI_CARD,
                 fg=GUI_SUB).pack(side="left")
        room_entry = tk.Entry(room_row, textvariable=room_var, font=small_font,
                              relief="flat", bg="#FFFFFF", fg=GUI_TEXT,
                              highlightthickness=1, highlightbackground=GUI_BORDER,
                              highlightcolor=GUI_ACCENT)
        room_entry.pack(side="left", fill="x", expand=True, padx=px(8), ipady=px(3))
        read_btn = _RoundedButton(room_row, "读取", kind="secondary", width=64, height=28,
                                  command=lambda: read_room())
        read_btn.pack(side="right")
        tk.Label(room_panel, textvariable=info_var, font=small_font, bg=GUI_CARD,
                 fg=GUI_SUB, justify="left", anchor="w").pack(fill="x", pady=(px(6), 0))

        # ---- 选项 ----
        opt_panel = make_panel(left, "录制选项")
        row1 = tk.Frame(opt_panel, bg=GUI_CARD)
        row1.pack(fill="x")
        tk.Label(row1, text="画质", font=small_font, bg=GUI_CARD, fg=GUI_SUB).pack(side="left")
        qn_combo = ttk.Combobox(row1, textvariable=qn_var, state="readonly",
                                values=["原画（10000）"], width=14)
        qn_combo.pack(side="left", padx=(px(6), px(14)))
        qn_combo.bind("<<ComboboxSelected>>", lambda _e: on_quality_change())
        tk.Label(row1, text="分段", font=small_font, bg=GUI_CARD, fg=GUI_SUB).pack(side="left")
        seg_box = ttk.Spinbox(row1, from_=1, to=120, width=5, textvariable=seg_var)
        seg_box.pack(side="left", padx=(px(6), px(4)))
        tk.Label(row1, text="分钟/段", font=small_font, bg=GUI_CARD,
                 fg=GUI_SUB).pack(side="left")

        row2 = tk.Frame(opt_panel, bg=GUI_CARD)
        row2.pack(fill="x", pady=(px(8), 0))
        ttk.Checkbutton(row2, text="精简弹幕", variable=light_var).pack(side="left")
        ttk.Checkbutton(row2, text="全部弹幕（含礼物 / 上舰）",
                        variable=full_var).pack(side="left", padx=(px(10), 0))
        ttk.Checkbutton(row2, text="保留分段", variable=keep_var).pack(side="left",
                                                                          padx=(px(10), 0))

        row3 = tk.Frame(opt_panel, bg=GUI_CARD)
        row3.pack(fill="x", pady=(px(8), 0))
        tk.Label(row3, text="保存到", font=small_font, bg=GUI_CARD, fg=GUI_SUB).pack(side="left")
        out_entry = tk.Entry(row3, textvariable=out_var_live, font=small_font, relief="flat",
                             bg="#FFFFFF", fg=GUI_TEXT, highlightthickness=1,
                             highlightbackground=GUI_BORDER, highlightcolor=GUI_ACCENT)
        out_entry.pack(side="left", fill="x", expand=True, padx=px(8), ipady=px(3))
        _RoundedButton(row3, "浏览", kind="ghost", width=56, height=26,
                       command=lambda: browse_live_out()).pack(side="right")

        # ---- 录制按钮 ----
        btn_row = tk.Frame(left, bg=GUI_BG)
        btn_row.pack(fill="x", pady=(0, px(8)))
        start_btn_live = _RoundedButton(btn_row, "开始录制", kind="accent", width=110, height=36,
                                        font=(GUI_FONT_FAMILY, 10, "bold"),
                                        command=lambda: start_record())
        start_btn_live.pack(side="left")
        stop_btn = _RoundedButton(btn_row, "停止", kind="secondary", width=76, height=36,
                                  enabled=False, command=lambda: stop_record())
        stop_btn.pack(side="left", padx=px(8))
        _RoundedButton(btn_row, "打开目录", kind="ghost", width=88, height=36,
                       command=lambda: open_folder(out_var_live.get())).pack(side="left")

        # ---- 预览 ----
        prev_panel = make_panel(right, "预览")
        prev_row = tk.Frame(prev_panel, bg=GUI_CARD)
        prev_row.pack(fill="both", expand=True)
        holder = tk.Frame(prev_row, bg="#101418", width=px(236), height=px(132))
        holder.pack(side="left")
        holder.pack_propagate(False)
        preview_label = tk.Label(holder, text="暂无预览", font=small_font,
                                 bg="#101418", fg="#8A8A8A")
        preview_label.pack(fill="both", expand=True)
        side = tk.Frame(prev_row, bg=GUI_CARD)
        side.pack(side="left", fill="both", expand=True, padx=(px(10), 0))
        tk.Label(side, textvariable=status_var_live, font=small_font, bg=GUI_CARD,
                 fg=GUI_TEXT, justify="left", anchor="w", wraplength=px(108)).pack(fill="x")
        _RoundedButton(side, "刷新预览", kind="secondary", width=74, height=24,
                       command=lambda: refresh_preview()).pack(anchor="w", pady=(px(8), px(4)))
        _RoundedButton(side, "试看 10 秒", kind="ghost", width=74, height=24,
                       command=lambda: sample_clip()).pack(anchor="w")

        # ---- 预约任务 ----
        task_panel = make_panel(right, "预约直播（开播自动录）")
        task_row = tk.Frame(task_panel, bg=GUI_CARD)
        task_row.pack(fill="x")
        task_entry = tk.Entry(task_row, textvariable=task_var, font=small_font, relief="flat",
                              bg="#FFFFFF", fg=GUI_TEXT, highlightthickness=1,
                              highlightbackground=GUI_BORDER, highlightcolor=GUI_ACCENT)
        task_entry.pack(side="left", fill="x", expand=True, ipady=px(3))
        _RoundedButton(task_row, "添加", kind="secondary", width=62, height=28,
                       command=lambda: add_task()).pack(side="left", padx=(px(6), 0))
        task_tree = ttk.Treeview(task_panel, columns=("room", "state"), show="headings",
                                 height=3, style="Win.Treeview")
        task_tree.heading("room", text="直播间")
        task_tree.heading("state", text="状态")
        task_tree.column("room", width=px(150), anchor="w")
        task_tree.column("state", width=px(60), anchor="center")
        task_tree.pack(fill="both", expand=True, pady=(px(8), px(6)))
        task_btns = tk.Frame(task_panel, bg=GUI_CARD)
        task_btns.pack(fill="x")
        _RoundedButton(task_btns, "暂停 / 启用", kind="ghost", width=92, height=26,
                       command=lambda: toggle_task()).pack(side="left")
        _RoundedButton(task_btns, "删除", kind="ghost", width=62, height=26,
                       command=lambda: remove_task()).pack(side="left", padx=px(6))

        # ---- 日志 ----
        log_panel = make_panel(left, "录制日志", expand=True)
        live_log = tk.Text(log_panel, height=6, width=1, font=mono_font, bg="#FFFFFF", fg=GUI_TEXT,
                           relief="flat", wrap="word", state="disabled")
        live_log.pack(fill="both", expand=True)

        footer = tk.Frame(win, bg=GUI_BG)
        footer.pack(fill="x", padx=px(16), pady=(0, px(12)))
        tk.Label(footer, text="录制直播只保存弹幕文件，不嵌进视频；要嵌进视频请用主界面的「合并弹幕」。",
                 font=small_font, bg=GUI_BG, fg=GUI_SUB).pack(side="left")
        _RoundedButton(footer, "关闭", kind="secondary", width=72, height=32,
                       command=lambda: close_live_window()).pack(side="right")
        _RoundedButton(footer, "最小化到托盘", kind="ghost", width=110, height=32,
                       command=lambda: hide_to_tray()).pack(side="right", padx=(0, px(8)))

        # ---- 行为 ----
        def mark_out_custom(*_args: object) -> None:
            # 用户自己动过保存目录，之后读直播间就不再覆盖
            live_state["out_custom"] = True

        def browse_live_out() -> None:
            chosen = filedialog.askdirectory(initialdir=out_var_live.get() or str(default_output()),
                                             title="选择直播保存目录", parent=win)
            if chosen:
                mark_out_custom()
                out_var_live.set(chosen)

        out_entry.bind("<KeyRelease>", mark_out_custom)

        def on_quality_change() -> None:
            rec = live_state.get("rec")
            qn = current_qn()
            if rec and rec.running:
                rec.switch_quality(qn)
            live_save(qn=qn)

        def apply_room(room: dict, play: dict | None) -> None:
            read_btn.set_enabled(True)
            live_state["room"] = room
            if play:
                set_quality_choices(live_quality_choices(play))
            else:
                set_quality_choices(sorted(((qn, LIVE_QN_DESC.get(qn, str(qn)))
                                            for qn in LIVE_QN_DESC), reverse=True))
            state_text = {1: "直播中", 2: "轮播中", 0: "未开播"}.get(room["live_status"], "未知")
            info_var.set(f"{room.get('uname') or ''}  ·  {room.get('title') or ''}\n"
                         f"{state_text}  ·  在线 {room.get('online') or 0}  ·  {room.get('area') or ''}")
            status_var_live.set(f"已读取（{state_text}）")
            if not live_state.get("out_custom"):
                # 默认落到 <桌面>/<直播间名称>/，录制时直接建好目录
                name = clean_name(str(room.get("title") or f"直播间{room.get('ref_id')}"), 60)
                folder = Path(default_output()) / (name or f"直播间{room.get('ref_id')}")
                try:
                    folder.mkdir(parents=True, exist_ok=True)
                except OSError:
                    folder = Path(default_output())
                out_var_live.set(str(folder))
            if room["live_status"] == 1:
                refresh_preview(auto=True)

        def fail_room(exc: Exception) -> None:
            read_btn.set_enabled(True)
            status_var_live.set("读取失败")
            messagebox.showerror("读取直播间", short_error(exc, 300), parent=win)

        def read_room() -> None:
            raw = room_var.get().strip()
            if not raw:
                messagebox.showinfo("提示", "先填直播间链接或房间号", parent=win)
                return
            try:
                room_id = parse_live_room_id(raw)
            except DownloadError as exc:
                messagebox.showerror("房间号", short_error(exc, 200), parent=win)
                return
            read_btn.set_enabled(False)
            status_var_live.set("正在读取房间…")

            def worker() -> None:
                try:
                    session, headers = live_http()
                    room = live_room_info(session, headers, room_id)
                    play = None
                    if room["live_status"] == 1:
                        try:
                            play = live_play_info(session, headers, room_id, current_qn())
                        except Exception:
                            play = None
                    ui_jobs.put(lambda: apply_room(room, play))
                except Exception as exc:
                    ui_jobs.put(lambda: fail_room(exc))

            threading.Thread(target=worker, name="live-read-room", daemon=True).start()

        def start_record(auto_room: dict | None = None) -> None:
            rec = live_state.get("rec")
            if rec and rec.running:
                messagebox.showinfo("正在录制", "已经有一段直播在录，先停止再开新的。", parent=win)
                return
            room = auto_room or live_state.get("room")
            if not room:
                messagebox.showinfo("提示", "先点「读取」拿到直播间信息", parent=win)
                return
            if int(room.get("live_status") or 0) != 1:
                messagebox.showwarning("还没开播",
                                       "这个直播间当前不在直播中。\n可以加到下面的预约列表，开播后自动开始。",
                                       parent=win)
                return
            try:
                minutes = max(1, int(float(seg_var.get() or LIVE_SEGMENT_MINUTES)))
            except ValueError:
                minutes = LIVE_SEGMENT_MINUTES
            dest_dir = Path(out_var_live.get().strip() or default_output())
            try:
                dest_dir.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                messagebox.showerror("保存目录不可用", short_error(exc, 300), parent=win)
                return
            session, headers = live_http()
            try:
                recorder = LiveRecorder(
                    session, headers, room, out_dir=dest_dir,
                    qn=current_qn(), segment_minutes=minutes,
                    danmaku_light=light_var.get(), danmaku_full=full_var.get(),
                    keep_segments=keep_var.get(),
                    log=lambda text: ui_jobs.put(lambda value=text: append_live_log(value)))
            except Exception as exc:
                messagebox.showerror("无法开始录制", short_error(exc, 300), parent=win)
                return
            live_state["rec"] = recorder
            recorder.start()
            start_btn_live.set_enabled(False)
            stop_btn.set_enabled(True)
            append_live_log(f"[直播] 开始录制：{room.get('title') or room.get('ref_id')}")
            live_save(last_link=room_var.get().strip(), qn=current_qn(),
                      segment_minutes=minutes, output=str(out_var_live.get()),
                      danmaku_light=light_var.get(), danmaku_full=full_var.get(),
                      keep_segments=keep_var.get())
            win.after(1200, lambda: refresh_preview(auto=True))

        def after_stop(result: dict) -> None:
            live_state["rec"] = None
            start_btn_live.set_enabled(True)
            stop_btn.set_enabled(False)
            status_var_live.set("已停止")
            lines = []
            for video in result.get("videos") or []:
                lines.append(f"视频：{video}")
            for mode, info in (result.get("danmaku") or {}).items():
                lines.append(f"{mode} 弹幕：{info['count']} 条 → {info['ass'].name}")
            if result.get("error"):
                lines.append(result["error"])
            body = "\n".join(lines) if lines else "没有产物（可能录得太短）"
            append_live_log("[直播] 录制结束\n" + body)
            messagebox.showinfo("录制结束", "已保存：\n" + body, parent=win)

        def stop_record() -> None:
            rec = live_state.get("rec")
            if not rec or not rec.running:
                return
            stop_btn.set_enabled(False)
            status_var_live.set("正在收尾：停弹幕、拼分段…")

            def worker() -> None:
                result = rec.finish()
                ui_jobs.put(lambda: after_stop(result))

            threading.Thread(target=worker, name="live-finish", daemon=True).start()

        def apply_preview(path: Path) -> None:
            try:
                image = tk.PhotoImage(file=str(path))
                # 缩略图不超过预览框（按实际容器尺寸算，别按固定数字，否则高缩放下会溢出）
                shrink = max(1, -(-image.width() // px(232)), -(-image.height() // px(128)))
                if shrink > 1:
                    image = image.subsample(shrink, shrink)
                preview_label.configure(image=image, text="")
                preview_label.image = image
                rec = live_state.get("rec")
                if not (rec and rec.running):
                    status_var_live.set("预览已更新")
            except Exception as exc:
                preview_failed(exc)

        def preview_failed(exc: Exception) -> None:
            status_var_live.set(f"预览失败：{short_error(exc, 80)}")

        def refresh_preview(auto: bool = False) -> None:
            room = live_state.get("room")
            if not room or int(room.get("live_status") or 0) != 1:
                return
            if live_state["preview_busy"]:
                return
            live_state["preview_busy"] = True
            live_state["preview_auto"] = bool(auto)
            rec = live_state.get("rec")
            if not (rec and rec.running):
                status_var_live.set("预览加载中…")
            session, headers = live_http()

            def worker() -> None:
                try:
                    dest = Path(tempfile.gettempdir()) / "bd_live_preview.png"
                    # 预览只要看得清，不必占原画带宽：取 150（高清），拿不到再由接口降级
                    live_snapshot(session, headers, room["ref_id"], 150, dest)
                    ui_jobs.put(lambda: apply_preview(dest))
                except Exception as exc:
                    ui_jobs.put(lambda: preview_failed(exc))
                finally:
                    live_state["preview_busy"] = False
                    ui_jobs.put(_schedule_next_preview)

            threading.Thread(target=worker, name="live-preview", daemon=True).start()

        def _schedule_next_preview() -> None:
            """只在主线程里排下一次刷新，tkiner 的 after 不能从工作线程调。"""
            if not live_state.get("preview_auto"):
                return
            try:
                if not win.winfo_exists():
                    return
            except tk.TclError:
                return
            win.after(12000, lambda: refresh_preview(True))

        def sample_clip() -> None:
            room = live_state.get("room")
            if not room or int(room.get("live_status") or 0) != 1:
                messagebox.showinfo("提示", "直播间当前没有开播", parent=win)
                return
            session, headers = live_http()

            def worker() -> None:
                try:
                    dest = Path(tempfile.gettempdir()) / "bd_live_sample.flv"
                    live_sample_clip(session, headers, room["ref_id"], current_qn(), dest, 10)
                    if IS_WIN:
                        os.startfile(str(dest))
                    elif sys.platform == "darwin":
                        subprocess.Popen(["open", str(dest)])
                    else:
                        subprocess.Popen(["xdg-open", str(dest)])
                except Exception as exc:
                    ui_jobs.put(lambda: messagebox.showerror("试看失败", short_error(exc, 300),
                                                            parent=win))

            threading.Thread(target=worker, name="live-sample", daemon=True).start()

        def refresh_tasks() -> None:
            for item in task_tree.get_children():
                task_tree.delete(item)
            for index, task in enumerate(live_cfg.get("tasks") or []):
                state_text = "启用" if task.get("enabled", True) else "暂停"
                task_tree.insert("", "end", iid=str(index),
                                 values=(f"{task.get('room_id')}  {task.get('link')}", state_text))

        def add_task() -> None:
            raw = task_var.get().strip() or room_var.get().strip()
            if not raw:
                messagebox.showinfo("提示", "填预约直播的链接", parent=win)
                return
            try:
                room_id = parse_live_room_id(raw)
            except DownloadError as exc:
                messagebox.showerror("预约链接", short_error(exc, 200), parent=win)
                return
            tasks = list(live_cfg.get("tasks") or [])
            if any(int(item.get("room_id") or 0) == room_id for item in tasks):
                messagebox.showinfo("提示", "这个直播间已经在预约列表里了", parent=win)
                return
            tasks.append({"link": raw, "room_id": room_id, "note": "", "enabled": True})
            live_save(tasks=tasks)
            task_var.set("")
            refresh_tasks()
            if scheduler:
                scheduler.set_tasks(tasks)
            append_live_log(f"[预约] 已添加房间 {room_id}，每 {LIVE_POLL_SECONDS} 秒查一次开播状态")

        def current_task() -> int | None:
            selection = task_tree.selection()
            return int(selection[0]) if selection else None

        def toggle_task() -> None:
            index = current_task()
            if index is None:
                return
            tasks = list(live_cfg.get("tasks") or [])
            if 0 <= index < len(tasks):
                tasks[index]["enabled"] = not bool(tasks[index].get("enabled", True))
                live_save(tasks=tasks)
                refresh_tasks()
                if scheduler:
                    scheduler.set_tasks(tasks)

        def remove_task() -> None:
            index = current_task()
            if index is None:
                return
            tasks = list(live_cfg.get("tasks") or [])
            if 0 <= index < len(tasks):
                tasks.pop(index)
                live_save(tasks=tasks)
                refresh_tasks()
                if scheduler:
                    scheduler.set_tasks(tasks)

        def close_live_window() -> None:
            if live_state.get("rec") and live_state["rec"].running:
                if not messagebox.askyesno("正在录制", "录制还在进行，关掉窗口会隐藏到托盘继续录。\n"
                                                          "要停止录制请先点「停止」。继续？", parent=win):
                    return
                win.withdraw()
                if tray:
                    tray.notify("直播录制中", "窗口已隐藏到托盘，录制继续。")
                return
            live_state["win"] = None
            win.destroy()
            if start_live_only:
                quit_app()

        def live_tick() -> None:
            try:
                if not win.winfo_exists():
                    return
            except Exception:
                return
            rec = live_state.get("rec")
            if rec and rec.running:
                seconds = int(rec.duration)
                status_var_live.set(
                    f"录制中  {seconds // 3600:02d}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}\n"
                    f"{human_size(rec.total_bytes)}  ·  {rec.qn_label()}\n"
                    f"分段 {len(rec.segments)} 个")
                try:
                    start_btn_live.set_enabled(False)
                    stop_btn.set_enabled(True)
                except Exception:
                    pass
            elif rec is None:
                try:
                    start_btn_live.set_enabled(True)
                    stop_btn.set_enabled(False)
                except Exception:
                    pass
            win.after(1000, live_tick)

        live_state["append"] = append_live_log

        # 打开窗口时的初始状态：有保存过的房间就顺手读一次
        set_quality_choices(sorted(((qn, LIVE_QN_DESC.get(qn, str(qn)))
                                    for qn in LIVE_QN_DESC), reverse=True))
        refresh_tasks()
        win.protocol("WM_DELETE_WINDOW", close_live_window)
        win.bind("<Unmap>", lambda _e: (win.after(30, lambda: win.state() == "iconic"
                                         and (win.withdraw(), tray and tray.notify(
                                             "B 站下载器", "直播窗口已最小化到托盘。")))))
        live_tick()
        if room_var.get().strip():
            win.after(300, lambda: read_room())
        win.focus_force()

    def open_merge_dialog() -> None:
        dlg = tk.Toplevel(root)
        dlg.title("合并弹幕 / 字幕")
        apply_window_icon(dlg)
        dlg.configure(bg=GUI_BG)
        dlg.geometry(f"{px(760)}x{px(430)}+{px(80)}+{px(80)}")
        dlg.transient(root)
        dlg.resizable(False, False)

        tk.Label(dlg, text="把弹幕 / 字幕合进视频（产物另存，绝不覆盖原视频）",
                 font=bold_font, bg=GUI_BG, fg=GUI_TEXT).pack(anchor="w", padx=px(18),
                                                              pady=(px(16), px(8)))
        form = tk.Frame(dlg, bg=GUI_CARD, highlightbackground=GUI_BORDER, highlightthickness=1)
        form.pack(fill="both", expand=True, padx=px(18), pady=(0, px(10)))
        video_var = tk.StringVar()
        sub_var = tk.StringVar()
        mode_var = tk.StringVar(value="soft")
        out_var_merge = tk.StringVar()

        def pick_file(var: tk.StringVar, title: str, patterns: str) -> None:
            chosen = filedialog.askopenfilename(title=title, parent=dlg,
                                                filetypes=[("支持的文件", patterns),
                                                           ("全部文件", "*.*")])
            if chosen:
                var.set(chosen)

        def row(label: str, var: tk.StringVar, title: str, patterns: str) -> None:
            line = tk.Frame(form, bg=GUI_CARD)
            line.pack(fill="x", padx=px(12), pady=(px(8), 0))
            tk.Label(line, text=label, font=small_font, bg=GUI_CARD, fg=GUI_SUB,
                     width=8, anchor="w").pack(side="left")
            entry = tk.Entry(line, textvariable=var, font=small_font, relief="flat",
                             bg="#FFFFFF", fg=GUI_TEXT, highlightthickness=1,
                             highlightbackground=GUI_BORDER, highlightcolor=GUI_ACCENT)
            entry.pack(side="left", fill="x", expand=True, padx=px(6), ipady=px(3))
            _RoundedButton(line, "浏览", kind="ghost", width=56, height=26,
                           command=lambda: pick_file(var, title, patterns)).pack(side="right")

        row("视频", video_var, "选择视频", "*.mp4 *.mkv *.flv *.mov *.ts")
        row("字幕 / 弹幕", sub_var, "选择字幕或弹幕", "*.ass *.srt *.xml *.json")

        def pick_folder() -> None:
            start_dir = str(default_output())
            raw = video_var.get().strip()
            if raw:
                try:
                    start_dir = str(Path(raw).expanduser().parent)
                except OSError:
                    pass
            chosen = filedialog.askdirectory(title="选择输出文件夹", parent=dlg,
                                             initialdir=start_dir, mustexist=False)
            if chosen:
                out_var_merge.set(chosen)

        out_line = tk.Frame(form, bg=GUI_CARD)
        out_line.pack(fill="x", padx=px(12), pady=(px(8), 0))
        tk.Label(out_line, text="输出文件夹", font=small_font, bg=GUI_CARD, fg=GUI_SUB,
                 width=8, anchor="w").pack(side="left")
        out_entry = tk.Entry(out_line, textvariable=out_var_merge, font=small_font,
                             relief="flat", bg="#FFFFFF", fg=GUI_TEXT, highlightthickness=1,
                             highlightbackground=GUI_BORDER, highlightcolor=GUI_ACCENT)
        out_entry.pack(side="left", fill="x", expand=True, padx=px(6), ipady=px(3))
        _RoundedButton(out_line, "浏览", kind="ghost", width=56, height=26,
                       command=pick_folder).pack(side="right")

        mode_row = tk.Frame(form, bg=GUI_CARD)
        mode_row.pack(fill="x", padx=px(12), pady=(px(10), px(8)))
        tk.Label(mode_row, text="保存方式", font=small_font, bg=GUI_CARD, fg=GUI_SUB,
                 width=8, anchor="w").pack(side="left")
        for text, value in (("软字幕（MKV，可开关）", "soft"),
                            ("硬字幕（烧进画面，较慢）", "hard")):
            ttk.Radiobutton(mode_row, text=text, value=value, variable=mode_var).pack(
                side="left", padx=(0, px(8)))

        hint_var = tk.StringVar(value="输出文件夹留空 = 与原视频同目录，产物名 ＜视频名＞.sub.mkv / .sub.mp4")
        tk.Label(dlg, textvariable=hint_var, font=small_font, bg=GUI_BG, fg=GUI_SUB,
                 justify="left", anchor="w").pack(fill="x", padx=px(18))

        buttons = tk.Frame(dlg, bg=GUI_BG)
        buttons.pack(fill="x", padx=px(18), pady=(px(8), px(12)))
        merge_btn = _RoundedButton(buttons, "开始合并", kind="accent", width=104, height=34,
                                   font=(GUI_FONT_FAMILY, 10, "bold"),
                                   command=lambda: run_merge())
        merge_btn.pack(side="right")
        _RoundedButton(buttons, "关闭", kind="ghost", width=70, height=34,
                       command=lambda: dlg.destroy()).pack(side="right", padx=(0, px(8)))

        def run_merge() -> None:
            video = Path(video_var.get().strip()).expanduser() if video_var.get().strip() else None
            subtitle = Path(sub_var.get().strip()).expanduser() if sub_var.get().strip() else None
            if not video or not subtitle:
                messagebox.showinfo("提示", "先选视频和字幕文件", parent=dlg)
                return
            out = Path(out_var_merge.get().strip()).expanduser() if out_var_merge.get().strip() else None
            merge_btn.set_enabled(False)
            hint_var.set("正在处理…（软字幕是秒级，硬字幕要重新编码整段视频）")

            def worker() -> None:
                try:
                    result = merge_subtitle(video, subtitle, mode_var.get(), out)
                    def done() -> None:
                        merge_btn.set_enabled(True)
                        hint_var.set(f"完成：{result}")
                        messagebox.showinfo("合并完成", f"已保存到：\n{result}", parent=dlg)
                    ui_jobs.put(done)
                except Exception as exc:
                    def failed() -> None:
                        merge_btn.set_enabled(True)
                        hint_var.set("失败")
                        messagebox.showerror("合并失败", short_error(exc, 300), parent=dlg)
                    ui_jobs.put(failed)

            threading.Thread(target=worker, name="merge-sub", daemon=True).start()

    def auto_record(info: dict) -> None:
        """预约开播的自动录制：不依赖直播窗口是否打开，按配置直接开录，结束自动收尾。"""
        rec = live_state.get("rec")
        if rec and rec.running:
            append_log("[预约] 已经有一段录制在进行，跳过这次自动录制\n")
            return
        try:
            session, headers = live_http()
            recorder = LiveRecorder(
                session, headers, info,
                out_dir=Path(str(live_cfg.get("output") or default_output())),
                qn=int(live_cfg.get("qn") or LIVE_DEFAULT_QN),
                segment_minutes=int(live_cfg.get("segment_minutes") or LIVE_SEGMENT_MINUTES),
                danmaku_light=bool(live_cfg.get("danmaku_light", True)),
                danmaku_full=bool(live_cfg.get("danmaku_full", True)),
                keep_segments=bool(live_cfg.get("keep_segments", False)),
                log=lambda text: ui_jobs.put(lambda value=text: append_log(value + "\n")))
        except Exception as exc:
            append_log(f"[预约] 无法开始录制：{short_error(exc)}\n")
            return
        live_state["rec"] = recorder
        recorder.start()
        append_log(f"[预约] 已开始录制：{info.get('title') or info.get('ref_id')}\n")
        if tray:
            tray.notify("直播开播", f"{info.get('uname') or ''} 开播了，已自动开始录制。")

        def watcher() -> None:
            while recorder.running:
                time.sleep(3)
            result = recorder.finish()
            lines = [f"视频：{item}" for item in result.get("videos") or []]
            for mode, item in (result.get("danmaku") or {}).items():
                lines.append(f"{mode} 弹幕：{item['count']} 条 → {item['ass'].name}")
            text = "\n".join(lines) or "没有产物（可能录得太短）"

            def done() -> None:
                if live_state.get("rec") is recorder:
                    live_state["rec"] = None
                append_log("[预约] 直播结束，已自动保存：\n" + text + "\n")
                if tray:
                    tray.notify("直播录制完成", text[:200])

            ui_jobs.put(done)

        threading.Thread(target=watcher, name="live-auto-finish", daemon=True).start()

    live_state["auto_start"] = auto_record

    # ---------------- 底部 ----------------
    bottom = tk.Frame(root, bg=GUI_BG)
    bottom.pack(side="bottom", fill="x", padx=px(18), pady=(px(8), px(12)))
    progress = ttk.Progressbar(bottom, mode="indeterminate",
                               style="Win.Horizontal.TProgressbar")
    progress.pack(fill="x", pady=(0, px(6)))

    info_row = tk.Frame(bottom, bg=GUI_BG)
    info_row.pack(fill="x")
    status_var = tk.StringVar(value="就绪")
    tk.Label(info_row, textvariable=status_var, font=small_font, bg=GUI_BG,
             fg=GUI_SUB).pack(side="left")
    tk.Label(info_row, text="使用 -h/--help 查看命令行帮助", font=small_font,
             bg=GUI_BG, fg=GUI_SUB).pack(side="right")

    foot = tk.Frame(bottom, bg=GUI_BG)
    foot.pack(fill="x", pady=(px(8), 0))
    start_btn = _RoundedButton(foot, "开始下载", kind="accent", width=112, height=34,
                               font=(GUI_FONT_FAMILY, 10, "bold"), command=lambda: start())
    start_btn.pack(side="right")
    cancel_btn = _RoundedButton(foot, "取消", kind="secondary", width=76, height=34,
                                enabled=False, command=lambda: cancel())
    cancel_btn.pack(side="right", padx=(0, px(8)))
    _RoundedButton(foot, "打开目录", kind="ghost", width=86, height=34,
                   command=lambda: open_folder(out_var.get())).pack(side="right", padx=(0, px(8)))
    _RoundedButton(foot, "帮助", kind="ghost", width=70, height=34,
                   command=lambda: show_help()).pack(side="right")
    _RoundedButton(foot, "合并弹幕", kind="ghost", width=92, height=34,
                   command=lambda: open_merge_dialog()).pack(side="left")
    _RoundedButton(foot, "录制直播", kind="secondary", width=92, height=34,
                   command=lambda: open_live_window()).pack(side="left", padx=(0, px(8)))
    main.pack(fill="both", expand=True, padx=px(18), pady=(0, px(4)))


    # ---------------- 状态 ----------------
    events: "queue.Queue[str]" = queue.Queue()
    dialog_jobs: "queue.Queue[tuple]" = queue.Queue()
    ui_jobs: "queue.Queue[Callable[[], None]]" = queue.Queue()
    state = {"running": False, "reading": False}
    preview: dict = {"labels": [], "items": [], "chosen": set()}

    def append_log(text: str) -> None:
        log_text.configure(state="normal")
        log_text.insert("end", text)
        log_text.see("end")
        if int(log_text.index("end-1c").split(".")[0]) > 4000:   # 日志别无限涨
            log_text.delete("1.0", "1000.0")
        log_text.configure(state="disabled")

    def paste_link() -> None:
        try:
            text = root.clipboard_get()
        except Exception:
            text = ""
        if text.strip():
            url_text.insert("end", (" " if url_text.get("1.0", "end").strip() else "") + text.strip())

    def browse_dir() -> None:
        chosen = filedialog.askdirectory(initialdir=out_var.get() or str(default_output()),
                                         title="选择保存目录")
        if chosen:
            out_var.set(chosen)

    def open_folder(path: str) -> None:
        target = Path((path or "").strip() or str(default_output())).expanduser()
        try:
            target.mkdir(parents=True, exist_ok=True)
            if IS_WIN:
                os.startfile(str(target))
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(target)])
            else:
                subprocess.Popen(["xdg-open", str(target)])
        except Exception as exc:
            messagebox.showerror("打不开目录", short_error(exc, 200))

    def mask_value(value: str) -> str:
        if len(value) <= 10:
            return "•" * len(value)
        return f"{value[:6]}…{value[-4:]}"

    def cred_log(*rows) -> None:
        console.configure(state="normal")
        console.delete("1.0", "end")
        for text, tag in rows:
            console.insert("end", text + "\n", tag)
        console.configure(state="disabled")

    def render_cred() -> None:
        """按凭证状态切换：未读取 / 待校验 / 有效 / 已失效 显示不同界面。"""
        state = cred["state"]
        if state == "valid":
            input_row.grid_remove()
            manage_row.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(px(8), 0))
            mask_label.configure(text=f"SESSDATA {mask_value(cred['value'])}")
            cred_log(("> 已登录 · 凭证有效", "ok"),
                     ("  可用 1080P+ / 4K / 无损音频；与下载速度无关", "dim"))
        elif state == "invalid":
            input_row.grid()
            manage_row.grid_remove()
            cred_log(("> 凭证已失效或已过期", "err"),
                     ("  继续下载会回退游客画质，可粘贴新的 SESSDATA 再校验", "dim"))
        elif state == "unknown":
            input_row.grid()
            manage_row.grid_remove()
            cred_log(("> 已读取 SESSDATA，但校验接口这次没连上", "warn"),
                     ("  先按已读取状态使用；网络恢复后可再点“保存并校验”", "dim"))
        elif state == "pending":
            input_row.grid()
            manage_row.grid_remove()
            source = f"（来源：{cred['source']}）" if cred["source"] else ""
            cred_log(("> 已读取 SESSDATA" + source, "warn"),
                     ("  正在校验…", "warn"))
        else:                                    # none：没读过任何凭证
            input_row.grid()
            manage_row.grid_remove()
            cred_log(("> 游客模式 · 还没读取凭证", "dim"),
                     ("  画质上限受游客限制（一般到 720P）", "dim"))

    def show_entry() -> None:
        cred["state"] = "pending" if cred["value"] else "none"
        sess_var.set("")
        render_cred()
        sess_entry.focus_set()

    def clear_cred() -> None:
        if IS_WIN:
            try:
                import winreg

                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0,
                                    winreg.KEY_SET_VALUE) as key:
                    winreg.DeleteValue(key, ENV_NAME)
                _broadcast_env_change()
            except OSError:
                pass
        os.environ.pop(ENV_NAME, None)
        for path in (SESSDATA_FILE, SESSDATA_HOME_FILE):
            try:
                path.unlink()
            except OSError:
                pass
        cred.update(value="", state="none", source="")
        sess_var.set("")
        render_cred()
        status_var.set("已清除凭证，回到游客模式")

    def check_cred_async(value: str, source: str = "") -> None:
        cred.update(value=value, state="pending", source=source)
        sess_var.set(value)
        render_cred()

        def done(state: str) -> None:
            if cred["value"] != value:
                return
            cred["state"] = state
            # 失效时把输入框清空，方便直接粘新的凭证
            sess_var.set("" if state == "invalid" else value)
            render_cred()

        def job() -> None:
            try:
                session = build_session()
                result = check_sessdata(session, build_headers(value), 8.0)
            except Exception:
                result = None
            ui_jobs.put(lambda: done("valid" if result else
                                     ("invalid" if result is False else "unknown")))

        threading.Thread(target=job, name="gui-cred", daemon=True).start()

    def save_cred() -> None:
        value = sess_var.get().strip()
        if not value:
            messagebox.showinfo("没有内容", "先粘贴 SESSDATA 再保存；留空就用游客模式。")
            return
        where = save_sessdata(value)
        os.environ[ENV_NAME] = value
        status_var.set(f"凭证已保存（{where}），正在校验…")
        check_cred_async(value, "界面输入")

    # ---------------- ffmpeg ----------------
    ff_label = tk.Label(info_row, text="", font=small_font, bg=GUI_BG, fg=GUI_SUB)
    ff_label.pack(side="left", padx=(px(14), 0))

    def refresh_ffmpeg() -> None:
        exe = ffmpeg_available()
        if exe:
            ff_label.configure(text="ffmpeg 已就绪（合并 / MP3 / 弹幕封装可用）", fg="#1A7F37")
            ff_install_btn.pack_forget()          # 已经能用就别占地方
        else:
            ff_label.configure(text="未检测到 ffmpeg：合并、MP3、弹幕封装都用不了", fg="#C0392B")
            ff_install_btn.pack(side="left", padx=(px(10), 0))

    def install_clicked() -> None:
        global FFMPEG_SOURCE
        if not IS_WIN:                 # macOS / Linux 交给系统包管理器，别硬塞一份二进制
            if IS_MAC:
                hint = "brew install ffmpeg"
            else:
                hint = ("sudo apt install ffmpeg        # Debian / Ubuntu\n"
                        "sudo dnf install ffmpeg        # Fedora")
            messagebox.showinfo(
                "安装 ffmpeg",
                f"当前系统（{PLATFORM_NAME}）请使用包管理器安装：\n\n{hint}\n\n"
                "装好后重新打开本程序即可识别；已经装过但仍提示找不到时，"
                "检查 ffmpeg 是否在 PATH 里（终端执行 ffmpeg -version）。")
            return
        _, size = resolve_ffmpeg_archive()
        shown = human_size(size) if size else f"约 {FFMPEG_FALLBACK_MB} MB"
        # 三态：是=镜像源，否=官方源，取消=不装（auto 会在失败时自动换源，这里先给个倾向）
        choice = messagebox.askyesnocancel(
            "安装 ffmpeg",
            "没有 ffmpeg 会导致无法使用完整功能（不能合并音视频、导出 MP3、嵌入弹幕）。\n\n"
            f"大小：{shown}\n安装到：{Path.home() / 'ffmpeg'}\n"
            "并自动加入用户 PATH。\n\n下载源：\n"
            "    是 → 镜像源（ghfast.top，国内通常更快）\n"
            "    否 → 官方源（GitHub 发布页）\n"
            "    取消 → 不安装\n\n"
            "（首选源连不上会自动换另一个，不会白等）")
        if choice is None:
            return
        FFMPEG_SOURCE = "mirror" if choice else "official"
        status_var.set("正在下载 ffmpeg…（可在日志里看进度）")

        def job() -> None:
            try:
                message = install_ffmpeg()
            except Aborted:
                message = "已取消"
            except Exception as exc:
                message = f"失败：{short_error(exc, 300)}"
            events.put(f"\n[ffmpeg] {message}\n")
            ui_jobs.put(refresh_ffmpeg)
            ui_jobs.put(lambda: status_var.set("就绪"))

        threading.Thread(target=job, daemon=True).start()

    ff_install_btn = _RoundedButton(info_row, "安装 ffmpeg", kind="ghost", width=104, height=24,
                                    command=lambda: install_clicked())
    ff_install_btn.pack(side="left", padx=(px(10), 0))

    # ---------------- 分集预览 ----------------
    def chosen_count() -> int:
        return len(preview["chosen"])

    def compress_selection(chosen) -> str:
        """把勾选集合压成 1,3-5,49-234 这样的紧凑写法。"""
        parts, start, prev = [], None, None
        for index in sorted(chosen):
            if start is None:
                start = prev = index
            elif index == prev + 1:
                prev = index
            else:
                parts.append(str(start) if start == prev else f"{start}-{prev}")
                start = prev = index
        if start is not None:
            parts.append(str(start) if start == prev else f"{start}-{prev}")
        return ",".join(parts)

    def sync_pick_text() -> None:
        """勾选变化时，把序号输入框刷新成对应写法。"""
        if preview["labels"]:
            pick_var.set(compress_selection(preview["chosen"]))
        else:
            pick_var.set("")

    def apply_pick_text(quiet: bool = False) -> None:
        """输入框里的 1,3-5 写法反过来改勾选状态。"""
        total = len(preview["labels"])
        if not total:
            return
        text = pick_var.get().strip()
        if not text:
            preview["chosen"] = set()
            update_count()
            return
        try:
            picked = parse_selection(text, total)
        except ValueError as exc:
            if not quiet:
                messagebox.showwarning("序号有误", str(exc))
            sync_pick_text()
            return
        preview["chosen"] = set(picked)
        update_count()

    def update_count() -> None:
        total = len(preview["labels"])
        if not total:
            count_var.set("还没有读取清单")
            sync_pick_text()
            return
        count_var.set(f"共 {total} 项 · 已选 {len(preview['chosen'])} 项")
        # 行首勾选框跟着状态刷新
        for index in range(1, total + 1):
            iid = str(index)
            values = list(tree.item(iid, "values"))
            if values:
                values[0] = "☑" if index in preview["chosen"] else "☐"
                tree.item(iid, values=values)
        sync_pick_text()

    def set_all(checked: bool) -> None:
        total = len(preview["labels"])
        preview["chosen"] = set(range(1, total + 1)) if checked else set()
        update_count()

    def toggle_row(event=None) -> None:
        iid = tree.focus()
        if not iid or not iid.isdigit():
            return
        index = int(iid)
        if index in preview["chosen"]:
            preview["chosen"].discard(index)
        else:
            preview["chosen"].add(index)
        update_count()

    def toggle_at(event) -> None:
        iid = tree.identify_row(event.y)
        if not iid:
            return
        tree.selection_set(iid)
        tree.focus(iid)
        toggle_row()

    tree.bind("<Button-1>", toggle_at)
    tree.bind("<space>", lambda event: toggle_row())
    pick_entry.bind("<Return>", lambda _event: apply_pick_text())
    pick_entry.bind("<FocusOut>", lambda _event: apply_pick_text(quiet=True))

    def fill_plan(items: Sequence[Item]) -> None:
        tree.delete(*tree.get_children())
        preview["items"] = list(items)
        preview["labels"] = [item.label for item in items]
        preview["chosen"] = set(range(1, len(items) + 1))
        for index, item in enumerate(items, 1):
            tree.insert("", "end", iid=str(index),
                        values=("☑", str(index), item.label,
                                _fmt_duration(item.duration)))
        update_count()
        status_var.set(f"已读取 {len(items)} 项，勾选后点“开始下载”")

    def read_plan() -> None:
        if state["reading"] or state["running"]:
            return
        urls = [part for part in url_text.get("1.0", "end").split() if part.strip()]
        if not urls:
            messagebox.showwarning("缺少链接", "请先填入 B 站视频链接 / BV 号。")
            return
        out = out_var.get().strip() or str(default_output())
        try:
            timeout = max(1.0, float(timeout_var.get()))
        except (tk.TclError, ValueError):
            messagebox.showwarning("参数有误", "超时需要填数字。")
            return

        state["reading"] = True
        read_btn.set_enabled(False)
        status_var.set("正在获取视频信息…")
        append_log(f"\n[界面] 正在读取：{' '.join(urls)}\n")
        credential = sess_var.get().strip()
        if credential:
            os.environ[ENV_NAME] = credential
        single = bool(single_var.get())

        def worker() -> None:
            old_out, old_err = sys.stdout, sys.stderr
            sys.stdout = sys.stderr = _GuiStream(events.put)   # type: ignore[assignment]
            try:
                argv = [*urls, "-o", out, "--timeout", str(timeout)]
                if single:
                    argv.append("--single")
                args = parse_args(argv)
                args.yes = True                  # 读取阶段不弹任何命令行提问
                session = build_session()
                _, headers = ensure_credential(session, args)
                items = build_plan(session, headers, args.inputs,
                                   root=Path(out).expanduser(), single=args.single,
                                   timeout=args.timeout)
                if items:
                    ui_jobs.put(lambda: fill_plan(items))
            except SystemExit as exc:
                events.put(f"\n[界面] 参数错误：{exc}\n")
            except Exception as exc:
                events.put(f"\n[界面] 读取失败：{short_error(exc, 300)}\n")
                ui_jobs.put(lambda: status_var.set("读取失败，详见日志"))
            finally:
                sys.stdout, sys.stderr = old_out, old_err

                def done() -> None:
                    state["reading"] = False
                    read_btn.set_enabled(True)

                ui_jobs.put(done)

        threading.Thread(target=worker, name="gui-read", daemon=True).start()

    # ---------------- 选择范围对话框（预览对不上时的兜底） ----------------
    def open_selection_dialog(total: int, items: Sequence[Item], box: dict) -> None:
        top = tk.Toplevel(root)
        top.title("选择要下载的项目")
        apply_window_icon(top)
        top.configure(bg=GUI_BG)
        top.transient(root)
        top.geometry(f"{px(640)}x{px(min(600, 260 + 22 * min(total, 14)))}")
        frame = tk.Frame(top, bg=GUI_BG, padx=px(12), pady=px(10))
        frame.pack(fill="both", expand=True)

        tk.Label(frame, text=f"共 {total} 项。可以直接全下，也可以只下部分（如 1,3,5,6-20）。",
                 font=small_font, bg=GUI_BG, fg=GUI_TEXT).pack(anchor="w")
        list_row = tk.Frame(frame, bg=GUI_CARD)
        list_row.pack(fill="both", expand=True, pady=px(8))
        listing = tk.Listbox(list_row, width=1, height=min(14, max(6, total)), activestyle="none",
                             relief="flat", bg="#FAFAFA", fg=GUI_TEXT,
                             highlightthickness=1, highlightbackground=GUI_BORDER,
                             font=small_font)
        bar = ttk.Scrollbar(list_row, orient="vertical", command=listing.yview,
                            style="Win.Vertical.TScrollbar")
        listing.configure(yscrollcommand=bar.set)
        listing.pack(side="left", fill="both", expand=True, padx=(px(6), 0), pady=px(6))
        bar.pack(side="right", fill="y", pady=px(6), padx=(0, px(6)))
        for index, item in enumerate(items, 1):
            listing.insert("end", f"{index:>3}. {item.label}")

        pick_var = tk.StringVar(value="")
        pick_row = tk.Frame(frame, bg=GUI_BG)
        pick_row.pack(fill="x")
        tk.Label(pick_row, text="序号", font=small_font, bg=GUI_BG, fg=GUI_TEXT).pack(side="left")
        entry = tk.Entry(pick_row, textvariable=pick_var, font=small_font, relief="flat",
                         bg="#FFFFFF", fg=GUI_TEXT, highlightthickness=1,
                         highlightbackground=GUI_BORDER, highlightcolor=GUI_ACCENT)
        entry.pack(side="left", fill="x", expand=True, padx=px(8))
        entry.focus_set()

        def finish(value: list[int] | None) -> None:
            box["picked"] = value
            try:
                top.grab_release()
            except Exception:
                pass
            top.destroy()
            box["done"].set()

        def pick_part() -> None:
            try:
                picked = parse_selection(pick_var.get(), total)
            except ValueError as exc:
                messagebox.showwarning("输入有误", str(exc), parent=top)
                return
            if not picked:
                messagebox.showwarning("没有选中", "至少要选一项。", parent=top)
                return
            finish(picked)

        buttons = tk.Frame(frame, bg=GUI_BG)
        buttons.pack(fill="x", pady=(px(10), 0))
        _RoundedButton(buttons, "全部下载", kind="accent", width=92, height=32,
                       command=lambda: finish(list(range(1, total + 1)))).pack(side="right")
        _RoundedButton(buttons, "只下选中的", kind="secondary", width=104, height=32,
                       command=pick_part).pack(side="right", padx=px(8))
        _RoundedButton(buttons, "取消", kind="ghost", width=70, height=32,
                       command=lambda: finish(None)).pack(side="right")
        top.protocol("WM_DELETE_WINDOW", lambda: finish(None))
        entry.bind("<Return>", lambda _event: pick_part())
        top.grab_set()

    def ask_in_gui(total: int, items: Sequence[Item]) -> list[int] | None:
        """工作线程调用：预览清单对得上就直接用勾选结果，否则弹对话框兜底。"""
        labels = [item.label for item in items]
        if preview["labels"] and len(labels) == len(preview["labels"]) and labels == preview["labels"]:
            picked = sorted(preview["chosen"])
            return picked or None
        box = {"picked": list(range(1, total + 1)), "done": threading.Event()}
        dialog_jobs.put((total, items, box))
        box["done"].wait()
        return box["picked"]

    # ---------------- 帮助 ----------------
    def show_help() -> None:
        win = tk.Toplevel(root)
        win.title("帮助（图形界面）")
        apply_window_icon(win)
        win.configure(bg=GUI_BG)
        win.geometry(f"{px(840)}x{px(680)}")
        win.transient(root)
        wrap = tk.Frame(win, bg=GUI_BG, padx=px(12), pady=px(10))
        wrap.pack(fill="both", expand=True)
        card = _Card(wrap, height=560)
        card.pack(fill="both", expand=True)
        hb = card.body
        hb.rowconfigure(0, weight=1)
        hb.columnconfigure(0, weight=1)
        body = tk.Text(hb, width=1, wrap="word", relief="flat", font=body_font, bg="#FAFAFA",
                       fg="#222222", padx=px(12), pady=px(10), highlightthickness=1,
                       highlightbackground=GUI_BORDER)
        bar = ttk.Scrollbar(hb, orient="vertical", command=body.yview,
                            style="Win.Vertical.TScrollbar")
        body.configure(yscrollcommand=bar.set)
        body.grid(row=0, column=0, sticky="nsew")
        bar.grid(row=0, column=1, sticky="ns")
        body.insert("1.0", gui_help_text())
        body.configure(state="disabled")
        _RoundedButton(wrap, "关闭", kind="secondary", width=80, height=32,
                       command=win.destroy).pack(side="right", pady=(px(10), 0))

    # ---------------- 参数与运行 ----------------
    def build_argv() -> list[str] | None:
        raw = url_text.get("1.0", "end").strip()
        if not raw:
            messagebox.showwarning("缺少链接", "请先填入 B 站视频链接 / BV 号。")
            return None
        urls = [part for part in raw.split() if part.strip()]
        out = out_var.get().strip() or str(default_output())
        danmaku = GUI_DANMAKU.get(danmaku_var.get(), "light")
        embed = GUI_EMBED.get(embed_var.get(), "none")
        if embed != "none" and danmaku == "none":
            messagebox.showwarning("选项冲突", "要把弹幕放进视频，弹幕就不能选“不下载”。")
            return None
        if embed != "none" and mode_var.get() == "audio":
            messagebox.showwarning("选项冲突", "“仅 MP3”没有视频流，没法把弹幕放进视频。")
            return None

        try:
            jobs = max(1, min(4, int(jobs_var.get())))
            retries = max(1, int(retries_var.get()))
            timeout = max(1.0, float(timeout_var.get()))
            reconnects = max(0, int(reconn_var.get()))
        except (tk.TclError, ValueError):
            messagebox.showwarning("参数有误", "并发/重试/超时/重连需要填数字。")
            return None

        argv = [*urls, "-o", out, "-q", GUI_QUALITY.get(quality_var.get(), "max"),
                "--mp3-bitrate", bitrate_var.get(),
                "--danmaku", danmaku, "--danmaku-video", embed,
                "-j", str(jobs), "--retries", str(retries),
                "--timeout", str(timeout), "--max-reconnects", str(reconnects)]
        if mode_var.get() == "audio":
            argv.append("--audio-only")
        elif mode_var.get() == "video":
            argv.append("--no-mp3")
        if single_var.get():
            argv.append("--single")
        if force_var.get():
            argv.append("--force")
        if no_probe_var.get():
            argv.append("--no-probe")
        if dry_var.get():
            argv.append("--dry-run")
        if reset_var.get():
            argv.append("--reset-sessdata")
        argv.append("-y")                 # 界面已经问过一遍，别让工作线程再等终端输入

        credential = sess_var.get().strip()
        if credential:
            os.environ[ENV_NAME] = credential      # 本次运行用界面里填的值
        return argv

    def start() -> None:
        if state["running"] or state["reading"]:
            return
        if preview["labels"] and not preview["chosen"]:
            messagebox.showwarning("没有勾选", "分集清单里一项都没勾，先勾上要下的项目。")
            return
        argv = build_argv()
        if argv is None:
            return

        state["running"] = True
        start_btn.set_enabled(False)
        read_btn.set_enabled(False)
        cancel_btn.set_enabled(True)
        progress.start(12)
        if preview["labels"] and preview["chosen"]:
            status_var.set(f"开始下载：已选 {len(preview['chosen'])}/{len(preview['labels'])} 项")
        else:
            status_var.set("正在下载…（进度见日志，取消会保留已完成部分）")
        append_log("\n" + "=" * 60 + "\n")

        def worker() -> None:
            old_out, old_err = sys.stdout, sys.stderr
            sys.stdout = sys.stderr = _GuiStream(events.put)   # type: ignore[assignment]
            try:
                code = _main_impl(argv)
                events.put(f"\n[界面] 流程结束（退出码 {code}）\n")
            except SystemExit as exc:                 # argparse 的参数错误
                events.put(f"\n[界面] 参数错误：{exc}\n")
            except Aborted:
                events.put("\n[界面] 已取消\n")
            except Exception as exc:                  # 兜底：界面不能因为异常就卡死
                events.put(f"\n[界面] 出错：{short_error(exc, 300)}\n")
            finally:
                sys.stdout, sys.stderr = old_out, old_err
                ui_jobs.put(finished)

        threading.Thread(target=worker, name="gui-download", daemon=True).start()

    def cancel() -> None:
        request_abort()
        status_var.set("正在取消…（当前分块下完就停）")
        cancel_btn.set_enabled(False)

    def finished() -> None:
        state["running"] = False
        progress.stop()
        start_btn.set_enabled(True)
        read_btn.set_enabled(True)
        cancel_btn.set_enabled(False)
        status_var.set("就绪（已结束，详见日志）")

    refresh_ffmpeg()
    _initial = load_sessdata()
    if _initial:
        check_cred_async(_initial, sessdata_origin())
    else:
        render_cred()

    tray_events: "queue.Queue[str]" = queue.Queue()
    tray = _TrayIcon("B 站视频下载器", tray_events.put)

    def hide_to_tray() -> None:
        # 托盘只有 Windows 有（macOS 的菜单栏图标需要 PyObjC，Linux 要看桌面环境）。
        # 没有托盘时不能把窗口藏起来，否则用户找不回来——直接走系统的最小化
        if not (tray and tray.available() and tray._thread):
            try:
                root.iconify()
            except tk.TclError:
                pass
            return
        root.withdraw()
        tray.notify("B 站视频下载器", "已最小化到托盘；右键托盘图标可以显示窗口或退出。")

    def quit_app() -> None:
        rec = live_state.get("rec")
        if rec and rec.running:
            if not messagebox.askyesno("正在录制直播",
                                       "录制还在进行，退出会停止录制并保留已经录下的分段。\n确定退出？"):
                return
            rec.stop()
        if scheduler:
            scheduler.stop()
        if tray:
            tray.stop()
        root.destroy()

    def maybe_minimize() -> None:
        try:
            if root.state() == "iconic" and tray and tray.available():
                root.withdraw()
        except Exception:
            pass

    def drain() -> None:
        try:
            while True:
                append_log(events.get_nowait())
        except queue.Empty:
            pass
        try:
            while True:
                total, items, box = dialog_jobs.get_nowait()
                open_selection_dialog(total, items, box)
        except queue.Empty:
            pass
        try:
            while True:
                action = tray_events.get_nowait()
                if action == "show":
                    root.deiconify()
                    root.state("normal")
                    root.lift()
                elif action == "live":
                    root.deiconify()
                    open_live_window()
                elif action == "quit":
                    quit_app()
        except queue.Empty:
            pass
        try:
            while True:
                ui_jobs.get_nowait()()
        except queue.Empty:
            pass
        root.after(100, drain)

    def on_close() -> None:
        if state["running"]:
            if not messagebox.askyesno("正在下载", "下载还没结束，确定退出？\n"
                                                   "（已下载的部分会保留，下次可续传）"):
                return
            request_abort()
        rec = live_state.get("rec")
        if rec and rec.running:
            if not messagebox.askyesno("正在录制直播",
                                       "录制还在进行，关掉主界面会隐藏到托盘继续录。\n"
                                       "要停止录制请在直播窗口点「停止」。继续？"):
                return
        hide_to_tray()

    _SELECTION_CALLBACK = ask_in_gui
    root.protocol("WM_DELETE_WINDOW", on_close)
    root.bind("<Unmap>", lambda _event: root.after(30, maybe_minimize))

    # 托盘：Windows 下才有；其他平台照常是普通窗口
    tray.start()

    # 预约任务：无论有没有任务都起一个线程，之后添加任务直接生效
    scheduler: LiveScheduler | None = None
    try:
        session_now, headers_now = live_http()
        scheduler = LiveScheduler(
            session_now, headers_now, list(live_cfg.get("tasks") or []),
            on_live=lambda info, task: ui_jobs.put(
                lambda: live_state.get("auto_start") and live_state["auto_start"](info)),
            log=lambda text: ui_jobs.put(lambda value=text: append_log(value + "\n")),
            interval=int(live_cfg.get("poll_seconds") or LIVE_POLL_SECONDS),
        )
        scheduler.start()
    except Exception:
        scheduler = None

    # 按内容实际尺寸定窗口：不同 DPI / 字体下控件请求的宽度差很多，
    # 写死 1240x900 会在 150% 缩放时把右栏挤出屏幕。
    for _card in (link_card, opt_card, cred_card, adv_card, preview_card, log_card):
        _card.fit()
    root.update_idletasks()
    need_w = root.winfo_reqwidth()
    need_h = root.winfo_reqheight()
    # 控件、字体、间距都按 SCALE 折算过了，请求尺寸就是物理像素，
    # 窗口只需要在"内容需要"和"屏幕可用"之间取一个合适的值。
    want_w = min(screen_w - px(60), max(need_w + px(16), int(screen_w * 0.68)))
    want_h = min(screen_h - px(150), max(need_h + px(16), int(screen_h * 0.72)))
    root.minsize(min(px(980), want_w), min(px(660), want_h))
    root.geometry(f"{want_w}x{want_h}+{max(0, (screen_w - want_w) // 2)}+"
                  f"{max(px(20), (screen_h - want_h) // 3)}")

    refresh_ffmpeg()
    append_log("1) 把视频链接粘到上面的输入框\n"
               "2) 点“读取分集”，在右侧清单里勾选要下的分集\n"
               "3) 选好画质 / 弹幕等选项，点“开始下载”\n")
    if start_live_only:
        root.withdraw()
        open_live_window()
    drain()
    try:
        root.mainloop()
    finally:
        _SELECTION_CALLBACK = None
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:          # 双保险：任何漏网的中断都不打 traceback
        print("\n[中断] 已取消")
        sys.exit(130)
