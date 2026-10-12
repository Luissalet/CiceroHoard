"""Shared chart rendering and graph layout through maintained specialist engines."""
from __future__ import annotations
import json
import shutil
from functools import lru_cache
from pathlib import Path
from .errors import CiceroError
from .hoard_link import proc

ROOT=Path(__file__).resolve().parent/'static/visual-runtime'

@lru_cache(maxsize=512)
def _run(payload: str) -> str:
    node=proc.find_exe('node') or shutil.which('node')
    if not node:raise CiceroError('Install the local visual engine runtime to render advanced charts.',code='visual_engine_unavailable')
    engine=ROOT/'engine.mjs'
    if not engine.is_file():raise CiceroError('Build the packaged visual runtime before using advanced visuals.',code='visual_engine_unavailable')
    result=proc.run([node,str(engine)],input=payload,timeout=30)
    if result.returncode:raise CiceroError('The visual engine could not render this dataset. Check chart dimensions and data.',code='visual_render_failed')
    return result.stdout

def chart_svg(block: dict,width: float,height: float,theme: dict,lang: str) -> str:
    if not block.get('categories') or not block.get('series'):
        return f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" role="img" aria-label="No data"></svg>'
    return _run(json.dumps({'kind':'chart','block':block,'width':width,'height':height,
        'palette':theme['colors'],'font':theme['fonts']['body'],'font_scale':block['font_size']/18 if block.get('font_size') else theme.get('chart_font_points',13.5)/13.5,'lang':lang},sort_keys=True))

def graph_layout(block: dict,width: float,height: float) -> dict:
    layout=json.loads(_run(json.dumps({'kind':'diagram','block':block},sort_keys=True)))
    scale=min(width/max(1,layout['width']),height/max(1,layout['height']))
    left=(width-layout['width']*scale)/2;top=(height-layout['height']*scale)/2
    nodes={n['id']:n for n in block['nodes']}
    return {'scale':scale,'nodes':[{**nodes[n['id']],'x':left+n['x']*scale,'y':top+n['y']*scale,
        'width':n['width']*scale,'height':n['height']*scale} for n in layout['children']],
        'edges':[{'source':e['source'],'target':e['target'],'label':e.get('label',''),
            'label_frame':([left+le['labels'][0]['x']*scale,top+le['labels'][0]['y']*scale,le['labels'][0]['width']*scale,le['labels'][0]['height']*scale] if le.get('labels') else None),
            'points':[{'x':left+p['x']*scale,'y':top+p['y']*scale} for p in
                [s['startPoint'],*s.get('bendPoints',[]),s['endPoint']]]}
            for e,le in zip(block['edges'],layout.get('edges',[])) for s in le.get('sections',[])]}
