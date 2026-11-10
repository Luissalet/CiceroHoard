"""Measured rehearsals: the time each slide stayed on screen while the presenter's timer ran, kept per deck.

The presenter console times every slide; "Guardar ensayo" keeps that run here so the Rehearsal tab can put it next to the plan
made from the notes. Runs live in the deck's settings (newest first, at most ``MAX_RUNS``), never in the slides.
"""
from __future__ import annotations

import time
import uuid
from typing import Literal, Optional

from pydantic import BaseModel, Field

from . import decks as store
from .errors import CiceroError

MAX_RUNS = 20


class RunsArgs(BaseModel):
    deck_id: str = Field(..., max_length=40)
    action: Literal["list", "save", "delete"] = Field("list", description="list: kept runs with the plan beside them; save: keep the timings of the live session now; delete: forget run_id.")
    run_id: Optional[str] = Field(None, max_length=40, description="The run to delete.")
    label: Optional[str] = Field(None, max_length=80, description="A name for the saved run (default: date and time).")
    words_per_minute: int = Field(130, ge=80, le=240, description="Pace of the plan the runs are compared with.")
    pause_seconds: int = Field(10, ge=0, le=120)


def _key(deck_id: str) -> str:
    return "rehearsal_runs:" + deck_id


def _runs(svc, deck_id: str) -> list[dict]:
    return list(svc.db.get_setting(_key(deck_id), []) or [])


def _compare(svc, deck: dict, run: dict, wpm: int, pause: int) -> dict:
    """The run next to the plan for the same limit and main talk: per slide planned slot, measured time and difference."""
    from .rehearsal import rehearsal_plan
    measured = {s["slide_id"]: s["seconds"] for s in run["slides"]}
    titles = {s["id"]: s["title"] for s in deck["slides"]}
    plan = None
    try:
        plan = rehearsal_plan(deck, duration_minutes=max(1, run["target_seconds"]) / 60, words_per_minute=wpm, pause_seconds=pause,
                              main_slides=min(run.get("main_slide_count") or len(deck["slides"]), len(deck["slides"])))
    except CiceroError:
        plan = None
    slots = {t["slide_id"]: t["slot_seconds"] for t in (plan or {}).get("timeline", [])}
    rows = []
    for slide in deck["slides"]:
        seconds = measured.get(slide["id"])
        slot = slots.get(slide["id"])
        rows.append({"slide_id": slide["id"], "position": slide["position"], "title": titles.get(slide["id"], ""),
                     "seconds": seconds, "slot_seconds": slot,
                     "delta_seconds": None if seconds is None or slot is None else round(seconds - slot, 1),
                     "skipped": seconds is None or seconds < 1})
    over = sorted((r for r in rows if r["delta_seconds"] and r["delta_seconds"] > 0), key=lambda r: -r["delta_seconds"])[:3]
    removed = [s["slide_id"] for s in run["slides"] if s["slide_id"] not in titles]
    return {**run, "rows": rows, "over_slot": [{"slide_id": r["slide_id"], "position": r["position"], "title": r["title"],
                                                "delta_seconds": r["delta_seconds"]} for r in over],
            "over_target_seconds": round(run["total_seconds"] - run["target_seconds"], 1),
            "slides_no_longer_in_deck": removed}


def run(svc, a: RunsArgs) -> dict:
    deck = store.deck_view(svc, a.deck_id)
    runs = _runs(svc, a.deck_id)
    if a.action == "save":
        sessions = svc.presentations
        with sessions.lock:
            if a.deck_id not in sessions.rooms:
                raise CiceroError("Open the presenter console and run the timer before saving a rehearsal.", code="no_live_session")
            room = sessions.rooms[a.deck_id]
            sessions.tick(room)
            dwell = sessions.dwell(room)
            elapsed = room["elapsed"] + (max(0, sessions.clock() - room["resumed"]) if room["running"] else 0)
            slides = [{"slide_id": s["id"], "title": s["title"], "seconds": dwell.get(s["id"], 0.0)} for s in room["slides"]]
            target, main = room["target_seconds"], room["main_slide_count"]
        if elapsed < 1 or not any(s["seconds"] >= 1 for s in slides):
            raise CiceroError("The timer has not run yet: start it in the presenter console and go through the slides.", code="empty_rehearsal")
        when = time.strftime("%Y-%m-%d %H:%M", time.localtime())
        saved = {"id": uuid.uuid4().hex[:12], "label": (a.label or "").strip() or when, "saved_at": when,
                 "total_seconds": round(elapsed, 1), "target_seconds": target, "main_slide_count": main, "slides": slides}
        runs = [saved, *runs][:MAX_RUNS]
        svc.db.set_setting(_key(a.deck_id), runs)
        return {"saved": _compare(svc, deck, saved, a.words_per_minute, a.pause_seconds), "count": len(runs)}
    if a.action == "delete":
        if not a.run_id or not any(r["id"] == a.run_id for r in runs):
            raise CiceroError("Name an existing run_id to delete.", code="not_found")
        runs = [r for r in runs if r["id"] != a.run_id]
        svc.db.set_setting(_key(a.deck_id), runs)
        return {"deleted": a.run_id, "count": len(runs)}
    return {"runs": [_compare(svc, deck, r, a.words_per_minute, a.pause_seconds) for r in runs], "count": len(runs),
            "basis": "time on screen while the presenter timer ran"}
