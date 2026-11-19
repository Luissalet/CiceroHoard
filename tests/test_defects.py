"""Slide defects sent back by a rehearsal: received, shown by deck_check, closed when the next verdict no longer has them, undoable."""
from __future__ import annotations

import pytest

from cicero_hoard import agent_tools, decks
from cicero_hoard.errors import CiceroError


def _call(svc, name, args):
    return agent_tools.call_tool(svc, name, args)


def _two_slides(services):
    deck = _call(services, "deck_create", {"title": "Impresoras", "language": "es"})
    weak = decks.add_slide(services, deck["id"], title="Capacidad de color", blocks=[{"type": "bullets", "items": ["Hasta 16 colores"]}])
    fine = decks.add_slide(services, deck["id"], title="Volumen", blocks=[{"type": "bullets", "items": ["350 mm"]}])
    return deck, weak, fine


OBJECTION = {"objection": "¿Hacen falta cuatro unidades para llegar a 16 colores?",
             "expected": "Sí: un CFS admite cuatro colores; 16 requieren cuatro unidades.",
             "evidence": ["Un CFS admite cuatro colores. La capacidad de 16 requiere cuatro unidades en total."],
             "ref": "hoard://hypatia/question/q1"}


def test_received_defect_shows_in_check_and_closes_when_the_verdict_drops_it(services):
    deck, weak, fine = _two_slides(services)
    got = _call(services, "deck_defects_receive", {"deck_id": deck["id"], "origin": "hypatia:rehearsal/s1",
                                                    "defects": [{"slide_id": weak["id"], **OBJECTION}]})
    assert len(got["opened"]) == 1 and got["open_total"] == 1 and not got["resolved"]

    issues = [i for i in services.check(deck["id"])["issues"] if i["kind"] == "rehearsal_objection"]
    assert [i["slide_id"] for i in issues] == [weak["id"]] and issues[0]["severity"] == "warning"
    assert "16 colores" in issues[0]["message"] and "cambiado" not in issues[0]["message"]

    listed = _call(services, "deck_defects", {"deck_id": deck["id"]})
    row = listed["defects"][0]
    assert row["position"] == weak["position"] and row["evidence"] == OBJECTION["evidence"] and row["slide_changed"] is False

    # the slide is fixed: the check still flags it, saying it changed, until the rehearsal runs again
    _call(services, "slide_edit_text", {"deck_id": deck["id"], "slide_id": weak["id"], "field": "notes",
                                        "text": "Cada CFS admite cuatro colores: 16 colores exigen cuatro unidades."})
    issues = [i for i in services.check(deck["id"])["issues"] if i["kind"] == "rehearsal_objection"]
    assert len(issues) == 1 and "cambiado" in issues[0]["message"]
    assert _call(services, "deck_defects", {"deck_id": deck["id"]})["defects"][0]["slide_changed"] is True

    again = _call(services, "deck_defects_receive", {"deck_id": deck["id"], "origin": "hypatia:rehearsal/s1", "defects": []})
    assert again["resolved"] == got["opened"] and again["open_total"] == 0
    assert not [i for i in services.check(deck["id"])["issues"] if i["kind"] == "rehearsal_objection"]
    closed = _call(services, "deck_defects", {"deck_id": deck["id"], "include_resolved": True})["defects"]
    assert closed[0]["status"] == "resolved" and closed[0]["resolved_by"] == "hypatia:rehearsal/s1"


def test_same_objection_is_one_defect_and_other_origins_are_left_alone(services):
    deck, weak, fine = _two_slides(services)
    _call(services, "deck_defects_receive", {"deck_id": deck["id"], "origin": "a", "defects": [{"slide_id": weak["id"], **OBJECTION}]})
    _call(services, "deck_defects_receive", {"deck_id": deck["id"], "origin": "b", "defects": [{"slide_id": fine["id"], "objection": "¿Y la purga?"}]})
    second = _call(services, "deck_defects_receive", {"deck_id": deck["id"], "origin": "a", "defects": [{"slide_id": weak["id"], **OBJECTION}]})
    assert second["still_open"] and not second["opened"] and second["open_total"] == 2
    rows = _call(services, "deck_defects", {"deck_id": deck["id"]})["defects"]
    assert sorted(r["origin"] for r in rows) == ["a", "b"] and next(r for r in rows if r["origin"] == "a")["times_flagged"] == 2


def test_unknown_slide_is_refused(services):
    deck, weak, fine = _two_slides(services)
    with pytest.raises(CiceroError):
        _call(services, "deck_defects_receive", {"deck_id": deck["id"], "origin": "a", "defects": [{"slide_id": "nope", "objection": "x"}]})
    assert _call(services, "deck_defects", {"deck_id": deck["id"]})["defects"] == []


def test_receiving_is_undoable_through_the_agent_session(client):
    svc = client.svc
    deck, weak, fine = _two_slides(svc)
    headers = {"Authorization": f"Bearer {svc.token}", "X-Agent-Id": "agent-a", "X-Agent-Session": "rehearsal"}
    response = client.post("/api/agent/call", headers=headers, json={"name": "deck_defects_receive", "reason": "Rehearsal verdict",
                           "arguments": {"deck_id": deck["id"], "origin": "a", "defects": [{"slide_id": weak["id"], **OBJECTION}]}})
    assert response.status_code == 200, response.text
    assert _call(svc, "deck_defects", {"deck_id": deck["id"]})["open"] == 1
    done = client.post("/api/agent/undo", headers=headers, json={"session": "rehearsal", "confirm": True, "reason": "Take it back"})
    assert done.status_code == 200 and len(done.json()["undone"]) == 1, done.text
    assert _call(svc, "deck_defects", {"deck_id": deck["id"], "include_resolved": True})["defects"] == []


def test_deleting_the_deck_forgets_its_defects(services):
    deck, weak, fine = _two_slides(services)
    _call(services, "deck_defects_receive", {"deck_id": deck["id"], "origin": "a", "defects": [{"slide_id": weak["id"], **OBJECTION}]})
    decks.delete_deck(services, deck["id"], confirm=True)
    assert services.db.get_setting("defects:" + deck["id"]) is None
