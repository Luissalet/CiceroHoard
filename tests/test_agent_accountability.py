"""Agent sessions: mandatory reasons, the write journal, undoing a whole session and the token profiles, on the real app."""
from __future__ import annotations

import json

import pytest

from conftest import SOURCE_TEXT, new_deck
from cicero_hoard import decks, generate
from cicero_hoard.errors import NotFound
from cicero_hoard.hoard_link import tokens as link_tokens


def agent_call(client, name, arguments=None, *, agent="agent-a", session="s1", reason="Because the person asked for it", token=None, **extra):
    headers = {"Authorization": f"Bearer {token or client.svc.token}", "X-Agent-Id": agent, "X-Agent-Session": session}
    body = {"name": name, "arguments": arguments or {}}
    if reason is not None:
        body["reason"] = reason
    body.update(extra)
    return client.post("/api/agent/call", json=body, headers=headers)


def ok(response):
    assert response.status_code == 200, response.text
    return response.json()


def undo(client, session, *, agent="agent-a", token=None, **body):
    headers = {"Authorization": f"Bearer {token or client.svc.token}", "X-Agent-Id": agent}
    if body.get("confirm"):
        body.setdefault("reason", "Taking the session back")
    return client.post("/api/agent/undo", json={"session": session, **body}, headers=headers)


def journal(client, **params):
    return client.get("/api/agent/journal", params=params, headers={"Authorization": f"Bearer {client.svc.token}"}).json()


def view(client, deck_id):
    return decks.deck_view(client.svc, deck_id)


def slide_of(client, deck_id, index=0):
    return view(client, deck_id)["slides"][index]


@pytest.fixture
def ready(client):
    """A deck with a source, an outline and generated slides, made by the services (not by an agent)."""
    d = new_deck(client.svc)
    decks.add_source_text(client.svc, d["id"], "Informe interno", SOURCE_TEXT)
    generate.generate_outline(client.svc, d["id"])
    generate.generate_slides(client.svc, d["id"])
    return view(client, d["id"])


# ---------------------------------------------------------------- reasons

def test_a_write_without_a_reason_is_refused_with_a_hint(client):
    r = agent_call(client, "deck_create", {"title": "Sin motivo"}, reason=None)
    assert r.status_code == 400 and r.json()["code"] == "reason_required" and r.json()["hint"]
    assert agent_call(client, "deck_create", {"title": "Sin motivo"}, reason="no").status_code == 400          # shorter than 3 characters
    assert ok(agent_call(client, "deck_list", reason=None)) == {"items": []}                                   # reads need no reason, and nothing was made


def test_the_web_ui_is_exempt_from_reasons(client):
    r = client.post("/api/decks", json={"title": "Desde la interfaz"})
    assert r.status_code in (200, 201) and r.json()["title"] == "Desde la interfaz"
    assert journal(client)["entries"] == []                       # the interface is not an agent: nothing in the agent journal


def test_the_catalogue_tells_agents_about_reasons_and_draft_safe_tools(client):
    tools = {t["name"]: t for t in client.get("/api/agent/tools", headers={"Authorization": f"Bearer {client.svc.token}"}).json()["tools"]}
    assert "reason" in tools["deck_create"]["inputSchema"]["properties"] and "reason" not in tools["deck_list"]["inputSchema"]["properties"]
    assert tools["slide_update"]["annotations"]["draftSafeHint"] is True
    for name in ("slide_delete", "deck_delete", "slide_approve", "deck_export", "slides_generate", "outline_update"):
        assert "draftSafeHint" not in tools[name]["annotations"], name


# ---------------------------------------------------------------- a session creates a deck and edits slides, then undoes it all

def test_undoing_a_session_restores_the_state_before_it(client):
    deck_id = ok(agent_call(client, "deck_create", {"title": "Presentación de la sesión", "slide_count": 4}))["id"]
    first = ok(agent_call(client, "slide_add", {"deck_id": deck_id, "title": "Uno", "blocks": [{"type": "bullets", "items": ["a", "b"]}]}))
    ok(agent_call(client, "slide_add", {"deck_id": deck_id, "title": "Dos"}))
    sid = slide_of(client, deck_id)["id"]
    assert first
    ok(agent_call(client, "slide_edit_text", {"deck_id": deck_id, "slide_id": sid, "field": "title", "text": "Uno editado"}))
    ok(agent_call(client, "slide_edit_text", {"deck_id": deck_id, "slide_id": sid, "field": "notes", "text": "Notas nuevas."}))
    assert slide_of(client, deck_id)["title"] == "Uno editado"

    entries = journal(client, session="s1")["entries"]
    assert sorted(e["tool"] for e in entries) == ["deck_create", "slide_add", "slide_add", "slide_edit_text", "slide_edit_text"]
    assert all(e["agent"] == "agent-a" and e["reason"] and e["ok"] and e["kind"] == "write" for e in entries)

    dry = ok(undo(client, "s1", dry_run=True))
    assert dry["complete"] is True and len(dry["would_undo"]) == 5 and view(client, deck_id)["title"] == "Presentación de la sesión"
    refused = undo(client, "s1")                                    # no confirm: nothing happens
    assert refused.status_code == 400 and refused.json()["code"] == "confirm_required"
    assert slide_of(client, deck_id)["title"] == "Uno editado"

    done = ok(undo(client, "s1", confirm=True, reason="The person did not want this deck"))
    assert len(done["undone"]) == 5 and not done["conflicts"] and not done["not_undoable"] and done["complete"] is True
    with pytest.raises(NotFound):
        view(client, deck_id)                                        # the deck the session created is gone again
    kinds = [e["kind"] for e in journal(client, session="s1")["entries"]]
    assert kinds.count("undo") == 5 and kinds.count("write") == 5
    assert ok(undo(client, "s1", confirm=True))["undone"] == []        # a second go finds nothing left to do


def test_undo_puts_slide_text_notes_and_deck_fields_back(client, ready):
    deck_id, sid = ready["id"], ready["slides"][0]["id"]
    before = slide_of(client, deck_id)
    ok(agent_call(client, "slide_edit_text", {"deck_id": deck_id, "slide_id": sid, "field": "title", "text": "Otro título"}))
    ok(agent_call(client, "slide_update", {"deck_id": deck_id, "slide_id": sid, "notes": "Notas distintas. Dos. Tres."}))
    ok(agent_call(client, "deck_update", {"deck_id": deck_id, "title": "Título nuevo"}))
    done = ok(undo(client, "s1", confirm=True))
    assert len(done["undone"]) == 3 and done["complete"] is True
    after = slide_of(client, deck_id)
    assert after["title"] == before["title"] and after["notes"] == before["notes"] and after["blocks"] == before["blocks"]
    assert view(client, deck_id)["title"] == ready["title"]


def test_undo_restores_a_deleted_slide_in_place(client, ready):
    deck_id = ready["id"]
    ids = [s["id"] for s in ready["slides"]]
    ok(agent_call(client, "slide_delete", {"deck_id": deck_id, "slide_id": ids[1], "confirm": True}))
    assert len(view(client, deck_id)["slides"]) == len(ids) - 1
    ok(undo(client, "s1", confirm=True))
    back = view(client, deck_id)["slides"]
    assert [s["id"] for s in back] == ids and back[1]["title"] == ready["slides"][1]["title"]


def test_undo_reorders_and_removes_added_slides_and_their_batch_receipt(client, ready):
    deck_id = ready["id"]
    ids = [s["id"] for s in ready["slides"]]
    ok(agent_call(client, "slides_reorder", {"deck_id": deck_id, "order": list(reversed(ids))}))
    ok(agent_call(client, "slides_add", {"deck_id": deck_id, "batch_key": "lote-1", "slides": [{"title": "Extra 1"}, {"title": "Extra 2"}]}))
    assert len(view(client, deck_id)["slides"]) == len(ids) + 2
    done = ok(undo(client, "s1", confirm=True))
    assert len(done["undone"]) == 2 and done["complete"] is True
    assert [s["id"] for s in view(client, deck_id)["slides"]] == ids
    # the receipt went with the batch, so the same key can be used again and really adds the slides
    ok(agent_call(client, "slides_add", {"deck_id": deck_id, "batch_key": "lote-1", "slides": [{"title": "Extra 1"}, {"title": "Extra 2"}]}, session="s2"))
    assert len(view(client, deck_id)["slides"]) == len(ids) + 2


def test_undo_takes_back_an_outline_a_generated_slide_set_and_a_source(client):
    deck_id = new_deck(client.svc)["id"]
    ok(agent_call(client, "source_add", {"deck_id": deck_id, "title": "Informe", "text": SOURCE_TEXT}))
    ok(agent_call(client, "outline_generate", {"deck_id": deck_id}))
    ok(agent_call(client, "slides_generate", {"deck_id": deck_id}))
    assert view(client, deck_id)["slides"]
    plan = ok(undo(client, "s1", dry_run=True))
    assert plan["complete"] is True and len(plan["would_undo"]) == 3
    ok(undo(client, "s1", confirm=True))
    state = view(client, deck_id)
    assert state["slides"] == [] and state["sources"] == []


# ---------------------------------------------------------------- sessions do not touch each other

def test_a_later_edit_by_another_session_is_a_conflict_and_is_left_alone(client, ready):
    deck_id, sid = ready["id"], ready["slides"][0]["id"]
    original = slide_of(client, deck_id)["title"]
    ok(agent_call(client, "slide_edit_text", {"deck_id": deck_id, "slide_id": sid, "field": "title", "text": "Edición de A"}, session="sa", agent="agent-a"))
    ok(agent_call(client, "slide_edit_text", {"deck_id": deck_id, "slide_id": sid, "field": "title", "text": "Edición de B"}, session="sb", agent="agent-b"))

    plan = ok(undo(client, "sa", dry_run=True))
    assert plan["would_undo"] == [] and len(plan["conflicts"]) == 1 and plan["complete"] is False
    done = ok(undo(client, "sa", confirm=True))
    assert done["undone"] == [] and len(done["conflicts"]) == 1
    assert slide_of(client, deck_id)["title"] == "Edición de B"        # the other session's work survived
    assert [e["kind"] for e in journal(client, session="sb")["entries"]] == ["write"]

    # once B is undone, A's edit can be taken back as well
    ok(undo(client, "sb", agent="agent-b", confirm=True))
    assert slide_of(client, deck_id)["title"] == "Edición de A"
    ok(undo(client, "sa", confirm=True))
    assert slide_of(client, deck_id)["title"] == original


def test_a_change_made_outside_the_session_is_a_conflict_too(client, ready):
    deck_id, sid = ready["id"], ready["slides"][0]["id"]
    ok(agent_call(client, "slide_edit_text", {"deck_id": deck_id, "slide_id": sid, "field": "title", "text": "Del agente"}))
    r = client.patch(f"/api/decks/{deck_id}/slides/{sid}", json={"title": "De la persona"})
    assert r.status_code == 200, r.text
    done = ok(undo(client, "s1", confirm=True))
    assert done["undone"] == [] and len(done["conflicts"]) == 1
    assert slide_of(client, deck_id)["title"] == "De la persona"


def test_tools_without_a_way_back_are_reported_not_undone(client, ready):
    deck_id = ready["id"]
    ok(agent_call(client, "deck_update", {"deck_id": deck_id, "audience": "Nueva audiencia"}))
    ok(agent_call(client, "deck_delete", {"deck_id": deck_id, "confirm": True}))
    done = ok(undo(client, "s1", confirm=True))
    assert [n["tool"] for n in done["not_undoable"]] == ["deck_delete"]
    assert done["complete"] is False


# ---------------------------------------------------------------- tokens and profiles

def mint(client, agent, profile):
    return link_tokens.mint_agent_token(client.svc.config.data_dir, agent, profile)["token"]


def test_a_read_only_token_cannot_write(client, ready):
    token = mint(client, "reader", "read_only")
    assert ok(agent_call(client, "deck_list", token=token, agent="spoofed"))["items"]
    r = agent_call(client, "deck_update", {"deck_id": ready["id"], "title": "No"}, token=token)
    assert r.status_code == 403 and r.json()["code"] == "profile_forbidden"
    assert view(client, ready["id"])["title"] == ready["title"]


def test_a_drafts_token_may_edit_drafts_but_not_delete_or_publish(client, ready):
    token = mint(client, "drafter", "drafts")
    deck_id, sid = ready["id"], ready["slides"][0]["id"]
    ok(agent_call(client, "slide_edit_text", {"deck_id": deck_id, "slide_id": sid, "field": "title", "text": "Borrador"}, token=token))
    ok(agent_call(client, "slide_add", {"deck_id": deck_id, "title": "Nueva"}, token=token))
    for name, args in (("slide_delete", {"deck_id": deck_id, "slide_id": sid, "confirm": True}),
                       ("deck_delete", {"deck_id": deck_id, "confirm": True}),
                       ("slide_approve", {"deck_id": deck_id, "slide_id": sid}),
                       ("slides_generate", {"deck_id": deck_id}),
                       ("deck_export", {"deck_id": deck_id, "format": "pdf"})):
        r = agent_call(client, name, args, token=token)
        assert r.status_code == 403 and r.json()["code"] == "profile_forbidden", name
    assert len(view(client, deck_id)["slides"]) == len(ready["slides"]) + 1
    # the token fixes the agent: the journal says "drafter" whatever the headers claim
    assert {e["agent"] for e in journal(client)["entries"]} == {"drafter"}
    # a drafts token may not undo (only the "all" profile can)
    assert undo(client, "s1", token=token, confirm=True).status_code == 403


def test_an_all_token_can_undo_its_own_session(client, ready):
    token = mint(client, "writer", "all")
    sid = ready["slides"][0]["id"]
    ok(agent_call(client, "slide_edit_text", {"deck_id": ready["id"], "slide_id": sid, "field": "title", "text": "Con token"}, token=token))
    done = ok(undo(client, "s1", token=token, confirm=True))
    assert len(done["undone"]) == 1 and slide_of(client, ready["id"])["title"] == ready["slides"][0]["title"]


# ---------------------------------------------------------------- the journal itself

def test_the_journal_records_who_why_and_masks_secrets(client):
    ok(agent_call(client, "deck_create", {"title": "Con secreto", "brief": "token sk-abcdefghijklmnopqrstuvwxyz0123456789 en el texto"},
                  reason="Prepare the deck; password=hunter2hunter2", agent="agent-z", session="zz"))
    entry = journal(client, agent="agent-z")["entries"][0]
    assert entry["tool"] == "deck_create" and entry["session"] == "zz" and entry["ok"] and entry["ids"]
    text = json.dumps(entry)
    assert "sk-abcdefghij" not in text and "hunter2hunter2" not in text
    assert len(entry["args_summary"]) <= 300
    assert client.get("/api/agent/journal").status_code == 401


def test_failed_writes_are_journaled_but_never_undone(client, ready):
    r = agent_call(client, "slide_edit_text", {"deck_id": ready["id"], "slide_id": "ghost", "field": "title", "text": "x"})
    assert r.status_code == 404
    entries = journal(client, session="s1")["entries"]
    assert entries and entries[0]["ok"] is False
    assert ok(undo(client, "s1", confirm=True))["undone"] == []
