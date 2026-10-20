"""Import and inspect a portable authored figure without contacting its origin."""
from __future__ import annotations

import base64
from copy import deepcopy
import io
from typing import Literal
from urllib.parse import urlsplit

from PIL import Image
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

from . import decks
from .errors import CiceroError, NotFound


class Preview(BaseModel):
    mime: Literal["image/png"]
    data: str = Field(min_length=1)


class Figure(BaseModel):
    format: Literal["vitruvius.figure/1"]
    document_id: str = Field(pattern=r"^[0-9a-f]{12}$")
    revision: int = Field(ge=1)
    page_id: str | None = None
    state_id: str | None = Field(None, min_length=1, max_length=60)
    title: str = ""
    content: dict
    origin: dict[str, str] = Field(default_factory=dict)
    preview: Preview

    @model_validator(mode="after")
    def selected_state(self):
        if self.state_id is None:
            return self
        if self.page_id is not None:
            raise ValueError("A figure selects either an infographic page or an isometric state.")
        mechanism = self.content.get("mechanism")
        states = mechanism.get("states") if isinstance(mechanism, dict) else None
        if self.content["diagram"].get("type") != "isometric" or not isinstance(states, list) or not any(
            isinstance(state, dict) and state.get("id") == self.state_id for state in states
        ):
            raise ValueError("The captured state must exist in the retained isometric source.")
        return self

    @field_validator("content")
    @classmethod
    def native_source(cls, value):
        diagram = value.get("diagram")
        if not isinstance(diagram, dict) or not isinstance(diagram.get("nodes"), list):
            raise ValueError("The figure must retain its native diagram source.")
        return value

    @field_validator("origin")
    @classmethod
    def links(cls, value):
        for link in value.values():
            address = urlsplit(link)
            if address.scheme not in ("http", "https") or not address.netloc or address.username or address.password:
                raise ValueError("Figure origin links must be HTTP(S) addresses without credentials.")
        return value


def import_bytes(svc, deck_id, data, filename="figure.vfigure"):
    if len(data) > svc.config.max_image_bytes:
        raise CiceroError("The figure exceeds the configured upload size.")
    try:
        figure = Figure.model_validate_json(data)
        png = base64.b64decode(figure.preview.data, validate=True)
        with Image.open(io.BytesIO(png)) as probe:
            if probe.format != "PNG":
                raise ValueError("The preview must be a PNG image.")
            probe.verify()
    except (ValidationError, ValueError, OSError, SyntaxError, Image.DecompressionBombError) as error:
        raise CiceroError(f"Invalid figure file: {error}") from error
    snapshot = figure.model_dump(exclude={"preview"} | ({"state_id"} if figure.state_id is None else set()))
    result = decks.add_asset(svc, deck_id, png, filename, metadata={"kind": "vitruvius.figure", "figure": snapshot})
    return {**result, "figure": snapshot}


class GetArgs(BaseModel):
    asset_id: str = Field(min_length=1, max_length=80)
    include_preview: bool = False


def get(svc, args):
    info = decks.asset_info(svc, args.asset_id)
    metadata = info.get("metadata", {}) if info else {}
    if metadata.get("kind") != "vitruvius.figure":
        raise NotFound("Figure source not found.")
    figure = deepcopy(metadata["figure"])
    if args.include_preview:
        figure["preview"] = {"mime": "image/png", "data": base64.b64encode(info["path"].read_bytes()).decode("ascii")}
    return {"asset_id": args.asset_id, "figure": figure}


def upload(svc, deck_id, data, filename):
    if filename.lower().endswith((".vfigure", ".json")):
        return import_bytes(svc, deck_id, data, filename)
    return decks.add_asset(svc, deck_id, data, filename)
