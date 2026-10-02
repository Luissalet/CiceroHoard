"""Generation: outline and slides through the local model (Hoard Link), with a deterministic fallback.

Rules that hold for every path:
- the model is asked for JSON only; the answer is parsed and validated with pydantic, gets one repair attempt, then
  a clear error (``generation_failed``) for the outline; a slide that still fails is built by the fallback and flagged;
- source material goes into the prompt as numbered excerpts ``[S<id>]`` within a character budget, never whole documents;
- charts are only kept when every value appears in the sources (nothing is invented);
- without a reachable model the outline and the slides come from the sources or the brief by rules, and the result says
  ``"generator": "fallback"``. Regenerating one slide with feedback needs a model and refuses to pretend otherwise.
"""

from __future__ import annotations

import json
import os
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Optional

from pydantic import ValidationError

from . import decks as store
from .check import all_number_values, chart_values_unsourced
from .errors import CiceroError, GenerationFailed, ModelUnavailable
from .hoard_link.docs import chunking
from .models import GeneratedOutline, GeneratedSlide, LAYOUTS
from .util import clip, jdump, shorten

MAX_BULLETS = 6
MAX_BULLET_CHARS = 110
LANG_NAME = {"es": "Spanish (Spain)", "en": "English"}
OUTLINE_BUDGET = 9000
SLIDE_BUDGET = 5000
CHUNK = 1100

LABELS = {
    "es": {"closing": "Conclusiones y siguientes pasos", "for": "Para", "notes_points": "Puntos", "no_material": "No hay material del que partir: añade un encargo (brief) o al menos una fuente."},
    "en": {"closing": "Summary and next steps", "for": "For", "notes_points": "Points", "no_material": "There is nothing to work from: add a brief or at least one source."},
}


class ModelDown(Exception):
    """The model could not be reached (not the same as: it answered badly)."""


# ---------------- talking to the model ----------------

def chat_json(svc: Any, messages: list[dict[str, str]], parse: Callable[[Any, bool], Any], *, max_tokens: int, effort: Optional[str] = None) -> tuple[Any, Optional[str]]:
    """Ask for JSON, parse it (strict), retry once with the error, then parse leniently. Returns (value, model name)."""

    def ask(msgs: list[dict[str, str]]) -> tuple[str, Optional[str]]:
        try:
            result = svc.link_sync.chat(msgs, effort=effort or slide_effort(), max_tokens=max_tokens, temperature=0.4)
        except Exception as error:  # noqa: BLE001 - any backend failure means "no model" for the caller
            raise ModelDown(f"{type(error).__name__}: {str(error)[:200]}") from error
        text = (getattr(result, "text", "") or "").strip()
        return text, getattr(result, "model", None)

    text, model = ask(messages)
    try:
        return parse(json_from_text(text), True), model
    except (ValueError, ValidationError) as first_error:
        problem = _describe(first_error)
        repair = messages + [{"role": "assistant", "content": text[:6000]},
                             {"role": "user", "content": f"That answer cannot be used: {problem}\nReturn only the corrected JSON object, with no text around it."}]
        text2, model2 = ask(repair)
        try:
            return parse(json_from_text(text2), False), model2 or model
        except (ValueError, ValidationError) as second_error:
            raise GenerationFailed(f"The model did not return valid JSON after one repair attempt: {_describe(second_error)}") from second_error


def _describe(error: Exception) -> str:
    if isinstance(error, ValidationError):
        return "; ".join(f"{'.'.join(str(p) for p in e['loc']) or 'input'}: {e['msg']}" for e in error.errors()[:6])
    return str(error)[:400]


def json_from_text(text: str) -> Any:
    """The JSON value in a model answer: bare, fenced in a code block, or surrounded by prose."""
    text = (text or "").strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.S | re.I)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except ValueError:
        pass
    starts = [i for i in (text.find("{"), text.find("[")) if i != -1]
    if not starts:
        raise ValueError("no JSON found in the answer")
    start = min(starts)
    opener = text[start]
    closer = "}" if opener == "{" else "]"
    end = text.rfind(closer)
    if end <= start:
        raise ValueError("the JSON in the answer is not closed")
    try:
        return json.loads(text[start: end + 1])
    except ValueError as error:
        raise ValueError(f"invalid JSON: {error}") from error


# ---------------- source excerpts ----------------

def _fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in text if not unicodedata.combining(c))


def chunk_text(text: str, size: int = CHUNK) -> list[str]:
    """Chunks of about ``size`` characters (paragraph and sentence boundaries) from the shared Hoard Link chunker, without overlap
    (an excerpt that repeated its neighbour would waste the model's context)."""
    return [c.text.strip() for c in chunking.chunk_text(text, size=size, overlap=0) if c.text.strip()]


def excerpts(sources: list[dict[str, Any]], query: str, budget: int) -> tuple[str, list[int]]:
    """Numbered excerpts ``[S<id>] ...`` within ``budget`` characters: the chunks that best match ``query``,
    always including the opening chunk of each source, in source order."""
    if not sources:
        return "", []
    terms = {w for w in re.findall(r"\w{4,}", _fold(query))}
    scored: list[tuple[float, int, int, str]] = []
    for s in sources:
        for i, chunk in enumerate(chunk_text(s["text"])):
            words = re.findall(r"\w{4,}", _fold(chunk))
            hits = sum(min(words.count(t), 3) for t in terms) if terms else 0
            bonus = 5.0 if i == 0 else 0.0
            spread = -0.001 * i  # earlier chunks win ties
            scored.append((hits + bonus + spread, s["id"], i, chunk))
    scored.sort(key=lambda x: -x[0])
    picked: list[tuple[int, int, str]] = []
    used = 0
    per_cap = max(400, budget // max(1, len(sources)) * 2)
    per_source: dict[int, int] = {}
    for _score, sid, i, chunk in scored:
        chunk = chunk[:1400]
        if used + len(chunk) > budget:
            continue
        if per_source.get(sid, 0) + len(chunk) > per_cap and i != 0:
            continue
        picked.append((sid, i, chunk))
        per_source[sid] = per_source.get(sid, 0) + len(chunk)
        used += len(chunk) + 8
    picked.sort()
    text = "\n\n".join(f"[S{sid}] {chunk}" for sid, _i, chunk in picked)
    return text, sorted({sid for sid, _i, _c in picked})


# ---------------- prompts ----------------

BLOCK_SPEC = """Block types (use only these):
{"type":"bullets","items":["..."]}            // at most 6 items, each at most 110 characters
{"type":"text","text":"..."}
{"type":"quote","text":"...","attribution":"..."}   // only a quote that appears in the sources
{"type":"columns","left_title":"...","left":["..."],"right_title":"...","right":["..."]}
{"type":"chart","chart":"bar|line|pie","title":"...","categories":["..."],"series":[{"name":"...","values":[1,2]}]}   // only with numbers that appear in the sources"""

LAYOUT_SPEC = "Layouts: title, section, bullets, two_column, image_text, quote, chart, closing."


def _deck_header(deck: dict[str, Any]) -> str:
    lines = [f"Language of the deck: {LANG_NAME.get(deck['language'], 'English')}.", f"Title: {deck['title']}"]
    if deck.get("brief"):
        lines.append(f"Brief: {clip(deck['brief'], 3000)}")
    if deck.get("audience"):
        lines.append(f"Audience: {deck['audience']}")
    if deck.get("tone"):
        lines.append(f"Tone: {deck['tone']}")
    return "\n".join(lines)


SYSTEM = ("You write presentation content. Answer with one JSON object and nothing else: no explanations, no code fences. "
          "State only facts that are in the brief or in the numbered source excerpts. Never invent figures, dates, names or quotes.")


def outline_messages(deck: dict[str, Any], excerpt_text: str) -> list[dict[str, str]]:
    n = deck["slide_count"]
    user = (f"{_deck_header(deck)}\nNumber of slides: exactly {n} (the first is the title slide, the last is the closing slide).\n\n"
            f"Source excerpts:\n{excerpt_text or '(no sources: use only the brief)'}\n\n"
            f'Return {{"items":[{{"title":"...","purpose":"what this slide must achieve","points":["2 to 5 short points"],"layout_hint":"one of the layouts or null"}}]}}.\n'
            f"{LAYOUT_SPEC} Use layout_hint \"title\" for the first item and \"closing\" for the last. Order the items as a talk: context, "
            "development, conclusion. Write titles and points in the deck language.")
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]


def slide_messages(deck: dict[str, Any], item: dict[str, Any], position: int, total: int, neighbours: tuple[str, str], excerpt_text: str,
                   *, current: Optional[dict[str, Any]] = None, feedback: str = "") -> list[dict[str, str]]:
    parts = [_deck_header(deck), f"This is slide {position} of {total}. Previous slide: {neighbours[0] or '-'}. Next slide: {neighbours[1] or '-'}.",
             "Outline item for this slide:", jdump(item) if item else "(none: a slide added by hand)"]
    if current is not None:
        parts += ["Current content of the slide:", jdump({k: current.get(k) for k in ("layout", "title", "subtitle", "blocks", "notes")})]
    if feedback:
        parts += [f"Change requested by the person: {feedback}"]
    parts += ["", f"Source excerpts:\n{excerpt_text or '(no sources: use only the brief and the outline)'}", "",
              'Return {"layout":"...","title":"...","subtitle":null,"blocks":[...],"notes":"2 to 5 sentences the speaker can say to this audience, in a plain spoken register without ceremonial forms of address unless the brief asks for them","sources":[ids of the excerpts used, e.g. [1,3]],"image_prompt":null}.',
              LAYOUT_SPEC, BLOCK_SPEC,
              "Rules: honour the outline item's layout_hint when it fits; a bullets slide has one bullets block; use a chart only when the excerpts contain the "
              "numbers; write everything in the deck language; keep bullets short; for image_text slides add an image_prompt describing the picture."]
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": "\n".join(parts)}]


# ---------------- parsing and enforcement ----------------

def parse_outline(data: Any, strict: bool, slide_count: int, warnings: list[str]) -> list[dict[str, Any]]:
    if isinstance(data, list):
        data = {"items": data}
    if isinstance(data, dict) and "items" not in data:
        for key in ("outline", "slides"):
            if isinstance(data.get(key), list):
                data = {"items": data[key]}
                break
    outline = GeneratedOutline.model_validate(data)
    items = [i.model_dump() for i in outline.items]
    if strict and len(items) != slide_count:
        raise ValueError(f"expected {slide_count} items, got {len(items)}")
    if len(items) > slide_count:
        warnings.append(f"The model returned {len(items)} outline items; kept the first {slide_count - 1} and the last one.")
        items = items[: slide_count - 1] + [items[-1]]
    elif len(items) < slide_count:
        warnings.append(f"The model returned {len(items)} outline items instead of {slide_count}.")
    if items:
        items[0]["layout_hint"] = "title"
        if len(items) > 1:
            items[-1]["layout_hint"] = "closing"
    for it in items:
        it["points"] = it["points"][:5]
    return items


def _slide_problems(draft: GeneratedSlide) -> list[str]:
    problems: list[str] = []
    if not draft.title.strip():
        problems.append("title is empty")
    for b in draft.blocks:
        if b.type == "bullets":
            if len(b.items) > MAX_BULLETS:
                problems.append(f"a bullets block has {len(b.items)} items (maximum {MAX_BULLETS})")
            if any(len(i) > MAX_BULLET_CHARS for i in b.items):
                problems.append(f"a bullet is longer than {MAX_BULLET_CHARS} characters")
    types = {b.type for b in draft.blocks}
    if draft.layout == "chart" and "chart" not in types:
        problems.append("layout chart needs a chart block")
    if draft.layout == "quote" and "quote" not in types:
        problems.append("layout quote needs a quote block")
    return problems


def finish_slide(draft: GeneratedSlide, *, strict: bool, source_ids: set[int], reference: Optional[set[float]], warnings: list[str],
                 fallback_title: str = "") -> dict[str, Any]:
    """Enforce the rules on a model slide: strict mode raises (so the model can repair it), lenient mode repairs mechanically."""
    problems = _slide_problems(draft)
    if strict and problems:
        raise ValueError("; ".join(problems))
    blocks: list[dict[str, Any]] = []
    for b in draft.blocks:
        data = b.model_dump(exclude_none=True)
        t = data["type"]
        if t == "image":
            continue  # the model has no picture files; it describes them in image_prompt instead
        if t == "bullets":
            items = [shorten(i, MAX_BULLET_CHARS) for i in data["items"]][:MAX_BULLETS]
            if len(data["items"]) > MAX_BULLETS or any(len(i) > MAX_BULLET_CHARS for i in data["items"]):
                warnings.append(f"Slide \"{clip(draft.title, 40)}\": bullets were shortened to fit the limits.")
            if not items:
                continue
            data["items"] = items
        if t == "columns":
            data["left"] = [shorten(i, MAX_BULLET_CHARS) for i in data["left"]][:MAX_BULLETS]
            data["right"] = [shorten(i, MAX_BULLET_CHARS) for i in data["right"]][:MAX_BULLETS]
        if t == "chart":
            ok = bool(data.get("categories")) and bool(data.get("series")) and all(len(s["values"]) == len(data["categories"]) for s in data["series"])
            if not ok:
                warnings.append(f"Slide \"{clip(draft.title, 40)}\": a chart with inconsistent data was dropped.")
                continue
            if reference is None or chart_values_unsourced(data, reference):
                warnings.append(f"Slide \"{clip(draft.title, 40)}\": a chart was dropped because its values are not in the sources.")
                continue
        blocks.append(data)
    layout = draft.layout
    if layout == "chart" and not any(b["type"] == "chart" for b in blocks):
        layout = "bullets"
    if layout == "quote" and not any(b["type"] == "quote" for b in blocks):
        layout = "bullets"
    if layout == "two_column" and not any(b["type"] == "columns" for b in blocks) and len(blocks) < 2:
        layout = "bullets"
    return {"layout": layout, "title": draft.title.strip() or fallback_title, "subtitle": (draft.subtitle or None), "blocks": blocks,
            "notes": draft.notes.strip(), "sources": [i for i in draft.sources if i in source_ids],
            "image_prompt": (draft.image_prompt or None) if layout == "image_text" or draft.image_prompt else None}


# ---------------- deterministic fallback ----------------

_HEADING = re.compile(r"^(#{1,4})\s+(.+?)\s*#*$")
_NUMBERED = re.compile(r"^(\d{1,2}[.)]|[IVX]{1,4}[.)])\s+(\S.{2,70})$")


def _sentences(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", text).strip()
    parts = re.split(r"(?<=[.!?…])\s+(?=[A-ZÁÉÍÓÚÑ¿¡0-9\"«(])", text)
    return [p.strip() for p in parts if len(p.strip()) > 2]


def _looks_like_heading(line: str) -> bool:
    s = line.strip()
    if not (2 < len(s) <= 80) or s.endswith((".", ",", ";", ":")) and not s.endswith("?"):
        return False
    letters = [c for c in s if c.isalpha()]
    if not letters:
        return False
    return s.isupper() or bool(_NUMBERED.match(s))


def sections_from_text(text: str) -> list[dict[str, Any]]:
    """Sections (title, sentences) from headings when the text has them, else from its paragraphs."""
    lines = text.splitlines()
    sections: list[dict[str, Any]] = []
    current: Optional[dict[str, Any]] = None
    for raw in lines:
        line = raw.strip()
        if not line:
            if current is not None:
                current["body"].append("")
            continue
        m = _HEADING.match(line)
        heading = m.group(2) if m else (_NUMBERED.match(line).group(2) if _NUMBERED.match(line) else (line if _looks_like_heading(line) else None))
        if heading:
            current = {"title": heading.strip(), "body": []}
            sections.append(current)
        elif current is not None:
            current["body"].append(re.sub(r"^\s*(?:[-*•·]|\d+[.)])\s+", "", line))
        else:
            current = {"title": "", "body": [line]}
            sections.append(current)
    result: list[dict[str, Any]] = []
    for s in sections:
        body_text = " ".join(x for x in s["body"] if x)
        bullets = [x for x in s["body"] if x]
        sentences = _sentences(body_text) if body_text else []
        if s["title"] and (sentences or bullets):
            # a list body keeps its lines as points; prose is split into sentences
            points = bullets if len(bullets) >= 2 and all(len(x) < 140 for x in bullets) else sentences
            result.append({"title": s["title"], "points": points})
        elif s["title"]:
            result.append({"title": s["title"], "points": []})
        elif sentences:
            result.append({"title": None, "points": sentences})
    if any(r["title"] for r in result):
        return [r for r in result if r["title"]]
    # no headings at all: split into paragraphs, the first sentence becomes the title
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    out = []
    for p in paras:
        sents = _sentences(p)
        if not sents:
            continue
        out.append({"title": shorten(sents[0].rstrip(".!?"), 70), "points": sents[1:] if len(sents) > 1 else [sents[0]]})
    return out


def fallback_outline(deck: dict[str, Any], sources: list[dict[str, Any]], warnings: list[str]) -> list[dict[str, Any]]:
    lang = deck["language"]
    labels = LABELS.get(lang, LABELS["es"])
    n = deck["slide_count"]
    sections: list[dict[str, Any]] = []
    for s in sources:
        sections += sections_from_text(s["text"])
    if not sections and deck.get("brief"):
        sections = sections_from_text(deck["brief"])
        if len(sections) == 1 and len(sections[0]["points"]) > 1:  # one paragraph: one section per sentence group
            pts = sections[0]["points"]
            sections = [{"title": shorten(p.rstrip(".!?"), 70), "points": [p]} for p in pts]
    if not sections:
        raise CiceroError(labels["no_material"], code="no_material")
    middle_n = max(1, n - 2)
    if len(sections) > middle_n:
        buckets: list[list[dict[str, Any]]] = [[] for _ in range(middle_n)]
        for i, s in enumerate(sections):
            buckets[min(middle_n - 1, i * middle_n // len(sections))].append(s)
        middle = []
        joiner = " y " if lang == "es" else " and "
        for b in buckets:
            if len(b) == 1:
                middle.append({"title": b[0]["title"], "purpose": "", "points": b[0]["points"][:5]})
            else:
                title = b[0]["title"] + joiner + b[1]["title"] if len(b) == 2 else f"{b[0]['title']} \u2013 {b[-1]['title']}"
                points = [(x["points"][0] if x["points"] else x["title"]) for x in b][:5]
                middle.append({"title": shorten(title, 70), "purpose": "", "points": points})
    else:
        middle = [{"title": s["title"], "purpose": "", "points": s["points"][:5]} for s in sections]
        if len(middle) < middle_n:
            warnings.append(f"The material only supports {len(middle) + 2} slides; add sources for {n}.")
    first_line = (_sentences(deck.get("brief", "")) or [""])[0]
    title_item = {"title": deck["title"], "purpose": clip(first_line, 300), "points": [], "layout_hint": "title"}
    closing = {"title": labels["closing"], "purpose": "", "points": [m["title"] for m in middle[:4]], "layout_hint": "closing"}
    for m in middle:
        m.setdefault("layout_hint", None)
    return [title_item, *middle, closing]


def _sources_matching(points: list[str], sources: list[dict[str, Any]]) -> list[int]:
    ids: list[int] = []
    for s in sources:
        hay = _fold(re.sub(r"\s+", " ", s["text"]))
        if any(len(p) >= 12 and _fold(re.sub(r"\s+", " ", p))[:60] in hay for p in points):
            ids.append(s["id"])
    return ids


def fallback_slide(deck: dict[str, Any], item: dict[str, Any], position: int, total: int, sources: list[dict[str, Any]]) -> dict[str, Any]:
    labels = LABELS.get(deck["language"], LABELS["es"])
    hint = item.get("layout_hint")
    points = [shorten(p, MAX_BULLET_CHARS) for p in item.get("points", [])][:MAX_BULLETS]
    purpose = (item.get("purpose") or "").strip()
    notes_parts = [purpose] if purpose else []
    if item.get("points"):
        notes_parts.append(f"{labels['notes_points']}: " + "; ".join(p.rstrip(".") for p in item["points"][:5]) + ".")
    notes = " ".join(notes_parts)
    used = _sources_matching(item.get("points", []), sources)
    base: dict[str, Any] = {"layout": "bullets", "title": item["title"], "subtitle": None, "blocks": [], "notes": notes, "sources": used, "image_prompt": None}
    if position == 1 or hint == "title":
        base.update(layout="title", subtitle=purpose or None)
        if deck.get("audience"):
            base["blocks"] = [{"type": "text", "text": f"{labels['for']}: {deck['audience']}"}]
        return base
    if position == total or hint == "closing":
        base.update(layout="closing", blocks=[{"type": "bullets", "items": points}] if points else [])
        return base
    if hint == "section":
        base.update(layout="section", subtitle=purpose or (points[0] if points else None))
        return base
    if hint == "two_column" and len(points) >= 2:
        half = (len(points) + 1) // 2
        base.update(layout="two_column", blocks=[{"type": "columns", "left": points[:half], "right": points[half:]}])
        return base
    if hint == "quote" and points:
        base.update(layout="quote", blocks=[{"type": "quote", "text": item["points"][0][:600]}])
        return base
    if hint == "image_text":
        base.update(layout="image_text", image_prompt=item["title"])
    base["blocks"] = [{"type": "bullets", "items": points}] if points else ([{"type": "text", "text": purpose}] if purpose else [])
    return base


# ---------------- orchestration ----------------

def _with_meta(deck: dict[str, Any], generator: str, warnings: list[str], **extra: Any) -> dict[str, Any]:
    deck = dict(deck)
    deck["generator"] = generator
    deck["warnings"] = warnings
    deck.update(extra)
    return deck


def model_status_note(error: str) -> str:
    return f"No model is reachable ({error}); used the rule-based fallback."


def generate_outline(svc: Any, deck_id: str) -> dict[str, Any]:
    deck = store.deck_view(svc, deck_id)
    sources = store.source_texts(svc, deck_id)
    warnings: list[str] = []
    excerpt_text, _ids = excerpts(sources, f"{deck['title']} {deck['brief']}", OUTLINE_BUDGET)
    generator, model = "model", None
    try:
        items, model = chat_json(svc, outline_messages(deck, excerpt_text), lambda d, strict: parse_outline(d, strict, deck["slide_count"], warnings),
                                 max_tokens=4000, effort="medium")
    except ModelDown as down:
        generator = "fallback"
        warnings.append(model_status_note(str(down)))
        items = fallback_outline(deck, sources, warnings)
    result = store.set_outline(svc, deck_id, items, model_used=model, set_model=True)
    svc.emit("cicero.outline.generated", {"id": deck_id, "items": len(items), "generator": generator})
    return _with_meta(result, generator, warnings)


def _order_after_generation(svc: Any, deck_id: str, outline_ids: list[str], old_order: list[dict[str, Any]]) -> None:
    """Slides follow the outline; slides added by hand stay after the slide they followed."""
    current = {s["id"]: s for s in store.deck_view(svc, deck_id)["slides"]}
    by_outline = {s["outline_id"]: s["id"] for s in current.values() if s.get("outline_id")}
    anchor: dict[Optional[str], list[str]] = {}
    prev_outline: Optional[str] = None
    for s in old_order:
        if s["id"] not in current:
            continue
        if s.get("outline_id") and s["outline_id"] in by_outline:
            prev_outline = s["outline_id"]
        elif not s.get("outline_id"):
            anchor.setdefault(prev_outline, []).append(s["id"])
    final: list[str] = list(anchor.get(None, []))
    for oid in outline_ids:
        sid = by_outline.get(oid)
        if sid:
            final.append(sid)
            final += anchor.get(oid, [])
    leftovers = [sid for sid in current if sid not in final]  # e.g. hand-added slides anchored to a removed outline item
    store.reorder_slides(svc, deck_id, final + leftovers)


def slide_effort() -> str:
    """Reasoning effort asked of the model for slides and rewrites (CICERO_SLIDE_EFFORT, default low).

    The outline decides the argument and keeps "medium"; a slide only lays out points already chosen, and on a
    local 27B model "medium" made one rewrite take minutes instead of about one.
    """
    value = (os.environ.get("CICERO_SLIDE_EFFORT") or "low").strip().lower()
    return value if value in ("off", "low", "medium", "high", "max") else "low"


def parallel_slides() -> int:
    """How many slides are written at the same time (CICERO_PARALLEL_SLIDES, 1-8, default 3)."""
    try:
        return max(1, min(8, int(os.environ.get("CICERO_PARALLEL_SLIDES", "3"))))
    except ValueError:
        return 3


def generate_slides(svc: Any, deck_id: str, only_missing: bool = False) -> dict[str, Any]:
    deck = store.deck_view(svc, deck_id)
    outline = deck["outline"]
    if not outline:
        raise CiceroError("Generate or write the outline first.", code="outline_required")
    sources = store.source_texts(svc, deck_id)
    source_ids = {s["id"] for s in sources}
    reference = all_number_values([s["text"] for s in sources]) if sources else None
    existing = {s["outline_id"]: s for s in deck["slides"] if s.get("outline_id")}
    old_order = deck["slides"]
    warnings: list[str] = []
    total = len(outline)
    model_down = False
    used_model = used_fallback = False
    model_name: Optional[str] = None
    generated = kept = 0
    jobs: list[tuple[int, dict[str, Any], Optional[dict[str, Any]]]] = []
    for index, item in enumerate(outline, start=1):
        current = existing.get(item["id"])
        if current is not None and (current["status"] == "approved" or only_missing):
            kept += 1
            continue
        jobs.append((index, item, current))

    def ask(job: tuple[int, dict[str, Any], Optional[dict[str, Any]]]) -> tuple[str, Any, Optional[str], list[str]]:
        index, item, _current = job
        neighbours = (outline[index - 2]["title"] if index > 1 else "", outline[index]["title"] if index < total else "")
        query = " ".join([item["title"], item.get("purpose", ""), *item.get("points", [])])
        excerpt_text, _ = excerpts(sources, query, SLIDE_BUDGET)
        slide_warnings: list[str] = []
        try:
            content, name = chat_json(
                svc, slide_messages(deck, item, index, total, neighbours, excerpt_text),
                lambda d, strict: finish_slide(GeneratedSlide.model_validate(d), strict=strict, source_ids=source_ids, reference=reference,
                                               warnings=slide_warnings, fallback_title=item["title"]),
                max_tokens=1600)
            return "ok", content, name, slide_warnings
        except ModelDown as down:
            return "down", None, str(down), []
        except GenerationFailed as failed:
            return "failed", None, str(failed), []

    # The first slide goes alone: it tells whether a model answers at all. The rest run a few at a time,
    # since a local server with several slots finishes them sooner together than one after another.
    answers: dict[int, tuple[str, Any, Optional[str], list[str]]] = {}
    if jobs:
        first = ask(jobs[0])
        answers[jobs[0][0]] = first
        if first[0] == "down":
            model_down = True
            warnings.append(model_status_note(first[2] or ""))
        elif len(jobs) > 1:
            workers = max(1, min(parallel_slides(), len(jobs) - 1))
            with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="cicero-slide") as pool:
                for job, answer in zip(jobs[1:], pool.map(ask, jobs[1:])):
                    answers[job[0]] = answer
            if any(a[0] == "down" for a in answers.values()):
                warnings.append(model_status_note(next(a[2] for a in answers.values() if a[0] == "down") or ""))

    for index, item, current in jobs:
        kind, content, detail, slide_warnings = answers.get(index, ("down", None, None, []))
        if kind == "ok":
            warnings += slide_warnings
            used_model = True
            model_name = detail or model_name
        elif kind == "failed":
            warnings.append(f"Slide {index} (\"{clip(item['title'], 40)}\"): {detail} Built by the fallback instead.")
            content = None
        else:
            content = None
        if content is None:
            content = fallback_slide(deck, item, index, total, sources)
            used_fallback = True
        content["sources"] = [i for i in content.get("sources", []) if i in source_ids]
        if current is not None:
            store.patch_slide(svc, deck_id, current["id"], {**content, "subtitle": content.get("subtitle") or ""}, reason="regenerated")
        else:
            store.add_slide(svc, deck_id, layout=content["layout"], title=content["title"], subtitle=content.get("subtitle"), blocks=content["blocks"],
                            notes=content["notes"], sources=content["sources"], image_prompt=content.get("image_prompt"), outline_id=item["id"],
                            reason="generated")
        generated += 1
    if not only_missing:  # drafts of removed outline items go away; approved ones and hand-made slides stay
        outline_ids = {o["id"] for o in outline}
        for s in store.deck_view(svc, deck_id)["slides"]:
            if s.get("outline_id") and s["outline_id"] not in outline_ids and s["status"] == "draft":
                store.delete_slide(svc, deck_id, s["id"])
    _order_after_generation(svc, deck_id, [o["id"] for o in outline], old_order)
    generator = "mixed" if used_model and used_fallback else "model" if used_model else "fallback"
    if generated:
        svc.db.execute("UPDATE decks SET model_used = ? WHERE id = ?", (model_name if generator != "fallback" else None, deck_id))
    svc.emit("cicero.slides.generated", {"id": deck_id, "generated": generated, "kept": kept, "generator": generator})
    return _with_meta(store.deck_view(svc, deck_id), generator, warnings, generated=generated, kept=kept)


def regenerate_slide(svc: Any, deck_id: str, slide_id: str, feedback: str) -> dict[str, Any]:
    deck = store.deck_view(svc, deck_id)
    slide = next((s for s in deck["slides"] if s["id"] == slide_id), None)
    if slide is None:
        store.get_slide(svc, deck_id, slide_id)  # raises NotFound
        raise CiceroError("Slide not found.")
    sources = store.source_texts(svc, deck_id)
    source_ids = {s["id"] for s in sources}
    reference = all_number_values([s["text"] for s in sources]) if sources else None
    item = next((o for o in deck["outline"] if o["id"] == slide.get("outline_id")), {})
    query = " ".join([slide["title"], feedback, item.get("purpose", ""), *item.get("points", [])])
    excerpt_text, _ = excerpts(sources, query, SLIDE_BUDGET)
    warnings: list[str] = []
    total = len(deck["slides"])
    neighbours = (deck["slides"][slide["position"] - 2]["title"] if slide["position"] > 1 else "",
                  deck["slides"][slide["position"]]["title"] if slide["position"] < total else "")
    try:
        content, model = chat_json(
            svc, slide_messages(deck, item, slide["position"], total, neighbours, excerpt_text, current=slide, feedback=feedback),
            lambda d, strict: finish_slide(GeneratedSlide.model_validate(d), strict=strict, source_ids=source_ids, reference=reference,
                                           warnings=warnings, fallback_title=slide["title"]),
            max_tokens=1600)
    except ModelDown as down:
        raise ModelUnavailable(f"Regenerating a slide with your feedback needs a model, and none is reachable ({down}). Edit the slide by hand or start a model.") from down
    # a regenerated slide keeps the pictures the person put on it (the model cannot see them)
    images = [b for b in slide["blocks"] if b.get("type") == "image"]
    content["blocks"] = content["blocks"] + images
    if images and content["layout"] == "bullets":
        content["layout"] = "image_text"
    updated = store.patch_slide(svc, deck_id, slide_id, {**content, "subtitle": content.get("subtitle") or ""}, reason="regenerated")
    svc.db.execute("UPDATE decks SET model_used = ? WHERE id = ?", (model, deck_id))
    return {**updated, "generator": "model", "warnings": warnings}
