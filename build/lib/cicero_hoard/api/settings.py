"""/api/settings."""

from __future__ import annotations

from fastapi import APIRouter, Request

from ..models import SettingsBody
from .deps import services

router = APIRouter(prefix="/api")


@router.get("/settings")
def settings_get(request: Request):
    return services(request).get_settings()


@router.patch("/settings")
@router.put("/settings")
def settings_patch(request: Request, body: SettingsBody):
    return services(request).update_settings(body.model_dump(exclude_none=True))
