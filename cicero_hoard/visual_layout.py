"""Content-driven diagrams, editable tables and flat metric compositions."""
from .layouts import Box,Para,fit_size,paras_height
from .visuals import graph_layout


def metric_columns(count,w):
    """Columns for a row of metrics: up to four side by side, then balanced rows (five as 3+2, six as 3+3)."""
    fit=max(1,int(w//230))
    if count<=4:return max(1,min(count,fit))
    return max(1,min(3 if count in (5,6,9) else 4,fit))


def layout_visual(block,x,y,w,h,ctx,scale=1.0):
    if block.get('title'):
        untitled={k:v for k,v in block.items() if k!='title'}
        boxes,used=layout_visual(untitled,x,y+48,w,max(1,h-48),ctx,scale)
        return [Box('text',x,y,w,40,paras=[Para(block['title'],26,bold=True)],object_id='heading'),*boxes],used+48
    kind=block['type']
    if kind=='timeline':
        items=block['items'];count=len(items);cw=w/count;boxes=[]
        axis=y+min(80,h*.22)
        for i,item in enumerate(items):
            left=x+i*cw;center=left+cw/2
            stage=item.get('build',i+1) if block.get('effect')=='stages' else item.get('build',block.get('build'))
            if i:
                boxes.append(Box('rule',center-cw,axis+7,cw,2,fill='muted',build=stage,effect='wipe'))
            ink='accent' if item.get('emphasis') else 'accent2'
            boxes.append(Box('marker',center-8,axis,16,16,fill=ink,build=stage,effect='fade'))
            if item.get('date'):
                boxes.append(Box('text',left+10,axis-45,cw-20,34,paras=[Para(item['date'],20,bold=True,color=ink,align='center')],build=stage))
            def make(size):
                paras=[Para(item['label'],size,bold=True,font='heading',align='center',space_after=12)]
                if item.get('detail'):paras.append(Para(item['detail'],max(14,size*.78),color='muted',align='center'))
                return paras
            size,overflow=fit_size(make,cw-20,max(1,h-(axis-y)-40),block.get('font_size') or 26,16,ctx)
            if overflow:ctx.overflow_where.append('timeline milestone: '+item['label'])
            boxes.append(Box('text',left+10,axis+36,cw-20,max(1,h-(axis-y)-40),paras=make(size),build=stage))
        return boxes,h
    if kind=='table':
        if h/(len(block['rows'])+1)<32:ctx.overflow_where.append('table density: split the rows across slides')
        rowh=max(56,(block.get('font_size') or 24)*1.5+16) if block.get('font_size') or scale>=1 else max(36,round(56*scale))
        return [Box('table',x,y,w,min(h,rowh*(len(block['rows'])+1)),data=block)],min(h,rowh*(len(block['rows'])+1))
    if kind=='metrics':
        items=block['items'];columns=metric_columns(len(items),w);rows=(len(items)+columns-1)//columns
        cellw=w/columns;limit=min(h/rows,220);boxes=[];inner=cellw-28
        k=max(.6,min(1.0,scale));gap=max(6,round(12*k))
        vhi=block.get('font_size') or max(28,round(60*k));lhi=max(16,round(26*k));dhi=max(13,round(19*k))
        # One value size per row of metrics, so figures side by side read as a set.
        cells=[]
        for item in items:
            label=item.get('label') or ''
            if str(label).strip().casefold()==str(item.get('value') or '').strip().casefold():label=''  # «Calidad / Calidad»
            cells.append((item,label))
        def heights(vs,ls,ds):
            out=[]
            for item,label in cells:
                hv=vs*1.25;hl=paras_height([Para(label,ls,bold=True,line=1.3)],inner,ctx) if label else 0
                hd=paras_height([Para(item['detail'],ds,line=1.3)],inner,ctx) if item.get('detail') else 0
                out.append((hv,hl,hd,hv+(gap+hl if hl else 0)+(gap+hd if hd else 0)))
            return out
        vs=vhi
        while vs>20 and any(fit_size(lambda n:[Para(str(it['value']),n,bold=True,font='heading',line=1.25)],inner,vs*1.25,vs,vs,ctx)[1] for it,_ in cells):vs-=2
        ls,ds=lhi,dhi
        while True:
            hs=heights(vs,ls,ds);need=max(r[3] for r in hs)
            if need<=limit or (ls<=16 and ds<=13 and vs<=max(20,round(vhi*.6))):break
            if ls>16:ls-=1
            if ds>13:ds-=1
            if need>limit and ls<=16 and ds<=13:vs=max(20,vs-2)
        cellh=min(limit,max(r[3] for r in hs))
        if max(r[3] for r in hs)>limit+1:ctx.overflow_where.append('metric text: '+str(cells[0][1] or cells[0][0].get('value')))
        for i,((item,label),(hv,hl,hd,_)) in enumerate(zip(cells,hs)):
            left=x+(i%columns)*cellw;top=y+(i//columns)*(cellh+(gap*2 if rows>1 else 0))
            build=item.get('build',block.get('build'))
            color='accent' if item.get('emphasis') else 'text'
            boxes.append(Box('text',left,top,inner,hv,paras=[Para(str(item['value']),vs,bold=True,color=color,font='heading',line=1.25)],build=build))
            cy=top+hv
            if label:
                boxes.append(Box('text',left,cy+gap,inner,hl,paras=[Para(label,ls,bold=True,line=1.3)],build=build));cy+=gap+hl
            if item.get('detail'):
                boxes.append(Box('text',left,cy+gap,inner,hd,paras=[Para(item['detail'],ds,color='muted',line=1.3)],build=build))
        return boxes,cellh*rows+(gap*2*(rows-1))
    layout=graph_layout(block,w,h);boxes=[];scale=layout['scale']
    nodes={node['id']:node for node in layout['nodes']}
    staged=block.get('effect')=='stages'
    if staged:
        for i,node in enumerate(layout['nodes']):node['build']=node.get('build',i+1)
    for edge in layout['edges']:
        target=nodes[edge['target']]
        build=target.get('build') if staged else block.get('build')
        edge_id = 'edge-' + edge['source'] + '-' + edge['target'] + '-' + str(sum(1 for b in boxes if b.kind == 'connector' and b.data['source'] == edge['source'] and b.data['target'] == edge['target']))
        boxes.append(Box('connector',x,y,w,h,data={**edge,'canvas':[w,h]},build=build,effect='wipe' if staged else None,object_id=edge_id))
        if edge.get('label') and edge.get('label_frame'):
            lx,ly,lw,lh=edge['label_frame']
            boxes.append(Box('text',x+lx,y+ly,lw,lh,paras=[Para(edge['label'],18*scale,color='muted',align='center')],build=build,effect='fade',object_id=edge_id+'-label'))
    for i,node in enumerate(layout['nodes']):
        build=node.get('build',i+1) if staged else block.get('build')
        left=x+node['x'];top=y+node['y'];nw=node['width'];nh=node['height']
        boxes.append(Box('node',left,top,nw,nh,fill='surface' if node.get('emphasis') else 'background',data=node,build=build,effect='fade',object_id='node-'+node['id']))
        pad=16*scale
        def text_at(size):
            label=Para(node['label'],size,bold=True,font='heading',line=1.15,align='center',space_after=10*scale if node.get('detail') else 0)
            return [label,Para(node['detail'],size*18/26,color='muted',align='center',line=1.2)] if node.get('detail') else [label]
        size,overflow=fit_size(text_at,nw-2*pad,nh-2*pad,block.get('font_size') or max(12,round(26*min(1.0,layout.get('vscale',scale)))),max(10,round(16*scale)),ctx)
        text=text_at(size)
        if overflow:ctx.overflow_where.append('diagram node: '+node['id'])
        boxes.append(Box('text',left+pad,top+pad,nw-2*pad,nh-2*pad,paras=text,anchor='middle',build=build,effect='fade',object_id='node-'+node['id']+'-label'))
    if scale<.5:ctx.overflow_where.append('diagram density: use fewer nodes or another direction')
    return boxes,h
