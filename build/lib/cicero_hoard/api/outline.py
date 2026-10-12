"""/api/decks/{id}/outline."""

from __future__ import annotations

from fastapi import APIRouter, Request

from ..models import OutlineBody
from .deps import tool

router = APIRouter(prefix="/api")


@router.post("/decks/{deck_id}/outline/generate")
def outline_generate(request: Request, deck_id: str):
    return tool(request, "outline_generate", deck_id=deck_id)


@router.put("/decks/{deck_id}/outline")
def outline_put(request: Request, deck_id: str, body: OutlineBody):
    return tool(request, "outline_update", deck_id=deck_id, items=[i.model_dump() for i in body.items])
