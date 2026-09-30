"""Optional image generation through the family's image studio (Prospero's Hoard, ``service: prosperos-hoard``).

The studio is found, in order, through ``CICERO_IMAGE_STUDIO_URL``, the hub's app list (``/api/apps``) and its default
local port; it is then called through the hub with this app's own token (``hoard_link.family.call``), so no other
app's token file is read. Everything is optional and isolated here: without a studio the endpoint answers
``image_studio_unavailable`` and the rest of the app is unaffected. Network access is injectable for tests: a
``transport`` for the discovery/download requests and a ``call_fn`` for the tool call.
"""

from __future__ import annotations

import base64
import re
from pathlib import Path
from typing import Any, Callable, Optional
from urllib.parse import urlsplit

import httpx

from . import decks as store
from .errors import CiceroError, ImageStudioUnavailable
from .hoard_link import _hubclient, family

STUDIO_SERVICE = "prosperos-hoard"
STUDIO_APP_ID = "prospero"
DEFAULT_STUDIO_URLS = ("http://127.0.0.1:8815",)
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp")
MAX_IMAGE_BYTES = 15 * 1024 * 1024
LOCAL_HOSTS = ("127.0.0.1", "localhost", "::1", "[::1]")

CallFn = Callable[[str, str, dict[str, Any]], dict[str, Any]]


class ImageStudio:
    def __init__(self, *, configured_url: str = "", tool: str = "studio_generate", transport: Optional[httpx.BaseTransport] = None,
                 call_fn: Optional[CallFn] = None, hub_url: Optional[str] = None, timeout: float = 600.0):
        self.configured_url = configured_url.rstrip("/")
        self.tool = tool
        self.transport = transport
        self.hub_url = hub_url
        self.timeout = timeout
        self._call = call_fn or (lambda app, name, args: family.call(app, name, args, timeout=timeout))

    # ---- discovery ----
    def _client(self, timeout: float = 4.0) -> httpx.Client:
        return httpx.Client(transport=self.transport, timeout=timeout, trust_env=False)

    def _is_studio(self, client: httpx.Client, url: str) -> bool:
        try:
            response = client.get(f"{url}/api/health")
            return response.status_code == 200 and response.json().get("service") == STUDIO_SERVICE
        except Exception:  # noqa: BLE001 - a closed port or a foreign service simply is not the studio
            return False

    def _hub_candidates(self, client: httpx.Client) -> list[tuple[str, str]]:
        hub = _hubclient.hub_url(self.hub_url)
        try:
            response = client.get(f"{hub}/api/apps")
            data = response.json() if response.status_code == 200 else None
        except Exception:  # noqa: BLE001
            return []
        apps = data.get("apps") if isinstance(data, dict) else data
        found: list[tuple[str, str]] = []
        for app in apps if isinstance(apps, list) else []:
            if not isinstance(app, dict):
                continue
            health = app.get("health") if isinstance(app.get("health"), dict) else {}
            names = {str(app.get("id", "")).lower(), str(app.get("service", "")).lower(), str(health.get("service", "")).lower()}
            if STUDIO_SERVICE in names or STUDIO_APP_ID in names:
                url = str(app.get("url") or app.get("ui_url") or "").rstrip("/")
                if not url and app.get("port"):
                    url = f"http://127.0.0.1:{app['port']}"
                found.append((str(app.get("id") or STUDIO_APP_ID), url))
        return found

    def discover(self) -> Optional[dict[str, str]]:
        """``{"app": id, "url": base url}`` of a reachable studio, or None."""
        with self._client() as client:
            if self.configured_url and self._is_studio(client, self.configured_url):
                return {"app": STUDIO_APP_ID, "url": self.configured_url}
            for app_id, url in self._hub_candidates(client):
                if url and self._is_studio(client, url):
                    return {"app": app_id, "url": url}
            for url in DEFAULT_STUDIO_URLS:
                if self._is_studio(client, url):
                    return {"app": STUDIO_APP_ID, "url": url}
        return None

    # ---- generation ----
    def generate(self, prompt: str, *, width: int = 1280, height: int = 720) -> bytes:
        studio = self.discover()
        if studio is None:
            raise ImageStudioUnavailable("No image studio is reachable. Start Prospero's Hoard (and the hub) to generate images, or upload one.")
        reply = self._call(studio["app"], self.tool, {"prompt": prompt, "width": width, "height": height})
        if not isinstance(reply, dict) or not reply.get("ok", True):
            detail = (reply or {}).get("error") if isinstance(reply, dict) else "no answer"
            raise ImageStudioUnavailable(f"The image studio did not generate an image: {detail}")
        with self._client(timeout=30.0) as client:
            data = self._extract(reply.get("result", reply), studio["url"], client)
        if not data:
            raise ImageStudioUnavailable("The image studio answered but returned no image data this app can read.")
        return data

    def _extract(self, result: Any, base_url: str, client: httpx.Client) -> Optional[bytes]:
        if isinstance(result, list):
            for item in result:
                got = self._extract(item, base_url, client)
                if got:
                    return got
            return None
        if isinstance(result, str):
            return self._from_string(result, base_url, client)
        if not isinstance(result, dict):
            return None
        for key in ("image_base64", "b64_json", "base64", "image_b64", "data", "image"):
            value = result.get(key)
            if isinstance(value, str) and value:
                got = self._from_string(value, base_url, client)
                if got:
                    return got
        for key in ("images", "outputs", "files", "assets", "result"):
            value = result.get(key)
            if isinstance(value, (list, dict)):
                got = self._extract(value, base_url, client)
                if got:
                    return got
        for key in ("path", "file", "output", "url", "file_url", "download_url"):
            value = result.get(key)
            if isinstance(value, str) and value:
                got = self._from_string(value, base_url, client)
                if got:
                    return got
        return None

    def _from_string(self, value: str, base_url: str, client: httpx.Client) -> Optional[bytes]:
        value = value.strip()
        if value.startswith("data:"):
            _, _, payload = value.partition(",")
            return _b64(payload)
        if re.fullmatch(r"[A-Za-z0-9+/=\s]{200,}", value):
            return _b64(value)
        try:
            path = Path(value)
            if path.suffix.lower() in IMAGE_SUFFIXES and path.is_file() and path.stat().st_size <= MAX_IMAGE_BYTES:
                return path.read_bytes()
        except OSError:
            pass
        if value.startswith("/"):
            return self._download(client, base_url + value)
        if value.startswith(("http://", "https://")):
            return self._download(client, value)
        return None

    def _download(self, client: httpx.Client, url: str) -> Optional[bytes]:
        host = (urlsplit(url).hostname or "").lower()
        if host not in LOCAL_HOSTS:
            return None  # the studio is local; never fetch from anywhere else
        try:
            response = client.get(url)
        except Exception:  # noqa: BLE001
            return None
        if response.status_code == 200 and len(response.content) <= MAX_IMAGE_BYTES:
            return response.content
        return None


def _b64(payload: str) -> Optional[bytes]:
    try:
        return base64.b64decode(re.sub(r"\s+", "", payload), validate=False)
    except Exception:  # noqa: BLE001
        return None


def generate_for_slide(svc: Any, deck_id: str, slide_id: str, prompt: Optional[str] = None) -> dict[str, Any]:
    """Generate a picture for a slide, store it as an asset and put it on the slide (new revision)."""
    slide = store.get_slide(svc, deck_id, slide_id)
    text = (prompt or slide.get("image_prompt") or "").strip()
    if not text:
        raise CiceroError("There is no image description: pass a prompt or set the slide's image_prompt.", code="prompt_required")
    data = svc.image_studio.generate(text)
    asset = store.add_asset(svc, deck_id, data, filename="generated.png")
    blocks = [dict(b) for b in slide["blocks"]]
    replaced = False
    for b in blocks:
        if b.get("type") == "image":
            b["asset_id"] = asset["asset_id"]
            replaced = True
            break
    if not replaced:
        blocks.append({"type": "image", "asset_id": asset["asset_id"], "caption": None})
    patch: dict[str, Any] = {"blocks": [{k: v for k, v in b.items() if v is not None} for b in blocks], "image_prompt": text}
    if slide["layout"] == "bullets":
        patch["layout"] = "image_text"
    return store.patch_slide(svc, deck_id, slide_id, patch)
