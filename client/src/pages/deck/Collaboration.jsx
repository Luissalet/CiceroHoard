import React,{useEffect,useRef,useState} from 'react';
import * as Y from 'yjs';
import {useApp} from '../../App.jsx';
import {useDeck} from '../../components/deckContext.js';
import {Field} from '../../components/ui.jsx';

const decode=v=>Uint8Array.from(atob(v),c=>c.charCodeAt(0));
const encode=v=>btoa(Array.from(v,b=>String.fromCharCode(b)).join(''));
export default function Collaboration({slideId}){
 const {t}=useApp(),{deckId,reload}=useDeck();const [values,setValues]=useState({title:'',subtitle:'',notes:''}),[peers,setPeers]=useState([]),[status,setStatus]=useState('connecting');
 const docRef=useRef(null),socketRef=useRef(null);
 useEffect(()=>{const doc=new Y.Doc(),actor=crypto.randomUUID(),socket=new WebSocket(`${location.protocol==='https:'?'wss':'ws'}://${location.host}/api/decks/${deckId}/slides/${slideId}/collaboration`);docRef.current=doc;socketRef.current=socket;
  const map=doc.getMap('slide');const observe=()=>setValues({title:String(map.get('title')||''),subtitle:String(map.get('subtitle')||''),notes:String(map.get('notes')||'')});map.observeDeep(observe);
  doc.on('update',(update,origin)=>{if(origin!=='remote'&&socket.readyState===1)socket.send(JSON.stringify({action:'apply',actor,update:encode(update)}));});
  socket.onmessage=event=>{const r=JSON.parse(event.data);if(r.error){setStatus(r.error);return;}Y.applyUpdate(doc,decode(r.state),'remote');setPeers(r.presence);setStatus('connected');observe();};
  socket.onopen=()=>socket.send(JSON.stringify({action:'presence',actor,label:actor.slice(0,8)}));socket.onerror=()=>setStatus('error');socket.onclose=()=>setStatus('closed');
  const heartbeat=setInterval(()=>{if(socket.readyState===1)socket.send(JSON.stringify({action:'presence',actor,label:actor.slice(0,8)}));},10000);
  return()=>{clearInterval(heartbeat);socket.close();doc.destroy();void reload();};
 },[deckId,slideId,reload]);
 function edit(key,next){const doc=docRef.current,map=doc.getMap('slide'),text=map.get(key);if(!(text instanceof Y.Text))return;const old=text.toString();let start=0;while(start<old.length&&start<next.length&&old[start]===next[start])start++;let tail=0;while(tail<old.length-start&&tail<next.length-start&&old.at(-tail-1)===next.at(-tail-1))tail++;
  doc.transact(()=>{text.delete(start,old.length-start-tail);text.insert(start,next.slice(start,next.length-tail));});}
 return <div className="space-y-3 max-w-3xl"><div role="status" className="text-sm">{['connecting','connected','closed','error'].includes(status)?t('collab_'+status):status} · {peers.length}</div><div className="flex gap-3 flex-wrap">{peers.map(p=><span key={p.actor} className="text-xs" style={{color:p.color}}>{p.label}</span>)}</div>
  {['title','subtitle','notes'].map(key=><Field key={key} label={t(key==='notes'?'speaker_notes':'slide_'+key)}>{key==='notes'?<textarea className="field" value={values[key]} rows={8} disabled={status!=='connected'} onChange={e=>edit(key,e.target.value)}/>:<input className="field" value={values[key]} disabled={status!=='connected'} onChange={e=>edit(key,e.target.value)}/>}</Field>)}
 </div>;
}
