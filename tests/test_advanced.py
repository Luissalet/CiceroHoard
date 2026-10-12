import sqlite3
from copy import deepcopy
import pytest
from pydantic import ValidationError
from cicero_hoard import advanced as a,connectors,decks,data_links as dl,datasets
from cicero_hoard.errors import CiceroError
from cicero_hoard.models import Scene3DBlock,ChartBlock
from conftest import new_deck


def test_poll_rounds_vote_replace_close_and_recover(services):
    d=new_deck(services);did=d['id']
    p=a.poll(services,a.PollArgs(deck_id=did,action='create',question='Which?',options=['A','B']))
    def call(action,**kw):return a.poll(services,a.PollArgs(deck_id=did,poll_id=p['id'],action=action,**kw))
    assert call('vote',participant='a',choice=0)['counts']==[1,0]
    assert call('vote',participant='a',choice=1)['counts']==[0,1]
    assert call('vote',participant='b',choice=1)['total']==2
    call('close')
    with pytest.raises(CiceroError,match='closed'):call('vote',participant='c',choice=0)
    call('open');assert call('reset')['total']==0
    rounds=call('rounds')['rounds'];assert rounds[0]['total']==2
    call('vote',participant='a',choice=0)
    assert call('restore',round_id=rounds[0]['id'])['counts']==[1,1]
    assert call('block')['block']['results']==[1,1]


def test_poll_wrong_deck_and_invalid_choices(services):
    d=new_deck(services)
    with pytest.raises(CiceroError):a.poll(services,a.PollArgs(deck_id=d['id'],action='create',question='Which?',options=['A']))
    p=a.poll(services,a.PollArgs(deck_id=d['id'],action='create',question='Which?',options=['A','B']))
    other=new_deck(services)
    with pytest.raises(CiceroError):a.poll_state(services,other['id'],p['id'])
    with pytest.raises(CiceroError):a.poll(services,a.PollArgs(deck_id=d['id'],poll_id=p['id'],action='vote',participant='p',choice=2))


def test_real_yjs_concurrent_text_edits_and_manual_notes_preserved(services):
    d=new_deck(services);s=decks.add_slide(services,d['id'],title='AB',notes='Original',blocks=[{'type':'text','text':'Keep'}])
    args={'deck_id':d['id'],'slide_id':s['id']}
    initial=a.collaboration(services,a.CollaborationArgs(**args))
    s=decks.get_slide(services,d['id'],s['id'])
    left=a.merge_document(initial['state'],{},patches={'title':'L AB'})
    right=a.merge_document(initial['state'],{},patches={'title':'AB R'})
    a.collaboration(services,a.CollaborationArgs(**args,action='apply',update=left['state'],actor='left'))
    result=a.collaboration(services,a.CollaborationArgs(**args,action='apply',update=right['state'],actor='right'))
    assert result['snapshot']['title']=='L AB R'
    assert len(result['presence'])==2
    decks.patch_slide(services,d['id'],s['id'],{'notes':'Later manual note'})
    result=a.collaboration(services,a.CollaborationArgs(**args,action='apply',patches={'subtitle':'New subtitle'}))
    assert result['snapshot']['notes']=='Later manual note'
    assert decks.get_slide(services,d['id'],s['id'])['blocks']==s['blocks']


def test_local_sql_snapshot_refresh_preserves_animation(services,tmp_path):
    d=new_deck(services);path=tmp_path/'source.sqlite'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE data(region TEXT,value REAL)');db.executemany('INSERT INTO data VALUES(?,?)',[('A',12),('B',20)])
    link=connectors.create(services,connectors.ConnectorArgs(deck_id=d['id'],kind='database',database_url='sqlite:///'+path.as_posix(),query='SELECT region,value FROM data',interval_s=10000))
    assert link['source_id'];dl.control(services,dl.ControlArgs(deck_id=d['id'],link_id=link['link_id'],action='pause'))
    saved=deepcopy(datasets.load(services,d['id'],link['source_id']))
    s=decks.add_slide(services,d['id'],title='Local values',blocks=[])
    bound=dl.bind(services,dl.BindArgs(deck_id=d['id'],link_id=link['link_id'],slide_id=s['id'],block_index=0,mapping={'category_column':'region','series_columns':['value']}))['slide']
    blocks=bound['blocks'];blocks[0].update(animation='update',animation_ms=1400,frame=[0,0,1,.8],action={'kind':'next'})
    decks.patch_slide(services,d['id'],s['id'],{'blocks':blocks})
    with sqlite3.connect(path) as db:db.execute('UPDATE data SET value=value+5')
    dl.refresh(services,d['id'],link['link_id'])
    updated=decks.get_slide(services,d['id'],s['id'])['blocks'][0]
    assert updated['series'][0]['values']==[17,25]
    assert updated['animation']=='update' and updated['animation_ms']==1400 and updated['action']=={'kind':'next'}
    assert datasets.load(services,d['id'],link['source_id'])==saved
    with pytest.raises(CiceroError):connectors.read(services,d['id'],{'adapter':{'kind':'database','database_url':'sqlite:///'+path.as_posix(),'query':'DELETE FROM data'}})
    with sqlite3.connect(path) as db:assert db.execute('SELECT count(*) FROM data').fetchone()[0]==2


def test_scene_and_state_validation():
    scene=Scene3DBlock(objects=[{'id':'one','shape':'sphere'}]);assert scene.camera_path[0].time==0
    with pytest.raises(ValidationError):Scene3DBlock(objects=[{'id':'one'},{'id':'one'}])
    with pytest.raises(ValidationError):Scene3DBlock(objects=[{'id':'one'}],camera_path=[{'time':2,'position':[1,2,3]},{'time':1,'position':[2,3,4]}])
    with pytest.raises(ValidationError):ChartBlock(chart='bubble',categories=['A'],series=[{'name':'A','values':[1],'x_values':[2],'sizes':[3]}],states=[{'categories':['A'],'series':[{'name':'A','values':[1]}]}])


def test_invalid_collaborative_blocks_do_not_persist(services):
    d=new_deck(services);s=decks.add_slide(services,d['id'],title='Valid',blocks=[{'type':'text','text':'Keep'}])
    args={'deck_id':d['id'],'slide_id':s['id']}
    state=a.collaboration(services,a.CollaborationArgs(**args))
    s=decks.get_slide(services,d['id'],s['id'])
    invalid=a.merge_document(state['state'],{},patches={'blocks':[{'type':'text','text':7}]})
    for kwargs in ({'patches':{'blocks':[{'type':'text','text':7}]}},{'update':invalid['state']}):
        with pytest.raises(ValidationError):a.collaboration(services,a.CollaborationArgs(**args,action='apply',**kwargs))
        assert decks.get_slide(services,d['id'],s['id'])['blocks']==s['blocks']
        assert a.collaboration(services,a.CollaborationArgs(**args))['snapshot']['blocks']==s['blocks']


@pytest.mark.parametrize('poster_kind',['missing','audio'])
def test_real_scene_poster_and_native_poll_snapshot(services,monkeypatch,poster_kind):
    from PIL import Image,ImageStat
    import io
    d=new_deck(services)
    lookup=services.assets_lookup()
    if poster_kind=='audio':
        monkeypatch.setattr(services,'assets_lookup',lambda:lambda aid:({'mime':'audio/wav','deck_id':d['id']} if aid=='missing-poster' else lookup(aid)))
    p=a.poll(services,a.PollArgs(deck_id=d['id'],action='create',question='Local poll',options=['A','B']))
    block=a.poll(services,a.PollArgs(deck_id=d['id'],poll_id=p['id'],action='block'))['block']
    s=decks.add_slide(services,d['id'],title='Scene',layout='freeform',blocks=[{'type':'scene3d','poster_id':'missing-poster','objects':[{'id':'one','shape':'sphere','color':'#D13E54'}],'frame':[0,0,.65,1]},block])
    converted=a.static_deck(services,decks.deck_view(services,d['id']))
    image=converted['slides'][0]['blocks'][0]
    assert image['type']=='image' and converted['slides'][0]['blocks'][1]['type']=='table'
    asset=services.assets_lookup()(image['asset_id'])
    png=Image.open(asset['path']).convert('RGB')
    assert max(ImageStat.Stat(png).stddev)>10
    assert decks.get_slide(services,d['id'],s['id'])['blocks'][0]['type']=='scene3d'
