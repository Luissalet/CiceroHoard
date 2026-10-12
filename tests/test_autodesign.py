from copy import deepcopy
import json,threading
from pathlib import Path
import pytest
from cicero_hoard import decks,autodesign as design,visual_lab as lab
from cicero_hoard.agent_tools import TOOLS_BY_NAME
from cicero_hoard.errors import CiceroError,RevisionConflict
from conftest import new_deck,FakeLink,png_bytes

def setup(svc,monkeypatch):
    d=new_deck(svc)
    s=decks.add_slide(svc,d['id'],title='Exact evidence',notes='Keep notes and units',blocks=[
        {'type':'chart','chart':'bar','categories':['North','South'],'series':[{'name':'kg','values':[-12,20]}],'y_label':'kg'},
        {'type':'text','text':'Observed results; not causal.'}])
    def render(svc,args,vid):
        deck,row=lab.variant_deck(svc,args,vid)
        path=svc.config.data_dir/(vid+'.png');path.write_bytes(png_bytes())
        from cicero_hoard.util import sha256_hex,jdump
        metrics={'errors':0,'warnings':0,'readability_penalty':0,'constraint_score':100,'min_font_px':24}
        svc.db.execute('UPDATE visual_variants SET png=?,metrics=? WHERE id=?',(str(path),jdump(metrics),vid))
        return {'id':vid,'label':row['label'],'png_path':str(path),'png_url':'/image/'+vid,'png_sha256':sha256_hex(path.read_bytes()),'metrics':metrics,'findings':[]}
    monkeypatch.setattr(lab,'render',render)
    svc.link_sync=FakeLink(lambda messages:json.dumps({'candidates':[{'label':'Evidence first','placements':[
        {'block_index':0,'frame':[0,0,1,.75],'chart':'bar_horizontal'},
        {'block_index':1,'frame':[0,.8,1,.2],'font_size':28}]}]}))
    return d,s

def test_real_model_loop_calls_model_preserves_evidence_and_applies(services,monkeypatch):
    d,s=setup(services,monkeypatch)
    result=design.run(services,design.DesignArgs(deck_id=d['id'],slide_id=s['id'],rounds=2))
    assert result['status']=='complete' and len(services.link_sync.calls)==2
    assert result['changed_slides']==[s['id']]
    current=decks.get_slide(services,d['id'],s['id'])
    assert current['revision']==s['revision']+1
    assert lab.content_signature(current)==lab.content_signature(s)
    assert current['notes']==s['notes'] and current['sources']==s['sources']
    assert result['slides'][0]['model_calls'][0]['model']=='fake-model'
    assert result['slides'][0]['model_calls'][0]['visual_input'] is False
    assert design.run(services,design.DesignArgs(deck_id=d['id'],run_id=result['run_id'],action='apply'))['status']=='complete'
    assert decks.get_slide(services,d['id'],s['id'])['revision']==current['revision']

def test_external_image_review_is_bound_to_exact_evidence(services,monkeypatch):
    d,s=setup(services,monkeypatch)
    r=design.run(services,design.DesignArgs(deck_id=d['id'],slide_id=s['id'],critic='external',include_image=True))
    assert r['status']=='awaiting_feedback' and r['_image']['mime']=='image/png'
    req=r['review_request'];args=dict(deck_id=d['id'],run_id=r['run_id'],action='feedback',variant_id=req['variant_id'],png_sha256=req['png_sha256'])
    with pytest.raises(RevisionConflict):design.run(services,design.DesignArgs(**{**args,'png_sha256':'wrong'},feedback={'accept':True}))
    different=next(c['id'] for c in r['slides'][0]['candidates'] if c['id']!=req['variant_id'])
    with pytest.raises(CiceroError,match='own image'):design.run(services,design.DesignArgs(**args,feedback={'preferred_variant_id':different}))
    status=design.run(services,design.DesignArgs(deck_id=d['id'],run_id=r['run_id'],action='status'))
    assert not status['slides'][0]['reviews']
    feedback=design.run(services,design.DesignArgs(**args,feedback={'issues':['Use more room for the evidence.'],'accept':False}))
    assert feedback['status']=='ready'
    r2=design.run(services,design.DesignArgs(deck_id=d['id'],run_id=r['run_id'],action='step'))
    assert r2['round']==2 and r2['status']=='awaiting_feedback'
    assert 'more room' in services.link_sync.calls[-1][1]['content']
    done=design.run(services,design.DesignArgs(**{**args,'variant_id':r2['review_request']['variant_id'],'png_sha256':r2['review_request']['png_sha256']},feedback={'accept':True}))
    assert done['status']=='complete'

def test_stale_source_and_unavailable_model_are_not_silently_replaced(services,monkeypatch):
    d,s=setup(services,monkeypatch)
    r=design.run(services,design.DesignArgs(deck_id=d['id'],slide_id=s['id'],action='start'))
    decks.patch_slide(services,d['id'],s['id'],{'notes':'New manual note'})
    failed=design.run(services,design.DesignArgs(deck_id=d['id'],run_id=r['run_id'],action='step'))
    assert failed['status']=='failed' and not services.link_sync.calls
    assert decks.get_slide(services,d['id'],s['id'])['notes']=='New manual note'
    services.link_sync.available=False
    failed=design.run(services,design.DesignArgs(deck_id=d['id'],slide_id=s['id']))
    assert failed['error']['code']=='design_model_failed'
    assert not failed['changed_slides']

def test_one_worker_per_run_and_cancel_during_model_call(services,monkeypatch):
    d,s=setup(services,monkeypatch)
    r=design.run(services,design.DesignArgs(deck_id=d['id'],slide_id=s['id'],action='start'))
    entered=threading.Event();release=threading.Event();original=services.link_sync.responder
    def model(messages):entered.set();release.wait(10);return original(messages)
    services.link_sync.responder=model
    results=[]
    args=design.DesignArgs(deck_id=d['id'],run_id=r['run_id'],action='step')
    worker=threading.Thread(target=lambda:results.append(design.run(services,args)));worker.start()
    try:
        assert entered.wait(10)
        with pytest.raises(CiceroError,match='already advancing'):design.run(services,args)
        assert design.run(services,design.DesignArgs(deck_id=d['id'],run_id=r['run_id'],action='status'))['status']=='running'
        design.run(services,design.DesignArgs(deck_id=d['id'],run_id=r['run_id'],action='cancel'))
    finally:release.set();worker.join(10)
    assert results[0]['status']=='cancelled' and not results[0]['changed_slides']
    assert decks.get_slide(services,d['id'],s['id'])['revision']==s['revision']

def test_design_undo_tracks_only_changed_slides_and_preserves_later_edits(services,monkeypatch):
    d,s=setup(services,monkeypatch);other=decks.add_slide(services,d['id'],title='Independent')
    tool=TOOLS_BY_NAME['deck_design'];args=design.DesignArgs(deck_id=d['id'],slide_id=s['id'],rounds=1)
    before=tool.capture(services,args);result=tool.run(services,args);track=tool.track(args,result,ctx=services)
    assert isinstance(track['etag'],str)
    decks.patch_slide(services,d['id'],other['id'],{'notes':'Later independent note'})
    assert tool.undo(services,{**track,'before':before})['restored']==[s['id']]
    assert decks.get_slide(services,d['id'],other['id'])['notes']=='Later independent note'
    before=tool.capture(services,args);result=tool.run(services,args);track=tool.track(args,result,ctx=services)
    decks.patch_slide(services,d['id'],s['id'],{'notes':'Keep this'})
    with pytest.raises(Exception,match='edited afterwards'):tool.undo(services,{**track,'before':before})

def test_chart_alternatives_preserve_analytic_semantics(services):
    d=new_deck(services);s=decks.add_slide(services,d['id'],blocks=[{'type':'chart','chart':'waterfall','categories':['Before','Change'],'series':[{'name':'Net','values':[10,-2]}]}])
    blocks=deepcopy(s['blocks']);blocks[0]['chart']='bar'
    with pytest.raises(CiceroError,match='evidence'):lab.run(services,lab.LabArgs(deck_id=d['id'],slide_id=s['id'],action='candidate',patch={'blocks':blocks}))

def test_vision_uses_image_content_on_global_multimodal_route(services,monkeypatch):
    d,s=setup(services,monkeypatch);calls=[];original=services.link_sync.chat
    def chat(messages,images=None,**kwargs):
        calls.append({'images':images,**kwargs})
        if 'review presentation design' in messages[0]['content']:
            from conftest import FakeChatResult
            return FakeChatResult(text='{"strengths":["Clear"],"issues":[]}')
        return original(messages,images=images,**kwargs)
    services.link_sync.chat=chat
    result=design.run(services,design.DesignArgs(deck_id=d['id'],slide_id=s['id'],critic='vision',rounds=1))
    assert result['status']=='complete'
    assert len(calls)==2 and all(c['capability']=='llm' and c['images'][0].startswith(b'\x89PNG') for c in calls)
    assert result['slides'][0]['model_calls'][0]['visual_input'] is True
    assert result['slides'][0]['reviews'][0]['route']=='global multimodal chat'

def test_manual_apply_remains_available_after_design_completes(services,monkeypatch):
    d,s=setup(services,monkeypatch)
    result=design.run(services,design.DesignArgs(deck_id=d['id'],slide_id=s['id'],rounds=1,auto_apply=False))
    assert result['status']=='complete' and not result['slides'][0]['applied']
    assert decks.get_slide(services,d['id'],s['id'])['revision']==s['revision']
    applied=design.run(services,design.DesignArgs(deck_id=d['id'],run_id=result['run_id'],action='apply'))
    assert applied['status']=='complete' and applied['slides'][0]['applied'] and applied['changed_slides']==[s['id']]
    assert decks.get_slide(services,d['id'],s['id'])['revision']==s['revision']+1

def test_cancel_confirmed_immediately_before_apply_prevents_write(services,monkeypatch):
    d,s=setup(services,monkeypatch);original=design._apply
    def cancel_before(svc,state,item):
        design.run(svc,design.DesignArgs(deck_id=d['id'],run_id=state['id'],action='cancel'))
        return original(svc,state,item)
    monkeypatch.setattr(design,'_apply',cancel_before)
    result=design.run(services,design.DesignArgs(deck_id=d['id'],slide_id=s['id'],rounds=1))
    assert result['status']=='cancelled' and not result['changed_slides']
    assert decks.get_slide(services,d['id'],s['id'])['revision']==s['revision']

def test_direct_run_claims_its_actual_id_before_calling_model(services,monkeypatch):
    d,s=setup(services,monkeypatch);entered=threading.Event();release=threading.Event();original=services.link_sync.responder
    def model(messages):entered.set();release.wait(10);return original(messages)
    services.link_sync.responder=model;result=[]
    worker=threading.Thread(target=lambda:result.append(design.run(services,design.DesignArgs(deck_id=d['id'],slide_id=s['id'],rounds=1))))
    worker.start()
    try:
        assert entered.wait(10)
        state=design.run(services,design.DesignArgs(deck_id=d['id'],action='list'))['runs'][0]
        with pytest.raises(CiceroError,match='already advancing'):
            design.run(services,design.DesignArgs(deck_id=d['id'],run_id=state['id'],action='step'))
        assert len(services.link_sync.calls)==1
    finally:release.set();worker.join(10)
    assert result[0]['status']=='complete'

def test_feedback_rejects_changed_png_bytes(services,monkeypatch):
    d,s=setup(services,monkeypatch)
    result=design.run(services,design.DesignArgs(deck_id=d['id'],slide_id=s['id'],critic='external'))
    Path(result['best']['png_path']).write_bytes(png_bytes(color=(10,20,30)))
    req=result['review_request']
    with pytest.raises(RevisionConflict,match='PNG changed'):
        design.run(services,design.DesignArgs(deck_id=d['id'],run_id=result['run_id'],action='feedback',variant_id=req['variant_id'],png_sha256=req['png_sha256'],feedback={'accept':True}))

def test_theme_changes_invalidate_image_feedback_without_changing_slide_revision(services,monkeypatch):
    from cicero_hoard.agent_tools import call_tool
    d,s=setup(services,monkeypatch)
    result=design.run(services,design.DesignArgs(deck_id=d['id'],slide_id=s['id'],critic='external'))
    call_tool(services,'deck_theme',{'deck_id':d['id'],'theme':'oscuro'})
    assert decks.get_slide(services,d['id'],s['id'])['revision']==s['revision']
    req=result['review_request']
    with pytest.raises(RevisionConflict,match='context changed'):
        design.run(services,design.DesignArgs(deck_id=d['id'],run_id=result['run_id'],action='feedback',variant_id=req['variant_id'],png_sha256=req['png_sha256'],feedback={'accept':True}))
    applied=design.run(services,design.DesignArgs(deck_id=d['id'],run_id=result['run_id'],action='apply'))
    assert applied['status']=='failed' and not applied['changed_slides']
    assert decks.get_slide(services,d['id'],s['id'])['revision']==s['revision']

def test_design_undo_survives_real_agent_journal_serialization(client,monkeypatch):
    from test_agent_accountability import agent_call,ok,undo
    d,s=setup(client.svc,monkeypatch)
    result=ok(agent_call(client,'deck_design',{'deck_id':d['id'],'slide_id':s['id'],'rounds':1},session='design-receipt'))
    assert result['status']=='complete'
    restored=ok(undo(client,'design-receipt',confirm=True))
    assert restored['complete'] and not restored['conflicts']
    assert lab.content_signature(decks.get_slide(client.svc,d['id'],s['id']))==lab.content_signature(s)
    assert decks.get_slide(client.svc,d['id'],s['id'])['layout']==s['layout']

@pytest.mark.parametrize('count',[1,2])
def test_failed_apply_after_complete_has_no_out_of_range_next(client,monkeypatch,count):
    from test_agent_accountability import agent_call,ok
    d,s=setup(client.svc,monkeypatch)
    slides=[s]
    if count==2:slides.append(decks.add_slide(client.svc,d['id'],title='Second',blocks=s['blocks']))
    result=ok(agent_call(client,'deck_design',{'deck_id':d['id'],'rounds':1,'auto_apply':False},session='completed-recovery'))
    assert result['index']==count and not result['can_advance'] and result['rounds']==1
    decks.patch_slide(client.svc,d['id'],slides[-1]['id'],{'notes':'Preserve this newer edit'})
    args={'deck_id':d['id'],'run_id':result['run_id']}
    failed=ok(agent_call(client,'deck_design',{**args,'action':'apply'},session='completed-recovery'))
    assert failed['status']=='failed' and not failed['can_advance']
    assert failed['changed_slides']==([s['id']] if count==2 else [])
    for action in ('step','run','review','feedback'):
        recovered=ok(agent_call(client,'deck_design',{**args,'action':action},session='completed-recovery'))
        assert recovered['status']=='failed' and recovered['error']==failed['error']
        assert recovered['index']==count and not recovered['changed_slides']
    assert decks.get_slide(client.svc,d['id'],slides[-1]['id'])['notes']=='Preserve this newer edit'

