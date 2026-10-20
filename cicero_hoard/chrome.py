"""Slide numbering and progress indicators shared by the preview, HTML, PPTX and template output.

A deck without settings keeps its historical footer: "n / total" with the built-in themes and the
template's own two-digit number. Support slides (after ``main_slides``) are excluded from the total
and from the progress indicator, so an appendix never reads "16 / 15".
"""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from . import decks
from .errors import CiceroError

KEY = 'chrome:'
CONTENT_LAYOUTS_ONLY = ('title', 'section', 'closing')


class Settings(BaseModel):
    model_config = ConfigDict(extra='forbid')
    number: Literal['auto', 'n', 'n_total', 'none'] = Field(
        'auto', description="auto keeps the theme's footer (n / total) or the template's two-digit number.")
    progress: Literal['none', 'bar', 'segments'] = 'none'
    position: Literal['bottom', 'top'] = 'bottom'
    thickness: int = Field(6, ge=2, le=20, description='Progress indicator height in slide pixels (1280-wide reference).')
    main_slides: Optional[int] = Field(None, ge=1, description='Slides after this count are support material: no total, no progress.')
    show_title: bool = Field(True, description='Show the deck title in the built-in footer.')
    on_cover: bool = Field(False, description='Also number title, section and closing slides.')


class Args(BaseModel):
    deck_id: str
    action: Literal['get', 'set', 'reset'] = 'get'
    settings: Optional[Settings] = None


def get(svc, deck_id: str) -> dict[str, Any]:
    decks._deck_row(svc, deck_id)
    return svc.db.get_setting(KEY + deck_id, {}) or {}


def run(svc, args: Args) -> dict[str, Any]:
    deck = decks.deck_view(svc, args.deck_id)
    if args.action == 'reset':
        svc.db.set_setting(KEY + args.deck_id, {})
    elif args.action == 'set':
        if args.settings is None:
            raise CiceroError('Pass settings to change numbering and progress.')
        if args.settings.main_slides and args.settings.main_slides > len(deck['slides']):
            raise CiceroError('main_slides cannot exceed the number of slides in the deck.')
        with svc.db.transaction():
            svc.db.set_setting(KEY + args.deck_id, args.settings.model_dump())
            svc.db.execute('UPDATE decks SET updated_ts=? WHERE id=?', (svc.clock(), args.deck_id))
    stored = get(svc, args.deck_id)
    return {'deck_id': args.deck_id, 'settings': resolve(stored), 'custom': bool(stored)}


def resolve(stored: Optional[dict[str, Any]]) -> dict[str, Any]:
    return Settings.model_validate(stored or {}).model_dump()


def counts(chrome: Optional[dict[str, Any]], number: int, total: int) -> tuple[int, bool]:
    """(main total, is support slide) for the 1-based slide ``number``."""
    main = (chrome or {}).get('main_slides') or total
    main = min(main, total)
    return main, number > main


def label(chrome: Optional[dict[str, Any]], number: int, total: int, *, template: bool = False) -> Optional[str]:
    """Text for the slide number, or None when no number is shown."""
    settings = resolve(chrome)
    main, support = counts(settings, number, total)
    mode = settings['number']
    if mode == 'none':
        return None
    if mode == 'auto':
        if template:
            return f'{number:02d}'
        mode = 'n_total'
    if support or mode == 'n':
        return f'{number:02d}' if template else str(number)
    return f'{number:02d} / {main:02d}' if template else f'{number} / {main}'


def shows_on(chrome: Optional[dict[str, Any]], layout: str) -> bool:
    return layout not in CONTENT_LAYOUTS_ONLY or resolve(chrome)['on_cover']


def progress_frames(chrome: Optional[dict[str, Any]], number: int, total: int, width: float, height: float) -> list[tuple[str, float, float, float, float]]:
    """(role, x, y, w, h) rectangles in slide pixels: a full track and the filled part, or one per segment."""
    settings = resolve(chrome)
    if settings['progress'] == 'none':
        return []
    main, support = counts(settings, number, total)
    if support:
        return []
    h = settings['thickness'] * width / 1280
    y = 0.0 if settings['position'] == 'top' else height - h
    if settings['progress'] == 'bar':
        done = width * number / main
        frames = [('track', 0.0, y, width, h)]
        return frames + [('fill', 0.0, y, done, h)] if done > 0 else frames
    gap = max(2.0, width / 640)
    step = (width - gap * (main - 1)) / main
    return [('fill' if i < number else 'track', i * (step + gap), y, step, h) for i in range(main)]
