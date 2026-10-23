import React, { useEffect, useState } from 'react';
import { api } from '../../api.js';
import { goReplace, useApp } from '../../App.jsx';
import { useDeck } from '../../components/deckContext.js';
import { Empty } from '../../components/ui.jsx';

function clock(seconds) {
  const amount = Math.abs(seconds);
  return `${seconds < 0 ? '−' : ''}${Math.floor(amount / 60)}:${String(amount % 60).padStart(2, '0')}`;
}

export default function Rehearsal() {
  const { t, notify, lang } = useApp();
  const { deckId, deck, run, busy, rehearsalOptions, setRehearsalOptions } = useDeck();
  const slides = deck.slides || [];
  const options = rehearsalOptions || {duration_minutes: 15, words_per_minute: 130,
    pause_seconds: 10, main_slides: slides.length, reserve_percent: 10};
  const [plan, setPlan] = useState(null);
  const notes = id => slides.find(slide => slide.id === id)?.notes || '';
  const edit = id => goReplace(`deck/${deckId}/slides?slide=${encodeURIComponent(id)}`);
  const change = event => {
    setRehearsalOptions({...options, [event.target.name]: event.target.value});
    setPlan(null);
  };
  const calculate = async event => {
    event?.preventDefault();
    setPlan(null);
    const result = await run(t('rehearsal_calculating'), () => api.rehearsal(deckId, {
      duration_minutes: Number(options.duration_minutes), words_per_minute: Number(options.words_per_minute),
      pause_seconds: Number(options.pause_seconds), main_slides: Number(options.main_slides),
      reserve_ratio: Number(options.reserve_percent) / 100,
      language: lang,
    }));
    if (result) setPlan(result);
  };
  useEffect(() => { if (slides.length) void calculate(); }, [deckId, deck.updated_at, lang]);
  const copy = async () => {
    try { await navigator.clipboard.writeText(plan.text); notify(t('rehearsal_copied')); }
    catch { notify(t('rehearsal_copy_failed')); }
  };
  const downloadUrl = plan ? `/api/decks/${encodeURIComponent(deckId)}/rehearsal.txt?${new URLSearchParams({
    duration_minutes: plan.target_seconds / 60, words_per_minute: plan.words_per_minute,
    pause_seconds: plan.pause_seconds_per_slide, main_slides: plan.main_slides,
    reserve_ratio: Number(options.reserve_percent) / 100, language: lang,
  })}` : undefined;

  if (!slides.length) return <Empty>{t('rehearsal_empty')}</Empty>;
  return <section className="rehearsal-page" aria-labelledby="rehearsal-title">
    <h2 id="rehearsal-title" className="text-lg font-semibold">{t('rehearsal_title')}</h2>
    <p className="help mt-1 mb-5">{t('rehearsal_help')}</p>
    <form onSubmit={calculate} className="rehearsal-settings">
      <label><span className="label">{t('target_minutes')}</span><input className="field" name="duration_minutes" type="number" min="1" max="180" step="0.5" required disabled={!!busy} value={options.duration_minutes} onChange={change}/></label>
      <label><span className="label">{t('rehearsal_pace')}</span><input className="field" name="words_per_minute" type="number" min="80" max="240" required disabled={!!busy} value={options.words_per_minute} onChange={change}/></label>
      <label><span className="label">{t('rehearsal_pauses')}</span><input className="field" name="pause_seconds" type="number" min="0" max="120" required disabled={!!busy} value={options.pause_seconds} onChange={change}/></label>
      <label><span className="label">{t('rehearsal_main')}</span><select className="field" name="main_slides" disabled={!!busy} value={options.main_slides} onChange={change}>
        {slides.map((slide, i) => <option key={slide.id} value={i + 1}>{i + 1} / {slides.length}</option>)}
      </select></label>
      <label><span className="label">{t('rehearsal_reserve_percent')}</span><input className="field" name="reserve_percent" type="number" min="0" max="50" required disabled={!!busy} value={options.reserve_percent} onChange={change}/></label>
      <div className="rehearsal-actions">
        <button className="btn btn-primary" type="submit" disabled={!!busy}>{t('rehearsal_calculate')}</button>
        <button className="btn" type="button" disabled={!plan || !!busy} onClick={copy}>{t('rehearsal_copy')}</button>
        <a className="btn" href={downloadUrl} aria-disabled={!plan || !!busy} onClick={event => { if (!plan || busy) event.preventDefault(); }}>{t('rehearsal_download')}</a>
        <a className="btn" href={`#/presenter/${deckId}`}>{t('presenter_console')}</a>
      </div>
    </form>
    <p className="help mt-2">{t('rehearsal_main_help')}</p>
    {!plan && !busy && <p className="help mt-5" role="status">{t('rehearsal_changed')}</p>}
    {plan && <>
      <dl className="rehearsal-summary">
        {[[t('rehearsal_limit'), clock(plan.target_seconds)],
          [t('rehearsal_estimate'), plan.estimated_seconds == null ? t('rehearsal_unknown') : clock(plan.estimated_seconds)],
          [t('rehearsal_planned'), clock(plan.planned_seconds)],
          [t('rehearsal_reserve'), clock(plan.reserve_seconds)]].map(([label, value]) => <div key={label}><dt>{label}</dt><dd className="num">{value}</dd></div>)}
      </dl>
      <p className={`rehearsal-verdict ${plan.risk === 'over' ? 'rehearsal-over' : ''}`} role="status">
        {t(`rehearsal_risk_${plan.risk || 'unknown'}`, {n: plan.missing_notes.length})}
      </p>
      {(plan.words_per_minute > 140 || plan.pause_seconds_per_slide < 5) && <p className="help mt-1">{t('rehearsal_optimistic')}</p>}
      <ol className="rehearsal-timeline" aria-label={t('rehearsal_timeline')}>
        {plan.timeline.map(item => <li key={item.slide_id}>
          <div className="rehearsal-clock num">{item.start}–{item.end}<span>{t('rehearsal_slot', {n: item.slot_seconds})}</span></div>
          <div className="min-w-0">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <h3 className="font-semibold">{item.position}. {item.title || t('untitled')}</h3>
              <button type="button" className="btn btn-sm" onClick={() => edit(item.slide_id)}>{t('rehearsal_edit_notes')}</button>
            </div>
            <p className="help mt-1">{t('rehearsal_words', {n: item.word_count})} · {item.notes_missing ? t('rehearsal_notes_missing') : `${t('rehearsal_estimate')}: ${clock(item.estimated_seconds)}`}</p>
            <details className="rehearsal-notes"><summary>{t('speaker_notes')}</summary><p>{notes(item.slide_id) || t('notes_empty')}</p></details>
          </div>
        </li>)}
      </ol>
      {plan.support.length > 0 && <section className="mt-5" aria-label={t('support_slides')}>
        <h3 className="font-semibold">{t('support_slides')} ({plan.support.length})</h3>
        <p className="help mt-1">{t('rehearsal_support_help')}</p>
        <ul className="mt-3 space-y-2">{plan.support.map(item => <li key={item.slide_id} className="flex flex-wrap justify-between gap-2"><span>{item.position}. {item.title}</span><button type="button" className="btn btn-sm" onClick={() => edit(item.slide_id)}>{t('rehearsal_edit_notes')}</button></li>)}</ul>
      </section>}
    </>}
  </section>;
}
