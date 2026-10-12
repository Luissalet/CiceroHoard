from copy import deepcopy
from pathlib import Path
import pytest
from cicero_hoard import decks,visual_lab as lab
from cicero_hoard.agent_tools import TOOLS_BY_NAME
from cicero_hoard.errors import CiceroError,RevisionConflict
from conftest import new_deck


def example(svc):
    deck=new_deck(svc)
    slide=decks.add_slide(svc,deck['id'],title='Measured comparison',notes='Keep these notes',layout='evidence',blocks=[
        {'type':'chart','chart':'bar_horizontal','categories':['A','B'],'series':[{'name':'Value','values':[12,20]}]},
        {'type':'text','text':'Same evidence in every composition.'},
        {'type':'metrics','items':[{'label':'Observed','value':'20'}]}])
    return deck,slide


def test_variants_distinct_and_preserve_evidence(services):
    d,s=example(services)
    result=lab.run(services,lab.LabArgs(deck_id=d['id'],slide_id=s['id']))
    assert len(result['variants'])==8
    signatures=set()
    for v in result['variants']:
        variant,_=lab.variant_deck(services,lab.LabArgs(deck_id=d['id']),v['id'])
        candidate=variant['slides'][0]
        assert lab.content_signature(candidate)==lab.content_signature(s)
        assert candidate['notes']==s['notes'] and candidate['sources']==s['sources']
        signatures.add(str(v['patch']))
    assert len(signatures)>=7


def test_custom_correction_rejects_content_and_notes_changes(services):
    d,s=example(services)
    for patch in ({'notes':'Changed'},{'blocks':[{'type':'text','text':'Invented value'}]}):
        with pytest.raises(CiceroError,match='evidence'):
            lab.run(services,lab.LabArgs(deck_id=d['id'],slide_id=s['id'],action='candidate',patch=patch))
    blocks=deepcopy(s['blocks']);blocks[0]['frame']=[0,0,.6,1]
    accepted=lab.run(services,lab.LabArgs(deck_id=d['id'],slide_id=s['id'],action='candidate',patch={'layout':'freeform','blocks':blocks}))
    assert accepted['content_preserved']

def test_legacy_invalid_geometry_can_be_corrected_without_rejecting_its_facts(services):
    d=new_deck(services);s=decks.add_slide(services,d['id'],layout='freeform',blocks=[{'type':'text','text':'Exact evidence','frame':[.9,0,.3,1]}])
    corrected=deepcopy(s['blocks']);corrected[0]['frame']=[0,0,1,1]
    result=lab.run(services,lab.LabArgs(deck_id=d['id'],slide_id=s['id'],action='candidate',patch={'blocks':corrected}))
    assert result['content_preserved']


def test_stale_variants_do_not_replace_manual_work(services):
    d,s=example(services)
    v=lab.run(services,lab.LabArgs(deck_id=d['id'],slide_id=s['id']))['variants'][1]
    decks.patch_slide(services,d['id'],s['id'],{'notes':'Later manual note'})
    with pytest.raises(RevisionConflict):lab.run(services,lab.LabArgs(deck_id=d['id'],variant_id=v['id'],action='apply'))
    assert decks.get_slide(services,d['id'],s['id'])['notes']=='Later manual note'


def test_apply_hooks_restore_without_touching_later_edits(services):
    d,s=example(services)
    v=lab.run(services,lab.LabArgs(deck_id=d['id'],slide_id=s['id']))['variants'][1]
    args=lab.LabArgs(deck_id=d['id'],variant_id=v['id'],action='apply')
    tool=TOOLS_BY_NAME['deck_visual_lab'];before=tool.capture(services,args)
    result=tool.run(services,args)
    track=tool.track(args,result,ctx=services)
    record={**track,'before':before}
    assert tool.undo(services,record)['restored_slide']==s['id']
    assert decks.get_slide(services,d['id'],s['id'])['layout']==s['layout']


def test_real_render_native_image_and_explicit_paired_baseline(services):
    d,s=example(services)
    variants=lab.run(services,lab.LabArgs(deck_id=d['id'],slide_id=s['id'],styles=['original','focus']))['variants']
    ids=[v['id'] for v in variants]
    with pytest.raises(CiceroError,match='baseline_id'):
        lab.run(services,lab.LabArgs(deck_id=d['id'],action='benchmark',variant_ids=ids))
    result=lab.run(services,lab.LabArgs(deck_id=d['id'],action='benchmark',variant_ids=ids,baseline_id=ids[0],include_image=True))
    assert result['_image']['mime']=='image/png' and len(result['_image']['data'])>1000
    assert all(Path(v['png_path']).is_file() for v in result['ranked'])
    assert next(p for p in result['paired'] if p['id']==ids[0])['score_delta']==0
    assert 'No universal' in result['scope']
    assert all('_image' not in v for v in result['ranked'])
    reviewed=lab.run(services,lab.LabArgs(deck_id=d['id'],action='critique',variant_id=ids[0],include_image=True))
    assert reviewed['_image']['mime']=='image/png'
    assert '_image' not in reviewed['measured']


def test_comparison_rejects_unpaired_slides(services):
    d,s=example(services)
    other=decks.add_slide(services,d['id'],title='Other',blocks=[{'type':'text','text':'Other'}])
    ids=[lab.run(services,lab.LabArgs(deck_id=d['id'],slide_id=x))['variants'][0]['id'] for x in (s['id'],other['id'])]
    with pytest.raises(CiceroError,match='same slide'):lab.run(services,lab.LabArgs(deck_id=d['id'],action='compare',variant_ids=ids))


def test_bundled_runtime_has_no_structural_closing_tags(services):
    from cicero_hoard.presentation import start,StartArgs,audience_document
    d=new_deck(services)
    decks.add_slide(services,d['id'],title='Scene',blocks=[{'type':'scene3d','objects':[{'id':'one'}]}])
    preview=services.preview_html(d['id'],mode='present')
    assert preview.count('</body>')==1
    room=start(services,StartArgs(deck_id=d['id']))
    audience=audience_document(services,d['id'],room['session_id'])
    assert audience.count('const contentVersion=')==1
    assert audience.count('</body>')==1


def test_chart_entrances_wait_for_activation_and_replay(services):
    import tempfile
    from playwright.sync_api import sync_playwright
    from cicero_hoard import visual_review as vr
    d=new_deck(services)
    decks.add_slide(services,d['id'],title='Start',layout='freeform',blocks=[{'type':'scene3d','objects':[{'id':'one'}],
        'camera_path':[{'time':0,'position':[6,5,8]},{'time':10,'position':[-6,5,8]}]}])
    decks.add_slide(services,d['id'],title='Animated evidence',blocks=[{'type':'chart','chart':'bar','animation':'series','categories':['A','B'],
        'series':[{'name':'Value','values':[12,20]}],'animation_ms':100,
        'states':[{'categories':['A','B'],'series':[{'name':'Value','values':[30,40]}]}]}])
    with sync_playwright() as p,tempfile.TemporaryDirectory() as profile:
        context=vr._launch(p,profile)
        try:
            page=context.new_page();page.emulate_media(reduced_motion='no-preference');page.set_content(services.preview_html(d['id'],mode='present'),wait_until='load')
            page.wait_for_function("document.querySelector('[data-chart]').closest('section').classList.contains('future')")
            chart=page.locator('[data-chart]')
            assert chart.get_attribute('data-animation-activation') is None
            assert chart.locator('svg').count()==1
            page.wait_for_function("document.querySelector('.scene3d').dataset.ready==='true'")
            page.evaluate('deck.slide(1)')
            page.wait_for_function("document.querySelector('[data-chart]').dataset.animationActivation==='1'")
            import json
            camera=json.loads(page.locator('.scene3d').get_attribute('data-camera'))
            page.evaluate('deck.slide(0)')
            page.wait_for_function("document.querySelector('[data-chart]').closest('section').classList.contains('future')")
            page.evaluate('deck.slide(1)')
            page.wait_for_function("document.querySelector('[data-chart]').dataset.animationActivation==='2'")
            assert chart.get_attribute('data-animation-ready')=='true'
            page.wait_for_timeout(400)
            assert chart.get_attribute('data-state')=='0'
            page.wait_for_function("document.querySelector('[data-chart]').dataset.state==='1'")
            page.evaluate('deck.slide(0)')
            page.evaluate('deck.slide(1); queueMicrotask(()=>{deck.slide(0);queueMicrotask(()=>deck.slide(1))})')
            page.wait_for_function("document.querySelector('[data-chart]').dataset.animationReady==='true'&&document.querySelector('[data-chart]').dataset.state==='0'")
            page.wait_for_timeout(200)
            assert chart.get_attribute('data-animation-activation')=='3'
            frame=page.locator('.scene3d').get_attribute('data-frame')
            page.evaluate('deck.slide(0)')
            page.wait_for_function("document.querySelector('.scene3d').dataset.frame!=="+repr(frame))
            resumed=json.loads(page.locator('.scene3d').get_attribute('data-camera'))
            assert abs(resumed[0]-camera[0])<.5
        finally:context.close()


def test_png_requires_render_and_websocket_errors_recover(client):
    d,s=example(client.svc)
    v=lab.run(client.svc,lab.LabArgs(deck_id=d['id'],slide_id=s['id']))['variants'][0]
    assert client.get(f"/api/decks/{d['id']}/visual-lab/{v['id']}.png").status_code==404
    with client.websocket_connect(f"ws://127.0.0.1/api/decks/{d['id']}/slides/{s['id']}/collaboration") as ws:
        assert ws.receive_json()['engine']=='Yjs CRDT'
        ws.send_json({'action':'invalid'});assert 'error' in ws.receive_json()
        ws.send_json({'action':'presence','actor':'first'});assert ws.receive_json()['presence'][0]['actor']=='first'
