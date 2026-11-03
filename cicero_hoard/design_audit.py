"""Deck design audit through the family design studio (Vitruvius's ``design_slop_audit``).

The deck is rendered as the stacked HTML document (every slide one below the other, assets inline), the studio renders it at
eight widths and scores the generated look 0-100, and each finding is mapped back to the slide it sits on:

* by geometry: the studio returns boxes in the coordinates of its display width; the audit document pins the stacked layout
  (``AUDIT_CSS``), so slide ``i`` covers ``[TOP + i*pitch, TOP + i*pitch + slide_h)``;
* by text, when a finding quotes a slide's words and has no box;
* the rest is deck-wide (``scope: deck``), or about the HTML wrapper rather than the slides (``scope: page``).

The latest audit of each deck is kept in ``design_audits`` and shown in the review screen next to the deck check.
"""

from __future__ import annotations

import json
import math
import os
import re
from typing import Any, Callable, Optional

from .errors import CiceroError
from .util import jload

VITRUVIUS_APP = "vitruvius"
AUDIT_TOOL = "design_slop_audit"
AUDIT_TIMEOUT_S = 240.0
MAX_INLINE_HTML = 1_900_000
VITRUVIUS_URL = os.environ.get("CICERO_VITRUVIUS_URL", "http://127.0.0.1:5191").rstrip("/")

# The stacked layout the audit document pins (same values as render.CSS for the preview, forced so a template stack maps too).
TOP, SIDE, SLIDE_MAX_W, GAP = 24, 16, 1280, 28
AUDIT_CSS = (".deck{padding:24px 16px!important;margin:0!important}"
             ".slide{width:min(100%,1280px)!important;aspect-ratio:16/9!important;margin:0 auto 28px!important;height:auto!important}")

# Findings about the HTML page that carries the slides (not about the slides themselves).
WRAPPER_RULES = {"craft/title-meta", "layout.no-max-width"}
WRAPPER_TARGETS = ("html", "body", "main", ".deck", ".slide", ":root")


# ---------------- talking to the studio ----------------

def unavailable(answer: dict[str, Any], what: str) -> CiceroError:
    """A CiceroError whose code says what the person can do: start the studio, switch its design module on, or start the hub."""
    error = str(answer.get("error") or f"status {answer.get('status')}")
    status = answer.get("status")
    if error.startswith("hub not reachable"):
        return CiceroError(f"Could not {what}: the Hoard Hub is not running ({error}).", code="hub_down")
    if "Enable module explicitly first" in error or "Enable design explicitly" in error:
        return CiceroError(f"Could not {what}: the design module of Vitruvius's Hoard is switched off. Switch it on (prepare=true, "
                           "or the button in Review) and try again.", code="design_module_off")
    if status in (None, 502, 503, 504) or "URLError" in error or "not reachable" in error or "unreachable" in error:
        return CiceroError(f"Could not {what}: Vitruvius's Hoard is not running. Start it through the Hub (prepare=true, or the "
                           "button in Review) and try again.", code="vitruvius_down")
    if "Unknown tool" in error:
        return CiceroError(f"Could not {what}: this Vitruvius's Hoard has no {AUDIT_TOOL}; update it.", code="vitruvius_outdated")
    return CiceroError(f"Could not {what}: {error}", code="family_unavailable")


def hub_post(path: str, body: dict[str, Any], timeout: float) -> tuple[Optional[int], Any]:
    """POST to the Hoard Hub (tests replace it)."""
    from .hoard_link import family
    return family._post(path, body, timeout)  # noqa: SLF001 - the family module's own hub client


def start_vitruvius(svc: Any) -> dict[str, Any]:
    """Ask the Hub to start Vitruvius's Hoard and switch its design module on. Never raises: says what happened."""
    status, body = hub_post(f"/api/apps/{VITRUVIUS_APP}/start", {}, 90.0)
    started = isinstance(body, dict) and bool(body.get("ok")) and status is not None and status < 400
    out: dict[str, Any] = {"started": started, "hub_status": status}
    if not started:
        out["error"] = (body or {}).get("error") if isinstance(body, dict) else ("the Hoard Hub is not running" if status is None else f"HTTP {status}")
        return out
    out.update(enable_design(svc))
    return out


def enable_design(svc: Any) -> dict[str, Any]:
    """Switch the studio's design module on when it is off (left as it is, with its own settings, when it is already on)."""
    state = svc.family_call(VITRUVIUS_APP, "software_modules", {}, timeout=30.0)
    modules = ((state.get("result") or {}).get("modules") or []) if state.get("ok") else []
    design = next((m for m in modules if isinstance(m, dict) and (m.get("module") or m.get("name")) == "design"), None)
    if design and design.get("state") == "on":
        return {"design_module": "on"}
    answer = svc.family_call(VITRUVIUS_APP, "software_module_set", {"module": "design", "enabled": True}, timeout=120.0)
    return {"design_module": "on" if answer.get("ok") else "unknown", **({} if answer.get("ok") else {"design_error": answer.get("error")})}


# ---------------- the audited document ----------------

def audit_document(svc: Any, deck: dict[str, Any]) -> tuple[str, float]:
    """The deck as one self-contained stacked HTML page (what the HTML export shows, every slide visible) with the layout pinned,
    and the slides' aspect ratio (16:9, or the PPTX template's own)."""
    from .advanced import hydrate
    from .render import esc, render_document

    deck = hydrate(svc, deck)
    if deck.get("template"):
        from .template_live import document as template_document
        html = template_document(svc, deck, slide_id=None, mode="stacked", inline=True)
    else:
        html, _ = render_document(deck, assets=svc.assets_lookup(), inline=True, mode="stacked")
    found = re.search(r"\.slide\{aspect-ratio:(\d+(?:\.\d+)?)/(\d+(?:\.\d+)?)\}", html)
    ratio = float(found.group(1)) / float(found.group(2)) if found and float(found.group(2)) else 16 / 9
    css = AUDIT_CSS.replace("aspect-ratio:16/9", f"aspect-ratio:{ratio:.6f}")
    description = (deck.get("brief") or deck.get("title") or "").strip()[:300]
    head = f'<meta name="description" content="{esc(description)}"><style id="cicero-audit-layout">{css}</style>'
    return mark_slides(html.replace("</head>", head + "</head>", 1)), ratio


# Every element of slide ``n`` (1-based) gets ``id="cs{n}-{k}"`` when it has none: the studio names elements by tag#id.class in its
# evidence ("h2#cs6-3 “Resultados del…”") and finds their boxes by that label, so a finding lands on its own slide even when
# several slides share the same words (a box found by quoted text alone is the first slide with those words).
MARK = re.compile(r"#cs(\d+)-\d+")
SECTION_MARK = re.compile(r"#s-([0-9A-Za-z_-]+)")
_SECTION_START = re.compile(r'(?=<section class="slide"[\s>])')
_OPEN_TAG = re.compile(r"<([a-zA-Z][a-zA-Z0-9-]*)(?=[\s/>])([^>]*)>")
_RAW_TEXT = re.compile(r"(<script\b.*?</script\s*>|<style\b.*?</style\s*>)", re.S | re.I)


def mark_slides(html: str) -> str:
    """The audit document with an id on every element of every slide that has none (``cs{slide number}-{k}``)."""
    parts = _SECTION_START.split(html)
    out = [parts[0]]
    for n, part in enumerate(parts[1:], start=1):
        end = part.find("</section>")
        body, rest = (part, "") if end < 0 else (part[:end], part[end:])
        counter = [0]

        def add(match: "re.Match[str]") -> str:
            if re.search(r"\sid\s*=", match.group(2)):
                return match.group(0)
            counter[0] += 1
            return f'<{match.group(1)} id="cs{n}-{counter[0]}"{match.group(2)}>'

        pieces = _RAW_TEXT.split(body)  # script and style text is left alone
        out.append("".join(p if i % 2 else _OPEN_TAG.sub(add, p) for i, p in enumerate(pieces)) + rest)
    return "".join(out)


def fingerprint(deck: dict[str, Any]) -> str:
    """What the audit looked at: the slides' revisions and the theme. A different value means the audit is out of date."""
    return f"{deck.get('content_version', '')}:{deck.get('theme', '')}:{(deck.get('template') or {}).get('sha256', '')}"


# ---------------- mapping findings to slides ----------------

def slide_index_for_box(box: list[Any], box_width: float, count: int, ratio: float = 16 / 9) -> Optional[int]:
    """The stacked slide a box ``[x, y, w, h]`` (in ``box_width`` page pixels) sits on, or None when it is between slides or off them."""
    try:
        x, y, w, h = (float(v) for v in box[:4])
    except (TypeError, ValueError):
        return None
    width = min(float(box_width or 1440) - 2 * SIDE, SLIDE_MAX_W)
    if width <= 0 or count <= 0 or ratio <= 0:
        return None
    slide_h = width / ratio
    pitch = slide_h + GAP
    centre = y + h / 2 - TOP
    if centre < 0:
        return None
    index = int(math.floor(centre / pitch))
    if index >= count or centre - index * pitch > slide_h:
        return None
    return index


def _items(evidence: Any) -> list[str]:
    if isinstance(evidence, str):
        return [evidence]
    if isinstance(evidence, dict):
        return _items(evidence.get("items") or [])
    if isinstance(evidence, (list, tuple)):
        return [str(x) for x in evidence if isinstance(x, (str, int, float))]
    return []


def _slide_text(slide: dict[str, Any]) -> str:
    parts = [slide.get("title") or "", slide.get("subtitle") or "", json.dumps(slide.get("blocks") or [], ensure_ascii=False)]
    return " ".join(parts).lower()


def _quoted(items: list[str]) -> list[str]:
    out = []
    for item in items:
        for found in re.findall(r"[“\"]([^”\"]{4,})", item):
            out.append(found.strip().rstrip("…").strip().lower()[:40])
    return [q for q in out if len(q) >= 4]


def _is_wrapper(finding: dict[str, Any], items: list[str]) -> bool:
    if finding.get("check_id") in WRAPPER_RULES:
        return True
    heads = [re.split(r"[\s:,{]", i.strip(), maxsplit=1)[0] for i in items]
    return bool(heads) and all(h in WRAPPER_TARGETS for h in heads)


def _severity(finding: dict[str, Any]) -> str:
    level = finding.get("level") or finding.get("severity") or ""
    return "warning" if level in ("error", "warning", "warn") else "info"


def map_findings(findings: list[dict[str, Any]], slides: list[dict[str, Any]], ratio: float = 16 / 9) -> list[dict[str, Any]]:
    """One issue per (finding, slide) for the slides a finding is on, one deck issue for the rest; ``scope`` slide / deck / page."""
    issues: list[dict[str, Any]] = []
    texts = [_slide_text(s) for s in slides]
    by_id = {s["id"]: i for i, s in enumerate(slides)}
    for f in findings:
        if f.get("pass") is True or f.get("waived"):
            continue
        named = _items(f.get("evidence"))
        items = [MARK.sub("", i) for i in named]  # the ids are Cicero's own marks: shown without them
        base = {"source": "design", "rule": f.get("check_id") or "", "title": f.get("title") or "", "message": f.get("detail") or f.get("title") or "",
                "fix": f.get("fix") or "", "severity": _severity(f), "tier": f.get("tier"), "pass": f.get("pass") if isinstance(f.get("pass"), str) else None,
                "slop": bool(f.get("slop")), "widths": (f.get("evidence") or {}).get("widths") if isinstance(f.get("evidence"), dict) else None,
                "items": items[:6]}
        indexes: list[int] = []
        for item in named:  # an element named by its mark (or the slide's own id) is on that slide, whatever its words
            mark, section = MARK.search(item), SECTION_MARK.search(item)
            i = int(mark.group(1)) - 1 if mark else by_id.get(section.group(1)) if section else None
            if i is not None and 0 <= i < len(slides) and i not in indexes:
                indexes.append(i)
        for box in ([] if indexes else f.get("boxes") or []):
            i = slide_index_for_box(box, f.get("box_width") or 1440, len(slides), ratio)
            if i is not None and i not in indexes:
                indexes.append(i)
        if not indexes:
            for quote in _quoted(items):
                indexes += [i for i, text in enumerate(texts) if quote in text and i not in indexes]
        if indexes:
            issues += [{**base, "scope": "slide", "slide_id": slides[i]["id"], "slide_number": i + 1} for i in sorted(indexes)]
        elif _is_wrapper(f, items):
            issues.append({**base, "scope": "page", "slide_id": None, "severity": "info"})
        else:
            issues.append({**base, "scope": "deck", "slide_id": None})
    return issues


# ---------------- running and keeping ----------------

def summarise(result: dict[str, Any], deck: dict[str, Any], ratio: float, clock: Callable[[], float]) -> dict[str, Any]:
    """The audit as Cicero keeps it: the studio's score, mode and plan summary, and the findings mapped to slides."""
    slides = deck.get("slides") or []
    issues = map_findings(result.get("findings") or [], slides, ratio)
    per_slide: dict[str, int] = {}
    for issue in issues:
        if issue["slide_id"]:
            per_slide[issue["slide_id"]] = per_slide.get(issue["slide_id"], 0) + 1
    render_id = str(result.get("render_id") or "")
    plan = result.get("plan") or {}
    return {"deck_id": deck["id"], "render_id": render_id, "slop_score": result.get("slop_score"), "mode": result.get("mode"),
            "signs": result.get("signs"), "sign_ids": result.get("sign_ids") or [], "summary": plan.get("summary") or "",
            "by_pass": result.get("by_pass") or {}, "rules_run": result.get("rules_run"), "widths": result.get("widths") or [],
            "issues": issues, "per_slide": per_slide,
            "counts": {s: sum(1 for i in issues if i["scope"] == s) for s in ("slide", "deck", "page")},
            "studio_url": f"{VITRUVIUS_URL}/design/#/critique/{render_id}" if render_id else None,
            "credit": result.get("credit") or "", "fingerprint": fingerprint(deck), "created_ts": clock(), "lang": result.get("lang") or "en"}


def norm_lang(lang: Optional[str] = None, accept_language: Optional[str] = None) -> str:
    """The language the review is shown in: explicit ``lang``, else the first supported Accept-Language tag, else Spanish."""
    for cand in [lang] + [p.split(";")[0] for p in (accept_language or "").split(",")]:
        c = (cand or "").strip().lower()[:2]
        if c in ("es", "en"):
            return c
    return "es"


def relocalize(svc: Any, audit: dict[str, Any], lang: str) -> dict[str, Any]:
    """The kept audit read again in ``lang``: Vitruvius keeps its audits in English and renders them in either language, so the
    titles, messages, fixes, summary and credit are replaced by the studio's text for the same rules; slides, scores and
    mapping stay. If the studio does not answer, the audit stays as it was."""
    if not audit.get("render_id") or audit.get("lang") == lang:
        return audit
    answer = svc.family_call(VITRUVIUS_APP, AUDIT_TOOL, {"render_id": audit["render_id"], "full": True, "rerender": False, "lang": lang}, timeout=AUDIT_TIMEOUT_S)
    result = answer.get("result") if answer.get("ok") else None
    if not isinstance(result, dict) or result.get("lang") != lang or "findings" not in result:
        return audit
    by_rule = {f.get("check_id"): f for f in result.get("findings") or []}
    for issue in audit.get("issues") or []:
        f = by_rule.get(issue.get("rule"))
        if f:
            issue["title"], issue["fix"] = f.get("title") or issue["title"], f.get("fix") or issue.get("fix", "")
            issue["message"] = f.get("detail") or f.get("title") or issue["message"]
    audit["summary"] = (result.get("plan") or {}).get("summary") or audit.get("summary", "")
    audit["credit"], audit["lang"] = result.get("credit") or audit.get("credit", ""), lang
    return audit


def run(svc: Any, deck_id: str, *, prepare: bool = False, lang: Optional[str] = None) -> dict[str, Any]:
    """Audit a deck with the studio and keep the result. ``prepare``: start the studio through the Hub (and switch its design
    module on) when it is not ready, then try once more. ``lang`` (es default | en): the language of the findings."""
    from . import decks as store

    lang = norm_lang(lang)
    deck = store.deck_view(svc, deck_id)
    if not deck["slides"]:
        raise CiceroError("The presentation has no slides to review.", code="no_slides")
    html, ratio = audit_document(svc, deck)
    arguments: dict[str, Any] = {"html": html, "full": True, "lang": lang}
    if len(html) > MAX_INLINE_HTML:  # the studio takes up to 2 MB inline; a deck with big pictures goes as a local file
        folder = svc.config.data_dir / "design-audits"
        folder.mkdir(parents=True, exist_ok=True)
        page = folder / f"{deck_id}.html"
        page.write_text(html, encoding="utf-8")
        arguments = {"path": str(page.resolve()), "full": True, "lang": lang}
    answer = svc.family_call(VITRUVIUS_APP, AUDIT_TOOL, arguments, timeout=AUDIT_TIMEOUT_S)
    prepared: Optional[dict[str, Any]] = None
    if not answer.get("ok") and prepare:
        error = unavailable(answer, "review the design")
        if error.code in ("vitruvius_down", "design_module_off"):
            prepared = start_vitruvius(svc) if error.code == "vitruvius_down" else enable_design(svc)
            answer = svc.family_call(VITRUVIUS_APP, AUDIT_TOOL, arguments, timeout=AUDIT_TIMEOUT_S)
    if not answer.get("ok"):
        raise unavailable(answer, "review the design")
    result = answer.get("result")
    if not isinstance(result, dict) or "findings" not in result:
        raise CiceroError("Could not review the design: unexpected answer from Vitruvius's Hoard.", code="family_unavailable")
    audit = summarise(result, deck, ratio, svc.clock)
    if prepared:
        audit["prepared"] = prepared
    svc.db.execute("INSERT OR REPLACE INTO design_audits(deck_id, result, created_ts) VALUES (?,?,?)",
                   (deck_id, json.dumps(audit, ensure_ascii=False), audit["created_ts"]))
    svc.emit("cicero.design_audit.done", {"deck": deck_id, "slop_score": audit["slop_score"], "mode": audit["mode"]})
    svc.refs_link(f"hoard://cicero/deck/{deck_id}", f"hoard://{VITRUVIUS_APP}/render/{audit['render_id']}", "reviewed_by",
                  from_label=deck["title"], to_label="design audit")
    return {**audit, "stale": False}


def latest(svc: Any, deck_id: str, lang: Optional[str] = None) -> Optional[dict[str, Any]]:
    """The deck's last audit, with ``stale`` true when the slides or the theme changed since. With ``lang`` it is shown in that
    language (re-read from the studio when it was kept in the other one, and kept that way)."""
    from . import decks as store

    deck = store.deck_view(svc, deck_id)
    row = svc.db.one("SELECT result FROM design_audits WHERE deck_id = ?", (deck_id,))
    if not row:
        return None
    audit = jload(row["result"], {})
    if lang and audit.get("lang", "en") != norm_lang(lang):
        audit = relocalize(svc, audit, norm_lang(lang))
        if audit.get("lang") == norm_lang(lang):
            svc.db.execute("UPDATE design_audits SET result = ? WHERE deck_id = ?", (json.dumps(audit, ensure_ascii=False), deck_id))
    known = {s["id"] for s in deck["slides"]}
    audit["issues"] = [i for i in audit.get("issues", []) if not i.get("slide_id") or i["slide_id"] in known]
    audit["stale"] = audit.get("fingerprint") != fingerprint(deck)
    return audit
