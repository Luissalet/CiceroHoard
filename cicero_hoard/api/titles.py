"""/api/decks/{id}/titles: titles that state the slide's conclusion (see titles.py)."""

from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field

from .deps import tool

router = APIRouter(prefix="/api")


class _Body(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ProposeBody(_Body):
    slide_ids: Optional[list[str]] = Field(None, max_length=120)
    use_model: bool = True
    force: bool = False


class ApplyBody(_Body):
    slide_ids: Optional[list[str]] = Field(None, max_length=120)
    titles: Optional[dict[str, str]] = None
    use_model: bool = True


class RestoreBody(_Body):
    slide_ids: Optional[list[str]] = Field(None, max_length=120)
    force: bool = False


class ModeBody(_Body):
    mode: Optional[Literal["label", "conclusion"]] = None
    slide_id: Optional[str] = Field(None, max_length=40)
    use_model: bool = True


@router.get("/decks/{deck_id}/titles")
def titles_get(request: Request, deck_id: str):
    return tool(request, "titles_overview", deck_id=deck_id)


@router.post("/decks/{deck_id}/titles/propose")
def titles_propose(request: Request, deck_id: str, body: ProposeBody):
    return tool(request, "titles_propose", deck_id=deck_id, **body.model_dump(exclude_none=True))


@router.post("/decks/{deck_id}/titles/apply")
def titles_apply(request: Request, deck_id: str, body: ApplyBody):
    return tool(request, "titles_apply", deck_id=deck_id, **body.model_dump(exclude_none=True))


@router.post("/decks/{deck_id}/titles/restore")
def titles_restore(request: Request, deck_id: str, body: RestoreBody):
    return tool(request, "titles_restore", deck_id=deck_id, **body.model_dump(exclude_none=True))


@router.post("/decks/{deck_id}/titles/mode")
def titles_mode(request: Request, deck_id: str, body: ModeBody):
    return tool(request, "titles_mode", deck_id=deck_id, **body.model_dump(exclude_none=True))
