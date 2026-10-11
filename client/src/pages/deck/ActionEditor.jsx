import React from 'react';
import {useApp} from '../../App.jsx';
import {useDeck} from '../../components/deckContext.js';
import {Field} from '../../components/ui.jsx';

export default function ActionEditor({block,onChange,disabled}){
  const {t}=useApp();const {deck}=useDeck();const action=block.action;
  const set=value=>onChange({...block,action:value});
  const select=kind=>set(kind==='none'?undefined:kind==='slide'?{kind,slide_id:deck.slides[0]?.id}:{kind,...(kind==='url'?{url:''}:{})});
  return <fieldset className="space-y-2 border-0 p-0">
    <Field label={t('nav_action')}><select className="field" disabled={disabled} value={action?.kind||'none'} onChange={e=>select(e.target.value)}>
      {['none','slide','url','next','previous','return'].map(kind=><option key={kind} value={kind}>{t('nav_'+kind)}</option>)}
    </select></Field>
    {action?.kind==='slide'&&<Field label={t('nav_destination')}><select className="field" disabled={disabled} value={action.slide_id||''} onChange={e=>set({...action,slide_id:e.target.value})}>
      {!deck.slides.some(s=>s.id===action.slide_id)&&<option value={action.slide_id||''}>{t('nav_missing')}</option>}
      {deck.slides.map(s=><option key={s.id} value={s.id}>{s.position}. {s.title}</option>)}
    </select></Field>}
    {action?.kind==='url'&&<Field label="URL"><input className="field" type="url" disabled={disabled} value={action.url||''} onChange={e=>set({...action,url:e.target.value})}/></Field>}
    {action&&<Field label={t('nav_label')}><input className="field" disabled={disabled} value={action.label||''} maxLength={200} onChange={e=>set({...action,label:e.target.value})}/></Field>}
  </fieldset>;
}
