import React,{useEffect,useState} from 'react';
import {Play,Square,RefreshCw,Check,ScanEye,ChevronRight} from 'lucide-react';
import {useApp} from '../../App.jsx';
import {useDeck} from '../../components/deckContext.js';
import {Field} from '../../components/ui.jsx';
import {api} from '../../api.js';

export default function DesignLoop({slideId}){
 const {t}=useApp(),{deckId,run,reload}=useDeck();
 const [state,setState]=useState(null),[runs,setRuns]=useState([]),[working,setWorking]=useState(false),[rounds,setRounds]=useState(3),[critic,setCritic]=useState('structured'),[apply,setApply]=useState(false),[feedback,setFeedback]=useState('');
 const invoke=async body=>{const result=await api.design(deckId,body);setState(result);if(result.changed_slides?.length)await reload();return result;};
 const act=body=>run(t('lab_rendering'),async()=>{setWorking(true);try{await invoke(body);}finally{setWorking(false);}});
 useEffect(()=>{let active=true;api.design(deckId,{action:'list'}).then(r=>{if(active)setRuns(r.runs.filter(r=>r.slides.some(s=>s.slide_id===slideId)));}).catch(()=>{});return()=>{active=false;};},[deckId,slideId]);
 useEffect(()=>{if(!working||!state?.run_id)return;let active=true;const timer=setInterval(()=>{api.design(deckId,{action:'status',run_id:state.run_id}).then(r=>{if(active)setState(r);}).catch(()=>{});},2000);return()=>{active=false;clearInterval(timer);};},[working,state?.run_id,deckId]);
 const start=()=>run(t('lab_rendering'),async()=>{setWorking(true);try{const r=await invoke({action:'start',slide_id:slideId,critic,rounds,auto_apply:apply});await invoke({action:'run',run_id:r.run_id});}finally{setWorking(false);}});
 const item=state?.slides?.find(s=>s.slide_id===state.slide_id),review=state?.review_request;
 return <div className="space-y-4">
  <div className="flex flex-wrap items-end gap-3">
   <Field label={t('design_critic')}><select className="field" value={critic} disabled={working} onChange={e=>setCritic(e.target.value)}>{['structured','external','vision'].map(x=><option key={x} value={x}>{t('design_'+x)}</option>)}</select></Field>
   <Field label={t('design_rounds')}><input className="field w-24" type="number" min={1} value={rounds} disabled={working} onChange={e=>setRounds(Math.max(1,Number(e.target.value)||1))}/></Field>
   <label className="flex items-center gap-2 py-2 text-sm"><input type="checkbox" checked={apply} disabled={working} onChange={e=>setApply(e.target.checked)}/>{t('design_auto_apply')}</label>
   <button className="btn" disabled={working} onClick={start}><Play size={16}/>{t('design_start')}</button>
  </div>
  {!!runs.length&&<Field label={t('design_runs')}><select className="field max-w-xl" value={state?.run_id||''} onChange={e=>e.target.value&&act({action:'status',run_id:e.target.value})}><option value="">{t('design_choose_run')}</option>{runs.map(r=><option key={r.id} value={r.id}>{new Date(r.created_ts*1000).toLocaleString()} · {t('design_status_'+r.status)}</option>)}</select></Field>}
  {state&&<>
   <div className="flex flex-wrap items-center gap-3 border-y py-3" style={{borderColor:'var(--line)'}}><strong className="text-sm" role="status">{t('design_status_'+state.status)}</strong><span className="text-sm">{t('design_round')} {state.round} / {state.rounds||rounds}</span>
    <button className="btn btn-sm" title={t('poll_refresh')} onClick={()=>act({action:'status',run_id:state.run_id})}><RefreshCw size={15}/></button>
    <button className="btn btn-sm" disabled={working||!state.can_advance} onClick={()=>act({action:'step',run_id:state.run_id})}><ChevronRight size={15}/>{t('design_next')}</button>
    <button className="btn btn-sm" disabled={!state.best||working||state.status==='cancelled'||state.slides.every(s=>s.applied)} onClick={()=>act({action:'apply',run_id:state.run_id})}><Check size={15}/>{t('lab_apply')}</button>
    <button className="btn btn-sm" disabled={['complete','cancelled'].includes(state.status)} onClick={()=>run(t('busy_saving'),()=>invoke({action:'cancel',run_id:state.run_id}))}><Square size={15}/>{t('design_cancel')}</button>
   </div>
   {state.error&&<p role="alert" className="text-sm" style={{color:'var(--danger)'}}>{state.error.message}</p>}
   {state.best&&<div className="grid gap-4 lg:grid-cols-[minmax(0,3fr)_minmax(220px,1fr)]">
    <img src={state.best.png_url} alt={t('lab_preview')} className="w-full" style={{aspectRatio:'16/9',objectFit:'contain'}}/>
    <div className="space-y-3"><h3 className="font-semibold text-sm">{state.best.label}</h3><dl className="text-sm grid grid-cols-2 gap-2"><dt>{t('lab_errors')}</dt><dd>{state.best.metrics.errors}</dd><dt>{t('lab_warnings')}</dt><dd>{state.best.metrics.warnings}</dd><dt>{t('lab_font')}</dt><dd>{state.best.metrics.min_font_px||'-'} px</dd></dl>{state.best.rationale&&<p className="text-sm">{state.best.rationale}</p>}
     {review&&<><Field label={t('design_feedback')}><textarea className="field" rows={5} value={feedback} onChange={e=>setFeedback(e.target.value)}/></Field><div className="flex flex-wrap gap-2"><button className="btn btn-sm" disabled={working||!feedback.trim()} onClick={()=>act({action:'feedback',run_id:state.run_id,variant_id:review.variant_id,png_sha256:review.png_sha256,feedback:{issues:[feedback],accept:false}})}><ScanEye size={15}/>{t('design_correct')}</button><button className="btn btn-sm" disabled={working} onClick={()=>act({action:'feedback',run_id:state.run_id,variant_id:review.variant_id,png_sha256:review.png_sha256,feedback:{accept:true}})}><Check size={15}/>{t('design_accept')}</button></div></>}
    </div>
   </div>}
   <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">{item?.candidates.map((c,i)=><button key={c.id} className="text-left border p-2" style={{borderRadius:6,borderColor:c.id===state.best?.id?'var(--accent)':'var(--line)'}} disabled={working||state.evaluation_mode!=='external'||state.index>=state.slides_total||state.status==='cancelled'} onClick={()=>act({action:'review',run_id:state.run_id,variant_id:c.id})}><img src={c.png_url} alt={c.label} className="w-full" style={{aspectRatio:'16/9',objectFit:'contain'}}/><div className="flex justify-between gap-2 text-xs mt-2"><span>{c.label}</span><span>{c.metrics.errors} / {c.metrics.warnings}</span></div></button>)}</div>
  </>}
 </div>;
}
