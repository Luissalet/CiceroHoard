import threading
import pytest
from cicero_hoard import data_links as dl, datasets, decks
from cicero_hoard.errors import RevisionConflict
from cicero_hoard.presentation import start, state, StartArgs, StateArgs
from conftest import new_deck


def setup(services, tmp_path, **changes):
    services.data_link_lock = threading.RLock()
    deck = new_deck(services)
    path = tmp_path / 'feed.csv'
    path.write_text('Region,Value\nNorth,12.5\nSouth,20\n', encoding='utf-8')
    link = dl.create(services, dl.LinkArgs(deck_id=deck['id'], path=str(path), **changes))
    slide = decks.add_slide(services, deck['id'], title='Values', blocks=[{'type':'text','text':'Keep'}], notes='Private notes')
    result = dl.bind(services, dl.BindArgs(deck_id=deck['id'], link_id=link['link_id'], slide_id=slide['id'], block_index=1,
                    mapping={'category_column':'Region','series_columns':['Value']}, expected_revision=1))
    return deck, path, link, result['slide']


def test_refresh_snapshot_and_bound_recipe_keep_notes_style_and_history(services, tmp_path):
    deck, path, link, slide = setup(services, tmp_path)
    before = datasets.load(services, deck['id'], link['source_id'])
    blocks = slide['blocks'];blocks[1]['frame']=[0,0,.8,.7]
    decks.patch_slide(services, deck['id'], slide['id'], {'blocks':blocks})
    path.write_text('Region,Value\nNorth,18.5\nSouth,21\n', encoding='utf-8')
    result = dl.refresh(services, deck['id'], link['link_id'])
    assert result['changed'] and result['bindings'][0]['changed']
    updated = decks.get_slide(services,deck['id'],slide['id'])
    assert updated['blocks'][1]['series'][0]['values']==[18.5,21]
    assert updated['blocks'][1]['frame']==[0,0,.8,.7]
    assert updated['notes']=='Private notes' and updated['blocks'][0]['text']=='Keep'
    assert datasets.load(services,deck['id'],link['source_id'])==before
    revision=updated['revision']
    result=dl.refresh(services,deck['id'],link['link_id'])
    assert not result['changed'] and not result['bindings'][0]['changed']
    assert decks.get_slide(services,deck['id'],slide['id'])['revision']==revision


def test_error_retains_last_good_and_manual_data_edit_not_overwritten(services,tmp_path):
    deck,path,link,slide=setup(services,tmp_path)
    path.unlink()
    result=dl.refresh(services,deck['id'],link['link_id'])
    assert result['retained_last_good'] and result['source_id']==link['source_id']
    blocks=slide['blocks'];blocks[1]['series'][0]['values'][0]=999
    decks.patch_slide(services,deck['id'],slide['id'],{'blocks':blocks})
    path.write_text('Region,Value\nNorth,7\nSouth,8\n',encoding='utf-8')
    result=dl.refresh(services,deck['id'],link['link_id'])
    assert 'edited manually' in result['bindings'][0]['error']
    assert decks.get_slide(services,deck['id'],slide['id'])['blocks'][1]['series'][0]['values'][0]==999
    assert dl.inspect(services,dl.RefArgs(deck_id=deck['id']))['items'][0]['bindings'][0]['error']


def test_notes_only_save_preserves_feed_and_stale_visual_edit_conflicts(services, tmp_path):
    from cicero_hoard.agent_tools import call_tool
    deck, path, link, old = setup(services, tmp_path, enabled=False)
    path.write_text('Region,Value\nNorth,99\nSouth,20\n', encoding='utf-8')
    dl.refresh(services, deck['id'], link['link_id'])
    with pytest.raises(RevisionConflict):
        call_tool(services, 'slide_update', {'deck_id':deck['id'], 'slide_id':old['id'],
            'blocks':old['blocks'], 'expected_revision':old['revision']}, cap=False)
    saved = call_tool(services, 'slide_update', {'deck_id':deck['id'], 'slide_id':old['id'], 'notes':'New notes'}, cap=False)
    assert saved['blocks'][1]['series'][0]['values'][0] == 99
    path.write_text('Region,Value\nNorth,101\nSouth,20\n', encoding='utf-8')
    refreshed = dl.refresh(services, deck['id'], link['link_id'])
    assert not refreshed['bindings'][0].get('error')
    latest = decks.get_slide(services, deck['id'], old['id'])
    assert latest['notes'] == 'New notes'
    assert latest['blocks'][1]['series'][0]['values'][0] == 101


def test_group_recipe_pause_resume_unlink_preserves_snapshot(services,tmp_path):
    deck,path,link,slide=setup(services,tmp_path,enabled=False,interval_s=.01)
    dl.bind(services,dl.BindArgs(deck_id=deck['id'],link_id=link['link_id'],slide_id=slide['id'],block_index=1,
        mapping={'category_column':'Region','series_columns':['Mean']},
        transform={'group_by':['Region'],'aggregations':[{'column':'Value','operation':'mean','name':'Mean'}]}))
    path.write_text('Region,Value\nNorth,2\nNorth,6\nSouth,8\n',encoding='utf-8')
    worker=dl.Worker(services);worker.tick()
    assert decks.get_slide(services,deck['id'],slide['id'])['blocks'][1]['series'][0]['values']==[12.5,20]
    dl.control(services,dl.ControlArgs(deck_id=deck['id'],link_id=link['link_id'],action='resume'))
    services.db.execute('UPDATE data_links SET checked_ts=NULL WHERE id=?',(link['link_id'],))
    worker.tick()
    updated=decks.get_slide(services,deck['id'],slide['id'])
    assert updated['blocks'][1]['series'][0]['values']==[4,8]
    count=services.db.one('SELECT count(*) c FROM sources')['c']
    dl.control(services,dl.ControlArgs(deck_id=deck['id'],link_id=link['link_id'],action='unlink'))
    assert not dl.inspect(services,dl.RefArgs(deck_id=deck['id']))['items']
    assert services.db.one('SELECT count(*) c FROM sources')['c']==count
    assert decks.get_slide(services,deck['id'],slide['id'])==updated


def test_live_session_adopts_only_automatic_data_changes(services,tmp_path):
    deck,path,link,slide=setup(services,tmp_path)
    initial=start(services,StartArgs(deck_id=deck['id']))
    path.write_text('Region,Value\nNorth,7\nSouth,8\n',encoding='utf-8')
    dl.refresh(services,deck['id'],link['link_id'])
    current=state(services,StateArgs(deck_id=deck['id']))
    assert current['content_version']==initial['content_version']+1
    assert current['slide_index']==initial['slide_index'] and current['session_id']==initial['session_id']
    decks.patch_slide(services,deck['id'],slide['id'],{'title':'Manual change'})
    with pytest.raises(RevisionConflict):state(services,StateArgs(deck_id=deck['id']))


def test_bind_stale_revision_and_deleted_block_report_conflict(services,tmp_path):
    deck,path,link,slide=setup(services,tmp_path)
    with pytest.raises(RevisionConflict):dl.bind(services,dl.BindArgs(deck_id=deck['id'],link_id=link['link_id'],slide_id=slide['id'],
        mapping={'category_column':'Region','series_columns':['Value']},expected_revision=1))
    decks.patch_slide(services,deck['id'],slide['id'],{'blocks':slide['blocks'][:1]})
    path.write_text('Region,Value\nNorth,7\nSouth,8\n',encoding='utf-8')
    assert 'removed' in dl.refresh(services,deck['id'],link['link_id'])['bindings'][0]['error']


def test_long_refresh_history_keeps_current_citations_bounded_without_losing_manual_sources(services,tmp_path):
    deck,path,link,slide=setup(services,tmp_path)
    manual=decks.add_source_text(services,deck['id'],'Manual citation','Manual evidence')
    decks.patch_slide(services,deck['id'],slide['id'],{'sources':[manual['id'],*slide['sources']]})
    for i in range(52):
        path.write_text(f'Region,Value\nNorth,{i}\nSouth,8\n',encoding='utf-8')
        result=dl.refresh(services,deck['id'],link['link_id'])
        assert not result['bindings'][0].get('error')
    updated=decks.get_slide(services,deck['id'],slide['id'])
    assert updated['sources']==[manual['id'],result['source_id']]
    from cicero_hoard.models import SlidePatch
    SlidePatch(sources=updated['sources'],blocks=updated['blocks'])
    assert services.db.one('SELECT count(*) c FROM sources')['c']>=53


def test_linked_append_respects_slide_block_contract(services,tmp_path):
    deck,path,link,slide=setup(services,tmp_path)
    blocks=[{'type':'text','text':str(i)} for i in range(8)]
    decks.patch_slide(services,deck['id'],slide['id'],{'blocks':blocks})
    from cicero_hoard.errors import CiceroError
    with pytest.raises(CiceroError):dl.bind(services,dl.BindArgs(deck_id=deck['id'],link_id=link['link_id'],slide_id=slide['id'],block_index=8,
        mapping={'category_column':'Region','series_columns':['Value']}))


def test_static_chart_added_after_binding_keeps_its_original_citation(services,tmp_path):
    deck,path,link,slide=setup(services,tmp_path)
    static=datasets.visual(services,datasets.VisualArgs(deck_id=deck['id'],source_id=link['source_id'],
        category_column='Region',series_columns=['Value']))
    decks.patch_slide(services,deck['id'],slide['id'],{'blocks':[*slide['blocks'],static['block']],
        'sources':slide['sources']})
    path.write_text('Region,Value\nNorth,99\nSouth,8\n',encoding='utf-8')
    result=dl.refresh(services,deck['id'],link['link_id'])
    updated=decks.get_slide(services,deck['id'],slide['id'])
    assert updated['blocks'][1]['series'][0]['values'][0]==99
    assert updated['blocks'][2]['series'][0]['values'][0]==12.5
    assert updated['sources']==[link['source_id'],result['source_id']]
