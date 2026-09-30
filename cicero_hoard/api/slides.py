"""/api/decks/{id}/slides: generate, add, edit, approve, revisions, images."""

from __future__ import annotations

from fastapi import APIRouter, Request

from .. import decks as store
from ..models import RegenerateBody, ReorderBody, RevertBody, SlideAddBody, SlideImageBody, SlidePatch, SlidesGenerateBody
from .deps import services, tool

router = APIRouter(prefix="/api")


@router.post("/decks/{deck_id}/slides/generate")
def slides_generate(request: Request, deck_id: str, body: SlidesGenerateBody | None = None):
    return tool(request, "slides_generate", deck_id=deck_id, only_missing=(body.only_missing if body else False))


@router.post("/decks/{deck_id}/slides/reorder")
def slides_reorder(request: Request, deck_id: str, body: ReorderBody):
    return tool(request, "slides_reorder", deck_id=deck_id, order=body.order)


@router.post("/decks/{deck_id}/slides", status_code=201)
def slides_add(request: Request, deck_id: str, body: SlideAddBody | None = None):
    data = (body or SlideAddBody()).model_dump(exclude_none=True)
    return tool(request, "slide_add", deck_id=deck_id, **data)


@router.get("/decks/{deck_id}/slides/{slide_id}")
def slide_get(request: Request, deck_id: str, slide_id: str):
    return tool(request, "slide_get", deck_id=deck_id, slide_id=slide_id)


@router.patch("/decks/{deck_id}/slides/{slide_id}")
def slide_patch(request: Request, deck_id: str, slide_id: str, body: SlidePatch):
    return tool(request, "slide_update", deck_id=deck_id, slide_id=slide_id, **body.model_dump(exclude_none=True))


@router.delete("/decks/{deck_id}/slides/{slide_id}")
def slide_delete(request: Request, deck_id: str, slide_id: str):
    return store.delete_slide(services(request), deck_id, slide_id)


@router.post("/decks/{deck_id}/slides/{slide_id}/regenerate")
def slide_regenerate(request: Request, deck_id: str, slide_id: str, body: RegenerateBody):
    return tool(request, "slide_regenerate", deck_id=deck_id, slide_id=slide_id, feedback=body.feedback)


@router.post("/decks/{deck_id}/slides/{slide_id}/approve")
def slide_approve(request: Request, deck_id: str, slide_id: str):
    return tool(request, "slide_approve", deck_id=deck_id, slide_id=slide_id, approved=True)


@router.post("/decks/{deck_id}/slides/{slide_id}/unapprove")
def slide_unapprove(request: Request, deck_id: str, slide_id: str):
    return tool(request, "slide_approve", deck_id=deck_id, slide_id=slide_id, approved=False)


@router.get("/decks/{deck_id}/slides/{slide_id}/revisions")
def slide_revisions(request: Request, deck_id: str, slide_id: str):
    return store.list_revisions(services(request), deck_id, slide_id)


@router.post("/decks/{deck_id}/slides/{slide_id}/revert")
def slide_revert(request: Request, deck_id: str, slide_id: str, body: RevertBody):
    return tool(request, "slide_revert", deck_id=deck_id, slide_id=slide_id, revision=body.revision)


@router.post("/decks/{deck_id}/slides/{slide_id}/image")
def slide_image(request: Request, deck_id: str, slide_id: str, body: SlideImageBody | None = None):
    return tool(request, "slide_image", deck_id=deck_id, slide_id=slide_id, prompt=(body.prompt if body else None))
