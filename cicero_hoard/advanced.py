"""Polls and collaborative state shared by API, editor and agents."""
import base64,json,shutil
from pathlib import Path
from typing import Literal,Optional,Any
from pydantic import BaseModel,Field
from . import decks
from .errors import CiceroError
from .hoard_link.ids import new_ulid
from .hoard_link import proc
from .util import jdump,jload
from .models import SlidePatch

class PollArgs(BaseModel):
    deck_id:str
    action:Literal['create','list','state','vote','open','close','reset','rounds','restore','block']='list'
    poll_id:Optional[str]=None
    round_id:Optional[str]=None
    question:str=Field('',max_length=300)
    options:list[str]=Field(default_factory=list,max_length=12)
    participant:str=Field('',max_length=100)
    choice:Optional[int]=Field(None,ge=0,le=11)

def poll_state(svc,deck_id,poll_id):
    row=svc.db.one('SELECT * FROM polls WHERE id=? AND deck_id=?',(poll_id,deck_id))
    if row is None:raise CiceroError('Poll not found')
    options=jload(row['options'],[]);counts=[0]*len(options)
    for v in svc.db.query('SELECT choice,count(*) total FROM poll_votes WHERE poll_id=? GROUP BY choice',(poll_id,)):
        counts[v['choice']]=v['total']
    return {'id':row['id'],'question':row['title'],'options':options,'counts':counts,'total':sum(counts),
            'open':bool(row['open']),'url':svc.base_url()+f'/api/decks/{deck_id}/polls/{poll_id}'}

def poll(svc,args):
    decks._deck_row(svc,args.deck_id)
    with svc.db.transaction():
        if args.action=='create':
            if not args.question.strip() or len(args.options)<2 or any(not s.strip() for s in args.options):
                raise CiceroError('Supply a question and at least two non-empty options')
            pid=new_ulid();svc.db.execute('INSERT INTO polls(id,deck_id,title,options,created_ts) VALUES(?,?,?,?,?)',
                                        (pid,args.deck_id,args.question,jdump(args.options),svc.clock()))
            return poll_state(svc,args.deck_id,pid)
        if args.action=='list':return {'polls':[poll_state(svc,args.deck_id,r['id']) for r in svc.db.query('SELECT id FROM polls WHERE deck_id=?',(args.deck_id,))]}
        if not args.poll_id:raise CiceroError('Supply poll_id')
        state=poll_state(svc,args.deck_id,args.poll_id)
        if args.action=='vote':
            if not state['open']:raise CiceroError('This poll is closed')
            if not args.participant or args.choice is None or args.choice>=len(state['options']):raise CiceroError('Supply participant and an existing choice')
            svc.db.execute('INSERT INTO poll_votes(poll_id,participant,choice,created_ts) VALUES(?,?,?,?) ON CONFLICT(poll_id,participant) DO UPDATE SET choice=excluded.choice,created_ts=excluded.created_ts',
                           (args.poll_id,args.participant,args.choice,svc.clock()))
        elif args.action in ('open','close'):svc.db.execute('UPDATE polls SET open=? WHERE id=?',(args.action=='open',args.poll_id))
        elif args.action=='reset':
            votes=[dict(v) for v in svc.db.query('SELECT participant,choice,created_ts FROM poll_votes WHERE poll_id=?',(args.poll_id,))]
            svc.db.execute('INSERT INTO poll_rounds(id,poll_id,votes,created_ts) VALUES(?,?,?,?)',(new_ulid(),args.poll_id,jdump(votes),svc.clock()))
            svc.db.execute('DELETE FROM poll_votes WHERE poll_id=?',(args.poll_id,))
        elif args.action=='rounds':
            return {'rounds':[{'id':r['id'],'created_ts':r['created_ts'],'total':len(jload(r['votes'],[]))} for r in svc.db.query('SELECT * FROM poll_rounds WHERE poll_id=? ORDER BY created_ts DESC',(args.poll_id,))]}
        elif args.action=='restore':
            row=svc.db.one('SELECT votes FROM poll_rounds WHERE id=? AND poll_id=?',(args.round_id,args.poll_id))
            if row is None:raise CiceroError('Poll round not found')
            for v in jload(row['votes'],[]):
                svc.db.execute('INSERT OR IGNORE INTO poll_votes(poll_id,participant,choice,created_ts) VALUES(?,?,?,?)',(args.poll_id,v['participant'],v['choice'],v['created_ts']))
        elif args.action=='block':return {'block':{'type':'poll','poll_id':state['id'],'question':state['question'],'options':state['options'],'results':state['counts'],'poll_url':state['url']}}
        return poll_state(svc,args.deck_id,args.poll_id)

class CollaborationOperation(BaseModel):
    op:Literal['set','text','insert','delete','move']
    block_id:Optional[str]=None
    path:list[str|int]=Field(default_factory=list)
    value:Any=None
    before_id:Optional[str]=None
    index:int=Field(0,ge=0)
    delete:int=Field(0,ge=0)
    text:str=''

class CollaborationArgs(BaseModel):
    deck_id:str
    slide_id:str
    action:Literal['state','apply','presence','leave']='state'
    update:Optional[str]=Field(None,max_length=2000000)
    patches:Optional[dict[str,Any]]=None
    operations:list[CollaborationOperation]=Field(default_factory=list)
    actor:str=Field('agent',min_length=1,max_length=100)
    label:str=Field('',max_length=100)
    color:str=Field('#278C8C',pattern=r'^#[a-fA-F0-9]{6}$')

def merge_document(state,seed,update=None,patches=None,operations=None):
    node=proc.find_exe('node') or shutil.which('node')
    file=Path(__file__).resolve().parent/'static/visual-runtime/collaboration.mjs'
    if not node or not file.exists():raise CiceroError('Build the packaged collaborative runtime first')
    response=proc.run([node,str(file)],input=jdump({'state':state,'seed':seed,'update':update,'patches':patches,'operations':operations}),timeout=30)
    if response.returncode:raise CiceroError('The collaborative document update is invalid')
    return json.loads(response.stdout)

def collaboration(svc,args):
    with svc.db.transaction():
        slide=decks.get_slide(svc,args.deck_id,args.slide_id)
        if any(not b.get('id') for b in slide['blocks']):
            blocks=[{**b,'id':b.get('id') or 'c-'+new_ulid()} for b in slide['blocks']]
            slide=decks.patch_slide(svc,args.deck_id,args.slide_id,{'blocks':blocks,'expected_revision':slide['revision']},reason='stable collaborative object identities')
        row=svc.db.one('SELECT * FROM collab_documents WHERE slide_id=?',(args.slide_id,))
        fields={k:(slide[k] if k=='blocks' else slide[k] or '') for k in ('title','subtitle','notes','blocks')}
        if row is None:
            merged=merge_document(None,fields)
            svc.db.execute('INSERT INTO collab_documents(slide_id,state,snapshot) VALUES(?,?,?)',(args.slide_id,merged['state'],jdump(merged['snapshot'])))
            row=svc.db.one('SELECT * FROM collab_documents WHERE slide_id=?',(args.slide_id,))
        previous=jload(row['snapshot'],{})
        external={k:v for k,v in fields.items() if previous.get(k)!=v}
        base=merge_document(row['state'],fields,patches=external or None)
        if args.action=='apply':
            if args.patches and any(k not in fields for k in args.patches):raise CiceroError('Collaborative fields are title, subtitle, notes and blocks')
            merged=merge_document(base['state'],fields,update=args.update,patches=args.patches,operations=[op.model_dump() for op in args.operations])
            changed={k:v for k,v in merged['snapshot'].items() if k in fields and v!=fields[k]}
            if changed:
                validated=SlidePatch(**changed).model_dump(exclude_unset=True,exclude_none=True)
                decks.patch_slide(svc,args.deck_id,args.slide_id,{**validated,'expected_revision':slide['revision']},reason='collaborative edit')
                normalized=decks.get_slide(svc,args.deck_id,args.slide_id)
                merged=merge_document(merged['state'],fields,patches={k:normalized[k] or ( [] if k=='blocks' else '') for k in fields})
            svc.db.execute('UPDATE collab_documents SET state=?,snapshot=?,version=version+1 WHERE slide_id=?',
                           (merged['state'],jdump(merged['snapshot']),args.slide_id))
            row=svc.db.one('SELECT * FROM collab_documents WHERE slide_id=?',(args.slide_id,))
        elif base['state']!=row['state']:
            svc.db.execute('UPDATE collab_documents SET state=?,snapshot=?,version=version+1 WHERE slide_id=?',(base['state'],jdump(base['snapshot']),args.slide_id))
            row=svc.db.one('SELECT * FROM collab_documents WHERE slide_id=?',(args.slide_id,))
        if args.action=='leave':svc.db.execute('DELETE FROM collab_presence WHERE slide_id=? AND actor=?',(args.slide_id,args.actor))
        elif args.action in ('presence','apply'):
            svc.db.execute('INSERT INTO collab_presence(slide_id,actor,label,color,updated_ts) VALUES(?,?,?,?,?) ON CONFLICT(slide_id,actor) DO UPDATE SET label=excluded.label,color=excluded.color,updated_ts=excluded.updated_ts',
                           (args.slide_id,args.actor,args.label or args.actor,args.color,svc.clock()))
        return {'state':row['state'],'snapshot':jload(row['snapshot'],{}),'version':row['version'],
                'presence':[dict(r) for r in svc.db.query('SELECT actor,label,color FROM collab_presence WHERE slide_id=? AND updated_ts>?',(args.slide_id,svc.clock()-30))],
                'slide_revision':decks.get_slide(svc,args.deck_id,args.slide_id)['revision'],'engine':'Yjs CRDT',
                'fields':['title','subtitle','notes','blocks'],'text_merge':'character CRDT',
                'block_merge':'stable object maps, nested field CRDT and identity order',
                'operations':['set','text','insert','delete','move'],'deletion':'tombstones win concurrent field edits; explicit insert restores identity'}

def hydrate(svc,deck):
    from copy import deepcopy
    result=deepcopy(deck)
    for slide in result['slides']:
        for block in slide['blocks']:
            if block['type']=='poll':
                state=poll_state(svc,deck['id'],block['poll_id'])
                block.update(question=state['question'],options=state['options'],results=state['counts'],poll_url=state['url'])
    return result

def static_deck(svc,deck):
    from copy import deepcopy
    result=hydrate(svc,deck)
    for slide in result['slides']:
        for index,block in enumerate(slide['blocks']):
            if block['type']=='chart':block.update(animation='none',states=None)
            base={k:block[k] for k in ('id','frame','font_size','build','effect','duration_ms','action') if k in block}
            if block['type']=='poll':
                slide['blocks'][index]={**base,'type':'table','title':block['question'],'headers':['Opcion','Votos'] if deck.get('language')=='es' else ['Option','Votes'],
                    'rows':[[label,str(block['results'][i])] for i,label in enumerate(block['options'])]}
            if block['type']=='scene3d':
                poster=block.get('poster_id')
                asset=svc.assets_lookup()(poster) if poster else None
                if not asset or asset.get('deck_id')!=deck['id'] or asset.get('mime') not in ('image/png','image/jpeg','image/gif','image/webp'):poster=None
                if not poster:
                    from . import visual_review as vr
                    from .render import render_document
                    from playwright.sync_api import sync_playwright
                    import tempfile
                    draft=deepcopy(deck);draft['slides']=[{**slide,'layout':'freeform','blocks':[{**block,'frame':[0,0,1,1]}]}]
                    html=render_document(draft,assets=svc.assets_lookup(),inline=True)[0]
                    with sync_playwright() as p,tempfile.TemporaryDirectory(prefix='cicero-scene-') as profile:
                        context=vr._launch(p,profile)
                        try:
                            page=context.new_page();page.emulate_media(reduced_motion='reduce');page.set_content(html,wait_until='load')
                            page.wait_for_function("document.querySelector('.scene3d')?.dataset.ready==='true'||document.querySelector('.scene3d')?.dataset.error",timeout=15000)
                            error=page.locator('.scene3d').get_attribute('data-error')
                            if error:raise CiceroError('3D poster could not render: '+error)
                            data=page.locator('.scene3d').screenshot()
                        finally:context.close()
                    poster=decks.add_asset(svc,deck['id'],data,'scene3d.png')['asset_id']
                slide['blocks'][index]={**base,'type':'image','asset_id':poster,'caption':block.get('caption','')}
    return result
