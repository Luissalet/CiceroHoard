"""Native model-driven render/correct loops with image-bound external review."""
from copy import deepcopy
from pathlib import Path
import base64,threading
from typing import Literal,Optional,Any
from pydantic import BaseModel,Field
from . import decks,visual_lab as lab,compositions,agent_undo
from .errors import CiceroError,NotFound,RevisionConflict
from .models import SlidePatch
from .generate import json_from_text
from .hoard_link.ids import new_ulid
from .util import jdump,jload,sha256_hex

class DesignArgs(BaseModel):
    deck_id:str
    action:Literal['run','start','step','review','feedback','status','list','apply','cancel']='run'
    slide_id:Optional[str]=None
    slide_ids:Optional[list[str]]=None
    run_id:Optional[str]=None
    critic:Literal['structured','vision','external']='structured'
    rounds:int=Field(3,ge=1)
    proposals:int=Field(2,ge=1)
    auto_apply:bool=True
    include_image:bool=False
    variant_id:Optional[str]=None
    png_sha256:Optional[str]=None
    feedback:Optional[dict[str,Any]]=None

def _lock(svc):
    if not hasattr(svc,'design_lock'):svc.design_lock=threading.RLock()
    return svc.design_lock

def _save(svc,state):
    with _lock(svc):
        row=svc.db.one('SELECT state FROM design_runs WHERE id=?',(state['id'],))
        if row and jload(row['state'],{}).get('cancel_requested'):
            state['cancel_requested']=True;state['status']='cancelled'
        svc.db.execute('UPDATE design_runs SET state=?,updated_ts=? WHERE id=?',(jdump(state),svc.clock(),state['id']))

def _get(svc,args):
    row=svc.db.one('SELECT state FROM design_runs WHERE id=? AND deck_id=?',(args.run_id,args.deck_id))
    if row is None:raise NotFound('Design run not found')
    return jload(row['state'],{})

def _start(svc,args):
    deck=decks.deck_view(svc,args.deck_id)
    ids=args.slide_ids or ([args.slide_id] if args.slide_id else [s['id'] for s in deck['slides']])
    slides=[decks.get_slide(svc,args.deck_id,sid) for sid in dict.fromkeys(ids)]
    if not slides:raise CiceroError('Choose at least one slide')
    state={'id':new_ulid(),'deck_id':args.deck_id,'status':'ready','index':0,'options':args.model_dump(exclude={'run_id','feedback','png_sha256','variant_id'}),
           'slides':[{'slide_id':s['id'],'revision':s['revision'],'source':s,'context_hash':lab.context_signature(svc,deck,s),'round':0,'candidates':[],'reviews':[],'model_calls':[],'applied':False} for s in slides],
           'created_ts':svc.clock(),'cancel_requested':False}
    svc.db.execute('INSERT INTO design_runs(id,deck_id,state,created_ts,updated_ts) VALUES(?,?,?,?,?)',
                   (state['id'],args.deck_id,jdump(state),svc.clock(),svc.clock()))
    return state

def _rank(rows):
    # Equal measured fit is not equal visual quality: keep the latest correction.
    return sorted(reversed(rows),key=lambda r:(r['metrics']['errors']+r['metrics'].get('legibility_errors',0),r['metrics']['warnings'],r['metrics']['readability_penalty'],-r['metrics']['constraint_score']))

def _check_context(svc,state,item,source=None):
    if not item.get('context_hash'):raise CiceroError('Start a fresh design run: this older run has no pinned rendering context',code='design_evidence_unpinned')
    if lab.context_signature(svc,decks.deck_view(svc,state['deck_id']),source or item['source'])!=item['context_hash']:
        raise RevisionConflict('The rendering context changed after the image review')

def _model_candidates(svc,state,item):
    source=item['source'];best=item.get('best');options=state['options']
    instruction={'source_slide':source,'profile':compositions.profile(source),'archetypes':compositions.ARCHETYPES,
                 'current_best':{k:v for k,v in (best or {}).items() if k not in ('_image',)},'reviews':item['reviews'],
                 'requested_candidates':options['proposals'],'response_schema':{'candidates':[compositions.Proposal.model_json_schema()]}}
    messages=[{'role':'system','content':'Design presentation compositions, not content. Return JSON {candidates:[{label,rationale,placements:[{block_index,frame:[x,y,w,h],font_size,chart,direction,show_legend,show_values}]}]}. Frames are fractions inside the body, must fit0..1; do not overlap. Preserve ALL values, labels, notes, sources and actions; never shorten/remove evidence. Match narrative and visual form to data. Prefer readable 24-34px body type. Use the actual render findings and prior critique to correct. Chart may use a supported alternative representation with the SAME categories/series data. Do not claim to have seen pixels when only supplied measurements.'},
              {'role':'user','content':jdump(instruction)}]
    for attempt in range(2):
        try:
            if _get(svc,DesignArgs(deck_id=state['deck_id'],run_id=state['id'],action='status'))['cancel_requested']:
                raise CiceroError('Design run cancelled',code='design_cancelled')
            images=[Path(best['png_path']).read_bytes()] if options['critic']=='vision' and best else None
            reply=svc.link_sync.chat(messages,images=images,capability='llm',max_tokens=5000,temperature=.35,effort='high')
            parsed=json_from_text(reply.text);proposals=[compositions.Proposal.model_validate(p) for p in parsed['candidates']]
            if not proposals:raise ValueError('No candidates returned')
            patches=[compositions.proposal_patch(source,p) for p in proposals]
            item['model_calls'].append({'model':getattr(reply,'model',None),'provider':getattr(reply,'provider',None),
                'elapsed_ms':getattr(reply,'elapsed_ms',None),'visual_input':bool(images),'round':item['round'],'output':parsed})
            return [(p,patch) for p,patch in zip(proposals,patches)]
        except Exception as error:
            if getattr(error,'code',None)=='design_cancelled':raise
            if attempt==0:messages.append({'role':'user','content':'Repair the JSON/geometry without changing evidence: '+str(error)[:800]})
            else:raise CiceroError('The configured global model could not produce valid compositions: '+str(error)[:400],code='design_model_failed') from error

def _picture(result,include):
    if include and result.get('best'):
        path=Path(result['best']['png_path'])
        data=path.read_bytes()
        if sha256_hex(data)!=result['best']['png_sha256']:raise RevisionConflict('The rendered evidence changed; render a fresh candidate')
        result['_image']={'mime':'image/png','data':base64.b64encode(data).decode()}
    return result

def view(state,include_image=False):
    current=state['slides'][min(state['index'],len(state['slides'])-1)]
    return _picture({'run_id':state['id'],'deck_id':state['deck_id'],'status':state['status'],'index':state['index'],
        'slides_total':len(state['slides']),'slide_id':current['slide_id'],'source_revision':current['revision'],
        'round':current['round'],'best':current.get('best'),'error':state.get('error'),
        'slides':[{'slide_id':s['slide_id'],'round':s['round'],'applied':s['applied'],'best':s.get('best'),
                   'candidates':s['candidates'],'reviews':s['reviews'],'model_calls':s['model_calls'],
                   'applied_render':s.get('applied_render')} for s in state['slides']],
        'review_request':current.get('review_request'),'evaluation_mode':state['options']['critic'],
        'source_preserved':True,'mutations':state.get('_call_mutations',[])},include_image)

def _apply(svc,state,item):
    if item['applied']:return
    if not item.get('best'):raise CiceroError('Render a candidate before applying')
    source=decks.get_slide(svc,state['deck_id'],item['slide_id'])
    row=lab._row(svc,lab.LabArgs(deck_id=state['deck_id']),item['best']['id'])
    if sha256_hex(Path(item['best']['png_path']).read_bytes())!=item['best']['png_sha256']:
        raise RevisionConflict('The selected image evidence changed before apply')
    patch=jload(row['patch'],{})
    normalized=SlidePatch.model_validate(patch).model_dump(exclude_unset=True)
    if source['revision']!=item['revision']:
        # Recover a successful apply whose durable run update was interrupted.
        actual=SlidePatch.model_validate({k:source[k] for k in normalized}).model_dump(exclude_unset=True)
        if source['revision']==item['revision']+1 and actual==normalized:
            item['applied']=True;item['applied_revision']=source['revision'];return
        raise RevisionConflict('The slide changed during design; preserve the later edit and start from its revision')
    with _lock(svc):
        if _get(svc,DesignArgs(deck_id=state['deck_id'],run_id=state['id'],action='status'))['cancel_requested']:
            raise CiceroError('Design run cancelled before apply',code='design_cancelled')
        _check_context(svc,state,item)
        updated=lab.run(svc,lab.LabArgs(deck_id=state['deck_id'],action='apply',variant_id=item['best']['id'],expected_revision=item['revision']))
        item['applied']=True;item['applied_revision']=updated['revision']
        state.setdefault('_call_mutations',[]).append({'slide_id':item['slide_id'],'etag':decks.slide_etag(updated)})
        _save(svc,state)
    # Compare the applied rendering to the selected evidence, on the fresh revision.
    fresh=lab.run(svc,lab.LabArgs(deck_id=state['deck_id'],slide_id=item['slide_id'],action='candidate',patch=patch))
    item['applied_render']=lab.render(svc,lab.LabArgs(deck_id=state['deck_id']),fresh['id'])
    item['applied_render']['same_png_as_selected']=item['applied_render']['png_sha256']==item['best']['png_sha256']

def _advance(svc,state):
    item=state['slides'][state['index']]
    if state['cancel_requested']:state['status']='cancelled';_save(svc,state);return
    if item['applied']:
        state['index']+=1;state['status']='complete' if state['index']==len(state['slides']) else 'ready';_save(svc,state);return
    source=decks.get_slide(svc,state['deck_id'],item['slide_id'])
    if source['revision']!=item['revision'] and not item['applied']:raise RevisionConflict('The source slide changed during the design run')
    _check_context(svc,state,item,source)
    if not item['candidates']:
        styles=['original',*compositions.recommend(item['source'])]
        seeded=lab.run(svc,lab.LabArgs(deck_id=state['deck_id'],slide_id=item['slide_id'],styles=styles))['variants']
        for v in seeded:item['candidates'].append(lab.render(svc,lab.LabArgs(deck_id=state['deck_id']),v['id']))
        item['best']=_rank(item['candidates'])[0];_save(svc,state)
    item['round']+=1
    prior=item['best']['metrics']['constraint_score']
    proposals=_model_candidates(svc,state,item)
    for proposal,patch in proposals:
        if _get(svc,DesignArgs(deck_id=state['deck_id'],run_id=state['id'],action='status'))['cancel_requested']:
            state['cancel_requested']=True;state['status']='cancelled';_save(svc,state);return
        v=lab.run(svc,lab.LabArgs(deck_id=state['deck_id'],slide_id=item['slide_id'],action='candidate',patch=patch))
        row=lab.render(svc,lab.LabArgs(deck_id=state['deck_id']),v['id']);row['rationale']=proposal.rationale;row['label']=proposal.label
        item['candidates'].append(row)
    item['best']=_rank(item['candidates'])[0]
    mode=state['options']['critic']
    if mode=='vision':
        reviewed=lab.critique(svc,lab.LabArgs(deck_id=state['deck_id'],variant_id=item['best']['id'],use_model=True),item['best'])
        item['reviews'].append({'variant_id':item['best']['id'],'png_sha256':item['best']['png_sha256'],**reviewed})
    if _get(svc,DesignArgs(deck_id=state['deck_id'],run_id=state['id'],action='status'))['cancel_requested']:
        state['cancel_requested']=True;state['status']='cancelled';_save(svc,state);return
    if mode=='external':
        item['review_request']={'run_id':state['id'],'slide_id':item['slide_id'],'source_revision':item['revision'],
                               'variant_id':item['best']['id'],'png_sha256':item['best']['png_sha256'],
                               'criteria':['legibility','hierarchy','evidence visibility','narrative clarity','composition']}
        state['status']='awaiting_feedback';_save(svc,state);return
    if item['round']>=state['options']['rounds'] or (item['round']>1 and item['best']['metrics']['constraint_score']<=prior):
        if state['options']['auto_apply']:_apply(svc,state,item)
        state['index']+=1
        state['status']='complete' if state['index']==len(state['slides']) else 'ready'
    else:state['status']='ready'
    _save(svc,state)

def _run(svc,args):
    decks._deck_row(svc,args.deck_id)
    if args.action=='list':return {'runs':[jload(r['state'],{}) for r in svc.db.query('SELECT state FROM design_runs WHERE deck_id=? ORDER BY created_ts DESC',(args.deck_id,))]}
    state=_start(svc,args) if args.action=='start' or (args.action=='run' and not args.run_id) else _get(svc,args)
    if args.action in ('status','start'):return view(state,args.include_image)
    state['_call_mutations']=[]
    if args.action=='cancel':
        with _lock(svc):
            state=_get(svc,args);state['_call_mutations']=[];state['cancel_requested']=True;state['status']='cancelled';_save(svc,state)
        return view(state)
    if state['status']=='cancelled':return view(state,args.include_image)
    if state['status']=='complete' and args.action!='apply':return view(state,args.include_image)
    if args.action=='apply':
        targets=([state['slides'][state['index']]] if state['index']<len(state['slides']) else state['slides'])
        if args.slide_id:targets=[s for s in state['slides'] if s['slide_id']==args.slide_id]
        if not targets:raise CiceroError('Choose a slide in this design run')
        try:
            for target in targets:
                if not target['applied']:_apply(svc,state,target)
            if state['index']<len(state['slides']):state['index']+=1
            state['status']='complete' if state['index']==len(state['slides']) else 'ready';_save(svc,state)
        except Exception as error:
            state['status']='failed';state['error']={'message':str(error),'code':getattr(error,'code','design_failed')};_save(svc,state)
        return view(state,args.include_image)
    item=state['slides'][state['index']]
    if args.action=='review':
        if state['options']['critic']!='external':raise CiceroError('Candidate image reviews require critic=external')
        chosen=next((c for c in item['candidates'] if c['id']==args.variant_id),None)
        if chosen is None:raise CiceroError('Choose a rendered candidate from this run')
        if decks.get_slide(svc,args.deck_id,item['slide_id'])['revision']!=item['revision']:raise RevisionConflict('The source revision changed')
        item['best']=chosen
        item['review_request']={'run_id':state['id'],'slide_id':item['slide_id'],'source_revision':item['revision'],
            'variant_id':chosen['id'],'png_sha256':chosen['png_sha256'],
            'criteria':['legibility','hierarchy','evidence visibility','narrative clarity','composition']}
        state['status']='awaiting_feedback';_save(svc,state);return view(state,args.include_image)
    if args.action=='feedback':
        requested=item.get('review_request')
        if state['status']!='awaiting_feedback' or not requested:raise CiceroError('This run is not awaiting an image review')
        if args.variant_id!=requested['variant_id'] or args.png_sha256!=requested['png_sha256']:raise RevisionConflict('Feedback must identify the exact rendered variant and PNG hash')
        if sha256_hex(Path(item['best']['png_path']).read_bytes())!=requested['png_sha256']:
            raise RevisionConflict('The requested PNG changed after the image review')
        current=decks.get_slide(svc,args.deck_id,item['slide_id'])
        if current['revision']!=item['revision']:raise RevisionConflict('Feedback is stale: the source revision changed')
        _check_context(svc,state,item,current)
        if args.feedback is None:raise CiceroError('Supply the image review feedback')
        selected=args.feedback.get('preferred_variant_id')
        if selected and selected!=requested['variant_id']:
            raise CiceroError('Review the requested PNG before selecting it; another candidate requires its own image-bound review')
        item['reviews'].append({**requested,'visual_input':True,'reviewer':'external MCP caller','feedback':args.feedback})
        item.pop('review_request',None)
        if args.feedback.get('accept') or item['round']>=state['options']['rounds']:
            if state['options']['auto_apply']:_apply(svc,state,item)
            state['index']+=1;state['status']='complete' if state['index']==len(state['slides']) else 'ready'
        else:state['status']='ready'
        _save(svc,state);return view(state,args.include_image)
    if state['status']=='awaiting_feedback':return view(state,args.include_image)
    try:
        state['status']='running';state.pop('error',None);_save(svc,state)
        _advance(svc,state)
        if args.action=='run':
            while state['status']=='ready':_advance(svc,state)
    except Exception as error:
        cancelled=_get(svc,DesignArgs(deck_id=state['deck_id'],run_id=state['id'],action='status'))['cancel_requested']
        state['status']='cancelled' if cancelled else 'failed'
        if not cancelled:state['error']={'message':str(error),'code':getattr(error,'code','design_failed')}
        _save(svc,state)
    return view(state,args.include_image)


def run(svc,args):
    if args.action in ('status','list','cancel'):return _run(svc,args)
    # Status and cancellation stay available while one worker calls the model.
    with _lock(svc):
        if args.action=='run' and not args.run_id:
            started=_start(svc,args);args=args.model_copy(update={'run_id':started['id']})
        key=args.run_id or 'start:'+args.deck_id
        active=getattr(svc,'design_active',set())
        svc.design_active=active
        if key in active:raise CiceroError('A worker is already advancing this design run',code='design_running')
        active.add(key)
    try:
        result=_run(svc,args)
        result['changed_slides']=list(dict.fromkeys(m['slide_id'] for m in result.get('mutations',[])))
        return result
    finally:
        with _lock(svc):active.discard(key)


def capture(svc,args):
    if args.action in ('status','list','cancel','start'):return {'noop':True}
    return {'deck_id':args.deck_id,'slides':decks.deck_view(svc,args.deck_id)['slides']}

def track(svc,args,result):
    mutations=[] if args.action in ('status','list','cancel','start','review') else result.get('mutations',[])
    ids=list(dict.fromkeys(m['slide_id'] for m in mutations))
    return {'objects':[f'deck:{args.deck_id}/slides/{sid}' for sid in ids],
            'ids':[f'deck_id={args.deck_id}'],
            'etag':jdump({m['slide_id']:m['etag'] for m in mutations})}

def undo(svc,record,dry_run=False):
    before=record.get('before',{});deck_id=before.get('deck_id');etag=record.get('etag') or '{}'
    etags=etag if isinstance(etag,dict) else jload(etag,None)
    if not isinstance(etags,dict):raise agent_undo._conflict('The design mutation receipt cannot be reconstructed')
    snapshot={s['id']:s for s in before.get('slides',[])}
    with svc.db.transaction():
        for sid,etag in etags.items():
            if sid not in snapshot or decks.slide_etag(decks.get_slide(svc,deck_id,sid))!=etag:
                raise agent_undo._conflict('A designed slide was edited afterwards; preserve that later edit')
        if not dry_run:
            for sid in etags:decks.restore_slide(svc,deck_id,sid,snapshot[sid],reason='undo design run')
    return {'would_restore' if dry_run else 'restored':list(etags)}
