import React, { useEffect, useRef, useState } from "react";

export function Icon({ d, size = 18 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={d} />
    </svg>
  );
}

export function Empty({ children }) {
  return <div className="panel help text-center">{children}</div>;
}

export function ConfirmButton({ label, confirmLabel, onConfirm, t, disabled, className = "btn btn-sm btn-danger" }) {
  const [pending, setPending] = useState(false);
  if (pending) {
    return (
      <span className="inline-flex gap-1">
        <button type="button" className={className} disabled={disabled} onClick={() => { setPending(false); onConfirm(); }}>{confirmLabel || t("confirm")}</button>
        <button type="button" className="btn btn-sm" onClick={() => setPending(false)}>{t("cancel")}</button>
      </span>
    );
  }
  return <button type="button" className={className} disabled={disabled} onClick={() => setPending(true)}>{label || t("delete")}</button>;
}

// Tabs with the WAI-ARIA pattern: roving tabindex, arrow keys, Home/End. Panels are rendered by the caller with `panelProps`.
export const tabId = (key) => `tab-${key}`;
export const panelId = (key) => `panel-${key}`;

export function Tabs({ tabs, active, onChange, label }) {
  const refs = useRef({});
  const onKeyDown = (event) => {
    const index = tabs.findIndex((tab) => tab.key === active);
    let next = null;
    if (event.key === "ArrowRight") next = (index + 1) % tabs.length;
    else if (event.key === "ArrowLeft") next = (index - 1 + tabs.length) % tabs.length;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = tabs.length - 1;
    if (next === null) return;
    event.preventDefault();
    onChange(tabs[next].key);
    refs.current[tabs[next].key]?.focus();
  };
  return (
    <div role="tablist" aria-label={label} className="tabs" onKeyDown={onKeyDown}>
      {tabs.map((tab) => (
        <button
          key={tab.key}
          ref={(el) => { refs.current[tab.key] = el; }}
          type="button"
          role="tab"
          id={tabId(tab.key)}
          aria-controls={panelId(tab.key)}
          tabIndex={tab.key === active ? 0 : -1}
          className="tab"
          aria-selected={tab.key === active}
          onClick={() => onChange(tab.key)}
        >
          {tab.label}
          {tab.badge !== undefined && tab.badge !== null && <span className="chip">{tab.badge}</span>}
        </button>
      ))}
    </div>
  );
}

export function Field({ label, children, help }) {
  return (
    <label className="block">
      <span className="label">{label}</span>
      {children}
      {help && <span className="help">{help}</span>}
    </label>
  );
}

export function Section({ title, right, children }) {
  return (
    <section className="panel">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-3">
        <h3 className="text-[14px] font-semibold">{title}</h3>
        {right}
      </div>
      {children}
    </section>
  );
}

export function Busy({ label }) {
  if (!label) return null;
  return (
    <div role="status" className="space-y-1">
      <div className="text-[12px]" style={{ color: "var(--muted)" }}>{label}</div>
      <div className="busy-bar" aria-hidden="true" />
    </div>
  );
}

// Ordered list of one-line strings with add / remove / move buttons. Enter adds a row after the current one.
export function ListEditor({ items, onChange, label, addLabel, placeholder, t, disabled }) {
  const inputs = useRef([]);
  const focusNext = useRef(null);
  useEffect(() => {
    if (focusNext.current !== null) {
      inputs.current[focusNext.current]?.focus();
      focusNext.current = null;
    }
  });
  const set = (i, value) => onChange(items.map((item, n) => (n === i ? value : item)));
  const remove = (i) => onChange(items.filter((_, n) => n !== i));
  const move = (i, d) => {
    const j = i + d;
    if (j < 0 || j >= items.length) return;
    const next = items.slice();
    [next[i], next[j]] = [next[j], next[i]];
    onChange(next);
  };
  const insertAfter = (i) => {
    const next = items.slice();
    next.splice(i + 1, 0, "");
    focusNext.current = i + 1;
    onChange(next);
  };
  return (
    <div>
      <ul className="space-y-1.5">
        {items.map((item, i) => (
          <li key={i} className="flex items-center gap-1">
            <input
              ref={(el) => { inputs.current[i] = el; }}
              className="field"
              value={item}
              disabled={disabled}
              placeholder={placeholder}
              aria-label={`${label} ${i + 1}`}
              onChange={(e) => set(i, e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); insertAfter(i); } }}
            />
            <button type="button" className="btn btn-icon" disabled={disabled || i === 0} onClick={() => move(i, -1)} aria-label={`${t("move_up")}: ${label} ${i + 1}`}>↑</button>
            <button type="button" className="btn btn-icon" disabled={disabled || i === items.length - 1} onClick={() => move(i, 1)} aria-label={`${t("move_down")}: ${label} ${i + 1}`}>↓</button>
            <button type="button" className="btn btn-icon" disabled={disabled} onClick={() => remove(i)} aria-label={`${t("remove")}: ${label} ${i + 1}`}>✕</button>
          </li>
        ))}
      </ul>
      <button type="button" className="btn btn-sm mt-2" disabled={disabled} onClick={() => { focusNext.current = items.length; onChange([...items, ""]); }}>+ {addLabel}</button>
    </div>
  );
}

export function useAsync(fn, deps) {
  const [state, setState] = useState({ loading: true, data: null, error: null });
  const [tick, setTick] = useState(0);
  useEffect(() => {
    let alive = true;
    setState((s) => ({ ...s, loading: true }));
    Promise.resolve()
      .then(fn)
      .then((data) => alive && setState({ loading: false, data, error: null }))
      .catch((error) => alive && setState({ loading: false, data: null, error }));
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);
  return { ...state, reload: () => setTick((n) => n + 1) };
}
