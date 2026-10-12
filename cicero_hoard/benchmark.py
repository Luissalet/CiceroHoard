"""Local end-to-end paired evaluation with a common native rasterizer and blind votes."""
from copy import deepcopy
from pathlib import Path
from collections import Counter
import base64,io,json,random,re,zipfile
from typing import Any,Literal,Optional
from lxml import etree
from pydantic import BaseModel,Field
from . import decks,native_slides
from .errors import CiceroError,NotFound,RevisionConflict
from .hoard_link.ids import new_ulid
from .util import jdump,jload,sha256_hex

RUBRIC=['legibility','hierarchy','evidence_visibility','narrative_clarity','composition']
NS={'a':'http://schemas.openxmlformats.org/drawingml/2006/main','c':'http://schemas.openxmlformats.org/drawingml/2006/chart',
    'r':'http://schemas.openxmlformats.org/package/2006/relationships'}
class CaseArgs(BaseModel):
    key:str
    brief:str
    deck_id:Optional[str]=None
    slide_ids:Optional[list[str]]=None
    baseline_path:str
    baseline_workflow:dict[str,Any]=Field(default_factory=dict)
    cicero_workflow:dict[str,Any]=Field(default_factory=dict)

class BenchmarkArgs(BaseModel):
    deck_id:str
    action:Literal['create','case','render','blind','rate','summary','list']='summary'
    benchmark_id:Optional[str]=None
    title:str='Paired local evaluation'
    case:Optional[CaseArgs]=None
    case_id:Optional[str]=None
    slide_position:int=Field(1,ge=1)
    token:Optional[str]=None
    reviewer:str='external LLM'
    ratings:Optional[dict[str,Any]]=None
    include_image:bool=False

def _save(svc,state):
    svc.db.execute('UPDATE visual_benchmarks SET state=?,updated_ts=? WHERE id=?',(jdump(state),svc.clock(),state['id']))

def _get(svc,args):
    row=svc.db.one('SELECT state FROM visual_benchmarks WHERE id=? AND deck_id=?',(args.benchmark_id,args.deck_id))
    if row is None:raise NotFound('Benchmark not found')
    return jload(row['state'],{})

def _xml(raw):return etree.fromstring(raw,parser=etree.XMLParser(resolve_entities=False,no_network=True))
def _norm(text):return re.sub(r'\s+',' ',str(text)).strip().casefold()

def _cache(element,path,numeric=False):
    points=element.xpath(path+'//c:pt',namespaces=NS)
    counts=element.xpath(path+'//c:ptCount/@val',namespaces=NS)
    length=int(counts[0]) if counts else max((int(p.get('idx','0'))+1 for p in points),default=0)
    result=[None]*length
    for point in points:
        value=point.find('c:v',namespaces=NS)
        if value is not None and value.text is not None:
            result[int(point.get('idx','0'))]=float(value.text) if numeric else value.text
    return result

def pptx_ledger(data):
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        paths=sorted((n for n in z.namelist() if re.fullmatch(r'ppt/slides/slide\d+\.xml',n)),key=lambda n:int(re.search(r'(\d+)\.xml',n)[1]))
        result=[]
        for path in paths:
            xml=_xml(z.read(path));text=xml.xpath('//a:t/text()',namespaces=NS);charts=[]
            relpath=path.replace('ppt/slides/','ppt/slides/_rels/')+'.rels'
            relationships={r.get('Id'):r.get('Target') for r in _xml(z.read(relpath))} if relpath in z.namelist() else {}
            for chart in xml.xpath('//c:chart',namespaces=NS):
                from posixpath import normpath,join
                target=relationships.get(chart.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id'))
                if not target:continue
                from urllib.parse import unquote
                cx=_xml(z.read(normpath(join('ppt/slides',unquote(target))).lstrip('/')))
                text+=cx.xpath('//a:t/text()',namespaces=NS)
                rows=[]
                for s in cx.xpath('//c:ser',namespaces=NS):
                    name=s.xpath('./c:tx//c:v/text()',namespaces=NS)
                    categories=_cache(s,'./c:cat')
                    values=_cache(s,'./c:val',True)
                    rows.append({'name':name[0] if name else '', 'categories':categories,'values':values})
                    text+=name+[c for c in categories if c is not None]
                charts.append(rows)
            result.append({'text':text,'charts':charts})
        return result

def _snippets(slide):
    result=[slide['title']]
    if slide.get('subtitle'):result.append(slide['subtitle'])
    for b in slide['blocks']:
        kind=b['type']
        if kind in ('text','quote'):result.append(b.get('text',''))
        elif kind=='bullets':result+=b['items']
        elif kind=='chart':result+=[b.get(k,'') for k in ('title','unit','x_label','y_label')]
        elif kind=='metrics':result += [v for item in b['items'] for v in [item['label'],item['value'],item.get('detail','')]]
        elif kind=='diagram':result += [v for item in b['nodes'] for v in [item['label'],item.get('detail','')]]
        elif kind=='table':result += b['headers']+[v for row in b['rows'] for v in row]
        elif kind=='timeline':result += [v for item in b['items'] for v in [item['label'],item.get('date',''),item.get('detail','')]]
        elif kind in ('image','scene3d','video','audio'):result.append(b.get('caption',''))
    return [s for s in result if s]

def fidelity(slides,ledger):
    defects=[];checks=[]
    if len(slides)!=len(ledger):defects.append({'kind':'slide_count','expected':len(slides),'actual':len(ledger)})
    for i,(slide,actual) in enumerate(zip(slides,ledger),1):
        text=' '.join(_norm(s) for s in actual['text'])
        missing=[s for s in _snippets(slide) if _norm(s) not in text]
        if missing:defects.append({'position':i,'kind':'missing_labels_units_or_evidence','missing':missing})
        expected=[b for b in slide['blocks'] if b['type']=='chart']
        for b in expected:
            if b['chart'] not in ('bar','bar_horizontal','line','area','pie','donut'):
                defects.append({'position':i,'kind':'semantic_check_requires_review','chart':b['chart']});continue
            target=[{'name':s['name'],'categories':b['categories'],'values':s['values']} for s in b['series']]
            if target not in actual['charts']:defects.append({'position':i,'kind':'chart_values_labels_or_order','expected':target,'actual':actual['charts']})
        checks.append({'position':i,'title_order':_norm(slide['title']) in text,'text_units_labels':not missing})
    return {'ok':not defects,'checks':checks,'defects':defects,'scope':'Exact declared text, title order and supported native categorical chart caches. Other semantics require explicit review; this does not certify every interpretation.'}

def _case(svc,state,args):
    item=args.case
    if item is None:raise CiceroError('Supply case')
    if any(c['key']==item.key for c in state['cases']):raise CiceroError('Case keys must be unique')
    deck=decks.deck_view(svc,item.deck_id or args.deck_id)
    if item.slide_ids:
        by_id={s['id']:s for s in deck['slides']}
        if any(sid not in by_id for sid in item.slide_ids):raise NotFound('A benchmark slide does not exist')
        deck['slides']=[by_id[sid] for sid in item.slide_ids]
    if not deck['slides']:raise CiceroError('Choose at least one slide')
    path=Path(item.baseline_path).expanduser().resolve()
    if not path.is_file() or path.suffix.lower()!='.pptx':raise CiceroError('Supply an independently authored local PPTX baseline')
    raw=path.read_bytes();digest=sha256_hex(raw)
    if svc.db.one('SELECT id FROM exports WHERE sha256=?',(digest,)):
        raise CiceroError('A Cicero export is not an independent harness baseline')
    ledger=pptx_ledger(raw);case_id=new_ulid()
    folder=svc.config.data_dir/'benchmarks'/state['id']/case_id;folder.mkdir(parents=True,exist_ok=True)
    (folder/'baseline.pptx').write_bytes(raw)
    result={'id':case_id,'key':item.key,'brief':item.brief,'deck':deck,'baseline_sha256':sha256_hex(raw),
        'baseline_fidelity':fidelity(deck['slides'],ledger),'status':'pending','ratings':[],
        'workflows':{'baseline':item.baseline_workflow,'cicero':item.cicero_workflow},'folder':str(folder)}
    state['cases'].append(result);_save(svc,state);return {'case_id':case_id,'status':result['status'],'baseline_fidelity':result['baseline_fidelity']}

def _render(svc,state,case):
    from .advanced import static_deck
    from .export_pptx import build_pptx
    folder=Path(case['folder'])
    try:
        current=decks.deck_view(svc,case['deck']['id']);revisions={s['id']:s['revision'] for s in current['slides']}
        if any(revisions.get(s['id'])!=s['revision'] for s in case['deck']['slides']):raise RevisionConflict('The benchmark source changed; register a fresh case')
        raw=build_pptx(static_deck(svc,case['deck']),assets=svc.assets_lookup());(folder/'cicero.pptx').write_bytes(raw)
        case['cicero_sha256']=sha256_hex(raw);case['cicero_fidelity']=fidelity(case['deck']['slides'],pptx_ledger(raw))
        reports={};render_paths={}
        for arm in ('baseline','cicero'):
            data=(folder/(arm+'.pptx')).read_bytes()
            target=folder/arm/(sha256_hex(data)+native_slides.renderer_fingerprint()[:16])
            report=(svc._native_render_fn or native_slides.render)(data,target);render_paths[arm]=str(target)
            reports[arm]={'renderer':report['renderer'],'slide_count':report['slide_count'],'findings':native_slides.layout_findings(report)}
        if reports['baseline']['renderer']!=reports['cicero']['renderer']:raise CiceroError('Both arms need the same native rasterizer')
        if reports['baseline']['slide_count']!=reports['cicero']['slide_count']:raise CiceroError('Both arms need the same slide count')
        from PIL import Image
        for pos in range(1,reports['cicero']['slide_count']+1):
            sizes=[Image.open(Path(render_paths[arm])/f'slide-{pos}.png').size for arm in ('baseline','cicero')]
            if sizes[0]!=sizes[1]:raise CiceroError('Both arms need the same slide canvas and viewport')
        case['rendered']=reports;case['render_paths']=render_paths;case['status']='rendered';case.pop('error',None)
    except Exception as error:
        case['status']='failed';case['error']=str(error)
    _save(svc,state)
    return {'case_id':case['id'],'status':case['status'],'error':case.get('error'),'rendered':case.get('rendered'),
        'baseline_fidelity':case['baseline_fidelity'],'cicero_fidelity':case.get('cicero_fidelity')}

def _blind(svc,state,case,args):
    if case['status']!='rendered':raise CiceroError('Render both workflows before creating a blind pair')
    position=args.slide_position
    if position>len(case['deck']['slides']):raise CiceroError('The slide position does not exist')
    from PIL import Image,ImageDraw
    arms=['baseline','cicero'];random.SystemRandom().shuffle(arms)
    paths=[Path(case['render_paths'][arm])/f'slide-{position}.png' for arm in arms]
    images=[Image.open(p).convert('RGB') for p in paths];width,height=images[0].size
    contact=Image.new('RGB',(width*2,height+50),'white');draw=ImageDraw.Draw(contact)
    for i,img in enumerate(images):contact.paste(img,(i*width,50));draw.text((i*width+24,16),'AB'[i],fill='black')
    token=new_ulid();path=Path(case['folder'])/(token+'.png');contact.save(path)
    evidence={'token':token,'position':position,'arms':arms,'path':str(path),'sha256':sha256_hex(path.read_bytes()),
        'arm_sha256':[sha256_hex(p.read_bytes()) for p in paths]}
    case.setdefault('blind_pairs',[]).append(evidence);_save(svc,state)
    result={'case_id':case['id'],'token':token,'position':position,'rubric':RUBRIC,'score_range':[1,5],
        'source_manifest':{'title':case['deck']['slides'][position-1]['title'],'blocks':case['deck']['slides'][position-1]['blocks'],
                           'sources':case['deck']['slides'][position-1]['sources']},
        'png_sha256':evidence['sha256'],'png_url':svc.base_url()+f"/api/decks/{state['deck_id']}/benchmarks/{state['id']}/{token}.png",
        'instruction':'Score A and B for each fixed criterion, then prefer A, B or tie. Inspect actual images. Do not infer the authoring workflow.'}
    if args.include_image:result['_image']={'mime':'image/png','data':base64.b64encode(path.read_bytes()).decode('ascii')}
    return result

def _rate(svc,state,case,args):
    pair=next((p for p in case.get('blind_pairs',[]) if p['token']==args.token),None)
    if pair is None:raise CiceroError('Choose a blind pair token from this case')
    ratings=args.ratings or {}
    if ratings.get('png_sha256')!=pair['sha256']:raise RevisionConflict('The judgement must identify the exact blind image')
    if sha256_hex(Path(pair['path']).read_bytes())!=pair['sha256']:raise RevisionConflict('The blind image changed')
    for arm in ('A','B'):
        if set(ratings.get(arm,{}))!=set(RUBRIC):raise CiceroError('Score every fixed criterion for both A and B')
        if any(type(v) not in (int,float) or not 1<=v<=5 for v in ratings[arm].values()):raise CiceroError('Rubric scores range from1 to5')
    if ratings.get('preference') not in ('A','B','tie'):raise CiceroError('Preference is A, B or tie')
    if set(ratings.get('source_checks',{}))!={'A','B'} or any(type(v) is not bool for v in ratings['source_checks'].values()):
        raise CiceroError('Explicitly verify source values, units, labels, citations and order for A and B')
    record={'token':args.token,'position':pair['position'],'reviewer':args.reviewer,'ratings':ratings}
    existing=next((r for r in case['ratings'] if r['token']==args.token and r['reviewer']==args.reviewer),None)
    if existing:
        if existing!=record:raise CiceroError('This reviewer already judged this pair; use a distinct reviewer for another judgement')
    else:case['ratings'].append(record);_save(svc,state)
    return {'recorded':True,'judgements':len(case['ratings'])}

def summary(state):
    outcomes=Counter();eligible_outcomes=Counter();cases=[]
    for case in state['cases']:
        votes=[]
        for vote in case['ratings']:
            pair=next(p for p in case['blind_pairs'] if p['token']==vote['token']);preference=vote['ratings']['preference']
            winner='tie' if preference=='tie' else pair['arms'][0 if preference=='A' else 1]
            outcomes[winner]+=1;votes.append({**vote,'winner':winner,'mapping':dict(zip(('A','B'),pair['arms']))})
        equivalent=case['baseline_fidelity']['ok'] and case.get('cicero_fidelity',{}).get('ok',False)
        for vote in votes:
            if equivalent and case['status']=='rendered' and all(vote['ratings']['source_checks'].values()):eligible_outcomes[vote['winner']]+=1
        cases.append({'case_id':case['id'],'key':case['key'],'brief':case['brief'],'status':case['status'],'error':case.get('error'),
            'source_equivalent':equivalent,'baseline_fidelity':case['baseline_fidelity'],'cicero_fidelity':case.get('cicero_fidelity'),
            'rendered':case.get('rendered'),'workflows':case['workflows'],'judgements':votes,
            'eligible_for_comparison':equivalent and case['status']=='rendered'})
    return {'benchmark_id':state['id'],'title':state['title'],'rubric':RUBRIC,'cases':cases,'outcomes':dict(outcomes),'source_verified_outcomes':dict(eligible_outcomes),
        'scope':'Actual independently authored PPTX workflows, common native rasterizer and fixed blind rubric. All cases, failures, ties and regressions remain visible. These results do not establish universal superiority.',
        'complete':bool(cases) and all(c['eligible_for_comparison'] and len({v['position'] for v in c['judgements'] if all(v['ratings']['source_checks'].values())})==c['rendered']['cicero']['slide_count'] for c in cases)}

def _run(svc,args):
    decks._deck_row(svc,args.deck_id)
    if args.action=='create':
        state={'id':new_ulid(),'deck_id':args.deck_id,'title':args.title,'cases':[],'created_ts':svc.clock()}
        svc.db.execute('INSERT INTO visual_benchmarks(id,deck_id,state,created_ts,updated_ts) VALUES(?,?,?,?,?)',(state['id'],args.deck_id,jdump(state),svc.clock(),svc.clock()))
        return summary(state)
    if args.action=='list':return {'benchmarks':[summary(jload(r['state'],{})) for r in svc.db.query('SELECT state FROM visual_benchmarks WHERE deck_id=?',(args.deck_id,))]}
    state=_get(svc,args)
    if args.action=='summary':return summary(state)
    if args.action=='case':return _case(svc,state,args)
    cases=[c for c in state['cases'] if not args.case_id or c['id']==args.case_id]
    if not cases:raise NotFound('Benchmark case not found')
    if args.action=='render':return {'results':[_render(svc,state,c) for c in cases]}
    if len(cases)!=1:raise CiceroError('Choose case_id')
    return _blind(svc,state,cases[0],args) if args.action=='blind' else _rate(svc,state,cases[0],args)

def run(svc,args):
    import threading
    with svc.benchmark_lock:lock=svc.benchmark_locks.setdefault(args.benchmark_id or args.deck_id,threading.RLock())
    with lock:return _run(svc,args)
