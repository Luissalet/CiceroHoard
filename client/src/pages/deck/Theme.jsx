import React from "react";
import { api } from "../../api.js";
import { useApp } from "../../App.jsx";
import { useDeck } from "../../components/deckContext.js";
import SlideFrame from "../../components/SlideFrame.jsx";
import { Empty, Section, useAsync } from "../../components/ui.jsx";

// Client-side miniature of a title slide in the theme's colours and fonts (the real slide is the iframe below).
function Mini({ theme, title, subtitle }) {
  const c = theme.colors || {};
  const f = theme.fonts || {};
  return (
    <div className="theme-mini" aria-hidden="true" style={{ background: c.background, color: c.text, fontFamily: f.body }}>
      <div style={{ width: "16%", height: "3cqw", background: c.accent, borderRadius: 2 }} />
      <div style={{ fontFamily: f.heading, fontWeight: 700, fontSize: "7.5cqw", lineHeight: 1.15, overflow: "hidden", maxHeight: "3.4em" }}>{title}</div>
      <div style={{ color: c.muted, fontSize: "4.2cqw", lineHeight: 1.3, overflow: "hidden", maxHeight: "2.7em" }}>{subtitle}</div>
      <div style={{ display: "flex", gap: "1.5cqw" }}>
        {[c.surface, c.accent, c.accent2].map((color, i) => <span key={i} style={{ width: "4cqw", height: "4cqw", borderRadius: "50%", background: color, border: "1px solid #ffffff44" }} />)}
      </div>
    </div>
  );
}

export default function Theme() {
  const { t } = useApp();
  const { deckId, deck, setDeck, run, busy } = useDeck();
  const themes = useAsync(() => api.themes(), []);
  const items = themes.data?.items || [];
  const slides = (deck.slides || []).slice().sort((a, b) => a.position - b.position);
  const first = slides[0];

  const choose = (id) => run(t("busy_saving"), async () => {
    const res = await api.deckUpdate(deckId, { theme: id });
    setDeck(res.deck || res);
    return true;
  });

  if (themes.error) return <Empty>{themes.error.message}</Empty>;
  return (
    <div className="space-y-4">
      <Section title={t("theme_choose")} right={<span className="help">{t("theme_help")}</span>}>
        <div role="radiogroup" aria-label={t("theme_choose")} className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {items.map((th) => (
            <label key={th.id} className="theme-card">
              <input type="radio" name="theme" className="sr-only-live" checked={deck.theme === th.id} disabled={!!busy} onChange={() => choose(th.id)} />
              <Mini theme={th} title={deck.title} subtitle={deck.audience || deck.brief || ""} />
              <div className="mt-2 flex items-center justify-between gap-2">
                <span className="font-semibold">{th.name}</span>
                {deck.theme === th.id && <span className="chip chip-accent">{t("theme_current")}</span>}
              </div>
              <div className="help">{th.fonts?.heading} · {th.fonts?.body}</div>
            </label>
          ))}
        </div>
      </Section>
      {first && (
        <Section title={t("theme_real")}>
          <div className="max-w-2xl"><SlideFrame deckId={deckId} slide={first} theme={deck.theme} title={t("theme_real")} /></div>
        </Section>
      )}
    </div>
  );
}
