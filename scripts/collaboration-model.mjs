import * as Y from 'yjs';

const textFields=new Set(['title','subtitle','notes','text','label','detail','caption','name','question','left_title','right_title']);
export function editText(text,next){
 const old=text.toString();next=String(next??'');let start=0,tail=0;
 while(start<old.length&&start<next.length&&old[start]===next[start])start++;
 while(tail<old.length-start&&tail<next.length-start&&old.at(-tail-1)===next.at(-tail-1))tail++;
 if(old.length-start-tail)text.delete(start,old.length-start-tail);
 if(next.length-start-tail)text.insert(start,next.slice(start,next.length-tail));
}
const sequence=value=>value instanceof Y.Map&&value.get('_kind')==='sequence';
function emptySequence(){const result=new Y.Map();result.set('_kind','sequence');result.set('entries',new Y.Map());result.set('order',new Y.Array());result.set('deleted',new Y.Map());return result;}
export function ids(seq){
 const order=seq.get('order').toArray(),last=new Map(order.map((id,i)=>[id,i]));
 return order.filter((id,i)=>last.get(id)===i&&seq.get('entries').has(id)&&!seq.get('deleted').get(id));
}
export function plain(value){
 if(value instanceof Y.Text)return value.toString();
 if(sequence(value))return ids(value).map(id=>plain(value.get('entries').get(id)));
 if(value instanceof Y.Map)return Object.fromEntries(Array.from(value.entries()).map(([key,item])=>[key,plain(item)]));
 return value;
}
function encoded(value,key=''){
 if(Array.isArray(value)){const seq=emptySequence();return {value:seq,initialize:()=>syncSequence(seq,value)};}
 if(value&&typeof value==='object'){const map=new Y.Map();return {value:map,initialize:()=>syncMap(map,value)};}
 if(typeof value==='string'&&textFields.has(key)){const text=new Y.Text();return {value:text,initialize:()=>text.insert(0,value)};}
 return {value,initialize:()=>{}};
}
function assign(map,key,next,hint=key){
 const old=map.get(key);
 if(old instanceof Y.Text&&typeof next==='string'){editText(old,next);return;}
 if(sequence(old)&&Array.isArray(next)){syncSequence(old,next);return;}
 if(old instanceof Y.Map&&!sequence(old)&&next&&typeof next==='object'&&!Array.isArray(next)){syncMap(old,next);return;}
 if(JSON.stringify(plain(old))===JSON.stringify(next))return;
 const item=encoded(next,hint);map.set(key,item.value);item.initialize();
}
function syncMap(map,next){
 for(const key of map.keys())if(!(key in next))map.delete(key);
 for(const [key,item] of Object.entries(next))assign(map,key,item);
}
function move(seq,id,before){
 const order=seq.get('order');
 for(let i=order.length-1;i>=0;i--)if(order.get(i)===id)order.delete(i,1);
 const index=before==null?order.length:order.toArray().indexOf(before);
 if(before!=null&&index<0)throw Error('The order target does not exist');
 order.insert(index,[id]);
}
function syncSequence(seq,next){
 const oldIds=ids(seq),entries=seq.get('entries'),deleted=seq.get('deleted');
 const wanted=next.map((value,i)=>String(value&&typeof value==='object'&&value.id||oldIds[i]||'item-'+i));
 if(new Set(wanted).size!==wanted.length)throw Error('Sequence identities must be distinct');
 for(const id of oldIds)if(!wanted.includes(id))deleted.set(id,true);
 for(let i=0;i<next.length;i++){
  const id=wanted[i];if(deleted.get(id))deleted.set(id,false);
  assign(entries,id,next[i],typeof next[i]==='string'?'text':id);
 }
 // Move only items that differ from the requested order; nested shared maps stay put.
 for(let i=wanted.length-1;i>=0;i--){const current=ids(seq),position=current.indexOf(wanted[i]);
  if(position<0||current[position+1]!==wanted[i+1]||(i===wanted.length-1&&position!==current.length-1))move(seq,wanted[i],wanted[i+1]);}
}

export function initialize(doc,seed){
 const map=doc.getMap('slide');
 doc.transact(()=>{
  for(const key of ['title','subtitle','notes'])if(!map.has(key))assign(map,key,seed[key]||'');
  if(!sequence(map.get('blocks_v2'))){const seq=emptySequence();map.set('blocks_v2',seq);syncSequence(seq,map.get('blocks')||seed.blocks||[]);}
 });
 return map;
}
export function snapshot(doc){const map=doc.getMap('slide');return {title:plain(map.get('title')),subtitle:plain(map.get('subtitle')),notes:plain(map.get('notes')),blocks:plain(map.get('blocks_v2'))};}
export function patch(doc,patches){
 const map=doc.getMap('slide');doc.transact(()=>{for(const [key,value] of Object.entries(patches)){
  if(key==='blocks')syncSequence(map.get('blocks_v2'),value);else assign(map,key,value);
 }});
}
function child(value,key){
 if(sequence(value)){const id=typeof key==='number'?ids(value)[key]:key;return {map:value.get('entries'),key:id};}
 if(value instanceof Y.Map)return {map:value,key:String(key)};
 throw Error('The field path is not a shared object');
}
export function operation(doc,op){
 const root=doc.getMap('slide'),blocks=root.get('blocks_v2'),entries=blocks.get('entries');
 doc.transact(()=>{
  if(op.op==='insert'){
   if(!op.block_id||!op.value||typeof op.value!=='object')throw Error('Insert needs block_id and a block');
   assign(entries,op.block_id,{...op.value,id:op.block_id});blocks.get('deleted').set(op.block_id,false);move(blocks,op.block_id,op.before_id);return;
  }
  if(op.op==='move'){if(!ids(blocks).includes(op.block_id))throw Error('The block does not exist');move(blocks,op.block_id,op.before_id);return;}
  if(op.op==='delete'&&op.block_id&&!(op.path||[]).length){blocks.get('deleted').set(op.block_id,true);return;}
  let value=op.block_id?entries.get(op.block_id):root;
  if(op.block_id&&(!value||blocks.get('deleted').get(op.block_id)))throw Error('The block was deleted');
  const path=op.path||[];if(!path.length)throw Error('Supply a field path');
  for(const key of path.slice(0,-1)){const field=child(value,key);value=field.map.get(field.key);}
  const field=child(value,path.at(-1));
  if(op.op==='set')assign(field.map,field.key,op.value);
  else if(op.op==='delete')field.map.delete(field.key);
  else if(op.op==='text'){
   const text=field.map.get(field.key);if(!(text instanceof Y.Text))throw Error('Text edits need a shared text field');
   if(op.index<0||op.index>text.length||op.index+(op.delete||0)>text.length)throw Error('Invalid text range');
   if(op.delete)text.delete(op.index,op.delete);if(op.text)text.insert(op.index,op.text);
  }else throw Error('Unknown object operation');
 });
}
