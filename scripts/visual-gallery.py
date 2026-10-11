"""Reproducible, source-grounded visual capability demo with fictional data."""
import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from cicero_hoard.config import Config
from cicero_hoard.services import Services
from cicero_hoard.agent_tools import call_tool
from cicero_hoard import decks,native_slides

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output-dir',type=Path,required=True)
args=parser.parse_args();args.output_dir.mkdir(parents=True,exist_ok=True)
with tempfile.TemporaryDirectory(prefix='cicero-gallery-') as directory:
    svc=Services(Config(data_dir=Path(directory),port=0))
    def call(name,**kw):return call_tool(svc,name,kw,cap=False)
    try:
        catalog=call('visual_catalog')
        blocks=[]
        for kind in catalog['charts']:
            b={'type':'chart','chart':kind,'unit':'Units','categories':['First','Second','Third'],
               'series':[{'name':'Measured','values':[3,4,6],'color':'#219BC3'}],'show_values':True}
            if kind=='dumbbell':b['series'].append({'name':'Comparison','values':[4,3,8],'color':'#C16B36'})
            if kind in ('scatter','bubble','band'):b['series'][0]['x_values']=[2,10,90]
            if kind=='bubble':b['series'][0]['sizes']=[1,4,9]
            if kind=='band':
                b['categories']=['2','10','30','60','90'];b['series'][0].update(values=[3,4,None,6,8],x_values=[2,10,30,60,90],lower=[2,3,None,5,7],upper=[4,5,None,7,9]);b['show_values']=False
            if kind=='heatmap':b['series'].append({'name':'Comparison','values':[8,2,5]})
            if kind=='waterfall':b['series'][0]['values']=[3,-6,4]
            if kind=='funnel':b['series'][0]['values']=[6,4,3]
            blocks.append(b)
        blocks += [
            {'type':'diagram','title':'Editable process','effect':'stages','nodes':[{'id':'a','label':'Measure'},{'id':'b','label':'Validate','detail':'Source and quality checks','emphasis':True},{'id':'c','label':'Compare'}],
             'edges':[{'source':'a','target':'b','label':'Evidence'},{'source':'b','target':'c'}]},
            {'type':'metrics','items':[{'value':'120','label':'Eligible observations','emphasis':True},{'value':'18%','label':'Eligibility','detail':'Fictional demonstration'},
             {'value':'3.49','label':'Measured score'}]},
            {'type':'table','headers':['Candidate','Result','Status'],'rows':[['A','3.49','Review'],['B','4.26','Reference']], 'highlight_rows':[0]},
        ]
        deck=call('deck_create',title='Cicero visual capability gallery',language='en',slide_count=len(blocks),brief='Fictional demonstration data, not research findings.')
        source=call('source_add',deck_id=deck['id'],title='Fictional demo data',text=json.dumps(blocks))
        call('slides_add',deck_id=deck['id'],batch_key='visual-gallery-v1',slides=[{'layout':'evidence','title':b.get('chart',b['type']).replace('_',' ').title(),
            'blocks':[b,{'type':'text','text':'Fictional demonstration data.'}],'notes':'Fictional demonstration data. Source: embedded demonstration dataset.','sources':[source['id']]} for b in blocks])
        for fmt in ('html','pptx'):
            result=call('deck_export',deck_id=deck['id'],format=fmt)
            shutil.copyfile(result['path'],args.output_dir/('visual-gallery.'+fmt))
        (args.output_dir/'check.json').write_text(json.dumps(call('deck_check',deck_id=deck['id']),indent=2),encoding='utf-8')
        (args.output_dir/'scene.json').write_text(json.dumps(call('deck_scene',deck_id=deck['id']),indent=2),encoding='utf-8')
        if native_slides.available():
            folder,report=svc._native_snapshot(decks.deck_view(svc,deck['id']))
            shutil.copytree(folder,args.output_dir/'native',dirs_exist_ok=True)
            print(json.dumps({'native_slides':report['slide_count'],'native_animations':report['animation_count']}))
        print(str(args.output_dir.resolve()))
    finally:svc.stop()
