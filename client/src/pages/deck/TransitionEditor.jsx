import React,{useEffect,useState} from 'react';
import {Save,RotateCcw} from 'lucide-react';
import {api} from '../../api.js';
import {useApp} from '../../App.jsx';
import {useDeck} from '../../components/deckContext.js';
import {Field,Section} from '../../components/ui.jsx';

const base={effect:'fade',duration_ms:700,easing:'ease-in-out',group:'default',unmatched:true};
export default function TransitionEditor(){
 const {t}=useApp();const {deckId,deck,run,busy,reload}=useDeck();
 const [settings,setSettings]=useState({}),[scope,setScope]=useState(''),[draft,setDraft]=useState(base),[motion,setMotion]=useState(null),[catalog,setCatalog]=useState(null),[error,setError]=useState('');
 useEffect(()=>{let active=true;Promise.all([api.transitions(deckId),api.animations(deckId),api.animationCatalogue()]).then(([s,m,c])=>{if(active){setSettings(s);setDraft(s.default||base);setMotion(m);setCatalog(c)}}).catch(e=>{if(active)setError(e.message)});return()=>{active=false}},[deckId]);
 const choose=value=>{setScope(value);setDraft(value?settings.slides?.[value]||settings.default||base:settings.default||base)};
 const save=()=>run(t('busy_saving'),async()=>{const result=await api.transitionsSet(deckId,scope?{slides:{[scope]:draft}}:{default:draft});setSettings(result);await reload();return true});
 const reset=()=>run(t('busy_saving'),async()=>{setSettings(await api.transitionsReset(deckId));setDraft(base);setScope('');await reload();return true});
 const update=(key,value)=>setDraft({...draft,[key]:value});
 return <Section title={t('transitions_title')}>
  {error&&<p role="alert">{error}</p>}
  <div className="grid gap-2 sm:grid-cols-2">
   <Field label={t('transition_scope')}><select className="field" value={scope} disabled={!!busy} onChange={e=>choose(e.target.value)}><option value="">{t('transition_default')}</option>{deck.slides.map((s,i)=><option key={s.id} value={s.id}>{i+1}. {s.title}</option>)}</select></Field>
   <Field label={t('transition_effect')}><select className="field" value={draft.effect} disabled={!!busy} onChange={e=>update('effect',e.target.value)}>{['none','fade','slide','convex','concave','zoom','morph'].map(v=><option key={v} value={v}>{t('transition_'+v)}</option>)}</select></Field>
   <Field label={t('motion_duration')}><input className="field" type="number" min="100" max="5000" step="50" disabled={!!busy} value={draft.duration_ms} onChange={e=>update('duration_ms',Number(e.target.value))}/></Field>
   <Field label={t('transition_easing')}><select className="field" value={draft.easing} disabled={!!busy} onChange={e=>update('easing',e.target.value)}>{['linear','ease','ease-in','ease-out','ease-in-out'].map(v=><option key={v} value={v}>{v}</option>)}</select></Field>
   {draft.effect==='morph'&&<><Field label={t('transition_group')}><input className="field" maxLength={80} value={draft.group} disabled={!!busy} onChange={e=>update('group',e.target.value)}/></Field><label className="flex gap-2 items-center text-sm"><input type="checkbox" checked={draft.unmatched} disabled={!!busy} onChange={e=>update('unmatched',e.target.checked)}/>{t('transition_unmatched')}</label></>}
   {catalog&&<Field label={t('native_transition')}><select className="field" value={draft.native_effect||''} disabled={!!busy} onChange={e=>update('native_effect',e.target.value||null)}><option value="">{t('native_transition_same')}</option>{catalog.transitions.map(v=><option key={v} value={v}>{v}</option>)}</select></Field>}
  </div>
  <div className="flex gap-2 mt-3"><button type="button" className="btn" disabled={!!busy} onClick={save}><Save size={16}/>{t('save')}</button><button type="button" className="btn btn-icon" disabled={!!busy} title={t('transition_reset')} aria-label={t('transition_reset')} onClick={reset}><RotateCcw size={18}/></button></div>
  {motion&&catalog&&<details className="mt-3 border-t pt-3" style={{borderColor:'var(--line)'}}><summary>{t('native_motion')}</summary><div className="grid gap-2 mt-2 sm:grid-cols-2">
   <Field label={t('motion_mode')}><select className="field" value={motion.mode} disabled={!!busy} onChange={e=>setMotion({...motion,mode:e.target.value})}>{catalog.modes.map(v=><option key={v} value={v}>{t('motion_mode_'+v)}</option>)}{Object.entries(catalog.effects).map(([group,values])=><optgroup key={group} label={group}>{values.map(v=><option key={v} value={v}>{v}</option>)}</optgroup>)}</select></Field>
   <Field label={t('motion_trigger')}><select className="field" value={motion.trigger} disabled={!!busy} onChange={e=>setMotion({...motion,trigger:e.target.value})}>{catalog.triggers.map(v=><option key={v} value={v}>{t('trigger_'+v)}</option>)}</select></Field>
   <Field label={t('motion_seconds')}><input className="field" type="number" min=".05" max="10" step=".05" value={motion.duration} disabled={!!busy} onChange={e=>setMotion({...motion,duration:Number(e.target.value)})}/></Field>
  </div><button className="btn mt-2" type="button" disabled={!!busy} onClick={()=>run(t('busy_saving'),async()=>{setMotion(await api.animationsSet(deckId,{mode:motion.mode,trigger:motion.trigger,duration:motion.duration}));return true})}><Save size={16}/>{t('save')}</button></details>}
 </Section>;
}
