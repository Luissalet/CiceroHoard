import copy
import pytest
from cicero_hoard.rehearsal import rehearsal_plan, spoken_notes
from cicero_hoard.errors import CiceroError
from cicero_hoard import agent_tools, decks


def _deck(notes):
    return {'id':'fixture','slides':[{'id':f's{i}','position':i+1,'title':f'Slide {i+1}','notes':n} for i,n in enumerate(notes)]}


def test_support_excluded_exact_clock_and_repeat_is_read_only():
    d=_deck(['hello '*60,'hola '*60,'backup '*2000]);before=copy.deepcopy(d)
    p=rehearsal_plan(d,duration_minutes=2,words_per_minute=120,pause_seconds=5,main_slides=2)
    assert p['estimated_seconds']==70 and p['remaining_seconds_estimate']==50
    assert p['timeline'][0]['start']=='00:00' and p['timeline'][-1]['end']=='02:00'
    assert p['support_slides']==1 and sum(s['slot_seconds'] for s in p['timeline'])==120
    assert p['actual_elapsed_seconds'] is None
    assert rehearsal_plan(d,duration_minutes=2,words_per_minute=120,pause_seconds=5,main_slides=2)==p
    assert d==before


def test_schedule_does_not_hide_overlong_speech():
    p=rehearsal_plan(_deck(['word '*300]),duration_minutes=1,words_per_minute=100,pause_seconds=0)
    assert p['estimated_seconds']==180 and p['planned_seconds']==60
    assert p['fits_estimate'] is False and p['remaining_seconds_estimate']==-120


def test_missing_notes_are_not_zero_length_measured_speech():
    p=rehearsal_plan(_deck(['Known note','']),main_slides=2)
    assert p['estimated_seconds'] is None and p['fits_estimate'] is None
    assert p['missing_notes']==['s1'] and p['actual_elapsed_seconds'] is None
    citation_only=rehearsal_plan(_deck(['(PDF p.7)']))
    assert citation_only['missing_notes']==['s0'] and citation_only['estimated_seconds'] is None


def test_citations_are_excluded_but_spoken_parentheses_remain():
    assert spoken_notes('Say this (an estimate). (75 s; PDF pp.70–71)')=='Say this (an estimate).'
    assert spoken_notes('Hola. (p. 7)')=='Hola.'
    assert spoken_notes('Hello\nSource: report p.7')=='Hello'


@pytest.mark.parametrize('notes,count',[([],None),(['x'],2),(['x'],0)])
def test_invalid_selection_is_not_silently_clamped(notes,count):
    with pytest.raises(CiceroError):rehearsal_plan(_deck(notes),main_slides=count)


def test_real_tool_never_changes_notes_revisions_or_approvals(services,deck):
    before=decks.deck_view(services,deck['id'])
    result=agent_tools.call_tool(services,'deck_rehearsal',{'deck_id':deck['id'],'main_slides':1,'duration_minutes':1})
    assert result['timeline'][0]['slide_id']==before['slides'][0]['id']
    assert decks.deck_view(services,deck['id'])==before
