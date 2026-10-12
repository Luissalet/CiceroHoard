import * as Y from 'yjs';
let raw='';for await(const chunk of process.stdin)raw+=chunk;const req=JSON.parse(raw),doc=new Y.Doc();
const from64=v=>Uint8Array.from(Buffer.from(v,'base64'));
const to64=v=>Buffer.from(v).toString('base64');
if(req.state)Y.applyUpdate(doc,from64(req.state));
const map=doc.getMap('slide');
function set(key,value){
  if(['title','subtitle','notes'].includes(key)){
    let text=map.get(key);if(!(text instanceof Y.Text)){text=new Y.Text();map.set(key,text);}
    const old=text.toString(),next=String(value??'');let start=0;while(start<old.length&&start<next.length&&old[start]===next[start])start++;
    let tail=0;while(tail<old.length-start&&tail<next.length-start&&old[old.length-tail-1]===next[next.length-tail-1])tail++;
    text.delete(start,old.length-start-tail);text.insert(start,next.slice(start,next.length-tail));
  }else map.set(key,value);
}
if(!req.state)doc.transact(()=>{for(const [key,value] of Object.entries(req.seed))set(key,value);});
if(req.update)Y.applyUpdate(doc,from64(req.update));
if(req.patches)doc.transact(()=>{for(const [key,value] of Object.entries(req.patches))set(key,value);});
process.stdout.write(JSON.stringify({state:to64(Y.encodeStateAsUpdate(doc)),snapshot:map.toJSON()}));
