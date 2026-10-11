"""Morph, multimedia and linked-data routes use the same contract as MCP."""
from fastapi import APIRouter, Request
from fastapi.concurrency import run_in_threadpool
from .. import media, decks
from .deps import services, tool
from .sources import read_upload

router = APIRouter(prefix='/api')

@router.post('/decks/{deck_id}/live/media')
async def media_control(request: Request, deck_id: str):
    return tool(request, 'deck_media_control', **{**await request.json(), 'deck_id': deck_id})

@router.get('/decks/{deck_id}/transitions')
def transitions_get(request: Request, deck_id: str):
    return tool(request, 'deck_transitions', deck_id=deck_id)

@router.put('/decks/{deck_id}/transitions')
async def transitions_set(request: Request, deck_id: str):
    return tool(request, 'deck_transitions', **{**await request.json(), 'deck_id': deck_id, 'action': 'set'})

@router.delete('/decks/{deck_id}/transitions')
def transitions_reset(request: Request, deck_id: str):
    return tool(request, 'deck_transitions', deck_id=deck_id, action='reset')

@router.post('/decks/{deck_id}/media', status_code=201)
async def media_add(request: Request, deck_id: str):
    svc = services(request)
    if request.headers.get('content-type', '').startswith('multipart/'):
        data, filename, _ = await read_upload(request, svc.config.max_upload_bytes)
        return await run_in_threadpool(media.add, svc, deck_id, data, filename)
    return await run_in_threadpool(tool, request, 'media_import', **{**await request.json(), 'deck_id': deck_id})

@router.get('/decks/{deck_id}/media')
def media_list(request: Request, deck_id: str):
    return tool(request, 'media_get', deck_id=deck_id)

@router.get('/decks/{deck_id}/data-links')
def links_get(request: Request, deck_id: str):
    return tool(request, 'dataset_links', deck_id=deck_id)

@router.get('/decks/{deck_id}/data-links/version')
def data_version(request: Request, deck_id: str):
    svc = services(request)
    decks._deck_row(svc, deck_id)
    from ..util import jdump, sha256_hex
    rows = svc.db.query('SELECT id,revision FROM slides WHERE deck_id=? ORDER BY position', (deck_id,))
    return {'content_version': sha256_hex(jdump([(r['id'],r['revision']) for r in rows]))[:16]}

@router.post('/decks/{deck_id}/data-links', status_code=201)
async def links_add(request: Request, deck_id: str):
    return await run_in_threadpool(tool, request, 'dataset_link', **{**await request.json(), 'deck_id': deck_id})

@router.post('/decks/{deck_id}/data-links/control')
async def links_control(request: Request, deck_id: str):
    return await run_in_threadpool(tool, request, 'dataset_link_control', **{**await request.json(), 'deck_id': deck_id})

@router.post('/decks/{deck_id}/data-links/bind')
async def links_bind(request: Request, deck_id: str):
    return await run_in_threadpool(tool, request, 'dataset_bind', **{**await request.json(), 'deck_id': deck_id})
