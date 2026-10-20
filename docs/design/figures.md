---
name: "Cicero image-block figures"
description: "Scoped record of portable Vitruvius figures in the incumbent slide image editor"
colors:
  primary: "#d98f86"
  primary-hover: "#e3aca5"
  primary-ink: "#1a1414"
  neutral-bg: "#1c1515"
  neutral-field: "#161110"
  neutral-surface: "#241d1c"
  neutral-elevated: "#2f2625"
  neutral-border: "#423736"
  neutral-text: "#ece3e1"
  neutral-muted: "#beb5b4"
typography:
  body:
    fontFamily: "Source Sans 3, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Noto Sans, Liberation Sans, Arial, sans-serif"
    fontSize: "14px"
    lineHeight: 1.5
  control:
    fontSize: "13px"
    fontWeight: 600
    lineHeight: "18px"
  small-control:
    fontSize: "12px"
    fontWeight: 600
    lineHeight: "18px"
  label:
    fontSize: "12px"
    fontWeight: 600
rounded:
  button: "7px"
  field: "6px"
  block: "8px"
spacing:
  field: "6px 9px"
  button: "6px 13px"
  small-button: "2px 9px"
  block: "10px"
  actions: "8px"
components:
  button-secondary:
    backgroundColor: "{colors.neutral-elevated}"
    textColor: "{colors.neutral-text}"
    rounded: "{rounded.button}"
    padding: "{spacing.small-button}"
  field:
    backgroundColor: "{colors.neutral-field}"
    textColor: "{colors.neutral-text}"
    rounded: "{rounded.field}"
    padding: "{spacing.field}"
  block:
    backgroundColor: "{colors.neutral-elevated}"
    rounded: "{rounded.block}"
    padding: "{spacing.block}"
---

# Image-block figures surface record

## Overview

**Creative North Star: "Existing Cicero slide workbench"**

This Operate extension imports a portable Vitruvius figure through the existing image upload control and keeps its native source beside the image asset. The slide, caption, crop and other editing controls remain part of the incumbent slide editor. Warm dark surfaces, muted coral actions, serif headings and sans controls are observed implementation facts; no replacement identity is introduced.

This brief covers `client/src/pages/deck/BlockEditor.jsx`, its API/i18n support and native figure storage. The companion `.impeccable/surfaces/figures.json` is surface-scoped. Root PRODUCT.md and DESIGN.md are absent at this checkpoint, but Cicero is an existing product with an established implementation. This record neither creates a root design system nor asserts automatic discovery by the context loader. The figures extension remains in an isolated worktree, unintegrated and uninstalled.

**Key Characteristics:**
- The existing image selector accepts PNG, JPEG, WebP and portable `.vfigure` files.
- Title, revision, document ID and optional page ID form one source group below the selector.
- Origin and source-download actions sit together using existing small buttons.
- Replacement changes the image asset while retaining the current block's caption, crop, position and other properties.
- Imported source is a frozen revision; opening the origin does not synchronize it automatically.

## Colors

### Primary

Muted coral is the inherited selection, action and focus accent. Its lighter sibling belongs to existing primary-action hover. The two figure-source actions use the secondary button treatment instead of creating another accent hierarchy.

### Neutral

Warm charcoal grounds distinguish the page, panels, raised image blocks and sunken fields. Pale text carries the title and revision; muted helper text carries document/page identity and upload guidance. The white figure and slide are authored content rather than shell color tokens.

**The Content Ground Rule.** Preserve the figure's authored preview independently of the surrounding Cicero theme.

## Typography

The loaded Hoard stylesheet assigns the body its Source Sans 3 and system fallback stack, superseding the layered Segoe UI declaration in `index.css`. Body and source-title copy use the body size; upload guidance, identifiers and small actions use the existing compact label/control sizes. The source group wraps words and its action row wraps buttons. The incumbent serif heading relationship remains unchanged.

`browser-results.json` records this body CSS stack and `document.fonts: []` for both apps at desktop/mobile sizes. Neither the declaration nor these captures proves Source Sans 3 or Cinzel was loaded. No webfont-loading claim is made.

## Layout

At the observed desktop width (1440px), the existing slide layout places thumbnails, slide preview and a 400px editor column beside one another. Its source CSS changes to two columns from 1024px and a sequential single column below that. On the observed mobile width (390px), the image block is in the normal vertical editing flow below the slide preview; no new overlay or floating source panel is added.

Within each image block, the preview precedes the upload/replace selector and accepted-format guidance. Provenance follows those controls and precedes the caption and fit fields. Title/revision and muted document/page identity are separate lines; the two source actions wrap together with an 8px gap. The supplied R2 detail captures show readable provenance and both actions at desktop/mobile sizes. Long full-page mobile captures establish sequence; their scaled display alone is not used to judge text size.

## Elevation & Depth

The extension uses the existing flat raised block surface, thin border and tonal fields. No new shadow or material treatment is added. Existing buttons transition background/border over 0.16s; the source group adds no motion.

## Shapes

Image blocks retain their existing rounded bordered container; fields and small buttons use the incumbent radii. The preview keeps its image border and rounded corners. Document geometry and the synthetic PNG's shapes are content and do not establish new shell primitives.

## Components

### Upload and replacement

Subir imagen / Cambiar imagen retains the existing labelled file input, busy upload flow and disabled behavior. Guidance explicitly adds Vitruvius `.vfigure` alongside ordinary images and the existing 15MB limit. The actual input also accepts `.json`; the native upload path recognizes either extension as a figure package. Invalid packages are rejected through the existing operation/error flow. Those errors and focus/hover appearance are not separately captured here.

The upload applies a returned `asset_id` to the latest block only if its request sequence and previous asset still match. It preserves current caption, fit, focus position, frame, identity and other block fields. Source reads discard stale responses after the asset changes or the component unmounts. This describes implemented behavior rather than a blanket race-freedom or accessibility certification.

### Figure source group

The labelled source group shows title (or document ID when untitled), Revisión/Revision, Documento de Vitruvius/Vitruvius document and optional page ID. Abrir en Vitruvius / Open in Vitruvius appears when an origin editor URL exists and opens separately. Descargar figura y fuente / Download figure and source downloads the retained package. The download is available without contacting the originating Hoard.

Source lookup uses `GET /api/assets/{asset_id}/source`; download adds `?download=true`. Ordinary images have no figure metadata, so they omit the group. A lookup error uses the inherited helper text with `role=status` rather than an empty source panel.

**The Frozen Source Rule.** Download the imported revision and native source attached to that asset; an origin link does not imply live synchronization.

### Native package and image controls

`vitruvius.figure/1` carries document ID, revision, title, optional selected page, full native content, origin links and a PNG preview. Cicero stores the preview through the existing asset store and retains the native metadata with it. Selecting one editorial page for the preview does not reduce the retained native document to that page. Different retained revisions may have identical preview pixels and remain distinct source assets. Caption and contain/cover with horizontal/vertical crop focus stay in their ordinary locations beneath provenance.

### Evidence and limits

The paragraphs below retain the earlier figures-only checkpoint and its original receipts. The combined checkpoint that follows records the later isolated combination without replacing that history.

Evidence directory: `D:/LocalAI/research-inbox/expansiones-fusiones-20261020/qa1021/`. This documenter inspected current component/API/i18n/styles and native figure code, read `browser-results.json`, `native-results.json`, `FINISH.txt` and both detector receipts, and opened all eleven required captures: Vitruvius/Cicero desktop/mobile full-r2 and viewport-r2, Cicero desktop/mobile source-r2 and Vitruvius mobile-export-controls. The obstructed R1 `cicero-mobile-figure-controls.png` is excluded.

The five-section finish review records `disposition: ship` for the added controls and provenance within the incumbent Operate extension, with no remaining material fixes. Its missing formal direction/quality contract and approved comp are disclosed; no new identity is inferred. It does not certify a whole-surface redesign, unseen states, actual font loading or installed activation.

Author browser receipts record save/reopen, retained source on download, replacement retaining caption/notes/crop/other blocks, dirty export saving, no horizontal overflow at desktop/mobile, and no JavaScript or HTTP errors. Author native receipts record Vitruvius 118/Cicero 68 tool catalogs, exact API/MCP source, retained revisions 1/2 with identical preview but distinct source, targeted replacement, selective undo preserving manual edits and real PPTX (39,205 bytes), PDF (33,681 bytes) and HTML (204,816 bytes) exports. This documentation pass did not independently execute those operations.

The supplied single detector run returns `[]` for Cicero. Vitruvius reports three pre-existing document-color advisories, not new figure-control styles. No detector, browser/server, model, GPU or functional test was rerun by this documenter. No real profiles or model-generated content quality were tested. Native synthetic diagram data and its PNG are QA content, not stock imagery, AI illustration or a new decorative asset. Code is not yet integrated or installed.

### Combined checkpoint — 20 October 2026

The isolated `D:/LocalAI/worktrees/cicero-combined1021` combination retains the pre-existing WIP that Luis authorised preserving. The effective visual authority remains the incumbent code and this figures brief; PRODUCT.md and DESIGN.md do not exist here. The companion `docs/design/export-chrome.md` and `.impeccable/surfaces/export-chrome.json` record the existing numbering/progress panel within Export. Formal combined review, integration and installation remain pending. The combination is not evidence that every retained WIP feature has newly passed validation.

Current source inspection of `client/src/pages/deck/BlockEditor.jsx` confirms the same imported revision, origin/download grouping, asset-only replacement and ordinary-image flow. Figures keep their source beside the preview; an ordinary image omits the provenance group and keeps the same caption, contain/cover and crop-focus controls. The source is frozen at import and downloadable independently of the originating editor. `ChromeEditor.jsx` and `Export.jsx` place numbering/progress between transitions and export actions, using two field columns on desktop and one on mobile, followed by appendix guidance and Save/Reset. The two extensions preserve the incumbent Operate hierarchy together.

The earlier frontmatter and examples above are preserved as historical extraction. In the combined source, the unlayered rules at the end of `client/src/index.css` override the layered defaults: secondary buttons are transparent at rest, fields use the Hoard surface, and both use the Hoard standard radius (8px); panels use its large radius (10px). This clarification describes the existing cascade and does not change the interface or introduce tokens.

The five-section finish at `D:/LocalAI/research-inbox/expansiones-fusiones-20261020/qa1021-combined/FINISH.txt` records `disposition: ship`, limited to the visible finish/coherence of the combined figure-source and ChromeEditor controls, with no material visual fixes. Its reviewer inspected eight final captures: figures-desktop.png, figures-desktop-controls.png, figures-mobile.png, figures-mobile-controls.png, chrome-desktop.png, chrome-desktop-controls.png, chrome-mobile.png and chrome-mobile-controls.png, all within that directory. Full captures show the real UI sequence. Detail captures hide sticky/Faustus overlays only while capturing the controls; the product retains those overlays. This documentation pass read the supplied review and receipts without independently opening a browser or repeating visual QA.

Author receipts at `D:/LocalAI/research-inbox/expansiones-fusiones-20261020/qa1021-combined/browser-results.json` report figure/chrome reopening, exact retained-source download, manual notes/crop/text preservation, no overflow in all four desktop/mobile views and no JS/HTTP errors. All four `loaded` font arrays are empty; the declared CSS stack does not prove Source Sans 3 or Cinzel loaded. `D:/LocalAI/research-inbox/expansiones-fusiones-20261020/qa1021-combined/native-results.json` reports 69 MCP tools, immutable source/deduplication, selective undo, numbering/appendix exports, a template snapshot after moving the template, a 90-second rehearsal reserve, zero model calls, and PPTX (44,136 bytes), HTML (198,592 bytes) and PDF (32,526 bytes) outputs. These are author functional receipts, not independent review, installed capability or LLM-quality evidence.

The author suite receipt `D:/LocalAI/research-inbox/expansiones-fusiones-20261020/cicero1021-combined-suite-r1.log` reports 493 passed and 8 skipped. The build receipt `D:/LocalAI/research-inbox/expansiones-fusiones-20261020/cicero1021-combined-build-r1.log` records a successful build. The supplied `D:/LocalAI/research-inbox/expansiones-fusiones-20261020/cicero1021-combined-detector.json` is `[]`. This documenter ran no context loader, detector, browser, server, functional tests, model calls or new polish round. No whole-app, unseen-state, font-loading, integration or installation certification follows from this checkpoint.

## Do's and Don'ts

### Do:
- **Do** extend the ordinary image selector and retain caption and crop controls in their existing flow.
- **Do** keep source identity, revision and the two related actions grouped and readable on narrow screens.
- **Do** preserve the full imported native source independently of its preview pixels.
- **Do** retain current block properties when an uploaded figure replaces its asset.

### Don't:
- **Don't** treat opening the origin as live synchronization or rewriting the imported revision.
- **Don't** promote authored figure colors or synthetic QA geometry into shell tokens.
- **Don't** infer loaded webfonts, unseen-state certification or installed activation from this scoped review.
