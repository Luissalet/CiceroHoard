import base64,io,json,struct,zipfile,tempfile
from pathlib import Path
import pytest
from cicero_hoard import decks,scene3d
from cicero_hoard.errors import CiceroError
from conftest import new_deck,png_bytes

def model_fixture(root):
    root.mkdir(parents=True,exist_ok=True)
    # One double-sided textured triangle plus a native translation clip.
    vertices=[-1,-1,0,1,-1,0,0,1,0];uv=[0,0,1,0,.5,1]
    raw=struct.pack('<9f6f2f6f',*vertices,*uv,0,1,0,0,0,.5,0,0)
    (root/'mesh.bin').write_bytes(raw);(root/'texture.png').write_bytes(png_bytes(16,16,(220,50,65)))
    document={'asset':{'version':'2.0'},'scene':0,'scenes':[{'nodes':[0]}],
        'nodes':[{'name':'Evidence model','mesh':0}],
        'buffers':[{'uri':'mesh.bin','byteLength':len(raw)}],
        'bufferViews':[{'buffer':0,'byteOffset':0,'byteLength':36},{'buffer':0,'byteOffset':36,'byteLength':24},
                       {'buffer':0,'byteOffset':60,'byteLength':8},{'buffer':0,'byteOffset':68,'byteLength':24}],
        'accessors':[{'bufferView':0,'componentType':5126,'count':3,'type':'VEC3','min':[-1,-1,0],'max':[1,1,0]},
                     {'bufferView':1,'componentType':5126,'count':3,'type':'VEC2'},
                     {'bufferView':2,'componentType':5126,'count':2,'type':'SCALAR','min':[0],'max':[1]},
                     {'bufferView':3,'componentType':5126,'count':2,'type':'VEC3'}],
        'images':[{'uri':'texture.png'}],'textures':[{'source':0}],
        'materials':[{'doubleSided':True,'pbrMetallicRoughness':{'baseColorTexture':{'index':0},'metallicFactor':0,'roughnessFactor':.8}}],
        'meshes':[{'primitives':[{'attributes':{'POSITION':0,'TEXCOORD_0':1},'material':0}]}],
        'animations':[{'name':'Move','samplers':[{'input':2,'output':3,'interpolation':'LINEAR'}],
                       'channels':[{'sampler':0,'target':{'node':0,'path':'translation'}}]}]}
    path=root/'model.gltf';path.write_text(json.dumps(document),encoding='utf-8');return path,document,raw

def test_full_resource_graph_import_and_deduplication(services,tmp_path):
    d=new_deck(services);path,original,_=model_fixture(tmp_path/'source')
    args=scene3d.ImportArgs(deck_id=d['id'],path=str(path));result=scene3d.run(services,args)
    assert result['offline'] and result['textures']==1 and result['animations'][0]['name']=='Move'
    assert {r['uri'] for r in result['resources']}=={'mesh.bin','texture.png'}
    asset=decks.asset_info(services,result['asset_id']);packed=json.loads(asset['path'].read_text())
    assert packed['buffers'][0]['uri'].startswith('data:') and packed['images'][0]['uri'].startswith('data:')
    assert packed['materials']==original['materials'] and packed['animations']==original['animations']
    assert scene3d.run(services,args)['reused']

def test_missing_or_escaping_dependencies_fail_before_import(services,tmp_path):
    d=new_deck(services);path,document,_=model_fixture(tmp_path/'source');(path.parent/'texture.png').unlink()
    with pytest.raises(CiceroError,match='Missing model resource'):scene3d.run(services,scene3d.ImportArgs(deck_id=d['id'],path=str(path)))
    document['images'][0]['uri']='../secret.png';path.write_text(json.dumps(document))
    with pytest.raises(CiceroError,match='escapes'):scene3d.run(services,scene3d.ImportArgs(deck_id=d['id'],path=str(path)))
    assert not services.db.query('SELECT id FROM assets WHERE deck_id=?',(d['id'],))

def test_glb_and_zip_are_packaged_offline(services,tmp_path):
    d=new_deck(services);path,document,binary=model_fixture(tmp_path/'source')
    del document['buffers'][0]['uri'];document['images'][0]['uri']='data:image/png;base64,'+base64.b64encode(png_bytes()).decode()
    data=json.dumps(document).encode();data+=b' '*((-len(data))%4);binary+=b'\x00'*((-len(binary))%4)
    glb=struct.pack('<III',0x46546c67,2,12+8+len(data)+8+len(binary))+struct.pack('<II',len(data),0x4e4f534a)+data+struct.pack('<II',len(binary),0x004e4942)+binary
    imported=scene3d.import_bytes(services,d['id'],glb,'model.glb')
    assert imported['offline']
    archive=io.BytesIO()
    with zipfile.ZipFile(archive,'w') as z:
        for f in path.parent.iterdir():z.write(f,'scene/'+f.name)
    result=scene3d.import_bytes(services,d['id'],archive.getvalue(),'model.zip')
    assert len(result['resources'])==2
    with pytest.raises(CiceroError,match='complete length'):scene3d.import_bytes(services,d['id'],glb[:-4],'broken.glb')

def test_actual_three_model_texture_camera_motion_and_offline(services,client,tmp_path):
    from playwright.sync_api import sync_playwright
    from cicero_hoard import visual_review as vr
    from PIL import Image,ImageChops
    d=new_deck(services);path,_,_=model_fixture(tmp_path/'source');asset=scene3d.run(services,scene3d.ImportArgs(deck_id=d['id'],path=str(path)))
    decks.add_slide(services,d['id'],title='Imported scene',layout='freeform',blocks=[{'type':'scene3d','objects':[
        {'id':'native','shape':'model','asset_id':asset['asset_id'],'animation_clip':0}],
        'camera_path':[{'time':0,'position':[0,0,4]},{'time':4,'position':[2,1,4]}],
        'lights':[{'type':'hemisphere','intensity':2},{'type':'directional','position':[2,3,5],'intensity':4}],
        'auto_frame':True,'frame':[0,0,1,1]}])
    response=client.get(f"/api/decks/{d['id']}/preview.html?mode=present");assert response.status_code==200
    html=response.text;assert 'texture.png' not in html or '"uri": "texture.png"' not in html
    # Source files can disappear; the presentation keeps its own complete copy.
    for f in path.parent.iterdir():f.unlink()
    with sync_playwright() as p,tempfile.TemporaryDirectory() as profile:
        context=vr._launch(p,profile)
        try:
            page=context.new_page();page.emulate_media(reduced_motion='no-preference');requests=[];errors=[]
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.on('request',lambda r:requests.append(r.url))
            page.route('http://127.0.0.1/fixture',lambda route:route.fulfill(status=200,headers=dict(response.headers),body=html))
            page.goto('http://127.0.0.1/fixture',wait_until='load')
            page.wait_for_timeout(150);assert not errors,errors
            page.wait_for_function("document.querySelector('.scene3d').dataset.ready==='true'||document.querySelector('.scene3d').dataset.error")
            el=page.locator('.scene3d');assert el.get_attribute('data-error') is None
            assert el.get_attribute('data-models-loaded')=='1'
            canvas=el.locator('canvas');first=canvas.screenshot();camera=el.get_attribute('data-camera')
            page.wait_for_timeout(350);second=canvas.screenshot()
            image=Image.open(io.BytesIO(first)).convert('RGB')
            assert sum(1 for r,g,b in image.getdata() if r>g*1.3 and r>b*1.3)>1000
            assert ImageChops.difference(image,Image.open(io.BytesIO(second)).convert('RGB')).getbbox()
            assert camera!=el.get_attribute('data-camera')
            assert not [url for url in requests if url.startswith(('http:','https:','file:')) and url!='http://127.0.0.1/fixture']
            page.set_viewport_size({'width':390,'height':844});page.wait_for_timeout(100)
            assert canvas.bounding_box()['width']>200
        finally:context.close()

