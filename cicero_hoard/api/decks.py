"""/api/decks: the presentation, its check and its previews."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from ..models import DeckCreate, DeckPatch
from .deps import services, tool

router = APIRouter(prefix="/api")

PREVIEW_HEADERS = {
    # The preview is our own generated document: it needs inline style/script and same-origin images, nothing else.
    "Content-Security-Policy": "default-src 'none'; img-src 'self' data:; style-src 'unsafe-inline'; script-src 'unsafe-inline'; frame-ancestors 'self'",
    "X-Content-Type-Options": "nosniff",
    "Cache-Control": "no-store",
}


@router.get("/decks")
def decks_list(request: Request):
    return tool(request, "deck_list")


@router.post("/decks", status_code=201)
def decks_create(request: Request, body: DeckCreate):
    return tool(request, "deck_create", **body.model_dump(exclude_none=True))


@router.get("/decks/{deck_id}")
def decks_get(request: Request, deck_id: str):
    return tool(request, "deck_get", deck_id=deck_id, detail="full")


@router.patch("/decks/{deck_id}")
def decks_patch(request: Request, deck_id: str, body: DeckPatch):
    return tool(request, "deck_update", deck_id=deck_id, **body.model_dump(exclude_none=True))


@router.delete("/decks/{deck_id}")
def decks_delete(request: Request, deck_id: str, confirm: bool = False):
    return tool(request, "deck_delete", deck_id=deck_id, confirm=confirm)


@router.get("/decks/{deck_id}/check")
def decks_check(request: Request, deck_id: str):
    return services(request).check(deck_id)


@router.get("/decks/{deck_id}/preview.html", response_class=HTMLResponse)
def deck_preview(request: Request, deck_id: str):
    return HTMLResponse(services(request).preview_html(deck_id), headers=PREVIEW_HEADERS)


@router.get("/decks/{deck_id}/slides/{slide_id}/preview.html", response_class=HTMLResponse)
def slide_preview(request: Request, deck_id: str, slide_id: str):
    return HTMLResponse(services(request).preview_html(deck_id, slide_id), headers=PREVIEW_HEADERS)
