# -*- coding: utf-8 -*-
"""README 素材渲染器（DSH dsh-github-readme 插件后端）。

用法:
  python render_readme_assets.py --plan-file plan.json
  python render_readme_assets.py --gallery out/style-gallery.png   # 生成 10 风格总览图
  python render_readme_assets.py --list-styles                     # 打印风格/配色清单

plan.json:
{
  "outDir": "输出目录（必填）",
  "style": "split | band | topbar | diagonal | center | terminal | editorial | cards | wave | minimal | random",
  "palette": "ocean | emerald | violet | amber | rose | cyan | indigo | slate | lime | sunset",
  "seed": 123456,                     // 可选：固定随机组合，便于复现
  "theme": "blue|green|violet|orange", // 旧字段兼容，等价于 palette 别名
  "banner": { ... },                  // 可选，有就画 banner
  "flow": { ... }                     // 可选，有就画 flow（配色跟随 palette/theme）
}

banner 字段（可省略）:
  icon         play | check | doc | branch | bolt | puzzle
  eyebrow / title / mono / headline / bullets / chips / note
  leftTop / leftCard / leftCaption（仅 split / band 风格使用）
  footerLeft / footerRight

flow 字段:
  title / subtitle / badge / steps[{title,tag,desc}] / productsTitle
  products[{name,detail,color}] / highlight{title,text} / footerLeft / footerRight

末尾输出一行 RESULT_JSON（含 bannerStyle / bannerPalette / seed）。
"""
import argparse
import json
import os
import random
import sys

from PIL import Image, ImageDraw, ImageFont

FD = r"C:\Windows\Fonts"
REG = os.path.join(FD, "msyh.ttc")
BOLD = os.path.join(FD, "msyhbd.ttc")
MONO = os.path.join(FD, "consola.ttf") if os.path.exists(os.path.join(FD, "consola.ttf")) else REG
MONOB = os.path.join(FD, "consolab.ttf") if os.path.exists(os.path.join(FD, "consolab.ttf")) else BOLD

BG = (247, 248, 251)
WHITE = (255, 255, 255)
TEXT = (31, 36, 48)
GRAY = (92, 100, 114)
GRAY2 = (120, 128, 140)
GREEN = (31, 122, 77)
RED = (163, 62, 40)
LINE = (226, 232, 244)

S = 2  # 超采样倍数

# ------------------------------- 配色 -------------------------------
PALETTES = {
    "ocean": {"accent": (47, 107, 255), "dark": (30, 64, 175), "bg": (234, 241, 255),
              "line": (201, 217, 255), "g1": (236, 243, 255), "g2": (156, 190, 255)},
    "emerald": {"accent": (31, 122, 77), "dark": (22, 78, 52), "bg": (241, 250, 244),
                "line": (159, 203, 176), "g1": (240, 248, 242), "g2": (146, 202, 172)},
    "violet": {"accent": (109, 76, 196), "dark": (76, 45, 140), "bg": (245, 242, 255),
               "line": (196, 184, 235), "g1": (246, 243, 255), "g2": (186, 170, 235)},
    "amber": {"accent": (232, 137, 12), "dark": (160, 84, 8), "bg": (255, 249, 242),
              "line": (240, 178, 92), "g1": (255, 250, 243), "g2": (245, 200, 150)},
    "rose": {"accent": (219, 64, 109), "dark": (150, 40, 72), "bg": (255, 240, 245),
             "line": (244, 196, 214), "g1": (255, 245, 249), "g2": (240, 160, 190)},
    "cyan": {"accent": (14, 140, 164), "dark": (10, 92, 108), "bg": (232, 248, 251),
             "line": (178, 224, 233), "g1": (236, 250, 252), "g2": (150, 215, 228)},
    "indigo": {"accent": (67, 56, 202), "dark": (44, 35, 150), "bg": (238, 237, 255),
               "line": (199, 197, 247), "g1": (241, 240, 255), "g2": (160, 155, 240)},
    "slate": {"accent": (71, 85, 105), "dark": (40, 52, 70), "bg": (241, 245, 249),
              "line": (203, 213, 225), "g1": (246, 249, 252), "g2": (170, 185, 205)},
    "lime": {"accent": (77, 124, 15), "dark": (52, 84, 10), "bg": (244, 251, 231),
             "line": (205, 228, 158), "g1": (247, 253, 238), "g2": (180, 215, 120)},
    "sunset": {"accent": (220, 80, 40), "dark": (150, 50, 20), "bg": (255, 243, 236),
               "line": (246, 199, 175), "g1": (255, 247, 241), "g2": (245, 170, 130)},
}

THEME_ALIAS = {"blue": "ocean", "green": "emerald", "violet": "violet",
               "orange": "amber", "purple": "violet"}
# 旧配色名（banner chips / flow products 里常用）→ 新 palette 名
COLOR_ALIAS = {"blue": "ocean", "green": "emerald", "orange": "amber",
               "violet": "violet", "purple": "violet", "red": "rose",
               "cyan": "cyan", "amber": "amber", "rose": "rose"}

# 10 种首图风格：每种风格自带一组可用配色，随机时从中抽
STYLES = [
    {"id": "split", "name": "经典分栏", "palettes": ["ocean", "emerald", "violet", "amber", "rose", "indigo"],
     "desc": "左渐变栏 + 斜切白带，图标/小卡在左，标题与卖点在右"},
    {"id": "band", "name": "左侧色带", "palettes": ["emerald", "ocean", "cyan", "slate", "lime"],
     "desc": "左侧纯色渐变色带，右侧白底放标题与卖点"},
    {"id": "topbar", "name": "顶部横幅", "palettes": ["violet", "indigo", "rose", "ocean", "sunset"],
     "desc": "顶部渐变色条承载标题，下方三张卖点卡片"},
    {"id": "diagonal", "name": "对角色块", "palettes": ["ocean", "emerald", "amber", "sunset", "cyan"],
     "desc": "右下大三角色块压阵，标题居左上，标签落在色块里"},
    {"id": "center", "name": "居中构图", "palettes": ["violet", "ocean", "emerald", "rose", "indigo", "slate"],
     "desc": "图标、标题、卖点全部居中，适合品牌型项目"},
    {"id": "terminal", "name": "终端窗口", "palettes": ["cyan", "lime", "amber", "rose", "violet"],
     "desc": "深色终端窗口 + 命令行式卖点，开发者工具首选"},
    {"id": "editorial", "name": "杂志编辑", "palettes": ["slate", "amber", "ocean", "rose", "emerald"],
     "desc": "大标题 + 右侧带编号的横线条目，克制留白"},
    {"id": "cards", "name": "卡片网格", "palettes": ["ocean", "violet", "emerald", "amber", "cyan"],
     "desc": "四张卡片拼成首图：图标、标题、卖点、标签各占一格"},
    {"id": "wave", "name": "波浪渐变", "palettes": ["ocean", "cyan", "violet", "emerald", "sunset"],
     "desc": "整屏渐变 + 底部白色波浪，标题在上、卖点落在波浪里"},
    {"id": "minimal", "name": "极简留白", "palettes": ["slate", "ocean", "emerald", "amber", "violet", "rose"],
     "desc": "白底大面积留白 + 一条强调竖线，标题最大"},
]
STYLE_IDS = [s["id"] for s in STYLES]
STYLE_MAP = {s["id"]: s for s in STYLES}


def fnt(path, size):
    return ImageFont.truetype(path, int(round(size * S)))


def wrap(text, f, max_w):
    text = str(text)
    if "\n" in text:
        out = []
        for seg in text.split("\n"):
            out.extend(wrap(seg, f, max_w))
        return out
    toks, i = [], 0
    punct = " ，。、；：（）《》「」！？—"
    while i < len(text):
        ch = text[i]
        if ord(ch) < 128 and ch not in punct:
            j = i
            while j < len(text) and ord(text[j]) < 128 and text[j] not in punct:
                j += 1
            toks.append(text[i:j])
            i = j
        else:
            toks.append(ch)
            i += 1
    lines, cur = [], ""
    for t in toks:
        if f.getlength(cur + t) <= max_w * S or not cur:
            cur += t
        else:
            lines.append(cur)
            cur = t
    if cur:
        lines.append(cur)
    tail = "，。、；：！？）》」』"
    for k in range(1, len(lines)):
        while lines[k] and lines[k][0] in tail:
            lines[k - 1] += lines[k][0]
            lines[k] = lines[k][1:]
    return [x for x in lines if x]


class C:
    def __init__(self, w, h, bg=BG):
        self.w, self.h = w, h
        self.img = Image.new("RGB", (w * S, h * S), bg)
        self.d = ImageDraw.Draw(self.img)

    def rect(self, x1, y1, x2, y2, fill=None, outline=None, width=1):
        self.d.rectangle([x1 * S, y1 * S, (x2 - 1) * S, (y2 - 1) * S],
                         fill=fill, outline=outline, width=int(width * S))

    def rrect(self, x1, y1, x2, y2, r=12, fill=None, outline=None, width=1):
        self.d.rounded_rectangle([x1 * S, y1 * S, x2 * S, y2 * S], radius=r * S,
                                 fill=fill, outline=outline, width=int(round(width * S)))

    def text(self, x, y, t, size=20, bold=False, color=TEXT, anchor="la", mono=False):
        path = (MONOB if bold else MONO) if mono else (BOLD if bold else REG)
        self.d.text((x * S, y * S), str(t), font=fnt(path, size), fill=color, anchor=anchor)

    def para(self, x, y, max_w, t, size=18, bold=False, color=TEXT, lh=28, max_lines=9):
        f = fnt(BOLD if bold else REG, size)
        lines = wrap(t, f, max_w)
        for k, ln in enumerate(lines[:max_lines]):
            self.d.text((x * S, (y + k * lh) * S), ln, font=f, fill=color)
        return y + min(len(lines), max_lines) * lh

    def text_w(self, t, size=20, bold=True, mono=False):
        path = (MONOB if bold else MONO) if mono else (BOLD if bold else REG)
        return fnt(path, size).getlength(str(t)) / S

    def fit(self, t, size, max_w, bold=True, min_size=18, mono=False):
        while size > min_size and self.text_w(t, size, bold=bold, mono=mono) > max_w:
            size -= 2
        return size

    def circle(self, cx, cy, r, fill, outline=None, width=1):
        self.d.ellipse([(cx - r) * S, (cy - r) * S, (cx + r) * S, (cy + r) * S],
                       fill=fill, outline=outline, width=int(round(width * S)))

    def line(self, x1, y1, x2, y2, fill=GRAY, width=2):
        self.d.line([x1 * S, y1 * S, x2 * S, y2 * S], fill=fill, width=int(round(width * S)))

    def poly(self, points, fill):
        self.d.polygon([(x * S, y * S) for x, y in points], fill=fill)

    def arrow_down(self, cx, y1, y2, color=GRAY, width=4, head=9):
        self.line(cx, y1, cx, y2 - head, fill=color, width=width)
        self.d.polygon([(cx * S, y2 * S), ((cx - head * 0.8) * S, (y2 - head * 1.4) * S),
                        ((cx + head * 0.8) * S, (y2 - head * 1.4) * S)], fill=color)

    def pill_w(self, t, size=16, pad_x=14):
        return fnt(BOLD, size).getlength(str(t)) / S + pad_x * 2

    def pill(self, x, y, t, size=16, pad_x=14, h=32, fill=None, color=None,
             outline=None, bold=True):
        f = fnt(BOLD if bold else REG, size)
        w = f.getlength(str(t)) / S + pad_x * 2
        self.rrect(x, y, x + w, y + h, r=h / 2, fill=fill, outline=outline)
        self.d.text(((x + pad_x) * S, (y + h / 2) * S), str(t), font=f, fill=color, anchor="lm")
        return w

    def gradient(self, x1, y1, x2, y2, c1, c2, horizontal=False):
        import numpy as np
        w, h = x2 - x1, y2 - y1
        if w <= 0 or h <= 0:
            return
        if horizontal:
            t = np.linspace(0, 1, w).reshape(1, w, 1).repeat(h, axis=0)
        else:
            t = np.linspace(0, 1, h).reshape(h, 1, 1).repeat(w, axis=1)
        arr = (np.array(c1)[None, None, :] * (1 - t) + np.array(c2)[None, None, :] * t).astype("uint8")
        im = Image.fromarray(arr, "RGB").resize((w * S, h * S), Image.BILINEAR)
        self.img.paste(im, (x1 * S, y1 * S))

    def save(self, path):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self.img.resize((self.w, self.h), Image.LANCZOS).save(path, "PNG", optimize=True)
        return os.path.getsize(path)


# ------------------------------- 通用绘制 -------------------------------
def _icon_base(c, x, y, size, fill, r=None):
    c.rrect(x, y, x + size, y + size, r=r if r is not None else size * 0.26, fill=fill)


def draw_icon(c, glyph, x, y, size, accent, tile=True):
    s = size / 64.0
    glyph = (glyph or "doc").lower()
    if tile:
        _icon_base(c, x, y, size, accent)
    lw = max(2, int(3 * s))
    ink = WHITE
    if glyph == "play":
        c.rrect(x + 17 * s, y + 22 * s, x + 47 * s, y + 44 * s, r=2 * s, outline=ink, width=lw)
        c.line(x + 25 * s, y + 17.5 * s, x + 22 * s, y + 22 * s, fill=ink, width=lw)
        c.line(x + 39 * s, y + 17.5 * s, x + 42 * s, y + 22 * s, fill=ink, width=lw)
        c.circle(x + 26 * s, y + 30 * s, 2.6 * s, ink)
        c.circle(x + 38 * s, y + 30 * s, 2.6 * s, ink)
        c.d.arc([(x + 23 * s) * S, (y + 30 * s) * S, (x + 41 * s) * S, (y + 41 * s) * S],
                start=20, end=160, fill=ink, width=int(round(2.4 * s * S)))
        c.line(x + 20 * s, y + 50 * s, x + 44 * s, y + 50 * s, fill=ink, width=lw)
    elif glyph == "check":
        c.line(x + 16 * s, y + 22 * s, x + 36 * s, y + 22 * s, fill=ink, width=lw)
        c.line(x + 16 * s, y + 32 * s, x + 44 * s, y + 32 * s, fill=ink, width=lw)
        c.line(x + 16 * s, y + 42 * s, x + 30 * s, y + 42 * s, fill=ink, width=lw)
        c.circle(x + 46 * s, y + 42 * s, 9 * s, (143, 211, 168))
        c.d.line([(x + 41.5 * s) * S, (y + 42 * s) * S, (x + 44.5 * s) * S, (y + 45 * s) * S,
                  (x + 50 * s) * S, (y + 38.5 * s) * S], fill=accent,
                 width=int(round(2.6 * s * S)), joint="curve")
    elif glyph == "branch":
        c.circle(x + 24 * s, y + 20 * s, 5 * s, ink)
        c.circle(x + 24 * s, y + 44 * s, 5 * s, ink)
        c.circle(x + 44 * s, y + 30 * s, 5 * s, ink)
        c.line(x + 24 * s, y + 25 * s, x + 24 * s, y + 39 * s, fill=ink, width=lw)
        c.line(x + 29 * s, y + 22 * s, x + 39 * s, y + 28 * s, fill=ink, width=lw)
        c.line(x + 29 * s, y + 42 * s, x + 39 * s, y + 33 * s, fill=ink, width=lw)
    elif glyph == "bolt":
        c.d.polygon([(x + 35 * s) * S, (y + 14 * s) * S, (x + 22 * s) * S, (y + 36 * s) * S,
                     (x + 31 * s) * S, (y + 36 * s) * S, (x + 28 * s) * S, (y + 50 * s) * S,
                     (x + 43 * s) * S, (y + 27 * s) * S, (x + 33 * s) * S, (y + 27 * s) * S], fill=ink)
    elif glyph == "puzzle":
        c.rrect(x + 15 * s, y + 15 * s, x + 30 * s, y + 30 * s, r=3 * s, fill=ink)
        c.rrect(x + 34 * s, y + 15 * s, x + 49 * s, y + 30 * s, r=3 * s, fill=ink)
        c.rrect(x + 15 * s, y + 34 * s, x + 30 * s, y + 49 * s, r=3 * s, fill=ink)
        c.circle(x + 42 * s, y + 42 * s, 7 * s, ink)
    else:  # doc
        c.rrect(x + 18 * s, y + 14 * s, x + 42 * s, y + 48 * s, r=3 * s, outline=ink, width=lw)
        c.line(x + 24 * s, y + 24 * s, x + 36 * s, y + 24 * s, fill=ink, width=lw)
        c.line(x + 24 * s, y + 31 * s, x + 36 * s, y + 31 * s, fill=ink, width=lw)
        c.line(x + 24 * s, y + 38 * s, x + 31 * s, y + 38 * s, fill=ink, width=lw)
        cx, cy, r1, r2 = x + 46 * s, y + 44 * s, 8 * s, 3.2 * s
        pts = []
        import math
        for k in range(8):
            ang = -math.pi / 2 + k * math.pi / 4
            rr = r1 if k % 2 == 0 else r2
            pts.append(((cx + rr * math.cos(ang)) * S, (cy + rr * math.sin(ang)) * S))
        c.d.polygon(pts, fill=ink)


def draw_bullets(c, x, y, width, bullets, pal, on_dark=False, gap=38, size=19, max_n=4):
    col = WHITE if on_dark else TEXT
    dot = pal["accent"] if not on_dark else WHITE
    for i, item in enumerate((bullets or [])[:max_n]):
        txt = item.get("text", "") if isinstance(item, dict) else str(item)
        c.circle(x + 5, y + 9, 5, dot)
        c.text(x + 20, y, txt, size, color=col)
        y += gap
    return y


def draw_chips(c, x, y, chips, pal, on_dark=False, max_w=1136, size=16):
    cx = x
    for ch in (chips or [])[:4]:
        text = ch.get("text", "") if isinstance(ch, dict) else str(ch)
        key = ch.get("color", "") if isinstance(ch, dict) else ""
        p2 = PALETTES.get(COLOR_ALIAS.get(key, key)) or pal
        if on_dark:
            fill, fg = (255, 255, 255), pal["dark"]
        else:
            fill, fg = p2["bg"], p2["dark"]
        w = cx + c.pill_w(text, size) - x
        if x + w > max_w:
            break
        cx += c.pill(cx, y, text, size, fill=fill, color=fg) + 10


def draw_footers(c, b, pal, on_dark=False, h=600):
    col = (203, 213, 225) if on_dark else GRAY2
    if b.get("footerLeft"):
        c.text(44, h - 36, b["footerLeft"], 14.5, color=col)
    if b.get("footerRight"):
        c.text(1156, h - 60, b["footerRight"], 14, color=col, anchor="ra")


# ------------------------------- 10 种首图风格 -------------------------------
def style_split(c, b, pal):
    a, dark = pal["accent"], pal["dark"]
    c.rect(0, 0, 1200, 600, fill=BG)
    c.gradient(0, 0, 470, 600, pal["g1"], pal["g2"])
    c.poly([(408, 0), (474, 0), (428, 600), (362, 600)], WHITE)
    draw_icon(c, b.get("icon") or "doc", 160, 66, 150, a)
    c.text(235, 242, b.get("leftTop") or "一个仓库 / 一个链接", 20, bold=True, color=dark, anchor="ma")
    c.arrow_down(235, 280, 318, color=dark, width=4, head=10)
    card = b.get("leftCard") or {}
    c.rrect(58, 330, 356, 520, r=16, fill=WHITE, outline=pal["line"], width=2)
    c.rrect(58, 330, 356, 372, r=16, fill=pal["bg"])
    c.rect(58, 356, 356, 372, fill=pal["bg"])
    c.text(74, 340, card.get("title") or "优化后的 README", 16, bold=True, color=dark)
    c.text(74, 382, card.get("label") or "首图 + 过程图 + 编号结构", 12, color=GRAY2)
    c.rrect(74, 400, 338, 412, r=5, fill=(228, 233, 243))
    c.rrect(74, 420, 300, 432, r=5, fill=(228, 233, 243))
    cx = 74
    for i, t in enumerate((card.get("chips") or [])[:3]):
        w = min(120, c.text_w(t, 10) + 16)
        c.rrect(cx, 444, cx + w, 466, r=5, fill=[a, dark, GREEN][i % 3])
        c.text(cx + 8, 449, t, 10, color=WHITE)
        cx += w + 8
    c.text(74, 476, card.get("foot") or "assets/readme/ · 相对路径引用", 11, color=GRAY2)
    c.text(235, 545, b.get("leftCaption") or "内容不变，只把表达和排版做清楚", 16, bold=True,
           color=dark, anchor="ma")

    X = 545
    c.text(X, 62, b.get("eyebrow") or "DEEPSEEK HARNESS · DSH 插件", 16, bold=True, color=a)
    title = b.get("title") or ""
    c.text(X, 88, title, c.fit(title, 56 if len(title) <= 11 else 46, 613), bold=True, color=TEXT)
    if b.get("mono"):
        c.text(X, 168, b["mono"], 19, color=GRAY, mono=True)
    c.line(X, 206, 1158, 206, fill=pal["line"], width=2)
    if b.get("headline"):
        c.text(X, 222, b["headline"], 21, bold=True, color=TEXT)
    draw_bullets(c, X, 272, 613, b.get("bullets"), pal)
    draw_chips(c, X, 404, b.get("chips"), pal)
    if b.get("note"):
        c.text(X, 466, b["note"], 15, color=GRAY2)
    c.line(X, 500, 1158, 500, fill=LINE, width=2)
    c.text(X, 516, b.get("footerLeft") or "", 15, color=GRAY2)
    c.text(1158, 560, b.get("footerRight") or "", 14, color=GRAY2, anchor="ra")


def style_band(c, b, pal):
    a, dark = pal["accent"], pal["dark"]
    c.rect(0, 0, 1200, 600, fill=WHITE)
    c.gradient(0, 0, 320, 600, pal["g1"], pal["g2"])
    draw_icon(c, b.get("icon") or "doc", 100, 64, 120, a)
    c.text(160, 208, b.get("leftTop") or "一个仓库", 18, bold=True, color=dark, anchor="ma")
    rows = [("README.md", "编号章节 + 表格"), ("banner.png", "1200×600 首图"), ("flow.png", "自适应高度过程图")]
    y = 266
    for fname, desc in rows:
        c.rrect(36, y, 284, y + 58, r=10, fill=WHITE)
        c.text(50, y + 9, fname, 13, bold=True, color=dark, mono=True)
        c.text(50, y + 31, desc, 11.5, color=GRAY)
        y += 68
    c.text(160, 560, b.get("leftCaption") or "内容不变，只把表达和排版做清楚", 14.5, bold=True,
           color=dark, anchor="ma")

    X = 372
    c.text(X, 66, b.get("eyebrow") or "DEEPSEEK HARNESS · DSH 插件", 15, bold=True, color=a)
    title = b.get("title") or ""
    c.text(X, 96, title, c.fit(title, 52, 780), bold=True, color=TEXT)
    if b.get("mono"):
        c.text(X, 174, b["mono"], 18, color=GRAY, mono=True)
    c.line(X, 210, 1158, 210, fill=pal["line"], width=2)
    if b.get("headline"):
        c.text(X, 226, b["headline"], 20, bold=True, color=TEXT)
    draw_bullets(c, X, 278, 780, b.get("bullets"), pal, gap=38, size=18.5)
    draw_chips(c, X, 410, b.get("chips"), pal)
    if b.get("note"):
        c.text(X, 474, b["note"], 14.5, color=GRAY2)
    c.line(X, 506, 1158, 506, fill=LINE, width=2)
    c.text(X, 522, b.get("footerLeft") or "", 14.5, color=GRAY2)
    c.text(1158, 564, b.get("footerRight") or "", 13.5, color=GRAY2, anchor="ra")


def style_topbar(c, b, pal):
    a, dark = pal["accent"], pal["dark"]
    c.rect(0, 0, 1200, 600, fill=BG)
    c.gradient(0, 0, 1200, 196, pal["dark"], pal["g2"])
    draw_icon(c, b.get("icon") or "doc", 44, 48, 96, a, tile=False)
    c.text(160, 58, b.get("eyebrow") or "DEEPSEEK HARNESS · DSH 插件", 15, color=(235, 240, 255))
    title = b.get("title") or ""
    c.text(160, 86, title, c.fit(title, 46, 660), bold=True, color=WHITE)
    if b.get("mono"):
        c.text(160, 146, b["mono"], 16, color=(220, 228, 255), mono=True)
    if b.get("headline"):
        c.text(44, 226, b["headline"], 26, bold=True, color=TEXT)
    bullets = (b.get("bullets") or [])[:3]
    bw, bx = 352, 44
    for i, item in enumerate(bullets):
        x = bx + i * (bw + 18)
        c.rrect(x, 288, x + bw, 438, r=14, fill=WHITE, outline=pal["line"], width=2)
        c.circle(x + 30, 320, 15, a)
        c.text(x + 30, 320, str(i + 1), 16, bold=True, color=WHITE, anchor="mm")
        txt = item.get("text", "") if isinstance(item, dict) else str(item)
        c.para(x + 20, 350, bw - 40, txt, 16.5, color=TEXT, lh=26, max_lines=3)
    draw_chips(c, 44, 466, b.get("chips"), pal)
    if b.get("note"):
        c.text(44, 512, b["note"], 14.5, color=GRAY2)
    c.line(44, 528, 1156, 528, fill=LINE, width=2)
    c.text(44, 544, b.get("footerLeft") or "", 14, color=GRAY2)
    c.text(1156, 566, b.get("footerRight") or "", 13.5, color=GRAY2, anchor="ra")


def style_diagonal(c, b, pal):
    a, dark = pal["accent"], pal["dark"]
    c.rect(0, 0, 1200, 600, fill=pal["bg"])
    c.poly([(640, 600), (1200, 600), (1200, 120)], a)
    c.poly([(680, 600), (1200, 600), (1200, 190)], dark)
    draw_icon(c, b.get("icon") or "doc", 56, 52, 104, a)
    c.text(56, 176, b.get("eyebrow") or "DEEPSEEK HARNESS · DSH 插件", 15, bold=True, color=a)
    title = b.get("title") or ""
    c.text(56, 206, title, c.fit(title, 52, 760), bold=True, color=TEXT)
    if b.get("mono"):
        c.text(56, 282, b["mono"], 18, color=GRAY, mono=True)
    if b.get("headline"):
        c.text(56, 320, b["headline"], 20, bold=True, color=TEXT)
    draw_bullets(c, 56, 370, 700, b.get("bullets"), pal, gap=36, size=18)
    draw_chips(c, 56, 474, b.get("chips"), pal)
    if b.get("note"):
        c.text(56, 520, b["note"], 14, color=GRAY2)
    c.text(44, 566, b.get("footerLeft") or "", 13.5, color=GRAY2)
    c.text(1156, 568, b.get("footerRight") or "", 13.5, color=WHITE, anchor="ra")


def style_center(c, b, pal):
    a, dark = pal["accent"], pal["dark"]
    c.rect(0, 0, 1200, 600, fill=pal["bg"])
    c.gradient(0, 0, 1200, 600, pal["g1"], WHITE, horizontal=True)
    for gx in range(0, 1200, 40):
        for gy in range(0, 600, 40):
            c.circle(gx + 20, gy + 20, 1.2, pal["line"])
    draw_icon(c, b.get("icon") or "doc", 552, 52, 96, a)
    c.text(600, 168, b.get("eyebrow") or "DEEPSEEK HARNESS · DSH 插件", 15, bold=True,
           color=a, anchor="ma")
    title = b.get("title") or ""
    c.text(600, 196, title, c.fit(title, 54, 980), bold=True, color=TEXT, anchor="ma")
    if b.get("headline"):
        c.text(600, 276, b["headline"], 22, color=GRAY, anchor="ma")
    bullets = (b.get("bullets") or [])[:3]
    bw = 330
    bx = 600 - (len(bullets) * bw + (len(bullets) - 1) * 20) / 2
    for i, item in enumerate(bullets):
        x = bx + i * (bw + 20)
        txt = item.get("text", "") if isinstance(item, dict) else str(item)
        c.rrect(x, 330, x + bw, 430, r=12, fill=WHITE, outline=pal["line"], width=2)
        c.circle(x + 24, 356, 12, a)
        c.text(x + 24, 356, str(i + 1), 14, bold=True, color=WHITE, anchor="mm")
        c.para(x + 18, 380, bw - 36, txt, 15.5, color=TEXT, lh=24, max_lines=2)
    total = sum(c.pill_w(ch.get("text", "") if isinstance(ch, dict) else str(ch), 15) + 10
                for ch in (b.get("chips") or [])[:4])
    cx = 600 - total / 2 + 5
    for ch in (b.get("chips") or [])[:4]:
        text = ch.get("text", "") if isinstance(ch, dict) else str(ch)
        key = ch.get("color", "") if isinstance(ch, dict) else ""
        p2 = PALETTES.get(COLOR_ALIAS.get(key, key)) or pal
        cx += c.pill(cx, 462, text, 15, fill=p2["bg"], color=p2["dark"]) + 10
    if b.get("note"):
        c.text(600, 516, b["note"], 14, color=GRAY2, anchor="ma")
    c.text(600, 566, b.get("footerLeft") or b.get("footerRight") or "", 13.5, color=GRAY2, anchor="ma")


def style_terminal(c, b, pal):
    a = pal["accent"]
    darkbg = (13, 20, 38)
    bar = (26, 35, 58)
    c.rect(0, 0, 1200, 600, fill=darkbg)
    c.rect(0, 0, 1200, 46, fill=bar)
    for i, col in enumerate([(248, 113, 113), (250, 204, 21), (74, 222, 128)]):
        c.circle(30 + i * 22, 23, 7, col)
    c.text(120, 14, "readme — optimize", 14, color=(148, 163, 184), mono=True)
    c.line(0, 46, 1200, 46, fill=(40, 52, 80), width=2)
    c.text(44, 78, "~/repo $", 16, color=a, mono=True)
    title = b.get("title") or ""
    c.text(150, 70, title, c.fit(title, 44, 960), bold=True, color=WHITE)
    if b.get("mono"):
        c.text(44, 140, "# " + b["mono"], 16, color=(148, 163, 184), mono=True)
    if b.get("headline"):
        c.text(44, 178, b["headline"], 21, color=(226, 232, 240))
    draw_bullets(c, 60, 236, 1050, b.get("bullets"), pal, on_dark=True, gap=36, size=18.5)
    if b.get("chips"):
        c.text(44, 404, "tags:", 15, color=(148, 163, 184), mono=True)
        draw_chips(c, 110, 396, b.get("chips"), pal, on_dark=True)
    if b.get("note"):
        c.text(44, 452, "> " + b["note"], 15, color=(148, 163, 184))
    c.text(44, 510, b.get("footerLeft") or "", 13.5, color=(100, 116, 139))
    c.text(1156, 510, b.get("footerRight") or "", 13.5, color=(100, 116, 139), anchor="ra")
    c.text(44, 556, "▍", 18, color=a)


def style_editorial(c, b, pal):
    a, dark = pal["accent"], pal["dark"]
    c.rect(0, 0, 1200, 600, fill=WHITE)
    c.rect(0, 0, 1200, 8, fill=a)
    draw_icon(c, b.get("icon") or "doc", 56, 54, 72, a)
    c.text(146, 66, b.get("eyebrow") or "DEEPSEEK HARNESS · DSH 插件", 15, bold=True, color=a)
    title = b.get("title") or ""
    c.text(56, 136, title, c.fit(title, 52, 620), bold=True, color=TEXT)
    if b.get("mono"):
        c.text(56, 214, b["mono"], 17, color=GRAY, mono=True)
    if b.get("headline"):
        c.para(56, 250, 560, b["headline"], 19, color=GRAY, lh=28, max_lines=2)
    c.line(56, 330, 616, 330, fill=pal["line"], width=2)
    bullets = (b.get("bullets") or [])[:3]
    y = 352
    for i, item in enumerate(bullets):
        text = item.get("text", "") if isinstance(item, dict) else str(item)
        c.text(56, y, "%02d" % (i + 1), 22, bold=True, color=a, mono=True)
        c.para(106, y + 2, 500, text, 16, color=TEXT, lh=24, max_lines=2)
        c.line(56, y + 54, 616, y + 54, fill=(235, 238, 244), width=2)
        y += 64
    draw_chips(c, 660, 392, b.get("chips"), pal)
    if b.get("note"):
        c.text(660, 450, b["note"], 14.5, color=GRAY2)
    c.text(56, 566, b.get("footerLeft") or "", 13.5, color=GRAY2)
    c.text(1156, 566, b.get("footerRight") or "", 13.5, color=GRAY2, anchor="ra")


def style_cards(c, b, pal):
    a, dark = pal["accent"], pal["dark"]
    c.rect(0, 0, 1200, 600, fill=pal["bg"])
    # 卡片 1：图标 + 标题
    c.rrect(44, 44, 560, 316, r=18, fill=WHITE, outline=pal["line"], width=2)
    draw_icon(c, b.get("icon") or "doc", 76, 72, 84, a)
    title = b.get("title") or ""
    c.text(76, 178, title, c.fit(title, 42, 440), bold=True, color=TEXT)
    if b.get("mono"):
        c.text(76, 240, b["mono"], 16, color=GRAY, mono=True)
    c.text(76, 270, b.get("eyebrow") or "", 13, color=a)
    # 卡片 2：headline
    c.rrect(580, 44, 1156, 316, r=18, fill=WHITE, outline=pal["line"], width=2)
    c.text(612, 78, "一句话", 14, bold=True, color=a)
    c.para(612, 108, 500, b.get("headline") or "", 22, bold=True, color=TEXT, lh=34, max_lines=4)
    # 卡片 3：卖点
    c.rrect(44, 336, 780, 556, r=18, fill=WHITE, outline=pal["line"], width=2)
    bullets = (b.get("bullets") or [])[:3]
    y = 366
    for i, item in enumerate(bullets):
        text = item.get("text", "") if isinstance(item, dict) else str(item)
        c.circle(78, y + 10, 9, a)
        c.text(78, y + 10, str(i + 1), 11, bold=True, color=WHITE, anchor="mm")
        c.para(100, y, 650, text, 16.5, color=TEXT, lh=25, max_lines=2)
        y += 62
    # 卡片 4：chips + note
    c.rrect(800, 336, 1156, 556, r=18, fill=WHITE, outline=pal["line"], width=2)
    draw_chips(c, 824, 366, b.get("chips"), pal, max_w=1130, size=14)
    if b.get("note"):
        c.para(824, 430, 300, b["note"], 13.5, color=GRAY2, lh=22, max_lines=4)
    c.text(44, 576, b.get("footerLeft") or "", 13, color=GRAY2)
    c.text(1156, 576, b.get("footerRight") or "", 13, color=GRAY2, anchor="ra")


def style_wave(c, b, pal):
    a, dark = pal["accent"], pal["dark"]
    c.rect(0, 0, 1200, 600, fill=WHITE)
    c.gradient(0, 0, 1200, 470, pal["g1"], pal["g2"])
    import math
    pts = [(0, 600), (0, 420)]
    for x in range(0, 1201, 40):
        pts.append((x, 400 + 28 * math.sin(x / 120.0 * math.pi)))
    pts.append((1200, 600))
    c.poly(pts, WHITE)
    draw_icon(c, b.get("icon") or "doc", 60, 56, 96, a, tile=False)
    c.text(60, 186, b.get("eyebrow") or "DEEPSEEK HARNESS · DSH 插件", 15, bold=True, color=dark)
    title = b.get("title") or ""
    c.text(60, 214, title, c.fit(title, 52, 760), bold=True, color=TEXT)
    if b.get("mono"):
        c.text(60, 292, b["mono"], 18, color=dark, mono=True)
    if b.get("headline"):
        c.text(60, 330, b["headline"], 20, color=(60, 68, 84))
    draw_bullets(c, 60, 430, 700, b.get("bullets"), pal, gap=34, size=17.5)
    draw_chips(c, 720, 430, b.get("chips"), pal)
    if b.get("note"):
        c.text(720, 500, b["note"], 13.5, color=GRAY2)
    c.text(44, 574, b.get("footerLeft") or "", 13, color=GRAY2)
    c.text(1156, 574, b.get("footerRight") or "", 13, color=GRAY2, anchor="ra")


def style_minimal(c, b, pal):
    a, dark = pal["accent"], pal["dark"]
    c.rect(0, 0, 1200, 600, fill=WHITE)
    c.rect(56, 96, 64, 300, fill=a)
    draw_icon(c, b.get("icon") or "doc", 92, 92, 64, a, tile=False)
    c.text(176, 100, b.get("eyebrow") or "DEEPSEEK HARNESS · DSH 插件", 14, bold=True, color=a)
    title = b.get("title") or ""
    c.text(92, 136, title, c.fit(title, 56, 1020), bold=True, color=TEXT)
    if b.get("mono"):
        c.text(92, 218, b["mono"], 18, color=GRAY, mono=True)
    if b.get("headline"):
        c.text(92, 256, b["headline"], 20, color=GRAY)
    c.line(92, 318, 1110, 318, fill=(232, 235, 242), width=2)
    bullets = (b.get("bullets") or [])[:3]
    for i, item in enumerate(bullets):
        text = item.get("text", "") if isinstance(item, dict) else str(item)
        x = 92 + i * 348
        c.circle(x + 4, 366, 4, a)
        c.para(x + 16, 352, 300, text, 15.5, color=TEXT, lh=24, max_lines=2)
    draw_chips(c, 92, 448, b.get("chips"), pal)
    if b.get("note"):
        c.text(92, 512, b["note"], 14, color=GRAY2)
    c.text(92, 566, b.get("footerLeft") or "", 13, color=GRAY2)
    c.text(1156, 566, b.get("footerRight") or "", 13, color=GRAY2, anchor="ra")


BANNER_STYLES = {
    "split": style_split, "band": style_band, "topbar": style_topbar,
    "diagonal": style_diagonal, "center": style_center, "terminal": style_terminal,
    "editorial": style_editorial, "cards": style_cards, "wave": style_wave,
    "minimal": style_minimal,
}


# ------------------------------- 过程图 -------------------------------
def flow_theme_from(pal):
    return {"accent": pal["accent"], "dark": pal["dark"], "bg": pal["bg"],
            "line": pal["line"], "grad1": pal["g1"], "grad2": pal["g2"]}


def draw_flow(plan, theme, out_path):
    fl = plan.get("flow") or {}
    a, dark = theme["accent"], theme["dark"]
    steps = fl.get("steps") or []
    n = max(1, min(6, len(steps)))
    products = fl.get("products") or []
    hl = fl.get("highlight") or {}
    has_products = bool(products)
    has_hl = bool(hl.get("text"))
    H = 168 + n * 162 + (150 if has_products else 0) + (92 if has_hl else 0) + 78
    c = C(1200, H)
    c.rect(0, 0, 1200, H, fill=BG)
    title = fl.get("title") or "过程：从输入到交付"
    badge = fl.get("badge")
    badge_w = c.pill_w(badge, 16) if badge else 0
    badge_x = 1136 - badge_w
    tsize = 40
    while tsize > 26 and 44 + c.text_w(title, tsize) > badge_x - 24:
        tsize -= 2
    c.text(44, 40, title, tsize, bold=True, color=TEXT)
    if badge:
        c.pill(badge_x, 46, badge, 16, fill=theme["bg"], color=dark)
    c.text(44, 100, fl.get("subtitle") or "", 19, color=GRAY)

    y0, sh, gap = 168, 132, 30
    for i, st in enumerate(steps[:6]):
        y = y0 + i * (sh + gap)
        c.rrect(40, y, 1160, y + sh, r=16, fill=WHITE, outline=LINE, width=2)
        c.circle(92, y + sh / 2, 26, a)
        c.text(92, y + sh / 2, str(i + 1), 24, bold=True, color=WHITE, anchor="mm")
        c.text(136, y + 22, st.get("title") or "", 25, bold=True, color=TEXT)
        if st.get("tag"):
            c.pill(1136 - c.pill_w(st["tag"], 15, 12), y + 18, st["tag"], 15,
                   fill=theme["bg"], color=dark, pad_x=12, h=30)
        c.para(136, y + 62, 860, st.get("desc") or "", 18.5, color=GRAY, lh=29, max_lines=2)
        if i < len(steps[:6]) - 1:
            c.line(92, y + sh, 92, y + sh + gap - 9, fill=theme["line"], width=4)
            c.d.polygon([(92 * S, (y + sh + gap) * S), ((92 - 8) * S, (y + sh + gap - 12) * S),
                         ((92 + 8) * S, (y + sh + gap - 12) * S)], fill=theme["line"])

    oy = y0 + len(steps[:6]) * (sh + gap) + 2
    if has_products:
        c.rrect(40, oy, 1160, oy + 134, r=16, fill=WHITE, outline=theme["line"], width=2)
        c.text(64, oy + 14, fl.get("productsTitle") or "产物（一次写进输出目录）", 20, bold=True, color=dark)
        for i, pr in enumerate(products[:3]):
            x = 64 + i * 372
            p2 = PALETTES.get(COLOR_ALIAS.get(pr.get("color", ""), pr.get("color", "")), None)
            color = p2["accent"] if p2 else a
            c.circle(x + 8, oy + 70, 7, color)
            c.text(x + 24, oy + 56, pr.get("name") or "", 19, bold=True, color=TEXT)
            c.text(x + 24, oy + 86, pr.get("detail") or "", 14.5, color=GRAY)
        oy += 150
    if has_hl:
        c.rrect(40, oy, 1160, oy + 76, r=14, fill=theme["bg"], outline=theme["line"], width=2)
        c.text(64, oy + 16, hl.get("title") or "备注", 17, bold=True, color=dark)
        c.text(64, oy + 44, hl.get("text") or "", 16, color=(60, 68, 84))
        oy += 92

    c.line(44, H - 52, 1156, H - 52, fill=LINE, width=2)
    c.text(44, H - 36, fl.get("footerLeft") or "", 14.5, color=GRAY2)
    c.text(1156, H - 60, fl.get("footerRight") or "", 14, color=GRAY2, anchor="ra")
    c.save(out_path)
    return os.path.getsize(out_path)


# ------------------------------- 选择风格/配色 -------------------------------
def resolve_style_palette(plan):
    """返回 (style_id, palette_name, rng, seed, 是否随机)。"""
    seed = plan.get("seed")
    seed = int(seed) if seed not in (None, "", 0) else random.SystemRandom().randrange(1, 10 ** 9)
    rng = random.Random(seed)
    style = plan.get("style")
    if style in (None, "", "random", "auto"):
        style = rng.choice(STYLE_IDS)
        random_style = True
    elif style not in BANNER_STYLES:
        raise ValueError("未知 style：%s，可选 %s" % (style, ", ".join(STYLE_IDS)))
    else:
        random_style = False
    explicit_pal = plan.get("palette") or THEME_ALIAS.get(str(plan.get("theme") or "").lower())
    if explicit_pal:
        if explicit_pal not in PALETTES:
            raise ValueError("未知 palette：%s，可选 %s" % (explicit_pal, ", ".join(PALETTES)))
        pal = explicit_pal
        random_pal = False
    else:
        pal = rng.choice(STYLE_MAP[style]["palettes"])
        random_pal = True
    return style, pal, rng, seed, (random_style or random_pal)


def render_banner_image(b, style_id, pal_name):
    pal = PALETTES[pal_name]
    c = C(1200, 600)
    BANNER_STYLES[style_id](c, b or {}, pal)
    return c.img.resize((1200, 600), Image.LANCZOS)


# ------------------------------- 风格总览图 -------------------------------
def render_gallery(out_path):
    from PIL import ImageDraw as _ID

    def gf(path, size):
        return ImageFont.truetype(path, size)

    sample = {
        "icon": "doc", "eyebrow": "DEEPSEEK HARNESS · DSH 插件",
        "title": "GitHub 仓库 README 优化", "mono": "dsh-github-readme",
        "headline": "上传 GitHub 之前，先把 README 收拾干净",
        "bullets": ["首图 + 过程图：本地渲染，2 倍超采样", "编号结构：1..N 章，参数表格化",
                    "推前自检：链接、标号、文案评分一起过"],
        "chips": [{"text": "仓库扫描"}, {"text": "首图 / 过程图", "color": "blue"},
                  {"text": "排版校验"}, {"text": "自动推送", "color": "green"}],
        "note": "四个工具：readme_scan → readme_assets → readme_lint → readme_publish",
        "leftTop": "一个本地仓库 / GitHub 链接",
        "leftCard": {"title": "README 优化后", "chips": ["banner.png", "flow.png", "lint 通过"]},
        "leftCaption": "内容不变，只把表达和排版做清楚",
        "footerLeft": "DeepSeek Harness 工具插件", "footerRight": "github.com/zz12hui/dsh-github-readme",
    }
    cols, tw, th, gap, label_h, top = 2, 560, 280, 26, 46, 104
    rows = (len(STYLES) + cols - 1) // cols
    W = cols * tw + (cols + 1) * gap
    H = top + rows * (th + label_h + gap) + gap
    sheet = Image.new("RGB", (W, H), (245, 246, 250))
    d = _ID.Draw(sheet)
    d.text((gap + 4, 22), "dsh-github-readme · 10 种首图风格", font=gf(BOLD, 26), fill=TEXT)
    d.text((gap + 4, 60), "每种风格随机抽一套配色；plan 里可用 style / palette / seed 固定",
           font=gf(REG, 15), fill=GRAY)
    name_font = gf(BOLD, 17)
    pal_font = gf(REG, 13)
    for i, st in enumerate(STYLES):
        pal = st["palettes"][i % len(st["palettes"])]
        img = render_banner_image(sample, st["id"], pal)
        img = img.resize((tw, th), Image.LANCZOS)
        r, col = i // cols, i % cols
        x = gap + col * (tw + gap)
        y = top + r * (th + label_h + gap)
        d.rounded_rectangle([x - 1, y - 1, x + tw, y + th], radius=6, outline=(210, 216, 228), width=2)
        sheet.paste(img, (x, y))
        d.text((x + 6, y + th + 12), "%02d  %s" % (i + 1, st["name"]), font=name_font, fill=TEXT)
        pal_text = "%s · %s" % (st["id"], pal)
        pw = pal_font.getlength(pal_text)
        d.text((x + tw - 6 - pw, y + th + 15), pal_text, font=pal_font, fill=GRAY)
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    sheet.save(out_path, "PNG", optimize=True)
    return os.path.getsize(out_path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan-file")
    ap.add_argument("--gallery")
    ap.add_argument("--list-styles", action="store_true")
    args = ap.parse_args()
    if args.list_styles:
        print(json.dumps({"styles": [{"id": s["id"], "name": s["name"],
                                      "palettes": s["palettes"], "desc": s["desc"]} for s in STYLES],
                          "palettes": list(PALETTES.keys())}, ensure_ascii=False))
        return 0
    if args.gallery:
        try:
            size = render_gallery(args.gallery)
            print("RESULT_JSON:" + json.dumps({"ok": True, "gallery": args.gallery, "bytes": size},
                                              ensure_ascii=False), flush=True)
        except Exception as e:  # noqa: BLE001
            print("RESULT_JSON:" + json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False), flush=True)
            return 1
        return 0

    if not args.plan_file:
        print("RESULT_JSON:" + json.dumps({"ok": False, "error": "需要 --plan-file 或 --gallery"},
                                          ensure_ascii=False), flush=True)
        return 1
    try:
        with open(args.plan_file, encoding="utf-8") as f:
            plan = json.load(f)
        out_dir = plan.get("outDir")
        if not out_dir:
            raise ValueError("plan.outDir 不能为空")
        style, pal_name, _rng, seed, randomed = resolve_style_palette(plan)
        pal = PALETTES[pal_name]
        images = []
        banner_meta = None
        if plan.get("banner"):
            name = plan["banner"].get("fileName") or "banner.png"
            path = os.path.join(out_dir, name)
            img = render_banner_image(plan["banner"], style, pal_name)
            os.makedirs(out_dir, exist_ok=True)
            img.save(path, "PNG", optimize=True)
            size = os.path.getsize(path)
            images.append({"kind": "banner", "path": path, "bytes": size})
            banner_meta = {"style": style, "styleName": STYLE_MAP[style]["name"],
                           "palette": pal_name, "seed": seed, "random": randomed}
        if plan.get("flow"):
            name = plan["flow"].get("fileName") or "flow.png"
            theme = flow_theme_from(pal)
            explicit_theme = THEME_ALIAS.get(str(plan.get("theme") or "").lower())
            if explicit_theme:
                theme = flow_theme_from(PALETTES[explicit_theme])
            path = os.path.join(out_dir, name)
            size = draw_flow(plan, theme, path)
            images.append({"kind": "flow", "path": path, "bytes": size})
        if not images:
            raise ValueError("plan 里 banner 和 flow 至少给一个")
        out = {"ok": True, "outDir": out_dir, "images": images, "seed": seed}
        if banner_meta:
            out["banner"] = banner_meta
        print("RESULT_JSON:" + json.dumps(out, ensure_ascii=False), flush=True)
    except Exception as e:  # noqa: BLE001
        print("RESULT_JSON:" + json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False),
              flush=True)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
