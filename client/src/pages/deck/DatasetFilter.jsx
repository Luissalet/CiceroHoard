import React, { useState } from 'react';
import { useApp } from '../../App.jsx';
import { useDeck } from '../../components/deckContext.js';
import { Field } from '../../components/ui.jsx';

export default function DatasetFilter({ columns, disabled, onCreate }) {
  const { t } = useApp();
  const { run } = useDeck();
  const [column, setColumn] = useState('');
  const [operator, setOperator] = useState('eq');
  const [value, setValue] = useState('');
  const [sort, setSort] = useState('');
  const [descending, setDescending] = useState(false);
  const [title, setTitle] = useState('');
  const [error, setError] = useState('');
  const columnField = (label, current, change) => <Field label={label}>
    <select className="field" value={current} disabled={disabled} onChange={e => change(e.target.value)}>
      <option value="">{t('none')}</option>
      {columns.map(name => <option key={name} value={name}>{name}</option>)}
    </select>
  </Field>;
  const create = () => run(t('busy_saving'), async () => {
    setError('');
    try {
      await onCreate({
        filters: column ? [{ column, operator, ...(operator === 'isnull' ? {} : { value }) }] : [],
        ...(sort ? { sort_column: sort, descending } : {}),
        title,
      });
    } catch (cause) { setError(cause.message); throw cause; }
  });
  return <details>
    <summary>{t('data_filter_sort')}</summary>
    <div className="mt-3 space-y-3">
      <p className="help">{t('data_filter_saved_hint')}</p>
      <div className="grid gap-3 sm:grid-cols-2">
        {columnField(t('data_filter_column'), column, setColumn)}
        <Field label={t('data_filter_operator')}>
          <select className="field" value={operator} disabled={disabled || !column} onChange={e => setOperator(e.target.value)}>
            {['eq','ne','gt','ge','lt','le','contains','isnull'].map(op => <option key={op} value={op}>{t('data_filter_' + op)}</option>)}
          </select>
        </Field>
        {column && operator !== 'isnull' && <Field label={t('data_filter_value')}><input className="field" value={value} disabled={disabled} onChange={e => setValue(e.target.value)} /></Field>}
      </div>
      <p className="help">{t('data_filter_semantics')}</p>
      <div className="grid gap-3 sm:grid-cols-2">
        {columnField(t('data_sort_column'), sort, setSort)}
        <Field label={t('data_sort_direction')}><select className="field" value={descending ? 'desc' : 'asc'} disabled={disabled || !sort} onChange={e => setDescending(e.target.value === 'desc')}>
          <option value="asc">{t('data_sort_asc')}</option><option value="desc">{t('data_sort_desc')}</option>
        </select></Field>
      </div>
      <p className="help">{t('data_sort_missing')}</p>
      <Field label={t('data_derived_title')}><input className="field" value={title} disabled={disabled} onChange={e => setTitle(e.target.value)} /></Field>
      {error && <p className="help [overflow-wrap:anywhere]" role="alert" style={{ color: 'var(--danger)' }}>{error}</p>}
      <button type="button" className="btn" disabled={disabled} onClick={create}>{t(error ? 'data_filter_retry' : 'derive_dataset')}</button>
    </div>
  </details>;
}
