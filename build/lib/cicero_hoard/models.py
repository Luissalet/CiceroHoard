"""Pydantic models shared by the API, the agent tools and the generator: every input goes through them."""

from __future__ import annotations

import math
from typing import Annotated, Any, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

LAYOUTS = ("title", "section", "bullets", "two_column", "image_text", "quote", "chart", "closing",
           "evidence", "comparison", "diagram", "metrics", "table", "image_full")
Layout = Literal["title", "section", "bullets", "two_column", "image_text", "quote", "chart", "closing",
                 "evidence", "comparison", "diagram", "metrics", "table", "image_full"]
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
    build: Optional[int] = Field(None, ge=0, le=40)
    effect: Optional[Literal['none','fade','wipe','draw','stages']] = None
    duration_ms: Optional[int] = Field(None, ge=100, le=2000)


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
    values: list[Optional[float]] = Field(default_factory=list, max_length=2000)
    x_values: Optional[list[float]] = Field(None, max_length=2000)
    lower: Optional[list[Optional[float]]] = Field(None, max_length=2000)
    upper: Optional[list[Optional[float]]] = Field(None, max_length=2000)
    color: Optional[str] = Field(None, pattern=r'^#[0-9a-fA-F]{6}$')
    sizes: Optional[list[float]] = Field(None, max_length=2000)

    @field_validator("values", "x_values", "lower", "upper", "sizes")
    @classmethod
    def _finite(cls, values):
        if values is not None and any(v is not None and not math.isfinite(v) for v in values):
            raise ValueError("chart values must be finite numbers")
        return values

    @model_validator(mode='after')
    def _bounds(self):
        for field in ('x_values','lower','upper','sizes'):
            value=getattr(self,field)
            if value is not None and len(value)!=len(self.values):
                raise ValueError(f'{field} must match the values length')
        if (self.lower is None)!=(self.upper is None):
            raise ValueError('Provide both lower and upper bounds')
        if self.lower is not None:
            for value,lo,hi in zip(self.values,self.lower,self.upper):
                if lo is not None and hi is not None and (lo>hi or (value is not None and not lo<=value<=hi)):
                    raise ValueError('Bounds must contain the central value')
        return self


class ChartAnnotation(_Block):
    text: str = Field(..., min_length=1, max_length=160)
    category: int = Field(0, ge=0, le=1999)
    series: int = Field(0, ge=0, le=5)


class ChartReference(_Block):
    value: float = Field(..., allow_inf_nan=False)
    label: str = Field('', max_length=80)


class ChartBlock(_Block):
    type: Literal["chart"] = "chart"
    chart: Literal["bar", "bar_horizontal", "line", "area", "pie", "donut", "scatter", "bubble",
                   "dot", "dumbbell", "band", "heatmap", "waterfall", "funnel"] = "bar"
    title: Optional[str] = Field(None, max_length=200)
    categories: list[str] = Field(default_factory=list, max_length=2000)
    series: list[ChartSeries] = Field(default_factory=list, max_length=6)
    unit: Optional[str] = Field(None, max_length=40)
    x_label: Optional[str] = Field(None, max_length=80)
    y_label: Optional[str] = Field(None, max_length=80)
    highlight: Optional[list[int]] = Field(None, max_length=40)
    annotations: Optional[list[ChartAnnotation]] = Field(None, max_length=12)
    references: Optional[list[ChartReference]] = Field(None, max_length=8)
    show_legend: Optional[bool] = None
    show_values: Optional[bool] = None
    zero_baseline: Optional[bool] = None
    stacked: Optional[bool] = None

    @field_validator("categories", mode="before")
    @classmethod
    def _cats(cls, value: Any) -> list[str]:
        return [str(v).strip()[:80] for v in (value or [])]

    @model_validator(mode='after')
    def _specialized(self):
        if self.chart=='dumbbell' and self.series and len(self.series)!=2:
            raise ValueError('A dumbbell comparison needs exactly two series')
        if self.chart in ('scatter','bubble','band'):
            for series in self.series:
                if series.values and series.x_values is None:
                    raise ValueError(f'{self.chart} needs numeric x_values')
        if self.chart=='band' and any(s.lower is None for s in self.series):
            raise ValueError('A band chart needs lower and upper bounds')
        if self.chart=='bubble' and any(s.sizes is None for s in self.series):
            raise ValueError('Bubble charts need explicit sizes')
        if any(v<0 for s in self.series for v in s.sizes or []):raise ValueError('Bubble sizes cannot be negative')
        if self.categories and self.series:
            if any(a.category>=len(self.categories) or a.series>=len(self.series) for a in self.annotations or []):
                raise ValueError('An annotation refers to an absent category or series')
            if any(i<0 or i>=len(self.categories) for i in self.highlight or []):raise ValueError('A highlight refers to an absent category')
        if self.chart in ('pie','donut','funnel') and any(v is not None and v<0 for s in self.series for v in s.values):
            raise ValueError('Proportion and funnel values cannot be negative')
        if self.categories and any(len(s.values)!=len(self.categories) for s in self.series):
            # Legacy charts retain their diagnostic instead of becoming uneditable.
            if self.chart not in ('bar','line','pie'):
                raise ValueError('Each series must match the categories length')
        return self


class DiagramNode(_Block):
    id: str = Field(..., min_length=1, max_length=40, pattern=r'^[a-zA-Z0-9_-]+$')
    label: str = Field(..., min_length=1, max_length=100)
    detail: Optional[str] = Field(None, max_length=160)
    emphasis: Optional[bool] = None


class DiagramEdge(_Block):
    source: str = Field(..., max_length=40)
    target: str = Field(..., max_length=40)
    label: Optional[str] = Field(None, max_length=60)


class DiagramBlock(_Block):
    type: Literal['diagram'] = 'diagram'
    direction: Literal['right','down'] = 'right'
    nodes: list[DiagramNode] = Field(..., min_length=1, max_length=24)
    edges: list[DiagramEdge] = Field(default_factory=list, max_length=48)
    title: Optional[str] = Field(None, max_length=200)

    @model_validator(mode='after')
    def _graph(self):
        ids=[n.id for n in self.nodes]
        if len(set(ids))!=len(ids):raise ValueError('Node IDs must be unique')
        if any(e.source not in ids or e.target not in ids for e in self.edges):
            raise ValueError('Every connection must refer to existing nodes')
        return self


class MetricItem(_Block):
    value: str = Field(..., min_length=1, max_length=32)
    label: str = Field(..., min_length=1, max_length=80)
    detail: Optional[str] = Field(None, max_length=160)
    emphasis: Optional[bool] = None


class MetricsBlock(_Block):
    type: Literal['metrics'] = 'metrics'
    items: list[MetricItem] = Field(..., min_length=1, max_length=6)


class TableBlock(_Block):
    type: Literal['table'] = 'table'
    headers: list[str] = Field(..., min_length=1, max_length=10)
    rows: list[list[str]] = Field(..., min_length=1, max_length=30)
    title: Optional[str] = Field(None, max_length=200)
    highlight_rows: Optional[list[int]] = Field(None, max_length=30)

    @model_validator(mode='after')
    def _dimensions(self):
        if any(len(row)!=len(self.headers) for row in self.rows):
            raise ValueError('All table rows must match the headers')
        if any(len(cell)>240 for row in [self.headers,*self.rows] for cell in row):
            raise ValueError('Table cells may contain at most 240 characters')
        return self


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
    Union[BulletsBlock, TextBlock, ImageBlock, QuoteBlock, ChartBlock, ColumnsBlock,
          DiagramBlock, MetricsBlock, TableBlock],
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


class SlideSetImageBody(_Body):
    asset_id: str = Field(..., min_length=1, max_length=64)
    caption: Optional[str] = Field(None, max_length=300,
                                   description="Omit to preserve an existing caption; null clears it.")
    image_index: int = Field(0, ge=0, le=MAX_BLOCKS,
                             description="Zero-based image number, excluding other block types. Use the image count to append.")
    expected_revision: Optional[int] = Field(None, ge=1,
                                            description="Optional revision from slide_get; stale edits return conflict.")


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
