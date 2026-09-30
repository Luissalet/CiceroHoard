"""Markdown export: slides separated by ``---``, speaker notes as HTML comments, charts as tables."""

from __future__ import annotations

from typing import Any

from .layouts import fmt_num

LABELS = {
    "es": {"image": "imagen", "notes": "Notas", "sources": "Fuentes"},
    "en": {"image": "image", "notes": "Notes", "sources": "Sources"},
}


def _cell(text: Any) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def _chart_table(block: dict[str, Any], lang: str) -> list[str]:
    cats = block.get("categories", [])
    series = block.get("series", [])
    lines: list[str] = []
    if block.get("title"):
        lines += [f"**{block['title']}**", ""]
    lines.append("| | " + " | ".join(_cell(s.get("name") or "") for s in series) + " |")
    lines.append("| --- |" + " --- |" * len(series))
    for i, cat in enumerate(cats):
        row = []
        for s in series:
            vals = s.get("values", [])
            row.append(fmt_num(vals[i], lang) if i < len(vals) else "")
        lines.append(f"| {_cell(cat)} | " + " | ".join(row) + " |")
    return lines


def _comment(text: str) -> str:
    """Text safe inside an HTML comment: no ``--`` sequences."""
    return text.replace("--", "- -").replace(">", "&gt;")


def build_markdown(deck: dict[str, Any]) -> bytes:
    lang = deck.get("language", "es")
    labels = LABELS.get(lang, LABELS["es"])
    out: list[str] = []
    slides = deck.get("slides", [])
    for index, s in enumerate(slides):
        lines: list[str] = []
        layout = s.get("layout")
        if s.get("title"):
            lines.append(f"# {s['title']}")
        if s.get("subtitle"):
            lines += ["", f"## {s['subtitle']}" if layout in ("title", "section") else f"*{s['subtitle']}*"]
        for block in s.get("blocks", []):
            kind = block.get("type")
            lines.append("")
            if kind == "bullets":
                lines += [f"- {item}" for item in block.get("items", [])]
            elif kind == "text":
                lines.append(block.get("text", ""))
            elif kind == "quote":
                lines += [f"> {ln}" for ln in (block.get("text") or "").splitlines() or [""]]
                if block.get("attribution"):
                    lines += [">", f"> \u2014 {block['attribution']}"]
            elif kind == "image":
                caption = block.get("caption") or ""
                lines.append(f"*[{labels['image']}{': ' + caption if caption else ''}]*")
            elif kind == "chart":
                lines += _chart_table(block, lang)
            elif kind == "columns":
                for side in ("left", "right"):
                    if block.get(f"{side}_title"):
                        lines += [f"**{block[f'{side}_title']}**", ""]
                    lines += [f"- {item}" for item in block.get(side, [])]
                    lines.append("")
                if lines and lines[-1] == "":
                    lines.pop()
        if s.get("notes"):
            lines += ["", f"<!-- {labels['notes']}: {_comment(s['notes'])} -->"]
        out.append("\n".join(lines).strip("\n"))
        if index < len(slides) - 1:
            out.append("\n---\n")
    return ("\n".join(out).strip() + "\n").encode("utf-8")
