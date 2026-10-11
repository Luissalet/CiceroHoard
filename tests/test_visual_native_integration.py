import pytest
from cicero_hoard import native_slides
from cicero_hoard.export_pptx import build_pptx
from test_visual_workbench import KINDS,chart

@pytest.mark.skipif(not native_slides.available(),reason='Optional local native slide engine')
def test_all_visual_types_open_together_with_native_labels(tmp_path):
    slides=[]
    for i,kind in enumerate(KINDS,1):
        b=chart(kind);b['series'][0]['values']=[3,4,6];b['show_values']=True
        if kind=='band':b['series'][0].update(lower=[2,3,5],upper=[4,5,7])
        slides.append({'id':str(i),'position':i,'title':kind,'layout':'evidence',
            'blocks':[b,{'type':'text','text':'Fictional demonstration data.'}]})
    raw=build_pptx({'title':'Generic visuals','language':'en','theme':'claro','slides':slides},assets=lambda _:None)
    report=native_slides.render(raw,tmp_path/'native')
    assert report['slide_count']==14 and all((tmp_path/'native'/f'slide-{n}.png').is_file() for n in range(1,15))
