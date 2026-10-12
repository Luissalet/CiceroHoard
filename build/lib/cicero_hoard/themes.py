"""Built-in themes: colours, fonts (all of them present on Windows and usable in PPTX) and contrast helpers."""

from __future__ import annotations

import re
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


def theme_of(deck: dict[str, Any]) -> dict[str, Any]:
    """The theme a deck is drawn with: its saved custom definition (``theme_def``, attached by ``deck_view``) or a built-in one."""
    definition = deck.get("theme_def")
    return definition if isinstance(definition, dict) else get_theme(deck.get("theme"))


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


# ---------------- contrast check ----------------

MIN_CONTRAST = 4.5
# Every colour that carries text or a mark must read on both the page and the card.
READABLE_ON = {"text": ("background", "surface"), "muted": ("background", "surface"),
               "accent": ("background", "surface"), "accent2": ("background", "surface")}


def contrast_issues(theme: dict[str, Any], minimum: float = MIN_CONTRAST) -> list[dict[str, Any]]:
    """The pairs of a theme that fall below ``minimum`` (WCAG contrast): ``[{"fg", "bg", "ratio"}]``; empty when the theme passes."""
    colors = theme["colors"]
    out: list[dict[str, Any]] = []
    for fg, backgrounds in READABLE_ON.items():
        for bg in backgrounds:
            ratio = contrast(colors[fg], colors[bg])
            if ratio < minimum:
                out.append({"fg": fg, "bg": bg, "ratio": round(ratio, 2)})
    return out


def fit_contrast(theme: dict[str, Any], minimum: float = MIN_CONTRAST) -> tuple[dict[str, Any], list[str]]:
    """A copy of the theme in which every failing colour is pulled toward black or white until it reads.

    The pull goes in the direction that raises contrast against the page, in steps of 5%, so the hue is kept as long as possible.
    Returns the theme and one warning per colour that had to change.
    """
    fixed = {**theme, "colors": dict(theme["colors"])}
    warnings: list[str] = []
    colors = fixed["colors"]
    for fg, backgrounds in READABLE_ON.items():
        original = colors[fg]
        # Lighten on a dark page, darken on a light one (the page and the card share a side in every sane theme).
        target = "#ffffff" if luminance(colors["background"]) < 0.4 else "#000000"
        for step in range(0, 21):
            candidate = blend(original, target, step / 20)
            if all(contrast(candidate, colors[bg]) >= minimum for bg in backgrounds):
                colors[fg] = candidate
                break
        else:
            colors[fg] = target
        if colors[fg] != original:
            warnings.append(f"{fg} changed from {original} to {colors[fg]} to reach a contrast of {minimum}:1 on the background and the cards")
    return fixed, warnings


# ---------------- custom themes ----------------

HEX6 = re.compile(r"^#[0-9a-fA-F]{6}$")
# Fonts that exist on Windows and embed predictably in PPTX; a design system's own font is used only when it is one of these.
SAFE_FONTS = ("Segoe UI", "Calibri", "Cambria", "Arial", "Georgia", "Consolas", "Times New Roman", "Verdana", "Tahoma", "Trebuchet MS",
              "Courier New", "Candara", "Constantia", "Corbel", "Garamond", "Palatino Linotype", "Century Gothic", "Franklin Gothic Medium")
_GENERIC_FONT = {"serif": "Georgia", "ui-serif": "Georgia", "monospace": "Consolas", "ui-monospace": "Consolas", "sans-serif": "Segoe UI",
                 "ui-sans-serif": "Segoe UI", "system-ui": "Segoe UI", "cursive": "Segoe UI", "fantasy": "Segoe UI"}
_SAFE_LOWER = {name.lower(): name for name in SAFE_FONTS}
MAX_RADIUS = 32


def pick_font(stack: str, fallback: str = "Segoe UI") -> tuple[str, str | None]:
    """A usable font name for a CSS family stack, and a warning when the stack's first family had to be replaced."""
    families = [f.strip().strip("\"'") for f in (stack or "").split(",") if f.strip()]
    if not families:
        return fallback, None
    first = families[0]
    for family in families:
        if family.lower() in _SAFE_LOWER:
            chosen = _SAFE_LOWER[family.lower()]
            return chosen, (None if family.lower() == first.lower() else f"font {first} is not a Windows font; using {chosen}")
    for family in families:
        if family.lower() in _GENERIC_FONT:
            chosen = _GENERIC_FONT[family.lower()]
            return chosen, (None if first.lower() in _GENERIC_FONT and _GENERIC_FONT[first.lower()] == chosen else f"font {first} is not a Windows font; using {chosen}")
    return fallback, f"font {first} is not a Windows font; using {fallback}"


def radius_px(value: Any) -> int:
    """A CSS length such as ``10px`` or ``0.5rem`` as whole pixels, clamped to 0..MAX_RADIUS; anything else is 0."""
    match = re.match(r"^\s*(-?\d+(?:\.\d+)?)\s*(px|rem|em)?\s*$", str(value or ""))
    if not match:
        return 0
    px = float(match.group(1)) * (16 if match.group(2) in ("rem", "em") else 1)
    return max(0, min(MAX_RADIUS, round(px)))


def clean_custom_theme(raw: dict[str, Any]) -> dict[str, Any]:
    """Validate a custom theme: the six colours as #rrggbb, two font names, an optional radius. Raises CiceroError."""
    colors = raw.get("colors") or {}
    fonts = raw.get("fonts") or {}
    for key in COLOR_KEYS:
        if not isinstance(colors.get(key), str) or not HEX6.match(colors[key]):
            raise CiceroError(f"Theme colour {key!r} must be a #rrggbb value.")
    for key in ("heading", "body"):
        if not isinstance(fonts.get(key), str) or not fonts[key].strip() or len(fonts[key]) > 80:
            raise CiceroError(f"Theme font {key!r} must be a font name.")
    name = str(raw.get("name") or "").strip()[:80]
    if not name:
        raise CiceroError("A theme needs a name.")
    return {"id": str(raw["id"]), "name": name, "colors": {k: colors[k].lower() for k in COLOR_KEYS},
            "fonts": {"heading": fonts["heading"].strip(), "body": fonts["body"].strip()}, "radius": radius_px(raw.get("radius", 0))}


def theme_from_roles(roles: dict[str, Any], *, theme_id: str, name: str, mode: str = "light") -> tuple[dict[str, Any], list[str]]:
    """Map a design system's roles (see Vitruvius's ``roles``) to a Cicero theme and make it pass the contrast check.

    Colours: page = background, card = the stronger panel fill (surface2), text, muted, accent and accent2 as given. Fonts: the
    heading and body stacks reduced to a Windows font. Radius: the system's ``md``. Returns the theme and the warnings
    (a replaced font, a colour pulled to reach the contrast).
    """
    if mode not in ("light", "dark"):
        raise CiceroError("mode must be 'light' or 'dark'.")
    palette = roles.get(mode)
    if not isinstance(palette, dict):
        raise CiceroError(f"The design system has no {mode} colours.")
    warnings: list[str] = []
    heading, warn_h = pick_font((roles.get("fonts") or {}).get("heading", ""))
    body, warn_b = pick_font((roles.get("fonts") or {}).get("body", ""))
    warnings += [w for w in (warn_h, warn_b) if w]
    raw = {"id": theme_id, "name": name,
           "colors": {"background": palette.get("background"), "surface": palette.get("surface2") or palette.get("surface"),
                      "text": palette.get("text"), "muted": palette.get("muted") or palette.get("text"),
                      "accent": palette.get("accent"), "accent2": palette.get("accent2") or palette.get("accent")},
           "fonts": {"heading": heading, "body": body}, "radius": (roles.get("radius") or {}).get("md", 0)}
    theme = clean_custom_theme(raw)
    theme, fixes = fit_contrast(theme)
    return theme, warnings + fixes
