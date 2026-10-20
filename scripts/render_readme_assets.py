# -*- coding: utf-8 -*-
"""README 首图 + 过程图渲染器（DSH github-readme 插件的素材后端）。

用法:
  python render_readme_assets.py --plan-file plan.json

plan.json:
{
  "outDir": "输出目录（必填）",
  "theme": "blue | green | violet | orange",     // 默认 blue
  "banner": { ... },                              // 可选，有就画 banner.png
  "flow": { ... }                                 // 可选，有就画 flow.png
}

banner 字段（都可省略，省略走默认）:
  icon         play | check | doc | branch | bolt | puzzle
  eyebrow      顶部小字，默认 "DEEPSEEK HARNESS · DSH 插件"
  title        大标题（必填才画）
  mono         英文包名/仓库名
  headline     一句主张
  bullets      ["...", ...]（每条一行，最多 4 条）
  chips        [{"text": "...", "color": "blue|green|orange|violet"}, ...]
  note         小字备注
  leftTop      左栏顶部标签
  leftCard     { "title", "label", "chips": ["", "", ""], "foot" }
  leftCaption  左栏底部一句
  footerLeft / footerRight

flow 字段:
  title        标题
  subtitle     副标题
  badge        右上角标签
  steps        [{"title","tag","desc"}, ...]  3–6 步
  productsTitle / products [{"name","detail","color"}]
  highlight    {"title","text"}               可选提示条
  footerLeft / footerRight

末尾输出一行 RESULT_JSON:{"ok":true,"images":[...],"bytes":{...}}
"""
import argparse
import json
import os
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

THEMES = {
    "blue": {
        "accent": (47, 107, 255), "dark": (30, 64, 175),
        "bg": (234, 241, 255), "line": (201, 217, 255),
        "grad1": (236, 243, 255), "grad2": (156, 190, 255),
    },
    "green": {
        "accent": (31, 122, 77), "dark": (22, 78, 52),
        "bg": (241, 250, 244), "line": (159, 203, 176),
        "grad1": (240, 248, 242), "grad2": (146, 202, 172),
    },
    "violet": {
        "accent": (109, 76, 196), "dark": (76, 45, 140),
        "bg": (245, 242, 255), "line": (196, 184, 235),
        "grad1": (246, 243, 255), "grad2": (186, 170, 235),
    },
    "orange": {
        "accent": (232, 137, 12), "dark": (160, 84, 8),
        "bg": (255, 249, 242), "line": (240, 178, 92),
        "grad1": (255, 250, 243), "grad2": (245, 200, 150),
    },
}
NAVY = (31, 56, 100)
GREEN = (31, 122, 77)
RED = (163, 62, 40)
LINE = (226, 232, 244)

S = 2


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
    def __init__(self, w, h):
        self.w, self.h = w, h
        self.img = Image.new("RGB", (w * S, h * S), BG)
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

    def circle(self, cx, cy, r, fill, outline=None, width=1):
        self.d.ellipse([(cx - r) * S, (cy - r) * S, (cx + r) * S, (cy + r) * S],
                       fill=fill, outline=outline, width=int(round(width * S)))

    def line(self, x1, y1, x2, y2, fill=GRAY, width=2):
        self.d.line([x1 * S, y1 * S, x2 * S, y2 * S], fill=fill, width=int(round(width * S)))

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

    def gradient(self, x1, y1, x2, y2, c1, c2):
        import numpy as np
        w, h = x2 - x1, y2 - y1
        t = np.linspace(0, 1, w * h).reshape(h, w, 1)
        arr = (np.array(c1)[None, None, :] * (1 - t) + np.array(c2)[None, None, :] * t).astype("uint8")
        im = Image.fromarray(arr, "RGB").resize((w * S, h * S), Image.BILINEAR)
        self.img.paste(im, (x1 * S, y1 * S))

    def save(self, path):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self.img.resize((self.w, self.h), Image.LANCZOS).save(path, "PNG", optimize=True)
        return os.path.getsize(path)


# ------------------------------- 图标 -------------------------------
def _icon_base(c, x, y, size, accent, r=19):
    c.rrect(x, y, x + size, y + size, r=r, fill=accent)


def draw_icon(c, glyph, x, y, size, accent):
    s = size / 64.0
    glyph = (glyph or "doc").lower()
    _icon_base(c, x, y, size, accent)
    lw = max(2, int(3 * s))
    if glyph == "play":
        c.rrect(x + 17 * s, y + 22 * s, x + 47 * s, y + 44 * s, r=2 * s, outline=WHITE, width=lw)
        c.line(x + 25 * s, y + 17.5 * s, x + 22 * s, y + 22 * s, fill=WHITE, width=lw)
        c.line(x + 39 * s, y + 17.5 * s, x + 42 * s, y + 22 * s, fill=WHITE, width=lw)
        c.circle(x + 26 * s, y + 30 * s, 2.6 * s, WHITE)
        c.circle(x + 38 * s, y + 30 * s, 2.6 * s, WHITE)
        c.d.arc([(x + 23 * s) * S, (y + 30 * s) * S, (x + 41 * s) * S, (y + 41 * s) * S],
                start=20, end=160, fill=WHITE, width=int(round(2.4 * s * S)))
        c.line(x + 20 * s, y + 50 * s, x + 44 * s, y + 50 * s, fill=WHITE, width=lw)
    elif glyph == "check":
        c.line(x + 16 * s, y + 22 * s, x + 36 * s, y + 22 * s, fill=WHITE, width=lw)
        c.line(x + 16 * s, y + 32 * s, x + 44 * s, y + 32 * s, fill=WHITE, width=lw)
        c.line(x + 16 * s, y + 42 * s, x + 30 * s, y + 42 * s, fill=WHITE, width=lw)
        c.circle(x + 46 * s, y + 42 * s, 9 * s, (143, 211, 168))
        c.d.line([(x + 41.5 * s) * S, (y + 42 * s) * S, (x + 44.5 * s) * S, (y + 45 * s) * S,
                  (x + 50 * s) * S, (y + 38.5 * s) * S], fill=accent,
                 width=int(round(2.6 * s * S)), joint="curve")
    elif glyph == "branch":
        c.circle(x + 24 * s, y + 20 * s, 5 * s, WHITE)
        c.circle(x + 24 * s, y + 44 * s, 5 * s, WHITE)
        c.circle(x + 44 * s, y + 30 * s, 5 * s, WHITE)
        c.line(x + 24 * s, y + 25 * s, x + 24 * s, y + 39 * s, fill=WHITE, width=lw)
        c.line(x + 29 * s, y + 22 * s, x + 39 * s, y + 28 * s, fill=WHITE, width=lw)
        c.line(x + 29 * s, y + 42 * s, x + 39 * s, y + 33 * s, fill=WHITE, width=lw)
    elif glyph == "bolt":
        c.d.polygon([(x + 35 * s) * S, (y + 14 * s) * S, (x + 22 * s) * S, (y + 36 * s) * S,
                     (x + 31 * s) * S, (y + 36 * s) * S, (x + 28 * s) * S, (y + 50 * s) * S,
                     (x + 43 * s) * S, (y + 27 * s) * S, (x + 33 * s) * S, (y + 27 * s) * S],
                    fill=WHITE)
    elif glyph == "puzzle":
        c.rrect(x + 15 * s, y + 15 * s, x + 30 * s, y + 30 * s, r=3 * s, fill=WHITE)
        c.rrect(x + 34 * s, y + 15 * s, x + 49 * s, y + 30 * s, r=3 * s, fill=WHITE)
        c.rrect(x + 15 * s, y + 34 * s, x + 30 * s, y + 49 * s, r=3 * s, fill=WHITE)
        c.circle(x + 42 * s, y + 42 * s, 7 * s, (255, 255, 255))
    else:  # doc + 星
        c.rrect(x + 18 * s, y + 14 * s, x + 42 * s, y + 48 * s, r=3 * s, outline=WHITE, width=lw)
        c.line(x + 24 * s, y + 24 * s, x + 36 * s, y + 24 * s, fill=WHITE, width=lw)
        c.line(x + 24 * s, y + 31 * s, x + 36 * s, y + 31 * s, fill=WHITE, width=lw)
        c.line(x + 24 * s, y + 38 * s, x + 31 * s, y + 38 * s, fill=WHITE, width=lw)
        cx, cy, r1, r2 = x + 46 * s, y + 44 * s, 8 * s, 3.2 * s
        pts = []
        import math
        for k in range(8):
            ang = -math.pi / 2 + k * math.pi / 4
            rr = r1 if k % 2 == 0 else r2
            pts.append(((cx + rr * math.cos(ang)) * S, (cy + rr * math.sin(ang)) * S))
        c.d.polygon(pts, fill=WHITE)


# ------------------------------- 首图 -------------------------------
def draw_banner(plan, theme, out_path):
    b = plan.get("banner") or {}
    a, dark = theme["accent"], theme["dark"]
    c = C(1200, 600)
    c.rect(0, 0, 1200, 600, fill=BG)
    c.gradient(0, 0, 470, 600, theme["grad1"], theme["grad2"])
    c.d.polygon([(408 * S, 0), (474 * S, 0), (428 * S, 600 * S), (362 * S, 600 * S)], fill=WHITE)

    draw_icon(c, b.get("icon") or "doc", 160, 66, 150, a)
    c.text(235, 242, b.get("leftTop") or "一个仓库 / 一个链接", 20, bold=True, color=dark, anchor="ma")
    c.arrow_down(235, 280, 318, color=dark, width=4, head=10)

    card = b.get("leftCard") or {}
    c.rrect(58, 330, 356, 520, r=16, fill=WHITE, outline=theme["line"], width=2)
    c.rrect(58, 330, 356, 372, r=16, fill=theme["bg"])
    c.rect(58, 356, 356, 372, fill=theme["bg"])
    c.text(74, 340, card.get("title") or "优化后的 README", 16, bold=True, color=dark)
    c.text(74, 382, card.get("label") or "首图 + 过程图 + 编号结构", 12, color=GRAY2)
    c.rrect(74, 400, 338, 412, r=5, fill=(228, 233, 243))
    c.rrect(74, 420, 300, 432, r=5, fill=(228, 233, 243))
    chips = card.get("chips") or ["首图 banner", "过程图", "编号章节"]
    cols = [a, theme["accent"], GREEN]
    cx = 74
    for i, t in enumerate(chips[:3]):
        w = min(120, fnt(REG, 10).getlength(str(t)) / S + 16)
        c.rrect(cx, 444, cx + w, 466, r=5, fill=cols[i % 3])
        c.text(cx + 8, 449, t, 10, color=WHITE)
        cx += w + 8
    c.text(74, 476, card.get("foot") or "assets/readme/ · 相对路径引用", 11, color=GRAY2)
    c.text(235, 545, b.get("leftCaption") or "内容不变，只把表达和排版做清楚", 16,
           bold=True, color=dark, anchor="ma")

    X = 545
    c.text(X, 62, b.get("eyebrow") or "DEEPSEEK HARNESS · DSH 插件", 16, bold=True, color=a)
    title = b.get("title") or ""
    tsize = 56 if len(title) <= 11 else 46
    while tsize > 34 and fnt(BOLD, tsize).getlength(title) / S > 613:
        tsize -= 2
    c.text(X, 88, title, tsize, bold=True, color=TEXT)
    if b.get("mono"):
        c.text(X, 168, b["mono"], 19, color=GRAY, mono=True)
    c.line(X, 206, 1158, 206, fill=theme["line"], width=2)
    if b.get("headline"):
        c.text(X, 222, b["headline"], 21, bold=True, color=TEXT)
    y = 272
    for i, item in enumerate((b.get("bullets") or [])[:4]):
        col = a
        if isinstance(item, dict):
            txt = item.get("text", "")
            col = {"blue": (47, 107, 255), "green": GREEN, "orange": (232, 137, 12),
                   "violet": (109, 76, 196), "red": RED}.get(item.get("color", ""), a)
        else:
            txt = str(item)
        c.circle(X + 5, y + 9, 5, col)
        c.text(X + 20, y, txt, 19, color=TEXT)
        y += 38
    cy = max(404, y + 14)
    x = X
    for ch in (b.get("chips") or [])[:4]:
        color = (ch.get("color") if isinstance(ch, dict) else "") or "theme"
        fill = theme["bg"] if color == "theme" else {
            "blue": (234, 241, 255), "green": (241, 250, 244),
            "orange": (255, 249, 242), "violet": (245, 242, 255)}.get(color, theme["bg"])
        fg = dark if color == "theme" else {
            "blue": (30, 64, 175), "green": GREEN,
            "orange": (160, 84, 8), "violet": (76, 45, 140)}.get(color, dark)
        text = ch.get("text", "") if isinstance(ch, dict) else str(ch)
        x += c.pill(x, cy, text, 16, fill=fill, color=fg) + 10
    if b.get("note"):
        c.text(X, cy + 58, b["note"], 15, color=GRAY2)
    c.line(X, 500, 1158, 500, fill=LINE, width=2)
    c.text(X, 516, b.get("footerLeft") or "", 15, color=GRAY2)
    c.text(1158, 560, b.get("footerRight") or "", 14, color=GRAY2, anchor="ra")
    return out_path, c.save(out_path)


# ------------------------------- 过程图 -------------------------------
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
    while tsize > 26 and 44 + fnt(BOLD, tsize).getlength(title) / S > badge_x - 24:
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
            color = {"blue": (47, 107, 255), "green": GREEN,
                     "orange": (232, 137, 12), "violet": (109, 76, 196)}.get(
                pr.get("color", "theme"), a)
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
    return out_path, c.save(out_path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan-file", required=True)
    args = ap.parse_args()
    try:
        with open(args.plan_file, encoding="utf-8") as f:
            plan = json.load(f)
        out_dir = plan.get("outDir")
        if not out_dir:
            raise ValueError("plan.outDir 不能为空")
        theme = THEMES.get(plan.get("theme") or "blue", THEMES["blue"])
        images = []
        if plan.get("banner"):
            name = plan["banner"].get("fileName") or "banner.png"
            path, size = draw_banner(plan, theme, os.path.join(out_dir, name))
            images.append({"kind": "banner", "path": path, "bytes": size})
        if plan.get("flow"):
            name = plan["flow"].get("fileName") or "flow.png"
            path, size = draw_flow(plan, theme, os.path.join(out_dir, name))
            images.append({"kind": "flow", "path": path, "bytes": size})
        if not images:
            raise ValueError("plan 里 banner 和 flow 至少给一个")
        print("RESULT_JSON:" + json.dumps({"ok": True, "outDir": out_dir, "images": images},
                                          ensure_ascii=False), flush=True)
    except Exception as e:  # noqa: BLE001
        print("RESULT_JSON:" + json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False),
              flush=True)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
