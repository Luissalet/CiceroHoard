"""The tool catalogue: shape, descriptions, annotations, result cap, confirms, a call to every tool and the MCP bridge."""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from cicero_hoard import agent_tools as at
from cicero_hoard.errors import CiceroError, NotFound, Refused
from conftest import BANNED_WORDS as BANNED, SOURCE_TEXT, png_bytes

ROOT = Path(__file__).resolve().parent.parent

REQUIRED = {"cicero_status", "deck_list", "deck_create", "deck_get", "deck_update", "deck_delete", "source_add", "source_list", "source_get", "source_remove",
            "outline_generate", "outline_update", "slides_generate", "slide_get", "slide_update", "slide_regenerate", "slide_approve", "slide_revert", "slide_add",
            "slide_delete", "slides_reorder", "deck_check", "deck_theme", "deck_export", "slide_image"}
READ_ONLY = {"cicero_status", "deck_list", "deck_get", "source_list", "source_get", "slide_get", "deck_check"}


def test_catalogue_has_every_tool_once():
    names = [t.name for t in at.TOOLS]
    assert set(names) == REQUIRED and len(names) == len(set(names)) == 25


def test_descriptions_are_short_first_lines_and_neutral():
    for spec in at.tool_catalog():
        first = spec["description"].splitlines()[0]
        assert 0 < len(first) <= 110, spec["name"]
        assert spec["inputSchema"]["type"] == "object"
        low = (spec["description"] + json.dumps(spec["inputSchema"])).lower()
        assert not any(b in low for b in BANNED), spec["name"]
    assert not any(b in at.AGENT_INSTRUCTIONS.lower() for b in BANNED)


def test_annotations():
    ann = {t.name: t.annotations for t in at.TOOLS}
    for name in READ_ONLY:
        assert ann[name]["readOnlyHint"] is True, name
    for name in REQUIRED - READ_ONLY - {"deck_theme"}:
        assert ann[name]["readOnlyHint"] is False, name
    for name in ("deck_delete", "slide_delete", "source_remove"):
        assert ann[name]["destructiveHint"] is True, name
    assert ann["slide_image"]["openWorldHint"] is False or ann["slide_image"]["openWorldHint"] is True
    for spec in at.tool_catalog():
        assert set(spec["annotations"]) >= {"readOnlyHint", "destructiveHint", "idempotentHint", "openWorldHint"}


def test_unknown_tool_and_bad_arguments(services):
    with pytest.raises(KeyError):
        at.call_tool(services, "teleport", {})
    with pytest.raises(ValidationError):
        at.call_tool(services, "deck_get", {})
    with pytest.raises(ValidationError):
        at.call_tool(services, "deck_create", {"title": "x", "slide_count": 2})
    with pytest.raises(ValidationError):
        at.call_tool(services, "deck_create", {"title": "x", "surprise": 1})


def test_cap_result_trims_big_lists_and_texts():
    big = {"items": [{"t": "x" * 500} for _ in range(200)], "n": 1}
    out = at.cap_result(big)
    assert len(json.dumps(out)) <= at.RESULT_CAP and out["truncated"] is True and "items" in out["truncated_fields"] and out["hint"]
    text = at.cap_result({"text": "y" * 60000})
    assert len(text["text"]) < 30000 and text["truncated"] is True
    small = {"a": 1}
    assert at.cap_result(small) == {"a": 1} and at.cap_result([1, 2]) == [1, 2]


def test_every_tool_full_flow(services, tmp_path):
    call = lambda _tool, **a: at.call_tool(services, _tool, a, caller="test")  # noqa: E731
    assert call("cicero_status")["service"] == "cicero-hoard"
    d = call("deck_create", title="Flujo", brief="Resumen del trimestre", audience="Dirección", slide_count=5, language="es")
    did = d["id"]
    assert call("deck_list")["items"][0]["id"] == did
    assert call("deck_update", deck_id=did, tone="cercano")["tone"] == "cercano"
    src = call("source_add", deck_id=did, title="Informe", text=SOURCE_TEXT)
    assert src["id"] == 1
    md = tmp_path / "extra.md"
    md.write_text("# Extra\n\nMás texto de apoyo.", encoding="utf-8")
    assert call("source_add", deck_id=did, path=str(md))["kind"] == "markdown"
    assert [s["id"] for s in call("source_list", deck_id=did)["items"]] == [1, 2]
    assert call("source_get", deck_id=did, source_id=1, max_chars=200)["text"].startswith("# Contexto")
    out = call("outline_generate", deck_id=did)
    assert out["generator"] == "model" and len(out["outline"]) == 5
    upd = call("outline_update", deck_id=did, items=[{"title": t, "purpose": "", "points": ["a"]} for t in ("Uno", "Dos", "Tres", "Cuatro", "Cinco")])
    assert [o["title"] for o in upd["outline"]][:2] == ["Uno", "Dos"]
    gen = call("slides_generate", deck_id=did)
    assert gen["generated"] == 5
    summary = call("deck_get", deck_id=did)
    assert set(summary["slides"][0]) >= {"id", "title", "bullets", "has_notes"} and "blocks" in summary["slides"][0] and "notes" not in summary["slides"][0]
    full = call("deck_get", deck_id=did, detail="full")
    assert "notes" in full["slides"][0]
    sid = full["slides"][1]["id"]
    assert call("slide_get", deck_id=did, slide_id=sid)["id"] == sid
    edited = call("slide_update", deck_id=did, slide_id=sid, title="Editada", blocks=[{"type": "bullets", "items": ["Uno", "Dos"]}])
    assert edited["title"] == "Editada" and edited["revision"] == 2
    revs = call("slide_revert", deck_id=did, slide_id=sid)["items"]
    assert [r["revision"] for r in revs] == [2, 1]
    assert call("slide_revert", deck_id=did, slide_id=sid, revision=1)["revision"] == 3
    regen = call("slide_regenerate", deck_id=did, slide_id=sid, feedback="más breve")
    assert regen["revision"] == 4
    assert call("slide_approve", deck_id=did, slide_id=sid)["status"] == "approved"
    assert call("slide_approve", deck_id=did, slide_id=sid, approved=False)["status"] == "draft"
    added = call("slide_add", deck_id=did, after_id=sid, title="Extra", blocks=[{"type": "text", "text": "hola"}], notes="n")
    assert added["position"] == 3
    order = [s["id"] for s in call("deck_get", deck_id=did)["slides"]]
    assert call("slides_reorder", deck_id=did, order=list(reversed(order)))["slides"][0]["id"] == order[-1]
    check = call("deck_check", deck_id=did)
    assert check["warnings"] + check["infos"] == len(check["issues"])
    assert call("deck_theme")["themes"][0]["id"] and call("deck_theme", deck_id=did)["current"] == "claro"
    assert call("deck_theme", deck_id=did, theme="oscuro")["current"] == "oscuro"
    with pytest.raises(CiceroError):
        call("deck_theme", theme="oscuro")
    with pytest.raises(CiceroError):
        call("deck_theme", deck_id=did, theme="nope")
    exp = call("deck_export", deck_id=did, format="md")
    assert Path(exp["path"]).is_file() and exp["download_url"].endswith(f"/api/exports/{exp['export']['id']}/file")
    img = call("slide_image", deck_id=did, slide_id=sid, prompt="un puente")
    assert any(b["type"] == "image" for b in img["blocks"]) and img["image_prompt"] == "un puente"
    assert call("slide_delete", deck_id=did, slide_id=added["id"], confirm=True)["deleted"] is True
    call("source_remove", deck_id=did, source_id=2, confirm=True)
    assert [x["id"] for x in call("source_list", deck_id=did)["items"]] == [1]
    assert call("deck_delete", deck_id=did, confirm=True)["deleted"] is True
    assert call("deck_list")["items"] == []


def test_confirms_are_enforced(services, deck):
    call = lambda _tool, **a: at.call_tool(services, _tool, a)  # noqa: E731
    with pytest.raises(CiceroError) as info:
        call("slide_delete", deck_id=deck["id"], slide_id=deck["slides"][0]["id"])
    assert info.value.code == "confirm_required"
    with pytest.raises(CiceroError) as info:
        call("source_remove", deck_id=deck["id"], source_id=1)
    assert info.value.code == "confirm_required"
    with pytest.raises(CiceroError):
        call("deck_delete", deck_id=deck["id"])
    assert call("deck_get", deck_id=deck["id"])["id"] == deck["id"]


def test_source_add_needs_exactly_one_input(services):
    d = at.call_tool(services, "deck_create", {"title": "x"})
    with pytest.raises(CiceroError):
        at.call_tool(services, "source_add", {"deck_id": d["id"]})
    with pytest.raises(CiceroError):
        at.call_tool(services, "source_add", {"deck_id": d["id"], "text": "a", "path": "b"})


def test_not_found_and_refused(services):
    with pytest.raises(NotFound):
        at.call_tool(services, "deck_get", {"deck_id": "nope"})
    d = at.call_tool(services, "deck_create", {"title": "x"})
    with pytest.raises(Refused):
        at.call_tool(services, "source_add", {"deck_id": d["id"], "path": str(ROOT / "LICENSE")})  # not a document type


def test_deck_get_summary_is_smaller_than_full(services, deck):
    small = len(json.dumps(at.call_tool(services, "deck_get", {"deck_id": deck["id"]})))
    big = len(json.dumps(at.call_tool(services, "deck_get", {"deck_id": deck["id"], "detail": "full"})))
    assert small < big


# ---------------- MCP bridge parity ----------------

def test_bridge_lists_the_catalogue_and_proxies_calls(client, monkeypatch):
    sys.path.insert(0, str(ROOT))
    import httpx
    import mcp_server

    catalog = client.get("/api/agent/tools").json()
    bridge = mcp_server.CiceroBridge(catalog["tools"], catalog["instructions"])
    listed = asyncio.run(bridge.list_tools())
    assert {t.name for t in listed} == {t.name for t in at.TOOLS}
    assert all(t.annotations is not None for t in listed)

    monkeypatch.setenv("CICERO_TOKEN", client.svc.token)

    class FakeAsyncClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None, headers=None):
            return client.post(url.replace(mcp_server.BASE_URL, ""), json=json, headers=headers)

    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    out = asyncio.run(bridge.call_tool("deck_create", {"title": "Vía puente"}))
    assert json.loads(out[0].text)["title"] == "Vía puente"
    err = asyncio.run(bridge.call_tool("deck_get", {"deck_id": "inexistente"}))
    assert "error" in json.loads(err[0].text)
    assert mcp_server._token() == client.svc.token


def test_bridge_refuses_non_local_urls():
    sys.path.insert(0, str(ROOT))
    import mcp_server

    with pytest.raises(SystemExit):
        mcp_server._check_local("http://evil.example:5194")
    mcp_server._check_local("http://127.0.0.1:5194")


def test_bridge_names_a_missing_or_foreign_token_instead_of_a_stopped_app(client, monkeypatch, tmp_path):
    """Seen live: a running app with its data in another folder was reported as 'not running', and the assistant tried
    to start it again."""
    sys.path.insert(0, str(ROOT))
    import httpx
    import mcp_server

    catalog = client.get("/api/agent/tools").json()
    bridge = mcp_server.CiceroBridge(catalog["tools"], catalog["instructions"])
    monkeypatch.delenv("CICERO_TOKEN", raising=False)
    started = []
    monkeypatch.setattr(mcp_server, "ensure_running", lambda *a, **k: started.append(1) or True)
    monkeypatch.setattr(mcp_server, "_healthy", lambda: True)

    class FakeAsyncClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None, headers=None):
            return client.post(url.replace(mcp_server.BASE_URL, ""), json=json, headers=headers)

    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(mcp_server, "TOKEN_FILE", tmp_path / "missing" / "mcp-token")
    missing = json.loads(asyncio.run(bridge.call_tool("deck_list", {}))[0].text)["error"]
    assert "running" in missing and "mcp-token" in missing and not started

    foreign = tmp_path / "mcp-token"
    foreign.write_text("not-the-token", encoding="utf-8")
    monkeypatch.setattr(mcp_server, "TOKEN_FILE", foreign)
    refused = json.loads(asyncio.run(bridge.call_tool("deck_list", {}))[0].text)["error"]
    assert "refused" in refused and "CICERO_TOKEN_FILE" in refused
