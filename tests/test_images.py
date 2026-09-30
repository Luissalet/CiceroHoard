"""The optional image studio: discovery, result formats, error codes, and putting the picture on a slide."""
from __future__ import annotations

import base64
import json

import httpx
import pytest

from cicero_hoard import decks, images
from cicero_hoard.errors import CiceroError, ImageStudioUnavailable
from conftest import FakeStudio, make_services, new_deck, png_bytes

STUDIO = "http://127.0.0.1:8815"
PNG = png_bytes(300, 200)


def transport(routes: dict, seen: list | None = None):
    """A fake network: ``routes`` maps a URL to (status, json or bytes); anything else refuses the connection."""

    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(str(request.url))
        hit = routes.get(str(request.url))
        if hit is None:
            raise httpx.ConnectError("refused")
        status, body = hit
        return httpx.Response(status, content=body) if isinstance(body, bytes) else httpx.Response(status, json=body)

    return httpx.MockTransport(handler)


HEALTH = {f"{STUDIO}/api/health": (200, {"service": "prosperos-hoard"})}


def studio(routes=None, reply=None, **kw):
    calls = []

    def call_fn(app, name, args):
        calls.append((app, name, args))
        return reply if not callable(reply) else reply(app, name, args)

    s = images.ImageStudio(transport=transport(routes if routes is not None else HEALTH), call_fn=call_fn, hub_url="http://127.0.0.1:1", **kw)
    s.calls = calls
    return s


def test_discovery_default_port_and_configured_url():
    assert studio().discover() == {"app": "prospero", "url": STUDIO}
    other = {"http://127.0.0.1:9999/api/health": (200, {"service": "prosperos-hoard"})}
    assert studio(other, configured_url="http://127.0.0.1:9999/").discover() == {"app": "prospero", "url": "http://127.0.0.1:9999"}


def test_discovery_ignores_a_foreign_service_and_closed_ports():
    assert studio({f"{STUDIO}/api/health": (200, {"service": "something-else"})}).discover() is None
    assert studio({}).discover() is None
    assert studio({f"{STUDIO}/api/health": (500, {})}).discover() is None


def test_discovery_through_the_hub_app_list():
    routes = {"http://127.0.0.1:1/api/apps": (200, {"apps": [{"id": "prospero-x", "service": "prosperos-hoard", "port": 9001}, {"id": "atlas", "service": "atlas-hoard", "port": 5193}]}),
              "http://127.0.0.1:9001/api/health": (200, {"service": "prosperos-hoard"})}
    assert studio(routes).discover() == {"app": "prospero-x", "url": "http://127.0.0.1:9001"}


def test_generate_calls_the_configured_tool_through_the_hub():
    b64 = base64.b64encode(PNG).decode()
    s = studio(reply={"ok": True, "result": {"image_base64": b64}}, tool="make_picture")
    assert s.generate("un faro", width=800, height=450) == PNG
    assert s.calls == [("prospero", "make_picture", {"prompt": "un faro", "width": 800, "height": 450})]


@pytest.mark.parametrize("result", [
    lambda b64: {"b64_json": b64},
    lambda b64: {"images": [{"base64": b64}]},
    lambda b64: [{"data": f"data:image/png;base64,{b64}"}],
    lambda b64: b64,
    lambda b64: {"outputs": {"image": b64}},
])
def test_result_formats_are_read_tolerantly(result):
    b64 = base64.b64encode(PNG).decode()
    assert studio(reply={"ok": True, "result": result(b64)}).generate("x") == PNG


def test_result_as_local_path_and_as_studio_url(tmp_path):
    path = tmp_path / "out.png"
    path.write_bytes(PNG)
    assert studio(reply={"ok": True, "result": {"path": str(path)}}).generate("x") == PNG
    routes = {**HEALTH, f"{STUDIO}/files/out.png": (200, PNG)}
    assert studio(routes, reply={"ok": True, "result": {"url": "/files/out.png"}}).generate("x") == PNG
    assert studio(routes, reply={"ok": True, "result": {"url": f"{STUDIO}/files/out.png"}}).generate("x") == PNG


def test_never_downloads_from_a_non_local_host():
    seen: list = []
    routes = {**HEALTH, "https://evil.example/x.png": (200, PNG)}
    s = studio(routes, reply={"ok": True, "result": {"url": "https://evil.example/x.png"}})
    with pytest.raises(ImageStudioUnavailable):
        s.generate("x")


def test_errors_carry_the_image_studio_code():
    with pytest.raises(ImageStudioUnavailable) as info:
        studio({}).generate("x")
    assert info.value.code == "image_studio_unavailable" and "Prospero" in str(info.value)
    with pytest.raises(ImageStudioUnavailable) as info:
        studio(reply={"ok": False, "error": "out of memory"}).generate("x")
    assert "out of memory" in str(info.value)
    with pytest.raises(ImageStudioUnavailable):
        studio(reply={"ok": True, "result": {"nothing": "useful"}}).generate("x")
    with pytest.raises(ImageStudioUnavailable):
        studio(reply=None).generate("x")


def test_generate_for_slide_puts_the_picture_on_the_slide(tmp_path):
    svc = make_services(tmp_path, studio=FakeStudio(PNG))
    d = new_deck(svc)
    s = decks.add_slide(svc, d["id"], title="Faro", blocks=[{"type": "bullets", "items": ["Punto"]}], image_prompt="un faro al amanecer")
    out = images.generate_for_slide(svc, d["id"], s["id"])
    imgs = [b for b in out["blocks"] if b["type"] == "image"]
    assert len(imgs) == 1 and out["layout"] == "image_text" and out["revision"] == 2 and svc.image_studio.calls == ["un faro al amanecer"]
    assert decks.asset_info(svc, imgs[0]["asset_id"]) is not None
    again = images.generate_for_slide(svc, d["id"], s["id"], prompt="otro faro")  # replaces the picture, does not add a second
    assert len([b for b in again["blocks"] if b["type"] == "image"]) == 1 and again["image_prompt"] == "otro faro"


def test_generate_for_slide_needs_a_prompt_and_a_studio(tmp_path):
    svc = make_services(tmp_path, studio=FakeStudio(error=ImageStudioUnavailable("none")))
    d = new_deck(svc)
    s = decks.add_slide(svc, d["id"], title="Sin descripción")
    with pytest.raises(CiceroError) as info:
        images.generate_for_slide(svc, d["id"], s["id"])
    assert info.value.code == "prompt_required"
    with pytest.raises(ImageStudioUnavailable):
        images.generate_for_slide(svc, d["id"], s["id"], prompt="algo")
    assert decks.get_slide(svc, d["id"], s["id"])["revision"] == 1  # a failed generation leaves the slide alone


def test_garbage_from_the_studio_is_not_stored(tmp_path):
    svc = make_services(tmp_path, studio=FakeStudio(b"this is not an image"))
    d = new_deck(svc)
    s = decks.add_slide(svc, d["id"], title="x")
    with pytest.raises(CiceroError):
        images.generate_for_slide(svc, d["id"], s["id"], prompt="algo")
    assert decks.get_slide(svc, d["id"], s["id"])["revision"] == 1
