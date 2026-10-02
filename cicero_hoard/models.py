"""Pydantic models shared by the API, the agent tools and the generator: every input goes through them."""

from __future__ import annotations

import math
from typing import Annotated, Any, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

LAYOUTS = ("title", "section", "bullets", "two_column", "image_text", "quote", "chart", "closing")
Layout = Literal["title", "section", "bullets", "two_column", "image_text", "quote", "chart", "closing"]
Language = Literal["es", "en"]
DeckStatus = Literal["draft", "outline", "review", "ready"]
SlideStatus = Literal["draft", "approved"]
ExportFormat = Literal["pptx", "pdf", "html", "md"]

MAX_SLIDES = 40
MAX_BLOCKS = 8
MAX_ITEMS = 12
MAX_ITEM_CHARS = 400
MAX_TEXT_CHARS = 2000


def _strip_list(values: Any, limit: int, maxlen: int) -> list[str]:
    out: list[str] = []
    for value in values or []:
        text = str(value).strip()
        if text:
            out.append(text)
    if len(out) > limit:
        raise ValueError(f"at most {limit} items")
    for text in out:
        if len(text) > maxlen:
            raise ValueError(f"an item is longer than {maxlen} characters")
    return out


class _Block(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)


class BulletsBlock(_Block):
    type: Literal["bullets"] = "bullets"
    items: list[str] = Field(default_factory=list)

    @field_validator("items", mode="before")
    @classmethod
    def _items(cls, value: Any) -> list[str]:
        return _strip_list(value, MAX_ITEMS, MAX_ITEM_CHARS)


class TextBlock(_Block):
    type: Literal["text"] = "text"
    text: str = Field("", max_length=MAX_TEXT_CHARS)


class ImageBlock(_Block):
    type: Literal["image"] = "image"
    asset_id: str = Field(..., min_length=1, max_length=64)
    caption: Optional[str] = Field(None, max_length=300)


class QuoteBlock(_Block):
    type: Literal["quote"] = "quote"
    text: str = Field("", max_length=600)
    attribution: Optional[str] = Field(None, max_length=200)


class ChartSeries(_Block):
    name: str = Field("", max_length=80)
    values: list[float] = Field(default_factory=list, max_length=40)

    @field_validator("values")
    @classmethod
    def _finite(cls, values: list[float]) -> list[float]:
        if any(not math.isfinite(v) for v in values):
            raise ValueError("chart values must be finite numbers")
        return values


class ChartBlock(_Block):
    type: Literal["chart"] = "chart"
    chart: Literal["bar", "line", "pie"] = "bar"
    title: Optional[str] = Field(None, max_length=200)
    categories: list[str] = Field(default_factory=list, max_length=40)
    series: list[ChartSeries] = Field(default_factory=list, max_length=6)

    @field_validator("categories", mode="before")
    @classmethod
    def _cats(cls, value: Any) -> list[str]:
        return [str(v).strip()[:80] for v in (value or [])]


class ColumnsBlock(_Block):
    type: Literal["columns"] = "columns"
    left_title: Optional[str] = Field(None, max_length=120)
    left: list[str] = Field(default_factory=list)
    right_title: Optional[str] = Field(None, max_length=120)
    right: list[str] = Field(default_factory=list)

    @field_validator("left", "right", mode="before")
    @classmethod
    def _items(cls, value: Any) -> list[str]:
        return _strip_list(value, MAX_ITEMS, MAX_ITEM_CHARS)


Block = Annotated[
    Union[BulletsBlock, TextBlock, ImageBlock, QuoteBlock, ChartBlock, ColumnsBlock],
    Field(discriminator="type"),
]


def dump_blocks(blocks: list[Any]) -> list[dict[str, Any]]:
    """Blocks as plain dicts, without unset optional keys, in a stable shape."""
    return [b.model_dump(exclude_none=True) if hasattr(b, "model_dump") else dict(b) for b in blocks]


class _Body(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class DeckCreate(_Body):
    title: str = Field(..., min_length=1, max_length=200)
    brief: str = Field("", max_length=8000)
    audience: str = Field("", max_length=300)
    tone: str = Field("", max_length=200)
    language: Optional[Language] = None
    slide_count: int = Field(10, ge=3, le=MAX_SLIDES)
    theme: Optional[str] = Field(None, max_length=40)


class DeckPatch(_Body):
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    brief: Optional[str] = Field(None, max_length=8000)
    audience: Optional[str] = Field(None, max_length=300)
    tone: Optional[str] = Field(None, max_length=200)
    language: Optional[Language] = None
    slide_count: Optional[int] = Field(None, ge=3, le=MAX_SLIDES)
    theme: Optional[str] = Field(None, max_length=40)


class SourceText(_Body):
    title: str = Field("", max_length=300)
    text: str = Field(..., min_length=1, max_length=400_000)
    kind: Literal["text", "markdown"] = "text"


class OutlineItemIn(_Body):
    id: Optional[str] = Field(None, max_length=40)
    title: str = Field(..., min_length=1, max_length=200)
    purpose: str = Field("", max_length=500)
    points: list[str] = Field(default_factory=list)
    layout_hint: Optional[Layout] = None

    @field_validator("points", mode="before")
    @classmethod
    def _points(cls, value: Any) -> list[str]:
        return _strip_list(value, 8, MAX_ITEM_CHARS)

    @field_validator("layout_hint", mode="before")
    @classmethod
    def _hint(cls, value: Any) -> Any:
        return value or None


class OutlineBody(_Body):
    items: list[OutlineItemIn] = Field(..., max_length=MAX_SLIDES)


class SlidesGenerateBody(_Body):
    only_missing: bool = False


class SlideAddBody(_Body):
    after_id: Optional[str] = Field(None, max_length=40)
    layout: Layout = "bullets"
    title: str = Field("", max_length=200)
    subtitle: Optional[str] = Field(None, max_length=300)
    blocks: Optional[list[Block]] = Field(None, max_length=MAX_BLOCKS)
    notes: str = Field("", max_length=6000)
    image_prompt: Optional[str] = Field(None, max_length=1000)
    sources: Optional[list[int]] = Field(None, max_length=50)


class SlidePatch(_Body):
    title: Optional[str] = Field(None, max_length=200)
    subtitle: Optional[str] = Field(None, max_length=300)
    layout: Optional[Layout] = None
    blocks: Optional[list[Block]] = Field(None, max_length=MAX_BLOCKS)
    notes: Optional[str] = Field(None, max_length=6000)
    image_prompt: Optional[str] = Field(None, max_length=1000)
    sources: Optional[list[int]] = Field(None, max_length=50)


class RegenerateBody(_Body):
    feedback: str = Field("", max_length=2000)


class RevertBody(_Body):
    revision: int = Field(..., ge=1)


class ReorderBody(_Body):
    order: list[str] = Field(..., min_length=1, max_length=MAX_SLIDES * 3)


class ExportBody(_Body):
    format: ExportFormat


class ThemeFromTokensBody(_Body):
    tokens_id: str = Field(..., min_length=1, max_length=80)
    mode: Literal["light", "dark"] = "light"


class SlideImageBody(_Body):
    prompt: Optional[str] = Field(None, max_length=1000)


class SettingsBody(_Body):
    model: Optional[str] = Field(None, max_length=200)
    default_language: Optional[Language] = None


class GeneratedSlide(BaseModel):
    """What the model (or the fallback) proposes for one slide, before it is stored."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    layout: Layout = "bullets"
    title: str = Field("", max_length=200)
    subtitle: Optional[str] = Field(None, max_length=300)
    blocks: list[Block] = Field(default_factory=list, max_length=MAX_BLOCKS)
    notes: str = Field("", max_length=6000)
    sources: list[int] = Field(default_factory=list, max_length=50)
    image_prompt: Optional[str] = Field(None, max_length=1000)

    @field_validator("sources", mode="before")
    @classmethod
    def _sources(cls, value: Any) -> list[int]:
        out: list[int] = []
        for item in value or []:
            text = str(item).strip().lstrip("Ss[").rstrip("]")
            if text.isdigit():
                out.append(int(text))
        return out

    @model_validator(mode="before")
    @classmethod
    def _null_lists(cls, data: Any) -> Any:
        if isinstance(data, dict):
            data = dict(data)
            for key in ("blocks", "sources"):
                if data.get(key) is None:
                    data.pop(key, None)
            if data.get("notes") is None:
                data.pop("notes", None)
        return data


class GeneratedOutlineItem(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    title: str = Field(..., min_length=1, max_length=200)
    purpose: str = Field("", max_length=500)
    points: list[str] = Field(default_factory=list)
    layout_hint: Optional[Layout] = None

    @field_validator("points", mode="before")
    @classmethod
    def _points(cls, value: Any) -> list[str]:
        return [str(p).strip()[:MAX_ITEM_CHARS] for p in (value or []) if str(p).strip()][:8]

    @field_validator("layout_hint", mode="before")
    @classmethod
    def _hint(cls, value: Any) -> Any:
        return value if value in LAYOUTS else None

    @field_validator("purpose", mode="before")
    @classmethod
    def _purpose(cls, value: Any) -> Any:
        return "" if value is None else str(value)[:500]


class GeneratedOutline(BaseModel):
    model_config = ConfigDict(extra="ignore")

    items: list[GeneratedOutlineItem] = Field(..., min_length=1, max_length=MAX_SLIDES)
