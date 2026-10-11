import React, { useEffect, useState } from "react";
import { api } from "../../api.js";
import { useApp } from "../../App.jsx";
import { useDeck } from "../../components/deckContext.js";
import { ConfirmButton, Field, Section, useAsync } from "../../components/ui.jsx";

// Native animations and transitions of the PPTX export (GET|PUT|DELETE /api/decks/{id}/animations, same code as the
// deck_animations tool). Deck settings plus per-slide overrides of mode and transition; "Check" reads what the next
// export would carry from the saved settings.
const DECK_KEYS = ["mode", "trigger", "duration", "transition", "transition_duration"];
const pretty = (key) => key.replace(/^(entrance|emphasis|exit|path)_/, "").replace(/_/g, " ");

function ModeSelect({ id, value, onChange, catalogue, t, inherit }) {
  return (
    <select id={id} className="field" value={value ?? ""} onChange={(e) => onChange(e.target.value)}>
      {inherit && <option value="">{t("anim_inherit")}</option>}
      <optgroup label={t("anim_modes")}>
        {catalogue.modes.map((m) => <option key={m} value={m}>{t(`anim_mode_${m}`)}</option>)}
      </optgroup>
      {Object.entries(catalogue.effects).map(([group, keys]) => (
        <optgroup key={group} label={t(`anim_group_${group}`)}>
          {keys.map((k) => <option key={k} value={k}>{pretty(k)}</option>)}
        </optgroup>
      ))}
    </select>
  );
}

function TransitionSelect({ id, value, onChange, catalogue, t, inherit }) {
  return (
    <select id={id} className="field" value={value ?? ""} onChange={(e) => onChange(e.target.value)}>
      {inherit && <option value="">{t("anim_inherit")}</option>}
      {catalogue.transitions.map((k) => <option key={k} value={k}>{k === "none" ? t("anim_none") : pretty(k)}</option>)}
    </select>
  );
}

export default function Motion() {
  const { t, notify } = useApp();
  const { deckId, deck, run, busy } = useDeck();
  const cat = useAsync(() => api.animationsCatalogue(), []);
  const saved = useAsync(() => api.animations(deckId), [deckId]);
  const [draft, setDraft] = useState(null);
  const [preview, setPreview] = useState(null);
  useEffect(() => { if (saved.data) setDraft(saved.data); }, [saved.data]);

  const slides = (deck.slides || []).slice().sort((a, b) => a.position - b.position);
  const failure = cat.error || saved.error;
  if (failure) return <Section title={t("anim_title")}><p className="help">{failure.message}</p></Section>;
  if (!draft || !cat.data) return <Section title={t("anim_title")}><p className="help" role="status">{t("loading")}</p></Section>;

  const catalogue = cat.data;
  const dirty = JSON.stringify(draft) !== JSON.stringify(saved.data);
  const set = (key, value) => setDraft((d) => ({ ...d, [key]: value }));
  const setSlide = (sid, key, value) => setDraft((d) => {
    const layer = { ...((d.slides || {})[sid] || {}) };
    if (value === "" || value == null) delete layer[key]; else layer[key] = value;
    return { ...d, slides: { ...(d.slides || {}), [sid]: layer } };
  });

  const save = async () => {
    const body = Object.fromEntries(DECK_KEYS.map((k) => [k, draft[k]]));
    body.slides = Object.fromEntries(slides.map((s) => [s.id, (draft.slides || {})[s.id] || {}])); // {} drops an override
    const res = await run(t("busy_saving"), () => api.animationsSave(deckId, body));
    if (res) { notify(t("anim_saved")); setPreview(null); saved.reload(); }
  };
  const reset = async () => {
    const res = await run(t("busy_saving"), () => api.animationsReset(deckId));
    if (res) { notify(t("anim_reset_done")); setPreview(null); saved.reload(); }
  };
  const check = async () => {
    const res = await run(t("anim_busy_check"), () => api.animationsPreview(deckId));
    if (res) setPreview(res);
  };

  const right = (
    <div className="flex flex-wrap gap-2">
      <button type="button" className="btn btn-primary" disabled={!!busy || !dirty} onClick={save}>{t("save")}</button>
      <button type="button" className="btn" disabled={!!busy || dirty || slides.length === 0} onClick={check}
        title={dirty ? t("anim_save_first") : undefined}>{t("anim_check")}</button>
      <ConfirmButton t={t} label={t("anim_reset")} confirmLabel={t("anim_reset_confirm")} onConfirm={reset}
        disabled={!!busy} className="btn btn-sm" />
    </div>
  );

  return (
    <Section title={t("anim_title")} right={right}>
      <p className="help mb-3">{t("anim_help")}</p>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <Field label={t("anim_mode")} help={t(`anim_mode_${catalogue.modes.includes(draft.mode) ? draft.mode : "effect"}_help`)}>
          <ModeSelect id="motion-mode" value={draft.mode} onChange={(v) => set("mode", v)} catalogue={catalogue} t={t} />
        </Field>
        <Field label={t("anim_trigger")}>
          <select className="field" value={draft.trigger} onChange={(e) => set("trigger", e.target.value)}>
            {catalogue.triggers.map((k) => <option key={k} value={k}>{t(`anim_trigger_${k.replace("-", "_")}`)}</option>)}
          </select>
        </Field>
        <Field label={t("anim_duration")}>
          <input className="field num" type="number" min="0.05" max="10" step="0.05" value={draft.duration}
            onChange={(e) => set("duration", e.target.value === "" ? "" : Number(e.target.value))} />
        </Field>
        <Field label={t("anim_transition")}>
          <TransitionSelect id="motion-transition" value={draft.transition} onChange={(v) => set("transition", v)} catalogue={catalogue} t={t} />
        </Field>
        <Field label={t("anim_transition_duration")}>
          <input className="field num" type="number" min="0.05" max="10" step="0.05" value={draft.transition_duration}
            disabled={draft.transition === "none"}
            onChange={(e) => set("transition_duration", e.target.value === "" ? "" : Number(e.target.value))} />
        </Field>
      </div>

      {slides.length > 0 && (
        <details className="mt-4">
          <summary className="cursor-pointer text-[13px] font-semibold">{t("anim_per_slide", { n: Object.values(draft.slides || {}).filter((l) => Object.keys(l).length).length })}</summary>
          <div className="mt-2 overflow-x-auto">
            <table className="grid">
              <thead>
                <tr>
                  <th scope="col">#</th>
                  <th scope="col">{t("anim_slide")}</th>
                  <th scope="col">{t("anim_mode")}</th>
                  <th scope="col">{t("anim_transition")}</th>
                </tr>
              </thead>
              <tbody>
                {slides.map((s, n) => {
                  const layer = (draft.slides || {})[s.id] || {};
                  return (
                    <tr key={s.id}>
                      <td className="num">{n + 1}</td>
                      <td className="[overflow-wrap:anywhere]">{s.title || t("untitled")}</td>
                      <td><ModeSelect id={`motion-mode-${s.id}`} value={layer.mode} inherit onChange={(v) => setSlide(s.id, "mode", v)} catalogue={catalogue} t={t} /></td>
                      <td><TransitionSelect id={`motion-tr-${s.id}`} value={layer.transition} inherit onChange={(v) => setSlide(s.id, "transition", v)} catalogue={catalogue} t={t} /></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </details>
      )}

      {dirty && <p className="help mt-2" role="status">{t("anim_unsaved")}</p>}
      {preview && (
        <div className="mt-4">
          <p className="help mb-2" role="status">{t("anim_preview_summary", { a: preview.animated, tr: preview.transitions })}</p>
          <div className="overflow-x-auto">
            <table className="grid">
              <thead>
                <tr>
                  <th scope="col">#</th>
                  <th scope="col">{t("anim_mode")}</th>
                  <th scope="col">{t("anim_transition")}</th>
                  <th scope="col">{t("anim_animated")}</th>
                  <th scope="col">{t("anim_clicks")}</th>
                  <th scope="col">{t("anim_effects")}</th>
                </tr>
              </thead>
              <tbody>
                {preview.slides.map((r) => (
                  <tr key={r.slide}>
                    <td className="num">{r.slide}</td>
                    <td>{catalogue.modes.includes(r.mode) ? t(`anim_mode_${r.mode}`) : pretty(r.mode)}</td>
                    <td>{r.transition === "none" ? t("anim_none") : pretty(r.transition)}</td>
                    <td className="num">{r.animated}</td>
                    <td className="num">{r.clicks}</td>
                    <td className="[overflow-wrap:anywhere]">{(r.effects || []).map(pretty).join(", ") || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </Section>
  );
}
