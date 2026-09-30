"""The optional image studio: discovery, the REST flow (project, job, polling, download), refusals, and the picture on a slide."""
from __future__ import annotations

import json
from urllib.parse import urlsplit

import httpx
import pytest

from cicero_hoard import decks, images
from cicero_hoard.errors import CiceroError, ImageStudioUnavailable
from conftest import FakeStudio, make_services, new_deck, png_bytes

STUDIO = "http://127.0.0.1:8815"
PNG = png_bytes(300, 200)
PROJECT = "Cicero's Hoard slides"


class FakeStudioServer:
    """A fake Prospero's Hoard behind an httpx.MockTransport; records every request."""

    def __init__(self, *, projects=None, states=("queued", "running", "done"), message="", asset=None, file_bytes=PNG, content_type="image/png",
                 job_project=None, outputs=None, health=True, extra=None):
        self.projects = list(projects) if projects is not None else []
        self.states = list(states)
        self.message = message
        self.asset = asset
        self.file_bytes = file_bytes
        self.content_type = content_type
        self.job_project = job_project
        self.outputs = outputs
        self.health = health
        self.extra = extra or {}  # url -> (status, json) for anything else, e.g. the hub
        self.requests: list[tuple[str, str, object]] = []
        self.polls = 0
        self.project = "p1"  # the project the last job was submitted to

    def handler(self, request: httpx.Request) -> httpx.Response:
        path, method = request.url.path, request.method
        body = json.loads(request.content) if request.content else None
        self.requests.append((method, str(request.url), body))
        if str(request.url) in self.extra:
            status, data = self.extra[str(request.url)]
            return httpx.Response(status, json=data)
        if request.url.host != "127.0.0.1" or request.url.port != 8815:
            raise httpx.ConnectError("refused")
        if path == "/api/health":
            return httpx.Response(200, json={"service": "prosperos-hoard"}) if self.health else httpx.Response(500)
        if path == "/api/projects" and method == "GET":
            return httpx.Response(200, json=self.projects)
        if path == "/api/projects" and method == "POST":
            self.projects.append({"id": "p-new", "name": body["name"]})
            return httpx.Response(201, json={"id": "p-new"})
        if path.endswith("/generate") and method == "POST":
            project_id = self.project = path.split("/")[3]
            return httpx.Response(200, json={"job": {"id": "job-1", "project_id": self.job_project or project_id}})
        if path == "/api/jobs/job-1":
            state = self.states[min(self.polls, len(self.states) - 1)]
            self.polls += 1
            outputs = self.outputs if self.outputs is not None else ({"asset_ids": ["asset-1"]} if state == "done" else {})
            return httpx.Response(200, json={"id": "job-1", "project_id": self.project, "state": state, "message": self.message, "outputs": outputs})
        if path == "/api/assets/asset-1":
            return httpx.Response(200, json=self.asset or {"id": "asset-1", "kind": "image", "project_id": self.project})
        if path == "/api/assets/asset-1/file":
            return httpx.Response(200, content=self.file_bytes, headers={"content-type": self.content_type})
        return httpx.Response(404, json={"detail": "not found"})

    def posts(self, suffix: str) -> list:
        return [r for r in self.requests if r[0] == "POST" and urlsplit(r[1]).path.endswith(suffix)]


class Clock:
    """A fake monotonic clock: sleeping advances it."""

    def __init__(self):
        self.now = 0.0
        self.sleeps: list[float] = []

    def __call__(self):
        return self.now

    def sleep(self, seconds: float):
        self.sleeps.append(seconds)
        self.now += seconds


def studio_for(server: FakeStudioServer, clock: Clock | None = None, **kw) -> images.ImageStudio:
    clock = clock or Clock()
    kw.setdefault("hub_url", "http://127.0.0.1:1")
    return images.ImageStudio(transport=httpx.MockTransport(server.handler), sleep_fn=clock.sleep, clock_fn=clock, **kw)


def with_project(**kw) -> FakeStudioServer:
    return FakeStudioServer(projects=[{"id": "p1", "name": PROJECT}], **kw)


# ---- discovery ----
def test_discovery_default_port_and_configured_url():
    assert studio_for(FakeStudioServer()).discover() == {"app": "prospero", "url": STUDIO}
    assert studio_for(FakeStudioServer(), configured_url="http://127.0.0.1:8815/").discover() == {"app": "prospero", "url": STUDIO}


def test_discovery_ignores_a_foreign_service_and_closed_ports():
    assert studio_for(FakeStudioServer(health=False)).discover() is None
    other = FakeStudioServer(extra={f"{STUDIO}/api/health": (200, {"service": "something-else"})})
    assert studio_for(other).discover() is None
    assert studio_for(FakeStudioServer(), configured_url="http://127.0.0.1:9/").discover() == {"app": "prospero", "url": STUDIO}  # falls back to the default


def test_discovery_through_the_hub_app_list():
    hub = {"http://127.0.0.1:1/api/apps": (200, {"apps": [{"id": "prospero-x", "service": "prosperos-hoard", "port": 9001}, {"id": "atlas", "service": "atlas-hoard", "port": 5193}]}),
           "http://127.0.0.1:9001/api/health": (200, {"service": "prosperos-hoard"})}
    assert studio_for(FakeStudioServer(health=False, extra=hub)).discover() == {"app": "prospero-x", "url": "http://127.0.0.1:9001"}


def test_a_non_loopback_url_is_never_contacted():
    hub = {"http://127.0.0.1:1/api/apps": (200, {"apps": [{"id": "prospero", "service": "prosperos-hoard", "url": "https://evil.example"},
                                                            {"id": "prospero2", "service": "prosperos-hoard", "url": "http://192.168.1.20:8815"}]})}
    server = FakeStudioServer(health=False, extra=hub)
    s = studio_for(server, configured_url="http://studio.example:8815")
    assert s.discover() is None
    hosts = {urlsplit(r[1]).hostname for r in server.requests}
    assert hosts <= {"127.0.0.1"}, hosts
    with pytest.raises(ImageStudioUnavailable):
        s.generate("x")
    assert not server.posts("/generate")
    assert images.is_loopback("http://localhost:8815") and images.is_loopback("http://[::1]:8815")
    assert not images.is_loopback("http://127.0.0.1.evil.example") and not images.is_loopback("ftp://127.0.0.1") and not images.is_loopback("http://10.0.0.1")


def test_the_client_never_follows_redirects_or_reads_the_proxy_environment(monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.invalid:3128")
    client = studio_for(FakeStudioServer())._client()
    assert client.follow_redirects is False and client.trust_env is False
    client.close()


# ---- the REST flow ----
def test_reuses_an_existing_project_and_polls_until_done():
    server = with_project(states=("queued", "waiting_gpu", "running", "running", "done"))
    clock = Clock()
    assert studio_for(server, clock).generate("un faro") == PNG
    assert not server.posts("/api/projects")  # reused, not created
    (_, _, body), = server.posts("/generate")
    assert body == {"prompt": "un faro", "aspect": "16:9", "count": 1}
    assert server.polls == 5 and clock.sleeps == [1.5] * 4


def test_creates_the_project_when_there_is_none():
    server = FakeStudioServer(projects=[{"id": "p9", "name": "Another project"}], states=("done",))
    assert studio_for(server).generate("x") == PNG
    (created,) = server.posts("/api/projects")
    assert created[2] == {"name": PROJECT}
    (post,) = server.posts("/generate")
    assert "/api/projects/p-new/generate" in post[1]


@pytest.mark.parametrize("wrap", [lambda items: {"items": items}, lambda items: {"projects": items}])
def test_the_project_list_may_be_wrapped(wrap):
    server = with_project()
    server.projects = wrap(server.projects)
    assert studio_for(server).generate("x") == PNG
    assert not server.posts("/api/projects")


def test_a_single_asset_id_is_accepted():
    server = with_project(states=("done",), outputs={"asset_id": "asset-1"})
    assert studio_for(server).generate("x") == PNG


def test_a_failed_job_carries_the_studios_message():
    for state in ("failed", "cancelled"):
        with pytest.raises(ImageStudioUnavailable) as info:
            studio_for(with_project(states=("running", state), message="out of memory")).generate("x")
        assert "out of memory" in str(info.value) and state in str(info.value) and info.value.code == "image_studio_unavailable"


def test_the_deadline_names_the_job_and_does_not_resubmit():
    server = with_project(states=("running",))
    clock = Clock()
    with pytest.raises(ImageStudioUnavailable) as info:
        studio_for(server, clock, timeout=5.0, poll_interval=2.0).generate("x")
    assert "job-1" in str(info.value) and "still running" in str(info.value)
    assert len(server.posts("/generate")) == 1 and clock.now >= 5.0 and server.polls == 4


def test_an_unusable_studio_answer_is_an_error():
    with pytest.raises(ImageStudioUnavailable):
        studio_for(with_project(states=("done",), outputs={})).generate("x")  # done but no image
    with pytest.raises(ImageStudioUnavailable) as info:
        studio_for(with_project(job_project="other")).generate("x")
    assert "different project" in str(info.value)
    with pytest.raises(ImageStudioUnavailable):
        studio_for(with_project(states=("done",), outputs={"asset_ids": ["../etc/passwd"]})).generate("x")  # ids are validated


def test_no_studio_is_a_clear_error():
    with pytest.raises(ImageStudioUnavailable) as info:
        studio_for(FakeStudioServer(health=False)).generate("x")
    assert "Prospero" in str(info.value)


# ---- what is downloaded ----
def test_an_asset_of_another_project_or_of_another_kind_is_refused():
    with pytest.raises(ImageStudioUnavailable) as info:
        studio_for(with_project(states=("done",), asset={"id": "asset-1", "kind": "image", "project_id": "p2"})).generate("x")
    assert "different project" in str(info.value)
    with pytest.raises(ImageStudioUnavailable) as info:
        studio_for(with_project(states=("done",), asset={"id": "asset-1", "kind": "video", "project_id": "p1"})).generate("x")
    assert "not an image" in str(info.value)


def test_non_image_bytes_are_refused():
    with pytest.raises(ImageStudioUnavailable) as info:
        studio_for(with_project(states=("done",), file_bytes=b"this is not an image")).generate("x")
    assert "not a valid image" in str(info.value)
    with pytest.raises(ImageStudioUnavailable) as info:
        studio_for(with_project(states=("done",), content_type="text/html")).generate("x")
    assert "text/html" in str(info.value)
    with pytest.raises(ImageStudioUnavailable):
        studio_for(with_project(states=("done",), file_bytes=b"")).generate("x")


def test_an_image_over_the_cap_is_refused(monkeypatch):
    monkeypatch.setattr(images, "MAX_IMAGE_BYTES", 100)
    with pytest.raises(ImageStudioUnavailable) as info:
        studio_for(with_project(states=("done",))).generate("x")
    assert "15 MB" in str(info.value)


# ---- on a slide ----
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


def test_a_render_from_the_fake_studio_updates_the_slide_end_to_end(tmp_path):
    server = with_project(states=("queued", "running", "done"))
    svc = make_services(tmp_path, studio=studio_for(server))
    d = new_deck(svc)
    s = decks.add_slide(svc, d["id"], title="Faro", blocks=[{"type": "bullets", "items": ["Punto"]}])
    out = images.generate_for_slide(svc, d["id"], s["id"], prompt="un faro")
    imgs = [b for b in out["blocks"] if b["type"] == "image"]
    assert len(imgs) == 1 and out["layout"] == "image_text" and out["revision"] == 2
    info = decks.asset_info(svc, imgs[0]["asset_id"])
    assert info is not None and info["width"] == 300 and info["height"] == 200


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


def test_a_failed_render_is_a_clear_400_through_the_api(client):
    d = new_deck(client.svc)
    s = decks.add_slide(client.svc, d["id"], title="Faro")
    client.svc.image_studio = studio_for(with_project(states=("running", "failed"), message="no GPU memory"))
    r = client.post(f"/api/decks/{d['id']}/slides/{s['id']}/image", json={"prompt": "un faro"})
    assert r.status_code == 400 and r.json()["code"] == "image_studio_unavailable" and "no GPU memory" in r.json()["error"]
    assert decks.get_slide(client.svc, d["id"], s["id"])["revision"] == 1
