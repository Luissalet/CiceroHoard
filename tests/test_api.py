"""The HTTP surface end to end (no network, fake model): guard, decks, sources, outline, slides, assets, exports, settings, agent, PWA."""
from __future__ import annotations

import io
import json

import pytest
from fastapi.testclient import TestClient

from cicero_hoard import main as main_mod
from cicero_hoard.main import create_app
from conftest import SOURCE_TEXT, FakeLink, make_services, png_bytes
from test_extract import _docx


def mk(client, **kw):
    body = {"title": "Trimestre", "brief": "Resultados", "slide_count": 6}
    body.update(kw)
    r = client.post("/api/decks", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def full_deck(client):
    d = mk(client)
    did = d["id"]
    assert client.post(f"/api/decks/{did}/sources", json={"title": "Informe", "text": SOURCE_TEXT}).status_code == 201
    assert client.post(f"/api/decks/{did}/outline/generate").status_code == 200
    r = client.post(f"/api/decks/{did}/slides/generate")
    assert r.status_code == 200
    return client.get(f"/api/decks/{did}").json()


# ---------------- health, status, guard ----------------

def test_health_and_status(client):
    h = client.get("/api/health").json()
    assert h["service"] == "cicero-hoard" and h["counts"]["decks"] == 0 and "hoard_link" in h
    s = client.get("/api/status").json()
    assert s["service"] == "cicero-hoard" and "model" in s and "pdf_available" in s and s["schema"] >= 1


def test_guard_rejects_foreign_hosts_and_origins(client):
    assert client.get("/api/health", headers={"Host": "evil.example"}).status_code == 403
    assert client.get("/api/health", headers={"Origin": "http://evil.example"}).status_code == 403
    assert client.post("/api/decks", json={"title": "x"}, headers={"Sec-Fetch-Site": "cross-site", "Sec-Fetch-Mode": "cors"}).status_code == 403
    assert client.get("/api/health", headers={"Host": "localhost:5194"}).status_code == 200
    assert client.get("/api/health", headers={"Origin": "http://localhost:5173"}).status_code == 200


def test_allowed_hosts_env_extends_the_guard(tmp_path):
    svc = make_services(tmp_path, allowed_hosts=("hub.example",))
    with TestClient(create_app(svc.config, svc), base_url="http://127.0.0.1") as c:
        assert c.get("/api/health", headers={"Host": "hub.example"}).status_code == 200


# ---------------- decks ----------------

def test_deck_crud_and_validation(client):
    d = mk(client, title="Uno")
    assert d["status"] == "draft" and len(d["id"]) == 12
    assert client.get("/api/decks").json()["items"][0]["title"] == "Uno"
    assert client.get(f"/api/decks/{d['id']}").json()["slides"] == []
    p = client.patch(f"/api/decks/{d['id']}", json={"title": "Dos", "theme": "oscuro"})
    assert p.status_code == 200 and p.json()["title"] == "Dos" and p.json()["theme"] == "oscuro"
    assert client.patch(f"/api/decks/{d['id']}", json={"theme": "nope"}).status_code == 400
    assert client.post("/api/decks", json={"title": ""}).status_code == 400
    assert client.post("/api/decks", json={"title": "x", "slide_count": 99}).status_code == 400
    assert client.post("/api/decks", json={"title": "x", "surprise": 1}).status_code == 400
    assert client.post("/api/decks", content=b"not json", headers={"content-type": "application/json"}).status_code == 400
    assert client.get("/api/decks/missing").status_code == 404
    assert client.get("/api/decks/missing").json()["error"]


def test_delete_needs_confirm(client):
    d = mk(client)
    r = client.delete(f"/api/decks/{d['id']}")
    assert r.status_code == 400 and "confirm" in r.json()["error"].lower()
    assert client.delete(f"/api/decks/{d['id']}?confirm=true").status_code == 200
    assert client.get(f"/api/decks/{d['id']}").status_code == 404


# ---------------- sources ----------------

def test_sources_json_and_multipart(client):
    d = mk(client)
    did = d["id"]
    r = client.post(f"/api/decks/{did}/sources", json={"title": "Pegado", "text": "Hola con 12 cosas"})
    assert r.status_code == 201 and r.json()["id"] == 1 and r.json()["kind"] == "text"
    up = client.post(f"/api/decks/{did}/sources", files={"file": ("informe.docx", _docx(["Contenido subido"]), "application/octet-stream")}, data={"title": "Mi informe"})
    assert up.status_code == 201 and up.json()["kind"] == "docx" and up.json()["title"] == "Mi informe"
    assert [s["id"] for s in client.get(f"/api/decks/{did}/sources").json()["items"]] == [1, 2]
    got = client.get(f"/api/decks/{did}/sources/1", params={"offset": 5, "max_chars": 200}).json()
    assert got["text"].startswith("con 12") and got["offset"] == 5
    assert client.get(f"/api/decks/{did}/sources/99").status_code == 404
    assert client.get(f"/api/decks/{did}/sources/abc").status_code == 400
    assert client.delete(f"/api/decks/{did}/sources/1").status_code == 200
    assert client.post(f"/api/decks/missing/sources", json={"text": "x"}).status_code == 404


def test_sources_rejections(client):
    did = mk(client)["id"]
    assert client.post(f"/api/decks/{did}/sources", json={"text": "   "}).status_code == 400
    assert client.post(f"/api/decks/{did}/sources", content=b"nope", headers={"content-type": "application/json"}).status_code == 400
    assert client.post(f"/api/decks/{did}/sources", files={"file": ("a.exe", b"MZ....", "application/octet-stream")}).status_code == 400
    assert client.post(f"/api/decks/{did}/sources", files={"other": ("a.txt", b"hola", "text/plain")}).status_code == 400
    assert client.post(f"/api/decks/{did}/sources", files={"file": ("a.pdf", b"not a pdf", "application/pdf")}).status_code == 400


def test_upload_size_limit(tmp_path):
    svc = make_services(tmp_path, max_upload_bytes=2048)
    with TestClient(create_app(svc.config, svc), base_url="http://127.0.0.1") as c:
        did = mk(c)["id"]
        assert c.post(f"/api/decks/{did}/sources", files={"file": ("a.txt", b"a" * 4000, "text/plain")}).status_code == 400
        assert c.post(f"/api/decks/{did}/sources", files={"file": ("a.txt", b"a" * 1000, "text/plain")}).status_code == 201


# ---------------- outline and slides ----------------

def test_generation_flow_and_status(client):
    d = full_deck(client)
    assert d["status"] == "review" and len(d["slides"]) == 6 and d["model_used"] == "fake-model"
    did = d["id"]
    s2 = d["slides"][1]
    r = client.post(f"/api/decks/{did}/slides/{s2['id']}/approve")
    assert r.status_code == 200 and r.json()["status"] == "approved"
    for s in client.get(f"/api/decks/{did}").json()["slides"]:
        client.post(f"/api/decks/{did}/slides/{s['id']}/approve")
    assert client.get(f"/api/decks/{did}").json()["status"] == "ready"
    assert client.post(f"/api/decks/{did}/slides/{s2['id']}/unapprove").json()["status"] == "draft"
    assert client.get(f"/api/decks/{did}").json()["status"] == "review"


def test_outline_put_and_slides_reorder(client):
    d = full_deck(client)
    did = d["id"]
    items = [{"id": o["id"], "title": o["title"], "purpose": o["purpose"], "points": o["points"]} for o in d["outline"]]
    items[1]["title"] = "Título nuevo"
    r = client.put(f"/api/decks/{did}/outline", json={"items": items})
    assert r.status_code == 200 and r.json()["outline"][1]["title"] == "Título nuevo" and r.json()["outline"][1]["id"] == items[1]["id"]
    assert client.put(f"/api/decks/{did}/outline", json={"items": [{"title": ""}]}).status_code == 400
    order = [s["id"] for s in d["slides"]]
    rev = client.post(f"/api/decks/{did}/slides/reorder", json={"order": list(reversed(order))})
    assert rev.status_code == 200 and [s["id"] for s in rev.json()["slides"]] == list(reversed(order))
    assert client.post(f"/api/decks/{did}/slides/reorder", json={"order": order[:2]}).status_code == 400


def test_slide_edit_revisions_revert_regenerate(client):
    d = full_deck(client)
    did, sid = d["id"], d["slides"][2]["id"]
    p = client.patch(f"/api/decks/{did}/slides/{sid}", json={"title": "Nueva", "notes": "Mis notas"})
    assert p.status_code == 200 and p.json()["revision"] == 2 and p.json()["status"] == "draft"
    assert client.patch(f"/api/decks/{did}/slides/{sid}", json={}).status_code == 400
    assert client.patch(f"/api/decks/{did}/slides/{sid}", json={"layout": "poster"}).status_code == 400
    revs = client.get(f"/api/decks/{did}/slides/{sid}/revisions").json()["items"]
    assert [r["revision"] for r in revs] == [2, 1] and revs[0]["reason"] == "edited"
    rv = client.post(f"/api/decks/{did}/slides/{sid}/revert", json={"revision": 1})
    assert rv.status_code == 200 and rv.json()["revision"] == 3 and rv.json()["title"] != "Nueva"
    assert client.post(f"/api/decks/{did}/slides/{sid}/revert", json={"revision": 99}).status_code == 404
    client.svc.link_sync.responder = lambda m: json.dumps({"layout": "bullets", "title": "Reescrita", "blocks": [{"type": "bullets", "items": ["a", "b"]}],
                                                           "notes": "n", "sources": [1]})
    rg = client.post(f"/api/decks/{did}/slides/{sid}/regenerate", json={"feedback": "otro enfoque"})
    assert rg.status_code == 200 and rg.json()["title"] == "Reescrita" and rg.json()["revision"] == 4


def test_regenerate_without_model_is_400_with_code(fallback_client):
    c = fallback_client
    d = full_deck(c)
    r = c.post(f"/api/decks/{d['id']}/slides/{d['slides'][1]['id']}/regenerate", json={"feedback": "x"})
    assert r.status_code == 400 and r.json()["code"] == "model_unavailable"


def test_fallback_flow_over_http(fallback_client):
    c = fallback_client
    did = mk(c)["id"]
    c.post(f"/api/decks/{did}/sources", json={"title": "Informe", "text": SOURCE_TEXT})
    o = c.post(f"/api/decks/{did}/outline/generate").json()
    assert o["generator"] == "fallback"
    s = c.post(f"/api/decks/{did}/slides/generate").json()
    assert s["generator"] == "fallback" and len(s["slides"]) == len(o["outline"])


def test_outline_failure_is_400_with_code(tmp_path):
    svc = make_services(tmp_path, link=FakeLink(["basura", "más basura"]))
    with TestClient(create_app(svc.config, svc), base_url="http://127.0.0.1") as c:
        did = mk(c)["id"]
        c.post(f"/api/decks/{did}/sources", json={"text": SOURCE_TEXT})
        r = c.post(f"/api/decks/{did}/outline/generate")
        assert r.status_code == 400 and r.json()["code"] == "generation_failed"


def test_slide_add_delete(client):
    did = mk(client)["id"]
    a = client.post(f"/api/decks/{did}/slides")  # no body at all
    assert a.status_code == 201 and a.json()["position"] == 1
    b = client.post(f"/api/decks/{did}/slides", json={"title": "Dos", "layout": "quote", "blocks": [{"type": "quote", "text": "hola"}], "after_id": a.json()["id"]})
    assert b.status_code == 201 and b.json()["position"] == 2 and b.json()["layout"] == "quote"
    assert client.post(f"/api/decks/{did}/slides", json={"blocks": [{"type": "bullets", "items": ["x"] * 20}]}).status_code == 400
    assert client.post(f"/api/decks/{did}/slides", json={"after_id": "ghost"}).status_code == 404
    assert client.delete(f"/api/decks/{did}/slides/{a.json()['id']}").status_code == 200
    assert client.get(f"/api/decks/{did}/slides/{b.json()['id']}").json()["position"] == 1


def test_slide_blocks_reference_existing_images(client):
    did = mk(client)["id"]
    r = client.post(f"/api/decks/{did}/slides", json={"layout": "image_text", "blocks": [{"type": "image", "asset_id": "ghost"}]})
    assert r.status_code == 400


# ---------------- assets and images ----------------

def test_assets_upload_and_fetch(client):
    did = mk(client)["id"]
    up = client.post(f"/api/decks/{did}/assets", files={"file": ("foto.png", png_bytes(120, 80), "image/png")})
    assert up.status_code == 201
    aid = up.json()["asset_id"]
    got = client.get(f"/api/assets/{aid}")
    assert got.status_code == 200 and got.headers["content-type"] == "image/png" and got.headers["x-content-type-options"] == "nosniff"
    assert client.get("/api/assets/ghost").status_code == 404
    assert client.post(f"/api/decks/{did}/assets", files={"file": ("x.png", b"not an image", "image/png")}).status_code == 400
    assert client.post(f"/api/decks/{did}/assets", files={"file": ("x.txt", b"hola", "text/plain")}).status_code == 400


def test_slide_image_from_studio_and_without_studio(client, tmp_path):
    did = mk(client)["id"]
    s = client.post(f"/api/decks/{did}/slides", json={"title": "Foto", "image_prompt": "un puente al amanecer"}).json()
    r = client.post(f"/api/decks/{did}/slides/{s['id']}/image")
    assert r.status_code == 200 and any(b["type"] == "image" for b in r.json()["blocks"]) and r.json()["layout"] == "image_text"
    from cicero_hoard.errors import ImageStudioUnavailable

    client.svc.image_studio.error = ImageStudioUnavailable("No image studio is reachable.")
    s2 = client.post(f"/api/decks/{did}/slides", json={"title": "Otra"}).json()
    r2 = client.post(f"/api/decks/{did}/slides/{s2['id']}/image", json={"prompt": "algo"})
    assert r2.status_code == 400 and r2.json()["code"] == "image_studio_unavailable"
    r3 = client.post(f"/api/decks/{did}/slides/{s2['id']}/image")  # no prompt anywhere
    assert r3.status_code == 400


# ---------------- check, previews ----------------

def test_check_and_previews(client):
    d = full_deck(client)
    did = d["id"]
    issues = client.get(f"/api/decks/{did}/check").json()["issues"]
    assert issues and all({"slide_id", "kind", "severity", "message"} <= set(i) for i in issues)
    p = client.get(f"/api/decks/{did}/preview.html")
    assert p.status_code == 200 and p.headers["content-type"].startswith("text/html") and p.text.count("<section") == 6
    assert "default-src 'none'" in p.headers["content-security-policy"] and p.headers["cache-control"] == "no-store"
    one = client.get(f"/api/decks/{did}/slides/{d['slides'][2]['id']}/preview.html")
    assert one.status_code == 200 and one.text.count("<section") == 1
    assert client.get(f"/api/decks/{did}/slides/ghost/preview.html").status_code == 404
    assert client.get("/api/decks/ghost/preview.html").status_code == 404


def test_preview_escapes_content(client):
    did = mk(client, title="<script>alert(1)</script>")["id"]
    client.post(f"/api/decks/{did}/slides", json={"title": "<img src=x onerror=alert(1)>", "blocks": [{"type": "text", "text": "<b>x</b>"}]})
    html = client.get(f"/api/decks/{did}/preview.html").text
    assert "<script>alert(1)" not in html and "<img src=x" not in html and "<b>x</b>" not in html


def test_preview_serves_uploaded_images_same_origin(client):
    did = mk(client)["id"]
    aid = client.post(f"/api/decks/{did}/assets", files={"file": ("f.png", png_bytes(), "image/png")}).json()["asset_id"]
    client.post(f"/api/decks/{did}/slides", json={"layout": "image_text", "title": "Foto", "blocks": [{"type": "image", "asset_id": aid}]})
    assert f"/api/assets/{aid}" in client.get(f"/api/decks/{did}/preview.html").text


# ---------------- exports ----------------

def test_exports_over_http(client):
    d = full_deck(client)
    did = d["id"]
    for fmt, ctype in (("pptx", "presentationml"), ("html", "text/html"), ("md", "text/markdown")):
        r = client.post(f"/api/decks/{did}/export", json={"format": fmt})
        assert r.status_code == 201, r.text
        exp = r.json()
        f = client.get(exp["url"])
        assert f.status_code == 200 and ctype in f.headers["content-type"] and len(f.content) == exp["bytes"]
        assert "attachment" in f.headers["content-disposition"]
        if fmt == "html":
            assert f.headers["content-security-policy"] == "sandbox"
    assert len(client.get(f"/api/decks/{did}/exports").json()["items"]) == 3
    assert client.post(f"/api/decks/{did}/export", json={"format": "odp"}).status_code == 400
    assert client.post(f"/api/decks/{did}/export", json={}).status_code == 400
    assert client.get("/api/exports/ghost/file").status_code == 404
    empty = mk(client)["id"]
    r = client.post(f"/api/decks/{empty}/export", json={"format": "pptx"})
    assert r.status_code == 400 and r.json()["code"] == "no_slides"


def test_pdf_over_http_reports_unavailable(tmp_path, monkeypatch):
    from cicero_hoard import export_pdf
    from cicero_hoard.errors import PdfUnavailable

    def boom(p):
        raise PdfUnavailable("No Chromium is available.")

    monkeypatch.setattr(export_pdf, "_launch", boom)
    svc = make_services(tmp_path)
    with TestClient(create_app(svc.config, svc), base_url="http://127.0.0.1") as c:
        d = full_deck(c)
        r = c.post(f"/api/decks/{d['id']}/export", json={"format": "pdf"})
        assert r.status_code == 400 and r.json()["code"] == "pdf_unavailable" and "Chromium" in r.json()["error"]


def test_pdf_over_http_with_injected_renderer(tmp_path):
    svc = make_services(tmp_path, pdf_fn=lambda deck, assets: b"%PDF-1.4\n%fake")
    with TestClient(create_app(svc.config, svc), base_url="http://127.0.0.1") as c:
        d = full_deck(c)
        r = c.post(f"/api/decks/{d['id']}/export", json={"format": "pdf"})
        assert r.status_code == 201 and c.get(r.json()["url"]).headers["content-type"] == "application/pdf"


def test_deleting_a_deck_removes_its_files(client):
    d = full_deck(client)
    exp = client.post(f"/api/decks/{d['id']}/export", json={"format": "md"}).json()
    folder = client.svc.config.exports_dir / exp["id"]
    assert folder.exists()
    client.delete(f"/api/decks/{d['id']}?confirm=true")
    assert not folder.exists() and client.get(exp["url"]).status_code == 404


# ---------------- themes, settings ----------------

def test_themes_and_settings(client):
    themes = client.get("/api/themes").json()["items"]
    assert len(themes) >= 6 and {"id", "name", "colors", "fonts"} <= set(themes[0])
    s = client.get("/api/settings").json()
    assert s["default_language"] == "es" and "pdf_available" in s and s["image_studio"]["timeout_s"] == 600.0
    assert client.patch("/api/settings", json={"default_language": "en"}).json()["default_language"] == "en"
    assert client.put("/api/settings", json={"model": "qwen3"}).json()["model"] == "qwen3"
    assert client.get("/api/settings").json()["model"] == "qwen3"
    assert client.patch("/api/settings", json={"default_language": "fr"}).status_code == 400
    assert client.patch("/api/settings", json={"surprise": 1}).status_code == 400
    assert mk(client, language=None)["language"] == "en"


# ---------------- agent bridge ----------------

def test_agent_endpoints_require_the_token(client):
    tools = client.get("/api/agent/tools").json()
    assert len(tools["tools"]) == 26 and tools["instructions"]
    assert client.post("/api/agent/call", json={"name": "deck_list"}).status_code == 401
    assert client.post("/api/agent/call", json={"name": "deck_list"}, headers={"Authorization": "Bearer wrong"}).status_code == 401
    good = {"Authorization": f"Bearer {client.svc.token}"}
    r = client.post("/api/agent/call", json={"name": "deck_list"}, headers=good)
    assert r.status_code == 200 and r.json() == {"items": []}
    assert client.post("/api/agent/call", json={"name": "nope"}, headers=good).status_code == 404
    assert client.post("/api/agent/call", json={"name": "deck_get", "arguments": {}}, headers=good).status_code == 400
    assert client.post("/api/agent/call", json={"name": "deck_get", "arguments": {"deck_id": "ghost"}}, headers=good).status_code == 404
    d = client.post("/api/agent/call", json={"name": "deck_create", "arguments": {"title": "Vía agente"}, "caller": "test"}, headers=good).json()
    assert d["title"] == "Vía agente"
    assert client.post("/api/agent/call", json={"name": "source_add", "arguments": {"deck_id": d["id"], "path": "/etc/hostname"}}, headers=good).status_code in (400, 403)


def test_token_is_persistent(tmp_path):
    a = make_services(tmp_path)
    b = make_services(tmp_path)
    assert a.token == b.token and len(a.token) == 64
    assert (tmp_path / "data" / "mcp-token").read_text() == a.token


# ---------------- PWA and SPA ----------------

def test_pwa_routes(client):
    m = client.get("/manifest.webmanifest")
    assert m.status_code == 200 and m.json()["short_name"] == "Cicero" and m.json()["name"] == "Cicero's Hoard"
    sw = client.get("/sw.js")
    assert sw.status_code == 200 and "cicero-hoard-assets" in sw.text and sw.headers["service-worker-allowed"] == "/"


def test_spa_fallback_and_unknown_api(client, tmp_path, monkeypatch):
    static = tmp_path / "static"
    (static / "assets").mkdir(parents=True)
    (static / "index.html").write_text("<!doctype html><title>app</title>", encoding="utf-8")
    (static / "assets" / "a.js").write_text("console.log(1)", encoding="utf-8")
    monkeypatch.setattr(main_mod, "_static_dir", lambda: static)
    assert "<title>app</title>" in client.get("/").text
    assert "<title>app</title>" in client.get("/decks/abc").text
    assert client.get("/assets/a.js").text == "console.log(1)"
    assert client.get("/api/nothing").status_code == 404 and "error" in client.get("/api/nothing").json()
    # path traversal never leaves the static folder
    (tmp_path / "secret.txt").write_text("secret", encoding="utf-8")
    assert "secret" not in client.get("/..%2fsecret.txt").text and "secret" not in client.get("/%2e%2e/secret.txt").text


def test_spa_without_a_built_client(client, tmp_path, monkeypatch):
    monkeypatch.setattr(main_mod, "_static_dir", lambda: tmp_path / "nothing")
    r = client.get("/")
    assert r.status_code == 503 and "error" in r.json()
