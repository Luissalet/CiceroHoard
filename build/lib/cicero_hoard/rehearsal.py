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


def rehearsal_plan(deck: dict[str, Any], *, duration_minutes: float = 15,
                   words_per_minute: int = 130, pause_seconds: int = 10,
                   main_slides: int | None = None) -> dict[str, Any]:
    slides = list(deck.get('slides') or [])
    if not slides:
        raise CiceroError('Add slides before planning a rehearsal.')
    count = len(slides) if main_slides is None else main_slides
    if not 1 <= count <= len(slides):
        raise CiceroError('main_slides must identify a nonempty prefix of this deck.')
    target = round(duration_minutes * 60)
    spoken = [spoken_notes(s.get('notes') or '') for s in slides[:count]]
    words = [len(_WORD.findall(n)) for n in spoken]
    missing = [s['id'] for s, n in zip(slides[:count], spoken) if not n]
    estimates = [math.ceil(n * 60 / words_per_minute) + pause_seconds for n in words]
    weights = [max(1, n) for n in estimates]
    # Largest remainder keeps the exact target without hiding a speech overrun.
    total_weight = sum(weights)
    allocated = [target * n // total_weight for n in weights]
    extra = target - sum(allocated)
    ranking = sorted(range(count), key=lambda i: (-(target * weights[i] % total_weight), i))
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
    return {'deck_id': deck['id'], 'target_seconds': target, 'planned_seconds': cursor,
            'main_slides': count, 'support_slides': len(slides) - count,
            'words_per_minute': words_per_minute, 'pause_seconds_per_slide': pause_seconds,
            'estimated_seconds': estimated, 'fits_estimate': None if estimated is None else estimated <= target,
            'remaining_seconds_estimate': None if estimated is None else target - estimated,
            'missing_notes': missing, 'timeline': timeline,
            'support': [{'slide_id': s['id'], 'position': s['position'], 'title': s['title']} for s in slides[count:]],
            'basis': 'speaker_notes_estimate', 'actual_elapsed_seconds': None,
            'note': 'Planning estimate: pauses, charts and delivery affect duration. An oral rehearsal has not been measured.'}
