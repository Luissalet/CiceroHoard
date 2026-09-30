"""Standalone HTML export: one self-contained file (inline CSS, script and images), arrow-key navigation.

Speaker notes are left out on purpose: the file is meant to be shared. They stay in the PPTX and Markdown exports.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from .render import render_document

AssetLookup = Callable[[str], Optional[dict[str, Any]]]


def build_html(deck: dict[str, Any], *, assets: AssetLookup) -> bytes:
    document, _ = render_document(deck, assets=assets, inline=True, mode="present")
    return document.encode("utf-8")
