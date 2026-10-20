"""Figure snapshots never reuse a mutable source just because pixels match."""
import base64
import json

import pytest

from conftest import png_bytes, new_deck
from cicero_hoard import decks, figures
from cicero_hoard.assets import import_file
from cicero_hoard.errors import CiceroError


def bundle(revision=1):
    return {'format':'vitruvius.figure/1','document_id':'abcdef012345','revision':revision,
            'title':'Proceso sintético','page_id':'detail',
            'content':{'diagram':{'type':'flowchart','nodes':[{'id':'n','label':'Enviar'}]}, 'view':{}},
            'origin':{'editor_url':'http://127.0.0.1:5191/design/#/diagrams?document=abcdef012345'},
            'preview':{'mime':'image/png','data':base64.b64encode(png_bytes()).decode('ascii')}}


def encoded(value):
    return json.dumps(value, ensure_ascii=False).encode('utf8')


def test_matching_pixels_with_distinct_sources_stay_immutable(services):
    deck = new_deck(services)
    first = figures.import_bytes(services, deck['id'], encoded(bundle()))
    same = figures.import_bytes(services, deck['id'], encoded(bundle()))
    assert same['asset_id'] == first['asset_id'] and same['reused']
    second = figures.import_bytes(services, deck['id'], encoded(bundle(2)))
    assert second['asset_id'] != first['asset_id']
    ordinary = decks.add_asset(services, deck['id'], png_bytes(), 'plain.png')
    assert ordinary['asset_id'] not in (first['asset_id'], second['asset_id'])
    assert decks.add_asset(services, deck['id'], png_bytes())['asset_id'] == ordinary['asset_id']
    for expected, row in ((1,first),(2,second)):
        retained = figures.get(services, figures.GetArgs(asset_id=row['asset_id'], include_preview=True))['figure']
        assert retained == bundle(expected)
    assert len(services.db.query('SELECT id FROM assets')) == 3


def test_import_source_api_and_invalid_upload_do_not_change_assets(client, tmp_path):
    deck = client.post('/api/decks', json={'title':'Figuras QA'}).json()
    endpoint = f'/api/decks/{deck["id"]}/assets'
    response = client.post(endpoint, files={'file':('figure.vfigure', encoded(bundle()), 'application/json')})
    assert response.status_code == 201, response.text
    asset = response.json()['asset_id']
    assert client.get(f'/api/assets/{asset}').content == png_bytes()
    download = client.get(f'/api/assets/{asset}/source?download=true')
    assert download.json() == bundle()
    assert '.vfigure' in download.headers['content-disposition']
    path = tmp_path / 'figure.vfigure'; path.write_bytes(encoded(bundle()))
    assert import_file(client.svc, deck['id'], str(path))['asset_id'] == asset
    count = len(client.svc.db.query('SELECT id FROM assets'))
    for bad in (b'{}', b'not json', encoded({**bundle(),'preview':{'mime':'image/png','data':'AAAA'}})):
        assert client.post(endpoint, files={'file':('bad.vfigure',bad)}).status_code == 400
    assert len(client.svc.db.query('SELECT id FROM assets')) == count


@pytest.mark.parametrize('patch', [
    {'format':'unsupported/1'}, {'revision':0}, {'content':{}},
    {'origin':{'editor_url':'javascript:alert(1)'}},
])
def test_invalid_sources_are_not_stored(services, patch):
    deck = new_deck(services)
    with pytest.raises(CiceroError):
        figures.import_bytes(services, deck['id'], encoded({**bundle(), **patch}))
    assert not services.db.query('SELECT id FROM assets')


def test_targeted_replace_and_undo_preserve_later_notes_geometry_and_other_figure(client):
    from test_agent_accountability import agent_call, ok, undo
    deck = new_deck(client.svc)
    first = figures.import_bytes(client.svc, deck['id'], encoded(bundle()))
    second = figures.import_bytes(client.svc, deck['id'], encoded(bundle(2)))
    original = decks.add_slide(client.svc, deck['id'], title='Figuras', notes='Original notes', blocks=[
        {'type':'image','asset_id':first['asset_id'],'caption':'Caption','fit':'cover','position':[0.2,0.8]},
        {'type':'image','asset_id':first['asset_id'],'caption':'Keep this one'},
        {'type':'text','text':'Unrelated text'}])
    updated = ok(agent_call(client,'slide_set_image',{'deck_id':deck['id'],'slide_id':original['id'],
                                                   'asset_id':second['asset_id']},session='figure-replace'))
    assert updated['blocks'][0]['caption'] == 'Caption' and updated['notes'] == original['notes']
    assert updated['blocks'][1:] == original['blocks'][1:]
    later = updated['blocks']; later[0]['position'] = [0.7,0.3]; later[0]['caption'] = 'Later caption'
    later[2]['text'] = 'Manual correction'
    decks.patch_slide(client.svc,deck['id'],original['id'],{'notes':'Later notes','blocks':later})
    result = ok(undo(client,'figure-replace',confirm=True))
    assert result['complete'], result
    restored = decks.get_slide(client.svc,deck['id'],original['id'])
    assert restored['notes'] == 'Later notes'
    assert restored['blocks'][0]['asset_id'] == first['asset_id']
    assert restored['blocks'][0]['caption'] == 'Later caption'
    assert restored['blocks'][0]['position'] == [0.7,0.3]
    assert restored['blocks'][1:] == later[1:]
    assert figures.get(client.svc,figures.GetArgs(asset_id=first['asset_id']))['figure']['revision'] == 1


def test_undo_does_not_overwrite_a_subsequent_image_replacement(client):
    from test_agent_accountability import agent_call, ok, undo
    deck = new_deck(client.svc)
    assets = [figures.import_bytes(client.svc,deck['id'],encoded(bundle(r)))['asset_id'] for r in (1,2,3)]
    slide = decks.add_slide(client.svc,deck['id'],blocks=[{'type':'image','asset_id':assets[0]}])
    for session, asset in zip(('earlier','later'), assets[1:]):
        ok(agent_call(client,'slide_set_image',{'deck_id':deck['id'],'slide_id':slide['id'],'asset_id':asset},session=session))
    result = ok(undo(client,'earlier',confirm=True))
    assert result['conflicts'] and not result['complete']
    assert decks.get_slide(client.svc,deck['id'],slide['id'])['blocks'][0]['asset_id'] == assets[2]


def test_image_undo_keeps_earlier_whole_slide_undo_compatible(client):
    from test_agent_accountability import agent_call, ok, undo
    deck = new_deck(client.svc)
    a,b = [figures.import_bytes(client.svc,deck['id'],encoded(bundle(r)))['asset_id'] for r in (1,2)]
    slide = decks.add_slide(client.svc,deck['id'],notes='Initial',blocks=[{'type':'image','asset_id':a}])
    ok(agent_call(client,'slide_edit_text',{'deck_id':deck['id'],'slide_id':slide['id'],'field':'notes','text':'Changed'},session='chain'))
    ok(agent_call(client,'slide_set_image',{'deck_id':deck['id'],'slide_id':slide['id'],'asset_id':b},session='chain'))
    result = ok(undo(client,'chain',confirm=True))
    assert result['complete'] and len(result['undone']) == 2, result
    restored = decks.get_slide(client.svc,deck['id'],slide['id'])
    assert restored['blocks'] == slide['blocks'] and restored['notes'] == 'Initial'
