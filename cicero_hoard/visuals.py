"""Shared chart rendering and graph layout through maintained specialist engines."""
from __future__ import annotations
import json
import shutil
from functools import lru_cache
from pathlib import Path
from .errors import CiceroError
from .hoard_link import proc

ROOT=Path(__file__).resolve().parent/'static/visual-runtime'
# Vertical stretch of width-limited diagrams: applies below this share of the frame height, fills up to
# STRETCH_FILL of it, and never makes nodes more than STRETCH_MAX times taller than the uniform scale.
STRETCH_BELOW, STRETCH_FILL, STRETCH_MAX = .55, .7, 1.8

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
    # A wide graph (a left-to-right chain) is limited by the width and used to leave most of the frame empty with
    # tiny labels. Stretch it vertically, within limits, so nodes gain room for larger, wrapped text. Orthogonal
    # routes stay orthogonal under an axis-aligned stretch.
    vscale=scale
    if layout['height']*scale<height*STRETCH_BELOW:
        vscale=scale*min(STRETCH_MAX,height*STRETCH_FILL/max(1,layout['height']*scale))
    left=(width-layout['width']*scale)/2;top=(height-layout['height']*vscale)/2
    nodes={n['id']:n for n in block['nodes']}
    return {'scale':scale,'vscale':vscale,'nodes':[{**nodes[n['id']],'x':left+n['x']*scale,'y':top+n['y']*vscale,
        'width':n['width']*scale,'height':n['height']*vscale} for n in layout['children']],
        'edges':[{'source':e['source'],'target':e['target'],'label':e.get('label',''),
            'label_frame':([left+le['labels'][0]['x']*scale,top+le['labels'][0]['y']*vscale,le['labels'][0]['width']*scale,le['labels'][0]['height']*vscale] if le.get('labels') else None),
            'points':[{'x':left+p['x']*scale,'y':top+p['y']*vscale} for p in
                [s['startPoint'],*s.get('bendPoints',[]),s['endPoint']]]}
            for e,le in zip(block['edges'],layout.get('edges',[])) for s in le.get('sections',[])]}
