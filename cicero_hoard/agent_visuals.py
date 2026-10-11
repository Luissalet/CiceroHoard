"""Agent-facing discovery, targeted visual edits and inspectable composition alternatives."""
from copy import deepcopy
from typing import Optional,Literal
from pydantic import BaseModel,Field
from .models import Block,ChartBlock,DiagramBlock,MetricsBlock,TableBlock,TimelineBlock,MediaBlock,LAYOUTS
from .errors import CiceroError,RevisionConflict
from . import decks as store
from .layouts import build_plan
from .themes import theme_of

class CatalogArgs(BaseModel):
    kind: Literal['summary','charts','diagrams','metrics','tables','timelines','media'] = 'summary'

class SceneArgs(BaseModel):
    deck_id: str = Field(...,max_length=40)
    slide_id: Optional[str] = Field(None,max_length=40)

class VisualUpdateArgs(BaseModel):
    deck_id: str = Field(...,max_length=40)
    slide_id: str = Field(...,max_length=40)
    block_index: int = Field(...,ge=0,le=7)
    block: Block
    expected_revision: Optional[int] = Field(None,ge=1)
    source_ids: Optional[list[int]] = Field(None,max_length=50)

def catalog(svc,args):
    types=['bar','bar_horizontal','line','area','pie','donut','scatter','bubble','dot','dumbbell','band','heatmap','waterfall','funnel']
    if args.kind!='summary':
        cls={'charts':ChartBlock,'diagrams':DiagramBlock,'metrics':MetricsBlock,'tables':TableBlock,'timelines':TimelineBlock,'media':MediaBlock}[args.kind]
        return {'schema_version':'cicero.visuals.v1','kind':args.kind,'schema':cls.model_json_schema(),
            'notes':['Coordinates are computed by Cicero. Values must come from cited sources.',
                'Numeric x_values preserve irregular spacing. Null values represent gaps.',
                'Use build and effect for click-triggered stages. Tables and diagrams export as editable objects.']}
    return {'schema_version':'cicero.visuals.v1','charts':types,'blocks':['diagram','metrics','table','timeline','video','audio'],'layouts':list(LAYOUTS),
        'composition':{'canvas':'normalized block.frame [x,y,width,height] inside the content area','font_size':[14,96],
                       'image_fit':['contain','cover'],'image_position':'normalized horizontal and vertical crop focus'},
        'motion':{'effects':['none','fade','wipe','draw','stages'],'trigger':'click','duration_ms':[100,2000],
            'web':'interactive objects and matched-object morph','pptx':'native timing and transitions','pdf':'complete static state',
            'transitions':['none','fade','slide','convex','concave','zoom','morph'],'identity':'stable block IDs',
            'tools':['deck_transitions','deck_animations']},
        'media':{'types':['video','audio'],'tools':['media_import','media_get','deck_media_control'],
            'playback':['start','end','volume','playback_rate','loop','autoplay','muted','controls','subtitles']},
        'linked_data':{'tools':['dataset_link','dataset_links','dataset_bind','dataset_link_control'],
            'origins':['local CSV/TSV/XLSX','HTTP(S) CSV/TSV/XLSX'],'offline':'immutable current snapshot'},
        'export_notes':{'band':'filled region in web; central and bounding curves in editable PPTX',
            'heatmap':'editable colored table in PPTX','funnel':'editable stage shapes in PPTX',
            'annotations':'point labels in web; editable analytical captions in PPTX',
            'references':'reference lines in web; editable value captions in PPTX',
            'numeric_area':'filled area in web; editable numeric line in PPTX',
            'media':'embedded native clips; trim/rate converted without modifying originals; PDF uses video poster',
            'subtitles':'WebVTT captions in web; captions burned into native video compatibility copy',
            'morph':'web uses easing/group/unmatched; native uses object morph with fade fallback',
            'live_data':'local live views refresh; offline HTML/PPTX/PDF keep the exported snapshot'},
        'workflow':['source_add','visual_catalog','slide_visual_update','slide_variants','deck_scene','deck_check','deck_present','deck_export']}

def update(svc,args):
    with svc.db.transaction():
        slide=store.get_slide(svc,args.deck_id,args.slide_id)
        if args.expected_revision is not None and slide['revision']!=args.expected_revision:
            raise RevisionConflict('The slide changed. Read its current revision before applying this visual edit.')
        blocks=deepcopy(slide['blocks'])
        if args.block_index>len(blocks):raise CiceroError('Replace an existing block or append at the current count.')
        block=args.block.model_dump(exclude_none=True)
        if args.block_index==len(blocks):blocks.append(block)
        else:blocks[args.block_index]=block
        sources=list(dict.fromkeys(slide['sources']+(args.source_ids or [])))
        if blocks==slide['blocks'] and sources==slide['sources']:return {**slide,'changed':False}
        return {**store.patch_slide(svc,args.deck_id,args.slide_id,{'blocks':blocks,'sources':sources},reason='targeted visual edit'),'changed':True}

def variants(svc,args):
    deck=store.deck_view(svc,args.deck_id)
    if not args.slide_id:raise CiceroError('Choose a slide for composition alternatives.')
    slide=store.get_slide(svc,args.deck_id,args.slide_id);types={b['type'] for b in slide['blocks']}
    choices=['evidence','chart','comparison'] if 'chart' in types else ['diagram','evidence','comparison'] if 'diagram' in types else ['metrics','evidence','comparison'] if 'metrics' in types else ['table','evidence','comparison'] if 'table' in types else ['bullets','two_column','comparison']
    out=[]
    for layout in choices:
        draft={**deepcopy(slide),'layout':layout}
        plan=build_plan(draft,deck_title=deck['title'],theme=theme_of(deck),number=slide['position'],total=len(deck['slides']),lang=deck['language'],assets=svc.assets_lookup())
        out.append({'layout':layout,'patch':{'layout':layout},'content_changed':False,'fits_estimate':not plan.overflow,'warnings':plan.overflow_where,'objects':len(plan.boxes),
            'preview_url':svc.base_url()+f'/api/decks/{deck["id"]}/slides/{slide["id"]}/variant.html?layout={layout}'})
    return {'slide_id':slide['id'],'expected_revision':slide['revision'],'variants':out,'basis':'deterministic composition, not a measured aesthetic score'}

def scene(svc,args):
    deck=store.deck_view(svc,args.deck_id);selected=[s for s in deck['slides'] if not args.slide_id or s['id']==args.slide_id]
    if args.slide_id and not selected:store.get_slide(svc,args.deck_id,args.slide_id)
    if deck.get('template'):
        from .template_live import scenes
        all_scenes,w,h=scenes(deck,svc.assets_lookup());plans={x['slide']['id']:x for x in all_scenes}
    else:w,h=1280,720;plans={}
    result=[]
    for slide in selected:
        if slide['id'] in plans:boxes=plans[slide['id']]['boxes'];warnings=plans[slide['id']]['overflow']
        else:
            plan=build_plan(slide,deck_title=deck['title'],theme=theme_of(deck),number=slide['position'],total=len(deck['slides']),lang=deck['language'],assets=svc.assets_lookup())
            boxes=plan.boxes;warnings=plan.overflow_where
        result.append({'slide_id':slide['id'],'revision':slide['revision'],'title':slide['title'],
            'objects':[{'id':b.object_id or f'{slide["id"]}/{i}','kind':b.kind,'frame':[round(v,2) for v in (b.x,b.y,b.w,b.h)],
                'text':[p.text for p in b.paras],'font_sizes':[round(p.size,2) for p in b.paras],'build':b.build,'effect':b.effect} for i,b in enumerate(boxes)],'warnings':warnings})
    return {'schema_version':'cicero.scene.v1','canvas':[w,h],'slides':result,'basis':'shared export geometry'}

def present(svc,args):
    deck=store.deck_view(svc,args.deck_id)
    return {'deck_id':deck['id'],'url':svc.base_url()+f'/api/decks/{deck["id"]}/preview.html?mode=present',
        'engine':'local_web','slides':len(deck['slides']),'controls':['next step','previous step','fullscreen','blackout'],
        'export':'deck_export format html creates a portable offline copy'}
