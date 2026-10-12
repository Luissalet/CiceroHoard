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


def test_comparison_rejects_unpaired_slides(services):
    d,s=example(services)
    other=decks.add_slide(services,d['id'],title='Other',blocks=[{'type':'text','text':'Other'}])
    ids=[lab.run(services,lab.LabArgs(deck_id=d['id'],slide_id=x))['variants'][0]['id'] for x in (s['id'],other['id'])]
    with pytest.raises(CiceroError,match='same slide'):lab.run(services,lab.LabArgs(deck_id=d['id'],action='compare',variant_ids=ids))


def test_png_requires_render_and_websocket_errors_recover(client):
    d,s=example(client.svc)
    v=lab.run(client.svc,lab.LabArgs(deck_id=d['id'],slide_id=s['id']))['variants'][0]
    assert client.get(f"/api/decks/{d['id']}/visual-lab/{v['id']}.png").status_code==404
    with client.websocket_connect(f"ws://127.0.0.1/api/decks/{d['id']}/slides/{s['id']}/collaboration") as ws:
        assert ws.receive_json()['engine']=='Yjs CRDT'
        ws.send_json({'action':'invalid'});assert 'error' in ws.receive_json()
        ws.send_json({'action':'presence','actor':'first'});assert ws.receive_json()['presence'][0]['actor']=='first'
