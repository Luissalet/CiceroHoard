import React,{useState} from 'react';
import {Wand2,ScanEye,Check,BarChart3,Users,Plus,Play,Pause,RefreshCw} from 'lucide-react';
import {useApp} from '../../App.jsx';
import {useDeck} from '../../components/deckContext.js';
import {Field} from '../../components/ui.jsx';
import {api} from '../../api.js';
import Collaboration from './Collaboration.jsx';
import DesignLoop from './DesignLoop.jsx';
import Benchmark from './Benchmark.jsx';

export default function VisualLab(){
 const {t}=useApp(),{deckId,deck,run,busy,reload}=useDeck();
 const [mode,setMode]=useState('variants'),[slide,setSlide]=useState(deck.slides[0]?.id||''),[variants,setVariants]=useState([]),[selected,setSelected]=useState(null),[review,setReview]=useState(null);
 const [polls,setPolls]=useState([]),[question,setQuestion]=useState(''),[options,setOptions]=useState(''),[connection,setConnection]=useState({kind:'database',database_url:'',query:'',spreadsheet_id:'',range:'Sheet1',title:''});
 const generate=()=>run(t('lab_generating'),async()=>{const r=await api.visualLab(deckId,{action:'variants',slide_id:slide});setVariants(r.variants);setSelected(null);setReview(null);});
 const compare=()=>run(t('lab_rendering'),async()=>{const r=await api.visualLab(deckId,{action:'compare',variant_ids:variants.map(v=>v.id)});setVariants(r.ranked);setSelected(r.ranked[0]);});
 const apply=()=>run(t('busy_saving'),async()=>{await api.visualLab(deckId,{action:'apply',variant_id:selected.id});await reload();setVariants([]);setSelected(null);});
 const critique=()=>run(t('lab_critique'),async()=>{const r=await api.visualLab(deckId,{action:'critique',variant_id:selected.id,use_model:true});setReview(r.review);});
 const loadPolls=async()=>{const r=await api.poll(deckId,{action:'list'});setPolls(r.polls);};
 return <div className="space-y-4">
  <div role="tablist" aria-label={t('tab_lab')} className="flex flex-wrap gap-2">
   {['design','variants','benchmark','polls','collaboration','connections'].map(key=><button key={key} role="tab" aria-selected={mode===key} className="btn btn-sm" onClick={()=>{setMode(key);if(key==='polls')void run(t('busy_loading'),loadPolls);}}>{t('lab_'+key)}</button>)}
  </div>
  <Field label={t('lab_slide')}><select className="field max-w-xl" value={slide} disabled={busy} onChange={e=>{setSlide(e.target.value);setVariants([]);setSelected(null);}}>{deck.slides.map(s=><option key={s.id} value={s.id}>{s.position}. {s.title}</option>)}</select></Field>
  {mode==='design'&&slide&&<DesignLoop key={slide} slideId={slide}/>}
  {mode==='benchmark'&&<Benchmark/>}
  {mode==='variants'&&<>
   <div className="flex flex-wrap gap-2"><button className="btn" disabled={busy||!slide} onClick={generate}><Wand2 size={16}/>{t('lab_generate')}</button><button className="btn" disabled={busy||!variants.length} onClick={compare}><ScanEye size={16}/>{t('lab_compare')}</button><button className="btn" disabled={busy||!selected} onClick={apply}><Check size={16}/>{t('lab_apply')}</button><button className="btn" disabled={busy||!selected} onClick={critique}>{t('lab_critique')}</button></div>
   <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">{variants.map(v=><button key={v.id} className="text-left border p-3 space-y-2" style={{borderColor:selected?.id===v.id?'var(--accent)':'var(--line)',borderRadius:6}} onClick={()=>setSelected(v)}>
    {v.png_url?<img src={v.png_url} alt={v.label} className="w-full" style={{aspectRatio:'16/9',objectFit:'contain'}}/>:<div className="border-b py-6" style={{aspectRatio:'16/9'}}><span>{t('lab_style_'+v.label)}</span></div>}
    <strong className="block text-sm">{t('lab_style_'+v.label)}</strong>{v.metrics&&<div className="flex flex-wrap gap-3 text-xs"><span>{t('lab_errors')}: {v.metrics.errors}</span><span>{t('lab_warnings')}: {v.metrics.warnings}</span><span>{t('lab_font')}: {v.metrics.min_font_px||'-'} px</span></div>}
   </button>)}</div>
   {selected&&!selected.png_url&&<iframe title={t('lab_preview')} src={selected.preview_url} className="w-full border-0" style={{aspectRatio:'16/9'}}/>}
   {review&&<div className="grid gap-4 md:grid-cols-2"><ul>{(review.strengths||[]).map((s,i)=><li key={i}>{s}</li>)}</ul><ul>{(review.issues||[]).map((s,i)=><li key={i}>{s}</li>)}</ul></div>}
  </>}
  {mode==='polls'&&<>
   <div className="grid gap-3 max-w-2xl"><Field label={t('poll_question')}><input className="field" value={question} onChange={e=>setQuestion(e.target.value)}/></Field><Field label={t('poll_options')}><textarea className="field" value={options} rows={4} onChange={e=>setOptions(e.target.value)}/></Field><button className="btn" disabled={busy} onClick={()=>run(t('busy_saving'),async()=>{await api.poll(deckId,{action:'create',question,options:options.split('\n').map(s=>s.trim()).filter(Boolean)});await loadPolls();})}><Plus size={16}/>{t('poll_create')}</button></div>
   {polls.map(p=><section key={p.id} className="border-t py-3" style={{borderColor:'var(--line)'}}><h3 className="font-semibold text-sm">{p.question}</h3><div className="flex flex-wrap gap-2 mt-2"><button className="btn btn-sm" disabled={busy} onClick={()=>run(t('busy_saving'),async()=>{await api.poll(deckId,{action:p.open?'close':'open',poll_id:p.id});await loadPolls();})}>{p.open?<Pause size={14}/>:<Play size={14}/>} {t(p.open?'poll_close':'poll_open')}</button><button className="btn btn-sm" onClick={()=>run(t('busy_loading'),loadPolls)}><RefreshCw size={14}/>{t('poll_refresh')}</button><button className="btn btn-sm" disabled={busy||!slide} onClick={()=>run(t('busy_saving'),async()=>{const b=await api.poll(deckId,{action:'block',poll_id:p.id});const current=deck.slides.find(s=>s.id===slide);await api.slideUpdate(deckId,slide,{blocks:[...current.blocks,b.block],expected_revision:current.revision});await reload();})}><Plus size={14}/>{t('poll_insert')}</button></div><ul className="mt-2 text-sm">{p.options.map((o,i)=><li key={i}>{o}: {p.counts[i]}</li>)}</ul></section>)}
  </>}
  {mode==='collaboration'&&slide&&<Collaboration key={slide} slideId={slide}/>}
  {mode==='connections'&&<div className="max-w-2xl space-y-3"><Field label={t('connector_kind')}><select className="field" value={connection.kind} onChange={e=>setConnection({...connection,kind:e.target.value})}><option value="database">SQL</option><option value="sheet">{t('connector_sheet')}</option></select></Field>
   <Field label={t('connector_title')}><input className="field" value={connection.title} onChange={e=>setConnection({...connection,title:e.target.value})}/></Field>
   {(connection.kind==='database'?['database_url','query']:['spreadsheet_id','range']).map(key=><Field key={key} label={t('connector_'+key)}><input className="field" value={connection[key]} onChange={e=>setConnection({...connection,[key]:e.target.value})}/></Field>)}
   <button className="btn" disabled={busy} onClick={()=>run(t('busy_saving'),async()=>{await api.connector(deckId,connection);await reload();})}><Plus size={16}/>{t('connector_create')}</button>
  </div>}
 </div>;
}
