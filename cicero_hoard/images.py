"""Optional image generation through the family's image studio (Prospero's Hoard, ``service: prosperos-hoard``).

The studio is found, in order, through ``CICERO_IMAGE_STUDIO_URL``, the hub's app list (``/api/apps``) and its default
local port, and is then used through its plain local REST API (no token: the studio only accepts loopback hosts):
a project named "Cicero's Hoard slides" is reused or created, a job is submitted, polled until it is done, and the
resulting image asset is downloaded and verified. Only loopback hosts are ever contacted, redirects are not followed and
proxy environment variables are ignored. Everything is optional and isolated here: without a studio the endpoint answers
``image_studio_unavailable`` and the rest of the app is unaffected. The network, the clock and the sleep between polls are
injectable for tests.
"""

from __future__ import annotations

import io
import re
import time
from typing import Any, Callable, Optional
from urllib.parse import urlsplit

import httpx

from . import decks as store
from .errors import CiceroError, ImageStudioUnavailable
from .hoard_link import _hubclient

STUDIO_SERVICE = "prosperos-hoard"
STUDIO_APP_ID = "prospero"
STUDIO_PROJECT_NAME = "Cicero's Hoard slides"
DEFAULT_STUDIO_URLS = ("http://127.0.0.1:8815",)
MAX_IMAGE_BYTES = 15 * 1024 * 1024
LOCAL_HOSTS = ("127.0.0.1", "localhost", "::1")
IMAGE_TYPES = ("image/png", "image/jpeg", "image/webp")
DEFAULT_TIMEOUT = 600.0
DEFAULT_POLL_INTERVAL = 1.5
ID_RE = re.compile(r"[A-Za-z0-9_-]{1,128}")
FAILED_STATES = ("failed", "cancelled")


def is_loopback(url: str) -> bool:
    """True only for an http(s) URL whose host is a loopback name or address."""
    try:
        parts = urlsplit(url)
        return parts.scheme in ("http", "https") and (parts.hostname or "").lower() in LOCAL_HOSTS
    except ValueError:
        return False


def _valid_id(value: Any) -> Optional[str]:
    if isinstance(value, int) and not isinstance(value, bool):
        value = str(value)
    return value if isinstance(value, str) and ID_RE.fullmatch(value) else None


class ImageStudio:
    def __init__(self, *, configured_url: str = "", transport: Optional[httpx.BaseTransport] = None, hub_url: Optional[str] = None,
                 timeout: float = DEFAULT_TIMEOUT, poll_interval: float = DEFAULT_POLL_INTERVAL,
                 sleep_fn: Callable[[float], None] = time.sleep, clock_fn: Callable[[], float] = time.monotonic):
        self.configured_url = configured_url.rstrip("/")
        self.transport = transport
        self.hub_url = hub_url
        self.timeout = timeout
        self.poll_interval = poll_interval
        self._sleep = sleep_fn
        self._clock = clock_fn

    # ---- discovery ----
    def _client(self, timeout: float = 4.0) -> httpx.Client:
        return httpx.Client(transport=self.transport, timeout=timeout, trust_env=False, follow_redirects=False)

    def _is_studio(self, client: httpx.Client, url: str) -> bool:
        if not is_loopback(url):
            return False
        try:
            response = client.get(f"{url}/api/health")
            return response.status_code == 200 and response.json().get("service") == STUDIO_SERVICE
        except Exception:  # noqa: BLE001 - a closed port or a foreign service simply is not the studio
            return False

    def _hub_candidates(self, client: httpx.Client) -> list[tuple[str, str]]:
        hub = _hubclient.hub_url(self.hub_url)
        if not is_loopback(hub):
            return []
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

    # ---- REST helpers ----
    def _json(self, client: httpx.Client, method: str, url: str, **kw: Any) -> Any:
        try:
            response = client.request(method, url, **kw)
        except httpx.HTTPError as error:
            raise ImageStudioUnavailable(f"The image studio could not be reached: {error}") from error
        if response.status_code >= 300:
            raise ImageStudioUnavailable(f"The image studio answered {response.status_code} to {method} {urlsplit(url).path}{_detail(response)}")
        try:
            return response.json()
        except ValueError as error:
            raise ImageStudioUnavailable(f"The image studio sent an unreadable answer to {method} {urlsplit(url).path}.") from error

    def _project(self, client: httpx.Client, base: str) -> str:
        listing = self._json(client, "GET", f"{base}/api/projects")
        if isinstance(listing, dict):
            listing = listing.get("items", listing.get("projects"))
        for item in listing if isinstance(listing, list) else []:
            if isinstance(item, dict) and item.get("name") == STUDIO_PROJECT_NAME and _valid_id(item.get("id")):
                return _valid_id(item["id"]) or ""
        created = self._json(client, "POST", f"{base}/api/projects", json={"name": STUDIO_PROJECT_NAME})
        if isinstance(created, dict) and isinstance(created.get("project"), dict):
            created = created["project"]
        project_id = _valid_id(created.get("id")) if isinstance(created, dict) else None
        if not project_id:
            raise ImageStudioUnavailable("The image studio did not return a valid project id.")
        return project_id

    def _submit(self, client: httpx.Client, base: str, project_id: str, prompt: str, aspect: str) -> str:
        reply = self._json(client, "POST", f"{base}/api/projects/{project_id}/generate", json={"prompt": prompt, "aspect": aspect, "count": 1})
        job = reply.get("job") if isinstance(reply, dict) else None
        job_id = _valid_id(job.get("id")) if isinstance(job, dict) else None
        if not job_id:
            raise ImageStudioUnavailable("The image studio did not return a valid job id.")
        if job.get("project_id") is not None and str(job["project_id"]) != project_id:
            raise ImageStudioUnavailable("The image studio started the job in a different project than the one requested.")
        return job_id

    def _wait(self, client: httpx.Client, base: str, project_id: str, job_id: str) -> str:
        """Poll the job until it is done; the id of the image asset it produced."""
        deadline = self._clock() + self.timeout
        while True:
            job = self._json(client, "GET", f"{base}/api/jobs/{job_id}")
            if not isinstance(job, dict):
                raise ImageStudioUnavailable("The image studio sent an unreadable job status.")
            if job.get("project_id") is not None and str(job["project_id"]) != project_id:
                raise ImageStudioUnavailable("The image studio reported a job of a different project.")
            state = str(job.get("state") or "").lower()
            if state in FAILED_STATES:
                raise ImageStudioUnavailable(f"The image studio {state} the render: {job.get('message') or 'no reason given'}")
            if state == "done":
                outputs = job.get("outputs") if isinstance(job.get("outputs"), dict) else {}
                ids = outputs.get("asset_ids")
                candidates = ids if isinstance(ids, list) else [outputs.get("asset_id")]
                for candidate in candidates:
                    asset_id = _valid_id(candidate)
                    if asset_id:
                        return asset_id
                raise ImageStudioUnavailable("The image studio finished the render but returned no image.")
            if self._clock() >= deadline:
                raise ImageStudioUnavailable(f"The render is still running in the image studio (job {job_id}) after {self.timeout:g} s; it was not submitted again. "
                                             "Check the studio and try again later.")
            self._sleep(self.poll_interval)

    def _download(self, client: httpx.Client, base: str, project_id: str, asset_id: str) -> bytes:
        info = self._json(client, "GET", f"{base}/api/assets/{asset_id}")
        if not isinstance(info, dict) or info.get("kind") != "image":
            raise ImageStudioUnavailable("The image studio returned an asset that is not an image.")
        if info.get("project_id") is not None and str(info["project_id"]) != project_id:
            raise ImageStudioUnavailable("The image studio returned an asset of a different project.")
        url = f"{base}/api/assets/{asset_id}/file"
        try:
            with client.stream("GET", url) as response:
                if response.status_code != 200:
                    raise ImageStudioUnavailable(f"The image studio answered {response.status_code} to the image download.")
                kind = response.headers.get("content-type", "").split(";")[0].strip().lower()
                if kind not in IMAGE_TYPES:
                    raise ImageStudioUnavailable(f"The image studio sent {kind or 'an unknown type'} instead of an image.")
                declared = response.headers.get("content-length", "")
                if declared.isdigit() and int(declared) > MAX_IMAGE_BYTES:
                    raise ImageStudioUnavailable("The image from the studio is larger than 15 MB.")
                data = bytearray()
                for chunk in response.iter_bytes():
                    data.extend(chunk)
                    if len(data) > MAX_IMAGE_BYTES:
                        raise ImageStudioUnavailable("The image from the studio is larger than 15 MB.")
        except httpx.HTTPError as error:
            raise ImageStudioUnavailable(f"The image download from the studio failed: {error}") from error
        _verify_image(bytes(data))
        return bytes(data)

    # ---- generation ----
    def generate(self, prompt: str, *, aspect: str = "16:9") -> bytes:
        studio = self.discover()
        if studio is None:
            raise ImageStudioUnavailable("No image studio is reachable. Start Prospero's Hoard (and the hub) to generate images, or upload one.")
        base = studio["url"]
        with self._client(timeout=30.0) as client:
            project_id = self._project(client, base)
            job_id = self._submit(client, base, project_id, prompt, aspect)
            asset_id = self._wait(client, base, project_id, job_id)
            return self._download(client, base, project_id, asset_id)


def _detail(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return ""
    if isinstance(body, dict):
        text = body.get("message") or body.get("detail") or body.get("error")
        if isinstance(text, str) and text:
            return f": {text[:200]}"
    return ""


def _verify_image(data: bytes) -> None:
    from PIL import Image

    if not data:
        raise ImageStudioUnavailable("The image studio sent an empty file.")
    try:
        Image.open(io.BytesIO(data)).verify()
    except Exception as error:  # noqa: BLE001 - any decoder failure means the bytes are not a usable image
        raise ImageStudioUnavailable(f"The image studio sent a file that is not a valid image: {error}") from error


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
