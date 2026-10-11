"""Per-slide transitions and stable object matching shared by web and native output."""
from __future__ import annotations

from typing import Literal, Optional
from pydantic import BaseModel, Field, field_validator
from . import decks
from .errors import CiceroError


class Transition(BaseModel):
    effect: Literal['none', 'fade', 'slide', 'convex', 'concave', 'zoom', 'morph'] = 'fade'
    duration_ms: int = Field(700, ge=100, le=5000)
    easing: Literal['linear', 'ease', 'ease-in', 'ease-out', 'ease-in-out'] = 'ease-in-out'
    group: str = Field('default', max_length=80)
    unmatched: bool = True
    native_effect: Optional[str] = None

    @field_validator('native_effect')
    @classmethod
    def _native(cls,value):
        if value is None:
            return None
        from .vendor.ppt_master import pptx_transitions as T
        return T.normalize_transition_effect(value,allow_none=True) or 'none'


class Args(BaseModel):
    deck_id: str
    action: Literal['get', 'set', 'reset', 'inspect'] = 'get'
    default: Optional[Transition] = None
    slides: dict[str, Transition] = Field(default_factory=dict)


def get(svc, deck_id):
    decks._deck_row(svc, deck_id)
    return svc.db.get_setting('transitions:' + deck_id, {}) or {}


def run(svc, args):
    deck = decks.deck_view(svc, args.deck_id)
    if args.action == 'inspect':
        pairs = []
        for before, after in zip(deck['slides'], deck['slides'][1:]):
            a = {b['id']: b for b in before['blocks'] if b.get('id')}
            b = {b['id']: b for b in after['blocks'] if b.get('id')}
            pairs.append({'from': before['id'], 'to': after['id'],
                          'matched': sorted(a.keys() & b.keys()),
                          'entering': sorted(b.keys() - a.keys()), 'leaving': sorted(a.keys() - b.keys())})
        return {'pairs': pairs, 'settings': get(svc, args.deck_id)}
    if args.action == 'reset':
        svc.db.set_setting('transitions:' + args.deck_id, {})
    elif args.action == 'set':
        ids = {s['id'] for s in deck['slides']}
        if args.slides.keys() - ids:
            raise CiceroError('Transition overrides must name slides in this deck.')
        with svc.db.transaction():
            settings = get(svc, args.deck_id)
            if args.default is not None:
                settings['default'] = args.default.model_dump()
            settings['slides'] = {**settings.get('slides', {}), **{k: v.model_dump() for k, v in args.slides.items()}}
            svc.db.set_setting('transitions:' + args.deck_id, settings)
            svc.db.execute('UPDATE decks SET updated_ts=? WHERE id=?', (svc.clock(), args.deck_id))
    return {'deck_id': args.deck_id, **get(svc, args.deck_id)}


def attributes(slide):
    t = slide.get('transition')
    if not t:
        return ''
    from .render import esc
    effect = t['effect']
    if effect == 'morph':
        return (f' data-auto-animate data-auto-animate-id="{esc(t["group"])}"'
                f' data-auto-animate-duration="{t["duration_ms"]/1000}"'
                f' data-auto-animate-easing="{t["easing"]}"'
                f' data-auto-animate-unmatched="{str(t["unmatched"]).lower()}" data-transition="none"')
    return f' data-transition="{effect}" data-transition-duration="{t["duration_ms"]}"'


def apply_native(prs, deck):
    """Transition XML remains native; object names beginning !! force identity matching."""
    from .vendor.ppt_master import pptx_transitions as T
    for slide, data in zip(prs.slides, deck['slides']):
        t = data.get('transition')
        if not t:
            continue
        effect = native_effect(t.get('native_effect') or t['effect'])
        T.apply_slide_motion(slide._element,
            enter=T.EnterUpdate(policy='replace', effect=effect, duration=t['duration_ms']/1000),
            advance=T.AdvanceUpdate(mode='preserve'))


def native_effect(effect):
    return {'none':None,'slide':'push','convex':'wheel','concave':'wipe'}.get(effect, effect)
