import pytest
from cicero_hoard import agent_tools, decks
from cicero_hoard.errors import CiceroError


def _call(services, deck, slides, key='intro'):
    return agent_tools.call_tool(services, 'slides_add',
                                 {'deck_id': deck['id'], 'batch_key': key, 'slides': slides})


def test_batch_replay_does_not_duplicate_slides_or_revisions(services, deck):
    slides = [{'title': 'First', 'notes': '45 seconds', 'blocks': []}, {'title': 'Second'}]
    before = len(decks.deck_view(services, deck['id'])['slides'])
    first = _call(services, deck, slides)
    again = _call(services, deck, slides)
    assert first['replayed'] is False and again['replayed'] is True
    assert [s['id'] for s in first['slides']] == [s['id'] for s in again['slides']]
    assert len(decks.deck_view(services, deck['id'])['slides']) == before + 2
    assert all(s['status'] == 'draft' and s['revision'] == 1 for s in again['slides'])


def test_invalid_second_slide_rolls_back_the_entire_batch(services, deck):
    before = decks.deck_view(services, deck['id'])
    with pytest.raises(CiceroError):
        _call(services, deck, [{'title': 'Good'}, {'title': 'Bad', 'sources': [999999]}])
    assert decks.deck_view(services, deck['id']) == before
    assert services.db.one('SELECT COUNT(*) n FROM slide_batches')['n'] == 0


def test_changed_content_requires_new_key(services, deck):
    _call(services, deck, [{'title': 'First'}])
    with pytest.raises(CiceroError, match='different content'):
        _call(services, deck, [{'title': 'Changed'}])


def test_existing_approval_and_order_are_preserved(services, deck):
    existing = decks.add_slide(services, deck['id'], title='Reviewed')
    decks.set_approval(services, deck['id'], existing['id'], True)
    before = decks.deck_view(services, deck['id'])['slides']
    _call(services, deck, [{'title': 'New draft'}])
    result = decks.deck_view(services, deck['id'])['slides']
    assert [s['id'] for s in result[:-1]] == [s['id'] for s in before]
    assert next(s for s in result if s['id'] == existing['id'])['status'] == 'approved'
    assert result[-1]['title'] == 'New draft' and result[-1]['status'] == 'draft'
