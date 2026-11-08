# -*- coding: utf-8 -*-
"""
文件搬运工具 v2.3  ·  作者：微尘
多选文件 / 拖拽 / 多目标文件夹 / 扩展名过滤 / 批量源文件夹 / 复制或移动
v2.1：文件夹连同目录层级整体搬运（含空文件夹、子目录），高清抗锯齿图标。
v2.2：新增星标管理器（1~10 星 / 筛选 / 重命名 / 清除 / 送回搬运）；
      文件夹与文件选择全部改为纯 Tk 自绘浏览器，
      修复在目录对话框内新建文件夹时界面缩放突变的问题。
v2.3：纯视觉改版。按钮 / 卡片改为 4x 超采样抗锯齿圆角，
      彻底消除 create_oval 拼圆角的阶梯感；配色由冷色绿蓝紫
      换成中黄 / 珊瑚橙 / 玫红为主的多巴胺暖色系；功能与交互不变。
纯本地运行，不联网、不上传任何文件。
"""
import os
import re
import string
import sys
import json
import queue
import shutil
import hashlib
import ctypes
import base64
import io
import threading
import traceback
from datetime import datetime

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import tkinter.font as tkfont

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    DND_OK = True
except Exception:
    DND_OK = False

# 抗锯齿圆角背景生成：Pillow 只参与位图生成，界面本身仍是纯 Tk 控件
try:
    from PIL import Image as _AAImage, ImageDraw as _AADraw
    AA_OK = True
except Exception:
    AA_OK = False


# ------------------------------------------------------------------ 路径与常量
def base_dir():
    # PyInstaller --onefile 时 __file__ 指向临时解压目录，配置必须写到 EXE 旁边
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def resource_path(rel):
    if getattr(sys, "frozen", False):
        return os.path.join(getattr(sys, "_MEIPASS", base_dir()), rel)
    return os.path.join(base_dir(), rel)


BASE_DIR = base_dir()
FAV_FILE = os.path.join(BASE_DIR, "常用目标.json")
LOG_FILE = os.path.join(BASE_DIR, "搬运日志.txt")
ERR_FILE = os.path.join(BASE_DIR, "错误日志.txt")

FONT = "Microsoft YaHei UI"

# ---- v2.3 多巴胺暖色系 ----
# 大面积用奶油白 / 纯白，高饱和彩色只出现在按钮、色条与标题栏，
# 因此整体明快热烈但不刺眼；冷色（青绿 / 蓝）仅作极少量点缀。
BG          = "#FFF8EF"   # 奶油暖白（窗口底）
CARD        = "#FFFFFF"   # 卡片纯白
INK         = "#3E2C26"   # 深棕墨，比纯黑柔和
MUTED       = "#9B8478"   # 暖灰
BORDER      = "#F1E2D0"   # 暖边框
SHADOW      = "#F3E4D2"   # 卡片柔和暖阴影

YELLOW      = "#FFC53D"   # 中黄：主 CTA / 首选动作
YELLOW_DK   = "#EFAE18"
ORANGE      = "#FF7043"   # 珊瑚橙：主要操作
ORANGE_DK   = "#EC5A2D"
PINK        = "#F0478A"   # 玫红：次主要操作
PINK_DK     = "#DA3070"
VIOLET      = "#9B6BFF"   # 亮紫：点缀
VIOLET_DK   = "#8552EA"
TEAL        = "#22C3B8"   # 青绿：极少量点缀

SOFT_YELLOW = "#FFF1C9"   # 柔黄底
SOFT_ORANGE = "#FFE6D8"   # 柔橙底
SOFT_PINK   = "#FFE3EE"
NEUTRAL     = "#F7EBDD"   # 次要按钮
NEUTRAL_HV  = "#EFDFCC"
NEUTRAL_TX  = "#6B5449"   # 次要按钮 / 版权行文字

FLAME_RGB = (255, 112, 67)   # 标题栏渐变：左 珊瑚橙
SUN_RGB   = (255, 190, 45)   #              中 中黄
BERRY_RGB = (238, 71, 138)   #              右 玫红

BTN_GAP = 4                  # 按钮水平间距统一值
BTN_RADIUS = 9               # 所有按钮统一的圆角半径
CARD_RADIUS = 14             # 所有卡片统一的圆角半径


def hexc(rgb):
    return "#%02X%02X%02X" % tuple(int(v) for v in rgb)


def lerp(a, b, t):
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(3))


def grad(t):
    if t < 0.5:
        return lerp(FLAME_RGB, SUN_RGB, t / 0.5)
    return lerp(SUN_RGB, BERRY_RGB, (t - 0.5) / 0.5)


# ------------------------------------------------------------------ 核心逻辑
def unique_path(path):
    base, ext = os.path.splitext(path)
    n = 1
    candidate = "{}_{}{}".format(base, n, ext)
    while os.path.exists(candidate):
        n += 1
        candidate = "{}_{}{}".format(base, n, ext)
    return candidate


def file_hash(path, algo="sha256"):
    h = hashlib.new(algo)
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_exts(text):
    """把 'jpg, .png txt' 解析成 {'.jpg', '.png', '.txt'}"""
    out = set()
    for raw in re.split(r"[,，;；\s]+", (text or "").strip()):
        if not raw:
            continue
        e = raw.lower().lstrip("*")
        if not e.startswith("."):
            e = "." + e
        out.add(e)
    return out


def passes_filter(path, exts, mode):
    if not exts:
        return True
    ext = os.path.splitext(path)[1].lower()
    return (ext in exts) if mode == "include" else (ext not in exts)


def collect_from_folders(folders, recursive=False, with_layout=False):
    """
    收集文件夹里的文件。

    with_layout=True 时额外返回 (files, roots, dirs)：
      roots = {文件路径: 所属根文件夹}，用于在目标里重建「文件夹名/子目录/文件」层级
      dirs  = 需要一并创建的相对目录（如 '项目A/空子目录'），保证空文件夹也不丢
    """
    out, roots, dirs = [], {}, set()
    for d in folders:
        if not os.path.isdir(d):
            continue
        d = os.path.normpath(d)
        top = os.path.basename(d) or d
        dirs.add(top)
        if recursive:
            for root, subdirs, names in os.walk(d):
                rel_dir = os.path.relpath(root, d)
                for sd in subdirs:
                    dirs.add(os.path.normpath(os.path.join(top, rel_dir, sd)))
                for n in sorted(names):
                    fp = os.path.join(root, n)
                    if os.path.isfile(fp):
                        out.append(fp)
                        roots[fp] = d
        else:
            for n in sorted(os.listdir(d)):
                fp = os.path.join(d, n)
                if os.path.isfile(fp):
                    out.append(fp)
                    roots[fp] = d
    if with_layout:
        return out, roots, sorted(dirs)
    return out


def build_layout(files, roots):
    """{源文件: 相对目标的路径}，例如 '项目A/子目录/a.txt'；散文件只有文件名。"""
    layout = {}
    for fp in files:
        root = (roots or {}).get(fp)
        if root:
            top = os.path.basename(os.path.normpath(root)) or root
            layout[fp] = os.path.normpath(
                os.path.join(top, os.path.relpath(fp, root)))
        else:
            layout[fp] = os.path.basename(fp)
    return layout


def is_within(child, parent):
    """child 是否位于 parent 之内（含相等）。用于阻止把源文件夹复制进它自己内部。"""
    try:
        c = os.path.normcase(os.path.abspath(child))
        q = os.path.normcase(os.path.abspath(parent))
        return os.path.commonpath([c, q]) == q
    except (ValueError, OSError):
        return False


def safe_rel(rel):
    """目标相对路径必须留在目标目录内，拒绝绝对路径与 .. 越界。"""
    rel = os.path.normpath(rel)
    if os.path.isabs(rel):
        return False
    return rel != ".." and not rel.startswith(".." + os.sep)


def send_to_recycle_bin(path):
    """把单个文件或整个文件夹送入 Windows 回收站（可还原），绝不永久删除。"""
    if os.name != "nt":
        raise RuntimeError("回收站功能仅支持 Windows")

    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [
            ("hwnd", ctypes.c_void_p),
            ("wFunc", ctypes.c_uint),
            ("pFrom", ctypes.c_wchar_p),
            ("pTo", ctypes.c_wchar_p),
            ("fFlags", ctypes.c_uint16),
            ("fAnyOperationsAborted", ctypes.c_int),
            ("hNameMappings", ctypes.c_void_p),
            ("lpszProgressTitle", ctypes.c_wchar_p),
        ]

    op = SHFILEOPSTRUCTW()
    op.hwnd = None
    op.wFunc = 3                      # FO_DELETE
    op.pFrom = path + "\0"            # 双 NUL 结尾
    op.pTo = None
    op.fFlags = 0x0040 | 0x0010 | 0x0004 | 0x0400  # ALLOWUNDO|NOCONFIRM|SILENT|NOERRORUI
    op.fAnyOperationsAborted = 0
    op.hNameMappings = None
    op.lpszProgressTitle = None
    res = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
    if res != 0 or op.fAnyOperationsAborted:
        raise RuntimeError("送入回收站失败(代码 {})，源文件已保留".format(res))


def transfer_multi(src_list, dest_list, mode="copy", conflict="rename",
                   verify_hash=False, progress=None, log=None,
                   layout=None, ensure_dirs=None, folder_roots=None,
                   folder_totals=None):
    """
    每个文件复制到【每一个】目标文件夹，并按 layout 保留文件夹层级。

    layout        {源文件: 相对目标路径}，例如 '项目A/子目录/a.txt'
    ensure_dirs   需要一并创建的相对目录（含空文件夹）
    folder_roots  {源文件: 根文件夹 or None}
    folder_totals {根文件夹: 添加时收集到的文件总数}

    移动模式：优先把「全部文件在所有目标都成功」的源文件夹整体送回收站
    （不留空壳、可还原）；条件不满足时退回逐文件安全清理。
    散文件始终逐文件清理；任何失败/跳过，源文件一律保留。
    """
    result = {"ok": [], "skipped": [], "failed": []}
    layout = layout or {}
    folder_roots = folder_roots or {}
    folder_totals = folder_totals or {}
    total = len(src_list) * len(dest_list)
    done = 0
    status = {}

    # 先补建目录骨架：文件夹连同子目录、空文件夹一起落地
    for dest_dir in dest_list:
        for rel in (ensure_dirs or []):
            if not safe_rel(rel):
                continue
            try:
                os.makedirs(os.path.join(dest_dir, rel), exist_ok=True)
            except OSError as exc:
                if log:
                    log("[警告] 无法创建目录 {}：{}".format(rel, exc))

    for src in src_list:
        src_ok = 0
        src_clean = True
        rel = os.path.normpath(layout.get(src, os.path.basename(src)))
        for dest_dir in dest_list:
            done += 1
            dst = ""
            try:
                if not os.path.isfile(src):
                    raise RuntimeError("源文件不存在或不是文件")
                if not safe_rel(rel):
                    raise RuntimeError("目标相对路径不合法")
                root = folder_roots.get(src)
                if root and is_within(dest_dir, root):
                    result["skipped"].append((src, dest_dir, "目标位于源文件夹内部，已跳过"))
                    src_clean = False
                    if log:
                        log("[跳过] {} → {}（目标在源文件夹内部）".format(rel, dest_dir))
                    continue

                dst = os.path.join(dest_dir, rel)
                dst_dir = os.path.dirname(dst)
                if os.path.normcase(os.path.abspath(dst_dir)) == \
                        os.path.normcase(os.path.abspath(os.path.dirname(src))):
                    result["skipped"].append((src, dest_dir, "源与目标为同一文件夹，已跳过"))
                    src_clean = False
                    if log:
                        log("[跳过] {}（同一目录）".format(rel))
                    continue
                os.makedirs(dst_dir, exist_ok=True)

                if os.path.exists(dst):
                    if conflict == "skip":
                        result["skipped"].append((src, dst, "目标已存在，按设置跳过"))
                        src_clean = False
                        if log:
                            log("[跳过] {} 目标已存在".format(rel))
                        continue
                    if conflict == "rename":
                        dst = unique_path(dst)

                shutil.copy2(src, dst)
                good = os.path.getsize(src) == os.path.getsize(dst)
                if verify_hash and good:
                    good = file_hash(src) == file_hash(dst)
                if not good:
                    try:
                        os.remove(dst)      # 只删本次刚生成的不完整副本
                    except OSError:
                        pass
                    raise RuntimeError("校验未通过，已删除不完整副本，源文件未改动")

                note = "复制成功" + ("（SHA-256 校验）" if verify_hash else "（按大小校验）")
                result["ok"].append((src, dst, note))
                src_ok += 1
                if log:
                    log("[成功] {} → {}".format(rel, dst))
            except Exception as exc:
                src_clean = False
                msg = "{}: {}".format(type(exc).__name__, exc)
                result["failed"].append((src, dst or dest_dir, msg))
                if log:
                    log("[失败] {} {}".format(rel, msg))
            finally:
                if progress:
                    progress(done, total)
        status[src] = (src_clean, src_ok)

    if mode == "move":
        groups = {}
        for src in src_list:
            groups.setdefault(folder_roots.get(src), []).append(src)
        # 嵌套的源文件夹只保留最外层，避免重复送回收站
        roots_all = [r for r in groups if r]
        roots_top = [r for r in roots_all
                     if not any(r != o and is_within(r, o) for o in roots_all)]
        whole_done = set()
        for root in roots_top:
            members = groups[root]
            expected = folder_totals.get(root, len(members))
            if len(members) == expected and all(
                    status[s][0] and status[s][1] == len(dest_list)
                    for s in members):
                try:
                    send_to_recycle_bin(root)
                    whole_done.add(root)
                    if log:
                        log("[移动] 文件夹「{}」已整体送回收站（可还原）".format(
                            os.path.basename(root)))
                except Exception as exc:
                    if log:
                        log("[警告] 文件夹未整体清理：{}；改为逐文件处理".format(exc))

        for src in src_list:
            root = folder_roots.get(src)
            if root and any(is_within(root, w) for w in whole_done):
                continue                       # 已随父文件夹整体移走
            clean, ok = status[src]
            if clean and ok == len(dest_list) and ok > 0:
                try:
                    send_to_recycle_bin(src)
                    if log:
                        log("[移动] {} 已送回收站（可还原）".format(
                            os.path.basename(src)))
                except Exception as exc:
                    result["failed"].append(
                        (src, "", "回收站处理失败：{}；源文件已保留".format(exc)))
                    if log:
                        log("[警告] {} 源文件未删除：{}".format(
                            os.path.basename(src), exc))
            else:
                if log:
                    log("[保留] {} 未在所有目标成功，源文件保留".format(
                        os.path.basename(src)))
    return result


def human_size(n):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return "{} B".format(n) if unit == "B" else "{:.1f} {}".format(n, unit)
        n /= 1024.0
    return "{} B".format(n)


# ------------------------------------------------------------------ 星标与重命名工具
STAR = "★"
STAR_RE = re.compile(r"^\((★{1,10})\)[ \t]*")
BAD_CHARS = set('\\/:*?"<>|')


def star_prefix(n):
    """1~10 星的名称前缀；0 星返回空串。"""
    return "({}) ".format(STAR * n) if 1 <= n <= 10 else ""


def split_star(name):
    """'(★★★) 报告.pdf' -> (3, '报告.pdf')；无前缀 -> (0, name)。"""
    m = STAR_RE.match(name)
    if not m:
        return 0, name
    return len(m.group(1)), name[m.end():]


def star_label(n):
    return (STAR * n) if n else "—"


def valid_name(name):
    if not name or not name.strip():
        return False, "名称不能为空"
    if name != name.strip():
        return False, "名称首尾不能有空格"
    if name.endswith("."):
        return False, "名称不能以句点结尾"
    for ch in name:
        if ch in BAD_CHARS:
            return False, "名称不能包含 \\ / : * ? \" < > |"
    if len(name) > 200:
        return False, "名称过长（超过 200 字符）"
    return True, ""


def rename_with_star(path, n):
    """把磁盘上的文件/文件夹改成 n 星名称。返回 (新路径, 是否有变化, 错误信息)。"""
    folder, old = os.path.split(path)
    _s, base = split_star(old)
    if not base:
        return path, False, "去掉星标后名称为空，无法修改"
    new = star_prefix(n) + base
    if new == old:
        return path, False, ""
    ok, msg = valid_name(new)
    if not ok:
        return path, False, msg
    dst = os.path.join(folder, new)
    if os.path.normcase(os.path.abspath(dst)) != os.path.normcase(os.path.abspath(path)) \
            and os.path.exists(dst):
        dst = unique_path(dst)          # 撞名时自动加序号，绝不覆盖别人
    try:
        os.rename(path, dst)
    except OSError as exc:
        return path, False, "重命名失败：{}".format(exc)
    return dst, True, ""


def rename_free(path, new_name):
    """手动重命名（编辑完整名称）。返回 (新路径, 是否有变化, 错误信息)。"""
    folder, old = os.path.split(path)
    ok, msg = valid_name(new_name)
    if not ok:
        return path, False, msg
    if new_name == old:
        return path, False, ""
    dst = os.path.join(folder, new_name)
    if os.path.normcase(os.path.abspath(dst)) != os.path.normcase(os.path.abspath(path)) \
            and os.path.exists(dst):
        dst = unique_path(dst)
    try:
        os.rename(path, dst)
    except OSError as exc:
        return path, False, "重命名失败：{}".format(exc)
    return dst, True, ""


# ------------------------------------------------------------------ DPI 感知
def enable_dpi_awareness():
    """
    备用工具：在创建任何窗口之前声明 DPI 感知。

    v2.2 实测后【故意不启用】。本机为 150% 缩放（物理 2560x1600 /
    逻辑 1707x1067），声明后 tk scaling 从 1.332 升到 1.998，字体放大
    1.5 倍而窗口物理尺寸不变，四张卡片会被挤出窗口 —— 属于新的布局回归。

    真正的修复是把文件夹 / 文件选择全部换成纯 Tk 自绘浏览器，彻底不再
    调用 Windows shell 目录对话框，也就不会触发 DPI 上下文来回切换。
    """
    if os.name != "nt":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)   # PROCESS_SYSTEM_DPI_AWARE
        return
    except Exception:
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


# ------------------------------------------------------------------ 自定义控件
# ------------------------------------------------------------------ 抗锯齿圆角背景
_AA_PNG_CACHE = {}


def _rgb_of(color):
    """'#RRGGBB' / '#RGB' -> (r, g, b)"""
    c = color.lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def relative_luminance(color):
    r, g, b = _rgb_of(color)
    return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255.0


def aa_rounded(w, h, radius, color):
    """
    生成【透明底 + 抗锯齿圆角】的 tk.PhotoImage。

    旧版 fill_round 用 Canvas 的 create_oval 拼圆角，而 Canvas 没有抗锯齿，
    圆角处必然出现阶梯状锯齿。这里改成 4 倍超采样绘制 + LANCZOS 缩小，
    因此任意宽度 / 高度 / 圆角 / 颜色（含 hover、disabled 各状态）都能得到
    平滑干净的边缘。PNG 按参数缓存，运行时只需 Tk 自带的 PhotoImage。

    返回 None 表示当前环境无法生成（自动降级到旧的 fill_round，不崩溃）。
    """
    w, h = int(w), int(h)
    if w < 2 or h < 2:
        return None
    radius = max(0, min(int(radius), min(w, h) // 2))
    key = (w, h, radius, color)
    data = _AA_PNG_CACHE.get(key)
    if data is None:
        if not AA_OK:
            return None
        scale = 4
        big = _AAImage.new("RGBA", (w * scale, h * scale), (0, 0, 0, 0))
        r, g, b = _rgb_of(color)
        _AADraw.Draw(big).rounded_rectangle(
            (0, 0, w * scale - 1, h * scale - 1),
            radius=radius * scale, fill=(r, g, b, 255))
        small = big.resize((w, h), _AAImage.Resampling.LANCZOS)
        buf = io.BytesIO()
        small.save(buf, format="PNG")
        data = base64.b64encode(buf.getvalue()).decode("ascii")
        _AA_PNG_CACHE[key] = data
    try:
        return tk.PhotoImage(data=data)
    except Exception:
        return None


def fill_round(cv, x1, y1, x2, y2, r, color, tags):
    cv.create_rectangle(x1 + r, y1, x2 - r, y2, fill=color, outline=color, tags=tags)
    cv.create_rectangle(x1, y1 + r, x2, y2 - r, fill=color, outline=color, tags=tags)
    for ox, oy in ((x1, y1), (x2 - 2 * r, y1), (x1, y2 - 2 * r), (x2 - 2 * r, y2 - 2 * r)):
        cv.create_oval(ox, oy, ox + 2 * r, oy + 2 * r, fill=color, outline=color, tags=tags)


class Pill(tk.Canvas):
    """抗锯齿圆角扁平按钮，normal / hover / disabled 三态边缘都平滑。"""
    def __init__(self, master, text, command, color, fg="#FFFFFF",
                 w=112, h=32, hover=None, bg=CARD, big=False):
        super().__init__(master, width=w, height=h, bg=bg,
                         highlightthickness=0, bd=0, cursor="hand2")
        self.color = color
        self.hover_color = hover or color
        # 亮底（中黄 / 柔黄）自动换成深墨字，保证多巴胺亮色上的文字对比度
        self.fg = INK if (fg == "#FFFFFF"
                          and relative_luminance(color) > 0.62) else fg
        self.command = command
        self.w, self.h = w, h
        self.radius = min(BTN_RADIUS, (h - 2) // 2, w // 2)
        self.enabled = True
        self._img = None
        self._draw(color)
        self.create_text(w / 2, h / 2, text=text, fill=self.fg,
                         font=(FONT, 11 if big else 10, "bold"), tags="txt")
        self.bind("<Enter>", lambda e: self._draw(self.hover_color) if self.enabled else None)
        self.bind("<Leave>", lambda e: self._draw(self.color) if self.enabled else None)
        self.bind("<Button-1>", lambda e: self.command() if self.enabled else None)

    def _draw(self, color):
        self.delete("pill")
        img = aa_rounded(self.w, self.h, self.radius, color)
        if img is not None:
            self._img = img          # 必须持有引用，否则 PhotoImage 会被回收
            self.create_image(0, 0, image=img, anchor="nw", tags="pill")
        else:                        # 无 Pillow 时的降级：功能不受影响
            fill_round(self, 1, 1, self.w - 1, self.h - 1,
                       (self.h - 2) // 2, color, "pill")
        self.tag_lower("pill")

    def set_enabled(self, ok):
        self.enabled = bool(ok)
        self.configure(cursor="hand2" if self.enabled else "arrow")
        self._draw(self.color if self.enabled else NEUTRAL)
        try:
            self.itemconfigure("txt", fill=self.fg if self.enabled else MUTED)
        except Exception:
            pass


class Header(tk.Canvas):
    """暖色渐变标题栏；白字带 1px 深棕投影，保证亮黄段同样清晰。"""
    def __init__(self, master, title="文件搬运工具",
                 subtitle="多选 · 拖拽 · 保留文件夹结构 · 多目标",
                 version="v2.3  ·  纯本地运行", height=88, icon=True):
        super().__init__(master, height=height, bg=BG, highlightthickness=0, bd=0)
        self.h_text, self.sub_text, self.ver_text = title, subtitle, version
        self.icon_img = None
        if icon:
            try:
                # 56x56 高清 PNG，边缘已抗锯齿；不依赖 Pillow 运行时
                self.icon_img = tk.PhotoImage(file=resource_path("icon_ui.png"))
            except Exception:
                pass
        self.bind("<Configure>", self._paint)

    def _text(self, x, y, value, font, anchor, fill):
        self.create_text(x + 1, y + 1, text=value, anchor=anchor,
                         fill="#8A3B24", font=font, tags="hg")
        self.create_text(x, y, text=value, anchor=anchor,
                         fill=fill, font=font, tags="hg")

    def _paint(self, ev=None):
        w, h = self.winfo_width(), self.winfo_height()
        if w < 40:
            return
        self.delete("hg")
        for x in range(w):
            self.create_line(x, 0, x, h, fill=hexc(grad(x / max(w - 1, 1))), tags="hg")
        self.create_oval(w - 150, -70, w + 40, 120,
                         fill=hexc(lerp(SUN_RGB, (255, 255, 255), 0.16)),
                         outline="", tags="hg")
        self.create_oval(w - 40, 48, w + 90, 178,
                         fill=hexc(lerp(BERRY_RGB, (255, 255, 255), 0.16)),
                         outline="", tags="hg")
        if self.icon_img:
            self.create_image(22, 16, image=self.icon_img, anchor="nw", tags="hg")
        tx = 92 if self.icon_img else 26
        self._text(tx, 18, self.h_text, (FONT, 22, "bold"), "nw", "#FFFFFF")
        self._text(tx + 2, 57, self.sub_text, (FONT, 10), "nw", "#FFF6E8")
        self._text(w - 24, 22, "by 微尘", (FONT, 12, "bold"), "ne", "#FFFFFF")
        self._text(w - 24, 49, self.ver_text, (FONT, 9), "ne", "#FFF0DC")


class Card(tk.Frame):
    """圆角白卡片，标题由 Canvas 绘制，控件放在 body 里。"""
    HEADER = 36

    def __init__(self, master, title, accent, badge=""):
        super().__init__(master, bg=BG)
        self.accent = accent
        self.title_text = title
        self.badge = badge
        self.cv = tk.Canvas(self, bg=BG, highlightthickness=0, bd=0, height=120)
        self.cv.pack(fill="both", expand=True)
        self.body = tk.Frame(self.cv, bg=CARD)
        self.win = self.cv.create_window(14, self.HEADER, window=self.body, anchor="nw")
        self._last_w = -1
        self.body.bind("<Configure>", self._on_body)
        self.cv.bind("<Configure>", self._on_cv)

    def _on_cv(self, ev):
        w = max(ev.width - 28, 40)
        if w != self._last_w:
            self._last_w = w
            self.cv.itemconfigure(self.win, width=w)
        self._paint()

    def _on_body(self, ev):
        need = self.HEADER + ev.height + 10
        if self.cv.winfo_height() != need:
            self.cv.configure(height=need)
        self._paint()

    def _paint(self):
        w, h = self.cv.winfo_width(), self.cv.winfo_height()
        if w < 60 or h < 60:
            return
        self.cv.delete("bg")
        self.cv.delete("bgimg")
        cw, ch = max(w - 8, 40), max(h - 8, 40)
        # ① 柔和暖阴影 ② 卡片本体：两张都是抗锯齿圆角图，边缘无阶梯
        sh = aa_rounded(cw, ch, CARD_RADIUS, SHADOW)
        card = aa_rounded(cw, ch, CARD_RADIUS, CARD)
        if sh is not None and card is not None:
            self._shadow_img, self._card_img = sh, card
            self.cv.create_image(6, 7, image=sh, anchor="nw", tags="bgimg")
            self.cv.create_image(2, 2, image=card, anchor="nw", tags="bgimg")
            self.cv.tag_lower("bgimg")
        else:                        # 降级：仍能正常显示，只是圆角带锯齿
            fill_round(self.cv, 3, 5, w - 3, h - 3, 18, SHADOW, "bg")
            fill_round(self.cv, 2, 2, w - 4, h - 4, 18, CARD, "bg")
        # ③ 标题左侧彩色方点（直角，天然无锯齿）+ 细分隔线，强化层次
        self.cv.create_rectangle(16, 13, 27, 24, fill=self.accent,
                                 outline="", tags="bg")
        self.cv.create_text(35, 18, text=self.title_text, anchor="w", fill=INK,
                            font=(FONT, 11, "bold"), tags="bg")
        if self.badge:
            self.cv.create_text(w - 18, 18, text=self.badge, anchor="e",
                                fill=MUTED, font=(FONT, 9), tags="bg")
        self.cv.create_line(16, 31, w - 18, 31, fill=BORDER, tags="bg")


def make_listbox(parent, height, select_bg=ORANGE):
    frame = tk.Frame(parent, bg=CARD)
    lb = tk.Listbox(frame, height=height, selectmode="extended",
                    bg="#FFFCF7", fg=INK, selectbackground=select_bg,
                    selectforeground="#FFFFFF", highlightthickness=1,
                    highlightbackground=BORDER, highlightcolor=select_bg,
                    relief="flat", bd=0, font=(FONT, 9), activestyle="none")
    sb = ttk.Scrollbar(frame, orient="vertical", command=lb.yview)
    lb.configure(yscrollcommand=sb.set)
    lb.pack(side="left", fill="both", expand=True)
    sb.pack(side="right", fill="y")
    return frame, lb


def make_entry(parent, textvar):
    return tk.Entry(parent, textvariable=textvar, bg="#FFFBF4", fg=INK,
                    relief="flat", bd=0, highlightthickness=1,
                    highlightbackground=BORDER, highlightcolor=YELLOW,
                    insertbackground=INK, font=(FONT, 10))


def small_label(parent, text="", fg=MUTED, var=None):
    return tk.Label(parent, text=text, textvariable=var, bg=CARD, fg=fg,
                    font=(FONT, 9), anchor="w")


# ------------------------------------------------------------------ 自绘目录 / 文件浏览器
def center_window(win, master, w, h):
    """固定尺寸并居中到父窗口，避免系统随机摆放造成的视觉跳变。"""
    try:
        master.update_idletasks()
        x = master.winfo_rootx() + max((master.winfo_width() - w) // 2, 0)
        y = master.winfo_rooty() + max((master.winfo_height() - h) // 2, 0)
    except Exception:
        x, y = 80, 60
    try:
        sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
        x = max(0, min(x, max(sw - w, 0)))
        y = max(0, min(y, max(sh - h - 60, 0)))
    except Exception:
        pass
    win.geometry("{}x{}+{}+{}".format(w, h, x, y))
    try:
        # 双保险：即使窗口管理器因 DPI 消息重算尺寸，也不会缩到设计尺寸以下
        win.minsize(w, h)
    except Exception:
        pass


class TextPrompt(tk.Toplevel):
    """纯 Tk 输入框，用来替代任何系统原生输入对话框。"""
    def __init__(self, master, title, prompt, initial=""):
        super().__init__(master)
        self.title(title)
        self.configure(bg=BG)
        self.resizable(False, False)
        self.value = None
        wrap = tk.Frame(self, bg=BG, padx=18, pady=16)
        wrap.pack(fill="both", expand=True)
        tk.Label(wrap, text=prompt, bg=BG, fg=INK, font=(FONT, 10),
                 wraplength=380, justify="left").pack(anchor="w", pady=(0, 10))
        self.var = tk.StringVar(value=initial)
        e = make_entry(wrap, self.var)
        e.pack(fill="x", ipady=5)
        e.focus_set()
        e.select_range(0, "end")
        bar = tk.Frame(wrap, bg=BG)
        bar.pack(fill="x", pady=(14, 0))
        Pill(bar, "取消", self._cancel, "#F7EBDD", fg=INK, w=84,
             hover="#EFDFCC", bg=BG).pack(side="right", padx=BTN_GAP)
        Pill(bar, "确定", self._ok, YELLOW, w=84, hover=YELLOW_DK, bg=BG).pack(side="right", padx=BTN_GAP)
        e.bind("<Return>", lambda _e: self._ok())
        e.bind("<Escape>", lambda _e: self._cancel())
        self.transient(master)
        center_window(self, master, 430, 170)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._cancel)

    def _ok(self):
        self.value = self.var.get().strip()
        self.destroy()

    def _cancel(self):
        self.value = None
        self.destroy()


def ask_text(master, title, prompt, initial=""):
    d = TextPrompt(master, title, prompt, initial)
    master.wait_window(d)
    return d.value


class BrowseFolderDialog(tk.Toplevel):
    """
    纯 Tk 自绘的文件夹 / 文件浏览器。

    这是 v2.2 修复「分辨率突变」的关键：不再调用 Windows shell 目录对话框
    （SHBrowseForFolder / IFileDialog），因此在其内部新建文件夹时不会触发
    进程 DPI 上下文切换，窗口尺寸、字体、控件位置全程恒定。

    mode="folder" -> 返回单个目录路径；mode="files" -> 返回选中的文件路径列表。
    """
    W, H = 660, 500

    def __init__(self, master, title="选择文件夹", initial=None,
                 mode="folder", allow_new=True):
        super().__init__(master)
        self.title(title)
        self.configure(bg=BG)
        self.resizable(False, False)
        self.mode = mode
        self.allow_new = allow_new
        self.result = None
        self.entries = []
        start = initial if initial and os.path.isdir(initial) else os.path.expanduser("~")
        self.current = os.path.normpath(os.path.abspath(start))
        self.path_var = tk.StringVar()
        try:
            self.iconbitmap(resource_path("icon.ico"))
        except Exception:
            pass

        wrap = tk.Frame(self, bg=BG, padx=16, pady=14)
        wrap.pack(fill="both", expand=True)
        tip = ("在下方列表中浏览，双击进入子文件夹；点「新建文件夹」可直接创建。"
               if mode == "folder" else
               "在下方列表中可 Ctrl / Shift 多选文件；双击文件夹进入。")
        tk.Label(wrap, text=tip, bg=BG, fg=MUTED, font=(FONT, 9),
                 wraplength=620, justify="left").pack(anchor="w", pady=(0, 10))

        nav = tk.Frame(wrap, bg=BG)
        nav.pack(fill="x", pady=(0, 8))
        Pill(nav, "↑ 上级", self.go_up, "#F7EBDD", fg=INK, w=76, h=30,
             hover="#EFDFCC", bg=BG).pack(side="left", padx=(0, BTN_GAP))
        self.drive = ttk.Combobox(nav, state="readonly", width=8, values=())
        self.drive.pack(side="left", padx=(0, 8))
        self.drive.bind("<<ComboboxSelected>>", self.on_drive)
        tk.Entry(nav, textvariable=self.path_var, bg="#FFFBF4", fg=INK,
                 relief="flat", bd=0, highlightthickness=1,
                 highlightbackground=BORDER, font=(FONT, 9),
                 state="readonly").pack(side="left", fill="x", expand=True, ipady=4)
        Pill(nav, "刷新", self._refresh, "#F7EBDD", fg=INK, w=64, h=30,
             hover="#EFDFCC", bg=BG).pack(side="left", padx=(8, 0))

        lf, self.lb = make_listbox(wrap, 15, ORANGE)
        lf.pack(fill="both", expand=True)
        self.lb.bind("<Double-Button-1>", self.on_double)

        tools = tk.Frame(wrap, bg=BG)
        tools.pack(fill="x", pady=(10, 0))
        if allow_new:
            Pill(tools, "+ 新建文件夹", self.new_folder, ORANGE, w=124, h=32,
                 hover="#EC5A2D", bg=BG).pack(side="left", padx=(0, BTN_GAP))
        self.count = tk.Label(tools, text="", bg=BG, fg=MUTED, font=(FONT, 9))
        self.count.pack(side="left", padx=6)

        bottom = tk.Frame(wrap, bg=BG)
        bottom.pack(fill="x", pady=(10, 0))
        Pill(bottom, "取消", self.cancel, "#F7EBDD", fg=INK, w=88,
             hover="#EFDFCC", bg=BG).pack(side="right", padx=BTN_GAP)
        label = "选择当前文件夹" if mode == "folder" else "添加选中文件"
        Pill(bottom, label, self.confirm, YELLOW, w=140,
             hover=YELLOW_DK, bg=BG).pack(side="right", padx=BTN_GAP)

        self.transient(master)
        center_window(self, master, self.W, self.H)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self.cancel)
        self._load_drives()
        self._refresh()

    def _load_drives(self):
        drives = [c + ":\\" for c in string.ascii_uppercase
                  if os.path.exists(c + ":\\")]
        self.drive["values"] = drives
        cur = os.path.splitdrive(self.current)[0] + "\\"
        if cur in drives:
            self.drive.set(cur)

    def _refresh(self):
        self.path_var.set(self.current)
        self.lb.delete(0, "end")
        self.entries = []
        try:
            names = sorted(os.listdir(self.current), key=lambda s: s.lower())
        except OSError as exc:
            self.count.configure(text="无法读取：{}".format(exc))
            return
        dirs, files = [], []
        for n in names:
            p = os.path.join(self.current, n)
            if os.path.isdir(p):
                dirs.append((n, p))
            elif self.mode == "files" and os.path.isfile(p):
                files.append((n, p))
        for n, p in dirs:
            self.entries.append(p)
            self.lb.insert("end", "[文件夹]  " + n)
        for n, p in files:
            self.entries.append(p)
            self.lb.insert("end", "[文件]      " + n)
        tail = "  ·  {} 个文件".format(len(files)) if self.mode == "files" else ""
        self.count.configure(text="{} 个子文件夹{}".format(len(dirs), tail))

    def on_double(self, _e):
        for i in self.lb.curselection():
            p = self.entries[i] if i < len(self.entries) else None
            if p and os.path.isdir(p):
                self.current = os.path.normpath(p)
                self._refresh()
                return

    def go_up(self):
        parent = os.path.dirname(self.current.rstrip(os.sep))
        if parent and parent != self.current and os.path.isdir(parent):
            self.current = parent
            self._refresh()

    def on_drive(self, _e=None):
        d = self.drive.get()
        if d and os.path.isdir(d):
            self.current = os.path.normpath(d)
            self._refresh()

    def new_folder(self):
        name = ask_text(self, "新建文件夹",
                        "在下方当前目录中新建文件夹，请输入名称：\n" + self.current,
                        "新建文件夹")
        if not name:
            return
        ok, msg = valid_name(name)
        if not ok:
            messagebox.showwarning("名称无效", msg, parent=self)
            return
        p = os.path.join(self.current, name)
        if os.path.exists(p):
            messagebox.showwarning("已存在", "该名称已经存在，请换一个。", parent=self)
            return
        try:
            os.mkdir(p)
        except OSError as exc:
            messagebox.showerror("创建失败", str(exc), parent=self)
            return
        self._refresh()
        if p in self.entries:
            i = self.entries.index(p)
            self.lb.selection_clear(0, "end")
            self.lb.selection_set(i)
            self.lb.see(i)

    def confirm(self):
        if self.mode == "folder":
            self.result = self.current
        else:
            paths = [self.entries[i] for i in self.lb.curselection()
                     if i < len(self.entries) and os.path.isfile(self.entries[i])]
            if not paths:
                messagebox.showinfo("提示", "请先在列表中选中一个或多个文件。", parent=self)
                return
            self.result = paths
        self.destroy()

    def cancel(self):
        self.result = None
        self.destroy()


def pick_browse(master, title, initial=None, mode="folder", allow_new=True):
    d = BrowseFolderDialog(master, title, initial, mode, allow_new)
    master.wait_window(d)
    return d.result


# ------------------------------------------------------------------ 星标管理器
class StarManagerDialog(tk.Toplevel):
    """
    打开一个文件夹，列出其中所有文件与子文件夹，可打 1~10 星、按星级筛选、
    手动重命名、一键清除全部星标，最后把筛选结果送回文件搬运流程。

    星标直接以 '(★★★) ' 前缀写进磁盘上的名称（可随时清除还原），
    不使用任何外部数据库或配置文件。
    """
    W, H = 940, 820

    def __init__(self, master, folder, on_apply=None, log=None):
        super().__init__(master)
        self.title("★ 星标管理  ·  by 微尘")
        self.configure(bg=BG)
        self.resizable(False, False)
        self.folder = os.path.normpath(os.path.abspath(folder))
        self.on_apply = on_apply
        self.log = log or (lambda _t: None)
        self.items = []
        self.shown = []
        self.filter_var = tk.StringVar(value="全部")
        self.at_least = tk.BooleanVar(value=False)
        self.status = tk.StringVar()
        self.dir_var = tk.StringVar()
        try:
            self.iconbitmap(resource_path("icon.ico"))
        except Exception:
            pass

        Header(self, title="★ 星标管理",
               subtitle="给文件 / 文件夹打 1~10 星，按星级筛选后送回搬运",
               version="v2.3 · 微尘", height=78).pack(fill="x")

        main = tk.Frame(self, bg=BG)
        main.pack(fill="both", expand=True, padx=16, pady=8)

        top = tk.Frame(main, bg=BG)
        top.pack(fill="x", pady=(0, 8))
        tk.Label(top, text="当前文件夹", bg=BG, fg=INK,
                 font=(FONT, 10, "bold")).pack(side="left", padx=(0, 8))
        tk.Label(top, textvariable=self.dir_var, bg=BG, fg=ORANGE,
                 font=(FONT, 9), anchor="w").pack(side="left", fill="x", expand=True)
        Pill(top, "切换文件夹", self.change_folder, ORANGE, w=104, h=30,
             hover="#EC5A2D", bg=BG).pack(side="left", padx=BTN_GAP)
        Pill(top, "刷新", self.refresh, "#F7EBDD", fg=INK, w=64, h=30,
             hover="#EFDFCC", bg=BG).pack(side="left", padx=BTN_GAP)

        c1 = Card(main, "① 给选中项打星", YELLOW, badge="星标写进名称前缀，可随时清除")
        c1.pack(fill="x", pady=(0, 7))
        b1 = c1.body
        stars = tk.Frame(b1, bg=CARD)
        stars.pack(fill="x", pady=(0, 6))
        for n in range(0, 11):
            if n == 0:
                color, fg = "#F7EBDD", INK
            elif n <= 3:
                color, fg = ORANGE, "#FFFFFF"
            elif n <= 6:
                color, fg = YELLOW, INK
            elif n <= 9:
                color, fg = PINK, "#FFFFFF"
            else:
                color, fg = VIOLET, "#FFFFFF"
            label = "清除" if n == 0 else "{}★".format(n)
            Pill(stars, label, lambda x=n: self.apply_star(x), color,
                 fg=fg, w=68, h=30).pack(side="left", padx=BTN_GAP)
        tk.Label(b1, text="例如 (★★★) 报告.pdf 表示 3 星；打星只改名称前缀，原名与扩展名保持不变。",
                 bg=CARD, fg=MUTED, font=(FONT, 9), anchor="w").pack(fill="x")

        c2 = Card(main, "② 筛选与操作", ORANGE, badge="筛选结果可直接送回搬运")
        c2.pack(fill="x", pady=(0, 7))
        b2 = c2.body
        row = tk.Frame(b2, bg=CARD)
        row.pack(fill="x")
        tk.Label(row, text="按星标筛选", bg=CARD, fg=INK,
                 font=(FONT, 10)).pack(side="left")
        values = ["全部", "未标星"] + ["{}★".format(i) for i in range(1, 11)]
        self.combo = ttk.Combobox(row, state="readonly", width=9,
                                  values=values, textvariable=self.filter_var)
        self.combo.current(0)
        self.combo.bind("<<ComboboxSelected>>", lambda _e: self.refresh())
        self.combo.pack(side="left", padx=(8, 12))
        tk.Checkbutton(row, text="≥ 该星级及以上", variable=self.at_least,
                       command=self.refresh, bg=CARD, fg=INK,
                       selectcolor=SOFT_YELLOW, activebackground=CARD,
                       highlightthickness=0, font=(FONT, 10)).pack(side="left", padx=(0, 14))
        Pill(row, "重命名选中", self.rename_selected, PINK, w=106, h=30,
             hover="#DA3070").pack(side="left", padx=BTN_GAP)
        Pill(row, "清除全部星标", self.clear_all, VIOLET, w=116, h=30,
             hover="#8552EA").pack(side="left", padx=BTN_GAP)
        tk.Label(b2, text="单击选中 · Ctrl / Shift 多选 · 双击重命名",
                 bg=CARD, fg=MUTED, font=(FONT, 9), anchor="w").pack(fill="x", pady=(6, 0))

        c3 = Card(main, "③ 文件夹内容", PINK, badge="显示所选文件夹的顶层文件与子文件夹")
        c3.pack(fill="both", expand=True, pady=(0, 7))
        b3 = c3.body
        st = ttk.Style()
        st.configure("Star.Treeview", background="#FFFCF7",
                     fieldbackground="#FFFCF7", foreground=INK,
                     rowheight=27, bordercolor=BORDER, font=(FONT, 10))
        st.configure("Star.Treeview.Heading", background=SOFT_ORANGE,
                     foreground=INK, font=(FONT, 10, "bold"),
                     relief="flat", padding=4)
        st.map("Star.Treeview", background=[("selected", ORANGE)],
               foreground=[("selected", "#FFFFFF")])
        self.tree = ttk.Treeview(b3, style="Star.Treeview",
                                 columns=("type", "star", "name", "size"),
                                 show="headings", height=10, selectmode="extended")
        for col, title, width, anchor in (
                ("type", "类型", 80, "center"),
                ("star", "星标", 132, "center"),
                ("name", "名称", 520, "w"),
                ("size", "大小", 100, "e")):
            self.tree.heading(col, text=title)
            self.tree.column(col, width=width, anchor=anchor, stretch=(col == "name"))
        self.tree.tag_configure("hot", foreground="#D64545")
        self.tree.tag_configure("dim", foreground=MUTED)
        vs = ttk.Scrollbar(b3, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vs.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vs.pack(side="right", fill="y")
        self.tree.bind("<Double-Button-1>", lambda _e: self.rename_selected())

        foot = tk.Frame(self, bg=BG)
        foot.pack(fill="x", padx=18, pady=(0, 10))
        tk.Label(foot, textvariable=self.status, bg=BG, fg=MUTED,
                 font=(FONT, 9), anchor="w").pack(side="left", fill="x", expand=True)
        Pill(foot, "关闭", self.close, "#F7EBDD", fg=INK, w=76, h=34,
             hover="#EFDFCC", bg=BG).pack(side="right", padx=BTN_GAP)
        Pill(foot, "把筛选结果送去搬运 →", self.send, YELLOW, w=196, h=34,
             hover=YELLOW_DK, big=True, bg=BG).pack(side="right", padx=BTN_GAP)

        self.transient(master)
        center_window(self, master, self.W, self.H)
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.refresh()

    # ---------------------------------------------------------- 数据
    def scan(self):
        out = []
        try:
            names = sorted(os.listdir(self.folder), key=lambda s: s.lower())
        except OSError:
            return out
        for n in names:
            p = os.path.join(self.folder, n)
            is_dir = os.path.isdir(p)
            size = 0
            if not is_dir:
                try:
                    size = os.path.getsize(p)
                except OSError:
                    pass
            star, _base = split_star(n)
            out.append({"path": p, "name": n, "star": star,
                        "is_dir": is_dir, "size": size})
        return out

    def refresh(self):
        self.dir_var.set(self.folder)
        self.items = self.scan()
        key = self.filter_var.get()
        at_least = self.at_least.get()
        if key == "全部":
            want = None
        elif key == "未标星":
            want = 0
        else:
            m = re.match(r"(\d+)★", key)
            want = int(m.group(1)) if m else None
        self.shown = []
        for it in self.items:
            if want is None:
                ok = True
            elif at_least and want > 0:
                ok = it["star"] >= want
            else:
                ok = it["star"] == want
            if ok:
                self.shown.append(it)
        kids = self.tree.get_children()
        if kids:
            self.tree.delete(*kids)
        for it in self.shown:
            tag = "hot" if it["star"] >= 7 else ("dim" if it["star"] == 0 else "")
            self.tree.insert("", "end", iid=it["path"], tags=(tag,) if tag else (),
                             values=("文件夹" if it["is_dir"] else "文件",
                                     star_label(it["star"]),
                                     it["name"],
                                     "—" if it["is_dir"] else human_size(it["size"])))
        marked = sum(1 for i in self.items if i["star"] > 0)
        extra = "（及以上）" if (at_least and want) else ""
        self.status.set("显示 {} / 共 {} 项   ·   已标星 {} 项   ·   筛选：{}{}".format(
            len(self.shown), len(self.items), marked, key, extra))

    # ---------------------------------------------------------- 操作
    def apply_star(self, n):
        sel = list(self.tree.selection())
        if not sel:
            messagebox.showinfo("提示", "请先在列表中选中一个或多个项目（可 Ctrl / Shift 多选）。",
                               parent=self)
            return
        errs, keep, changed = [], [], 0
        for p in sel:
            np, done, err = rename_with_star(p, n)
            if err:
                errs.append("{}：{}".format(os.path.basename(p), err))
            else:
                keep.append(np)
                if done:
                    changed += 1
        self.refresh()
        for np in keep:
            if self.tree.exists(np):
                self.tree.selection_add(np)
        self.log("[星标] {} 个项目设为 {}{}".format(
            len(sel), n, "★" if n else "（清除）"))
        if errs:
            messagebox.showwarning("部分未成功",
                                   "改名 {} 项，失败 {} 项：\n{}".format(
                                       changed, len(errs), "\n".join(errs[:6])),
                                   parent=self)

    def clear_all(self):
        marked = [i for i in self.items if i["star"] > 0]
        if not marked:
            messagebox.showinfo("提示", "当前文件夹里没有已打星标的项目。", parent=self)
            return
        if not messagebox.askyesno(
                "确认清除",
                "将清除当前文件夹内 {} 个项目的星标前缀，恢复原始名称。\n"
                "只改名称前缀，不会删除任何文件。\n\n确定继续吗？".format(len(marked)),
                parent=self):
            return
        errs, n_ok = [], 0
        for it in marked:
            _p, done, err = rename_with_star(it["path"], 0)
            if err:
                errs.append(it["name"])
            elif done:
                n_ok += 1
        self.refresh()
        self.log("[星标] 清除全部：{} 项恢复原名".format(n_ok))
        if errs:
            messagebox.showwarning("部分未成功",
                                   "以下 {} 项未能清除：\n{}".format(
                                       len(errs), "\n".join(errs[:6])), parent=self)

    def rename_selected(self):
        sel = list(self.tree.selection())
        if len(sel) != 1:
            messagebox.showinfo("提示", "请选中一个项目进行重命名。", parent=self)
            return
        p = sel[0]
        old = os.path.basename(p)
        new = ask_text(self, "重命名",
                       "输入新的名称（可保留或修改 (★) 前缀）：", old)
        if not new or new == old:
            return
        np, done, err = rename_free(p, new)
        if err:
            messagebox.showwarning("重命名失败", err, parent=self)
            return
        self.refresh()
        if self.tree.exists(np):
            self.tree.selection_set(np)
        self.log("[星标] 重命名：{} → {}".format(old, os.path.basename(np)))

    def change_folder(self):
        d = pick_browse(self, "选择要管理的文件夹", self.folder, "folder", True)
        if d:
            self.folder = os.path.normpath(os.path.abspath(d))
            self.refresh()

    def send(self):
        if not self.shown:
            messagebox.showinfo("提示", "当前筛选结果为空，请调整筛选条件。", parent=self)
            return
        if self.on_apply:
            self.on_apply(self.folder, list(self.shown))
        self.log("[星标] 已把 {} 个筛选结果送回搬运列表".format(len(self.shown)))
        self.destroy()

    def close(self):
        self.destroy()


# ------------------------------------------------------------------ 文件夹批量选择对话框
class FolderPickerDialog(tk.Toplevel):
    def __init__(self, master, title, show_recursive=False, recursive_default=False):
        super().__init__(master)
        self.title(title)
        self.configure(bg=BG)
        self.resizable(False, False)
        self.folders = []
        self.result = None
        self.recursive = tk.BooleanVar(value=recursive_default)

        wrap = tk.Frame(self, bg=BG, padx=18, pady=16)
        wrap.pack(fill="both", expand=True)
        tk.Label(wrap, text="可连续添加多个文件夹，一次全部导入", bg=BG, fg=INK,
                 font=(FONT, 11, "bold")).pack(anchor="w", pady=(0, 7))

        lf, self.lb = make_listbox(wrap, 7, ORANGE)
        lf.pack(fill="both", expand=True)
        bar = tk.Frame(wrap, bg=BG)
        bar.pack(fill="x", pady=10)
        Pill(bar, "+ 添加文件夹", self.add, ORANGE, w=118, bg=BG).pack(side="left", padx=(0, BTN_GAP))
        Pill(bar, "移除选中", self.remove, "#F7EBDD", fg=INK, w=96, hover="#EFDFCC", bg=BG).pack(side="left", padx=BTN_GAP)
        Pill(bar, "清空", self.clear, "#F7EBDD", fg=INK, w=68, hover="#EFDFCC", bg=BG).pack(side="left", padx=BTN_GAP)

        if show_recursive:
            tk.Checkbutton(wrap, text="包含子文件夹（递归收集）", variable=self.recursive,
                           bg=BG, fg=INK, selectcolor=SOFT_YELLOW, activebackground=BG,
                           highlightthickness=0, font=(FONT, 10)).pack(anchor="w", pady=(0, 7))

        bottom = tk.Frame(wrap, bg=BG)
        bottom.pack(fill="x")
        Pill(bottom, "取消", self.cancel, "#F7EBDD", fg=INK, w=88,
             hover="#EFDFCC", bg=BG).pack(side="right", padx=BTN_GAP)
        Pill(bottom, "确定导入", self.confirm, YELLOW, w=104,
             hover=YELLOW_DK, bg=BG).pack(side="right", padx=BTN_GAP)
        self.count = tk.Label(wrap, text="已添加 0 个文件夹", bg=BG, fg=MUTED, font=(FONT, 9))
        self.count.pack(anchor="w", pady=(4, 0))

        self.transient(master)
        self.grab_set()
        self.geometry("560x360")
        self.protocol("WM_DELETE_WINDOW", self.cancel)

    def _refresh(self):
        self.lb.delete(0, "end")
        for p in self.folders:
            self.lb.insert("end", p)
        self.count.configure(text="已添加 {} 个文件夹".format(len(self.folders)))

    def add(self):
        d = pick_browse(self, "选择一个文件夹", mode="folder")
        if d and d not in self.folders:
            self.folders.append(os.path.normpath(d))
            self._refresh()

    def remove(self):
        for i in reversed(self.lb.curselection()):
            del self.folders[i]
        self._refresh()

    def clear(self):
        self.folders.clear()
        self._refresh()

    def confirm(self):
        self.result = (list(self.folders), self.recursive.get())
        self.destroy()

    def cancel(self):
        self.result = None
        self.destroy()


def pick_folders(master, title, show_recursive=False, recursive_default=False):
    dlg = FolderPickerDialog(master, title, show_recursive, recursive_default)
    master.wait_window(dlg)
    return dlg.result


# ------------------------------------------------------------------ 主界面
class App:
    def __init__(self, root):
        self.root = root
        self.root.title("文件搬运工具 v2.3  ·  by 微尘")
        self.root.geometry("980x860+80+20")
        self.root.minsize(880, 760)
        self.root.configure(bg=BG)
        try:
            tkfont.nametofont("TkDefaultFont").configure(family=FONT, size=10)
            self.root.iconbitmap(resource_path("icon.ico"))
        except Exception:
            pass

        self.files = []
        self.file_roots = {}       # {文件路径: 所属根文件夹}；散文件不登记
        self.folder_totals = {}    # {根文件夹: 添加时收集到的文件总数}
        self.empty_dirs = set()    # 需要一并重建的相对目录（含空文件夹）
        self.targets = []
        self.favorites = []
        self.queue = queue.Queue()
        self.running = False

        self.mode = tk.StringVar(value="copy")
        self.conflict_display = tk.StringVar(value="自动改名")
        self.conflict = tk.StringVar(value="rename")
        self.verify_hash = tk.BooleanVar(value=False)
        self.include_sub = tk.BooleanVar(value=True)
        self.filter_text = tk.StringVar()
        self.filter_mode = tk.StringVar(value="排除")
        self.target_entry = tk.StringVar()
        self.file_stat = tk.StringVar()
        self.target_stat = tk.StringVar()
        self.progress_text = tk.StringVar(value="准备就绪")

        self._setup_style()
        self.build_ui()
        self.load_favorites()
        self.filter_text.trace_add("write", lambda *a: self.refresh_files())
        self.filter_mode.trace_add("write", lambda *a: self.refresh_files())
        self.setup_dnd()
        self.refresh_files()
        self.refresh_targets()
        self.root.after(100, self.poll_queue)

    def _setup_style(self):
        st = ttk.Style()
        try:
            st.theme_use("clam")
        except tk.TclError:
            pass
        st.configure("TCombobox", fieldbackground=CARD, background=CARD,
                     foreground=INK, arrowcolor=ORANGE, bordercolor=BORDER,
                     lightcolor=CARD, darkcolor=CARD, padding=5)
        st.map("TCombobox",
               fieldbackground=[("readonly", "#FFFBF4")],
               background=[("readonly", "#FFFBF4")],
               foreground=[("readonly", INK)])
        st.configure("TScrollbar", background="#EFDCC6", troughcolor=CARD,
                     bordercolor=CARD, arrowcolor=MUTED)
        st.configure("Mint.Horizontal.TProgressbar", troughcolor="#F7EAD8",
                     background=YELLOW, bordercolor=CARD, lightcolor=YELLOW,
                     darkcolor=YELLOW, thickness=12)

    # ------------------------------------------------------------ 构建界面
    def build_ui(self):
        Header(self.root).pack(fill="x")
        main = tk.Frame(self.root, bg=BG)
        main.pack(fill="both", expand=True, padx=18, pady=8)

        # ① 文件区
        c1 = Card(main, "① 选择文件", YELLOW, badge="文件夹会连同目录结构一起搬运")
        c1.pack(fill="x", pady=(0, 7))
        b = c1.body
        bar = tk.Frame(b, bg=CARD)
        bar.pack(fill="x", pady=(0, 6))
        Pill(bar, "+ 添加文件", self.add_files, YELLOW, w=112, hover=YELLOW_DK).pack(side="left", padx=(0, BTN_GAP))
        Pill(bar, "+ 多个文件夹", self.add_folders, ORANGE, w=124, hover="#EC5A2D").pack(side="left", padx=BTN_GAP)
        Pill(bar, "★ 星标管理", self.open_star_manager, PINK, w=112,
             hover="#DA3070").pack(side="left", padx=BTN_GAP)
        Pill(bar, "移除选中", self.remove_selected, "#F7EBDD", fg=INK, w=96, hover="#EFDFCC").pack(side="left", padx=BTN_GAP)
        Pill(bar, "清空", self.clear_files, "#F7EBDD", fg=INK, w=66, hover="#EFDFCC").pack(side="left", padx=BTN_GAP)

        self.drop_hint = tk.Label(b, text="", bg=SOFT_YELLOW, fg="#9A5A12",
                                  font=(FONT, 10), pady=5)
        self.drop_hint.pack(fill="x", pady=(0, 6))
        self.set_drop_hint(False)

        lf, self.file_list = make_listbox(b, 4)
        lf.pack(fill="both", expand=True)
        self.file_stat_label = small_label(b, var=self.file_stat)
        self.file_stat_label.pack(anchor="w", pady=(6, 4))

        filt = tk.Frame(b, bg=CARD)
        filt.pack(fill="x")
        tk.Label(filt, text="扩展名", bg=CARD, fg=INK, font=(FONT, 10)).pack(side="left")
        e = make_entry(filt, self.filter_text)
        e.pack(side="left", fill="x", expand=True, padx=8, ipady=4)
        fm = ttk.Combobox(filt, state="readonly", width=8,
                          values=("排除", "仅包含"), textvariable=self.filter_mode)
        fm.current(0)
        fm.pack(side="left", padx=(0, 8))
        for label, exts in (("图片", ".jpg .jpeg .png .gif .webp .bmp"),
                            ("文档", ".pdf .doc .docx .xls .xlsx .ppt .pptx .txt .md"),
                            ("视频", ".mp4 .mkv .mov .avi"),
                            ("全部", "")):
            Pill(filt, label, lambda x=exts: self.preset(x), "#F7EBDD", fg=INK,
                 w=52, h=28, hover="#EFDFCC").pack(side="left", padx=BTN_GAP)

        # ② 目标区
        c2 = Card(main, "② 目标文件夹（可多个）", ORANGE, badge="每个文件会复制到全部目标")
        c2.pack(fill="x", pady=(0, 7))
        b2 = c2.body
        bar2 = tk.Frame(b2, bg=CARD)
        bar2.pack(fill="x", pady=(0, 6))
        Pill(bar2, "+ 添加目标", self.add_target, ORANGE, w=112, hover="#EC5A2D").pack(side="left", padx=(0, BTN_GAP))
        Pill(bar2, "+ 批量多个", self.add_targets_batch, PINK, w=112, hover="#DA3070").pack(side="left", padx=BTN_GAP)
        Pill(bar2, "移除选中", self.remove_target, "#F7EBDD", fg=INK, w=96, hover="#EFDFCC").pack(side="left", padx=BTN_GAP)
        Pill(bar2, "清空", self.clear_targets, "#F7EBDD", fg=INK, w=66, hover="#EFDFCC").pack(side="left", padx=BTN_GAP)
        lf2, self.target_list = make_listbox(b2, 2, ORANGE)
        lf2.pack(fill="both", expand=True)

        fav = tk.Frame(b2, bg=CARD)
        fav.pack(fill="x", pady=(8, 0))
        make_entry(fav, self.target_entry).pack(side="left", fill="x", expand=True, padx=(0, 8), ipady=4)
        self.fav_combo = ttk.Combobox(fav, state="readonly", width=20, values=())
        self.fav_combo.set("常用目标")
        self.fav_combo.bind("<<ComboboxSelected>>", self.on_fav_selected)
        self.fav_combo.pack(side="left", padx=(0, BTN_GAP))
        Pill(fav, "存为常用", self.save_favorite, "#F7EBDD", fg=INK, w=82, h=28,
             hover="#EFDFCC").pack(side="left", padx=BTN_GAP)
        Pill(fav, "打开", self.open_target, "#F7EBDD", fg=INK, w=56, h=28,
             hover="#EFDFCC").pack(side="left", padx=BTN_GAP)
        self.target_stat_label = small_label(b2, var=self.target_stat)
        self.target_stat_label.pack(anchor="w", pady=(6, 0))

        # ③ 动作区
        c3 = Card(main, "③ 动作与选项", PINK, badge="执行前会二次确认")
        c3.pack(fill="x", pady=(0, 7))
        b3 = c3.body
        row1 = tk.Frame(b3, bg=CARD)
        row1.pack(fill="x")
        tk.Radiobutton(row1, text="复制（源文件保留）", variable=self.mode, value="copy",
                       bg=CARD, fg=INK, selectcolor=SOFT_YELLOW, activebackground=CARD,
                       highlightthickness=0, font=(FONT, 10)).pack(side="left", padx=(0, 14))
        tk.Radiobutton(row1, text="移动（文件夹整体送回收站）", variable=self.mode, value="move",
                       bg=CARD, fg=INK, selectcolor=SOFT_YELLOW, activebackground=CARD,
                       highlightthickness=0, font=(FONT, 10)).pack(side="left", padx=(0, 14))
        tk.Label(row1, text="同名：", bg=CARD, fg=INK, font=(FONT, 10)).pack(side="left")
        cb = ttk.Combobox(row1, state="readonly", width=10,
                          values=("自动改名", "覆盖", "跳过"),
                          textvariable=self.conflict_display)
        cb.current(0)
        cb.bind("<<ComboboxSelected>>", self.on_conflict)
        cb.pack(side="left", padx=(0, 14))
        tk.Checkbutton(row1, text="SHA-256 严格校验", variable=self.verify_hash,
                       bg=CARD, fg=INK, selectcolor=SOFT_YELLOW, activebackground=CARD,
                       highlightthickness=0, font=(FONT, 10)).pack(side="left")
        tk.Checkbutton(row1, text="拖入文件夹含子目录", variable=self.include_sub,
                       bg=CARD, fg=INK, selectcolor=SOFT_YELLOW, activebackground=CARD,
                       highlightthickness=0, font=(FONT, 10)).pack(side="left", padx=(10, 0))

        row2 = tk.Frame(b3, bg=CARD)
        row2.pack(fill="x", pady=(12, 0))
        self.run_btn = Pill(row2, "开始搬运", self.start, YELLOW, w=150, h=40,
                            hover=YELLOW_DK, big=True)
        self.run_btn.pack(side="left", padx=(0, 14))
        self.progress = ttk.Progressbar(row2, style="Mint.Horizontal.TProgressbar",
                                        orient="horizontal", mode="determinate", length=360)
        self.progress.pack(side="left", padx=(0, 12))
        tk.Label(row2, textvariable=self.progress_text, bg=CARD, fg=MUTED,
                 font=(FONT, 9)).pack(side="left")

        # ④ 日志区
        c4 = Card(main, "运行日志", VIOLET, badge="结果同时写入 搬运日志.txt")
        c4.pack(fill="both", expand=True)
        b4 = c4.body
        self.logbox = tk.Text(b4, height=3, wrap="word", state="disabled",
                              bg="#FFFCF7", fg=INK, relief="flat", bd=0,
                              highlightthickness=1, highlightbackground=BORDER,
                              font=(FONT, 9))
        ls = ttk.Scrollbar(b4, orient="vertical", command=self.logbox.yview)
        self.logbox.configure(yscrollcommand=ls.set)
        self.logbox.pack(side="left", fill="both", expand=True)
        ls.pack(side="right", fill="y")
        Pill(b4, "清空", self.clear_log, "#F7EBDD", fg=INK, w=62, h=26,
             hover="#EFDFCC").pack(side="bottom", anchor="e", pady=(6, 0))

        foot = tk.Frame(self.root, bg=BG)
        foot.pack(fill="x", padx=20, pady=(0, 7))
        tk.Label(foot, text="© 微尘  ·  纯本地运行，不联网、不上传任何文件",
                 bg=BG, fg=NEUTRAL_TX, font=(FONT, 9)).pack(side="left")
        Pill(foot, "关于", self.show_about, "#F7EBDD", fg=INK, w=64, h=26,
             hover="#EFDFCC", bg=BG).pack(side="right")

    # ------------------------------------------------------------ 拖拽
    def setup_dnd(self):
        if not DND_OK:
            self.drop_hint.configure(
                text="当前环境未加载拖拽组件，请用上方「添加文件 / 多个文件夹」按钮",
                bg="#F7EBDD", fg=MUTED)
            return
        self.root.drop_target_register(DND_FILES)
        self.root.dnd_bind("<<Drop>>", self.on_drop)
        self.root.dnd_bind("<<DragEnter>>", lambda e: self.set_drop_hint(True))
        self.root.dnd_bind("<<DragLeave>>", lambda e: self.set_drop_hint(False))

    def set_drop_hint(self, active):
        if not DND_OK:
            return
        if active:
            self.drop_hint.configure(text="松开鼠标，即可添加文件 / 文件夹", bg=YELLOW, fg=INK)
        else:
            self.drop_hint.configure(
                text="↧  把文件或文件夹拖到窗口任意位置即可添加", bg=SOFT_YELLOW, fg="#9A5A12")

    def on_drop(self, event):
        self.set_drop_hint(False)
        try:
            paths = self.root.tk.splitlist(event.data)
        except Exception:
            paths = [event.data]
        added, folders = 0, 0
        recursive = self.include_sub.get()
        for raw in paths:
            p = os.path.normpath(str(raw))
            if os.path.isfile(p):
                if p not in self.files:
                    self.files.append(p)
                    added += 1
            elif os.path.isdir(p):
                folders += 1
                added += self.register_folders([p], recursive)
        self.refresh_files()
        self.write_log("拖入 {} 个文件夹，新增 {} 个文件{}（保留目录层级）".format(
            folders, added, "（含子文件夹）" if recursive else "（仅顶层）"))

    # ------------------------------------------------------------ 文件列表
    def display_files(self):
        exts = parse_exts(self.filter_text.get())
        mode = "include" if self.filter_mode.get() == "仅包含" else "exclude"
        return [p for p in self.files if passes_filter(p, exts, mode)]

    def display_label(self, p):
        """文件夹里的文件显示成 '项目A/子目录/a.txt'，一眼看出层级会被保留。"""
        root = self.file_roots.get(p)
        if root:
            top = os.path.basename(os.path.normpath(root)) or root
            return os.path.normpath(os.path.join(top, os.path.relpath(p, root)))
        return p

    def refresh_files(self):
        shown = self.display_files()
        self.file_list.delete(0, "end")
        for p in shown:
            self.file_list.insert("end", self.display_label(p))
        total = 0
        for p in shown:
            try:
                total += os.path.getsize(p)
            except OSError:
                pass
        exts = parse_exts(self.filter_text.get())
        note = ""
        if exts:
            note = "  ·  {} {}".format(self.filter_mode.get(), " ".join(sorted(exts)))
        struct_note = "  ·  文件夹按原层级落到目标" if any(
            p in self.file_roots for p in shown) else ""
        self.file_stat.set("已选 {} 个文件，当前显示 {} 个（{}）{}{}".format(
            len(self.files), len(shown), human_size(total), note, struct_note))

    def add_files(self):
        paths = pick_browse(self.root, "选择一个或多个文件", None, "files", False)
        if not paths:
            return
        for p in paths:
            if p not in self.files:
                self.files.append(p)
        self.refresh_files()

    # ------------------------------------------------------------ 星标管理
    def open_star_manager(self):
        initial = None
        for p in reversed(self.files):
            r = self.file_roots.get(p)
            if r and os.path.isdir(r):
                initial = r
                break
        folder = pick_browse(self.root, "选择要星标管理的文件夹",
                             initial or os.path.expanduser("~"), "folder", True)
        if not folder:
            return
        StarManagerDialog(self.root, folder,
                          on_apply=self.apply_star_selection, log=self.write_log)

    def apply_star_selection(self, folder, items):
        """把星标筛选结果送回搬运列表：保留父文件夹层级，并禁止整体清理源文件夹。"""
        added = 0
        for it in items:
            p = it["path"]
            if it["is_dir"]:
                if os.path.isdir(p):
                    added += self.register_folders([p], True)
            elif os.path.isfile(p) and p not in self.files:
                self.files.append(p)
                self.file_roots[p] = folder
                added += 1
        top = os.path.basename(os.path.normpath(folder)) or folder
        self.empty_dirs.add(top)
        # 筛选结果只是源文件夹的一部分：把「应有文件数」设成极大值，
        # 移动模式就一定退回逐文件安全清理，绝不整体删除源文件夹。
        self.folder_totals[folder] = max(self.folder_totals.get(folder, 0), 1 << 30)
        self.refresh_files()
        self.write_log("星标筛选送回搬运：{} 个项目，新增 {} 个文件（保留「{}」层级）".format(
            len(items), added, top))
        try:
            self.root.lift()
            self.root.focus_force()
        except Exception:
            pass

    def register_folders(self, folders, recursive):
        """登记文件夹：文件 + 层级归属 + 目录骨架（含空文件夹）。"""
        files, roots, dirs = collect_from_folders(
            folders, recursive, with_layout=True)
        added = 0
        for fp in files:
            if fp not in self.files:
                self.files.append(fp)
                self.file_roots[fp] = roots[fp]
                added += 1
        counts = {}
        for root in roots.values():
            counts[root] = counts.get(root, 0) + 1
        for root, n in counts.items():
            self.folder_totals[root] = max(self.folder_totals.get(root, 0), n)
        self.empty_dirs.update(dirs)
        return added

    def add_folders(self):
        r = pick_folders(self.root, "批量添加源文件夹", True, self.include_sub.get())
        if not r:
            return
        folders, recursive = r
        added = self.register_folders(folders, recursive)
        self.refresh_files()
        self.write_log("从 {} 个文件夹导入 {} 个文件{}（保留目录层级）".format(
            len(folders), added, "（含子文件夹）" if recursive else "（仅顶层）"))

    def remove_selected(self):
        shown = self.display_files()
        gone = {shown[i] for i in self.file_list.curselection() if i < len(shown)}
        if gone:
            self.files = [p for p in self.files if p not in gone]
            for p in gone:
                self.file_roots.pop(p, None)
        self.refresh_files()

    def clear_files(self):
        self.files.clear()
        self.file_roots.clear()
        self.folder_totals.clear()
        self.empty_dirs.clear()
        self.refresh_files()

    def preset(self, exts):
        self.filter_text.set(exts)
        self.filter_mode.set("仅包含" if exts else "排除")
        self.refresh_files()

    # ------------------------------------------------------------ 目标列表
    def refresh_targets(self):
        self.target_list.delete(0, "end")
        for p in self.targets:
            self.target_list.insert("end", p)
        self.target_stat.set("已添加 {} 个目标文件夹  ·  每个文件将复制 {} 份".format(
            len(self.targets), len(self.targets)))

    def add_target(self):
        d = pick_browse(self.root, "选择目标文件夹", None, "folder", True)
        if d:
            d = os.path.normpath(d)
            if d not in self.targets:
                self.targets.append(d)
                self.refresh_targets()

    def add_targets_batch(self):
        r = pick_folders(self.root, "批量添加目标文件夹")
        if not r:
            return
        folders, _ = r
        for d in folders:
            if d not in self.targets:
                self.targets.append(d)
        self.refresh_targets()

    def remove_target(self):
        for i in reversed(self.target_list.curselection()):
            del self.targets[i]
        self.refresh_targets()

    def clear_targets(self):
        self.targets.clear()
        self.refresh_targets()

    def load_favorites(self):
        try:
            with open(FAV_FILE, "r", encoding="utf-8") as f:
                self.favorites = json.load(f)
            if not isinstance(self.favorites, list):
                self.favorites = []
        except (OSError, ValueError):
            self.favorites = []
        self.fav_combo["values"] = self.favorites

    def save_favorite(self):
        d = self.target_entry.get().strip().strip('"')
        if not d:
            messagebox.showinfo("提示", "请先在左侧输入框填写一个目标文件夹路径。", parent=self.root)
            return
        if d not in self.favorites:
            self.favorites.append(d)
            with open(FAV_FILE, "w", encoding="utf-8") as f:
                json.dump(self.favorites, f, ensure_ascii=False, indent=2)
            self.fav_combo["values"] = self.favorites
            self.write_log("已存为常用目标：{}".format(d))
        else:
            messagebox.showinfo("提示", "这个目录已经在常用列表里了。", parent=self.root)

    def on_fav_selected(self, _event=None):
        d = self.fav_combo.get()
        if d:
            self.target_entry.set(d)

    def open_target(self):
        sel = self.target_list.curselection()
        d = self.targets[sel[0]] if sel else self.target_entry.get().strip()
        if d and os.path.isdir(d):
            os.startfile(d)
        else:
            messagebox.showwarning("提示", "请先选中一个有效目标文件夹。", parent=self.root)

    def on_conflict(self, _event=None):
        self.conflict.set({"自动改名": "rename", "覆盖": "overwrite",
                           "跳过": "skip"}.get(self.conflict_display.get(), "rename"))

    # ------------------------------------------------------------ 日志/进度
    def write_log(self, text):
        self.logbox.configure(state="normal")
        self.logbox.insert("end", "[{}] {}\n".format(datetime.now().strftime("%H:%M:%S"), text))
        self.logbox.see("end")
        self.logbox.configure(state="disabled")

    def clear_log(self):
        self.logbox.configure(state="normal")
        self.logbox.delete("1.0", "end")
        self.logbox.configure(state="disabled")

    def poll_queue(self):
        try:
            while True:
                kind, payload = self.queue.get_nowait()
                if kind == "log":
                    self.write_log(payload)
                elif kind == "progress":
                    cur, total = payload
                    self.progress["maximum"] = max(total, 1)
                    self.progress["value"] = cur
                    self.progress_text.set("进度 {}/{}".format(cur, total))
                elif kind == "done":
                    self.on_done(payload)
        except queue.Empty:
            pass
        self.root.after(100, self.poll_queue)

    def show_about(self):
        messagebox.showinfo(
            "关于",
            "文件搬运工具  v2.3\n\n"
            "作者：微尘\n\n"
            "功能：多选文件、拖拽添加、批量源文件夹、多目标文件夹、\n"
            "完整保留文件夹层级（含子目录与空文件夹）、扩展名过滤、\n"
            "星标管理（1~10 星 / 筛选 / 重命名 / 清除 / 送回搬运）、\n"
            "复制 / 移动、同名策略、SHA-256 校验。\n\n"
            "v2.3 视觉：多巴胺暖色配色 + 按钮 / 卡片全抗锯齿圆角。\n"
            "v2.2 起：文件夹选择改用纯 Tk 自绘浏览器，\n"
            "在对话框内新建文件夹不会再引起界面缩放突变。\n\n"
            "安全：默认不删源文件；移动时文件夹在所有目标全部成功后\n"
            "整体送入回收站（可还原），不留空壳；失败则源文件保留。\n\n"
            "技术：Python + tkinter 标准库，纯本地运行，\n"
            "不联网、不上传任何文件。\n\n"
            "拖拽组件：{}".format("已启用 (tkinterdnd2)" if DND_OK else "未加载"),
            parent=self.root)

    # ------------------------------------------------------------ 执行
    def start(self):
        if self.running:
            return
        files = self.display_files()
        targets = list(self.targets)
        if not files:
            messagebox.showwarning("提示", "请先添加文件，或调整扩展名过滤条件。", parent=self.root)
            return
        if not targets:
            messagebox.showwarning("提示", "请至少添加一个目标文件夹。", parent=self.root)
            return

        missing = [d for d in targets if not os.path.isdir(d)]
        if missing:
            if not messagebox.askyesno(
                    "目录不存在",
                    "以下 {} 个目标文件夹不存在：\n{}\n\n要现在创建吗？".format(
                        len(missing), "\n".join(missing[:5])), parent=self.root):
                return
            try:
                for d in missing:
                    os.makedirs(d, exist_ok=True)
            except OSError as exc:
                messagebox.showerror("错误", "创建目录失败：{}".format(exc), parent=self.root)
                return

        mode, conflict = self.mode.get(), self.conflict.get()
        exts = parse_exts(self.filter_text.get())
        msg = ("待搬运文件：{} 个\n目标文件夹：{} 个\n共 {} 次复制\n"
               "动作：{}\n同名处理：{}\n校验：{}\n扩展名：{}\n"
               "文件夹：保留完整目录层级（目标 / 文件夹名 / 子目录 / ...）").format(
            len(files), len(targets), len(files) * len(targets),
            "复制（源文件保留）" if mode == "copy" else "移动",
            self.conflict_display.get(),
            "SHA-256 严格校验" if self.verify_hash.get() else "按文件大小",
            ("{} {}".format(self.filter_mode.get(), " ".join(sorted(exts)))) if exts else "不过滤")
        if mode == "move":
            msg += "\n\n注意：移动模式下，文件夹在全部目标都成功后会整体送入回收站（可还原），不留空壳；任一步失败则源文件保留。"
        if conflict == "overwrite":
            msg += "\n\n注意：你选择了「覆盖」，目标里的同名文件会被直接替换。"
        if not messagebox.askyesno("确认执行", msg + "\n\n确定开始吗？", parent=self.root):
            return

        self.running = True
        self.run_btn.set_enabled(False)
        self.progress["value"] = 0
        self.write_log("开始：{} 个文件 × {} 个目标 = {} 次复制".format(
            len(files), len(targets), len(files) * len(targets)))

        layout = build_layout(files, self.file_roots)
        roots_arg = {p: self.file_roots.get(p) for p in files}
        active_tops = {os.path.basename(os.path.normpath(r))
                       for r in roots_arg.values() if r}
        ensure = sorted(d for d in self.empty_dirs
                        if d.split(os.sep)[0] in active_tops)
        totals = dict(self.folder_totals)

        t = threading.Thread(
            target=self.worker,
            args=(files, targets, mode, conflict, self.verify_hash.get(),
                  layout, ensure, roots_arg, totals),
            daemon=True)
        t.start()

    def worker(self, files, targets, mode, conflict, verify,
               layout, ensure_dirs, folder_roots, folder_totals):
        def cb_progress(cur, total):
            self.queue.put(("progress", (cur, total)))

        def cb_log(text):
            self.queue.put(("log", text))

        try:
            res = transfer_multi(files, targets, mode=mode, conflict=conflict,
                                 verify_hash=verify, progress=cb_progress, log=cb_log,
                                 layout=layout, ensure_dirs=ensure_dirs,
                                 folder_roots=folder_roots,
                                 folder_totals=folder_totals)
        except Exception:
            self.queue.put(("log", "严重错误：\n" + traceback.format_exc()))
            res = {"ok": [], "skipped": [], "failed": []}
        self.queue.put(("done", res))

    def on_done(self, res):
        self.running = False
        self.run_btn.set_enabled(True)
        ok, skipped, failed = res["ok"], res["skipped"], res["failed"]
        summary = "完成：成功 {} 次，跳过 {} 次，失败 {} 次".format(len(ok), len(skipped), len(failed))
        self.write_log(summary)
        self.progress_text.set(summary)
        try:
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write("\n=== {} ===\n{}\n".format(datetime.now().strftime("%Y-%m-%d %H:%M:%S"), summary))
                for src, dst, note in ok:
                    f.write("[成功] {} -> {} | {}\n".format(src, dst, note))
                for src, dst, note in skipped:
                    f.write("[跳过] {} -> {} | {}\n".format(src, dst, note))
                for src, dst, note in failed:
                    f.write("[失败] {} -> {} | {}\n".format(src, dst, note))
        except OSError:
            pass
        if failed:
            messagebox.showwarning("有文件未成功", "{}\n\n详情见下方日志。源文件均未受影响。".format(summary),
                                   parent=self.root)
        else:
            messagebox.showinfo("完成", summary, parent=self.root)


def main():
    # 不启用 DPI 感知声明：150% 缩放下会造成界面缩水 / 卡片被裁（见函数说明）。
    # 「在目录对话框内新建文件夹时界面缩放突变」已由纯 Tk 自绘浏览器从根源解决。
    root = TkinterDnD.Tk() if DND_OK else tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        with open(ERR_FILE, "a", encoding="utf-8") as f:
            f.write(datetime.now().isoformat() + "\n" + traceback.format_exc() + "\n")
        raise
