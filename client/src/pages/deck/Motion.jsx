import React, { useEffect, useState } from "react";
import { api } from "../../api.js";
import { useApp } from "../../App.jsx";
import { useDeck, useDirty } from "../../components/deckContext.js";
import { ConfirmButton, Section, useAsync } from "../../components/ui.jsx";

// Native animations of the PPTX export, per slide (GET|PUT|DELETE /api/decks/{id}/animations, same code as the
// deck_animations tool). The deck-wide mode and the transitions live in the transitions panel above; here each slide can
// take its own animation mode, and «Check» lists what the next PPTX will carry, slide by slide, from the saved settings.
const pretty = (key) => key.replace(/^(entrance|emphasis|exit|path)_/, "").replace(/_/g, " ");

function ModeSelect({ value, onChange, catalogue, t, label }) {
  return (
    <select className="field" aria-label={label} value={value ?? ""} onChange={(e) => onChange(e.target.value)}>
      <option value="">{t("anim_inherit")}</option>
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

const modesOf = (settings) => Object.fromEntries(Object.entries(settings?.slides || {}).map(([sid, layer]) => [sid, layer.mode || ""]));

export default function Motion() {
  const { t, notify } = useApp();
  const { deckId, deck, run, busy } = useDeck();
  const cat = useAsync(() => api.animationCatalogue(), []);
  const saved = useAsync(() => api.animations(deckId), [deckId]);
  const [draft, setDraft] = useState(null);
  const [preview, setPreview] = useState(null);
  useEffect(() => { if (saved.data) setDraft(modesOf(saved.data)); }, [saved.data]);
  // Same unsaved-changes guard as the other editors: changing tab or leaving asks first.
  const dirty = !!draft && !!saved.data && JSON.stringify(draft) !== JSON.stringify(modesOf(saved.data));
  useDirty(dirty);

  const slides = (deck.slides || []).slice().sort((a, b) => a.position - b.position);
  const failure = cat.error || saved.error;
  if (failure) return <Section title={t("anim_title")}><p className="help">{failure.message}</p></Section>;
  if (!draft || !cat.data) return <Section title={t("anim_title")}><p className="help" role="status">{t("loading")}</p></Section>;
  const catalogue = cat.data;

  const save = async () => {
    // Only the mode is sent: null drops that slide's own mode («as the presentation») and keeps any other per-slide
    // setting made elsewhere (transition, trigger or duration through the tool); a layer left empty disappears.
    const body = { slides: Object.fromEntries(slides.map((s) => [s.id, { mode: draft[s.id] || null }])) };
    const res = await run(t("busy_saving"), () => api.animationsSet(deckId, body));
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
  const deckMode = saved.data.mode;
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
      <p className="help mb-3">{t("anim_help", { mode: catalogue.modes.includes(deckMode) ? t(`anim_mode_${deckMode}`) : pretty(deckMode || "") })}</p>
      {slides.length > 0 && (
        <div className="overflow-x-auto">
          <table className="grid">
            <thead>
              <tr>
                <th scope="col">#</th>
                <th scope="col">{t("anim_slide")}</th>
                <th scope="col">{t("anim_mode")}</th>
              </tr>
            </thead>
            <tbody>
              {slides.map((s, n) => (
                <tr key={s.id}>
                  <td className="num">{n + 1}</td>
                  <td className="[overflow-wrap:anywhere]">{s.title || t("untitled")}</td>
                  <td><ModeSelect value={draft[s.id]} label={t("anim_mode_for", { n: n + 1 })} catalogue={catalogue} t={t}
                    onChange={(v) => setDraft((d) => ({ ...d, [s.id]: v }))} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
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
