"""Tools exposed to the assistant. One catalogue drives /api/agent/*, mcp_server.py and the UI routes."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Literal, Optional

from pydantic import BaseModel, Field

from . import decks as store
from . import generate as gen
from . import images as images_mod
from .errors import CiceroError
from .models import (Block, DeckCreate, DeckPatch, ExportFormat, Language, Layout, MAX_BLOCKS, MAX_SLIDES, OutlineItemIn, SlidePatch)
from .services import Services
from . import custom_themes

AGENT_INSTRUCTIONS = """Cicero's Hoard builds presentations that a person can review slide by slide. Work in this order: deck_create (title, brief,
audience, tone, language, number of slides) -> source_add (paste the text you may use, or a document the user names; figures on slides must come from
sources) -> outline_generate (or outline_update with your own items) -> show the outline to the user and wait for their agreement -> slides_generate ->
deck_check -> slide_update / slide_regenerate for what the check reports -> slide_approve for each slide the user accepts -> deck_export
(pptx, pdf, html or md).
Rules: never invent figures, names, dates or quotes: a number on a slide must appear in a source (deck_check lists the ones that do not); charts only
from numbers in the sources. Every edit creates a revision and slide_revert undoes it. Approved slides are kept when slides are generated again;
draft slides are rewritten. Without a reachable model the outline and slides come from the sources by fixed rules ("generator": "fallback"), and
slide_regenerate says so instead of pretending. Speaker notes are part of the deliverable: write them. Deletes (deck_delete, slide_delete,
source_remove) need confirm=true; ask the user first. Replacing the outline (outline_generate, outline_update) or drafts (slides_generate) discards
what they held: ask when the user has edited them. deck_export returns the file path on disk and the download URL."""


class Empty(BaseModel):
    pass


DeckId = Field(..., min_length=1, max_length=40, description="Deck id (from deck_list or deck_create).")


class DeckGetArgs(BaseModel):
    deck_id: str = DeckId
    detail: Literal["summary", "full"] = Field("summary", description="summary: slides as one line each; full: every block and note (large).")


class DeckUpdateArgs(DeckPatch):
    deck_id: str = DeckId


class DeckDeleteArgs(BaseModel):
    deck_id: str = DeckId
    confirm: bool = Field(False, description="Required: removes the deck with its sources, slides, revisions, images and exports.")


class SourceAddArgs(BaseModel):
    deck_id: str = DeckId
    title: str = Field("", max_length=300)
    text: str = Field("", max_length=400_000, description="The text to keep as a source (paste it).")
    path: str = Field("", max_length=1000, description="A local txt/md/pdf/docx/pptx file the user named explicitly (allowed folders may be restricted).")
    kind: Literal["text", "markdown"] = "text"


class SourceRefArgs(BaseModel):
    deck_id: str = DeckId
    source_id: int


class SourceGetArgs(SourceRefArgs):
    offset: int = Field(0, ge=0)
    max_chars: int = Field(4000, ge=200, le=12000)


class SourceRemoveArgs(SourceRefArgs):
    confirm: bool = Field(False, description="Required to remove the source.")


class DeckIdArgs(BaseModel):
    deck_id: str = DeckId


class OutlineUpdateArgs(BaseModel):
    deck_id: str = DeckId
    items: list[OutlineItemIn] = Field(..., max_length=MAX_SLIDES, description="The whole outline: {id?, title, purpose, points[], layout_hint?} in order.")


class SlidesGenerateArgs(BaseModel):
    deck_id: str = DeckId
    only_missing: bool = Field(False, description="Only create slides for outline items that have none.")


class SlideRefArgs(BaseModel):
    deck_id: str = DeckId
    slide_id: str = Field(..., min_length=1, max_length=40)


class SlideUpdateArgs(SlidePatch):
    deck_id: str = DeckId
    slide_id: str = Field(..., min_length=1, max_length=40)


class SlideRegenerateArgs(SlideRefArgs):
    feedback: str = Field("", max_length=2000, description="What to change, in the person's words.")


class SlideApproveArgs(SlideRefArgs):
    approved: bool = Field(True, description="false removes the approval.")


class SlideRevertArgs(SlideRefArgs):
    revision: Optional[int] = Field(None, ge=1, description="Restore this revision as a new one; omit to list the revisions.")


class SlideAddArgs(BaseModel):
    deck_id: str = DeckId
    after_id: Optional[str] = Field(None, max_length=40, description="Insert after this slide; omit to append.")
    layout: Layout = "bullets"
    title: str = Field("", max_length=200)
    subtitle: Optional[str] = Field(None, max_length=300)
    blocks: Optional[list[Block]] = Field(None, max_length=MAX_BLOCKS)
    notes: str = Field("", max_length=6000)
    image_prompt: Optional[str] = Field(None, max_length=1000, description="Description of the picture for the image studio (slide_image).")
    sources: Optional[list[int]] = Field(None, max_length=50, description="Source ids this slide draws on.")


class SlideDeleteArgs(SlideRefArgs):
    confirm: bool = Field(False, description="Required to delete the slide and its revisions.")


class ReorderArgs(BaseModel):
    deck_id: str = DeckId
    order: list[str] = Field(..., min_length=1, max_length=MAX_SLIDES * 3, description="Every slide id, in the new order.")


class ThemeArgs(BaseModel):
    deck_id: Optional[str] = Field(None, max_length=40)
    theme: Optional[str] = Field(None, max_length=40, description="Theme id to apply; omit to list the themes.")


class ThemeFromTokensArgs(BaseModel):
    tokens_id: Optional[str] = Field(None, max_length=80, description="Id of a design system in the family design-system app; omit to list the ones available.")
    mode: Literal["light", "dark"] = Field("light", description="Which of the design system's two colour modes becomes the theme.")
    deck_id: Optional[str] = Field(None, max_length=40, description="Also apply the new theme to this presentation.")


class ExportArgs(BaseModel):
    deck_id: str = DeckId
    format: ExportFormat


class SlideImageArgs(SlideRefArgs):
    prompt: Optional[str] = Field(None, max_length=1000, description="Picture description; defaults to the slide's image_prompt.")


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    input_model: type[BaseModel]
    annotations: dict[str, bool]
    run: Callable[[Services, Any], Any]


def _ann(read_only: bool, destructive: bool = False, idempotent: bool | None = None, open_world: bool = False) -> dict[str, bool]:
    return {"readOnlyHint": read_only, "destructiveHint": destructive,
            "idempotentHint": read_only if idempotent is None else idempotent, "openWorldHint": open_world}


# ---------------- runners ----------------

def run_status(svc: Services, args: Empty) -> dict:
    return svc.status()


def run_deck_list(svc: Services, args: Empty) -> dict:
    return store.list_decks(svc)


def run_deck_create(svc: Services, a: DeckCreate) -> dict:
    return store.create_deck(svc, a)


def _compact_slide(s: dict) -> dict:
    bullets = sum(len(b.get("items", [])) for b in s["blocks"] if b.get("type") == "bullets")
    return {"id": s["id"], "position": s["position"], "layout": s["layout"], "title": s["title"], "status": s["status"], "revision": s["revision"],
            "blocks": [b["type"] for b in s["blocks"]], "bullets": bullets, "has_notes": bool(s["notes"].strip()), "sources": s["sources"]}


def run_deck_get(svc: Services, a: DeckGetArgs) -> dict:
    deck = store.deck_view(svc, a.deck_id)
    if a.detail == "summary":
        deck["slides"] = [_compact_slide(s) for s in deck["slides"]]
    return deck


def run_deck_update(svc: Services, a: DeckUpdateArgs) -> dict:
    return store.update_deck(svc, a.deck_id, a.model_dump(exclude={"deck_id"}, exclude_none=True))


def run_deck_delete(svc: Services, a: DeckDeleteArgs) -> dict:
    return store.delete_deck(svc, a.deck_id, a.confirm)


def run_source_add(svc: Services, a: SourceAddArgs) -> dict:
    if a.path and a.text:
        raise CiceroError("Pass either text or path, not both.")
    if a.path:
        return store.add_source_path(svc, a.deck_id, a.path)
    if not a.text.strip():
        raise CiceroError("Pass the source text (text) or a local file (path).")
    return store.add_source_text(svc, a.deck_id, a.title or "Text", a.text, a.kind)


def run_source_list(svc: Services, a: DeckIdArgs) -> dict:
    return store.list_sources(svc, a.deck_id)


def run_source_get(svc: Services, a: SourceGetArgs) -> dict:
    return store.get_source(svc, a.deck_id, a.source_id, offset=a.offset, max_chars=a.max_chars)


def run_source_remove(svc: Services, a: SourceRemoveArgs) -> dict:
    if not a.confirm:
        raise CiceroError("Removing a source needs confirm=true; slides that cite it lose the reference.", code="confirm_required")
    return store.remove_source(svc, a.deck_id, a.source_id)


def run_outline_generate(svc: Services, a: DeckIdArgs) -> dict:
    return gen.generate_outline(svc, a.deck_id)


def run_outline_update(svc: Services, a: OutlineUpdateArgs) -> dict:
    return store.set_outline(svc, a.deck_id, a.items)


def run_slides_generate(svc: Services, a: SlidesGenerateArgs) -> dict:
    return gen.generate_slides(svc, a.deck_id, a.only_missing)


def run_slide_get(svc: Services, a: SlideRefArgs) -> dict:
    return store.get_slide(svc, a.deck_id, a.slide_id)


def run_slide_update(svc: Services, a: SlideUpdateArgs) -> dict:
    return store.patch_slide(svc, a.deck_id, a.slide_id, a.model_dump(exclude={"deck_id", "slide_id"}, exclude_none=True))


def run_slide_regenerate(svc: Services, a: SlideRegenerateArgs) -> dict:
    return gen.regenerate_slide(svc, a.deck_id, a.slide_id, a.feedback)


def run_slide_approve(svc: Services, a: SlideApproveArgs) -> dict:
    return store.set_approval(svc, a.deck_id, a.slide_id, a.approved)


def run_slide_revert(svc: Services, a: SlideRevertArgs) -> dict:
    if a.revision is None:
        items = store.list_revisions(svc, a.deck_id, a.slide_id)["items"]
        return {"items": [{"revision": r["revision"], "created_at": r["created_at"], "reason": r["reason"], "title": r["snapshot"].get("title", ""),
                           "layout": r["snapshot"].get("layout", "")} for r in items]}
    return store.revert_slide(svc, a.deck_id, a.slide_id, a.revision)


def run_slide_add(svc: Services, a: SlideAddArgs) -> dict:
    return store.add_slide(svc, a.deck_id, after_id=a.after_id, layout=a.layout, title=a.title, subtitle=a.subtitle, blocks=a.blocks, notes=a.notes,
                          image_prompt=a.image_prompt, sources=a.sources)


def run_slide_delete(svc: Services, a: SlideDeleteArgs) -> dict:
    if not a.confirm:
        raise CiceroError("Deleting a slide needs confirm=true; its revisions are deleted with it.", code="confirm_required")
    return store.delete_slide(svc, a.deck_id, a.slide_id)


def run_slides_reorder(svc: Services, a: ReorderArgs) -> dict:
    return store.reorder_slides(svc, a.deck_id, a.order)


def run_deck_check(svc: Services, a: DeckIdArgs) -> dict:
    issues = svc.check(a.deck_id)["issues"]
    return {"issues": issues, "warnings": sum(1 for i in issues if i["severity"] == "warning"), "infos": sum(1 for i in issues if i["severity"] == "info")}


def run_deck_theme(svc: Services, a: ThemeArgs) -> dict:
    if a.theme is None:
        current = store.deck_view(svc, a.deck_id)["theme"] if a.deck_id else None
        return {"current": current, "themes": svc.themes()}
    if not a.deck_id:
        raise CiceroError("Pass deck_id to set a theme.")
    store.update_deck(svc, a.deck_id, {"theme": a.theme})  # validates the id, built-in or made from a design system
    return {"current": a.theme, "themes": [{"id": t["id"], "name": t["name"]} for t in svc.themes()]}


def run_theme_from_tokens(svc: Services, a: ThemeFromTokensArgs) -> dict:
    if not a.tokens_id:
        return {"ok": True, "design_systems": [{"id": d["id"], "name": d["name"]} for d in svc.design_systems()],
                "hint": "Call again with tokens_id (and mode light or dark) to turn one into a theme."}
    made = svc.theme_from_tokens(a.tokens_id, a.mode)
    out = {"ok": True, "theme_id": made["theme"]["id"], "theme": {k: made["theme"][k] for k in ("id", "name", "colors", "fonts", "radius")}, "created": made["created"],
           "warnings": made["warnings"], "contrast_issues": made["contrast_issues"]}
    if a.deck_id:
        store.update_deck(svc, a.deck_id, {"theme": made["theme"]["id"]})
        out["applied_to"] = a.deck_id
    return out


def run_deck_export(svc: Services, a: ExportArgs) -> dict:
    export = svc.export(a.deck_id, a.format)
    path, _ = store.export_file(svc, export["id"])
    base = svc.base_url()
    return {"export": export, "path": str(path.resolve()), "download_url": f"{base}{export['url']}"}


def run_slide_image(svc: Services, a: SlideImageArgs) -> dict:
    return images_mod.generate_for_slide(svc, a.deck_id, a.slide_id, a.prompt)


TOOLS: list[Tool] = [
    Tool("cicero_status",
         "Health and counts: decks, sources, slides, exports; model and PDF availability. Estado de Cicero.\n"
         "Sinónimos: estado, salud, ¿funciona?, modelo disponible.\nKeywords: status, health, counts.",
         Empty, _ann(True), run_status),
    Tool("deck_list",
         "List presentations with status, slides approved/total and last update. Listar presentaciones.\n"
         "Sinónimos: presentaciones, diapositivas, mis decks, buscar presentación.\nKeywords: decks, list, presentations.",
         Empty, _ann(True), run_deck_list),
    Tool("deck_create",
         "Create a presentation: title, brief, audience, tone, language (es/en), slide count, theme. Crear presentación.\n"
         "Sinónimos: nueva presentación, encargo, charla, guion, pase de diapositivas.\nKeywords: new deck, brief, audience, slides.",
         DeckCreate, _ann(False, False, False), run_deck_create),
    Tool("deck_get",
         "One presentation with sources, outline and slides (summary or full). Ver presentación.\n"
         "Sinónimos: abrir presentación, estado, qué diapositivas hay, esquema.\nKeywords: deck, outline, slides, status.",
         DeckGetArgs, _ann(True), run_deck_get),
    Tool("deck_update",
         "Edit the brief, audience, tone, language, slide count, title or theme of a presentation. Editar presentación.\n"
         "Sinónimos: cambiar encargo, público, tono, idioma, número de diapositivas.\nKeywords: update deck, brief, tone.",
         DeckUpdateArgs, _ann(False, False, True), run_deck_update),
    Tool("deck_delete",
         "Delete a presentation with everything in it (needs confirm=true). Borrar presentación.\n"
         "Only when the user asks. Sinónimos: eliminar, quitar presentación.\nKeywords: delete deck, remove.",
         DeckDeleteArgs, _ann(False, True, True), run_deck_delete),
    Tool("source_add",
         "Add a source to a presentation: pasted text or a local txt/md/pdf/docx/pptx file. Añadir fuente.\n"
         "Figures on slides must come from sources. Sinónimos: documento, material, pegar texto, adjuntar.\nKeywords: source, document, text, file.",
         SourceAddArgs, _ann(False, False, False), run_source_add),
    Tool("source_list",
         "List the sources of a presentation (id, title, kind, size). Listar fuentes.\n"
         "Sinónimos: fuentes, documentos, material.\nKeywords: sources, list.",
         DeckIdArgs, _ann(True), run_source_list),
    Tool("source_get",
         "Read the text of one source, paged. Leer una fuente.\n"
         "Sinónimos: ver fuente, texto del documento, comprobar una cifra.\nKeywords: source text, read.",
         SourceGetArgs, _ann(True), run_source_get),
    Tool("source_remove",
         "Remove a source (needs confirm=true); slides that cite it lose the reference. Quitar fuente.\n"
         "Sinónimos: borrar fuente, eliminar documento.\nKeywords: remove source, delete.",
         SourceRemoveArgs, _ann(False, True, True), run_source_remove),
    Tool("outline_generate",
         "Generate the outline from the brief and sources; replaces the current one. Generar guion.\n"
         "Uses the local model, or fixed rules without one (generator=fallback). Sinónimos: esquema, índice, estructura, guion.\nKeywords: outline, structure.",
         DeckIdArgs, _ann(False, True, False), run_outline_generate),
    Tool("outline_update",
         "Replace the outline with your own items {title, purpose, points, layout_hint}. Editar guion.\n"
         "Sinónimos: reordenar guion, cambiar puntos, escribir el esquema.\nKeywords: outline, edit, items.",
         OutlineUpdateArgs, _ann(False, True, True), run_outline_update),
    Tool("slides_generate",
         "Generate one slide per outline item; approved slides are kept, drafts are rewritten. Generar diapositivas.\n"
         "Charts only from source numbers. Sinónimos: crear diapositivas, redactar slides, montar.\nKeywords: generate slides.",
         SlidesGenerateArgs, _ann(False, True, False), run_slides_generate),
    Tool("slide_get",
         "One slide in full: layout, title, blocks, notes, status, revision, sources. Ver diapositiva.\n"
         "Sinónimos: leer slide, contenido de la diapositiva.\nKeywords: slide, blocks, notes.",
         SlideRefArgs, _ann(True), run_slide_get),
    Tool("slide_update",
         "Edit a slide; makes a new revision and returns it to draft. Editar diapositiva.\n"
         "Blocks: bullets, text, quote, columns, chart, image. Sinónimos: cambiar texto, corregir, añadir notas.\nKeywords: edit slide, blocks.",
         SlideUpdateArgs, _ann(False, False, True), run_slide_update),
    Tool("slide_regenerate",
         "Rewrite one slide with the model from the person's feedback; needs a model. Regenerar diapositiva.\n"
         "Sinónimos: rehacer, reescribir con indicaciones, mejorar esta slide.\nKeywords: regenerate, feedback, rewrite.",
         SlideRegenerateArgs, _ann(False, False, False), run_slide_regenerate),
    Tool("slide_approve",
         "Approve a slide the person accepted (approved=false removes it). Aprobar diapositiva.\n"
         "The deck is ready when all slides are approved. Sinónimos: dar por buena, validar, revisar.\nKeywords: approve, review.",
         SlideApproveArgs, _ann(False, False, True), run_slide_approve),
    Tool("slide_revert",
         "List a slide's revisions, or restore one as a new revision. Revisiones y deshacer.\n"
         "Sinónimos: versiones, volver atrás, deshacer cambios, historial.\nKeywords: revisions, revert, undo, history.",
         SlideRevertArgs, _ann(False, False, False), run_slide_revert),
    Tool("slide_add",
         "Add a slide (blank or with content) after a given slide or at the end. Añadir diapositiva.\n"
         "Sinónimos: nueva slide, insertar diapositiva.\nKeywords: add slide, insert.",
         SlideAddArgs, _ann(False, False, False), run_slide_add),
    Tool("slide_delete",
         "Delete a slide and its revisions (needs confirm=true). Borrar diapositiva.\n"
         "Only when the user asks. Sinónimos: quitar slide, eliminar diapositiva.\nKeywords: delete slide, remove.",
         SlideDeleteArgs, _ann(False, True, True), run_slide_delete),
    Tool("slides_reorder",
         "Reorder the slides: pass every slide id in the new order. Reordenar diapositivas.\n"
         "Sinónimos: mover, cambiar el orden, subir, bajar.\nKeywords: reorder, move, order.",
         ReorderArgs, _ann(False, False, True), run_slides_reorder),
    Tool("deck_check",
         "Review the deck: overflow, numbers absent from sources, missing notes, unapproved. Revisar.\n"
         "Sinónimos: comprobar, validar, errores, qué falta, cifras sin fuente.\nKeywords: check, review, issues, overflow.",
         DeckIdArgs, _ann(True), run_deck_check),
    Tool("deck_theme",
         "List the themes, or set the theme of a presentation. Tema visual.\n"
         "Sinónimos: colores, tipografía, estilo, tema claro u oscuro.\nKeywords: theme, colours, fonts, style.",
         ThemeArgs, _ann(False, False, True), run_deck_theme),
    Tool("theme_from_tokens",
         "Make a theme from a design system (colours, fonts, radius); no tokens_id lists them. Tema desde diseño.\n"
         "Colours are adjusted to read (contrast 4.5:1); a font that is not a Windows font is replaced. Sinónimos: usar mi marca, identidad visual, paleta corporativa, design system, tokens.\n"
         "Keywords: theme, design system, tokens, brand, palette, vitruvius.",
         ThemeFromTokensArgs, _ann(False, False, True, True), run_theme_from_tokens),
    Tool("deck_export",
         "Export to pptx (editable, native charts), pdf, html or md; returns the file path and download URL. Exportar.\n"
         "PDF needs Chromium. Sinónimos: descargar, guardar, generar archivo, pptx, PDF.\nKeywords: export, pptx, pdf, html, markdown.",
         ExportArgs, _ann(False, False, False), run_deck_export),
    Tool("slide_image",
         "Generate a picture for a slide with the family image studio (optional). Generar imagen.\n"
         "Fails with image_studio_unavailable when no studio runs. Sinónimos: ilustración, foto, imagen para la slide.\nKeywords: image, picture, studio.",
         SlideImageArgs, _ann(False, False, False, True), run_slide_image),
]

TOOLS_BY_NAME = {t.name: t for t in TOOLS}
RESULT_CAP = 20_000


def tool_catalog() -> list[dict]:
    return [
        {"name": t.name, "description": t.description, "annotations": t.annotations,
         "inputSchema": t.input_model.model_json_schema(by_alias=True)}
        for t in TOOLS
    ]


def cap_result(result: Any, limit: int = RESULT_CAP) -> Any:
    """Keep an agent-facing result under ~20 KB: halve the biggest list (or text) until it fits and say so."""
    if not isinstance(result, dict) or len(json.dumps(result, ensure_ascii=False)) <= limit:
        return result
    cut: list[str] = []
    for _ in range(40):
        size = len(json.dumps(result, ensure_ascii=False))
        if size <= limit:
            break
        best: tuple[int, Any, str] | None = None
        for key, value in result.items():
            if isinstance(value, list) and len(value) > 1:
                n = len(json.dumps(value, ensure_ascii=False))
                if best is None or n > best[0]:
                    best = (n, result, key)
        if best is None:
            text_key = max((k for k, v in result.items() if isinstance(v, str)), key=lambda k: len(result[k]), default=None)
            if text_key and len(result[text_key]) > 1000:
                result[text_key] = result[text_key][: len(result[text_key]) // 2] + "…"
                cut.append(text_key)
                continue
            break
        _, holder, key = best
        holder[key] = holder[key][: max(1, len(holder[key]) // 2)]
        cut.append(key)
    if cut:
        result["truncated"] = True
        result["truncated_fields"] = sorted(set(cut))
        result["hint"] = "The result was trimmed to fit ~20 KB: ask for detail=summary, or read one slide or source at a time."
    return result


def call_tool(svc: Services, name: str, arguments: dict | None, *, caller: str | None = None, cap: bool = False) -> Any:
    tool = TOOLS_BY_NAME.get(name)
    if tool is None:
        raise KeyError(f"Unknown tool: {name}")
    args = tool.input_model.model_validate(arguments or {})
    result = tool.run(svc, args)
    return cap_result(result) if cap else result
