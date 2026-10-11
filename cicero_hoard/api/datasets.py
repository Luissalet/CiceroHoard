"""Tabular sources: immutable import, inspection, transformation and visual mapping."""
from fastapi import APIRouter,Request
from fastapi.concurrency import run_in_threadpool
from .. import datasets
from .deps import services,tool
from .sources import read_upload

router=APIRouter(prefix='/api')

@router.post('/decks/{deck_id}/datasets',status_code=201)
async def import_dataset(request:Request,deck_id:str):
    svc=services(request)
    if request.headers.get('content-type','').startswith('multipart/'):
        data,filename,fields=await read_upload(request,svc.config.max_upload_bytes)
        args=datasets.ImportArgs.model_validate({**fields,'deck_id':deck_id})
        return await run_in_threadpool(datasets.import_data,svc,args,data,filename)
    return tool(request,'dataset_import',**{**await request.json(),'deck_id':deck_id})

@router.get('/decks/{deck_id}/datasets/{source_id}')
def get_dataset(request:Request,deck_id:str,source_id:int,offset:int=0,limit:int=20):
    return tool(request,'dataset_get',deck_id=deck_id,source_id=source_id,offset=offset,limit=limit)

@router.post('/decks/{deck_id}/datasets/{source_id}/transform')
async def transform_dataset(request:Request,deck_id:str,source_id:int):
    return tool(request,'dataset_transform',**{**await request.json(),'deck_id':deck_id,'source_id':source_id})

@router.post('/decks/{deck_id}/datasets/{source_id}/visual')
async def map_dataset(request:Request,deck_id:str,source_id:int):
    return tool(request,'dataset_visual',**{**await request.json(),'deck_id':deck_id,'source_id':source_id})
