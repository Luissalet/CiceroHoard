"""Content-driven diagrams, editable tables and flat metric compositions."""
from .layouts import Box,Para,fit_size
from .visuals import graph_layout


def layout_visual(block,x,y,w,h,ctx):
    if block.get('title'):
        untitled={k:v for k,v in block.items() if k!='title'}
        boxes,used=layout_visual(untitled,x,y+48,w,max(1,h-48),ctx)
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
            size,overflow=fit_size(make,cw-20,max(1,h-(axis-y)-40),26,16,ctx)
            if overflow:ctx.overflow_where.append('timeline milestone: '+item['label'])
            boxes.append(Box('text',left+10,axis+36,cw-20,max(1,h-(axis-y)-40),paras=make(size),build=stage))
        return boxes,h
    if kind=='table':
        if h/(len(block['rows'])+1)<32:ctx.overflow_where.append('table density: split the rows across slides')
        return [Box('table',x,y,w,min(h,56*(len(block['rows'])+1)),data=block)],min(h,56*(len(block['rows'])+1))
    if kind=='metrics':
        items=block['items'];columns=min(3,len(items));rows=(len(items)+columns-1)//columns
        cellw=w/columns;cellh=min(h/rows,220);boxes=[]
        for i,item in enumerate(items):
            left=x+(i%columns)*cellw;top=y+(i//columns)*cellh
            build=item.get('build',block.get('build'))
            color='accent' if item.get('emphasis') else 'text'
            vs,vo=fit_size(lambda n:[Para(item['value'],n,line=1.1)],cellw-28,84,64,26,ctx)
            ls,lo=fit_size(lambda n:[Para(item['label'],n,line=1.2)],cellw-28,64,26,18,ctx)
            if vo or lo:ctx.overflow_where.append('metric text: '+item['label'])
            boxes.extend([Box('text',left,top,cellw-28,84,paras=[Para(item['value'],vs,bold=True,color=color,font='heading',line=1.1)],build=build),
                Box('text',left,top+98,cellw-28,64,paras=[Para(item['label'],ls,bold=True,line=1.2)],build=build)])
            if item.get('detail'):
                ds,do=fit_size(lambda n:[Para(item['detail'],n)],cellw-28,50,19,14,ctx)
                if do:ctx.overflow_where.append('metric detail: '+item['label'])
                boxes.append(Box('text',left,top+164,cellw-28,50,paras=[Para(item['detail'],ds,color='muted')],build=build))
        return boxes,cellh*rows
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
        size,overflow=fit_size(text_at,nw-2*pad,nh-2*pad,max(12,round(26*scale)),max(10,round(16*scale)),ctx)
        text=text_at(size)
        if overflow:ctx.overflow_where.append('diagram node: '+node['id'])
        boxes.append(Box('text',left+pad,top+pad,nw-2*pad,nh-2*pad,paras=text,anchor='middle',build=build,effect='fade',object_id='node-'+node['id']+'-label'))
    if scale<.5:ctx.overflow_where.append('diagram density: use fewer nodes or another direction')
    return boxes,h
