import React,{useEffect,useState} from 'react';
import {ArrowLeft,ChevronLeft,ChevronRight,ExternalLink,Pause,Play,RotateCcw,MonitorOff} from 'lucide-react';
import {api} from '../api.js';
import {useApp} from '../App.jsx';
import './presenter.css';

const time=(seconds)=>{const s=Math.max(0,Math.floor(Math.abs(seconds)));return `${seconds<0?'-':''}${String(Math.floor(s/60)).padStart(2,'0')}:${String(s%60).padStart(2,'0')}`};
export default function Presenter({deckId}){
 const {t}=useApp();const [room,setRoom]=useState(null),[notes,setNotes]=useState([]),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 useEffect(()=>{
   let active=true,timer;
   const init=async()=>{try{const r=await api.liveStart(deckId,{});const speaker=await api.liveSpeaker(deckId,r.session_id);
     if(!active)return;setRoom(r);setNotes(speaker.slides);setError('');
     timer=setInterval(async()=>{try{const state=await api.liveState(deckId,r.session_id);if(active){setRoom(prev=>({...prev,...state}));setError('');}}catch(e){if(active)setError(e.message)}},1000);
   }catch(e){if(active)setError(e.message)}};init();return()=>{active=false;clearInterval(timer)};
 },[deckId]);
 const command=async(action,extra={})=>{if(!room||busy)return;setBusy(true);try{
   const state=await api.liveControl(deckId,room.session_id,{action,...extra});setRoom(prev=>({...prev,...state}));setError('');
 }catch(e){setError(e.message)}finally{setBusy(false)}};
 const restart=async()=>{setBusy(true);try{const r=await api.liveStart(deckId,{restart:true,target_seconds:room?.target_seconds||900,main_slide_count:room?.main_slide_count});
   const speaker=await api.liveSpeaker(deckId,r.session_id);setNotes(speaker.slides);setRoom(r);setError('');
   // A fresh route mounts a new poller and audience frame for the replacement session.
   window.location.reload();
 }catch(e){setError(e.message);setBusy(false)}};
 const current=room?.slides[room.slide_index],next=room?.slides[room.slide_index+1];
 const button=(Icon,label,action,extra={})=><button type="button" className="btn btn-icon" title={label} aria-label={label} disabled={busy||!room} onClick={()=>command(action,extra)}><Icon size={20}/></button>;
 return <main className="presenter" id="main" tabIndex={-1}>
   <header className="presenter-toolbar"><a className="btn btn-icon" href={`#/deck/${deckId}/slides`} title={t('back')} aria-label={t('back')}><ArrowLeft size={20}/></a><h1>{t('presenter_console')}</h1>
     {room&&<a className="btn" href={room.audience_url} target="_blank" rel="noreferrer"><ExternalLink size={16}/>{t('audience')}</a>}
     <button className="btn btn-icon" type="button" title={t('restart_session')} aria-label={t('restart_session')} disabled={busy} onClick={restart}><RotateCcw size={18}/></button>
   </header>
   {error&&<p role="alert" className="presenter-error">{error}</p>}
   {!room&&!error&&<p role="status">{t('loading')}</p>}
   {room&&<>
    <div className="presenter-controls"><div className="flex items-center gap-2">{button(ChevronLeft,t('previous'),'previous')}
      <select className="field presenter-jump" aria-label={t('slide_title')} value={room.slide_index} disabled={busy} onChange={e=>command('goto',{slide_index:Number(e.target.value)})}>
        {room.slides.map((s,i)=><option key={s.id} value={i}>{i+1}. {s.title}{i>=room.main_slide_count?` (${t('support_slides')})`:''}</option>)}
      </select>{button(ChevronRight,t('next'),'next')}
      <span className="num presenter-stage">{room.fragment_index+1}/{current.steps}</span>
      <button type="button" className={`btn btn-icon ${room.blackout?'btn-active':''}`} title={t('blackout')} aria-label={t('blackout')} aria-pressed={room.blackout} disabled={busy} onClick={()=>command('blackout',{blackout:!room.blackout})}><MonitorOff size={20}/></button>
    </div><div className="presenter-clock"><output className={room.remaining_seconds<0?'overtime':''} aria-label={t('remaining')}>{time(room.remaining_seconds)}</output>
      <span className="num">{time(room.elapsed_seconds)}</span>{button(room.running?Pause:Play,t(room.running?'pause_timer':'start_timer'),room.running?'pause':'resume')}{button(RotateCcw,t('reset_timer'),'reset')}
      <label>{t('target_minutes')}<input className="field" type="number" min="0.5" max="240" step="0.5" defaultValue={room.target_seconds/60} onBlur={e=>{const v=Number(e.target.value);if(v>=.5&&v<=240)command('target',{target_seconds:Math.round(v*60)})}}/></label>
      <label>{t('main_slides')}<input className="field" type="number" min="1" max={room.slides.length} defaultValue={room.main_slide_count} onBlur={e=>{const v=Number(e.target.value);if(Number.isInteger(v)&&v>=1&&v<=room.slides.length)command('main',{main_slide_count:v})}}/></label>
    </div></div>
    <div className="presenter-workspace"><section className="presenter-current" aria-label={t('current_slide')}>
       <iframe key={room.session_id} src={room.audience_url} title={t('current_slide')} allow="fullscreen"/>
       <h2>{current.title}</h2>
    </section><aside className="presenter-notes"><h2>{t('notes')}</h2><div className="presenter-note-text" tabIndex={0}>{notes.find(n=>n.id===current.id)?.notes||t('notes_empty')}</div>
       <h2>{t('next_slide')}</h2>{next?<iframe src={api.slidePreviewUrl(deckId,next.id,next.revision)} title={t('next_slide')}/>:<p>{t('end_presentation')}</p>}
    </aside></div>
   </>}
 </main>;
}
