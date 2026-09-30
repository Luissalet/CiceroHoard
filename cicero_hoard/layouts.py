"""Slide geometry shared by the HTML renderer and the PPTX exporter.

A slide is laid out once, on a 1280 x 720 px canvas (13.333 x 7.5 in at 96 dpi), as a list of boxes: rectangles,
text boxes (with paragraphs), pictures and charts. Both renderers draw exactly these boxes, so a preview, a PDF and
a PPTX agree. Text is fitted here: the font size goes down step by step until the estimated height fits the box,
and a box that still does not fit at the smallest size is flagged as overflowing (the checker reports it).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .themes import font_kind

W, H = 1280, 720
MARGIN_X = 72
CONTENT_BOTTOM = 652
GAP = 22
BODY_LINE = 1.3
HEAD_LINE = 1.15
# Body text starts at this size and only shrinks when a slide is full: a short slide reads from the back of the room.
BODY_MAX = 34
SAFETY = 1.05  # estimated widths are inflated a little so that a fallback font does not wrap unexpectedly

COLOR_KEYS = ("background", "surface", "text", "muted", "accent", "accent2")


@dataclass
class Para:
    text: str
    size: float
    bold: bool = False
    italic: bool = False
    color: str = "text"
    font: str = "body"  # "heading" | "body"
    bullet: bool = False
    indent: int = 0  # px, only for bullets
    align: str = "left"
    space_after: float = 0.0
    line: float = BODY_LINE


@dataclass
class Box:
    kind: str  # "rect" | "text" | "image" | "chart"
    x: float
    y: float
    w: float
    h: float
    fill: Optional[str] = None
    paras: list[Para] = field(default_factory=list)
    anchor: str = "top"  # "top" | "middle" | "bottom"
    role: str = ""  # "title" for the slide title, "footer" for footers
    image: Optional[dict[str, Any]] = None  # {"asset_id", "alt"}
    chart: Optional[dict[str, Any]] = None  # the chart block
    overflow: bool = False


@dataclass
class Plan:
    boxes: list[Box]
    overflow: bool = False
    overflow_where: list[str] = field(default_factory=list)


@dataclass
class Ctx:
    theme: dict[str, Any]
    lang: str = "es"
    assets: Callable[[str], Optional[dict[str, Any]]] = lambda _id: None
    overflow_where: list[str] = field(default_factory=list)

    def font_name(self, key: str) -> str:
        return self.theme["fonts"]["heading" if key == "heading" else "body"]

    def kind(self, key: str) -> str:
        return font_kind(self.font_name(key))


# ---------------- text measurement ----------------

_NARROW = set("il.,;:'|!¡¿")
_SMALL = set("tfrjI()[]{}/\\-\" ")
_WIDE = set("mw")
_VERY_WIDE = set("MW@%")


def char_width(c: str) -> float:
    if c in _NARROW:
        return 0.27
    if c == " ":
        return 0.28
    if c in _SMALL:
        return 0.34
    if c in _WIDE:
        return 0.80
    if c in _VERY_WIDE:
        return 0.92
    if c.isupper():
        return 0.64
    if c.isdigit():
        return 0.56
    if ord(c) > 0x2E80:  # CJK and friends
        return 1.0
    return 0.52


def text_width(text: str, size: float, kind: str = "sans", bold: bool = False) -> float:
    if kind == "mono":
        return len(text) * size * 0.6 * (1.0)
    factor = 1.03 if kind == "serif" else 1.0
    if bold:
        factor *= 1.07
    return sum(char_width(c) for c in text) * size * factor * SAFETY


def count_lines(text: str, width: float, size: float, kind: str, bold: bool) -> int:
    """Greedy word wrap using the width estimate; an over-long word is broken by characters."""
    if width <= 0:
        return 1
    lines = 1
    cur = 0.0
    space = text_width(" ", size, kind, bold)
    for word in text.split():
        w = text_width(word, size, kind, bold)
        if w > width:  # break the word across lines
            if cur > 0:
                lines += 1
                cur = 0.0
            extra = int(w // width)
            lines += extra
            cur = w - extra * width
            continue
        if cur == 0:
            cur = w
        elif cur + space + w <= width:
            cur += space + w
        else:
            lines += 1
            cur = w
    return lines


def para_height(p: Para, width: float, ctx: Ctx) -> float:
    avail = width - (p.indent if p.bullet else 0)
    lines = count_lines(p.text, avail, p.size, ctx.kind(p.font), p.bold)
    return lines * p.size * p.line + p.space_after


def paras_height(paras: list[Para], width: float, ctx: Ctx) -> float:
    if not paras:
        return 0.0
    total = sum(para_height(p, width, ctx) for p in paras)
    return total - paras[-1].space_after


def fit_size(make: Callable[[int], list[Para]], width: float, height: float, hi: int, lo: int, ctx: Ctx) -> tuple[int, bool]:
    for size in range(int(hi), int(lo) - 1, -1):
        if paras_height(make(size), width, ctx) <= height:
            return size, False
    return int(lo), True


def bullet_indent(size: float) -> int:
    return max(18, round(size * 0.95))


# ---------------- number formatting ----------------

def fmt_num(value: float, lang: str = "es") -> str:
    """Numbers as they were typed: no invented precision, decimal comma in Spanish."""
    # Spanish business documents group thousands with a point (250.000), as the sources usually do.
    if float(value).is_integer():
        if abs(value) < 10_000:
            return f"{int(value)}"
        grouped = f"{int(value):,}"
        return grouped.replace(",", ".") if lang == "es" else grouped
    text = f"{value:.6g}"
    if "e" in text:
        text = f"{value:.4f}".rstrip("0").rstrip(".")
    return text.replace(".", ",") if lang == "es" else text


# ---------------- block layout ----------------

def _translate(boxes: list[Box], dx: float, dy: float) -> None:
    for b in boxes:
        b.x += dx
        b.y += dy


def _text_box(paras: list[Para], x: float, y: float, w: float, ctx: Ctx, **kw: Any) -> Box:
    h = paras_height(paras, w, ctx)
    return Box("text", x, y, w, h, paras=paras, **kw)


def _split_lines(text: str) -> list[str]:
    return [ln.strip() for ln in re.split(r"\n+", text or "") if ln.strip()]


def _bullet_paras(items: list[str], size: float, color: str = "text") -> list[Para]:
    return [Para(t, size, bullet=True, indent=bullet_indent(size), color=color, space_after=round(size * 0.55)) for t in items]


def layout_block(block: dict[str, Any], x: float, y: float, w: float, size: int, ctx: Ctx, *, region_h: float, n_blocks: int) -> tuple[list[Box], float]:
    """Lay one block out at font size ``size``; returns its boxes and its height."""
    kind = block.get("type")
    if kind == "bullets":
        items = [i for i in block.get("items", []) if i]
        if not items:
            return [], 0.0
        box = _text_box(_bullet_paras(items, size), x, y, w, ctx)
        return [box], box.h
    if kind == "text":
        lines = _split_lines(block.get("text", ""))
        if not lines:
            return [], 0.0
        paras = [Para(t, size, space_after=round(size * 0.6)) for t in lines]
        box = _text_box(paras, x, y, w, ctx)
        return [box], box.h
    if kind == "quote":
        text = (block.get("text") or "").strip()
        if not text:
            return [], 0.0
        paras = [Para(f"“{text}”", size * 1.1, italic=True, font="heading", space_after=round(size * 0.5), line=1.25)]
        if block.get("attribution"):
            paras.append(Para(f"— {block['attribution']}", size * 0.8, color="muted"))
        inner = _text_box(paras, x + 26, y, w - 26, ctx)
        bar = Box("rect", x, y, 6, inner.h, fill="accent")
        return [bar, inner], inner.h
    if kind == "image":
        info = ctx.assets(block.get("asset_id", ""))
        if not info:
            return [], 0.0
        caption = (block.get("caption") or "").strip()
        cap_paras = [Para(caption, 14, color="muted", align="center")] if caption else []
        cap_h = paras_height(cap_paras, w, ctx) + (8 if caption else 0)
        max_h = region_h if n_blocks == 1 else min(300, region_h * 0.5)
        max_h = max(60.0, max_h - cap_h)
        scale = min(w / info["width"], max_h / info["height"])
        iw, ih = info["width"] * scale, info["height"] * scale
        boxes = [Box("image", x + (w - iw) / 2, y, iw, ih, image={"asset_id": block["asset_id"], "alt": caption or ""})]
        if cap_paras:
            boxes.append(_text_box(cap_paras, x, y + ih + 8, w, ctx))
        return boxes, ih + cap_h
    if kind == "chart":
        if not block.get("categories") or not block.get("series"):
            return [], 0.0
        boxes: list[Box] = []
        cy = 0.0
        if block.get("title"):
            t = _text_box([Para(block["title"], 20, bold=True, color="muted", font="heading", line=HEAD_LINE)], x, y, w, ctx)
            boxes.append(t)
            cy = t.h + 10
        avail = region_h - cy
        ch = avail if n_blocks == 1 else min(340.0, avail * 0.6)
        ch = max(180.0, ch)
        boxes.append(Box("chart", x, y + cy, w, ch, chart=block))
        return boxes, cy + ch
    if kind == "columns":
        gap = 32
        cw = (w - gap) / 2
        pad = 22
        cols = []
        heights = []
        for side in ("left", "right"):
            paras: list[Para] = []
            title = block.get(f"{side}_title")
            if title:
                paras.append(Para(title, size * 0.95, bold=True, color="accent", font="heading", space_after=round(size * 0.5), line=HEAD_LINE))
            paras += _bullet_paras(block.get(side, []), size)
            cols.append(paras)
            heights.append(paras_height(paras, cw - 2 * pad, ctx))
        total = max(heights + [0.0]) + 2 * pad
        if total <= 2 * pad:
            return [], 0.0
        boxes = []
        for i, paras in enumerate(cols):
            cx = x + i * (cw + gap)
            boxes.append(Box("rect", cx, y, cw, total, fill="surface"))
            if paras:
                boxes.append(Box("text", cx + pad, y + pad, cw - 2 * pad, heights[i], paras=paras))
        return boxes, total
    return [], 0.0


def stack(blocks: list[dict[str, Any]], x: float, y: float, w: float, h: float, ctx: Ctx, *, smax: int = 28, smin: int = 16, where: str = "content") -> tuple[list[Box], bool]:
    """Place blocks one under the other; pick the largest common font size that fits the region."""
    blocks = [b for b in blocks if b]

    def build(size: int) -> tuple[list[Box], float]:
        boxes: list[Box] = []
        cy = 0.0
        for b in blocks:
            got, bh = layout_block(b, 0, cy, w, size, ctx, region_h=h, n_blocks=len(blocks))
            if bh > 0:
                boxes += got
                cy += bh + GAP
        return boxes, max(0.0, cy - GAP)

    overflow = False
    boxes: list[Box] = []
    for size in range(smax, smin - 1, -1):
        boxes, total = build(size)
        if total <= h:
            break
    else:
        boxes, total = build(smin)
        overflow = total > h + 1
    if overflow:
        ctx.overflow_where.append(where)
        for b in boxes:
            if b.kind == "text":
                b.overflow = True
    _translate(boxes, x, y)
    return boxes, overflow


def stack_size(blocks: list[dict[str, Any]], w: float, h: float, ctx: Ctx, smax: int, smin: int) -> int:
    """The font size ``stack`` would pick (used to give two columns the same size)."""
    for size in range(smax, smin - 1, -1):
        cy = 0.0
        for b in blocks:
            _, bh = layout_block(b, 0, cy, w, size, ctx, region_h=h, n_blocks=len(blocks))
            if bh > 0:
                cy += bh + GAP
        if max(0.0, cy - GAP) <= h:
            return size
    return smin


def title_box(text: str, x: float, y: float, w: float, h: float, ctx: Ctx, *, hi: int, lo: int, anchor: str = "bottom", color: str = "text", where: str = "title", italic: bool = False) -> Box:
    def make(size: int) -> list[Para]:
        return [Para(text, size, bold=True, color=color, font="heading", line=HEAD_LINE, italic=italic)]

    size, over = fit_size(make, w, h, hi, lo, ctx)
    if over:
        ctx.overflow_where.append(where)
    return Box("text", x, y, w, h, paras=make(size), anchor=anchor, role="title", overflow=over)


def plain_box(text: str, x: float, y: float, w: float, h: float, ctx: Ctx, *, hi: int, lo: int, color: str = "muted", anchor: str = "top", bold: bool = False, where: str = "subtitle", font: str = "body", role: str = "") -> Box:
    def make(size: int) -> list[Para]:
        return [Para(text, size, bold=bold, color=color, font=font, line=BODY_LINE if font == "body" else HEAD_LINE)]

    size, over = fit_size(make, w, h, hi, lo, ctx)
    if over:
        ctx.overflow_where.append(where)
    return Box("text", x, y, w, h, paras=make(size), anchor=anchor, overflow=over, role=role)


def _footer(deck_title: str, number: int, total: int, ctx: Ctx) -> list[Box]:
    return [
        Box("text", MARGIN_X, 682, 900, 20, role="footer", paras=[Para(deck_title, 13, color="muted")], anchor="middle"),
        Box("text", W - MARGIN_X - 120, 682, 120, 20, role="footer", paras=[Para(f"{number} / {total}", 13, color="muted", align="right")], anchor="middle"),
    ]


def _first_blocks_text(blocks: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for b in blocks:
        if b.get("type") == "text" and b.get("text"):
            parts.append(" ".join(_split_lines(b["text"])))
        elif b.get("type") == "bullets":
            parts.append(" · ".join(b.get("items", [])))
        elif b.get("type") == "quote" and b.get("text"):
            parts.append(b["text"])
    return "   ".join(p for p in parts if p)


def build_plan(slide: dict[str, Any], *, deck_title: str, theme: dict[str, Any], number: int, total: int,
               lang: str = "es", assets: Optional[Callable[[str], Optional[dict[str, Any]]]] = None) -> Plan:
    ctx = Ctx(theme=theme, lang=lang, assets=assets or (lambda _id: None))
    layout = slide.get("layout") or "bullets"
    title = (slide.get("title") or "").strip()
    subtitle = (slide.get("subtitle") or "").strip()
    blocks: list[dict[str, Any]] = list(slide.get("blocks") or [])
    boxes: list[Box] = []

    if layout in ("title", "closing"):
        boxes.append(Box("rect", 0, 0, 22, H, fill="accent"))
        if layout == "title":
            top, bottom = 130, 392
            rule_y, sub_y, sub_h = 412, 436, 100
        else:
            top, bottom = 90, 300
            rule_y, sub_y, sub_h = 318, 342, 70
        if title:
            boxes.append(title_box(title, 96, top, 1088, bottom - top, ctx, hi=64 if layout == "title" else 54, lo=30))
        boxes.append(Box("rect", 96, rule_y, 112, 6, fill="accent2"))
        if subtitle:
            boxes.append(plain_box(subtitle, 96, sub_y, 1088, sub_h, ctx, hi=28, lo=16))
        if layout == "title":
            line = _first_blocks_text(blocks)
            if line:
                boxes.append(Box("rect", 22, 588, W - 22, 132, fill="surface"))
                boxes.append(plain_box(line, 96, 604, 1088, 100, ctx, hi=22, lo=14, anchor="middle", where="title_line"))
        else:
            got, _ = stack(blocks, 96, 420 if subtitle else 380, 1088, 236 if subtitle else 276, ctx, smax=26, smin=15, where="closing")
            boxes += got
    elif layout == "section":
        boxes.append(Box("rect", 0, 0, W, H, fill="surface"))
        boxes.append(Box("rect", 96, 200, 8, 230, fill="accent"))
        if title:
            boxes.append(title_box(title, 132, 200, 1050, 150, ctx, hi=56, lo=28))
        if subtitle:
            boxes.append(plain_box(subtitle, 132, 366, 1050, 120, ctx, hi=26, lo=16))
        line = _first_blocks_text(blocks)
        if line:
            boxes.append(plain_box(line, 132, 500, 1050, 80, ctx, hi=20, lo=14, where="section_line"))
    elif layout == "quote":
        quote = next((b for b in blocks if b.get("type") == "quote" and (b.get("text") or "").strip()), None)
        rest = [b for b in blocks if b is not quote]
        if title:
            boxes.append(plain_box(title, MARGIN_X, 44, 1136, 40, ctx, hi=22, lo=14, bold=True, font="heading", where="title", role="title"))
        if quote is None:
            got, _ = stack(blocks, MARGIN_X, 130, 1136, CONTENT_BOTTOM - 130, ctx, smax=30, smin=16)
            boxes += got
        else:
            has_attr = bool((quote.get("attribution") or "").strip())
            attr_h = 44 if has_attr else 0
            rest_h = 120 if rest else 0
            q_h = 520 - 90 - attr_h - (rest_h + 20 if rest else 0)

            def make(size: int) -> list[Para]:
                return [Para(quote["text"].strip(), size, italic=True, font="heading", line=1.25)]

            size, over = fit_size(make, 980, q_h, 44, 20, ctx)
            if over:
                ctx.overflow_where.append("quote")
            text_h = min(q_h, paras_height(make(size), 980, ctx))
            group_h = 90 + text_h + (16 + attr_h if has_attr else 0)
            gy = 100 + max(0, (520 - rest_h - (20 if rest else 0) - group_h) / 2)
            boxes.append(Box("text", 84, gy, 120, 110, paras=[Para("\u201c", 150, color="accent", font="heading", line=1.0)]))
            boxes.append(Box("text", 150, gy + 90, 980, text_h, paras=make(size), overflow=over))
            if has_attr:
                boxes.append(plain_box(f"\u2014 {quote['attribution'].strip()}", 150, gy + 90 + text_h + 16, 980, attr_h, ctx, hi=24, lo=14, where="attribution"))
            if rest:
                got, _ = stack(rest, 150, 640 - rest_h, 980, rest_h, ctx, smax=20, smin=13)
                boxes += got
    else:  # bullets, two_column, image_text, chart (and anything unknown)
        if title:
            boxes.append(title_box(title, MARGIN_X, 40, 1136, 88, ctx, hi=40, lo=22))
            boxes.append(Box("rect", MARGIN_X, 138, 72, 5, fill="accent"))
        top = 168
        if subtitle:
            boxes.append(plain_box(subtitle, MARGIN_X, 154, 1136, 32, ctx, hi=20, lo=14, where="subtitle"))
            top = 204
        elif not title:
            top = 60
        region_h = CONTENT_BOTTOM - top
        if layout == "two_column" and not any(b.get("type") == "columns" for b in blocks) and len(blocks) >= 2:
            half = (len(blocks) + 1) // 2
            left, right = blocks[:half], blocks[half:]
            cw = 548
            s = min(stack_size(left, cw, region_h, ctx, BODY_MAX, 16), stack_size(right, cw, region_h, ctx, BODY_MAX, 16))
            got, o1 = stack(left, MARGIN_X, top, cw, region_h, ctx, smax=s, smin=s, where="left column")
            got2, o2 = stack(right, MARGIN_X + cw + 40, top, cw, region_h, ctx, smax=s, smin=s, where="right column")
            boxes += got + got2
        elif layout == "image_text":
            images = [b for b in blocks if b.get("type") == "image"]
            others = [b for b in blocks if b.get("type") != "image"]
            if images and others:
                got, _ = stack(images[:1], MARGIN_X, top, 540, region_h, ctx, where="image")
                got2, _ = stack(others, MARGIN_X + 580, top, 556, region_h, ctx, smax=26, smin=15)
                boxes += got + got2
            else:
                got, _ = stack(blocks, MARGIN_X, top, 1136, region_h, ctx, smax=BODY_MAX)
                boxes += got
        elif layout == "chart":
            charts = [b for b in blocks if b.get("type") == "chart"]
            others = [b for b in blocks if b.get("type") != "chart"]
            if charts and others:
                got, _ = stack(charts[:1], MARGIN_X, top, 760, region_h, ctx, where="chart")
                got2, _ = stack(others, MARGIN_X + 800, top, 336, region_h, ctx, smax=24, smin=14)
                boxes += got + got2
            else:
                got, _ = stack(blocks, MARGIN_X, top, 1136, region_h, ctx, smax=BODY_MAX)
                boxes += got
        else:
            got, _ = stack(blocks, MARGIN_X, top, 1136, region_h, ctx, smax=BODY_MAX)
            boxes += got
        boxes += _footer(deck_title, number, total, ctx)

    return Plan(boxes=boxes, overflow=bool(ctx.overflow_where), overflow_where=list(ctx.overflow_where))
