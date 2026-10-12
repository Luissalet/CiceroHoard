"""Content-led presentation archetypes and a fact-preserving design proposal grammar."""
from copy import deepcopy
from typing import Literal,Optional
from pydantic import BaseModel,Field
from .models import SlidePatch
from .errors import CiceroError

ARCHETYPES={
    'evidence_band':'Full-width evidence with a compact conclusion band',
    'visual_pair':'Two comparable visuals at equal scale with a shared takeaway',
    'process_detail':'Process scene with aligned context and measured outcomes',
    'metric_focus':'Primary outcome with subordinate evidence and qualification',
    'image_story':'Unframed image or scene with a separate factual caption column',
    'table_analysis':'Readable table beside an analytical takeaway',
    'sequence':'Chronological evidence followed by context',
    'editorial_flow':'Reading-order text with a separate supporting figure',
}
CHART_STYLES={'show_legend','show_values','highlight'}

def chart_semantics(kind,stacked=False):
    if stacked:return 'stacked_comparison' if kind in ('bar','bar_horizontal') else kind
    return 'category_comparison' if kind in ('bar','bar_horizontal','dot') else kind

class Placement(BaseModel):
    block_index:int=Field(...,ge=0)
    frame:list[float]=Field(...,min_length=4,max_length=4)
    font_size:Optional[int]=Field(None,ge=14,le=96)
    direction:Optional[Literal['right','down']]=None
    chart:Optional[str]=None
    show_legend:Optional[bool]=None
    show_values:Optional[bool]=None

class Proposal(BaseModel):
    label:str=Field('model composition',max_length=200)
    rationale:str=Field('',max_length=3000)
    placements:list[Placement]

def profile(slide):
    blocks=slide['blocks'];counts={}
    for b in blocks:counts[b['type']]=counts.get(b['type'],0)+1
    chars=sum(len(b.get('text',''))+sum(len(s) for s in b.get('items',[]) if isinstance(s,str)) for b in blocks)
    return {'types':counts,'text_characters':chars,'blocks':len(blocks),
            'table_cells':sum(len(b.get('rows',[]))*len(b.get('headers',[])) for b in blocks if b['type']=='table'),
            'data_points':sum(len(s['values']) for b in blocks if b['type']=='chart' for s in b.get('series',[])),
            'recommended':recommend(slide)}

def recommend(slide):
    types=[b['type'] for b in slide['blocks']]
    if sum(t in ('chart','image','scene3d','diagram') for t in types)>1:return ['visual_pair','evidence_band','editorial_flow']
    if 'table' in types:return ['table_analysis','evidence_band','editorial_flow']
    if 'diagram' in types:return ['process_detail','evidence_band','sequence']
    if 'timeline' in types:return ['sequence','evidence_band','process_detail']
    if 'image' in types or 'scene3d' in types:return ['image_story','evidence_band','editorial_flow']
    if 'metrics' in types:return ['metric_focus','evidence_band','editorial_flow']
    return ['editorial_flow','evidence_band','sequence']

def compose(slide,style):
    draft=deepcopy(slide);draft['layout']='freeform';blocks=draft['blocks']
    if not blocks:return draft
    primary=next((i for i,b in enumerate(blocks) if b['type'] in ('chart','diagram','image','scene3d','table','timeline')),0)
    metrics=next((i for i,b in enumerate(blocks) if b['type']=='metrics'),primary)
    main=metrics if style=='metric_focus' else primary
    others=[i for i in range(len(blocks)) if i!=main]
    visuals=[i for i,b in enumerate(blocks) if b['type'] in ('chart','image','scene3d','diagram')]
    for i,b in enumerate(blocks):
        if style=='visual_pair' and len(visuals)>=2:
            pair=visuals[:2];rest=[j for j in range(len(blocks)) if j not in pair]
            b['frame']=[pair.index(i)*.52,0,.48,.76 if rest else 1] if i in pair else [rest.index(i)/len(rest),.82,.94/len(rest),.18]
        elif style=='metric_focus':
            b['frame']=[0,0,1,.4] if i==main else [others.index(i)/len(others),.49,.94/len(others),.51]
        elif style in ('evidence_band','sequence'):
            b['frame']=[0,0,1,.7 if others else 1] if i==main else [others.index(i)/len(others),.78,.94/len(others),.22]
        elif style=='process_detail':
            b['frame']=[0,.24,1,.76] if i==main else [others.index(i)/len(others),0,.94/len(others),.18]
            if b['type']=='diagram':b['direction']='right'
        elif style in ('image_story','table_analysis'):
            fraction=.7 if style=='image_story' else .72
            b['frame']=[0,0,fraction,1] if i==main else [fraction+.04,others.index(i)/len(others),.96-fraction,.9/len(others)]
        else:
            if others:b['frame']=[.62,0,.38,1] if i==main else [0,others.index(i)/len(others),.56,.92/len(others)]
            else:b['frame']=[0,0,1,1]
        if b['type'] in ('text','quote','bullets'):
            text=b.get('text','') or ' '.join(s for s in b.get('items',[]) if isinstance(s,str))
            b['font_size']=24 if len(text)>350 else 28 if len(text)>150 else 32
        if b['type']=='chart' and b['chart'] in ('bar','bar_horizontal'):
            longest=max((len(s) for s in b.get('categories',[])),default=0)
            if longest>12 or len(b.get('categories',[]))>6:b['chart']='bar_horizontal'
    SlidePatch.model_validate({'layout':'freeform','blocks':blocks})
    return draft

def proposal_patch(source,proposal):
    blocks=deepcopy(source['blocks']);seen=set()
    for p in proposal.placements:
        if p.block_index>=len(blocks) or p.block_index in seen:
            raise CiceroError('Proposal indexes '+str([p.block_index for p in proposal.placements])+' must be distinct ZERO-BASED indexes in0..'+str(len(blocks)-1))
        seen.add(p.block_index);block=blocks[p.block_index];block['frame']=p.frame
        if p.font_size is not None:block['font_size']=p.font_size
        if p.direction is not None:
            if block['type']=='diagram':block['direction']=p.direction
        for key in ('chart','show_legend','show_values'):
            value=getattr(p,key)
            if value is not None:
                if block['type']=='chart':block[key]=value
    return SlidePatch.model_validate({'layout':'freeform','blocks':blocks})
