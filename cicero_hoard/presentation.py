"""Local live presentation sessions. Audience state never contains speaker notes."""
from __future__ import annotations
import threading
import uuid
from typing import Literal,Optional
from pydantic import BaseModel,Field
from . import decks as store
from .errors import CiceroError,RevisionConflict
from .layouts import build_plan
from .themes import theme_of

class StartArgs(BaseModel):
    deck_id:str
    target_seconds:int=Field(900,ge=30,le=14400)
    main_slide_count:Optional[int]=Field(None,ge=1,le=40)
    restart:bool=False

class StateArgs(BaseModel):
    deck_id:str

class ControlArgs(BaseModel):
    deck_id:str
    action:Literal['next','previous','goto','sync','pause','resume','reset','blackout','target','main']
    slide_index:Optional[int]=Field(None,ge=0,le=39)
    fragment_index:Optional[int]=Field(None,ge=-1,le=39)
    blackout:Optional[bool]=None
    target_seconds:Optional[int]=Field(None,ge=30,le=14400)
    main_slide_count:Optional[int]=Field(None,ge=1,le=40)
    expected_version:Optional[int]=Field(None,ge=1)

class Sessions:
    def __init__(self,clock):
        self.clock=clock
        self.lock=threading.RLock()
        self.rooms={}

    def require(self,deck_id):
        if deck_id not in self.rooms:raise CiceroError('Start a live presentation session first.')
        return self.rooms[deck_id]

    def public(self,room):
        elapsed=room['elapsed']+(max(0,self.clock()-room['resumed']) if room['running'] else 0)
        return {k:room[k] for k in ('session_id','deck_id','version','slide_index','fragment_index','blackout','running','target_seconds','main_slide_count','slides')}|{
            'elapsed_seconds':round(elapsed,2),'remaining_seconds':round(room['target_seconds']-elapsed,2)}

def start(svc,args):
    deck=store.deck_view(svc,args.deck_id)
    if not deck['slides']:raise CiceroError('Add slides before starting a presentation.')
    if args.main_slide_count and args.main_slide_count>len(deck['slides']):raise CiceroError('The main talk cannot exceed the slide count.')
    sessions=svc.presentations
    with sessions.lock:
        if args.restart or args.deck_id not in sessions.rooms:
            slides=[]
            for i,slide in enumerate(deck['slides']):
                plan=build_plan(slide,deck_title=deck['title'],theme=theme_of(deck),number=i+1,total=len(deck['slides']),lang=deck['language'],assets=svc.assets_lookup())
                groups={b.build for b in plan.boxes if b.build and b.effect!='none'}
                slides.append({'id':slide['id'],'title':slide['title'],'revision':slide['revision'],'steps':len(groups)})
            sessions.rooms[args.deck_id]={'session_id':uuid.uuid4().hex,'deck_id':args.deck_id,'version':1,'slide_index':0,'fragment_index':-1,
                'blackout':False,'running':False,'elapsed':0,'resumed':sessions.clock(),'target_seconds':args.target_seconds,
                'main_slide_count':args.main_slide_count or len(slides),'slides':slides}
        room=sessions.rooms[args.deck_id]
        return sessions.public(room)|{
            'presenter_url':svc.base_url()+f"/#/presenter/{args.deck_id}",
            'audience_url':svc.base_url()+f"/api/decks/{args.deck_id}/live/{room['session_id']}/audience.html",
            'persistence':'local memory until server restart; restart=true adopts deck edits'}

def state(svc,args):
    with svc.presentations.lock:
        room=svc.presentations.require(args.deck_id)
        return validate_room(svc,args.deck_id,room['session_id'])

def control(svc,args):
    sessions=svc.presentations
    with sessions.lock:
        room=sessions.require(args.deck_id)
        validate_room(svc,args.deck_id,room['session_id'])
        if args.expected_version is not None and args.expected_version!=room['version']:raise RevisionConflict('Presentation state changed. Read the current version.')
        if args.action=='sync' and args.slide_index==room['slide_index'] and args.fragment_index==room['fragment_index']:
            return sessions.public(room)
        slide=room['slide_index'];fragment=room['fragment_index'];steps=room['slides'][slide]['steps']
        if args.action=='next':
            if fragment<steps-1:fragment+=1
            elif slide<len(room['slides'])-1:slide+=1;fragment=-1
        elif args.action=='previous':
            if fragment>=0:fragment-=1
            elif slide>0:slide-=1;fragment=room['slides'][slide]['steps']-1
        elif args.action in ('goto','sync'):
            if args.slide_index is None or args.slide_index>=len(room['slides']):raise CiceroError('Choose an existing zero-based slide index.')
            slide=args.slide_index;fragment=args.fragment_index if args.fragment_index is not None else -1
            if fragment>=room['slides'][slide]['steps']:raise CiceroError('The fragment index exceeds the stages on this slide.')
        elif args.action=='blackout':room['blackout']=args.blackout if args.blackout is not None else not room['blackout']
        elif args.action in ('pause','resume','reset'):
            if room['running']:room['elapsed']+=max(0,sessions.clock()-room['resumed'])
            room['running']=args.action=='resume';room['resumed']=sessions.clock()
            if args.action=='reset':room['elapsed']=0
        elif args.action=='target':
            if args.target_seconds is None:raise CiceroError('Supply target_seconds.')
            room['target_seconds']=args.target_seconds
        elif args.action=='main':
            if args.main_slide_count is None or args.main_slide_count>len(room['slides']):raise CiceroError('Supply an existing main slide count.')
            room['main_slide_count']=args.main_slide_count
        room.update(slide_index=slide,fragment_index=fragment,version=room['version']+1)
        return sessions.public(room)

def validate_room(svc,deck_id,session_id):
    with svc.presentations.lock:
        room=svc.presentations.require(deck_id)
        if room['session_id']!=session_id:raise CiceroError('This presentation session was replaced. Open its current audience URL.')
        store._deck_row(svc,deck_id)
        current=svc.db.query('SELECT id,revision FROM slides WHERE deck_id=? ORDER BY position',(deck_id,))
        if [(s['id'],s['revision']) for s in current]!=[(s['id'],s['revision']) for s in room['slides']]:
            raise RevisionConflict('Slides changed during this session. Restart the session to adopt them.')
        return sessions_copy(svc,deck_id)

def sessions_copy(svc,deck_id):
    return svc.presentations.public(svc.presentations.require(deck_id))

def audience_document(svc,deck_id,session_id):
    validate_room(svc,deck_id,session_id)
    document=svc.preview_html(deck_id,mode='present')
    base=f'/api/decks/{deck_id}/live/{session_id}'
    runtime='''<script>
    (()=>{
      const base=BASE;let version=0,applying=false,blackout=false,working=false,authoritative=null;
      const status=document.createElement('div');status.setAttribute('role','alert');
      status.style.cssText='position:fixed;top:0;left:0;right:0;z-index:110;background:#a22;color:white;padding:12px;font:16px Arial;display:none';document.body.append(status);
      async function poll(){
        if(working)return;
        try{const response=await fetch(base+'/state');if(!response.ok)throw new Error((await response.json()).error||'Presentation unavailable');
          const state=await response.json();status.style.display='none';
          authoritative=state;
          if(state.version!==version){applying=true;version=state.version;blackout=state.blackout;
            deck.slide(state.slide_index,0,state.fragment_index);document.body.classList.toggle('blackout',blackout);
            requestAnimationFrame(()=>{applying=false});}
        }catch(error){status.textContent=error.message;status.style.display='block';}
      }
      async function send(payload){if(applying||working)return;working=true;
        try{const response=await fetch(base+'/control',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
          if(!response.ok&&response.status!==409)throw new Error((await response.json()).error||'Navigation unavailable');}
        catch(error){status.textContent=error.message;status.style.display='block';}
        finally{working=false;await poll();}}
      // Only user intents write shared state. Renderer events can fire during
      // initialization or transitions and must never overwrite a live session.
      deck.configure({keyboard:false});
      document.addEventListener('click',event=>{
        const button=event.target.closest('.controls button');
        if(button){event.preventDefault();event.stopImmediatePropagation();
          send({action:button.classList.contains('navigate-left')||button.classList.contains('navigate-up')?'previous':'next'});}
        else if(deck.isOverview()){
          const slide=event.target.closest('.slide');
          if(slide){event.preventDefault();event.stopImmediatePropagation();deck.toggleOverview(false);send({action:'goto',slide_index:Number(slide.dataset.index)});}
        }
      },true);
      document.addEventListener('keydown',event=>{
        if(event.altKey||event.ctrlKey||event.metaKey||/INPUT|TEXTAREA|SELECT|BUTTON/.test(event.target.tagName))return;
        const key=event.key.toLowerCase();let payload;
        if(['arrowright','arrowdown','pagedown',' ','enter','n'].includes(key))payload={action:'next'};
        else if(['arrowleft','arrowup','pageup','backspace','p'].includes(key))payload={action:'previous'};
        else if(key==='home')payload={action:'goto',slide_index:0};
        else if(key==='end'&&authoritative)payload={action:'goto',slide_index:authoritative.slides.length-1};
        else if(key==='b'||key==='.')payload={action:'blackout'};
        else if(key==='o'){deck.toggleOverview();event.preventDefault();}
        else if(key==='f'){event.preventDefault();(document.fullscreenElement?document.exitFullscreen():document.documentElement.requestFullscreen()).catch(()=>{});}
        else if(key==='escape'){deck.toggleOverview(false);if(document.fullscreenElement)document.exitFullscreen();}
        if(payload){event.preventDefault();send(payload);}
      });
      document.querySelectorAll('.elapsed,.hud').forEach(el=>el.remove());
      deck.on('ready',poll);setInterval(poll,500);
    })();
    </script>'''.replace('BASE',repr(base))
    return document.replace('</body>',runtime+'</body>')
