import React, { useCallback, useEffect, useState } from 'react';
import { Trash2 } from 'lucide-react';
import { api } from '../../api.js';
import { useApp } from '../../App.jsx';

// Rehearsals measured in the presenter console: time on screen per slide next to the plan's slot.
const clock = (seconds) => {
  if (seconds == null) return '–';
  const s = Math.round(Math.abs(seconds));
  return `${seconds < 0 ? '−' : ''}${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
};
const signed = (seconds) => seconds == null ? '–' : `${seconds > 0 ? '+' : seconds < 0 ? '−' : ''}${clock(Math.abs(seconds))}`;

export default function MeasuredRuns({ deckId, pace, pause, version }) {
  const { t, notify } = useApp();
  const [runs, setRuns] = useState(null);
  const [error, setError] = useState('');
  const load = useCallback(async () => {
    try { const res = await api.rehearsalRuns(deckId, { words_per_minute: pace, pause_seconds: pause }); setRuns(res.runs); setError(''); }
    catch (e) { setError(e.message); }
  }, [deckId, pace, pause]);
  useEffect(() => { void load(); }, [load, version]);
  const remove = async (run) => {
    if (!window.confirm(t('runs_delete_confirm', { name: run.label }))) return;
    try { await api.rehearsalRunDelete(deckId, run.id); notify(t('runs_deleted')); void load(); }
    catch (e) { setError(e.message); }
  };
  return <section className="mt-8" aria-labelledby="runs-title">
    <h3 id="runs-title" className="font-semibold">{t('runs_title')}</h3>
    <p className="help mt-1">{t('runs_help')}</p>
    {error && <p role="alert" className="help mt-2">{error}</p>}
    {runs && runs.length === 0 && <p className="help mt-3" role="status">{t('runs_empty')}</p>}
    {(runs || []).map(run => <article key={run.id} className="panel mt-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h4 className="font-semibold">{run.label}</h4>
        <div className="flex flex-wrap items-center gap-2">
          <span className="chip num">{t('runs_total')}: {clock(run.total_seconds)} / {clock(run.target_seconds)}</span>
          <span className={`chip num ${run.over_target_seconds > 0 ? 'rehearsal-over' : ''}`}>
            {run.over_target_seconds > 0 ? t('runs_over') : t('runs_under')}: {clock(Math.abs(run.over_target_seconds))}</span>
          <button type="button" className="btn btn-icon" title={t('runs_delete')} aria-label={t('runs_delete')} onClick={() => remove(run)}><Trash2 size={16}/></button>
        </div>
      </div>
      {run.over_slot.length > 0 && <p className="help mt-2">{t('runs_worst', { list: run.over_slot.map(r => `${r.position}. ${r.title} (${signed(r.delta_seconds)})`).join(' · ') })}</p>}
      <div className="overflow-x-auto mt-2"><table className="grid w-full text-[13px]">
        <thead><tr><th className="text-left">{t('runs_slide')}</th><th className="text-right">{t('runs_planned')}</th><th className="text-right">{t('runs_measured')}</th><th className="text-right">{t('runs_delta')}</th></tr></thead>
        <tbody>{run.rows.map(row => <tr key={row.slide_id}>
          <td>{row.position}. {row.title}</td>
          <td className="num text-right">{clock(row.slot_seconds)}</td>
          <td className="num text-right">{row.skipped ? t('runs_skipped') : clock(row.seconds)}</td>
          <td className={`num text-right ${row.delta_seconds > 0 ? 'rehearsal-over' : ''}`}>{row.skipped ? '–' : signed(row.delta_seconds)}</td>
        </tr>)}</tbody>
      </table></div>
    </article>)}
  </section>;
}
