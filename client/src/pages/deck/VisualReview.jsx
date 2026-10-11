import React, { useState } from "react";
import { api } from "../../api.js";
import { goReplace, useApp } from "../../App.jsx";
import { useDeck } from "../../components/deckContext.js";
import { Empty, Section } from "../../components/ui.jsx";

// Visual review before export (POST /api/decks/{id}/visual-review, same code as the deck_visual_review tool): every
// slide is rendered in the browser and measured; each finding comes with its fix, and the one automatic fix (minimum
// font size where text overflows) is offered as a button.
export default function VisualReview() {
  const { t, notify } = useApp();
  const { deckId, deck, run, busy, reload } = useDeck();
  const [result, setResult] = useState(null);
  const [stamp, setStamp] = useState(0);
  const count = (deck.slides || []).length;

  const start = async (fix) => {
    const res = await run(t(fix ? "vr_busy_fix" : "vr_busy", { n: count }), () => api.visualReview(deckId, fix));
    if (!res) return;
    setResult(res);
    setStamp(Date.now());
    if (fix) {
      if (res.fixed?.length) { notify(t("vr_fixed", { n: res.fixed.length })); await reload(); }
      else if (res.skipped?.length) { notify(t("vr_skipped", { list: res.skipped.map((f) => f.position).join(", ") })); await reload(); }
      else notify(t("vr_nothing_fixed"));
    }
  };

  const slides = result?.slides || [];
  const flagged = slides.filter((s) => s.findings.length);
  const canFix = slides.some((s) => s.findings.some((f) => f.auto_fix));
  const right = (
    <div className="flex flex-wrap gap-2">
      <button type="button" className="btn" disabled={!!busy || count === 0} onClick={() => start(false)}>
        {result ? t("vr_again") : t("vr_run")}
      </button>
      {canFix && <button type="button" className="btn btn-primary" disabled={!!busy} onClick={() => start(true)}>{t("vr_fix")}</button>}
    </div>
  );

  return (
    <Section title={t("vr_title")} right={right}>
      <p className="help">{t("vr_help")}</p>
      {count === 0 && <p className="help mt-2">{t("export_no_slides")}</p>}
      {result && (
        <p className="mt-2 text-[13px]" role="status">
          <span className={result.ok ? "chip chip-ok" : "chip chip-danger"}>{result.ok ? t("vr_ok_chip") : t("vr_errors_chip")}</span>{" "}
          {t("vr_summary", { s: slides.length, e: result.errors, w: result.warnings })}
        </p>
      )}
      {result?.skipped?.length > 0 && (
        <p className="help mt-1" role="status">{t("vr_skipped", { list: result.skipped.map((f) => f.position).join(", ") })}</p>
      )}
      {result?.fixed?.length > 0 && (
        <p className="help mt-1">{t("vr_fixed_list", { list: result.fixed.map((f) => f.position).join(", "), before: result.before?.errors ?? "?" })}</p>
      )}
      {result && flagged.length === 0 && <div className="mt-3"><Empty>{t("vr_clean")}</Empty></div>}
      <ul className="mt-3 space-y-3">
        {flagged.map((s) => (
          <li key={s.slide_id} className="flex flex-wrap items-start gap-3 rounded-md border p-3" style={{ borderColor: "var(--line)" }}>
            {s.png_url && (
              <a href={`${s.png_url}?v=${stamp}`} target="_blank" rel="noreferrer" className="shrink-0">
                <img src={`${s.png_url}?v=${stamp}`} alt={t("vr_png_alt", { n: s.position })} width="240" height="135"
                  className="block rounded border" style={{ borderColor: "var(--line)" }} loading="lazy" />
              </a>
            )}
            <div className="min-w-0 flex-1">
              <div className="mb-1.5 flex flex-wrap items-center justify-between gap-2">
                <h4 className="text-[14px] font-semibold [overflow-wrap:anywhere]">{s.position}. {s.title || t("untitled")}</h4>
                <button type="button" className="btn btn-sm" onClick={() => goReplace(`deck/${deckId}/slides?slide=${encodeURIComponent(s.slide_id)}`)}>{t("review_go")}</button>
              </div>
              <ul className="space-y-1.5">
                {s.findings.map((f, n) => (
                  <li key={n} className="flex items-start gap-2 text-[13px]">
                    <span className={f.severity === "error" ? "chip chip-danger" : "chip chip-amber"}>{t(`vr_sev_${f.severity}`)}</span>
                    <span className="min-w-0 [overflow-wrap:anywhere]">
                      <strong>{t(`vr_rule_${f.rule}`)}</strong>
                      {f.where ? <span className="help"> · «{f.where}»</span> : null}
                      {f.detail ? <span className="help"> ({f.detail})</span> : null}
                      <span className="help block">{t(`vr_fix_${f.rule}`)}{f.auto_fix ? ` ${t("vr_auto_fix_note")}` : ""}</span>
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          </li>
        ))}
      </ul>
    </Section>
  );
}
