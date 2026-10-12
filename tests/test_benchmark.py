from copy import deepcopy
from pathlib import Path
import pytest
from cicero_hoard import decks,benchmark as b
from cicero_hoard.export_pptx import build_pptx
from cicero_hoard.errors import CiceroError,RevisionConflict
from conftest import new_deck,png_bytes

def setup(svc,tmp_path):
    d=new_deck(svc);s=decks.add_slide(svc,d['id'],title='Measured outcome',notes='Source: synthetic fixture.',blocks=[
        {'type':'chart','chart':'bar','categories':['A','B'],'unit':'kg','series':[{'name':'Observed','values':[12,20]}]},
        {'type':'text','text':'Source: synthetic fixture.'}])
    # Unit-test fixture only. Real independent authoring is exercised separately through MCP.
    path=tmp_path/'fixture.pptx';path.write_bytes(build_pptx(decks.deck_view(svc,d['id']),assets=svc.assets_lookup()))
    def render(raw,folder):
        folder.mkdir(parents=True,exist_ok=True);(folder/'slide-1.png').write_bytes(png_bytes(1600,900))
        return {'renderer':'unit_test_rasterizer','slide_count':1,'slides':[{'position':1,'shapes':[]}]}
    svc._native_render_fn=render
    state=b.run(svc,b.BenchmarkArgs(deck_id=d['id'],action='create'))
    args={'deck_id':d['id'],'benchmark_id':state['benchmark_id']}
    case=b.run(svc,b.BenchmarkArgs(**args,action='case',case={'key':'fixture','brief':'Compare exact values and sources','baseline_path':str(path)}))
    return d,s,args,case

def test_exact_native_chart_values_categories_units_and_order(services,tmp_path):
    d,s,args,case=setup(services,tmp_path)
    assert case['baseline_fidelity']['ok'],case['baseline_fidelity']
    deck=decks.deck_view(services,d['id']);ledger=b.pptx_ledger((tmp_path/'fixture.pptx').read_bytes())
    wrong=deepcopy(ledger);wrong[0]['charts'][0][0]['values']=[20,12]
    assert not b.fidelity(deck['slides'],wrong)['ok']
    wrong=deepcopy(ledger);wrong[0]['charts'][0][0]['categories']=['B','A']
    assert not b.fidelity(deck['slides'],wrong)['ok']
    wrong=deepcopy(ledger);wrong[0]['text']=[v.replace('kg','g') for v in wrong[0]['text']]
    assert not b.fidelity(deck['slides'],wrong)['ok']

def test_blind_image_bound_rubric_and_all_outcomes(services,tmp_path):
    d,s,args,case=setup(services,tmp_path);cid=case['case_id']
    rendered=b.run(services,b.BenchmarkArgs(**args,action='render'))
    assert rendered['results'][0]['status']=='rendered'
    pair=b.run(services,b.BenchmarkArgs(**args,case_id=cid,action='blind',include_image=True))
    assert pair['_image']['mime']=='image/png' and 'arms' not in pair and 'mapping' not in pair
    rating={arm:{k:3 for k in b.RUBRIC} for arm in ('A','B')};rating.update(preference='tie',png_sha256=pair['png_sha256'],source_checks={'A':True,'B':True})
    with pytest.raises(RevisionConflict):b.run(services,b.BenchmarkArgs(**args,case_id=cid,action='rate',token=pair['token'],ratings={**rating,'png_sha256':'wrong'}))
    with pytest.raises(CiceroError):b.run(services,b.BenchmarkArgs(**args,case_id=cid,action='rate',token=pair['token'],ratings={**rating,'A':{'legibility':3}}))
    b.run(services,b.BenchmarkArgs(**args,case_id=cid,action='rate',token=pair['token'],ratings=rating))
    b.run(services,b.BenchmarkArgs(**args,case_id=cid,action='rate',token=pair['token'],ratings=rating))
    summary=b.run(services,b.BenchmarkArgs(**args))
    assert summary['outcomes']=={'tie':1} and summary['source_verified_outcomes']=={'tie':1} and summary['complete']

def test_failures_and_source_regressions_remain_in_summary(services,tmp_path):
    d,s,args,case=setup(services,tmp_path)
    decks.patch_slide(services,d['id'],s['id'],{'notes':'Later manual edit'})
    rendered=b.run(services,b.BenchmarkArgs(**args,action='render'))
    assert rendered['results'][0]['status']=='failed'
    summary=b.run(services,b.BenchmarkArgs(**args))
    assert not summary['complete'] and len(summary['cases'])==1 and 'source changed' in summary['cases'][0]['error']

def test_existing_cicero_export_is_not_independent(services,tmp_path):
    d,s,args,case=setup(services,tmp_path)
    raw=(tmp_path/'fixture.pptx').read_bytes();decks.add_export(services,d['id'],'pptx',raw,'Already exported')
    with pytest.raises(CiceroError,match='not an independent'):
        b.run(services,b.BenchmarkArgs(**args,action='case',case={'key':'not-independent','brief':'Same artifact','baseline_path':str(tmp_path/'fixture.pptx')}))

def test_native_chart_relationships_accept_absolute_package_paths(services,tmp_path):
    import io,zipfile,posixpath
    from lxml import etree
    d,s,args,case=setup(services,tmp_path)
    raw=(tmp_path/'fixture.pptx').read_bytes();output=io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(raw)) as source,zipfile.ZipFile(output,'w') as target:
        for name in source.namelist():
            data=source.read(name)
            if name.startswith('ppt/slides/_rels/') and name.endswith('.rels'):
                xml=etree.fromstring(data)
                for rel in xml:
                    if rel.get('Type','').endswith('/chart'):
                        rel.set('Target','/'+posixpath.normpath(posixpath.join('ppt/slides',rel.get('Target'))))
                data=etree.tostring(xml)
            target.writestr(name,data)
    assert b.pptx_ledger(output.getvalue())==b.pptx_ledger(raw)

