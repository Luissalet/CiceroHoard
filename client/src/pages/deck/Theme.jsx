import React from "react";
import { api } from "../../api.js";
import { useApp } from "../../App.jsx";
import { useDeck } from "../../components/deckContext.js";
import SlideFrame from "../../components/SlideFrame.jsx";
import { Empty, Section, Tabs, panelId, tabId, useAsync } from "../../components/ui.jsx";
import { StartVitruvius } from "./DesignAudit.jsx";

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

// A design system's roles in one mode, shaped like a theme so the same miniature can draw it.
function roleTheme(roles, mode) {
  const p = roles?.[mode];
  if (!p) return null;
  return {
    colors: { background: p.background, surface: p.surface2 || p.surface, text: p.text, muted: p.muted, accent: p.accent, accent2: p.accent2 },
    fonts: { heading: roles.fonts?.heading, body: roles.fonts?.body },
  };
}

// "Theme from a design system": the design systems of the family design-system app, each in its light and dark mode.
function FromDesignSystems({ deckId, setDeck, run, busy, onCreated }) {
  const { t, notify } = useApp();
  const systems = useAsync(() => api.designSystems(), []);
  const [last, setLast] = React.useState(null);
  const items = systems.data?.items || [];

  const make = (system, mode) => run(t("busy_saving"), async () => {
    const made = await api.themeFromTokens(system.id, mode);
    const res = await api.deckUpdate(deckId, { theme: made.theme.id });
    setDeck(res.deck || res);
    setLast({ name: made.theme.name, warnings: made.warnings || [], created: made.created });
    onCreated();
    notify(t(made.created ? "theme_ds_created" : "theme_ds_reused", { name: made.theme.name }));
    return true;
  });

  return (
    <Section title={t("theme_ds_title")} right={<button type="button" className="btn" onClick={systems.reload} disabled={systems.loading}>{t("theme_ds_reload")}</button>}>
      <p className="help mb-3">{t("theme_ds_help")}</p>
      {systems.loading && !items.length && <p className="help" role="status">{t("theme_ds_loading")}</p>}
      {systems.error && <p className="help" role="alert">{t("theme_ds_unavailable", { reason: systems.error.message })}</p>}
      {!systems.loading && !systems.error && !items.length && <p className="help">{t("theme_ds_none")}</p>}
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {items.map((system) => (
          <div key={system.id} className="theme-card" data-design-system={system.id}>
            <div className="grid grid-cols-2 gap-2">
              {["light", "dark"].map((mode) => {
                const th = roleTheme(system.roles, mode);
                return th ? <Mini key={mode} theme={th} title={system.name} subtitle={t(mode === "light" ? "theme_ds_light" : "theme_ds_dark")} /> : <span key={mode} />;
              })}
            </div>
            <div className="mt-2 font-semibold">{system.name}</div>
            <div className="mt-1 flex flex-wrap gap-2">
              {["light", "dark"].filter((mode) => system.roles?.[mode]).map((mode) => (
                <button key={mode} type="button" className="btn" disabled={!!busy} onClick={() => make(system, mode)}>
                  {t(mode === "light" ? "theme_ds_use_light" : "theme_ds_use_dark")}
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>
      {last && (
        <div className="mt-3" role="status">
          <div className="help">{t(last.created ? "theme_ds_created" : "theme_ds_reused", { name: last.name })}</div>
          {last.warnings.length > 0 && (
            <ul className="help mt-1 list-disc pl-5">{last.warnings.map((w) => <li key={w}>{w}</li>)}</ul>
          )}
        </div>
      )}
    </Section>
  );
}

// A preset's swatches (background, card, muted, primary, foreground) shaped like a theme for the miniature.
function swatchTheme(preset, mode) {
  const s = preset.swatches?.[mode];
  if (!s || s.length < 5) return null;
  return { colors: { background: s[0], surface: s[2], text: s[4], muted: s[4], accent: s[3], accent2: s[3] },
           fonts: { heading: preset.fonts?.heading, body: preset.fonts?.body } };
}

function PresetCard({ preset, recommended, busy, onUse }) {
  const { t } = useApp();
  return (
    <div className="theme-card" data-preset={preset.name}>
      <div className="grid grid-cols-2 gap-2">
        {["light", "dark"].map((mode) => {
          const th = swatchTheme(preset, mode);
          return th ? <Mini key={mode} theme={th} title={preset.title || preset.name} subtitle={t(mode === "light" ? "theme_ds_light" : "theme_ds_dark")} /> : <span key={mode} />;
        })}
      </div>
      {["light", "dark"].map((mode) => (
        <div key={mode} className="mt-1 flex gap-1" aria-hidden="true">
          {(preset.swatches?.[mode] || []).map((c, i) => <span key={i} title={c} style={{ width: 18, height: 12, background: c, borderRadius: 2, border: "1px solid #8884" }} />)}
        </div>
      ))}
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <span className="font-semibold">{preset.title || preset.name}</span>
        {recommended && <span className="chip chip-accent">{t("theme_vp_recommended")}</span>}
        {preset.genre && <span className="help">{preset.genre}</span>}
      </div>
      {preset.why && <div className="help">{preset.why}</div>}
      {preset.character && <div className="help" style={{ display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}>{preset.character}</div>}
      <div className="help">{preset.fonts?.heading} · {preset.fonts?.body} · {preset.radius}</div>
      <div className="mt-1 flex flex-wrap gap-2">
        {["light", "dark"].filter((mode) => preset.swatches?.[mode]).map((mode) => (
          <button key={mode} type="button" className="btn btn-sm" disabled={!!busy} onClick={() => onUse(preset, mode)} data-use={`${preset.name}:${mode}`}>
            {t(mode === "light" ? "theme_ds_use_light" : "theme_ds_use_dark")}
          </button>
        ))}
      </div>
    </div>
  );
}

const PAGE = 24;

// "From Vitruvius": the design presets of the family design studio, searchable, and three picked for the deck brief.
function FromPresets({ deckId, setDeck, run, busy, onCreated }) {
  const { t, notify } = useApp();
  const presets = useAsync(() => api.designPresets({ limit: 200 }), []);
  const [query, setQuery] = React.useState("");
  const [shown, setShown] = React.useState(PAGE);
  const [picks, setPicks] = React.useState({ busy: false, data: null, error: null });
  const [last, setLast] = React.useState(null);
  const all = presets.data?.items || [];
  const q = query.trim().toLowerCase();
  const filtered = q ? all.filter((p) => [p.name, p.title, p.genre, p.character, ...(p.keywords || [])].join(" ").toLowerCase().includes(q)) : all;

  const pick = async () => {
    setPicks({ busy: true, data: null, error: null });
    try {
      setPicks({ busy: false, data: await api.pickPresets(deckId, 3), error: null });
    } catch (error) {
      setPicks({ busy: false, data: null, error: error.message });
    }
  };
  const use = (preset, mode) => run(t("busy_saving"), async () => {
    const made = await api.themeFromPreset(preset.name, mode);
    const res = await api.deckUpdate(deckId, { theme: made.theme.id });
    setDeck(res.deck || res);
    setLast({ name: made.theme.name, warnings: made.warnings || [], created: made.created });
    onCreated();
    notify(t(made.created ? "theme_ds_created" : "theme_ds_reused", { name: made.theme.name }));
    return true;
  });
  const failed = presets.error || picks.error;
  const reloadAll = () => { presets.reload(); if (picks.error) pick(); };

  return (
    <Section title={t("theme_vp_title")} right={<button type="button" className="btn" onClick={presets.reload} disabled={presets.loading}>{t("theme_ds_reload")}</button>}>
      <p className="help mb-3">{t("theme_vp_help")}</p>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <button type="button" className="btn btn-primary" disabled={picks.busy || !!busy} onClick={pick} data-action="pick-presets">
          {picks.busy ? t("theme_vp_picking") : t("theme_vp_pick")}
        </button>
        <input type="search" className="field w-full max-w-xs" placeholder={t("theme_vp_search")} aria-label={t("theme_vp_search")} value={query}
          onChange={(e) => { setQuery(e.target.value); setShown(PAGE); }} />
      </div>
      {failed && (
        <div className="mb-3 flex flex-wrap items-center gap-2" role="alert">
          <span className="help">{t("theme_vp_unavailable", { reason: (presets.error && presets.error.message) || picks.error })}</span>
          <StartVitruvius onStarted={reloadAll} />
        </div>
      )}
      {picks.data && (
        <div className="mb-4" data-picks="">
          <h4 className="mb-2 text-[13px] font-semibold">{t("theme_vp_picks")}</h4>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {picks.data.items.map((p) => <PresetCard key={p.name} preset={p} recommended={p.name === picks.data.recommended} busy={busy} onUse={use} />)}
          </div>
        </div>
      )}
      {presets.loading && !all.length && <p className="help" role="status">{t("theme_vp_loading")}</p>}
      {!presets.loading && !presets.error && (
        <p className="help mb-2">{t("theme_vp_all", { n: Math.min(shown, filtered.length), total: filtered.length })}</p>
      )}
      {!presets.loading && !presets.error && q && !filtered.length && <p className="help">{t("theme_vp_none")}</p>}
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {filtered.slice(0, shown).map((p) => <PresetCard key={p.name} preset={p} busy={busy} onUse={use} />)}
      </div>
      {filtered.length > shown && (
        <button type="button" className="btn mt-3" onClick={() => setShown(shown + PAGE)}>{t("theme_vp_more")}</button>
      )}
      {last && (
        <div className="mt-3" role="status">
          <div className="help">{t(last.created ? "theme_ds_created" : "theme_ds_reused", { name: last.name })}</div>
          {last.warnings.length > 0 && <ul className="help mt-1 list-disc pl-5">{last.warnings.map((w) => <li key={w}>{w}</li>)}</ul>}
        </div>
      )}
    </Section>
  );
}

// Same rule as the server (relative luminance under 0.4 is a dark page).
function isDark(hex) {
  const m = /^#([0-9a-f]{6})$/i.exec(hex || "");
  if (!m) return false;
  const [r, g, b] = [0, 2, 4].map((i) => parseInt(m[1].slice(i, i + 2), 16) / 255).map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b < 0.4;
}

export default function Theme() {
  const { t, notify } = useApp();
  const [source, setSource] = React.useState("theme-ds");
  const { deckId, deck, setDeck, run, busy } = useDeck();
  const themes = useAsync(() => api.themes(), []);
  const items = themes.data?.items || [];
  const slides = (deck.slides || []).slice().sort((a, b) => a.position - b.position);
  const first = slides[0];
  const uploadTemplate = (file) => file && run(t("busy_uploading"), async () => {
    const res = await api.templateUpload(deckId, file);
    setDeck(res.deck || res);
    return true;
  });
  const clearTemplate = () => run(t("busy_saving"), async () => {
    const res = await api.templateClear(deckId);
    setDeck(res.deck || res);
    return true;
  });

  const choose = (id) => run(t("busy_saving"), async () => {
    const res = await api.deckUpdate(deckId, { theme: id });
    setDeck(res.deck || res);
    return true;
  });

  // Deleting a saved theme: decks that used it move to the built-in theme of the same kind (the server says which).
  const remove = (th) => {
    const fallbackId = isDark(th.colors?.background) ? "oscuro" : "claro";
    const fallback = items.find((x) => x.id === fallbackId)?.name || fallbackId;
    if (!window.confirm(t("theme_delete_confirm", { name: th.name, fallback }))) return;
    run(t("busy_saving"), async () => {
      const res = await api.themeDelete(th.id);
      const moved = res.decks_moved || [];
      if (moved.includes(deckId)) { const fresh = await api.deck(deckId); setDeck(fresh.deck || fresh); }
      themes.reload();
      notify(moved.length ? t("theme_deleted_moved", { name: th.name, n: moved.length, fallback }) : t("theme_deleted", { name: th.name }));
      return true;
    });
  };

  if (themes.error) return <Empty>{themes.error.message}</Empty>;
  return (
    <div className="space-y-4">
      <Section title={t("template_title")}>
        <p className="help mb-3">{t("template_help")}</p>
        <div className="flex flex-wrap items-center gap-3">
          <label className="btn">
            {t("template_upload")}
            <input type="file" accept=".pptx" aria-label={t("template_upload")} className="sr-only-live" disabled={!!busy}
              onChange={(e) => { uploadTemplate(e.target.files[0]); e.target.value = ""; }} />
          </label>
          {deck.template && <>
            <span className="min-w-0 [overflow-wrap:anywhere]" role="status">{deck.template.name}</span>
            <button type="button" className="btn" disabled={!!busy} onClick={clearTemplate}>{t("template_clear")}</button>
          </>}
        </div>
        {deck.template && <p className="help mt-3">{t("template_preview_help")}</p>}
      </Section>
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
              <div className="help">{th.fonts?.heading} · {th.fonts?.body}{th.custom ? ` · ${t(String(th.source_ref || "").includes("/preset/") ? "theme_vp_badge" : "theme_ds_badge")}` : ""}</div>
              {th.custom && (
                <button type="button" className="btn btn-sm mt-2" disabled={!!busy} data-action="theme-delete" data-theme={th.id}
                  onClick={(e) => { e.preventDefault(); e.stopPropagation(); remove(th); }}>{t("theme_delete")}</button>
              )}
            </label>
          ))}
        </div>
      </Section>
      <Tabs label={t("theme_choose")} active={source} onChange={setSource}
        tabs={[{ key: "theme-ds", label: t("theme_tab_ds") }, { key: "theme-presets", label: t("theme_tab_presets") }]} />
      <div role="tabpanel" id={panelId(source)} aria-labelledby={tabId(source)}>
        {source === "theme-ds"
          ? <FromDesignSystems deckId={deckId} setDeck={setDeck} run={run} busy={busy} onCreated={themes.reload} />
          : <FromPresets deckId={deckId} setDeck={setDeck} run={run} busy={busy} onCreated={themes.reload} />}
      </div>
      {first && (
        <Section title={t("theme_real")}>
          {deck.template && <p className="help mb-3">{t("template_preview_help")}</p>}
          <div className="max-w-2xl"><SlideFrame deckId={deckId} slide={first} theme={deck.theme} title={t("theme_real")} /></div>
        </Section>
      )}
    </div>
  );
}
