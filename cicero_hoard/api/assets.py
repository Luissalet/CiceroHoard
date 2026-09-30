"""/api/decks/{id}/assets (upload) and /api/assets/{id} (the image)."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse

from .. import decks as store
from ..errors import NotFound
from .deps import services
from .sources import read_upload

router = APIRouter(prefix="/api")


@router.post("/decks/{deck_id}/assets", status_code=201)
async def assets_upload(request: Request, deck_id: str):
    svc = services(request)
    data, filename, _fields = await read_upload(request, svc.config.max_image_bytes)
    return await run_in_threadpool(store.add_asset, svc, deck_id, data, filename)


@router.get("/assets/{asset_id}")
def assets_get(request: Request, asset_id: str):
    info = store.asset_info(services(request), asset_id)
    if info is None:
        raise NotFound("Image not found.")
    return FileResponse(info["path"], media_type=info["mime"], headers={"Cache-Control": "private, max-age=3600", "X-Content-Type-Options": "nosniff"})
