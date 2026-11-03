"""/api/themes: the built-in themes, the ones made from design systems and presets, and the way to make one.

Also the deck design audit (/api/decks/{id}/design-audit) and starting the design studio through the Hub, which share the
family design studio with the presets."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Request

from .. import decks as store
from ..models import DesignAuditBody, PresetPickBody, ThemeFromPresetBody, ThemeFromTokensBody
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


def deck_brief(svc, deck_id: str) -> str:
    """What a deck is for, in one line: title, brief, audience and tone."""
    deck = store.deck_view(svc, deck_id)
    return " ".join(x for x in (deck.get("title"), deck.get("brief"), deck.get("audience"), deck.get("tone")) if x)


@router.get("/themes/presets")
def presets(request: Request, query: Optional[str] = None, source: Optional[str] = None, limit: int = 200):
    return services(request).design_presets(query=query, source=source, limit=limit)


@router.post("/themes/presets/pick")
def presets_pick(request: Request, body: PresetPickBody):
    svc = services(request)
    brief = body.brief or (deck_brief(svc, body.deck_id) if body.deck_id else "")
    return svc.pick_presets(brief, n=body.n, use_model=body.use_model)


@router.post("/themes/from-preset", status_code=201)
def from_preset(request: Request, body: ThemeFromPresetBody):
    return services(request).theme_from_preset(body.preset, body.mode)


@router.get("/decks/{deck_id}/design-audit")
def design_audit_latest(request: Request, deck_id: str, lang: Optional[str] = None):
    from ..design_audit import norm_lang
    return {"audit": services(request).design_audit_latest(deck_id, norm_lang(lang, request.headers.get("accept-language")))}


@router.post("/decks/{deck_id}/design-audit")
def design_audit_run(request: Request, deck_id: str, body: DesignAuditBody):
    from ..design_audit import norm_lang
    return {"audit": services(request).design_audit(deck_id, prepare=body.prepare, lang=norm_lang(body.lang, request.headers.get("accept-language")))}


@router.post("/design/vitruvius/start")
def vitruvius_start(request: Request):
    return services(request).vitruvius_prepare()
