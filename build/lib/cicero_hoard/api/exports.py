"""/api/decks/{id}/export, /api/decks/{id}/exports and /api/exports/{id}/file."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse

from .. import decks as store
from ..models import ExportBody
from .deps import services

router = APIRouter(prefix="/api")

MEDIA_TYPES = {
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "pdf": "application/pdf",
    "html": "text/html; charset=utf-8",
    "md": "text/markdown; charset=utf-8",
    "designcraft": "application/vnd.designcraft+zip",
    "png": "image/png",
}


@router.post("/decks/{deck_id}/export", status_code=201)
def export_create(request: Request, deck_id: str, body: ExportBody):
    # A plain (threadpool) function: the PDF export drives a browser with a blocking API.
    return services(request).export(deck_id, body.format)


@router.get("/decks/{deck_id}/exports")
def exports_list(request: Request, deck_id: str):
    return store.list_exports(services(request), deck_id)


@router.get("/exports/{export_id}/file")
def export_file(request: Request, export_id: str):
    path, view = store.export_file(services(request), export_id)
    headers = {"X-Content-Type-Options": "nosniff"}
    if view["format"] == "html":
        headers["Content-Security-Policy"] = "sandbox"  # a downloaded page opened in the browser must not reach the app's origin
    return FileResponse(path, media_type=MEDIA_TYPES.get(view["format"], "application/octet-stream"), filename=view["filename"], headers=headers)
