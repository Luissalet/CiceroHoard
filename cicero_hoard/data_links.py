"""Durable linked data with immutable snapshots and conflict-aware visual recipes."""
from __future__ import annotations

import json
import logging
import threading
from copy import deepcopy
from pathlib import Path
from typing import Literal, Optional
from urllib.parse import urlsplit, unquote
import httpx
from pydantic import BaseModel, Field, model_validator, create_model
from . import datasets, decks
from .errors import CiceroError, RevisionConflict
from .models import MAX_BLOCKS
from .hoard_link.ids import new_ulid as new_id
from .util import jdump, jload


class LinkArgs(BaseModel):
    deck_id: str
    path: str = ''
    url: str = ''
    filename: str = ''
    title: str = ''
    sheet: Optional[str] = None
    header_row: int = Field(1, ge=1)
    delimiter: Optional[Literal[',', ';', '\t', '|']] = None
    number_format: datasets.NumberFormat = 'auto'
    interval_s: float = Field(60, gt=0, allow_inf_nan=False)
    enabled: bool = True

    @model_validator(mode='after')
    def _location(self):
        if bool(self.path) == bool(self.url):
            raise ValueError('Supply exactly one local path or HTTP(S) URL')
        if self.url and urlsplit(self.url).scheme not in ('http', 'https'):
            raise ValueError('Use an HTTP(S) data URL')
        return self


class RefArgs(BaseModel):
    deck_id: str
    link_id: Optional[str] = None


class ControlArgs(RefArgs):
    action: Literal['refresh', 'pause', 'resume', 'unlink'] = 'refresh'
    interval_s: Optional[float] = Field(None, gt=0, allow_inf_nan=False)


VisualMapping = create_model('VisualMapping', **{name: (field.annotation, deepcopy(field))
    for name, field in datasets.VisualArgs.model_fields.items() if name not in ('deck_id', 'source_id')})
TransformRecipe = create_model('TransformRecipe', **{name: (field.annotation, deepcopy(field))
    for name, field in datasets.TransformArgs.model_fields.items() if name not in ('deck_id', 'source_id')})


class BindArgs(BaseModel):
    deck_id: str
    link_id: str
    slide_id: str
    block_index: int = Field(0, ge=0, le=8)
    mapping: VisualMapping = Field(default_factory=VisualMapping)
    transform: Optional[TransformRecipe] = None
    expected_revision: Optional[int] = Field(None, ge=1)


def _row(svc, deck_id, link_id):
    decks._deck_row(svc, deck_id)
    row = svc.db.one('SELECT * FROM data_links WHERE id=? AND deck_id=?', (link_id, deck_id))
    if row is None:
        raise CiceroError('Linked dataset not found.')
    return row


def inspect(svc, args):
    decks._deck_row(svc, args.deck_id)
    rows = [_row(svc, args.deck_id, args.link_id)] if args.link_id else svc.db.query('SELECT * FROM data_links WHERE deck_id=? ORDER BY id', (args.deck_id,))
    items = []
    for row in rows:
        bindings = [dict(r) for r in svc.db.query('SELECT id,slide_id,block_id,error,definition FROM data_bindings WHERE link_id=?', (row['id'],))]
        for b in bindings:
            b['definition'] = jload(b['definition'], {})
        items.append({**dict(row), 'enabled': bool(row['enabled']), 'definition': jload(row['definition'], {}), 'bindings': bindings})
    return {'items': items}


def create(svc, args):
    decks._deck_row(svc, args.deck_id)
    definition = args.model_dump(exclude={'deck_id', 'enabled', 'interval_s'})
    if args.path:
        definition['path'] = str(Path(args.path).expanduser().resolve())
    key = jdump(definition)
    with svc.db.transaction():
        row = svc.db.one('SELECT id FROM data_links WHERE deck_id=? AND definition=?', (args.deck_id, key))
        link_id = row['id'] if row else new_id()
        if not row:
            svc.db.execute('INSERT INTO data_links(id,deck_id,definition,enabled,interval_s) VALUES(?,?,?,?,?)',
                           (link_id, args.deck_id, key, args.enabled, args.interval_s))
    result = refresh(svc, args.deck_id, link_id)
    return {**result, 'reused': bool(row)}


def _read(svc, deck_id, definition):
    args = datasets.ImportArgs.model_validate({**definition, 'deck_id': deck_id})
    if definition.get('path'):
        return datasets.import_data(svc, args)
    try:
        with httpx.Client(follow_redirects=True, timeout=30) as client:
            with client.stream('GET', definition['url']) as response:
                response.raise_for_status()
                chunks = []
                size = 0
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > svc.config.max_upload_bytes:
                        raise CiceroError('The data exceeds the configured upload size.')
                    chunks.append(chunk)
                data = b''.join(chunks)
    except httpx.HTTPError as error:
        raise CiceroError('Data URL could not be read: ' + str(error)) from error
    filename = definition.get('filename') or Path(unquote(urlsplit(definition['url']).path)).name or 'feed.csv'
    # Include the URL in the immutable provenance, not only in the link recipe.
    return datasets.import_data(svc, args, data, filename, {'url': definition['url']})


def _visual(svc, deck_id, source_id, definition):
    if definition.get('transform'):
        transformed = datasets.transform(svc, datasets.TransformArgs.model_validate({**definition['transform'], 'deck_id': deck_id, 'source_id': source_id}))
        source_id = transformed['source_id']
    return datasets.visual(svc, datasets.VisualArgs.model_validate({**definition['mapping'], 'deck_id': deck_id, 'source_id': source_id}))


def bind(svc, args):
    with svc.data_link_lock:
        return _bind(svc, args)


def _bind(svc, args):
    row = _row(svc, args.deck_id, args.link_id)
    if row['source_id'] is None:
        raise CiceroError('Refresh this link successfully before binding a visual.')
    definition = {'mapping': args.mapping.model_dump(exclude_none=True),
                  'transform': args.transform.model_dump(exclude_none=True) if args.transform else {}}
    result = _visual(svc, args.deck_id, row['source_id'], definition)
    with svc.db.transaction():
        slide = decks.get_slide(svc, args.deck_id, args.slide_id)
        if args.expected_revision is not None and args.expected_revision != slide['revision']:
            raise RevisionConflict('The slide changed before binding this visual.')
        if args.block_index > len(slide['blocks']):
            raise CiceroError('Replace an existing block or append at the current block count.')
        if args.block_index == len(slide['blocks']) and len(slide['blocks']) >= MAX_BLOCKS:
            raise CiceroError('This slide is full; replace a block or choose another slide.')
        blocks = deepcopy(slide['blocks'])
        old = blocks[args.block_index] if args.block_index < len(blocks) else {}
        block_id = old.get('id') or 'data-' + new_id()
        block = {**result['block'], **{k: old[k] for k in ('frame', 'font_size', 'build', 'effect', 'duration_ms') if k in old}, 'id': block_id}
        if args.block_index == len(blocks):
            blocks.append(block)
        else:
            blocks[args.block_index] = block
        binding = svc.db.one('SELECT * FROM data_bindings WHERE slide_id=? AND block_id=?', (args.slide_id, block_id))
        binding_id = binding['id'] if binding else new_id()
        before = jload(binding['definition'], {}) if binding else {}
        definition['citation_baseline'] = before.get('citation_baseline', slide['sources'])
        definition['source_ids'] = result['source_ids']
        sources = _citations(svc, slide, binding_id, before.get('source_ids', []), result['source_ids'], definition['citation_baseline'])
        if blocks != slide['blocks'] or sources != slide['sources']:
            slide = decks.patch_slide(svc, args.deck_id, args.slide_id, {'blocks': blocks, 'sources': sources}, reason='linked visual')
        svc.db.execute('INSERT INTO data_bindings(id,link_id,slide_id,block_id,definition,last_block) VALUES(?,?,?,?,?,?) '
                       'ON CONFLICT(slide_id,block_id) DO UPDATE SET link_id=excluded.link_id,definition=excluded.definition,last_block=excluded.last_block,error=\'\'',
                       (binding_id, args.link_id, args.slide_id, block_id, jdump(definition), jdump(block)))
    return {'binding_id': binding_id, 'slide': slide, 'warnings': result['warnings']}


def _citations(svc, slide, binding_id, old_sources, new_sources, baseline):
    protected = set(baseline)
    protected.update(svc.db.get_setting('manual_citations:' + slide['id'], []))
    for other in svc.db.query('SELECT definition FROM data_bindings WHERE slide_id=? AND id!=?', (slide['id'],binding_id)):
        protected.update(jload(other['definition'], {}).get('source_ids', []))
    return list(dict.fromkeys([sid for sid in slide['sources'] if sid not in old_sources or sid in protected] + new_sources))


def _apply(svc, deck_id, binding, result):
    with svc.db.transaction():
        slide = decks.get_slide(svc, deck_id, binding['slide_id'])
        blocks = deepcopy(slide['blocks'])
        indices = [i for i, b in enumerate(blocks) if b.get('id') == binding['block_id']]
        if len(indices) != 1:
            raise RevisionConflict('The linked block was removed or its ID changed; bind it again.')
        index = indices[0]
        old = blocks[index]
        previous = jload(binding['last_block'], {})
        # Layout and stage edits are preserved; manual changes to data are never overwritten.
        style = ('frame', 'font_size', 'build', 'effect', 'duration_ms', 'action')
        if {k: v for k, v in old.items() if k not in style} != {k: v for k, v in previous.items() if k not in style}:
            raise RevisionConflict('The linked visual was edited manually; bind it again to resume data updates.')
        block = {**result['block'], **{k: old[k] for k in style if k in old}, 'id': binding['block_id']}
        blocks[index] = block
        definition = jload(binding['definition'], {})
        sources = _citations(svc, slide, binding['id'], definition.get('source_ids', []), result['source_ids'], definition.get('citation_baseline', []))
        changed = blocks != slide['blocks'] or sources != slide['sources']
        if changed:
            decks.patch_slide(svc, deck_id, slide['id'], {'blocks': blocks, 'sources': sources}, reason='linked data refresh')
        definition['source_ids'] = result['source_ids']
        svc.db.execute('UPDATE data_bindings SET last_block=?,definition=?,error=\'\' WHERE id=?', (jdump(block), jdump(definition), binding['id']))
    return changed


def refresh(svc, deck_id, link_id):
    with svc.data_link_lock:
        row = _row(svc, deck_id, link_id)
        try:
            result = _read(svc, deck_id, jload(row['definition'], {}))
            source_id = result['source_id']
            changed = source_id != row['source_id']
            svc.db.execute('UPDATE data_links SET source_id=?,checked_ts=?,refreshed_ts=?,error=\'\' WHERE id=?',
                           (source_id, svc.clock(), svc.clock() if changed else row['refreshed_ts'], link_id))
            applied = []
            for binding in svc.db.query('SELECT * FROM data_bindings WHERE link_id=?', (link_id,)):
                try:
                    visual = _visual(svc, deck_id, source_id, jload(binding['definition'], {}))
                    updated = _apply(svc, deck_id, binding, visual)
                    applied.append({'binding_id': binding['id'], 'changed': updated, 'warnings': visual['warnings']})
                except Exception as error:
                    svc.db.execute('UPDATE data_bindings SET error=? WHERE id=?', (str(error), binding['id']))
                    applied.append({'binding_id': binding['id'], 'error': str(error)})
            return {'link_id': link_id, 'source_id': source_id, 'changed': changed, 'bindings': applied}
        except Exception as error:
            svc.db.execute('UPDATE data_links SET checked_ts=?,error=? WHERE id=?', (svc.clock(), str(error), link_id))
            return {'link_id': link_id, 'source_id': row['source_id'], 'changed': False, 'error': str(error), 'retained_last_good': row['source_id'] is not None}


def control(svc, args):
    rows = inspect(svc, args)['items']
    results = []
    with svc.data_link_lock:
        for row in rows:
            if args.action == 'refresh':
                results.append(refresh(svc, args.deck_id, row['id']))
            elif args.action == 'unlink':
                svc.db.execute('DELETE FROM data_links WHERE id=?', (row['id'],))
                results.append({'link_id': row['id'], 'unlinked': True, 'snapshots_and_visuals_preserved': True})
            else:
                svc.db.execute('UPDATE data_links SET enabled=?,interval_s=?,revision=revision+1 WHERE id=?',
                               (args.action == 'resume', args.interval_s or row['interval_s'], row['id']))
                results.append({'link_id': row['id'], 'enabled': args.action == 'resume'})
    return {'items': results}


class Worker:
    def __init__(self, svc):
        self.svc = svc
        self.stopping = threading.Event()
        self.thread = None

    def tick(self):
        for row in self.svc.db.query('SELECT id,deck_id,checked_ts,interval_s FROM data_links WHERE enabled=1'):
            if self.stopping.is_set():
                break
            if row['checked_ts'] is None or self.svc.clock() - row['checked_ts'] >= row['interval_s']:
                refresh(self.svc, row['deck_id'], row['id'])

    def start(self):
        if self.thread is not None:
            return
        def loop():
            while not self.stopping.wait(.5):
                try:
                    self.tick()
                except Exception:
                    logging.getLogger('cicero').exception('Linked data refresh failed')
        self.thread = threading.Thread(target=loop, name='cicero-linked-data', daemon=True)
        self.thread.start()

    def stop(self):
        self.stopping.set()
        if self.thread is not None:
            self.thread.join()  # never close the DB while an in-flight refresh still uses it
