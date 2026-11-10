"""Measured rehearsals: time on screen per slide while the presenter timer runs, kept beside the plan."""
from __future__ import annotations

import pytest

from cicero_hoard import decks
from cicero_hoard.agent_tools import call_tool
from cicero_hoard.errors import CiceroError
from conftest import new_deck


def three_slides(svc):
    deck = new_deck(svc)
    ids = [decks.add_slide(svc, deck["id"], title=f"S{i}", blocks=[{"type": "text", "text": "x"}], notes="palabra " * (40 * (i + 1)))["id"] for i in range(3)]
    return deck, ids


def test_time_counts_only_while_the_timer_runs(services):
    now = [1000.0]
    services.presentations.clock = lambda: now[0]
    deck, ids = three_slides(services)
    control = lambda action, **kw: call_tool(services, "deck_live_control", {"deck_id": deck["id"], "action": action, **kw})  # noqa: E731
    call_tool(services, "deck_live_start", {"deck_id": deck["id"], "target_seconds": 120})
    now[0] += 50  # timer still paused: nothing is measured
    control("resume"); now[0] += 30
    state = control("next")
    assert state["slide_seconds"][ids[0]] == 30 and state["current_slide_seconds"] == 0
    now[0] += 45; control("pause"); now[0] += 100; control("resume"); now[0] += 5
    state = control("previous"); now[0] += 10
    assert call_tool(services, "deck_live_state", {"deck_id": deck["id"]})["slide_seconds"] == {ids[0]: 40, ids[1]: 50}
    saved = call_tool(services, "deck_rehearsal_runs", {"deck_id": deck["id"], "action": "save", "label": "Primer ensayo"})["saved"]
    assert saved["label"] == "Primer ensayo" and saved["total_seconds"] == 90 and saved["target_seconds"] == 120
    rows = {r["slide_id"]: r for r in saved["rows"]}
    assert rows[ids[0]]["seconds"] == 40 and rows[ids[2]]["skipped"] and rows[ids[0]]["slot_seconds"] > 0
    assert rows[ids[0]]["delta_seconds"] == round(40 - rows[ids[0]]["slot_seconds"], 1)
    listed = call_tool(services, "deck_rehearsal_runs", {"deck_id": deck["id"]})
    assert listed["count"] == 1 and listed["runs"][0]["id"] == saved["id"]
    control("reset")
    assert call_tool(services, "deck_live_state", {"deck_id": deck["id"]})["slide_seconds"] == {}
    gone = call_tool(services, "deck_rehearsal_runs", {"deck_id": deck["id"], "action": "delete", "run_id": saved["id"]})
    assert gone["count"] == 0


def test_saving_needs_a_session_that_ran(services):
    deck, _ = three_slides(services)
    with pytest.raises(CiceroError):
        call_tool(services, "deck_rehearsal_runs", {"deck_id": deck["id"], "action": "save"})
    call_tool(services, "deck_live_start", {"deck_id": deck["id"]})
    with pytest.raises(CiceroError):
        call_tool(services, "deck_rehearsal_runs", {"deck_id": deck["id"], "action": "save"})


def test_runs_over_http(client):
    deck = client.post("/api/decks", json={"title": "Ensayo", "slide_count": 3}).json()
    assert client.get(f"/api/decks/{deck['id']}/rehearsal/runs").json() == {"runs": [], "count": 0,
                                                                            "basis": "time on screen while the presenter timer ran"}
    assert client.post(f"/api/decks/{deck['id']}/rehearsal/runs", json={}).status_code == 400
