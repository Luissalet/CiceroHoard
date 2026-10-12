"""/api/themes: the built-in themes, the ones made from design systems, and the way to make one."""

from __future__ import annotations

from fastapi import APIRouter, Request

from ..models import ThemeFromTokensBody
from .deps import services

router = APIRouter(prefix="/api")


@router.get("/themes")
def themes(request: Request):
    return {"items": services(request).themes()}


@router.get("/themes/design-systems")
def design_systems(request: Request):
    # Plain functions: they wait for the hub, which must not block the event loop.
    return {"items": services(request).design_systems()}


@router.post("/themes/from-tokens", status_code=201)
def from_tokens(request: Request, body: ThemeFromTokensBody):
    return services(request).theme_from_tokens(body.tokens_id, body.mode)
