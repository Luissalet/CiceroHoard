"""Deck review: text that will not fit, over-long bullets, numbers that no source contains, missing notes and more.

Pure functions over the deck as the API returns it. The number check is what keeps a generated deck honest: every
figure on a slide must appear somewhere in the deck's sources (or in the brief the person wrote).
"""

from __future__ import annotations

import re
from typing import Any, Callable, Iterable, Optional

from .layouts import build_plan
from .themes import get_theme

AssetLookup = Callable[[str], Optional[dict[str, Any]]]

CHAR_BUDGET = {"title": 240, "section": 220, "bullets": 700, "two_column": 620, "image_text": 460, "quote": 320, "chart": 280, "closing": 440}
MAX_BULLETS = 6
MAX_BULLET_CHARS = 110

_NUM = re.compile(r"(?<![\w.,])(\d[\d.,  ]*\d|\d)(\s?%)?")

MSG = {
    "es": {
        "no_slides": "La presentación aún no tiene diapositivas.",
        "overflow": "El texto no cabe en «{where}» ni con la letra más pequeña.",
        "overflow_risk": "Mucho texto para este diseño ({chars} caracteres, presupuesto {budget}): puede no caber.",
        "too_many_bullets": "Más de {max} viñetas en un bloque ({n}).",
        "long_bullet": "Una viñeta tiene {n} caracteres (máximo recomendado {max}).",
        "unsourced_numbers": "Cifras que no aparecen en ninguna fuente: {numbers}.",
        "missing_notes": "Sin notas del orador.",
        "not_approved": "Sin aprobar.",
        "empty_slide": "La diapositiva está vacía.",
        "chart_mismatch": "La serie «{name}» tiene {n} valores y hay {cats} categorías.",
        "chart_empty": "El gráfico no tiene categorías o series.",
        "chart_pie_series": "Un gráfico circular solo usa la primera serie.",
        "image_missing": "Una imagen de la diapositiva ya no existe.",
        "image_prompt_only": "Hay una descripción de imagen pero ninguna imagen.",
        "layout_content": "El diseño «{layout}» espera un bloque de tipo {expected}.",
        "unsourced_chart": "Valores del gráfico que no aparecen en ninguna fuente: {numbers}.",
    },
    "en": {
        "no_slides": "The presentation has no slides yet.",
        "overflow": "The text does not fit in \"{where}\" even at the smallest font size.",
        "overflow_risk": "A lot of text for this layout ({chars} characters, budget {budget}): it may not fit.",
        "too_many_bullets": "More than {max} bullets in one block ({n}).",
        "long_bullet": "A bullet has {n} characters (recommended maximum {max}).",
        "unsourced_numbers": "Figures that appear in no source: {numbers}.",
        "missing_notes": "No speaker notes.",
        "not_approved": "Not approved.",
        "empty_slide": "The slide is empty.",
        "chart_mismatch": "Series \"{name}\" has {n} values and there are {cats} categories.",
        "chart_empty": "The chart has no categories or series.",
        "chart_pie_series": "A pie chart only uses the first series.",
        "image_missing": "An image on this slide no longer exists.",
        "image_prompt_only": "There is an image description but no image.",
        "layout_content": "The \"{layout}\" layout expects a block of type {expected}.",
        "unsourced_chart": "Chart values that appear in no source: {numbers}.",
    },
}


# ---------------- numbers ----------------

def number_variants(token: str) -> frozenset[float]:
    """Every value a printed number can mean: ``1.234`` is 1234 or 1.234, ``1,5`` is 1.5, ``1.234,5`` is 1234.5."""
    t = token.replace(" ", "").replace(" ", "").strip(".,")
    if not t:
        return frozenset()
    dots, commas = t.count("."), t.count(",")
    values: set[float] = set()

    def add(text: str) -> None:
        try:
            values.add(round(float(text), 6))
        except ValueError:
            pass

    if dots and commas:
        last = max(t.rfind("."), t.rfind(","))
        intpart = re.sub(r"[.,]", "", t[:last])
        add(f"{intpart}.{t[last + 1:]}")
    elif dots or commas:
        sep = "." if dots else ","
        count = t.count(sep)
        head, _, tail = t.rpartition(sep)
        if count > 1:
            add(t.replace(sep, ""))
        elif len(tail) == 3 and 1 <= len(head) <= 3:
            add(head + tail)  # 1.234 -> 1234
            add(head + "." + tail)  # or 1.234 as a decimal
        else:
            add(head + "." + tail)
    else:
        add(t)
    return frozenset(values)


def significant_numbers(text: str) -> list[tuple[str, frozenset[float]]]:
    """(printed form, possible values) for each number worth checking: 2+ digits, a decimal, or a percentage."""
    out: list[tuple[str, frozenset[float]]] = []
    for m in _NUM.finditer(text or ""):
        raw = m.group(1)
        digits = re.sub(r"\D", "", raw)
        if len(digits) >= 2 or m.group(2) or re.search(r"[.,]\d", raw):
            variants = number_variants(raw)
            if variants:
                out.append((raw + ("%" if m.group(2) else ""), variants))
    return out


def all_number_values(texts: Iterable[str]) -> set[float]:
    """Every number in the texts (also single digits): the reference set a slide number is looked up in."""
    values: set[float] = set()
    for text in texts:
        for m in _NUM.finditer(text or ""):
            values |= number_variants(m.group(1))
    return values


def unsourced(text: str, reference: set[float]) -> list[str]:
    seen: list[str] = []
    for printed, variants in significant_numbers(text):
        if not (variants & reference) and printed not in seen:
            seen.append(printed)
    return seen


def chart_values_unsourced(block: dict[str, Any], reference: set[float]) -> list[str]:
    bad: list[str] = []
    for s in block.get("series", []):
        for v in s.get("values", []):
            if round(float(v), 6) not in reference:
                text = f"{v:g}"
                if text not in bad:
                    bad.append(text)
    return bad


# ---------------- slide text ----------------

def slide_text_parts(slide: dict[str, Any]) -> list[str]:
    parts = [slide.get("title") or "", slide.get("subtitle") or ""]
    for b in slide.get("blocks", []):
        t = b.get("type")
        if t == "bullets":
            parts += b.get("items", [])
        elif t == "text":
            parts.append(b.get("text", ""))
        elif t == "quote":
            parts += [b.get("text", ""), b.get("attribution") or ""]
        elif t == "columns":
            parts += [b.get("left_title") or "", b.get("right_title") or ""] + b.get("left", []) + b.get("right", [])
        elif t == "chart":
            parts += [b.get("title") or ""] + list(b.get("categories", []))
        elif t == "image":
            parts.append(b.get("caption") or "")
    return [p for p in parts if p]


def slide_char_count(slide: dict[str, Any]) -> int:
    total = 0
    for b in slide.get("blocks", []):
        t = b.get("type")
        if t == "bullets":
            total += sum(len(i) for i in b.get("items", []))
        elif t == "text":
            total += len(b.get("text", ""))
        elif t == "quote":
            total += len(b.get("text", "")) + len(b.get("attribution") or "")
        elif t == "columns":
            total += sum(len(i) for i in b.get("left", []) + b.get("right", [])) + len(b.get("left_title") or "") + len(b.get("right_title") or "")
        elif t == "chart":
            total += len(b.get("title") or "")
    return total + len(slide.get("title") or "") + len(slide.get("subtitle") or "")


def _is_empty(slide: dict[str, Any]) -> bool:
    if (slide.get("layout") in ("title", "section", "closing")) and slide.get("title"):
        return False
    for b in slide.get("blocks", []):
        t = b.get("type")
        if t == "bullets" and b.get("items"):
            return False
        if t == "text" and (b.get("text") or "").strip():
            return False
        if t == "quote" and (b.get("text") or "").strip():
            return False
        if t == "columns" and (b.get("left") or b.get("right")):
            return False
        if t == "chart" and b.get("series"):
            return False
        if t == "image":
            return False
    return True


EXPECTED_BLOCK = {"quote": "quote", "chart": "chart", "two_column": "columns", "image_text": "image"}


def check_deck(deck: dict[str, Any], sources: list[dict[str, Any]], assets: AssetLookup) -> list[dict[str, Any]]:
    lang = deck.get("language", "es")
    m = MSG.get(lang, MSG["es"])
    theme = get_theme(deck.get("theme"))
    issues: list[dict[str, Any]] = []
    slides = deck.get("slides", [])

    def add(slide: Optional[dict[str, Any]], kind: str, severity: str, key: str, **fmt: Any) -> None:
        issues.append({"slide_id": slide["id"] if slide else None, "kind": kind, "severity": severity, "message": m[key].format(**fmt),
                       "position": slide["position"] if slide else None})

    if not slides:
        add(None, "no_slides", "info", "no_slides")
        return issues
    reference: Optional[set[float]] = None
    if sources:
        own = [deck.get("title", ""), deck.get("brief", ""), deck.get("audience", ""), deck.get("tone", "")]
        reference = all_number_values([s["text"] for s in sources] + own)
    for slide in slides:
        if _is_empty(slide):
            add(slide, "empty_slide", "warning", "empty_slide")
        plan = build_plan(slide, deck_title=deck.get("title", ""), theme=theme, number=slide["position"], total=len(slides), lang=lang, assets=assets)
        if plan.overflow:
            add(slide, "overflow", "warning", "overflow", where=", ".join(dict.fromkeys(plan.overflow_where)))
        else:
            budget = CHAR_BUDGET.get(slide.get("layout"), 700)
            chars = slide_char_count(slide)
            if chars > budget:
                add(slide, "overflow_risk", "warning", "overflow_risk", chars=chars, budget=budget)
        for b in slide.get("blocks", []):
            t = b.get("type")
            lists = [b.get("items", [])] if t == "bullets" else [b.get("left", []), b.get("right", [])] if t == "columns" else []
            for items in lists:
                if len(items) > MAX_BULLETS:
                    add(slide, "too_many_bullets", "warning", "too_many_bullets", max=MAX_BULLETS, n=len(items))
                for item in items:
                    if len(item) > MAX_BULLET_CHARS:
                        add(slide, "long_bullet", "warning", "long_bullet", n=len(item), max=MAX_BULLET_CHARS)
                        break
            if t == "chart":
                cats, series = b.get("categories", []), b.get("series", [])
                if not cats or not series:
                    add(slide, "chart_empty", "warning", "chart_empty")
                else:
                    for s in series:
                        if len(s.get("values", [])) != len(cats):
                            add(slide, "chart_mismatch", "warning", "chart_mismatch", name=s.get("name") or "?", n=len(s.get("values", [])), cats=len(cats))
                    if b.get("chart") == "pie" and len(series) > 1:
                        add(slide, "chart_pie_series", "info", "chart_pie_series")
                    if reference is not None:
                        bad = chart_values_unsourced(b, reference)
                        if bad:
                            add(slide, "unsourced_chart", "warning", "unsourced_chart", numbers=", ".join(bad[:8]))
            if t == "image" and assets(b.get("asset_id", "")) is None:
                add(slide, "image_missing", "warning", "image_missing")
        expected = EXPECTED_BLOCK.get(slide.get("layout", ""))
        if expected and not any(b.get("type") == expected for b in slide.get("blocks", [])):
            if expected == "image" and slide.get("image_prompt"):
                add(slide, "image_prompt_only", "info", "image_prompt_only")
            elif not _is_empty(slide) or expected != "image":
                if not (expected == "columns" and len(slide.get("blocks", [])) >= 2):
                    add(slide, "layout_content", "info", "layout_content", layout=slide["layout"], expected=expected)
        if reference is not None:
            bad_numbers = unsourced(" \n".join(slide_text_parts(slide)), reference)
            if bad_numbers:
                add(slide, "unsourced_numbers", "warning", "unsourced_numbers", numbers=", ".join(bad_numbers[:8]))
        if not (slide.get("notes") or "").strip():
            add(slide, "missing_notes", "info", "missing_notes")
        if slide.get("status") != "approved":
            add(slide, "not_approved", "info", "not_approved")
    return issues
