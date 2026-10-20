"""/api/decks/{id}/assets (upload) and /api/assets/{id} (the image)."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse

from .. import decks as store
from ..errors import NotFound
from .deps import services
from .sources import read_upload
from .deps import tool
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api")


class ImportRequest(BaseModel):
    path: str = Field(..., min_length=1, max_length=1000)


@router.post('/decks/{deck_id}/assets/import', status_code=201)
def assets_import(request: Request, deck_id: str, body: ImportRequest):
    return tool(request, 'asset_import', deck_id=deck_id, path=body.path)


@router.post("/decks/{deck_id}/assets", status_code=201)
async def assets_upload(request: Request, deck_id: str):
    svc = services(request)
    data, filename, _fields = await read_upload(request, svc.config.max_image_bytes)
    from ..figures import upload
    return await run_in_threadpool(upload, svc, deck_id, data, filename)


@router.get("/assets/{asset_id}/source")
def figure_source(request: Request, asset_id: str, download: bool = False):
    from ..figures import GetArgs, get
    if not download:
        info = store.asset_info(services(request), asset_id)
        if info is None:
            raise NotFound("Image not found.")
        if info.get("metadata", {}).get("kind") != "vitruvius.figure":
            return {"asset_id": asset_id, "figure": None}
    result = get(services(request), GetArgs(asset_id=asset_id, include_preview=download))
    if download:
        return JSONResponse(result["figure"], headers={"Content-Disposition": f'attachment; filename="{asset_id}.vfigure"'})
    return result


@router.get("/assets/{asset_id}")
def assets_get(request: Request, asset_id: str):
    info = store.asset_info(services(request), asset_id)
    if info is None:
        raise NotFound("Image not found.")
    return FileResponse(info["path"], media_type=info["mime"], headers={"Cache-Control": "private, max-age=3600", "X-Content-Type-Options": "nosniff"})


@router.get("/assets/{asset_id}/native")
def assets_native_get(request: Request, asset_id: str):
    info = store.asset_info(services(request), asset_id)
    path = info.get("native_path") if info else None
    if path is None or not path.is_file():
        raise NotFound("Editable vector source not found.")
    return FileResponse(path, media_type="application/octet-stream", filename=f"{asset_id}.vectorcraft",
                        headers={"X-Content-Type-Options": "nosniff"})


@router.get("/assets/{asset_id}/preview")
def assets_preview_get(request: Request, asset_id: str):
    info = store.asset_info(services(request), asset_id)
    path = info.get("fallback_path") if info else None
    if path is None or not path.is_file():
        raise NotFound("Vector preview not found.")
    return FileResponse(path, media_type="image/png", headers={"X-Content-Type-Options": "nosniff"})
