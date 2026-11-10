import React from "react";
import { api } from "../../api.js";
import { goReplace, useApp } from "../../App.jsx";
import { useDeck } from "../../components/deckContext.js";
import { Empty, useAsync } from "../../components/ui.jsx";
import { approvedCount } from "../../format.js";
import VisualReview from "./VisualReview.jsx";
import DesignAudit, { AuditIssue } from "./DesignAudit.jsx";
import ConclusionTitles from "./ConclusionTitles.jsx";

export default function Review() {
  const { t, lang } = useApp();
  const { deckId, deck, run, busy, reload } = useDeck();
  const check = useAsync(() => api.check(deckId), [deckId, deck.updated_at]);
  const saved = useAsync(() => api.designAudit(deckId, lang), [deckId, deck.updated_at, deck.theme, lang]);
  const [fresh, setFresh] = React.useState(null);
  React.useEffect(() => setFresh(null), [deckId, saved.data]);
  const audit = fresh || saved.data?.audit || null;
  const slides = (deck.slides || []).slice().sort((a, b) => a.position - b.position);
  const issues = check.data?.issues || [];
  const design = (audit?.issues || []).filter((i) => i.scope !== "page");
  const pending = slides.length - approvedCount(deck);

  const groups = [];
  const general = [...issues.filter((i) => !i.slide_id), ...design.filter((i) => !i.slide_id)];
  if (general.length) groups.push({ key: "deck", title: t("review_general"), issues: general });
  slides.forEach((s, n) => {
    const own = [...issues.filter((i) => i.slide_id === s.id), ...design.filter((i) => i.slide_id === s.id)];
    if (own.length) groups.push({ key: s.id, slide: s, n: n + 1, title: s.title || t("untitled"), issues: own });
  });
  const warnings = issues.filter((i) => i.severity === "warning").length;

  const approveAll = () => run(t("busy_saving"), async () => {
    for (const s of slides) if (s.status !== "approved") await api.slideApprove(deckId, s.id);
    await reload();
    return true;
  });

  return (
    <div className="max-w-4xl space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <button type="button" className="btn" disabled={!!busy || check.loading} onClick={check.reload}>{t("review_refresh")}</button>
        <button type="button" className="btn" disabled={!!busy || pending === 0} onClick={approveAll}>{t("approve_all", { n: pending })}</button>
        {!check.loading && !check.error && (
          <span className="help" role="status">{t("review_summary", { w: warnings, i: issues.length - warnings })}</span>
        )}
      </div>
      <ConclusionTitles onChanged={check.reload} />
      <DesignAudit deckId={deckId} audit={audit} setAudit={setFresh} loading={saved.loading} />
      {check.error && <Empty>{check.error.message}</Empty>}
      {check.loading && !check.data && <div className="help" role="status">{t("loading")}</div>}
      {!check.loading && !check.error && issues.length === 0 && <Empty>{t("review_clean")}</Empty>}
      <ul className="space-y-3">
        {groups.map((g) => (
          <li key={g.key} className="panel">
            <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
              <h2 className="text-[14px] font-semibold [overflow-wrap:anywhere]">{g.slide ? `${g.n}. ${g.title}` : g.title}</h2>
              {g.slide && <button type="button" className="btn btn-sm" onClick={() => goReplace(`deck/${deckId}/slides?slide=${encodeURIComponent(g.slide.id)}`)}>{t("review_go")}</button>}
            </div>
            <ul className="space-y-1.5">
              {g.issues.map((issue, n) => issue.source === "design" ? <AuditIssue key={n} issue={issue} /> : (
                <li key={n} className="flex items-start gap-2 text-[13px]">
                  <span className={issue.severity === "warning" ? "chip chip-amber" : "chip"}>{t(`severity_${issue.severity}`)}</span>
                  <span className="min-w-0 [overflow-wrap:anywhere]">{issue.message}</span>
                </li>
              ))}
            </ul>
          </li>
        ))}
      </ul>
      <VisualReview />
    </div>
  );
}
