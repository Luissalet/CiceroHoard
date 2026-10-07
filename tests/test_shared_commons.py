"""What comes from Hoard Link: the one-instance start, the stable token, the shared guard, error envelope and bridge, the ids."""
from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from pathlib import Path

import httpx
import pytest

from cicero_hoard.hoard_link import ids, net

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def running_app(tmp_path):
    """The real app (``python -m cicero_hoard``) in a child process on a free port."""
    port = net.free_port()
    env = {**os.environ, "CICERO_DATA_DIR": str(tmp_path / "data"), "CICERO_PORT": str(port), "HOARD_NO_BROWSER": "1", "PYTHONPATH": str(ROOT)}
    command = [sys.executable, "-m", "cicero_hoard"]
    child = subprocess.Popen(command, cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        assert net.wait_healthy(f"http://127.0.0.1:{port}", "cicero-hoard", timeout=40), "the app did not start"
        yield {"port": port, "env": env, "command": command, "data": tmp_path / "data"}
    finally:
        child.terminate()
        try:
            child.wait(timeout=15)
        except subprocess.TimeoutExpired:
            child.kill()


def test_second_start_exits_cleanly_and_keeps_the_token(running_app):
    token_file = running_app["data"] / "mcp-token"
    token = token_file.read_text(encoding="utf-8")
    second = subprocess.run(running_app["command"], cwd=ROOT, env=running_app["env"], capture_output=True, text=True, timeout=40)
    assert second.returncode == 0 and "already running" in second.stdout
    assert token_file.read_text(encoding="utf-8") == token
    health = httpx.get(f"http://127.0.0.1:{running_app['port']}/api/health", trust_env=False).json()
    assert health["service"] == "cicero-hoard" and health["dataDirConfigured"] is True and "hoard_link" in health and "counts" in health
    assert (running_app["data"] / "logs").is_dir()  # the shared launcher logs to <data>/logs


def test_the_shared_bridge_lists_and_calls_the_tools_of_the_running_app(running_app, monkeypatch):
    from cicero_hoard.hoard_link.bridge import CatalogBridge

    monkeypatch.setenv("CICERO_DATA_DIR", str(running_app["data"]))
    monkeypatch.setenv("CICERO_URL", f"http://127.0.0.1:{running_app['port']}")
    monkeypatch.setenv("CICERO_BRIDGE_AUTOSTART", "0")
    bridge = CatalogBridge(app="cicero", service="cicero-hoard", package="cicero_hoard", default_port=5194,
                           data_dir_env="CICERO_DATA_DIR", title="Cicero's Hoard", root=str(ROOT / "mcp_server.py"))

    async def go():
        tools = await bridge.tools()
        created = await bridge.call("deck_create", {"title": "Vía puente"})
        missing = await bridge.call("deck_get", {"deck_id": "nope"})
        refused = await bridge.call("deck_delete", {"deck_id": created.body["id"]})
        return tools, created, missing, refused

    tools, created, missing, refused = asyncio.run(go())
    assert len(tools) == 37 and next(t for t in tools if t["name"] == "slides_generate")["x-timeout-s"] >= 600
    assert not created.is_error and created.body["title"] == "Vía puente"
    assert missing.is_error and missing.body["code"] == "not_found"
    assert refused.is_error and refused.body["code"] == "confirm_required"


def test_errors_share_one_envelope_with_a_code(client):
    missing = client.get("/api/decks/missing")
    assert missing.status_code == 404 and missing.json()["code"] == "not_found" and missing.json()["error"]
    invalid = client.post("/api/decks", json={"title": ""})
    assert invalid.status_code == 400 and invalid.json()["code"] == "invalid_arguments" and invalid.json()["issues"]
    assert client.get("/api/nothing-here").json()["code"] == "not_found"
    refused = client.post("/api/agent/call", json={"name": "deck_list"})
    assert refused.status_code == 401


def test_new_ids_are_ordered_ulids_and_old_ids_still_work(services):
    from cicero_hoard import decks
    from conftest import new_deck

    first = new_deck(services, title="A")["id"]
    second = new_deck(services, title="B")["id"]
    assert ids.is_ulid(first) and first < second
    # a deck made by an earlier version has a 12-hex id: it is still found and edited
    services.db.execute("UPDATE decks SET id = ? WHERE id = ?", ("0123456789ab", first))
    assert decks.deck_view(services, "0123456789ab")["title"] == "A"


def test_the_guard_pins_the_port_of_an_allowed_host(tmp_path):
    from fastapi.testclient import TestClient

    from cicero_hoard.main import create_app
    from conftest import make_services

    svc = make_services(tmp_path, allowed_hosts=("pc2.example",))
    with TestClient(create_app(svc.config, svc), base_url="http://127.0.0.1") as c:
        assert c.get("/api/health", headers={"Host": "pc2.example"}).status_code == 200
        assert c.get("/api/health", headers={"Host": "evil.example"}).status_code == 403


def test_the_launcher_script_imports_the_shared_net_helpers():
    import importlib.util

    spec = importlib.util.spec_from_file_location("cicero_launch_script", ROOT / "scripts" / "launch.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # a deleted helper module would fail here, not on the user's double click
    assert module.SERVICE == "cicero-hoard" and callable(module.main)
