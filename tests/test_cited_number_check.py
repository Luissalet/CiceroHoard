from cicero_hoard.check import check_deck


def test_template_or_brief_cannot_validate_number_missing_from_cited_source():
    slide = {'id':'one','position':1,'layout':'chart','title':'Result 123.45',
             'sources':[1],'notes':'Speaker notes','status':'draft',
             'blocks':[{'type':'chart','chart':'bar','categories':['A'],
                        'series':[{'name':'RMSE','values':[123.45]}]}]}
    deck = {'title':'Test','brief':'123.45','language':'en','slides':[slide]}
    sources = [{'id':1,'text':'Measured RMSE 3.49'}, {'id':2,'text':'Template dummy 123.45'}]
    issues = check_deck(deck, sources, lambda _:None)
    assert {'unsourced_numbers','unsourced_chart'} <= {i['kind'] for i in issues}
    slide['blocks'][0]['series'][0]['values']=[3.49]
    slide['title']='Result 3.49'
    issues = check_deck(deck, sources, lambda _:None)
    assert not {'unsourced_numbers','unsourced_chart'} & {i['kind'] for i in issues}
