import React,{useEffect,useState} from 'react';
import {Save,RotateCcw} from 'lucide-react';
import {api} from '../../api.js';
import {useApp} from '../../App.jsx';
import {useDeck} from '../../components/deckContext.js';
import {Field,Section} from '../../components/ui.jsx';

// Slide numbering and progress indicator; the same settings drive preview, HTML, PPTX and templates.
const base={number:'auto',progress:'none',position:'bottom',thickness:6,main_slides:null,show_title:true,on_cover:false};
export default function ChromeEditor(){
 const {t}=useApp();const {deckId,deck,run,busy,reload}=useDeck();
 const [draft,setDraft]=useState(base),[error,setError]=useState('');
 useEffect(()=>{let active=true;api.chrome(deckId).then(r=>{if(active)setDraft({...base,...r.settings})}).catch(e=>{if(active)setError(e.message)});return()=>{active=false}},[deckId]);
 const update=(key,value)=>setDraft({...draft,[key]:value});
 const save=()=>run(t('busy_saving'),async()=>{const r=await api.chromeSet(deckId,draft);setDraft({...base,...r.settings});await reload();return true});
 const reset=()=>run(t('busy_saving'),async()=>{const r=await api.chromeReset(deckId);setDraft({...base,...r.settings});await reload();return true});
 const total=(deck.slides||[]).length;
 return <Section title={t('chrome_title')}>
  {error&&<p role="alert">{error}</p>}
  <div className="grid gap-2 sm:grid-cols-2">
   <Field label={t('chrome_number')}><select className="field" value={draft.number} disabled={!!busy} onChange={e=>update('number',e.target.value)}>{['auto','n_total','n','none'].map(v=><option key={v} value={v}>{t('chrome_number_'+v)}</option>)}</select></Field>
   <Field label={t('chrome_progress')}><select className="field" value={draft.progress} disabled={!!busy} onChange={e=>update('progress',e.target.value)}>{['none','bar','segments'].map(v=><option key={v} value={v}>{t('chrome_progress_'+v)}</option>)}</select></Field>
   {draft.progress!=='none'&&<><Field label={t('chrome_position')}><select className="field" value={draft.position} disabled={!!busy} onChange={e=>update('position',e.target.value)}>{['bottom','top'].map(v=><option key={v} value={v}>{t('chrome_position_'+v)}</option>)}</select></Field>
   <Field label={t('chrome_thickness')}><input className="field" type="number" min="2" max="20" step="1" value={draft.thickness} disabled={!!busy} onChange={e=>update('thickness',Number(e.target.value))}/></Field></>}
   <Field label={t('chrome_main')}><input className="field" type="number" min="1" max={total||1} step="1" placeholder={String(total)} value={draft.main_slides??''} disabled={!!busy} onChange={e=>update('main_slides',e.target.value?Number(e.target.value):null)}/></Field>
   <div className="flex flex-col gap-1 justify-end text-sm">
    <label className="flex gap-2 items-center"><input type="checkbox" checked={draft.show_title} disabled={!!busy} onChange={e=>update('show_title',e.target.checked)}/>{t('chrome_show_title')}</label>
    <label className="flex gap-2 items-center"><input type="checkbox" checked={draft.on_cover} disabled={!!busy} onChange={e=>update('on_cover',e.target.checked)}/>{t('chrome_on_cover')}</label>
   </div>
  </div>
  <p className="help mt-2">{t('chrome_main_help')}</p>
  <div className="flex gap-2 mt-3"><button type="button" className="btn" disabled={!!busy} onClick={save}><Save size={16}/>{t('save')}</button><button type="button" className="btn btn-icon" disabled={!!busy} title={t('chrome_reset')} aria-label={t('chrome_reset')} onClick={reset}><RotateCcw size={18}/></button></div>
 </Section>;
}
