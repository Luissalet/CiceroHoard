import json,tempfile
from copy import deepcopy
from playwright.sync_api import sync_playwright
from cicero_hoard import decks,visual_review as vr
from conftest import new_deck

KINDS=['bar','bar_horizontal','line','area','pie','donut','scatter','bubble','dot','dumbbell','band','heatmap','waterfall','funnel']

def block(kind):
    series=[{'name':'Observed','values':[12,None,20]}]
    if kind in ('scatter','bubble','band'):series[0]['x_values']=[0,3,11]
    if kind=='bubble':series[0]['sizes']=[4,9,16]
    if kind=='band':series[0].update(lower=[8,None,16],upper=[15,None,24])
    if kind=='dumbbell':series.append({'name':'Proposed','values':[10,None,15]})
    if kind=='waterfall':series[0]['values']=[12,None,-4]
    states=deepcopy(series)
    for s in states:s['values']=[v+1 if v is not None else None for v in s['values']]
    return {'type':'chart','chart':kind,'categories':['A','Missing','C'],'series':series,'unit':'kg',
            'animation':'points','animation_ms':100,'states':[{'categories':['A','Missing','C'],'series':states}]}

def test_all_fourteen_chart_types_activate_update_and_keep_gaps(services):
    d=new_deck(services)
    for kind in KINDS:decks.add_slide(services,d['id'],title=kind,blocks=[block(kind)])
    with sync_playwright() as p,tempfile.TemporaryDirectory() as profile:
        context=vr._launch(p,profile)
        try:
            page=context.new_page();page.emulate_media(reduced_motion='no-preference');errors=[]
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.set_content(services.preview_html(d['id']),wait_until='load')
            page.wait_for_timeout(150);assert not errors,errors
            page.wait_for_function("Array.from(document.querySelectorAll('[data-chart]')).every(el=>el.dataset.animationReady==='true')")
            assert page.locator('[data-chart] svg').count()==14
            before=page.locator('[data-chart]').nth(9).inner_html()
            page.wait_for_function("Array.from(document.querySelectorAll('[data-chart]')).every(el=>el.dataset.state==='1')")
            page.wait_for_timeout(350)
            assert page.locator('[data-chart]').nth(9).inner_html()!=before
            assert not errors
            for i,kind in enumerate(KINDS):
                el=page.locator('[data-chart]').nth(i)
                assert el.get_attribute('data-animation-activation')=='1'
                assert el.locator('svg path,svg circle,svg rect').count()>1
                assert len(el.locator('svg').inner_html())>200
                if kind=='band':assert 'Missing' not in el.locator('svg').text_content()
            page.emulate_media(reduced_motion='reduce');page.set_content(services.preview_html(d['id']),wait_until='load')
            assert page.locator('[data-chart] svg').count()==14
            assert all(page.locator('[data-chart]').nth(i).get_attribute('data-animation-ready') is None for i in range(14))
        finally:context.close()

