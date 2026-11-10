"""Conclusion titles: a slide title that states what the slide shows instead of naming its topic.

A label ("Resultados del trimestre") names the subject. A conclusion ("Las ventas crecieron un 12 % por el canal online")
says what the audience should remember. This module tells them apart, proposes the conclusion from what the slide really
holds (its text, its table and metrics, its chart series) and never lets a figure into a title that the slide does not
contain or that does not follow from its chart by plain arithmetic. Applying keeps the label, so every title can go back.

The mode lives per deck (``label`` or ``conclusion``) and can be overridden per slide; the state is one setting per deck,
``titles:<deck id>``: ``{"mode", "slides": {slide id: {"mode", "label", "conclusion", "proposal", "by", "for"}}}``.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from . import decks as store
from . import generate as gen
from .check import all_number_values, significant_numbers, slide_text_parts
from .errors import CiceroError, NotFound
from .util import jdump

MODES = ("label", "conclusion")
#: layouts whose title is legitimately a label: the cover, a section divider, the closing slide, a quote
EXEMPT_LAYOUTS = frozenset({"title", "section", "closing", "quote"})
MAX_TITLE_CHARS = 120
BATCH = 12

MSG = {
    "es": {"label_title": "El título es un rótulo: nombra el tema, no dice la conclusión de la diapositiva.",
           "label_title_proposal": "El título es un rótulo: nombra el tema, no dice la conclusión. Propuesta: «{proposal}».",
           "rise": "{name} sube de {a} a {b} entre {c0} y {c1} ({pct} %)", "fall": "{name} baja de {a} a {b} entre {c0} y {c1} ({pct} %)",
           "flat": "{name} se mantiene en {a} entre {c0} y {c1}", "share": "{cat} concentra el {pct} % de {name}",
           "leader": "{cat} tiene el valor más alto de {name}: {v}", "metric": "{label} se sitúa en {value}", "default_name": "El valor"},
    "en": {"label_title": "The title is a label: it names the topic instead of stating the slide's conclusion.",
           "label_title_proposal": "The title is a label: it names the topic instead of stating the conclusion. Proposal: \"{proposal}\".",
           "rise": "{name} rises from {a} to {b} between {c0} and {c1} ({pct}%)", "fall": "{name} falls from {a} to {b} between {c0} and {c1} ({pct}%)",
           "flat": "{name} stays at {a} between {c0} and {c1}", "share": "{cat} accounts for {pct}% of {name}",
           "leader": "{cat} has the highest {name}: {v}", "metric": "{label} stands at {value}", "default_name": "The value"},
}


# ---------------- label or conclusion ----------------

def _fold(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", (text or "").lower()) if not unicodedata.combining(c))


# conjugated forms that are a verb wherever they stand
_VERBS = frozenset("""
es son esta estan hay tiene tienen crece crecen aumenta aumentan reduce reducen supera superan permite permiten necesita necesitan debe deben
puede pueden genera generan representa representan lidera lideran pierde pierden duplica duplican triplica triplican explica explican
demuestra demuestran cuesta cuestan ahorra ahorran acelera aceleran frena frenan depende dependen concentra concentran impulsa impulsan
aporta aportan sigue siguen funciona funcionan llega llegan vale valen sirve sirven exige exigen basta conviene sera seran fue fueron ha han
hemos habra va van vamos somos tenemos queremos podemos debemos crecimos logramos conseguimos necesitamos cumple cumplen alcanza alcanzan
obtiene obtienen ofrece ofrecen mantiene mantienen produce producen provoca provocan evita evitan requiere requieren
is are was were has have had will can must should does did grew grows rose rises fell falls drove drives cut cuts doubled tripled increased
decreased improved reduced exceeded outperformed outperforms leads led shows showed proves proved means needs requires saves costs wins won
loses lost beats beat makes made gives gave takes took keeps kept remains remained accounts reaches reached delivers delivered stays
""".split())
# forms that are also nouns ("Mejora de procesos"): a verb only when something stands before them
_AMBIGUOUS = frozenset("mejora mejoran baja bajan sube suben cae caen gana ganan falta faltan cambia cambian pasa pasan queda quedan muestra "
                       "muestran cuenta cuentan suma suman resta restan marca marcan cierra cierran abre abren".split())
# Spanish endings that only verbs have: plural preterite and imperfect, first person plural future...
_VERB_ENDING = re.compile(r"^[a-zñ]{2,}(?:aron|ieron|aban|aremos|eremos|iremos)$")
# ...and the accented ones, read with their accent (creció, subían, mejorará): «dominó» is the rare noun that slips in
_ACCENTED = re.compile(r"[a-zñáéíóú]{2,}(?:ó|ían|ará|erá|irá|arán|erán|irán)$")
# English regular past («Costs dropped»): a verb only after another word, so «Updated roadmap» stays a label
_ENGLISH_PAST = re.compile(r"^[a-z]{3,}ed$")
_NOT_PAST = frozenset("pared usted merced cesped".split())
_WORD = re.compile(r"[\wñÑáéíóúüÁÉÍÓÚÜ']+")


def has_verb(title: str) -> bool:
    words = _WORD.findall(title or "")
    folded = [_fold(w) for w in words]
    for i, (raw, word) in enumerate(zip(words, folded)):
        if word in _VERBS or _VERB_ENDING.match(word) or _ACCENTED.search(raw.lower()):
            return True
        if i > 0 and (word in _AMBIGUOUS or (_ENGLISH_PAST.match(word) and word not in _NOT_PAST)):
            return True
        if word == "se" and i + 1 < len(folded) and i > 0:      # «El coste se reduce»
            return True
    return False


def is_label(title: str) -> bool:
    """True when the title names a topic instead of stating something: no verb, a question, or too short to assert anything.
    A short headline that carries a signed figure or a percentage («Ventas: +12 % interanual») counts as a statement."""
    text = (title or "").strip()
    if not text:
        return False                                            # an empty title is another problem (empty slide)
    words = _WORD.findall(text)
    if text.endswith("?"):
        return True
    figure = bool(re.search(r"\d\s?%|(?:^|(?<=[\s(]))[+\-−]\d", text))
    if len(words) < 3:
        return True
    if figure:
        return False
    return not has_verb(text)


# ---------------- what the slide holds ----------------

def _fmt(value: float, lang: str) -> str:
    if abs(value - round(value)) < 1e-9:
        return str(int(round(value)))
    text = f"{value:.2f}".rstrip("0").rstrip(".")
    return text.replace(".", ",") if lang == "es" else text


def _lc(label: str) -> str:
    """«Ventas» inside a sentence is «ventas»; «EBITDA» stays as it is."""
    return label[0].lower() + label[1:] if len(label) > 1 and label[1].islower() else label


def _signed(value: float, lang: str) -> str:
    return ("+" if value > 0 else "−" if value < 0 else "") + _fmt(abs(value), lang)


def _series(block: dict[str, Any]) -> list[tuple[str, list[tuple[str, float]]]]:
    cats = [str(c) for c in block.get("categories") or []]
    out = []
    for s in block.get("series") or []:
        points = [(cats[i], float(v)) for i, v in enumerate(s.get("values") or []) if v is not None and i < len(cats)]
        if points:
            out.append((str(s.get("name") or "").strip(), points))
    return out


def chart_facts(block: dict[str, Any], lang: str, fallback_name: str = "") -> list[dict[str, Any]]:
    """What plain arithmetic says about a chart: the change from the first to the last category of each series, or, for a
    chart of parts, the share of the largest one. Each fact is a sentence and the numbers it rests on."""
    m = MSG.get(lang, MSG["es"])
    kind = block.get("chart") or "bar"
    facts: list[dict[str, Any]] = []
    for name, points in _series(block)[:3]:
        label = name or (block.get("title") or "").strip() or fallback_name or m["default_name"]
        values = [v for _, v in points]
        if kind in ("pie", "donut", "funnel"):
            total = sum(values)
            if total > 0 and len(points) >= 2:
                cat, top = max(points, key=lambda p: p[1])
                pct = round(top / total * 100, 1)
                facts.append({"kind": "share", "text": m["share"].format(cat=cat, pct=_fmt(pct, lang), name=_lc(label)),
                              "numbers": {pct, float(round(pct)), top, total}})
            break
        if len(points) < 2:
            continue
        (c0, a), (c1, b) = points[0], points[-1]
        ordered = kind in ("line", "area", "band", "waterfall") or bool(re.search(r"\d", c0 + c1))
        if ordered:
            numbers = {a, b, abs(b - a)}
            if a == b:
                facts.append({"kind": "flat", "text": m["flat"].format(name=label, a=_fmt(a, lang), c0=c0, c1=c1), "numbers": numbers})
            elif a != 0:
                pct = round((b - a) / abs(a) * 100, 1)
                numbers |= {abs(pct), float(round(abs(pct))), pct, float(round(pct))}
                facts.append({"kind": "rise" if b > a else "fall",
                              "text": m["rise" if b > a else "fall"].format(name=label, a=_fmt(a, lang), b=_fmt(b, lang), c0=c0, c1=c1, pct=_signed(pct, lang)),
                              "numbers": numbers})
        else:
            cat, top = max(points, key=lambda p: p[1])
            facts.append({"kind": "leader", "text": m["leader"].format(cat=cat, name=_lc(label), v=_fmt(top, lang)), "numbers": {top}})
    return facts


def evidence(slide: dict[str, Any], lang: str = "es") -> dict[str, Any]:
    """The slide as evidence for its own title: the text it shows, the numbers it holds (text, table, metrics, chart
    values, notes) and the facts computed from its charts."""
    parts = [p for p in slide_text_parts(slide) if p]
    numbers = all_number_values(parts + [slide.get("notes") or ""])
    facts: list[dict[str, Any]] = []
    charts: list[dict[str, Any]] = []
    for b in slide.get("blocks") or []:
        if b.get("type") != "chart":
            continue
        for name, points in _series(b):
            numbers |= {v for _, v in points}
        found = chart_facts(b, lang, fallback_name=(slide.get("title") or "").strip())
        facts += found
        for f in found:
            numbers |= {float(n) for n in f["numbers"]}
        charts.append({"chart": b.get("chart") or "bar", "title": b.get("title") or "", "categories": [str(c) for c in (b.get("categories") or [])][:40],
                       "series": [{"name": n, "values": [v for _, v in pts][:40]} for n, pts in _series(b)]})
    return {"text": parts, "notes": (slide.get("notes") or "").strip(), "numbers": numbers, "facts": facts, "charts": charts}


def unbacked(title: str, ev: dict[str, Any]) -> list[str]:
    """Figures of a title that the slide does not hold (the same rule as the deck check: 2+ digits, a decimal or a percentage)."""
    missing: list[str] = []
    for printed, variants in significant_numbers(title or ""):
        if not ({abs(v) for v in variants} & {abs(n) for n in ev["numbers"]}) and printed not in missing:
            missing.append(printed)
    return missing


def _tidy(title: Any) -> str:
    text = re.sub(r"\s+", " ", str(title or "")).strip().strip("\"'«»“”").strip()
    return text[:-1] if text.endswith(".") and not text.endswith("..") else text


def rule_proposal(slide: dict[str, Any], lang: str = "es") -> Optional[str]:
    """A conclusion written without a model: what the chart's own numbers say, the first metric, or the first sentence of
    the slide that already is a statement. None when the slide holds nothing that can be stated by rule."""
    ev = evidence(slide, lang)
    m = MSG.get(lang, MSG["es"])
    if ev["facts"]:
        return _tidy(ev["facts"][0]["text"])[:MAX_TITLE_CHARS]
    for b in slide.get("blocks") or []:
        if b.get("type") == "metrics" and b.get("items"):
            item = next((i for i in b["items"] if i.get("emphasis")), b["items"][0])
            return _tidy(m["metric"].format(label=item["label"], value=item["value"]))[:MAX_TITLE_CHARS]
    current = _fold(slide.get("title") or "")
    for part in ev["text"]:
        for sentence in re.split(r"(?<=[.!?])\s+", part):
            candidate = _tidy(sentence)
            if 20 <= len(candidate) <= MAX_TITLE_CHARS and _fold(candidate) != current and not is_label(candidate):
                return candidate
    return None


# ---------------- state ----------------

def _key(deck_id: str) -> str:
    return "titles:" + deck_id


def _state(svc: Any, deck_id: str) -> dict[str, Any]:
    raw = svc.db.get_setting(_key(deck_id), {}) or {}
    return {"mode": raw.get("mode") if raw.get("mode") in MODES else "label", "slides": dict(raw.get("slides") or {})}


def _save(svc: Any, deck_id: str, state: dict[str, Any], live: set[str]) -> None:
    state["slides"] = {sid: {k: v for k, v in entry.items() if v not in (None, "")} for sid, entry in state["slides"].items() if sid in live}
    state["slides"] = {sid: entry for sid, entry in state["slides"].items() if entry}
    svc.db.set_setting(_key(deck_id), state)


def slide_mode(state: dict[str, Any], slide_id: str) -> str:
    own = (state["slides"].get(slide_id) or {}).get("mode")
    return own if own in MODES else state["mode"]


def _slide_view(state: dict[str, Any], slide: dict[str, Any]) -> dict[str, Any]:
    entry = state["slides"].get(slide["id"]) or {}
    exempt = slide.get("layout") in EXEMPT_LAYOUTS
    label = not exempt and is_label(slide.get("title") or "")
    proposal = entry.get("proposal") if entry.get("for") == (slide.get("title") or "") else None
    applied = bool(entry.get("label")) and entry.get("conclusion") == (slide.get("title") or "")
    return {"mode": slide_mode(state, slide["id"]), "own_mode": entry.get("mode") if entry.get("mode") in MODES else None,
            "exempt": exempt, "is_label": label, "proposal": proposal, "proposal_by": entry.get("by") if proposal else None,
            "label": entry.get("label") if applied else None, "applied": applied}


def annotate(svc: Any, view: dict[str, Any]) -> dict[str, Any]:
    """Add the title mode to a deck view: ``view["title_mode"]`` and ``slide["titling"]`` for each slide."""
    state = _state(svc, view["id"])
    view["title_mode"] = state["mode"]
    for slide in view.get("slides") or []:
        slide["titling"] = _slide_view(state, slide)
    return view


def review_issues(deck: dict[str, Any]) -> list[dict[str, Any]]:
    """The check's part: every content slide whose title is a label, with a proposal when there is one (a stored one, or
    one the slide's own data gives by rule). A warning where the conclusion mode is on, a note elsewhere; a slide that was
    told to keep its label is left alone."""
    lang = deck.get("language", "es")
    m = MSG.get(lang, MSG["es"])
    issues = []
    for slide in deck.get("slides") or []:
        info = slide.get("titling") or {"mode": "label", "own_mode": None, "exempt": slide.get("layout") in EXEMPT_LAYOUTS,
                                         "is_label": slide.get("layout") not in EXEMPT_LAYOUTS and is_label(slide.get("title") or ""), "proposal": None}
        if info["exempt"] or not info["is_label"] or info.get("own_mode") == "label":
            continue
        proposal = info.get("proposal") or rule_proposal(slide, lang)
        issue = {"slide_id": slide["id"], "kind": "label_title", "severity": "warning" if info["mode"] == "conclusion" else "info",
                 "message": m["label_title_proposal"].format(proposal=proposal) if proposal else m["label_title"], "position": slide["position"]}
        if proposal:
            issue["proposal"] = proposal
        issues.append(issue)
    return issues


# ---------------- proposing ----------------

SYSTEM = ("You rewrite slide titles as conclusion titles: one sentence that states what the audience should remember from the slide, instead of "
          "naming its topic. Use only what each slide contains: its text, its table and metrics, its chart data and the computed facts given. "
          "Never introduce a figure, date, name or cause that is not there; when the slide gives no cause, state none. Prefer the computed facts "
          "for charts. Write in the deck language, at most 110 characters, with a verb, without a final period and without quotation marks. "
          "If a slide holds nothing that can be concluded (an agenda, a list of topics), return an empty title for it. "
          'Answer with one JSON object and nothing else: {"titles":[{"id":"<slide id>","title":"<conclusion title>"}]}.')


def _brief(slide: dict[str, Any], ev: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {"id": slide["id"], "current_title": slide.get("title") or "", "content": [p[:400] for p in ev["text"][1:40]]}
    if ev["charts"]:
        out["charts"] = ev["charts"]
    if ev["facts"]:
        out["computed_facts"] = [f["text"] for f in ev["facts"]]
    if ev["notes"]:
        out["speaker_notes"] = ev["notes"][:800]
    return out


def _ask(svc: Any, deck: dict[str, Any], briefs: list[dict[str, Any]], feedback: str = "") -> tuple[dict[str, str], Optional[str]]:
    lang = gen.LANG_NAME.get(deck.get("language", "es"), "Spanish (Spain)")
    user = f"Deck: {deck.get('title', '')}\nLanguage: {lang}\n\nSlides:\n{jdump(briefs)}"
    if feedback:
        user += f"\n\n{feedback}"

    def parse(data: Any, strict: bool) -> dict[str, str]:
        items = data.get("titles") if isinstance(data, dict) else data
        if not isinstance(items, list):
            raise ValueError('expected {"titles": [...]}')
        return {str(i.get("id")): _tidy(i.get("title")) for i in items if isinstance(i, dict) and i.get("id")}

    return gen.chat_json(svc, [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}], parse,
                         max_tokens=1200 + 120 * len(briefs), effort="low")


def _candidates(deck: dict[str, Any], state: dict[str, Any], slide_ids: Optional[list[str]], force: bool) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    by_id = {s["id"]: s for s in deck["slides"]}
    if slide_ids:
        for sid in slide_ids:
            if sid not in by_id:
                raise NotFound(f"Slide {sid} does not exist in this deck.")
    chosen, skipped = [], []
    for slide in deck["slides"]:
        if slide_ids and slide["id"] not in slide_ids:
            continue
        reason = None
        if slide.get("layout") in EXEMPT_LAYOUTS:
            reason = "exempt_layout"
        elif not (slide.get("title") or "").strip():
            reason = "no_title"
        elif not force and not is_label(slide["title"]):
            reason = "already_a_conclusion"
        elif not slide_ids and (state["slides"].get(slide["id"]) or {}).get("mode") == "label":
            reason = "kept_as_label"
        if reason:
            skipped.append({"slide_id": slide["id"], "position": slide["position"], "title": slide.get("title") or "", "reason": reason})
        else:
            chosen.append(slide)
    return chosen, skipped


def propose(svc: Any, deck_id: str, slide_ids: Optional[list[str]] = None, *, use_model: bool = True, force: bool = False) -> dict[str, Any]:
    """Write a conclusion title for every label title (or for the given slides) and keep it as a proposal. Nothing on the
    slides changes. Every proposal is checked: a figure that the slide does not hold sends it back once and then to the
    rule-made title; a slide where neither works is reported with the reason."""
    deck = store.deck_view(svc, deck_id)
    lang = deck.get("language", "es")
    state = _state(svc, deck_id)
    chosen, skipped = _candidates(deck, state, slide_ids, force)
    evs = {s["id"]: evidence(s, lang) for s in chosen}
    made: dict[str, tuple[str, str]] = {}
    notes: dict[str, str] = {}
    model: Optional[str] = None
    model_note = None
    if use_model and chosen:
        try:
            for start in range(0, len(chosen), BATCH):
                group = chosen[start:start + BATCH]
                titles, used = _ask(svc, deck, [_brief(s, evs[s["id"]]) for s in group])
                model = used or model
                retry = []
                for slide in group:
                    title = titles.get(slide["id"], "")
                    bad = unbacked(title, evs[slide["id"]]) if title else []
                    if title and not bad and len(title) <= MAX_TITLE_CHARS and not is_label(title):
                        made[slide["id"]] = (title, "model")
                    elif title:
                        retry.append((slide, bad))
                if retry:
                    lines = [f"- {s['id']}: " + (f"these figures are not on the slide: {', '.join(bad)}" if bad else
                                                 f"it must be one statement with a verb, at most {MAX_TITLE_CHARS} characters") for s, bad in retry]
                    again, used = _ask(svc, deck, [_brief(s, evs[s["id"]]) for s, _ in retry],
                                       "Your previous titles for these slides cannot be used:\n" + "\n".join(lines) + "\nWrite them again within the rules.")
                    for slide, _ in retry:
                        title = again.get(slide["id"], "")
                        bad = unbacked(title, evs[slide["id"]]) if title else []
                        if title and not bad and len(title) <= MAX_TITLE_CHARS and not is_label(title):
                            made[slide["id"]] = (title, "model")
                        elif bad:
                            notes[slide["id"]] = "invented_figures: " + ", ".join(bad)
        except gen.ModelDown as error:
            model_note = gen.model_status_note(str(error))
        except CiceroError as error:                              # the model answered, but not with usable JSON
            model_note = str(error)
    proposals = []
    for slide in chosen:
        title, by = made.get(slide["id"], ("", ""))
        if not title:
            ruled = rule_proposal(slide, lang)
            if ruled and _fold(ruled) != _fold(slide["title"]):
                title, by = ruled, "rule"
        entry = dict(state["slides"].get(slide["id"]) or {})
        if title:
            entry.update({"proposal": title, "by": by, "for": slide["title"]})
            proposals.append({"slide_id": slide["id"], "position": slide["position"], "title": slide["title"], "proposal": title, "by": by})
        else:
            entry.pop("proposal", None)
            skipped.append({"slide_id": slide["id"], "position": slide["position"], "title": slide["title"],
                            "reason": notes.get(slide["id"]) or "nothing_to_conclude"})
        state["slides"][slide["id"]] = entry
    _save(svc, deck_id, state, {s["id"] for s in deck["slides"]})
    out = {"deck_id": deck_id, "mode": state["mode"], "proposals": proposals, "skipped": sorted(skipped, key=lambda s: s["position"]),
           "generator": "model" if any(p["by"] == "model" for p in proposals) else "rules", "model": model}
    if model_note:
        out["note"] = model_note
    return out


# ---------------- applying and going back ----------------

def apply(svc: Any, deck_id: str, slide_ids: Optional[list[str]] = None, *, titles: Optional[dict[str, str]] = None,
          use_model: bool = True) -> dict[str, Any]:
    """Put the conclusion in the title of every label slide (or of the given ones) and keep the label to go back to. A
    title given by hand in ``titles`` is checked like a proposal: figures the slide does not hold are refused. Slides
    without a proposal get one first. Applied to the whole deck, it also turns the deck's mode to ``conclusion``."""
    titles = {k: _tidy(v) for k, v in (titles or {}).items() if _tidy(v)}
    deck = store.deck_view(svc, deck_id)
    lang = deck.get("language", "es")
    state = _state(svc, deck_id)
    by_id = {s["id"]: s for s in deck["slides"]}
    for sid in list(slide_ids or []) + list(titles):
        if sid not in by_id:
            raise NotFound(f"Slide {sid} does not exist in this deck.")
    wanted = slide_ids or (list(titles) or None)
    chosen, skipped = _candidates(deck, state, wanted, force=bool(wanted))
    missing = [s["id"] for s in chosen if s["id"] not in titles and (state["slides"].get(s["id"]) or {}).get("for") != s["title"]]
    if missing:
        propose(svc, deck_id, missing, use_model=use_model, force=True)
        state = _state(svc, deck_id)
    applied = []
    for slide in chosen:
        entry = dict(state["slides"].get(slide["id"]) or {})
        new = titles.get(slide["id"]) or (entry.get("proposal") if entry.get("for") == slide["title"] else "")
        reason = None
        if not new:
            reason = "nothing_to_conclude"
        elif len(new) > 200:
            reason = "too_long"
        elif slide["id"] in titles and (bad := unbacked(new, evidence(slide, lang))):
            reason = "invented_figures: " + ", ".join(bad)
        elif new == slide["title"]:
            reason = "unchanged"
        if reason:
            skipped.append({"slide_id": slide["id"], "position": slide["position"], "title": slide["title"], "reason": reason})
            continue
        # the label to go back to is the first one: applying twice must not lose it
        label = entry.get("label") if entry.get("conclusion") == slide["title"] and entry.get("label") else slide["title"]
        store.patch_slide(svc, deck_id, slide["id"], {"title": new}, reason="conclusion title")
        entry.update({"label": label, "conclusion": new, "mode": "conclusion"})
        for key in ("proposal", "by", "for"):
            entry.pop(key, None)
        state["slides"][slide["id"]] = entry
        applied.append({"slide_id": slide["id"], "position": slide["position"], "from": slide["title"], "to": new})
    if not slide_ids and not titles:
        state["mode"] = "conclusion"
        for entry in state["slides"].values():                   # the deck decides again, except where a label was asked for
            if entry.get("mode") == "conclusion":
                entry.pop("mode", None)
    _save(svc, deck_id, state, set(by_id))
    return {"deck_id": deck_id, "mode": state["mode"], "applied": applied, "skipped": sorted(skipped, key=lambda s: s["position"]),
            "undo": "titles_restore puts the labels back; each slide also keeps its revision (slide_revert)."}


def restore(svc: Any, deck_id: str, slide_ids: Optional[list[str]] = None, *, force: bool = False) -> dict[str, Any]:
    """Put the labels back where a conclusion was applied (the whole deck, or the given slides). A title that was edited
    by hand after applying is left as it is unless ``force``. The conclusion stays as a proposal, so it can be applied again."""
    deck = store.deck_view(svc, deck_id)
    state = _state(svc, deck_id)
    by_id = {s["id"]: s for s in deck["slides"]}
    for sid in slide_ids or []:
        if sid not in by_id:
            raise NotFound(f"Slide {sid} does not exist in this deck.")
    restored, skipped = [], []
    for slide in deck["slides"]:
        if slide_ids and slide["id"] not in slide_ids:
            continue
        entry = dict(state["slides"].get(slide["id"]) or {})
        label = entry.get("label")
        if not label:
            if slide_ids:
                entry["mode"] = "label"                          # asked for by name: this slide keeps its label from now on
                state["slides"][slide["id"]] = entry
            continue
        if slide["title"] != entry.get("conclusion") and not force:
            skipped.append({"slide_id": slide["id"], "position": slide["position"], "title": slide["title"], "reason": "edited_since"})
            continue
        if slide["title"] != label:
            store.patch_slide(svc, deck_id, slide["id"], {"title": label}, reason="label title restored")
        entry = {"proposal": entry.get("conclusion"), "by": "kept", "for": label, **({"mode": "label"} if slide_ids else {})}
        state["slides"][slide["id"]] = entry
        restored.append({"slide_id": slide["id"], "position": slide["position"], "from": slide["title"], "to": label})
    if not slide_ids:
        state["mode"] = "label"
        for entry in state["slides"].values():
            entry.pop("mode", None)
    _save(svc, deck_id, state, set(by_id))
    return {"deck_id": deck_id, "mode": state["mode"], "restored": restored, "skipped": skipped}


def overview(svc: Any, deck_id: str) -> dict[str, Any]:
    """The mode of the deck and, slide by slide, whether its title is a label, a proposal waiting, or a conclusion applied."""
    deck = store.deck_view(svc, deck_id)
    slides = [{"slide_id": s["id"], "position": s["position"], "layout": s["layout"], "title": s["title"], **s["titling"]} for s in deck["slides"]]
    return {"deck_id": deck_id, "mode": deck["title_mode"], "slides": slides,
            "labels": sum(1 for s in slides if s["is_label"] and s["own_mode"] != "label"), "applied": sum(1 for s in slides if s["applied"]),
            "proposals": sum(1 for s in slides if s["proposal"])}


def set_mode(svc: Any, deck_id: str, mode: Optional[str], slide_id: Optional[str] = None, *, use_model: bool = True) -> dict[str, Any]:
    """Deck: ``conclusion`` applies conclusion titles to the whole deck, ``label`` puts every label back. Slide: the same
    for one slide (``label`` also makes it keep its label while the deck is in conclusion mode); None lets the slide follow the deck."""
    if mode is not None and mode not in MODES:
        raise CiceroError("mode must be 'label' or 'conclusion'.")
    if slide_id is None:
        if mode is None:
            raise CiceroError("A deck needs a mode: 'label' or 'conclusion'.")
        return apply(svc, deck_id, use_model=use_model) if mode == "conclusion" else restore(svc, deck_id)
    if mode == "conclusion":
        return apply(svc, deck_id, [slide_id], use_model=use_model)
    if mode == "label":
        return restore(svc, deck_id, [slide_id])
    deck = store.deck_view(svc, deck_id)
    if slide_id not in {s["id"] for s in deck["slides"]}:
        raise NotFound(f"Slide {slide_id} does not exist in this deck.")
    state = _state(svc, deck_id)
    (state["slides"].get(slide_id) or {}).pop("mode", None)
    _save(svc, deck_id, state, {s["id"] for s in deck["slides"]})
    return {"deck_id": deck_id, "mode": state["mode"], "slide_id": slide_id, "slide_mode": slide_mode(state, slide_id)}


# ---------------- tool arguments ----------------

class TitlesArgs(BaseModel):
    deck_id: str = Field(..., max_length=40)


class TitlesProposeArgs(TitlesArgs):
    slide_ids: Optional[list[str]] = Field(None, max_length=120, description="Only these slides; omit for every slide whose title is a label.")
    use_model: bool = Field(True, description="False writes them by rule only (chart arithmetic, first metric, first statement of the slide).")
    force: bool = Field(False, description="Also propose for titles that already read as a conclusion.")


class TitlesApplyArgs(TitlesArgs):
    slide_ids: Optional[list[str]] = Field(None, max_length=120, description="Only these slides; omit to apply to the whole deck and turn its mode to conclusion.")
    titles: Optional[dict[str, str]] = Field(None, description="Your own conclusion per slide id, instead of the stored proposal. Figures the slide does not hold are refused.")
    use_model: bool = True


class TitlesRestoreArgs(TitlesArgs):
    slide_ids: Optional[list[str]] = Field(None, max_length=120, description="Only these slides; omit to put every label back and turn the deck's mode to label.")
    force: bool = Field(False, description="Also overwrite titles edited by hand after the conclusion was applied.")


class TitlesModeArgs(TitlesArgs):
    mode: Optional[Literal["label", "conclusion"]] = Field(None, description="Omit with slide_id to let the slide follow the deck again.")
    slide_id: Optional[str] = Field(None, max_length=40)
    use_model: bool = True


def tool_overview(svc: Any, a: TitlesArgs) -> dict:
    return overview(svc, a.deck_id)


def tool_propose(svc: Any, a: TitlesProposeArgs) -> dict:
    return propose(svc, a.deck_id, a.slide_ids, use_model=a.use_model, force=a.force)


def tool_apply(svc: Any, a: TitlesApplyArgs) -> dict:
    return apply(svc, a.deck_id, a.slide_ids, titles=a.titles, use_model=a.use_model)


def tool_restore(svc: Any, a: TitlesRestoreArgs) -> dict:
    return restore(svc, a.deck_id, a.slide_ids, force=a.force)


def tool_mode(svc: Any, a: TitlesModeArgs) -> dict:
    return set_mode(svc, a.deck_id, a.mode, a.slide_id, use_model=a.use_model)
