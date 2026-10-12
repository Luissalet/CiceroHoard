"""Self-contained glTF assets: complete resource graphs, not fragile source paths."""
from copy import deepcopy
from pathlib import Path,PurePosixPath
import base64,io,json,mimetypes,struct,zipfile
from urllib.parse import urlsplit,unquote
from typing import Optional
from pydantic import BaseModel
from . import decks
from .errors import CiceroError
from .hoard_link.ids import new_ulid
from .hoard_link.atomic import write_bytes_atomic
from .util import sha256_hex,jdump

class ImportArgs(BaseModel):
    deck_id:str
    path:str
    resource_root:Optional[str]=None
    entry:Optional[str]=None

def _gltf(raw):
    binary=None
    if raw[:4]==b'glTF':
        if len(raw)<20:raise CiceroError('Truncated GLB header')
        magic,version,length=struct.unpack_from('<III',raw)
        if version!=2 or length!=len(raw):raise CiceroError('A GLB v2 with a complete length is required')
        pos=12;document=None
        while pos<len(raw):
            if pos+8>len(raw):raise CiceroError('Truncated GLB chunk header')
            size,kind=struct.unpack_from('<II',raw,pos);pos+=8
            if pos+size>len(raw):raise CiceroError('Truncated GLB resource chunk')
            chunk=raw[pos:pos+size];pos+=size
            if kind==0x4e4f534a:document=json.loads(chunk.rstrip(b'\x00 \t\r\n'))
            elif kind==0x004e4942:binary=chunk
        if document is None:raise CiceroError('The GLB has no JSON scene')
    else:document=json.loads(raw.decode('utf-8-sig'))
    if document.get('asset',{}).get('version')!='2.0':raise CiceroError('A glTF 2.0 scene is required')
    return document,binary

def package(raw,filename,read_resource):
    try:document,binary=_gltf(raw)
    except (ValueError,UnicodeError,struct.error) as error:raise CiceroError('Invalid glTF document: '+str(error)) from error
    resources=[]
    def embedded(data,mime):return 'data:'+mime+';base64,'+base64.b64encode(data).decode('ascii')
    def resource(uri):
        parsed=urlsplit(uri)
        if parsed.scheme=='data':
            try:
                header,payload=uri.split(',',1)
                data=base64.b64decode(payload,validate=True) if ';base64' in header else unquote(payload).encode('latin1')
            except Exception as error:raise CiceroError('Invalid embedded glTF resource') from error
            return data,uri
        if parsed.scheme or parsed.netloc:raise CiceroError('Package remote model resources locally before importing: '+uri)
        name=unquote(parsed.path).replace('\\','/')
        data=read_resource(name)
        resources.append({'uri':name,'bytes':len(data),'sha256':sha256_hex(data)})
        mime=mimetypes.guess_type(name)[0] or 'application/octet-stream'
        return data,embedded(data,mime)
    for i,buffer in enumerate(document.get('buffers',[])):
        if 'uri' not in buffer:
            if i!=0 or binary is None:raise CiceroError('Missing binary buffer '+str(i))
            data=binary;buffer['uri']=embedded(binary,'application/octet-stream')
        else:data,buffer['uri']=resource(buffer['uri'])
        if len(data)<buffer.get('byteLength',0):raise CiceroError('A model buffer is shorter than its declared length')
    def resolve(value):
        if isinstance(value,dict):
            for key,item in list(value.items()):
                if key=='uri' and isinstance(item,str) and not item.startswith('data:'):value[key]=resource(item)[1]
                else:resolve(item)
        elif isinstance(value,list):
            for item in value:resolve(item)
    resolve(document)
    for view in document.get('bufferViews',[]):
        buffers=document.get('buffers',[]);index=view.get('buffer',-1)
        if not 0<=index<len(buffers) or view.get('byteOffset',0)+view.get('byteLength',0)>buffers[index]['byteLength']:
            raise CiceroError('A bufferView points outside its model buffer')
    if not document.get('meshes') and not document.get('nodes'):raise CiceroError('The model has no scene objects')
    metadata={'filename':filename,'source_sha256':sha256_hex(raw),'resources':resources,'offline':True,
        'nodes':[{'index':i,'name':n.get('name','node-'+str(i))} for i,n in enumerate(document.get('nodes',[]))],
        'animations':[{'index':i,'name':a.get('name','clip-'+str(i))} for i,a in enumerate(document.get('animations',[]))],
        'materials':len(document.get('materials',[])),'textures':len(document.get('textures',[])),
        'extensions':document.get('extensionsUsed',[])}
    return jdump(document).encode('utf-8'),metadata

def import_bytes(svc,deck_id,raw,filename,*,resource_root=None,entry=None):
    decks._deck_row(svc,deck_id)
    if filename.lower().endswith('.zip'):
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                names=[n for n in archive.namelist() if n.lower().endswith(('.gltf','.glb'))]
                selected=entry or (names[0] if len(names)==1 else None)
                if selected not in names:raise CiceroError('Choose one glTF/GLB entry from the model archive')
                parent=PurePosixPath(selected).parent
                def read(name):
                    from posixpath import normpath
                    target=normpath(str(parent/name))
                    if target.startswith('../') or target.startswith('/'):raise CiceroError('A model resource escapes its archive')
                    try:return archive.read(target)
                    except KeyError as error:raise CiceroError('Missing model resource: '+target) from error
                data,metadata=package(archive.read(selected),filename,read)
        except zipfile.BadZipFile as error:raise CiceroError('Invalid model archive') from error
    else:
        root=Path(resource_root).resolve() if resource_root else None
        def read(name):
            if root is None:raise CiceroError('External resources need resource_root or a ZIP containing the complete model')
            target=(root/name).resolve()
            if not target.is_relative_to(root):raise CiceroError('A model resource escapes resource_root')
            if not target.is_file():raise CiceroError('Missing model resource: '+name)
            return target.read_bytes()
        data,metadata=package(raw,filename,read)
    digest=sha256_hex(data)
    with svc.db.transaction():
        existing=svc.db.one('SELECT id FROM assets WHERE deck_id=? AND sha256=?',(deck_id,digest))
        if existing and decks.asset_info(svc,existing['id']):return {'asset_id':existing['id'],'reused':True,**metadata}
        asset_id=new_ulid();path=svc.config.assets_dir/(asset_id+'.gltf')
        path.parent.mkdir(parents=True,exist_ok=True);write_bytes_atomic(path,data,fsync=False)
        svc.db.execute('INSERT INTO assets(id,deck_id,filename,mime,ext,width,height,bytes,sha256,created_ts) VALUES(?,?,?,?,?,?,?,?,?,?)',
            (asset_id,deck_id,filename,'model/gltf+json','gltf',0,0,len(data),digest,svc.clock()))
        svc.db.execute('INSERT INTO media_metadata(asset_id,definition) VALUES(?,?)',(asset_id,jdump(metadata)))
    return {'asset_id':asset_id,'bytes':len(data),'sha256':digest,**metadata}

def run(svc,args):
    path=Path(args.path).expanduser().resolve()
    if not path.is_file():raise CiceroError('The local model file does not exist')
    return import_bytes(svc,args.deck_id,path.read_bytes(),path.name,resource_root=args.resource_root or str(path.parent),entry=args.entry)

def render_data(block,assets):
    data=deepcopy(block);models={};extensions=set()
    for obj in data.get('objects',[]):
        if obj.get('shape')!='model':continue
        asset=assets(obj.get('asset_id',''))
        if not asset or asset.get('mime')!='model/gltf+json':models[obj['id']]={'error':'Missing imported model'}
        else:
            document=json.loads(Path(asset['path']).read_text(encoding='utf-8'));models[obj['id']]={'document':document}
            extensions.update(document.get('extensionsUsed',[]))
    data['_models']=models
    if models:
        decoder=Path(__file__).parent/'static'/'visual-runtime'/'decoders'
        names=set()
        if 'KHR_draco_mesh_compression' in extensions:names.update(['draco_decoder.js','draco_wasm_wrapper.js','draco_decoder.wasm'])
        if 'KHR_texture_basisu' in extensions:names.update(['basis_transcoder.js','basis_transcoder.wasm'])
        data['_decoders']={p.name:'data:application/octet-stream;base64,'+base64.b64encode(p.read_bytes()).decode('ascii') for p in decoder.iterdir() if p.is_file() and p.name in names}
    return data
