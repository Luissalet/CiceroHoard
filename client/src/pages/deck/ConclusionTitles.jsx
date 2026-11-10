import React from "react";
import { api } from "../../api.js";
import { useApp } from "../../App.jsx";
import { useDeck } from "../../components/deckContext.js";

// Titles that state the slide's conclusion: the deck's mode, the proposals, and applying or undoing them slide by slide or all at once.
export default function ConclusionTitles({ onChanged }) {
  const { t, notify } = useApp();
  const { deckId, deck, run, busy, reload } = useDeck();
  const [drafts, setDrafts] = React.useState({});
  const [report, setReport] = React.useState(null);
  const slides = (deck.slides || []).slice().sort((a, b) => a.position - b.position).filter((s) => s.titling && !s.titling.exempt);
  const mode = deck.title_mode || "label";
  const labels = slides.filter((s) => s.titling.is_label && s.titling.own_mode !== "label");
  const applied = slides.filter((s) => s.titling.applied);
  const proposals = slides.filter((s) => s.titling.proposal);

  const act = (label, fn, done) => run(label, async () => {
    const out = await fn();
    setReport(out);
    setDrafts({});
    await reload();
    onChanged?.();
    if (done) notify(done(out));
    return true;
  });
  const propose = (ids) => act(t("titles_busy_propose"), () => api.titlesPropose(deckId, ids ? { slide_ids: ids } : {}),
    (out) => t("titles_done_propose", { n: out.proposals.length }));
  const applyAll = () => act(t("titles_busy_apply"), () => api.titlesMode(deckId, { mode: "conclusion" }), (out) => t("titles_done_apply", { n: out.applied.length }));
  const restoreAll = () => act(t("titles_busy_restore"), () => api.titlesMode(deckId, { mode: "label" }), (out) => t("titles_done_restore", { n: out.restored.length }));
  const applyOne = (s) => {
    const own = (drafts[s.id] ?? "").trim();
    const body = own && own !== s.titling.proposal ? { titles: { [s.id]: own } } : { slide_ids: [s.id] };
    return act(t("titles_busy_apply"), () => api.titlesApply(deckId, body), (out) => (out.applied.length ? t("titles_done_apply", { n: 1 }) : reason(out.skipped[0]?.reason)));
  };
  const restoreOne = (s) => act(t("titles_busy_restore"), () => api.titlesRestore(deckId, { slide_ids: [s.id] }), () => t("titles_done_restore", { n: 1 }));
  const keepLabel = (s) => act(t("busy_saving"), () => api.titlesMode(deckId, { slide_id: s.id, mode: "label" }), () => t("saved"));
  const followDeck = (s) => act(t("busy_saving"), () => api.titlesMode(deckId, { slide_id: s.id }), () => t("saved"));
  const reason = (code) => {
    const key = `titles_reason_${String(code || "").split(":")[0]}`;
    const text = t(key);
    return text === key ? String(code || "") : `${text}${String(code).includes(":") ? ` (${String(code).split(":")[1].trim()})` : ""}`;
  };
  const skipped = (report?.skipped || []).filter((s) => !["exempt_layout", "already_a_conclusion", "kept_as_label"].includes(s.reason));

  if (!slides.length) return null;
  return (
    <section className="panel" data-testid="titles-panel" data-mode={mode}>
      <div className="mb-2 flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-[14px] font-semibold">{t("titles_heading")}</h2>
        <div className="flex flex-wrap items-center gap-1" role="group" aria-label={t("titles_mode")}>
          <button type="button" className={`btn btn-sm ${mode === "label" ? "btn-primary" : ""}`} aria-pressed={mode === "label"} disabled={!!busy || mode === "label"} onClick={restoreAll} data-testid="titles-mode-label">{t("titles_mode_label")}</button>
          <button type="button" className={`btn btn-sm ${mode === "conclusion" ? "btn-primary" : ""}`} aria-pressed={mode === "conclusion"} disabled={!!busy || mode === "conclusion"} onClick={applyAll} data-testid="titles-mode-conclusion">{t("titles_mode_conclusion")}</button>
        </div>
      </div>
      <p className="help mb-3">{t("titles_help")}</p>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <button type="button" className="btn btn-sm" disabled={!!busy || labels.length === 0} onClick={() => propose(null)} data-testid="titles-propose">{t("titles_propose", { n: labels.length })}</button>
        <button type="button" className="btn btn-sm btn-primary" disabled={!!busy || labels.length === 0} onClick={applyAll} data-testid="titles-apply-all">{t("titles_apply_all")}</button>
        <button type="button" className="btn btn-sm" disabled={!!busy || applied.length === 0} onClick={restoreAll} data-testid="titles-restore-all">{t("titles_restore_all", { n: applied.length })}</button>
        <span className="help" role="status" data-testid="titles-summary">{t("titles_summary", { l: labels.length, p: proposals.length, a: applied.length })}</span>
      </div>
      {report?.note && <p className="help mb-2" role="status">{report.note}</p>}
      {skipped.length > 0 && (
        <ul className="help mb-2 space-y-0.5" data-testid="titles-skipped">
          {skipped.map((s) => <li key={s.slide_id}>{s.position}. {s.title}: {reason(s.reason)}</li>)}
        </ul>
      )}
      <ul className="space-y-2" data-testid="titles-list">
        {slides.map((s) => {
          const info = s.titling;
          const keeps = info.own_mode === "label";
          return (
            <li key={s.id} className="border-t pt-2" style={{ borderColor: "var(--line)" }} data-testid="titles-row" data-slide={s.id}
              data-state={info.applied ? "applied" : keeps ? "kept" : info.is_label ? "label" : "conclusion"}>
              <div className="flex flex-wrap items-center gap-2 text-[13px]">
                <span className="font-semibold [overflow-wrap:anywhere]">{s.position}. {s.title || t("untitled")}</span>
                <span className={info.applied || !info.is_label ? "chip chip-ok" : keeps ? "chip" : "chip chip-amber"}>
                  {info.applied ? t("titles_state_applied") : keeps ? t("titles_state_kept") : info.is_label ? t("titles_state_label") : t("titles_state_conclusion")}
                </span>
              </div>
              {info.applied && (
                <div className="mt-1 flex flex-wrap items-center gap-2 text-[12px]">
                  <span className="help">{t("titles_was", { label: info.label })}</span>
                  <button type="button" className="btn btn-sm" disabled={!!busy} onClick={() => restoreOne(s)} data-testid="titles-restore-one">{t("titles_restore_one")}</button>
                </div>
              )}
              {!info.applied && info.is_label && !keeps && (
                <div className="mt-1 flex flex-wrap items-center gap-2">
                  {info.proposal ? (
                    <input className="field min-w-0 flex-1" aria-label={t("titles_proposal_for", { n: s.position })} value={drafts[s.id] ?? info.proposal} maxLength={200}
                      onChange={(e) => setDrafts((d) => ({ ...d, [s.id]: e.target.value }))} disabled={!!busy} data-testid="titles-proposal" />
                  ) : <span className="help flex-1">{t("titles_no_proposal")}</span>}
                  {info.proposal
                    ? <button type="button" className="btn btn-sm btn-primary" disabled={!!busy} onClick={() => applyOne(s)} data-testid="titles-apply-one">{t("titles_apply_one")}</button>
                    : <button type="button" className="btn btn-sm" disabled={!!busy} onClick={() => propose([s.id])}>{t("titles_propose_one")}</button>}
                  <button type="button" className="btn btn-sm" disabled={!!busy} onClick={() => keepLabel(s)} data-testid="titles-keep">{t("titles_keep")}</button>
                </div>
              )}
              {keeps && (
                <div className="mt-1">
                  <button type="button" className="btn btn-sm" disabled={!!busy} onClick={() => followDeck(s)}>{t("titles_follow")}</button>
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
