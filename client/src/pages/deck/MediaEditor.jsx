import React,{useEffect,useState} from 'react';
import {Upload,Link2,ImagePlus} from 'lucide-react';
import {api} from '../../api.js';
import {useApp} from '../../App.jsx';
import {useDeck} from '../../components/deckContext.js';
import {Field} from '../../components/ui.jsx';

export default function MediaEditor({block,onChange,disabled}){
 const {t}=useApp();const {deckId,run}=useDeck();const [items,setItems]=useState([]),[url,setUrl]=useState('');
 const load=()=>api.media(deckId).then(r=>setItems(r.items||[]));
 useEffect(()=>{let active=true;api.media(deckId).then(r=>{if(active)setItems(r.items||[])}).catch(()=>{});return()=>{active=false}},[deckId]);
 const imported=async result=>{if(result.kind!==block.type)throw new Error(t('media_wrong_kind'));await load();onChange({...block,asset_id:result.asset_id,poster_id:result.poster_id||null,start:0,end:null})};
 const upload=file=>file&&run(t('busy_uploading'),async()=>imported(await api.mediaUpload(deckId,file)));
 const fromUrl=()=>run(t('busy_uploading'),async()=>{await imported(await api.mediaImport(deckId,{url}));setUrl('')});
 const chosen=items.find(x=>x.asset_id===block.asset_id);
 const set=(key,value)=>onChange({...block,[key]:value});
 return <div className="space-y-2">
  <Field label={t('media_asset')}><select className="field" disabled={disabled} value={block.asset_id||''} onChange={e=>{const item=items.find(x=>x.asset_id===e.target.value);onChange({...block,asset_id:e.target.value,poster_id:item?.poster_id||null,start:0,end:null})}}><option value="">{t('none')}</option>{items.filter(x=>x.kind===block.type).map(x=><option key={x.asset_id} value={x.asset_id}>{x.filename} ({x.duration.toFixed(1)} s)</option>)}</select></Field>
  <label className="btn btn-sm"><Upload size={16}/>{t('media_upload')}<input className="sr-only-live" type="file" accept={block.type==='video'?'.mp4,.webm,.mov':'.mp3,.wav,.ogg,.m4a,.flac'} disabled={disabled} onChange={e=>{upload(e.target.files?.[0]);e.target.value=''}}/></label>
  <div className="flex gap-2"><input className="field min-w-0" type="url" value={url} disabled={disabled} placeholder="https://" aria-label={t('media_url')} onChange={e=>setUrl(e.target.value)}/><button type="button" className="btn btn-icon shrink-0" disabled={disabled||!url} title={t('media_import_url')} aria-label={t('media_import_url')} onClick={fromUrl}><Link2 size={18}/></button></div>
  {block.asset_id&&<div>{block.type==='video'?<video src={api.assetUrl(block.asset_id)} poster={block.poster_id?api.assetUrl(block.poster_id):undefined} controls preload="metadata" style={{width:'100%',maxHeight:220}}/>:<audio src={api.assetUrl(block.asset_id)} controls preload="metadata" style={{width:'100%'}}/>}</div>}
  <Field label={t('image_caption')}><input className="field" value={block.caption||''} disabled={disabled} onChange={e=>set('caption',e.target.value)}/></Field>
  <div className="grid gap-2 sm:grid-cols-3">{[['start',t('media_start'),0,chosen?.duration,.1],['end',t('media_end'),0,chosen?.duration,.1],['playback_rate',t('media_rate'),.25,4,.25]].map(([key,label,min,max,step])=><Field key={key} label={label}><input className="field" type="number" min={min} max={max} step={step} disabled={disabled} value={block[key]??''} onChange={e=>set(key,e.target.value)}/></Field>)}</div>
  <Field label={t('media_volume')}><input className="w-full" type="range" min="0" max="1" step=".01" value={block.volume??1} disabled={disabled} onChange={e=>set('volume',Number(e.target.value))}/></Field>
  <div className="flex flex-wrap gap-3">{['autoplay','loop','muted','controls'].map(key=><label key={key} className="flex items-center gap-1 text-sm"><input type="checkbox" checked={!!block[key]} disabled={disabled} onChange={e=>set(key,e.target.checked)}/>{t('media_'+key)}</label>)}</div>
  {block.type==='video'&&<><Field label={t('image_fit')}><select className="field" disabled={disabled} value={block.fit||'contain'} onChange={e=>set('fit',e.target.value)}>{['contain','cover'].map(v=><option key={v} value={v}>{t('image_'+v)}</option>)}</select></Field>
   <label className="btn btn-sm"><ImagePlus size={16}/>{t('media_poster')}<input className="sr-only-live" type="file" accept="image/png,image/jpeg,image/webp" disabled={disabled} onChange={e=>{const file=e.target.files?.[0];if(file)run(t('busy_uploading'),async()=>{const result=await api.assetUpload(deckId,file);set('poster_id',result.asset_id)});e.target.value=''}}/></label>
  </>}
  <details><summary>{t('media_subtitles')}</summary><textarea className="field mt-2" rows={4} disabled={disabled} value={block.subtitles||''} placeholder="WEBVTT" aria-label={t('media_subtitles')} onChange={e=>set('subtitles',e.target.value||null)}/></details>
 </div>;
}
