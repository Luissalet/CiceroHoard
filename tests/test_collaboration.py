from copy import deepcopy
import pytest
from cicero_hoard import decks,advanced as a
from cicero_hoard.errors import CiceroError
from conftest import new_deck

def example(svc):
    d=new_deck(svc);s=decks.add_slide(svc,d['id'],title='AB',blocks=[
        {'id':'first','type':'text','text':'AB','frame':[0,0,.5,1]},
        {'id':'second','type':'chart','chart':'bar','categories':['A','B'],'series':[{'name':'Observed','values':[12,20]}]},
        {'id':'third','type':'text','text':'Tail'}])
    args={'deck_id':d['id'],'slide_id':s['id']};initial=a.collaboration(svc,a.CollaborationArgs(**args));return d,s,args,initial

def peer(initial,*ops):return a.merge_document(initial['state'],{},operations=list(ops))['state']

def test_two_peers_merge_object_fields_and_character_edits(services):
    d,s,args,initial=example(services)
    left=peer(initial,{'op':'text','block_id':'first','path':['text'],'index':0,'text':'L '},
        {'op':'set','block_id':'second','path':['series',0,'values',0],'value':15})
    right=peer(initial,{'op':'text','block_id':'first','path':['text'],'index':2,'text':' R'},
        {'op':'set','block_id':'second','path':['series',0,'values',1],'value':25})
    a.collaboration(services,a.CollaborationArgs(**args,action='apply',update=left))
    result=a.collaboration(services,a.CollaborationArgs(**args,action='apply',update=right))
    blocks=result['snapshot']['blocks'];assert blocks[0]['text']=='L AB R'
    assert blocks[1]['series'][0]['values']==[15,25]
    replay=a.collaboration(services,a.CollaborationArgs(**args,action='apply',update=right))
    assert replay['snapshot']==result['snapshot'] and replay['slide_revision']==result['slide_revision']

def test_concurrent_order_and_edit_preserve_shared_maps(services):
    d,s,args,initial=example(services)
    left=peer(initial,{'op':'move','block_id':'first','before_id':None})
    right=peer(initial,{'op':'set','block_id':'first','path':['frame',0],'value':.2})
    a.collaboration(services,a.CollaborationArgs(**args,action='apply',update=left))
    result=a.collaboration(services,a.CollaborationArgs(**args,action='apply',update=right))
    assert [b['id'] for b in result['snapshot']['blocks']]==['second','third','first']
    assert result['snapshot']['blocks'][-1]['frame'][0]==.2

@pytest.mark.parametrize('reverse',[False,True])
def test_delete_wins_concurrent_edit_and_explicit_restore(services,reverse):
    d,s,args,initial=example(services)
    left=peer(initial,{'op':'delete','block_id':'first'})
    right=peer(initial,{'op':'set','block_id':'first','path':['text'],'value':'Edited concurrently'})
    for state in ([right,left] if reverse else [left,right]):result=a.collaboration(services,a.CollaborationArgs(**args,action='apply',update=state))
    assert [b['id'] for b in result['snapshot']['blocks']]==['second','third']
    restored=a.collaboration(services,a.CollaborationArgs(**args,action='apply',operations=[{'op':'insert','block_id':'first','before_id':'second','value':s['blocks'][0]}]))
    assert restored['snapshot']['blocks'][0]['text']=='AB'

def test_manual_fields_and_undo_flow_into_existing_peer_document(services):
    d,s,args,initial=example(services)
    stale=peer(initial,{'op':'set','block_id':'first','path':['text'],'value':'Peer text'})
    current=decks.get_slide(services,d['id'],s['id']);blocks=deepcopy(current['blocks']);blocks[1]['series'][0]['values']=[17,27]
    decks.patch_slide(services,d['id'],s['id'],{'blocks':blocks,'notes':'Manual note'})
    result=a.collaboration(services,a.CollaborationArgs(**args,action='apply',update=stale))
    assert result['snapshot']['blocks'][1]['series'][0]['values']==[17,27] and result['snapshot']['notes']=='Manual note'
    decks.restore_slide(services,d['id'],s['id'],s,reason='undo by user')
    state=a.collaboration(services,a.CollaborationArgs(**args))
    assert state['snapshot']['blocks']==s['blocks'] and state['snapshot']['notes']==s['notes']

def test_nested_scene_object_fields_merge(services):
    d=new_deck(services);s=decks.add_slide(services,d['id'],blocks=[{'id':'scene','type':'scene3d','objects':[{'id':'x'},{'id':'y'}]}])
    args={'deck_id':d['id'],'slide_id':s['id']};initial=a.collaboration(services,a.CollaborationArgs(**args))
    left=peer(initial,{'op':'set','block_id':'scene','path':['objects',0,'position'],'value':[1,0,0]})
    right=peer(initial,{'op':'set','block_id':'scene','path':['objects',1,'position'],'value':[0,2,0]})
    a.collaboration(services,a.CollaborationArgs(**args,action='apply',update=left))
    result=a.collaboration(services,a.CollaborationArgs(**args,action='apply',update=right))
    assert [o['position'] for o in result['snapshot']['blocks'][0]['objects']]==[[1,0,0],[0,2,0]]

def test_stable_identity_migration_is_durable_and_idempotent(services):
    d=new_deck(services);s=decks.add_slide(services,d['id'],blocks=[{'type':'text','text':'Keep'}]);args={'deck_id':d['id'],'slide_id':s['id']}
    first=a.collaboration(services,a.CollaborationArgs(**args));again=a.collaboration(services,a.CollaborationArgs(**args))
    assert first['snapshot']==again['snapshot'] and first['slide_revision']==again['slide_revision']==s['revision']+1
    assert first['snapshot']['blocks'][0]['id']==decks.get_slide(services,d['id'],s['id'])['blocks'][0]['id']

def test_invalid_operations_roll_back_document_and_slide(services):
    d,s,args,initial=example(services)
    with pytest.raises(Exception):a.collaboration(services,a.CollaborationArgs(**args,action='apply',operations=[{'op':'set','block_id':'first','path':['frame',2],'value':-1}]))
    after=a.collaboration(services,a.CollaborationArgs(**args))
    assert after['snapshot']==initial['snapshot'] and after['slide_revision']==s['revision']

