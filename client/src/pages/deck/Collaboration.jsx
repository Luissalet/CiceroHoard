import React,{useEffect,useRef,useState} from 'react';
import * as Y from 'yjs';
import {useApp} from '../../App.jsx';
import {useDeck} from '../../components/deckContext.js';
import {Field} from '../../components/ui.jsx';
import {Plus,Trash2,ArrowUp,ArrowDown} from 'lucide-react';
import {snapshot,operation,editText} from '../../../../scripts/collaboration-model.mjs';

const decode=v=>Uint8Array.from(atob(v),c=>c.charCodeAt(0));
const encode=v=>btoa(Array.from(v,b=>String.fromCharCode(b)).join(''));
export default function Collaboration({slideId}){
 const {t}=useApp(),{deckId,reload}=useDeck();const [values,setValues]=useState({title:'',subtitle:'',notes:'',blocks:[]}),[peers,setPeers]=useState([]),[status,setStatus]=useState('connecting'),[error,setError]=useState('');
 const docRef=useRef(null),socketRef=useRef(null);
 useEffect(()=>{let doc=new Y.Doc(),recover=false;const actor=crypto.randomUUID(),socket=new WebSocket(`${location.protocol==='https:'?'wss':'ws'}://${location.host}/api/decks/${deckId}/slides/${slideId}/collaboration`);socketRef.current=socket;
  const observe=()=>{if(doc.getMap('slide').has('blocks_v2'))setValues(snapshot(doc));};
  function bind(){docRef.current=doc;doc.getMap('slide').observeDeep(observe);doc.on('update',(update,origin)=>{if(origin!=='remote'&&socket.readyState===1){setError('');socket.send(JSON.stringify({action:'apply',actor,update:encode(update)}));}});}
  bind();
  socket.onmessage=event=>{const r=JSON.parse(event.data);if(r.error){setError(r.error);setStatus('connecting');recover=true;socket.send(JSON.stringify({action:'state',actor}));return;}if(recover){doc.destroy();doc=new Y.Doc();bind();recover=false;}Y.applyUpdate(doc,decode(r.state),'remote');setPeers(r.presence);setStatus('connected');observe();};
  socket.onopen=()=>socket.send(JSON.stringify({action:'presence',actor,label:actor.slice(0,8)}));socket.onerror=()=>setStatus('error');socket.onclose=()=>setStatus('closed');
  const heartbeat=setInterval(()=>{if(socket.readyState===1)socket.send(JSON.stringify({action:'presence',actor,label:actor.slice(0,8)}));},10000);
  return()=>{clearInterval(heartbeat);socket.close();doc.destroy();void reload();};
 },[deckId,slideId,reload]);
 function edit(key,next){const doc=docRef.current,text=doc.getMap('slide').get(key);if(text instanceof Y.Text)doc.transact(()=>editText(text,next));}
 function change(op){try{operation(docRef.current,op);}catch(error){setStatus(error.message);}}
 function fields(block,value,path=[]){
  if(value&&typeof value==='object')return <div className="space-y-2">{Object.entries(value).filter(([k])=>!['id','type','asset_id','poll_url'].includes(k)).map(([key,item])=><React.Fragment key={key}>{fields(block,item,[...path,Array.isArray(value)?Number(key):key])}</React.Fragment>)}</div>;
  const label=path.join(' / '),set=next=>change({op:'set',block_id:block.id,path,value:next});
  if(typeof value==='boolean')return <label className="text-sm flex items-center gap-2"><input type="checkbox" disabled={status!=='connected'} checked={value} onChange={e=>set(e.target.checked)}/>{label}</label>;
  return <Field label={label}><input className="field" type={typeof value==='number'?'number':typeof value==='string'&&/^#[a-f\d]{6}$/i.test(value)?'color':'text'} step="any" value={value??''} disabled={status!=='connected'} onChange={e=>set(typeof value==='number'?Number(e.target.value):e.target.value)}/></Field>;
 }
 return <div className="space-y-3 max-w-3xl"><div role="status" className="text-sm">{['connecting','connected','closed','error'].includes(status)?t('collab_'+status):status} · {peers.length}</div><div className="flex gap-3 flex-wrap">{peers.map(p=><span key={p.actor} className="text-xs" style={{color:p.color}}>{p.label}</span>)}</div>
  {error&&<p role="alert" className="text-sm" style={{color:'var(--danger)'}}>{t('collab_not_applied')}: {error}</p>}
  {['title','subtitle','notes'].map(key=><Field key={key} label={t(key==='notes'?'speaker_notes':'slide_'+key)}>{key==='notes'?<textarea className="field" value={values[key]} rows={8} disabled={status!=='connected'} onChange={e=>edit(key,e.target.value)}/>:<input className="field" value={values[key]} disabled={status!=='connected'} onChange={e=>edit(key,e.target.value)}/>}</Field>)}
  {values.blocks.map((b,i)=><details key={b.id} className="border-t py-3" style={{borderColor:'var(--line)'}}><summary className="text-sm font-semibold">{b.title||b.caption||b.type}</summary><div className="flex gap-2 my-2"><button className="btn btn-icon" title={t('collab_move_up')} aria-label={t('collab_move_up')} disabled={status!=='connected'||i===0} onClick={()=>change({op:'move',block_id:b.id,before_id:values.blocks[i-1].id})}><ArrowUp size={16}/></button><button className="btn btn-icon" title={t('collab_move_down')} aria-label={t('collab_move_down')} disabled={status!=='connected'||i===values.blocks.length-1} onClick={()=>change({op:'move',block_id:b.id,before_id:values.blocks[i+2]?.id})}><ArrowDown size={16}/></button><button className="btn btn-icon" title={t('scene_remove')} aria-label={t('scene_remove')} disabled={status!=='connected'} onClick={()=>change({op:'delete',block_id:b.id})}><Trash2 size={16}/></button></div>{fields(b,b)}</details>)}
  <button className="btn btn-sm" disabled={status!=='connected'} onClick={()=>change({op:'insert',block_id:'c-'+crypto.randomUUID(),value:{type:'text',text:''}})}><Plus size={16}/>{t('collab_add_text')}</button>
 </div>;
}
