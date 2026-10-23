import React,{useEffect,useState} from 'react';
import {Upload,Plus,BarChart3,Table2} from 'lucide-react';
import {api} from '../../api.js';
import {useApp} from '../../App.jsx';
import {useDeck} from '../../components/deckContext.js';
import {Field} from '../../components/ui.jsx';
import {CHART_KINDS} from '../../format.js';
import DatasetFilter from './DatasetFilter.jsx';

export default function DataPanel({onInsert,disabled=false}){
 const {t,notify}=useApp();const {deckId,deck,run,reload,busy}=useDeck();
 const [selected,setSelected]=useState(''),[data,setData]=useState(null),[text,setText]=useState(''),[mode,setMode]=useState('auto'),[sheet,setSheet]=useState('');
 const [kind,setKind]=useState('chart'),[chart,setChart]=useState('bar'),[category,setCategory]=useState(''),[values,setValues]=useState([]),[extra,setExtra]=useState({});
 const [group,setGroup]=useState(''),[aggregate,setAggregate]=useState('sum'),[measure,setMeasure]=useState('');
 const [error,setError]=useState(''),[loading,setLoading]=useState(false),[retry,setRetry]=useState(0);
 const [rowLimit,setRowLimit]=useState(30);
 const off=disabled||!!busy;const sources=(deck.sources||[]).filter(s=>s.kind==='dataset');
 useEffect(()=>{let active=true;setData(null);setError('');setLoading(!!selected);if(!selected)return;api.dataset(deckId,selected).then(d=>{if(active){setData(d);setCategory(d.columns[0]||'');setValues([]);setExtra({});setMeasure('');setGroup('');setRowLimit(Math.min(2000,d.row_count)||1);}}).catch(e=>{if(active)setError(e.message)}).finally(()=>{if(active)setLoading(false)});return()=>{active=false}},[selected,deckId,retry]);
 const added=async(result)=>{await reload();setSelected(String(result.source_id));setData(result)};
 const upload=file=>{if(file)run(t('busy_uploading'),async()=>added(await api.datasetUpload(deckId,file,{number_format:mode,sheet})))};
 const paste=()=>run(t('busy_saving'),async()=>{await added(await api.datasetImport(deckId,{text,number_format:mode}));setText('')});
 const map=()=>run(t('busy_saving'),async()=>{const mapped=await api.datasetVisual(deckId,selected,{kind,chart,category_column:category,series_columns:values,limit:rowLimit,...extra});if(mapped.warnings?.length)notify(mapped.warnings.join(' '));onInsert(mapped)});
 const transform=()=>run(t('busy_saving'),async()=>added(await api.datasetTransform(deckId,selected,{group_by:group?[group]:[],aggregations:[{column:measure,operation:aggregate}]})));
 const columnSelect=(label,value,change,optional=false)=><Field label={label}><select className="field" disabled={off} value={value||''} onChange={e=>change(e.target.value)}><option value="">{optional?t('none'):t('choose_column')}</option>{(data?.columns||[]).map(c=><option key={c} value={c}>{c}</option>)}</select></Field>;
 return <div className="space-y-3">
  {error&&<div><p role="alert" style={{color:'var(--danger)'}}>{error}</p><button type="button" className="btn btn-sm" disabled={off} onClick={()=>setRetry(n=>n+1)}>{t('retry')}</button></div>}
  <div className="grid gap-2 sm:grid-cols-3"><Field label={t('number_format')}><select className="field" value={mode} disabled={off} onChange={e=>setMode(e.target.value)}>{['auto','es','en'].map(v=><option key={v} value={v}>{t('number_format_'+v)}</option>)}</select></Field><Field label={t('worksheet')}><input className="field" value={sheet} disabled={off} onChange={e=>setSheet(e.target.value)}/></Field>
   <label className="btn self-end"><Upload size={16}/>{t('data_import')}<input type="file" className="sr-only-live" accept=".csv,.tsv,.xlsx" disabled={off} onChange={e=>{upload(e.target.files?.[0]);e.target.value=''}}/></label>
  </div>
  <details><summary>{t('paste_csv')}</summary><textarea className="field mt-2" rows={4} aria-label={t('paste_csv')} value={text} disabled={off} onChange={e=>setText(e.target.value)}/><button className="btn btn-sm mt-2" type="button" disabled={off||!text.trim()} onClick={paste}><Plus size={16}/>{t('data_import')}</button></details>
  <Field label={t('dataset')}><select className="field" value={selected} disabled={off} onChange={e=>setSelected(e.target.value)}><option value="">{t('choose_dataset')}</option>{sources.map(s=><option key={s.id} value={s.id}>{s.title} · #{s.id}</option>)}</select></Field>
  {loading&&<p className="help" role="status">{t('loading')}</p>}
  {data&&String(data.source_id)===selected&&<>
   <p className="text-sm num">{data.row_count} {t(data.row_count===1?'data_row':'data_rows')} · {data.columns.length} {t('data_columns')}</p>
   <p className="help [overflow-wrap:anywhere]">{t('data_saved_source',{id:data.source_id})}{data.origin?.derived_from!=null&&<> · {t('data_derived_origin',{id:data.origin.derived_from})}</>}</p>
   {data.origin?.transformation&&<details><summary>{t('data_saved_transform')}</summary><pre className="pre mt-2 whitespace-pre-wrap [overflow-wrap:anywhere]">{JSON.stringify(data.origin.transformation,null,2)}</pre></details>}
   {(data.warnings||[]).map(w=><p key={w} role="status" className="text-sm" style={{color:'var(--warn)'}}>{w}</p>)}
   <details><summary>{t('data_preview')}</summary><p className="help mt-2">{t('data_preview_first',{n:Math.min(8,data.rows.length),total:data.row_count})}</p><div className="overflow-x-auto mt-2"><table className="grid"><thead><tr>{data.columns.map(c=><th key={c}>{c}</th>)}</tr></thead><tbody>{data.rows.slice(0,8).map((r,i)=><tr key={i}>{r.map((v,j)=><td key={j}>{v??''}</td>)}</tr>)}</tbody></table></div></details>
   <DatasetFilter key={selected} columns={data.columns} disabled={off} onCreate={async(body)=>added(await api.datasetTransform(deckId,selected,body))}/>
   <details><summary>{t('data_aggregate')}</summary><div className="grid gap-2 mt-2 sm:grid-cols-3">{columnSelect(t('group_by'),group,setGroup,true)}{columnSelect(t('data_measure'),measure,setMeasure)}<Field label={t('operation')}><select className="field" value={aggregate} disabled={off} onChange={e=>setAggregate(e.target.value)}>{['sum','mean','median','min','max','count','last'].map(op=><option key={op} value={op}>{t('aggregate_'+op)}</option>)}</select></Field></div><button type="button" className="btn btn-sm mt-2" disabled={off||!measure} onClick={transform}>{t('derive_dataset')}</button></details>
   {onInsert&&<>
    <div className="flex gap-1" role="group" aria-label={t('visual_type')}>{[['chart',BarChart3],['table',Table2]].map(([type,Icon])=><button key={type} type="button" className={`btn btn-icon ${kind===type?'btn-active':''}`} aria-pressed={kind===type} title={t('block_'+type)} aria-label={t('block_'+type)} disabled={off} onClick={()=>setKind(type)}><Icon size={18}/></button>)}</div>
    {kind==='chart'&&<div className="grid gap-2 sm:grid-cols-2"><Field label={t('chart_kind')}><select className="field" value={chart} disabled={off} onChange={e=>setChart(e.target.value)}>{CHART_KINDS.map(c=><option key={c} value={c}>{t('chart_'+c)}</option>)}</select></Field>{columnSelect(t('chart_category'),category,setCategory)}</div>}
    <fieldset><legend className="label">{t('data_value_columns')}</legend><div className="flex flex-wrap gap-3">{data.columns.map(c=><label key={c} className="text-sm flex gap-1 items-center"><input type="checkbox" checked={values.includes(c)} disabled={off||(!values.includes(c)&&values.length>=(kind==='table'?10:6))} onChange={e=>setValues(e.target.checked?[...values,c]:values.filter(v=>v!==c))}/>{c}</label>)}</div></fieldset>
    <Field label={t('data_selected_rows')}><input className="field" type="number" min="1" max={Math.max(1,Math.min(2000,data.row_count))} value={rowLimit} disabled={off||!data.row_count} onChange={e=>setRowLimit(Number(e.target.value))}/></Field>
    {kind==='chart'&&['scatter','bubble','band'].includes(chart)&&<div className="grid gap-2 sm:grid-cols-2">{['x_column',...(chart==='bubble'?['size_column']:[]),...(chart==='band'?['lower_column','upper_column']:[])].map(key=><React.Fragment key={key}>{columnSelect(t('data_'+key),extra[key],v=>setExtra({...extra,[key]:v}))}</React.Fragment>)}</div>}
    {!data.row_count&&<p className="help">{t('data_empty_visual')}</p>}
    <button type="button" className="btn" disabled={off||!data.row_count||!values.length||(kind==='chart'&&!category)} onClick={map}><Plus size={16}/>{t('insert_visual')}</button>
   </>}
  </>}
 </div>;
}
