"""Small shared helpers: JSON columns, ids, timestamps, slugs, text clipping."""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import unicodedata
from datetime import datetime, timezone
from typing import Any, Iterable


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


def new_id() -> str:
    """12 hex characters: short enough for URLs, random enough for a local app."""
    return secrets.token_hex(6)


def sha256_hex(data: bytes | str) -> str:
    return hashlib.sha256(data.encode("utf-8") if isinstance(data, str) else data).hexdigest()


def slugify(text: str, fallback: str = "presentation", maxlen: int = 60) -> str:
    """ASCII, lowercase, hyphen-separated; safe as a file name on any platform."""
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return (text[:maxlen].strip("-")) or fallback


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
