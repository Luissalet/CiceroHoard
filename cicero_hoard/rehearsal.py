"""A rehearsal schedule from speaker notes; planning, never measured speech."""
from __future__ import annotations

import math
import re
from typing import Any

from .errors import CiceroError

_WORD = re.compile(r"[^\W_]+(?:[’'-][^\W_]+)*", re.UNICODE)
_SOURCE_LINE = re.compile(r"(?im)^\s*(?:source|sources|fuente|fuentes|references|referencias|timing|tiempo asignado)\s*:.*$")
_END_CITATION = re.compile(r"\s*\((?=[^()]*\b(?:PDF|TFM|pp?\.|fuente|source))[^()]*\)\s*$", re.IGNORECASE)


def spoken_notes(notes: str) -> str:
    """Exclude clearly marked citations/clock cues, retaining spoken asides."""
    text = _SOURCE_LINE.sub('', notes or '').strip()
    return _END_CITATION.sub('', text).strip()


def _clock(seconds: int) -> str:
    return f'{seconds // 60:02d}:{seconds % 60:02d}'


# Pace and pause assumptions beyond these make an estimate optimistic for a spoken defence or talk.
TYPICAL_MAX_WPM = 140
TYPICAL_MIN_PAUSE_SECONDS = 5


def rehearsal_plan(deck: dict[str, Any], *, duration_minutes: float = 15,
                   words_per_minute: int = 130, pause_seconds: int = 10,
                   main_slides: int | None = None, reserve_ratio: float = 0.1) -> dict[str, Any]:
    slides = list(deck.get('slides') or [])
    if not slides:
        raise CiceroError('Add slides before planning a rehearsal.')
    count = len(slides) if main_slides is None else main_slides
    if not 1 <= count <= len(slides):
        raise CiceroError('main_slides must identify a nonempty prefix of this deck.')
    if not 0 <= reserve_ratio < 1:
        raise CiceroError('reserve_ratio must be at least 0 and below 1.')
    target = round(duration_minutes * 60)
    # The schedule is built inside a reserve: a plan that ends exactly at the limit has no room for delivery.
    reserve = round(target * reserve_ratio)
    budget = target - reserve
    spoken = [spoken_notes(s.get('notes') or '') for s in slides[:count]]
    words = [len(_WORD.findall(n)) for n in spoken]
    missing = [s['id'] for s, n in zip(slides[:count], spoken) if not n]
    estimates = [math.ceil(n * 60 / words_per_minute) + pause_seconds for n in words]
    weights = [max(1, n) for n in estimates]
    # Largest remainder fills the budget exactly without hiding a speech overrun.
    total_weight = sum(weights)
    allocated = [budget * n // total_weight for n in weights]
    extra = budget - sum(allocated)
    ranking = sorted(range(count), key=lambda i: (-(budget * weights[i] % total_weight), i))
    for i in ranking[:extra]:
        allocated[i] += 1
    timeline, cursor = [], 0
    for i, slide in enumerate(slides[:count]):
        end = cursor + allocated[i]
        timeline.append({'slide_id': slide['id'], 'position': slide['position'], 'title': slide['title'],
                         'word_count': words[i], 'notes_missing': slide['id'] in missing,
                         'estimated_seconds': None if slide['id'] in missing else estimates[i],
                         'slot_seconds': allocated[i], 'start': _clock(cursor), 'end': _clock(end)})
        cursor = end
    estimated = None if missing else sum(estimates)
    risk = None if estimated is None else 'over' if estimated > target else 'tight' if estimated > budget else 'ok'
    warnings = []
    if words_per_minute > TYPICAL_MAX_WPM:
        warnings.append(f'{words_per_minute} words per minute is faster than a typical spoken pace '
                        f'(up to {TYPICAL_MAX_WPM}); the estimate is optimistic.')
    if pause_seconds < TYPICAL_MIN_PAUSE_SECONDS:
        warnings.append(f'{pause_seconds} s per slide leaves little time for changes, charts and click stages; '
                        f'the estimate is optimistic.')
    if risk == 'over':
        warnings.append(f'The speech is estimated {estimated - target} s over the limit. Shorten the notes '
                        'instead of assuming a faster pace.')
    elif risk == 'tight':
        warnings.append(f'The estimate leaves {target - estimated} s, less than the {reserve} s reserve. '
                        'Live delivery usually runs longer than a word count.')
    return {'deck_id': deck['id'], 'target_seconds': target, 'reserve_seconds': reserve,
            'budget_seconds': budget, 'planned_seconds': cursor,
            'main_slides': count, 'support_slides': len(slides) - count,
            'words_per_minute': words_per_minute, 'pause_seconds_per_slide': pause_seconds,
            'estimated_seconds': estimated, 'fits_estimate': None if estimated is None else estimated <= target,
            'remaining_seconds_estimate': None if estimated is None else target - estimated,
            'fits_with_reserve': None if estimated is None else estimated <= budget, 'risk': risk,
            'warnings': warnings,
            'missing_notes': missing, 'timeline': timeline,
            'support': [{'slide_id': s['id'], 'position': s['position'], 'title': s['title']} for s in slides[count:]],
            'basis': 'speaker_notes_estimate', 'actual_elapsed_seconds': None,
            'note': 'Planning estimate: pauses, charts and delivery affect duration. An oral rehearsal has not been measured.'}
