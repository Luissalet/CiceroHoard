"""Advanced authoring and evidence tools share the native agent implementations."""
from pathlib import Path
from fastapi import APIRouter,Request,WebSocket,WebSocketDisconnect,UploadFile,File
from fastapi.responses import HTMLResponse,FileResponse
from fastapi.concurrency import run_in_threadpool
from .deps import services,tool
from .. import visual_lab,advanced,scene3d,benchmark
from ..errors import CiceroError,NotFound
from pydantic import ValidationError
from ..render import present_document

router=APIRouter(prefix='/api')

@router.post('/decks/{deck_id}/benchmarks')
async def evaluate(request:Request,deck_id:str):
    return await run_in_threadpool(tool,request,'deck_benchmark',**{**await request.json(),'deck_id':deck_id})

@router.get('/decks/{deck_id}/benchmarks/{benchmark_id}/{token}.png')
def blind_png(request:Request,deck_id:str,benchmark_id:str,token:str):
    state=benchmark._get(services(request),benchmark.BenchmarkArgs(deck_id=deck_id,benchmark_id=benchmark_id))
    pair=next((p for c in state['cases'] for p in c.get('blind_pairs',[]) if p['token']==token),None)
    if pair is None:raise NotFound('Blind evidence not found')
    return FileResponse(pair['path'],media_type='image/png')

@router.post('/decks/{deck_id}/models')
async def model_import(request:Request,deck_id:str):
    return await run_in_threadpool(tool,request,'scene_model_import',**{**await request.json(),'deck_id':deck_id})

@router.post('/decks/{deck_id}/models/upload')
async def model_upload(request:Request,deck_id:str,file:UploadFile=File(...)):
    return await run_in_threadpool(scene3d.import_bytes,services(request),deck_id,await file.read(),file.filename or 'model.glb')

@router.post('/decks/{deck_id}/design')
async def design(request:Request,deck_id:str):
    return await run_in_threadpool(tool,request,'deck_design',**{**await request.json(),'deck_id':deck_id})

@router.post('/decks/{deck_id}/visual-lab')
async def lab(request:Request,deck_id:str):
    return await run_in_threadpool(tool,request,'deck_visual_lab',**{**await request.json(),'deck_id':deck_id})

@router.get('/decks/{deck_id}/visual-lab/{variant_id}.html',response_class=HTMLResponse)
def preview(request:Request,deck_id:str,variant_id:str):
    svc=services(request);deck,_=visual_lab.variant_deck(svc,visual_lab.LabArgs(deck_id=deck_id),variant_id)
    return visual_lab.document(svc,deck)

@router.get('/decks/{deck_id}/visual-lab/{variant_id}.png')
def png(request:Request,deck_id:str,variant_id:str):
    row=visual_lab._row(services(request),visual_lab.LabArgs(deck_id=deck_id),variant_id)
    if not row['png'] or not Path(row['png']).is_file():raise NotFound('Render the variant first')
    return FileResponse(row['png'],media_type='image/png')

@router.post('/decks/{deck_id}/polls')
async def polls(request:Request,deck_id:str):
    return tool(request,'deck_poll',**{**await request.json(),'deck_id':deck_id})

@router.get('/decks/{deck_id}/polls/{poll_id}')
def poll_state(request:Request,deck_id:str,poll_id:str):
    return advanced.poll_state(services(request),deck_id,poll_id)

@router.post('/decks/{deck_id}/polls/{poll_id}/vote')
async def vote(request:Request,deck_id:str,poll_id:str):
    return tool(request,'deck_poll',**{**await request.json(),'deck_id':deck_id,'poll_id':poll_id,'action':'vote'})

@router.post('/decks/{deck_id}/connectors')
async def connector(request:Request,deck_id:str):
    return await run_in_threadpool(tool,request,'dataset_connect',**{**await request.json(),'deck_id':deck_id})

@router.post('/decks/{deck_id}/slides/{slide_id}/collaboration')
async def collaboration(request:Request,deck_id:str,slide_id:str):
    return await run_in_threadpool(tool,request,'slide_collaborate',**{**await request.json(),'deck_id':deck_id,'slide_id':slide_id})

@router.websocket('/decks/{deck_id}/slides/{slide_id}/collaboration')
async def collaborative_socket(socket:WebSocket,deck_id:str,slide_id:str):
    await socket.accept();svc=socket.app.state.services
    peers=getattr(svc,'collaboration_peers',{})
    svc.collaboration_peers=peers;room=peers.setdefault(slide_id,set());room.add(socket)
    try:
        initial=await run_in_threadpool(advanced.collaboration,svc,advanced.CollaborationArgs(deck_id=deck_id,slide_id=slide_id))
        await socket.send_json(initial)
        while True:
            body=await socket.receive_json()
            try:
                args=advanced.CollaborationArgs(**{**body,'deck_id':deck_id,'slide_id':slide_id})
                result=await run_in_threadpool(advanced.collaboration,svc,args)
            except (CiceroError,ValidationError) as error:
                await socket.send_json({'error':str(error)});continue
            for peer in list(room):
                try:await peer.send_json(result)
                except Exception:room.discard(peer)
    except WebSocketDisconnect:pass
    finally:room.discard(socket)
