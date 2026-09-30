import React, { useEffect, useMemo, useState } from "react";
import { api } from "../../api.js";
import { useApp } from "../../App.jsx";
import { useDeck, useDirty } from "../../components/deckContext.js";
import { ConfirmButton, Field, Section } from "../../components/ui.jsx";
import { BLOCK_TYPES, LAYOUTS, clock } from "../../format.js";
import BlockEditor from "./BlockEditor.jsx";
import { blockToApi, blockToDraft, newBlock } from "./blocks.js";

const toDraft = (slide) => ({
  layout: slide.layout || "bullets",
  title: slide.title || "",
  subtitle: slide.subtitle || "",
  notes: slide.notes || "",
  image_prompt: slide.image_prompt || "",
  blocks: (slide.blocks || []).map(blockToDraft),
});

function Revisions({ slide }) {
  const { t, lang } = useApp();
  const { deckId, run, busy, reload } = useDeck();
  const [items, setItems] = useState(null);
  const load = async () => {
    const res = await run(t("busy_loading"), () => api.slideRevisions(deckId, slide.id));
    if (res) setItems((res.items || []).slice().sort((a, b) => b.revision - a.revision));
  };
  const revert = async (revision) => {
    await run(t("busy_saving"), async () => { await api.slideRevert(deckId, slide.id, revision); await reload(); return true; });
  };
  return (
    <details onToggle={(e) => { if (e.currentTarget.open && items === null) load(); }}>
      <summary className="cursor-pointer text-[13px] font-semibold">{t("revisions")}</summary>
      <div className="mt-2">
        {items === null && <p className="help">{t("loading")}</p>}
        {items && items.length === 0 && <p className="help">{t("revisions_empty")}</p>}
        <ul className="space-y-1.5">
          {(items || []).map((r) => (
            <li key={r.revision} className="flex flex-wrap items-center gap-2 text-[12px]">
              <span className="chip num">{t("revision_n", { n: r.revision })}</span>
              <span>{t(`reason_${r.reason}`)}</span>
              <span className="help">{clock(r.created_at, lang)}</span>
              <span className="ml-auto">
                {r.revision === slide.revision ? (
                  <span className="chip chip-ok">{t("revision_current")}</span>
                ) : (
                  <button type="button" className="btn btn-sm" disabled={!!busy} onClick={() => revert(r.revision)} aria-label={t("revision_restore_n", { n: r.revision })}>{t("revision_restore")}</button>
                )}
              </span>
            </li>
          ))}
        </ul>
      </div>
    </details>
  );
}

export default function SlideEditor({ slide, onDeleted }) {
  const { t, notify } = useApp();
  const { deckId, deck, reload, run, busy, noteGenerator } = useDeck();
  const initialKey = JSON.stringify(toDraft(slide));
  const initial = useMemo(() => JSON.parse(initialKey), [initialKey]);
  const [draft, setDraft] = useState(initial);
  const [feedback, setFeedback] = useState("");
  const [blockType, setBlockType] = useState("bullets");
  useEffect(() => setDraft(initial), [initial]);
  const dirty = JSON.stringify(draft) !== initialKey;
  useDirty(dirty);
  const off = !!busy;
  const approved = slide.status === "approved";
  const hasImage = draft.layout === "image_text" || draft.blocks.some((b) => b.type === "image");
  const set = (key) => (event) => setDraft({ ...draft, [key]: event.target.value });

  const setBlock = (i, block) => setDraft({ ...draft, blocks: draft.blocks.map((b, n) => (n === i ? block : b)) });
  const moveBlock = (i, d) => {
    const j = i + d;
    const blocks = draft.blocks.slice();
    [blocks[i], blocks[j]] = [blocks[j], blocks[i]];
    setDraft({ ...draft, blocks });
  };

  const patchBody = () => ({
    title: draft.title,
    subtitle: draft.subtitle,
    layout: draft.layout,
    notes: draft.notes,
    image_prompt: draft.image_prompt,
    blocks: draft.blocks.map((b, i) => blockToApi(b, t, i + 1)),
  });
  const saveInner = async () => { await api.slideUpdate(deckId, slide.id, patchBody()); await reload(); };

  const save = () => run(t("busy_saving"), async () => { await saveInner(); notify(t("saved")); return true; });
  const approve = () => run(t("busy_saving"), async () => {
    await (approved ? api.slideUnapprove(deckId, slide.id) : api.slideApprove(deckId, slide.id));
    await reload();
    return true;
  });
  const regenerate = () => run(t("busy_regenerate"), async () => {
    const res = await api.slideRegenerate(deckId, slide.id, feedback.trim());
    await reload();
    noteGenerator(res, t("what_slide"), deck.model_used);
    setFeedback("");
    return true;
  });
  const generateImage = () => run(t("busy_image"), async () => {
    if (dirty) await saveInner();
    await api.slideImage(deckId, slide.id, draft.image_prompt.trim());
    await reload();
    notify(t("image_generated"));
    return true;
  });
  const remove = async () => {
    const done = await run(t("busy_deleting"), async () => { await api.slideDelete(deckId, slide.id); await reload(); return true; });
    if (done) onDeleted();
  };

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <button type="button" className="btn btn-primary" disabled={off || !dirty} onClick={save}>{t("save")}</button>
        <button type="button" className="btn" disabled={off || !dirty} onClick={() => setDraft(initial)}>{t("discard")}</button>
        <button type="button" className={approved ? "btn" : "btn btn-active"} disabled={off || dirty} onClick={approve} title={dirty ? t("save_first") : undefined}>
          {approved ? t("unapprove") : t("approve")}
        </button>
        {dirty && <span className="help" role="status">{t("unsaved")}</span>}
      </div>

      <Section title={t("slide_content")}>
        <div className="space-y-3">
          <Field label={t("layout")}>
            <select className="field" value={draft.layout} disabled={off} onChange={set("layout")}>
              {LAYOUTS.map((l) => <option key={l} value={l}>{t(`layout_${l}`)}</option>)}
            </select>
          </Field>
          <Field label={t("slide_title")}><input className="field" value={draft.title} disabled={off} onChange={set("title")} /></Field>
          <Field label={t("slide_subtitle")}><input className="field" value={draft.subtitle} disabled={off} onChange={set("subtitle")} /></Field>
        </div>
      </Section>

      <Section title={t("blocks")}>
        <div className="space-y-2.5">
          {draft.blocks.length === 0 && <p className="help">{t("blocks_empty")}</p>}
          {draft.blocks.map((block, i) => (
            <BlockEditor
              key={i}
              block={block}
              index={i}
              count={draft.blocks.length}
              disabled={off}
              onChange={(b) => setBlock(i, b)}
              onMove={(d) => moveBlock(i, d)}
              onRemove={() => setDraft({ ...draft, blocks: draft.blocks.filter((_, n) => n !== i) })}
            />
          ))}
          <div className="flex flex-wrap items-end gap-2">
            <Field label={t("block_add_type")}>
              <select className="field" value={blockType} disabled={off} onChange={(e) => setBlockType(e.target.value)}>
                {BLOCK_TYPES.map((b) => <option key={b} value={b}>{t(`block_${b}`)}</option>)}
              </select>
            </Field>
            <button type="button" className="btn" disabled={off} onClick={() => setDraft({ ...draft, blocks: [...draft.blocks, newBlock(blockType, t)] })}>+ {t("block_add")}</button>
          </div>
        </div>
      </Section>

      {hasImage && (
        <Section title={t("image_section")}>
          <Field label={t("image_prompt")} help={t("image_prompt_help")}>
            <textarea className="field" rows={2} value={draft.image_prompt} disabled={off} onChange={set("image_prompt")} />
          </Field>
          <button type="button" className="btn mt-2" disabled={off} onClick={generateImage}>{t("image_generate")}</button>
          <p className="help mt-1">{t("image_generate_help")}</p>
        </Section>
      )}

      <Section title={t("notes")}>
        <textarea className="field" rows={5} value={draft.notes} disabled={off} aria-label={t("notes")} onChange={set("notes")} placeholder={t("notes_ph")} />
      </Section>

      <Section title={t("regenerate")}>
        <Field label={t("regenerate_feedback")} help={dirty ? t("regenerate_dirty") : t("regenerate_help")}>
          <textarea className="field" rows={3} value={feedback} disabled={off} onChange={(e) => setFeedback(e.target.value)} placeholder={t("regenerate_ph")} />
        </Field>
        <button type="button" className="btn mt-2" disabled={off || dirty} onClick={regenerate}>{t("regenerate_go")}</button>
      </Section>

      <section className="panel space-y-3">
        <Revisions slide={slide} />
        <div className="flex flex-wrap items-center justify-between gap-2 border-t pt-3" style={{ borderColor: "var(--line)" }}>
          <span className="help">{t("revision_n", { n: slide.revision })}</span>
          <ConfirmButton t={t} disabled={off} label={t("slide_delete")} confirmLabel={t("slide_delete_confirm")} onConfirm={remove} />
        </div>
      </section>
    </div>
  );
}
