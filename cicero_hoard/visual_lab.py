"""Content-preserving compositions, real render evidence and an inspectable agent design loop."""
from copy import deepcopy
from pathlib import Path
from typing import Literal,Optional
import base64,json,math
from pydantic import BaseModel,Field
from . import decks
from .models import SlidePatch
from .errors import CiceroError,RevisionConflict,NotFound
from .hoard_link.ids import new_ulid
from .util import jdump,jload
from .layouts import build_plan
from .themes import theme_of

STYLES=('original','balanced','visual_left','visual_right','focus','comparison','editorial','stacked')
VISUALS={'image','chart','diagram','metrics','table','timeline','scene3d','poll'}

class LabArgs(BaseModel):
    deck_id:str
    action:Literal['variants','candidate','render','compare','apply','improve','critique','benchmark','history']='variants'
    slide_id:Optional[str]=None
    variant_id:Optional[str]=None
    variant_ids:Optional[list[str]]=Field(None,max_length=12)
    baseline_id:Optional[str]=None
    styles:list[Literal['original','balanced','visual_left','visual_right','focus','comparison','editorial','stacked']]=Field(default_factory=lambda:list(STYLES))
    expected_revision:Optional[int]=Field(None,ge=1)
    include_image:bool=False
    use_model:bool=False
    patch:Optional[SlidePatch]=None

def content_signature(slide):
    blocks=SlidePatch(blocks=deepcopy(slide['blocks'])).model_dump(exclude_none=True)['blocks']
    for block in blocks:
        for key in ('frame','font_size','build','effect','duration_ms'):block.pop(key,None)
    return jdump(blocks)

def composition(slide,style):
    draft=deepcopy(slide)
    if style=='original':return draft
    draft['layout']='freeform';blocks=draft['blocks'];count=len(blocks)
    if not count:return draft
    primary=next((i for i,b in enumerate(blocks) if b['type'] in VISUALS),0)
    rest=[i for i in range(count) if i!=primary]
    for i,b in enumerate(blocks):
        if style in ('visual_left','visual_right') and rest:
            left=0 if style=='visual_left' else .38
            frame=[left,0,.62,1] if i==primary else [0 if left else .67,rest.index(i)/len(rest),.33,.9/len(rest)]
        elif style=='focus' and rest:
            frame=[0,0,1,.69] if i==primary else [rest.index(i)/len(rest),.76,.94/len(rest),.24]
        elif style=='stacked':frame=[0,i/count,1,.92/count]
        elif style=='comparison':
            columns=min(count,3);rows=math.ceil(count/columns)
            frame=[(i%columns)/columns,(i//columns)/rows,.92/columns,.88/rows]
        elif style=='balanced' and rest:
            frame=[0,0,1,.58] if i==primary else [rest.index(i)/len(rest),.65,.94/len(rest),.35]
        elif style=='editorial' and rest:
            frame=[.37,0,.63,1] if i==primary else [0,rest.index(i)/len(rest),.31,.9/len(rest)]
        else:
            columns=2 if count>1 else 1;rows=math.ceil(count/columns)
            frame=[(i%columns)/columns,(i//columns)/rows,.94/columns,.92/rows]
        b['frame']=frame
        if b['type'] in ('text','bullets','quote'):b['font_size']=26 if count>2 else 32
    return draft

def _row(svc,args,variant_id):
    row=svc.db.one('SELECT * FROM visual_variants WHERE id=? AND deck_id=?',(variant_id,args.deck_id))
    if row is None:raise NotFound('Visual variant not found')
    return dict(row)

def _record(svc,deck,slide,style):
    candidate=composition(slide,style);vid=new_ulid()
    patch={'layout':candidate['layout'],'blocks':candidate['blocks']}
    svc.db.execute('INSERT INTO visual_variants(id,deck_id,slide_id,revision,label,patch,created_ts) VALUES(?,?,?,?,?,?,?)',
                   (vid,deck['id'],slide['id'],slide['revision'],style,jdump(patch),svc.clock()))
    return {'id':vid,'label':style,'slide_id':slide['id'],'expected_revision':slide['revision'],'patch':patch,
            'preview_url':svc.base_url()+f'/api/decks/{deck["id"]}/visual-lab/{vid}.html','content_changed':False}

def variant_deck(svc,args,vid):
    row=_row(svc,args,vid);deck=decks.deck_view(svc,args.deck_id)
    source=decks.get_slide(svc,args.deck_id,row['slide_id'])
    if source['revision']!=row['revision']:raise RevisionConflict('The source changed; generate fresh variants before comparing or applying.')
    deck['slides']=[{**source,**jload(row['patch'],{})}]
    return deck,row

def document(svc,deck):
    if deck.get('template'):
        from .template_live import document as template_document
        return template_document(svc,deck,inline=True)
    from .render import render_document
    return render_document(deck,assets=svc.assets_lookup(),inline=True)[0]

def render(svc,args,vid):
    from . import visual_review as vr
    deck,row=variant_deck(svc,args,vid)
    folder=svc.config.data_dir/'visual_lab'/vid
    scene=svc._review_scene(deck) if hasattr(svc,'_review_scene') else {}
    result=vr.review(deck,assets=svc.assets_lookup(),png_dir=folder,**scene)
    slide=deck['slides'][0];plan=build_plan(slide,deck_title=deck['title'],theme=theme_of(deck),number=1,total=1,assets=svc.assets_lookup())
    boxes=plan.boxes
    if deck.get('template'):
        from .template_live import scenes
        boxes=scenes(deck,svc.assets_lookup())[0][0]['boxes']
    text_sizes=[p.size for b in boxes if b.role!='footer' for p in b.paras]
    metrics={'errors':result['errors'],'warnings':result['warnings'],'objects':len(plan.boxes),
             'min_font_px':round(min(text_sizes),1) if text_sizes else None,
             'readability_penalty':sum(p<18 for p in text_sizes),'overflow_estimate':len(plan.overflow_where)}
    metrics['constraint_score']=max(0,100-30*metrics['errors']-8*metrics['warnings']-4*metrics['readability_penalty'])
    png=folder/'slide-01.png'
    svc.db.execute('UPDATE visual_variants SET metrics=?,png=? WHERE id=?',(jdump(metrics),str(png),vid))
    output={'id':vid,'label':row['label'],'metrics':metrics,'findings':result['slides'][0]['findings'],
            'png_url':svc.base_url()+f'/api/decks/{args.deck_id}/visual-lab/{vid}.png','png_path':str(png),
            'basis':'Measured fit and readability constraints, not an aesthetic grade or a superiority claim.'}
    if args.include_image:output['_image']={'mime':'image/png','data':base64.b64encode(png.read_bytes()).decode()}
    return output

def critique(svc,args,variant):
    if not args.use_model:return {'used_model':False,'criteria':['legibility','evidence visibility','hierarchy','spacing','template consistency'],
                                  'measured':variant,'instruction':'Inspect the PNG before judging visual quality; measured fit alone is insufficient.'}
    messages=[{'role':'system','content':'You review presentation design. Do not rewrite facts, values, labels or citations. Return JSON: strengths (list), issues (list), preferred_style (one of '+','.join(STYLES)+'), rationale (string). Judge the actual image, not a style stereotype.'},
              {'role':'user','content':jdump({'slide':decks.get_slide(svc,args.deck_id,args.slide_id or _row(svc,args,variant['id'])['slide_id']),
                                            'measurements':variant['metrics'],'findings':variant['findings']})}]
    try:
        reply=svc.link_sync.chat(messages,images=[Path(variant['png_path']).read_bytes()],capability='vision',max_tokens=1800,temperature=.2)
        from .generate import json_from_text
        return {'used_model':True,'model':getattr(reply,'model',None),'visual_input':True,'review':json_from_text(reply.text)}
    except Exception as error:
        raise CiceroError('The configured visual model could not review the image: '+str(error)[:250],code='visual_model_unavailable') from error

def run(svc,args):
    deck=decks.deck_view(svc,args.deck_id)
    if args.action=='candidate':
        if not args.slide_id or args.patch is None:raise CiceroError('Supply slide_id and a composition patch')
        source=decks.get_slide(svc,args.deck_id,args.slide_id)
        candidate={**source,**args.patch.model_dump(exclude_unset=True)}
        if any(candidate.get(k)!=source.get(k) for k in ('title','subtitle','notes','sources')) or content_signature(candidate)!=content_signature(source):
            raise CiceroError('A comparison candidate may change composition, not evidence or speaker notes')
        vid=new_ulid();patch={'layout':candidate['layout'],'blocks':candidate['blocks']}
        svc.db.execute('INSERT INTO visual_variants(id,deck_id,slide_id,revision,label,patch,created_ts) VALUES(?,?,?,?,?,?,?)',
                       (vid,args.deck_id,args.slide_id,source['revision'],'custom',jdump(patch),svc.clock()))
        return {'id':vid,'slide_id':args.slide_id,'expected_revision':source['revision'],'content_preserved':True}
    if args.action=='history':
        return {'variants':[{'id':r['id'],'slide_id':r['slide_id'],'label':r['label'],'revision':r['revision'],'metrics':jload(r['metrics'],{})}
                            for r in svc.db.query('SELECT * FROM visual_variants WHERE deck_id=? ORDER BY created_ts DESC',(args.deck_id,))]}
    if args.action in ('variants','improve'):
        if not args.slide_id:raise CiceroError('Choose slide_id')
        slide=decks.get_slide(svc,args.deck_id,args.slide_id)
        variants=[_record(svc,deck,slide,style) for style in dict.fromkeys(args.styles)]
        if args.action=='variants':return {'variants':variants,'expected_revision':slide['revision'],'content_preserved':True}
        args=LabArgs(**{**args.model_dump(),'action':'compare','variant_ids':[v['id'] for v in variants]})
    if args.action in ('compare','benchmark'):
        ids=args.variant_ids or []
        if not ids:raise CiceroError('Supply variant_ids')
        sources={(_row(svc,args,vid)['slide_id'],_row(svc,args,vid)['revision']) for vid in ids}
        if len(sources)!=1:raise CiceroError('Compare variants of the same slide and revision')
        if args.action=='benchmark' and args.baseline_id not in ids:raise CiceroError('Choose baseline_id from variant_ids')
        rows=[render(svc,args,vid) for vid in ids]
        rows.sort(key=lambda v:(-v['metrics']['constraint_score'],v['metrics']['errors'],v['metrics']['warnings']))
        output={'ranked':rows,'recommended_id':rows[0]['id'],'criteria':'Fit, measured defects and minimum type size; visual preference remains explicit.'}
        if args.include_image:
            output['_image']=rows[0].get('_image')
            for row in rows:row.pop('_image',None)
        if args.action=='benchmark':
            baseline=next(r for r in rows if r['id']==args.baseline_id)
            output['baseline_id']=baseline['id']
            output['paired']=[{'id':r['id'],'score_delta':r['metrics']['constraint_score']-baseline['metrics']['constraint_score'],
                              'errors_delta':r['metrics']['errors']-baseline['metrics']['errors'],
                              'warnings_delta':r['metrics']['warnings']-baseline['metrics']['warnings']} for r in rows]
            output['scope']='Paired content-preserving compositions with the same renderer. Baseline must be authored independently; inspect both images and report ties/regressions. No universal superiority claim.'
        return output
    if not args.variant_id:raise CiceroError('Supply variant_id')
    if args.action=='apply':
        deck,row=variant_deck(svc,args,args.variant_id)
        revision=args.expected_revision if args.expected_revision is not None else row['revision']
        return decks.patch_slide(svc,args.deck_id,row['slide_id'],{**jload(row['patch'],{}),'expected_revision':revision},reason='visual variant selected')
    measured=render(svc,args,args.variant_id)
    if args.action=='critique':
        picture=measured.pop('_image',None)
        result=critique(svc,args,measured)
        if picture:result['_image']=picture
        return result
    return measured

def capture(svc,args):
    if args.action!='apply':return {'noop':True}
    from . import agent_undo
    row=_row(svc,args,args.variant_id)
    return agent_undo.capture_slide(svc,LabArgs(deck_id=args.deck_id,slide_id=row['slide_id']))

def track(svc,args,result):
    if args.action!='apply':return {'objects':[],'etag':''}
    from . import agent_undo
    row=_row(svc,args,args.variant_id)
    return agent_undo.track_slide(svc,LabArgs(deck_id=args.deck_id,slide_id=row['slide_id']),result)
