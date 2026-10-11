"""Exercise the running isolated app through its actual stdio MCP bridge with fictional data."""
import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client

async def run(args):
    root=Path(__file__).resolve().parent.parent
    env={**os.environ,'CICERO_URL':args.url,'CICERO_DATA_DIR':str(Path(args.data_dir).resolve()),'CICERO_BRIDGE_AUTOSTART':'0',
        'HOARD_AGENT_ID':'cicero-workbench-smoke','HOARD_AGENT_SESSION':'isolated-workbench-smoke'}
    server=StdioServerParameters(command=sys.executable,args=[str(root/'mcp_server.py')],env=env,cwd=str(root))
    async with stdio_client(server) as (read,write):
        async with ClientSession(read,write) as session:
            await session.initialize();catalog=await session.list_tools();meta={t.name:t for t in catalog.tools}
            async def call(name,**arguments):
                if not meta[name].annotations.readOnlyHint:arguments['reason']='Verify reusable capabilities with fictional data in an isolated instance.'
                result=await session.call_tool(name,arguments)
                if result.isError:raise RuntimeError(name+': '+str(result.content))
                return result.structuredContent or json.loads(next(c.text for c in result.content if c.type=='text'))
            deck=await call('deck_create',title='Data and delivery workbench',language='en',slide_count=3)
            deck_id=deck['id'];await call('visual_catalog',kind='timelines')
            dataset=await call('dataset_import',deck_id=deck_id,text='Region;Before;After\nNorth;7,8;5,1\nCentre;6,4;4,3\nSouth;8,2;6,0',number_format='es',title='Fictional measurements')
            await call('dataset_get',deck_id=deck_id,source_id=dataset['id'])
            derived=await call('dataset_transform',deck_id=deck_id,source_id=dataset['id'],sort_column='After')
            mapped=await call('dataset_visual',deck_id=deck_id,source_id=derived['id'],chart='dumbbell',category_column='Region',series_columns=['Before','After'])
            mapped['block'].update(show_values=True,unit='units',build=1,effect='fade')
            first=await call('slide_add',deck_id=deck_id,layout='evidence',title='Compare the observed measurements',notes='Private speaker note: these are fictional measurements.',sources=mapped['source_ids'])
            await call('slide_visual_update',deck_id=deck_id,slide_id=first['id'],block_index=0,block=mapped['block'],source_ids=mapped['source_ids'],expected_revision=1)
            await call('slide_add',deck_id=deck_id,layout='evidence',title='From records to a reviewed delivery',blocks=[{'type':'timeline','effect':'stages','items':[
                {'date':'Source','label':'Import','detail':'Preserve original rows'},{'date':'Analysis','label':'Compare','detail':'Use explicit column mappings'},
                {'date':'Delivery','label':'Present','detail':'Separate audience and notes','emphasis':True}]}],notes='Each click reveals the next milestone.')
            await call('slide_add',deck_id=deck_id,layout='freeform',title='Compose with a clear hierarchy',blocks=[
                {'type':'text','id':'conclusion','text':'A comparison should make its conclusion easy to inspect.','frame':[0,0,.37,1],'font_size':36},
                {**mapped['block'],'id':'measurements','frame':[.43,0,.57,1],'build':0,'effect':'none'}],sources=mapped['source_ids'],notes='Reserve slide with an alternative composition.')
            scene=await call('deck_scene',deck_id=deck_id);assert len(scene['slides'])==3
            room=await call('deck_live_start',deck_id=deck_id,target_seconds=900,main_slide_count=2)
            for action in ('resume','next','pause','reset'):
                room=await call('deck_live_control',deck_id=deck_id,action=action)
            await call('deck_live_control',deck_id=deck_id,action='goto',slide_index=0)
            current=await call('deck_live_state',deck_id=deck_id);assert current['slide_index']==0
            large=await call('dataset_import',deck_id=deck_id,text='Category,Value\n'+'\n'.join(f'Row_{i},{i}' for i in range(2000)),title='Fictional precision test')
            full=await call('dataset_visual',deck_id=deck_id,source_id=large['id'],category_column='Category',series_columns=['Value'],limit=2000)
            assert len(full['block']['categories'])==2000 and full['block']['series'][0]['values']==list(range(2000))
            exports={}
            for format in ('pptx','html','md'):
                exports[format]=await call('deck_export',deck_id=deck_id,format=format)
            report={'tool_count':len(meta),'deck_id':deck_id,'presenter_url':args.url+f'/#/presenter/{deck_id}',
                    'exports':exports,'check':await call('deck_check',deck_id=deck_id),'scene':scene}
            output=Path(args.data_dir)/'workbench-smoke.json';output.write_text(json.dumps(report,indent=2),encoding='utf-8')
            print(json.dumps({'tool_count':len(meta),'deck_id':deck_id,'presenter_url':report['presenter_url'],'report':str(output)}))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url',required=True);parser.add_argument('--data-dir',required=True)
    asyncio.run(run(parser.parse_args()))
