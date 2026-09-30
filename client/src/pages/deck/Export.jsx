import React from "react";
import { api } from "../../api.js";
import { useApp } from "../../App.jsx";
import { useDeck } from "../../components/deckContext.js";
import { Empty, Section, useAsync } from "../../components/ui.jsx";
import { EXPORT_FORMATS, approvedCount, clock, formatBytes } from "../../format.js";

export default function Export() {
  const { t, notify, lang } = useApp();
  const { deckId, deck, run, busy } = useDeck();
  const list = useAsync(() => api.exports(deckId), [deckId]);
  const items = (Array.isArray(list.data) ? list.data : list.data?.items || []).slice().sort((a, b) => String(b.created_at).localeCompare(String(a.created_at)));
  const slides = deck.slides || [];
  const pending = slides.length - approvedCount(deck);

  const create = async (format) => {
    const res = await run(t("busy_export", { format: t(`format_${format}`) }), async () => {
      const out = await api.exportCreate(deckId, format);
      return out.export || out;
    });
    if (res) { notify(t("export_done", { name: res.filename })); list.reload(); }
  };

  return (
    <div className="max-w-4xl space-y-4">
      <Section title={t("export_title")}>
        {slides.length === 0 && <p className="help mb-2">{t("export_no_slides")}</p>}
        {slides.length > 0 && pending > 0 && <p className="help mb-2">{t("export_pending", { n: pending })}</p>}
        <div className="grid gap-2 sm:grid-cols-2">
          {EXPORT_FORMATS.map((f) => (
            <div key={f} className="rounded-md border p-3" style={{ borderColor: "var(--line)" }}>
              <button type="button" className="btn btn-primary" disabled={!!busy || slides.length === 0} onClick={() => create(f)}>{t(`export_${f}`)}</button>
              <p className="help mt-1.5">{t(`export_${f}_help`)}</p>
            </div>
          ))}
        </div>
      </Section>
      <Section title={t("exports_previous")}>
        {list.error && <p className="help">{list.error.message}</p>}
        {!list.error && !list.loading && items.length === 0 && <p className="help">{t("exports_empty")}</p>}
        {items.length > 0 && (
          <div className="overflow-x-auto">
            <table className="grid">
              <thead>
                <tr>
                  <th scope="col">{t("export_file")}</th>
                  <th scope="col">{t("export_format")}</th>
                  <th scope="col">{t("export_size")}</th>
                  <th scope="col">{t("export_date")}</th>
                  <th scope="col">SHA-256</th>
                </tr>
              </thead>
              <tbody>
                {items.map((x) => (
                  <tr key={x.id}>
                    <td><a href={x.url || api.exportUrl(x.id)} download={x.filename}>{x.filename}</a></td>
                    <td><span className="chip">{String(x.format).toUpperCase()}</span></td>
                    <td className="num">{formatBytes(x.bytes, lang)}</td>
                    <td className="num">{clock(x.created_at, lang)}</td>
                    <td className="mono" title={x.sha256}>{(x.sha256 || "").slice(0, 12)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>
    </div>
  );
}
