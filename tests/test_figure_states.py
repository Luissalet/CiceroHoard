"""Identical pixels can represent different authored states of the same revision."""
from copy import deepcopy
import pytest

from conftest import new_deck
from test_figures import bundle, encoded
from cicero_hoard import figures
from cicero_hoard.errors import CiceroError


def state_bundle(state='closed'):
    value=bundle()
    value.update(page_id=None,state_id=state)
    value['content']['diagram']={'type':'isometric','nodes':[], 'pieces':[
        {'id':'base','kind':'slab','plan':{'x':0,'y':0,'w':80,'d':50},'z':0,'h':8}]}
    value['content']['mechanism']={'parts':[], 'states':[
        {'id':'closed','title':'Cerrado','poses':{},'hidden':[]},
        {'id':'open','title':'Abierto','poses':{},'hidden':[]}]}
    return value


def test_same_pixels_and_source_keep_distinct_captured_states(services):
    deck=new_deck(services)
    closed=figures.import_bytes(services,deck['id'],encoded(state_bundle()))
    opened=figures.import_bytes(services,deck['id'],encoded(state_bundle('open')))
    assert closed['asset_id']!=opened['asset_id']
    assert figures.import_bytes(services,deck['id'],encoded(state_bundle()))['asset_id']==closed['asset_id']
    for state,row in [('closed',closed),('open',opened)]:
        assert figures.get(services,figures.GetArgs(asset_id=row['asset_id'],include_preview=True))['figure']==state_bundle(state)
    assert len(services.db.query('SELECT id FROM assets'))==2


def test_state_source_download_retains_exact_captured_selection(client):
    deck=client.post('/api/decks',json={'title':'Estados sintéticos'}).json()
    source=state_bundle('open')
    imported=client.post(f'/api/decks/{deck["id"]}/assets',files={'file':('state.vfigure',encoded(source),'application/json')})
    assert imported.status_code==201,imported.text
    aid=imported.json()['asset_id']
    # Subsequent caller-side changes do not rewrite the imported snapshot.
    later=deepcopy(source);later['content']['mechanism']['states'][1]['title']='Cambio posterior'
    assert client.get(f'/api/assets/{aid}/source?download=true').json()==source
    result=figures.get(client.svc,figures.GetArgs(asset_id=aid))['figure']
    assert result['state_id']=='open' and result['revision']==1


@pytest.mark.parametrize('patch',[
    {'state_id':'missing'}, {'state_id':''}, {'state_id':'open','page_id':'detail'},
    {'content':{'diagram':{'type':'flowchart','nodes':[]}}},
    {'content':{'diagram':{'type':'isometric','nodes':[]},'mechanism':{'states':None}}},
])
def test_invalid_state_selection_does_not_create_assets(services,patch):
    deck=new_deck(services)
    with pytest.raises(CiceroError):figures.import_bytes(services,deck['id'],encoded({**state_bundle(),**patch}))
    assert not services.db.query('SELECT id FROM assets')


def test_legacy_figure_serialization_has_no_new_null_key(services):
    deck=new_deck(services)
    imported=figures.import_bytes(services,deck['id'],encoded(bundle()))
    assert figures.get(services,figures.GetArgs(asset_id=imported['asset_id'],include_preview=True))['figure']==bundle()
