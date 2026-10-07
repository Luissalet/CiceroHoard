import pytest
from cicero_hoard import agent_tools, decks
from cicero_hoard.errors import CiceroError


def test_one_bullet_edit_keeps_chart_and_other_bullets(services, deck):
    chart={'type':'chart','chart':'bar','categories':['A'], 'series':[{'name':'Bias','values':[3.64]}]}
    slide=decks.add_slide(services,deck['id'],title='Bias',blocks=[chart,{'type':'bullets','items':['First','Second','Third']}],notes='Kept notes')
    result=agent_tools.call_tool(services,'slide_edit_text',{'deck_id':deck['id'],'slide_id':slide['id'],
                                    'field':'bullet','block_index':1,'item_index':1,'text':'Corrected'})
    assert result['blocks'][0] == slide['blocks'][0]
    assert result['blocks'][1]['items'] == ['First','Corrected','Third']
    assert result['notes'] == 'Kept notes' and result['revision'] == 2


def test_invalid_target_changes_nothing(services, deck):
    slide=decks.add_slide(services,deck['id'],title='Text',blocks=[{'type':'text','text':'Body'}])
    with pytest.raises(CiceroError):
        agent_tools.call_tool(services,'slide_edit_text',{'deck_id':deck['id'],'slide_id':slide['id'],
                                              'field':'bullet','block_index':0,'item_index':0,'text':'Wrong'})
    assert decks.get_slide(services,deck['id'],slide['id']) == slide


def test_notes_edit_preserves_title_and_blocks(services, deck):
    slide=decks.add_slide(services,deck['id'],title='Title',blocks=[{'type':'bullets','items':['Keep']}])
    result=agent_tools.call_tool(services,'slide_edit_text',{'deck_id':deck['id'],'slide_id':slide['id'],
                                              'field':'notes','text':'Correct notes'})
    assert result['title'] == 'Title' and result['blocks'] == slide['blocks']
    assert result['notes'] == 'Correct notes'
