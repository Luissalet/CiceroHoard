import React from "react";
import { api } from "../../api.js";
import { useApp } from "../../App.jsx";
import { Section } from "../../components/ui.jsx";

// Codes the server sends when the design studio is not ready; both are solved by starting it through the Hub.
const NOT_READY = new Set(["vitruvius_down", "design_module_off"]);

// "Start Vitruvius from the Hub": also used by the theme picker when the presets cannot be read.
export function StartVitruvius({ onStarted, label }) {
  const { t, notify } = useApp();
  const [state, setState] = React.useState({ busy: false, error: null });
  const start = async () => {
    setState({ busy: true, error: null });
    try {
      const res = await api.vitruviusStart();
      if (res.started === false && !res.running) throw new Error(res.error || "Hub");
      notify(t("vitruvius_started"));
      setState({ busy: false, error: null });
      onStarted && onStarted(res);
    } catch (error) {
      setState({ busy: false, error: error.message });
    }
  };
  return (
    <span className="inline-flex flex-wrap items-center gap-2">
      <button type="button" className="btn btn-sm" disabled={state.busy} onClick={start} data-action="vitruvius-start">
        {state.busy ? t("vitruvius_starting") : (label || t("vitruvius_start"))}
      </button>
      {state.error && <span className="help" role="alert">{t("vitruvius_start_failed", { reason: state.error })}</span>}
    </span>
  );
}

// One finding of the design review, in the same row shape as the deck check: chip, title, message and the fix.
export function AuditIssue({ issue }) {
  const { t } = useApp();
  return (
    <li className="flex items-start gap-2 text-[13px]" data-design-issue={issue.rule}>
      <span className={issue.severity === "warning" ? "chip chip-amber" : "chip"}>{t("audit_chip")}</span>
      <span className="min-w-0 [overflow-wrap:anywhere]">
        <span className="font-semibold">{issue.title}</span>
        {issue.message && issue.message !== issue.title && <span> {issue.message}</span>}
        {issue.fix && <span className="block help">{t("audit_fix")}: {issue.fix}</span>}
      </span>
    </li>
  );
}

// The "Review design" action: runs Vitruvius's slop audit on the deck and shows the score; the findings themselves are
// merged by Review into the per-slide groups of the deck check.
export default function DesignAudit({ deckId, audit, setAudit, loading }) {
  const { t } = useApp();
  const [state, setState] = React.useState({ busy: false, error: null, code: null });
  const runAudit = async (prepare) => {
    setState({ busy: true, error: null, code: null });
    try {
      const res = await api.designAuditRun(deckId, prepare);
      setAudit(res.audit);
      setState({ busy: false, error: null, code: null });
    } catch (error) {
      setState({ busy: false, error: error.message, code: error.code || null });
    }
  };
  const page = (audit?.issues || []).filter((i) => i.scope === "page");
  const counts = audit?.counts || {};
  return (
    <Section title={t("audit_title")} right={audit?.studio_url && (
      <a className="btn btn-sm" href={audit.studio_url} target="_blank" rel="noreferrer">{t("audit_open")}</a>)}>
      <p className="help mb-3">{t("audit_help")}</p>
      <div className="flex flex-wrap items-center gap-2">
        <button type="button" className="btn btn-primary" disabled={state.busy} onClick={() => runAudit(false)} data-action="design-audit">
          {state.busy ? t("audit_running") : t("audit_run")}
        </button>
        {audit && (
          <span className="flex flex-wrap items-center gap-2" role="status" data-design-score={audit.slop_score}>
            <span className={audit.slop_score >= 25 ? "chip chip-amber" : "chip chip-accent"}>{t("audit_score", { score: audit.slop_score })}</span>
            <span className="help">{t(`audit_mode_${audit.mode}`)}</span>
            <span className="help">{t("audit_when", { when: new Date((audit.created_ts || 0) * 1000).toLocaleString() })}</span>
          </span>
        )}
      </div>
      {state.error && (
        <div className="mt-3 flex flex-wrap items-center gap-2" role="alert">
          <span className="help">{state.code === "vitruvius_down" ? t("audit_down") : state.code === "design_module_off" ? t("audit_module_off") : state.error}</span>
          {NOT_READY.has(state.code) && (
            <button type="button" className="btn btn-sm" disabled={state.busy} onClick={() => runAudit(true)} data-action="design-audit-prepare">{t("audit_prepare")}</button>
          )}
          {state.code === "family_unavailable" && <StartVitruvius onStarted={() => runAudit(false)} />}
        </div>
      )}
      {!audit && !loading && !state.error && <p className="help mt-3">{t("audit_none")}</p>}
      {audit?.stale && <p className="help mt-3" role="status">{t("audit_stale")}</p>}
      {audit && (
        <div className="mt-3 space-y-2">
          {audit.summary && <p className="text-[13px]">{audit.summary}</p>}
          <p className="help">{t("audit_counts", { s: counts.slide || 0, d: counts.deck || 0, p: counts.page || 0 })}</p>
          {page.length > 0 && (
            <details>
              <summary className="help cursor-pointer">{t("audit_page")} ({page.length})</summary>
              <ul className="mt-2 space-y-1.5">{page.map((issue, n) => <AuditIssue key={n} issue={issue} />)}</ul>
            </details>
          )}
          {audit.credit && <p className="help text-[11px]">{audit.credit}</p>}
        </div>
      )}
    </Section>
  );
}
