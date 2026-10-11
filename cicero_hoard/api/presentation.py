"""Separate local audience and speaker surfaces, sharing only navigation state."""
from fastapi import APIRouter,Request
from fastapi.responses import HTMLResponse
from .. import presentation,decks as store
from .deps import services,tool
from .decks import PREVIEW_HEADERS

router=APIRouter(prefix='/api')

@router.post('/decks/{deck_id}/live')
async def start(request:Request,deck_id:str):
    return tool(request,'deck_live_start',**{**await request.json(),'deck_id':deck_id})

@router.get('/decks/{deck_id}/live/{session_id}/state')
def state(request:Request,deck_id:str,session_id:str):
    return presentation.validate_room(services(request),deck_id,session_id)

@router.post('/decks/{deck_id}/live/{session_id}/control')
async def control(request:Request,deck_id:str,session_id:str):
    presentation.validate_room(services(request),deck_id,session_id)
    return tool(request,'deck_live_control',**{**await request.json(),'deck_id':deck_id})

@router.get('/decks/{deck_id}/live/{session_id}/speaker')
def speaker(request:Request,deck_id:str,session_id:str):
    svc=services(request);state=presentation.validate_room(svc,deck_id,session_id)
    return {'slides':[{'id':s['id'],'notes':s['notes']} for s in store.deck_view(svc,deck_id)['slides']], 'state':state}

@router.get('/decks/{deck_id}/live/{session_id}/audience.html',response_class=HTMLResponse)
def audience(request:Request,deck_id:str,session_id:str,monitor:bool=False):
    return HTMLResponse(presentation.audience_document(services(request),deck_id,session_id,monitor=monitor),headers=PREVIEW_HEADERS)
