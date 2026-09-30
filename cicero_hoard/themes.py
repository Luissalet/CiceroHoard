"""Built-in themes: colours, fonts (all of them present on Windows and usable in PPTX) and contrast helpers."""

from __future__ import annotations

from typing import Any

from .errors import CiceroError

COLOR_KEYS = ("background", "surface", "text", "muted", "accent", "accent2")

THEMES: list[dict[str, Any]] = [
    {"id": "claro", "name": "Claro",
     "colors": {"background": "#ffffff", "surface": "#eef1f6", "text": "#1a1d23", "muted": "#4b5563", "accent": "#1d4ed8", "accent2": "#9f4507"},
     "fonts": {"heading": "Segoe UI", "body": "Segoe UI"}},
    {"id": "oscuro", "name": "Oscuro",
     "colors": {"background": "#12151c", "surface": "#1e2430", "text": "#f1f3f7", "muted": "#b0b8c6", "accent": "#7db0ff", "accent2": "#f2b45a"},
     "fonts": {"heading": "Segoe UI", "body": "Segoe UI"}},
    {"id": "editorial", "name": "Editorial",
     "colors": {"background": "#fbf7f0", "surface": "#f0e8da", "text": "#211b15", "muted": "#5a4d3f", "accent": "#9a2b2b", "accent2": "#2f5d62"},
     "fonts": {"heading": "Georgia", "body": "Calibri"}},
    {"id": "carmesi", "name": "Carmesí",
     "colors": {"background": "#4a1520", "surface": "#5f2230", "text": "#fdf3f2", "muted": "#ecc9cb", "accent": "#f4b3b6", "accent2": "#f3d491"},
     "fonts": {"heading": "Georgia", "body": "Calibri"}},
    {"id": "pizarra", "name": "Pizarra",
     "colors": {"background": "#16211d", "surface": "#223229", "text": "#eef5f1", "muted": "#b2c5ba", "accent": "#82d6a6", "accent2": "#e8c672"},
     "fonts": {"heading": "Cambria", "body": "Calibri"}},
    {"id": "tecnico", "name": "Técnico",
     "colors": {"background": "#ffffff", "surface": "#f0f0f0", "text": "#111111", "muted": "#454545", "accent": "#0b5c8a", "accent2": "#a1361b"},
     "fonts": {"heading": "Consolas", "body": "Arial"}},
    {"id": "oceano", "name": "Océano",
     "colors": {"background": "#f2f7fb", "surface": "#deebf5", "text": "#0f2233", "muted": "#3d5468", "accent": "#0b6e99", "accent2": "#b8410a"},
     "fonts": {"heading": "Calibri", "body": "Calibri"}},
]
DEFAULT_THEME = "claro"
_BY_ID = {t["id"]: t for t in THEMES}


def list_themes() -> list[dict[str, Any]]:
    return [{"id": t["id"], "name": t["name"], "colors": dict(t["colors"]), "fonts": dict(t["fonts"])} for t in THEMES]


def get_theme(theme_id: str | None) -> dict[str, Any]:
    """The theme, or the default one when the id is unknown (an old deck must still render)."""
    return _BY_ID.get(theme_id or "", _BY_ID[DEFAULT_THEME])


def require_theme(theme_id: str) -> str:
    if theme_id not in _BY_ID:
        raise CiceroError(f"Unknown theme {theme_id!r}. Available: {', '.join(_BY_ID)}.")
    return theme_id


# ---------------- colour maths ----------------

def hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


def rgb_to_hex(rgb: tuple[float, float, float]) -> str:
    return "#{:02x}{:02x}{:02x}".format(*(max(0, min(255, round(c))) for c in rgb))


def blend(a: str, b: str, t: float) -> str:
    """Linear mix of two hex colours: t=0 gives ``a``, t=1 gives ``b``."""
    ra, rb = hex_to_rgb(a), hex_to_rgb(b)
    return rgb_to_hex(tuple(x * (1 - t) + y * t for x, y in zip(ra, rb)))  # type: ignore[arg-type]


def _lin(c: int) -> float:
    s = c / 255
    return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4


def luminance(value: str) -> float:
    r, g, b = hex_to_rgb(value)
    return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)


def contrast(fg: str, bg: str) -> float:
    """WCAG contrast ratio between two hex colours (1 to 21)."""
    l1, l2 = luminance(fg), luminance(bg)
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


def series_colors(theme: dict[str, Any]) -> list[str]:
    """Colours for chart series and pie slices; each one reads against the theme background."""
    c = theme["colors"]
    palette = [c["accent"], c["accent2"], blend(c["accent"], c["text"], 0.45), blend(c["accent2"], c["text"], 0.45),
               blend(c["accent"], c["accent2"], 0.5), c["muted"]]
    out: list[str] = []
    for colour in palette:
        if colour not in out:
            out.append(colour)
    return out


def font_kind(name: str) -> str:
    low = (name or "").lower()
    if any(k in low for k in ("consolas", "courier", "mono")):
        return "mono"
    if any(k in low for k in ("georgia", "cambria", "times", "garamond")):
        return "serif"
    return "sans"


def css_font_stack(name: str) -> str:
    kind = font_kind(name)
    fallback = {"mono": '"Cascadia Mono", "DejaVu Sans Mono", monospace',
                "serif": '"Times New Roman", "Liberation Serif", "DejaVu Serif", serif',
                "sans": '"Helvetica Neue", Arial, "Liberation Sans", "DejaVu Sans", sans-serif'}[kind]
    return f'"{name}", {fallback}'
