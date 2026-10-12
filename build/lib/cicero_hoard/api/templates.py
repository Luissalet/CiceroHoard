"""Reusable PPTX template attachment, through the same product service as MCP."""
from fastapi import APIRouter, Request
from fastapi.concurrency import run_in_threadpool
from ..agent_tools import DeckTemplateArgs
from ..templates import attach_template, inspect_bytes, read_template
from ..errors import CiceroError
from .deps import services, tool
from .sources import read_upload

router=APIRouter(prefix='/api')


@router.post('/templates/inspect')
async def inspect(request: Request):
    svc=services(request)
    if request.headers.get('content-type','').startswith('multipart/'):
        data,filename,_=await read_upload(request,svc.config.max_upload_bytes)
        if not filename.lower().endswith('.pptx'):raise CiceroError('Choose a .pptx template file.')
    else:
        body=await request.json();data=read_template(svc,str(body.get('path') or ''))
    return await run_in_threadpool(inspect_bytes,data)


@router.get('/decks/{deck_id}/template')
def get_template(request: Request, deck_id: str):
    return tool(request,'deck_template',deck_id=deck_id)


@router.post('/decks/{deck_id}/template')
async def apply(request: Request, deck_id: str):
    svc=services(request)
    if request.headers.get('content-type','').startswith('multipart/'):
        data,filename,_=await read_upload(request,svc.config.max_upload_bytes)
        if not filename.lower().endswith('.pptx'):raise CiceroError('Choose a .pptx template file.')
        return await run_in_threadpool(attach_template,svc,deck_id,data,filename)
    body=DeckTemplateArgs.model_validate({**await request.json(),'deck_id':deck_id})
    return tool(request,'deck_template',**body.model_dump(exclude_none=True))
