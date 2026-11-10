"""Import an existing PPTX as a new, editable deck: each slide's title, text, tables, native charts, pictures and speaker notes become
Cicero blocks, so the deck can be re-themed, reviewed, regenerated slide by slide and exported again.

What is read: title and subtitle placeholders (or the topmost, largest text when there is none), every other text frame as bullets
(paragraph by paragraph, one level deep is flattened), tables (first row as headers), column/bar/line/pie/doughnut charts with their
categories and series, pictures (PNG, JPEG, WEBP, BMP, GIF and TIFF are converted to PNG) and the notes page. What is not: shapes'
positions, the original theme, animations, SmartArt geometry (its text is kept), embedded media and charts of other kinds (their data is
kept as a table when it can be read). The file is also added as a source, so every figure on the imported slides has its evidence.
"""
from __future__ import annotations

import io
import re
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field

from . import decks as store
from .errors import CiceroError, Refused
from .models import MAX_BLOCKS, MAX_ITEM_CHARS, MAX_ITEMS, MAX_SLIDES, MAX_TEXT_CHARS, DeckCreate

SKIP_PLACEHOLDERS = {"FOOTER", "SLIDE_NUMBER", "DATE", "HEADER"}
TITLE_PLACEHOLDERS = {"TITLE", "CENTER_TITLE", "VERTICAL_TITLE"}
SUBTITLE_PLACEHOLDERS = {"SUBTITLE"}


class ImportArgs(BaseModel):
    path: Optional[str] = Field(None, max_length=1000, description="A local .pptx file to import (inside CICERO_FILE_ROOTS when set).")
    title: Optional[str] = Field(None, max_length=200, description="Title of the new deck; defaults to the first slide's title or the file name.")
    theme: Optional[str] = Field(None, max_length=40, description="Theme for the new deck (deck_theme lists them); the original look is not copied.")
    language: Optional[str] = Field(None, pattern="^(es|en)$")
    brief: str = Field("", max_length=8000)


def _clean(text: str) -> str:
    return re.sub(r"[ \t ]+", " ", (text or "").replace("\v", " ")).strip()


def _ph_type(shape: Any) -> Optional[str]:
    try:
        return shape.placeholder_format.type.name if shape.is_placeholder else None
    except (AttributeError, ValueError):
        return None


def _walk(shapes: Any):
    for shape in shapes:
        if shape.shape_type is not None and shape.shape_type == 6:  # group
            yield from _walk(shape.shapes)
        else:
            yield shape


def _font_size(shape: Any) -> float:
    sizes = [r.font.size.pt for p in shape.text_frame.paragraphs for r in p.runs if r.font.size]
    return max(sizes) if sizes else 18.0


def _chart_block(shape: Any) -> Optional[dict[str, Any]]:
    chart = shape.chart
    name = chart.chart_type.name if chart.chart_type is not None else ""
    kind = "pie" if "PIE" in name or "DOUGHNUT" in name else "line" if "LINE" in name else "bar_horizontal" if name.startswith("BAR") else "bar"
    try:
        plot = chart.plots[0]
        cats = [str(c) for c in plot.categories]
        series = []
        for s in list(plot.series)[:6]:
            values = [None if v is None else float(v) for v in s.values][: len(cats)]
            series.append({"name": _clean(s.name or "")[:80], "values": values})
    except Exception:  # charts python-pptx cannot read (scatter, combo): nothing reliable to keep
        return None
    if not cats or not series or not any(v is not None for s in series for v in s["values"]):
        return None
    block: dict[str, Any] = {"type": "chart", "chart": kind, "categories": cats[:2000], "series": series}
    if chart.has_title and chart.chart_title.has_text_frame and _clean(chart.chart_title.text_frame.text):
        block["title"] = _clean(chart.chart_title.text_frame.text)[:200]
    return block


def _table_block(shape: Any) -> Optional[dict[str, Any]]:
    rows = [[_clean(c.text)[:200] for c in r.cells] for r in shape.table.rows]
    rows = [r[:10] for r in rows if any(r)]
    if len(rows) < 2:
        return None
    return {"type": "table", "headers": rows[0], "rows": rows[1:31]}


def _picture(svc: Any, deck_id: str, shape: Any) -> Optional[str]:
    try:
        image = shape.image
    except Exception:
        return None
    data, ext = image.blob, (image.ext or "").lower()
    if ext not in ("png", "jpg", "jpeg", "webp"):
        try:
            from PIL import Image
            out = io.BytesIO()
            Image.open(io.BytesIO(data)).save(out, format="PNG")
            data, ext = out.getvalue(), "png"
        except Exception:
            return None
    try:
        return store.add_asset(svc, deck_id, data, f"imported.{ext}")["asset_id"]
    except CiceroError:
        return None


def _bullet_blocks(paragraphs: list[str]) -> list[dict[str, Any]]:
    items = [p[:MAX_ITEM_CHARS] for p in paragraphs if p]
    if len(items) == 1 and len(items[0]) > 160:
        return [{"type": "text", "text": items[0][:MAX_TEXT_CHARS]}]
    return [{"type": "bullets", "items": items[i:i + MAX_ITEMS]} for i in range(0, len(items), MAX_ITEMS)]


def read_slide(svc: Any, deck_id: str, slide: Any, index: int, total: int, height: int = 0) -> dict[str, Any]:
    title = subtitle = ""
    texts: list[tuple[float, float, Any]] = []
    visuals: list[dict[str, Any]] = []
    images: list[str] = []
    for shape in _walk(slide.shapes):
        ph = _ph_type(shape)
        if ph in SKIP_PLACEHOLDERS:
            continue
        if getattr(shape, "has_chart", False) and shape.has_chart:
            block = _chart_block(shape)
            if block:
                visuals.append(block)
            continue
        if getattr(shape, "has_table", False) and shape.has_table:
            block = _table_block(shape)
            if block:
                visuals.append(block)
            continue
        if shape.shape_type == 13 or (ph == "PICTURE" and hasattr(shape, "image")):
            asset = _picture(svc, deck_id, shape)
            if asset:
                images.append(asset)
            continue
        if not getattr(shape, "has_text_frame", False) or not _clean(shape.text_frame.text):
            continue
        # A footer drawn as a plain text box (deck name, "3 / 10") in the bottom strip in small type is not content.
        if height and (shape.top or 0) > height * 0.9 and _font_size(shape) <= 12:
            continue
        if ph in TITLE_PLACEHOLDERS and not title:
            title = _clean(shape.text_frame.text)
        elif ph in SUBTITLE_PLACEHOLDERS and not subtitle:
            subtitle = _clean(shape.text_frame.text)
        else:
            texts.append((shape.top or 0, -_font_size(shape), shape))
    texts.sort(key=lambda t: (t[0], t[1]))
    if not title and texts:  # no title placeholder: the topmost text in the largest type is the title
        biggest = min(texts, key=lambda t: (t[1], t[0]))
        if -biggest[1] >= 24 or len(texts) == 1:
            title = _clean(biggest[2].text_frame.text)
            texts.remove(biggest)
    paragraphs = [_clean(p.text) for _, _, s in texts for p in s.text_frame.paragraphs if _clean(p.text)]
    notes = ""
    if slide.has_notes_slide:
        notes = _clean(slide.notes_slide.notes_text_frame.text if slide.notes_slide.notes_text_frame else "")[:6000]
    blocks = visuals[:]
    blocks += [{"type": "image", "asset_id": a} for a in images[:2]]
    blocks += _bullet_blocks(paragraphs)
    blocks = blocks[:MAX_BLOCKS]
    has = {b["type"] for b in blocks}
    if index == 0 and not visuals and not images:
        layout = "title"
    elif not blocks:
        layout = "section"
    elif "chart" in has:
        layout = "chart" if has & {"bullets", "text"} else "evidence"
    elif "table" in has:
        layout = "table"
    elif "image" in has:
        layout = "image_text" if has & {"bullets", "text"} else "image_full"
    else:
        layout = "bullets"
    if index == total - 1 and index > 0 and layout in ("bullets", "section") and len(paragraphs) <= 3:
        layout = "closing"
    return {"layout": layout, "title": title[:200] or f"Diapositiva {index + 1}", "subtitle": subtitle[:300] or None,
            "blocks": blocks, "notes": notes}


def _resolve(svc: Any, path: str) -> Path:
    p = Path(path).expanduser()
    try:
        p = p.resolve(strict=True)
    except OSError:
        raise CiceroError(f"File not found: {path}") from None
    if not p.is_file() or p.suffix.lower() != ".pptx":
        raise CiceroError("Choose a .pptx presentation.")
    roots = svc.config.file_roots
    if roots and not any(root.resolve() in p.parents for root in roots):
        raise Refused("That file is outside the folders allowed by CICERO_FILE_ROOTS.")
    return p


def import_bytes(svc: Any, data: bytes, filename: str, *, title: Optional[str] = None, theme: Optional[str] = None,
                 language: Optional[str] = None, brief: str = "") -> dict[str, Any]:
    from pptx import Presentation
    if len(data) > svc.config.max_upload_bytes:
        raise CiceroError(f"The file is larger than {svc.config.max_upload_bytes // (1024 * 1024)} MB.")
    try:
        prs = Presentation(io.BytesIO(data))
    except Exception:
        raise CiceroError("The file is not a readable PPTX presentation.", code="invalid_pptx") from None
    slides = list(prs.slides)
    if not slides:
        raise CiceroError("The presentation has no slides.", code="empty_pptx")
    skipped = max(0, len(slides) - MAX_SLIDES)
    slides = slides[:MAX_SLIDES]
    first_title = ""
    for shape in _walk(slides[0].shapes):
        if _ph_type(shape) in TITLE_PLACEHOLDERS and _clean(shape.text_frame.text):
            first_title = _clean(shape.text_frame.text)
            break
    name = (title or "").strip() or first_title or Path(filename).stem or "Presentación importada"
    deck = store.create_deck(svc, DeckCreate(title=name[:200], brief=brief, language=language, theme=theme,
                                             slide_count=max(3, min(MAX_SLIDES, len(slides)))))
    deck_id = deck["id"]
    warnings: list[str] = []
    source_id = None
    try:
        source_id = store.add_source_file(svc, deck_id, data, Path(filename).name or "imported.pptx")["id"]
    except CiceroError as e:
        warnings.append(f"The file could not be added as a source: {e}")
    items = [read_slide(svc, deck_id, slide, i, len(slides), prs.slide_height or 0) for i, slide in enumerate(slides)]
    chart_source = None
    charts = [(i + 1, b) for i, item in enumerate(items) for b in item["blocks"] if b["type"] == "chart"]
    if charts:  # the slide text of a PPTX leaves chart data out: keep it as its own source so the figures have evidence
        from .layouts import fmt_num
        lang = deck["language"]
        lines = []
        for position, b in charts:
            lines.append(f"{'Diapositiva' if lang == 'es' else 'Slide'} {position}: {b.get('title') or ''}".strip())
            for s in b["series"]:
                pairs = "; ".join(f"{c}: {fmt_num(v, lang)}" for c, v in zip(b["categories"], s["values"]) if v is not None)
                lines.append(f"{s['name'] or '-'}: {pairs}")
        try:
            chart_source = store.add_source_text(svc, deck_id, "Datos de los gráficos" if lang == "es" else "Chart data", "\n".join(lines))["id"]
        except CiceroError as e:
            warnings.append(f"Chart data could not be kept as a source: {e}")
    made = []
    for i, item in enumerate(items):
        cited = [x for x in (source_id, chart_source if any(b["type"] == "chart" for b in item["blocks"]) else None) if x]
        try:
            created = store.add_slide(svc, deck_id, layout=item["layout"], title=item["title"], subtitle=item["subtitle"], blocks=item["blocks"],
                                      notes=item["notes"], sources=cited, reason="imported")
        except (CiceroError, ValueError) as e:  # a block the store refuses: keep the slide with its text only
            text = [b for b in item["blocks"] if b["type"] in ("bullets", "text")]
            warnings.append(f"Slide {i + 1}: {str(e)[:160]}; kept its text only.")
            created = store.add_slide(svc, deck_id, layout="bullets", title=item["title"], subtitle=item["subtitle"], blocks=text,
                                      notes=item["notes"], sources=[source_id] if source_id else [], reason="imported")
        made.append(created)
    if skipped:
        warnings.append(f"Only the first {MAX_SLIDES} slides were imported; {skipped} more were left out.")
    no_notes = [s["position"] for s in made if not (s.get("notes") or "").strip()]
    svc.emit("cicero.deck.imported", {"id": deck_id, "ref": store.deck_ref(deck_id), "slides": len(made)})
    return {"deck": store.deck_view(svc, deck_id), "imported_slides": len(made), "source_id": source_id,
            "charts": sum(1 for s in made for b in s["blocks"] if b["type"] == "chart"),
            "tables": sum(1 for s in made for b in s["blocks"] if b["type"] == "table"),
            "images": sum(1 for s in made for b in s["blocks"] if b["type"] == "image"),
            "slides_without_notes": no_notes, "warnings": warnings}


def run(svc: Any, a: ImportArgs) -> dict[str, Any]:
    if not a.path:
        raise CiceroError("Give the path of a local .pptx file.")
    p = _resolve(svc, a.path)
    res = import_bytes(svc, p.read_bytes(), p.name, title=a.title, theme=a.theme, language=a.language, brief=a.brief)
    deck = res.pop("deck")
    return {**res, "deck_id": deck["id"], "title": deck["title"], "theme": deck["theme"],
            "slides": [{"id": s["id"], "position": s["position"], "layout": s["layout"], "title": s["title"],
                        "blocks": [b["type"] for b in s["blocks"]], "notes": bool(s["notes"])} for s in deck["slides"]],
            "hint": "Review with deck_check, change the look with deck_theme, rewrite one slide with slide_regenerate, export with deck_export."}
