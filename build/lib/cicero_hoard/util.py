"""Small helpers: JSON columns, timestamps, slugs, text clipping. Ids come from ``hoard_link.ids``."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Iterable

from .hoard_link.text import slugify as _slugify


def jload(raw: Any, default: Any) -> Any:
    if raw is None or raw == "":
        return default
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return default


def jdump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def iso_stamp(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_hex(data: bytes | str) -> str:
    return hashlib.sha256(data.encode("utf-8") if isinstance(data, str) else data).hexdigest()


def slugify(text: str, fallback: str = "presentation", maxlen: int = 60) -> str:
    """ASCII, lowercase, hyphen-separated; safe as a file name on any platform (the shared ``hoard_link.text.slugify``)."""
    return _slugify(text, max_len=maxlen, fallback=fallback)


def clip(text: str | None, n: int) -> str:
    text = text or ""
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def shorten(text: str, limit: int) -> str:
    """Cut at a clause or word boundary before ``limit`` characters and add an ellipsis."""
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    cut = text[: limit - 1]
    for sep in ("; ", ", ", ": ", " - ", " "):
        at = cut.rfind(sep)
        if at >= limit * 0.55:
            cut = cut[:at]
            break
    return cut.rstrip(" ,;:-") + "…"


def clean_list(values: Iterable[Any] | None, *, limit: int = 50, maxlen: int = 400) -> list[str]:
    out: list[str] = []
    for value in values or []:
        text = str(value).strip()[:maxlen]
        if text:
            out.append(text)
        if len(out) >= limit:
            break
    return out
