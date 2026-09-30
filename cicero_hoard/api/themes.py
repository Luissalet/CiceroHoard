"""/api/themes."""

from __future__ import annotations

from fastapi import APIRouter

from ..themes import list_themes

router = APIRouter(prefix="/api")


@router.get("/themes")
def themes():
    return {"items": list_themes()}
