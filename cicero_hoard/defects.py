"""Slide defects sent back by another station: a slide plus the objection it did not withstand.

A rehearsal station (Hypatia's objection rehearsal) checks each slide against hard questions and sends back the ones whose content
does not answer them. Each defect names the slide, the objection, the expected answer and the evidence behind it, and where it came
from (``origin``). Receiving a station's list again is its complete current verdict: open defects of that origin that are not in the
new list are closed as resolved, so fixing the slide and re-running the rehearsal clears the warning. Objections the station could
not judge this time are named in ``pending``: their open defects stay as they are, since no verdict is not a fix. Defects live in the deck's
settings (``defects:<deck>``), never in the slides; open ones show up in ``deck_check`` as ``rehearsal_objection`` warnings.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Optional

from pydantic import BaseModel, Field

from . import decks as store
from .errors import CiceroError
from .hoard_link.agentkit import AppError

MAX_DEFECTS = 400
#: what a slide says, without its approval: approving a slide is not fixing it
FINGERPRINT_FIELDS = tuple(f for f in store.SLIDE_CONTENT_FIELDS if f != "status")

MSG = {
    "es": {"open": "Objeción del ensayo sin respuesta en la diapositiva: «{objection}».",
           "changed": " La diapositiva ha cambiado desde entonces: repite el ensayo para cerrarla."},
    "en": {"open": "Rehearsal objection the slide does not answer: \"{objection}\".",
           "changed": " The slide has changed since: run the rehearsal again to close it."},
}


class DefectIn(BaseModel):
    slide_id: str = Field(..., min_length=1, max_length=40, description="The slide that did not withstand the objection.")
    objection: str = Field(..., min_length=1, max_length=2000, description="The hard question, as asked.")
    expected: str = Field("", max_length=4000, description="The answer the slide should support.")
    feedback: str = Field("", max_length=4000, description="Why the slide failed (what the check said).")
    missing: list[str] = Field(default_factory=list, max_length=20, description="Points of the expected answer the slide lacks.")
    evidence: list[str] = Field(default_factory=list, max_length=10, description="Quotes from the sources that back the expected answer.")
    ref: str = Field("", max_length=300, description="The objection in its own station (e.g. hoard://hypatia/question/<id>).")
    key: str = Field("", max_length=100, description="Stable id of the objection in its origin; default: slide and objection text.")


class ReceiveArgs(BaseModel):
    deck_id: str = Field(..., min_length=1, max_length=40)
    origin: str = Field(..., min_length=1, max_length=200,
                        description="Who sends them, stable across runs (e.g. hypatia:rehearsal/<subject id>).")
    defects: list[DefectIn] = Field(default_factory=list, max_length=200,
                                    description="Every slide that fails now. An empty list closes all open defects of this origin.")
    pending: list[str] = Field(default_factory=list, max_length=400,
                               description="Keys of objections not judged this time: their open defects stay open, none is opened.")


class ListArgs(BaseModel):
    deck_id: str = Field(..., min_length=1, max_length=40)
    slide_id: Optional[str] = Field(None, max_length=40, description="Only this slide.")
    include_resolved: bool = Field(False, description="Also the defects already closed.")


def _key(deck_id: str) -> str:
    return "defects:" + deck_id


def _all(svc, deck_id: str) -> list[dict]:
    return list(svc.db.get_setting(_key(deck_id), []) or [])


def fingerprint(slide: dict[str, Any]) -> str:
    content = {k: slide.get(k) for k in FINGERPRINT_FIELDS}
    return hashlib.sha256(json.dumps(content, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()[:16]


def _defect_key(d: DefectIn) -> str:
    if d.key.strip():
        return d.key.strip()
    return hashlib.sha256(f"{d.slide_id}\n{' '.join(d.objection.split()).casefold()}".encode()).hexdigest()[:16]


def digest(items: list[dict]) -> str:
    return hashlib.sha256(json.dumps(items, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()[:16]


def receive(svc, a: ReceiveArgs) -> dict:
    deck = store.deck_view(svc, a.deck_id)
    slides = {s["id"]: s for s in deck["slides"]}
    unknown = sorted({d.slide_id for d in a.defects if d.slide_id not in slides})
    if unknown:
        raise CiceroError(f"These slides are not in deck {a.deck_id}: {', '.join(unknown)}. Read deck_get for the slide ids.",
                          code="unknown_slide")
    now = svc.clock()
    items = _all(svc, a.deck_id)
    by_key = {(i["origin"], i["key"]): i for i in items}
    seen, opened, kept, reopened = set(), [], [], []
    for d in a.defects:
        k = (a.origin, _defect_key(d))
        if k in seen:
            continue
        seen.add(k)
        fields = {"slide_id": d.slide_id, "objection": d.objection.strip(), "expected": d.expected.strip(), "feedback": d.feedback.strip(),
                  "missing": d.missing, "evidence": d.evidence, "ref": d.ref, "slide_fingerprint": fingerprint(slides[d.slide_id]),
                  "updated_at": now}
        current = by_key.get(k)
        if current is None:
            current = {"id": hashlib.sha256(f"{a.deck_id}|{k[0]}|{k[1]}".encode()).hexdigest()[:12], "origin": a.origin, "key": k[1],
                       "status": "open", "opened_at": now, "resolved_at": None, "times_flagged": 1, **fields}
            items.append(current)
            opened.append(current["id"])
        else:
            if current["status"] != "open":
                reopened.append(current["id"])
            else:
                kept.append(current["id"])
            current.update(fields, status="open", resolved_at=None, times_flagged=int(current.get("times_flagged") or 1) + 1)
    unjudged = {(a.origin, k.strip()) for k in a.pending if k.strip()} - seen
    resolved, pending = [], []
    for item in items:
        if item["origin"] != a.origin or item["status"] != "open" or (item["origin"], item["key"]) in seen:
            continue
        if (item["origin"], item["key"]) in unjudged:
            pending.append(item["id"])
        else:
            item.update(status="resolved", resolved_at=now, resolved_by=a.origin)
            resolved.append(item["id"])
    if len(items) > MAX_DEFECTS:  # forget the oldest closed ones first
        closed = sorted((i for i in items if i["status"] != "open"), key=lambda i: i.get("resolved_at") or 0)
        drop = {i["id"] for i in closed[: len(items) - MAX_DEFECTS]}
        items = [i for i in items if i["id"] not in drop]
    svc.db.set_setting(_key(a.deck_id), items)
    svc.emit("cicero.deck.defects", {"id": a.deck_id, "origin": a.origin, "open": len(seen) + len(pending), "resolved": len(resolved)})
    return {"deck_id": a.deck_id, "origin": a.origin, "opened": opened, "reopened": reopened, "still_open": kept, "resolved": resolved,
            "pending": pending,
            "open_total": sum(1 for i in items if i["status"] == "open"),
            "next": "Fix each slide (slide_edit_text / slide_update), then run the rehearsal check again: it closes what now holds."}


def listing(svc, a: ListArgs) -> dict:
    deck = store.deck_view(svc, a.deck_id)
    slides = {s["id"]: s for s in deck["slides"]}
    rows = []
    for item in _all(svc, a.deck_id):
        if a.slide_id and item["slide_id"] != a.slide_id:
            continue
        if item["status"] != "open" and not a.include_resolved:
            continue
        slide = slides.get(item["slide_id"])
        rows.append({**item, "position": slide["position"] if slide else None, "title": slide["title"] if slide else "",
                     "slide_exists": slide is not None,
                     "slide_changed": slide is not None and fingerprint(slide) != item.get("slide_fingerprint")})
    rows.sort(key=lambda r: (r["status"] != "open", r["position"] or 0))
    return {"deck_id": a.deck_id, "defects": rows, "open": sum(1 for r in rows if r["status"] == "open"),
            "basis": "objections sent back by a rehearsal station; receiving its verdict again closes what now holds"}


def check_issues(svc, deck: dict[str, Any]) -> list[dict[str, Any]]:
    """Open defects as deck_check warnings (kind rehearsal_objection)."""
    m = MSG.get(deck.get("language", "es"), MSG["es"])
    slides = {s["id"]: s for s in deck.get("slides", [])}
    issues = []
    for item in _all(svc, deck["id"]):
        slide = slides.get(item["slide_id"])
        if item["status"] != "open" or slide is None:
            continue
        objection = item["objection"] if len(item["objection"]) <= 160 else item["objection"][:157] + "…"
        message = m["open"].format(objection=objection)
        if fingerprint(slide) != item.get("slide_fingerprint"):
            message += m["changed"]
        issues.append({"slide_id": slide["id"], "kind": "rehearsal_objection", "severity": "warning", "message": message,
                       "position": slide["position"], "defect_id": item["id"], "origin": item["origin"]})
    return issues


# ---------------------------------------------------------------- undo (see agent_undo.py)

def capture(svc, args) -> dict:
    return {"deck_id": args.deck_id, "items": _all(svc, args.deck_id)}


def track(svc, args, result) -> dict:
    return {"objects": [f"deck:{args.deck_id}/defects"], "ids": [f"deck_id={args.deck_id}"], "etag": digest(_all(svc, args.deck_id))}


def undo(svc, record: dict, dry_run: bool = False) -> dict:
    before = record.get("before") if isinstance(record.get("before"), dict) else {}
    deck_id = before.get("deck_id")
    if not deck_id:
        return {"unchanged": True}
    if digest(_all(svc, deck_id)) != record.get("etag"):
        raise AppError("conflict", "The deck's defects changed after this write.",
                       hint="Read deck_defects before undoing anything else.")
    if dry_run:
        return {"would_restore_defects": len(before.get("items") or [])}
    svc.db.set_setting(_key(deck_id), before.get("items") or [])
    return {"restored_defects": len(before.get("items") or [])}
