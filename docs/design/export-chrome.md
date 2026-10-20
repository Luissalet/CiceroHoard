# Numbering and progress in Export

> Final status, 20 October 2026: independently approved through CAS4, integrated in Main at be7769bfe0750b17eba5ab2e692bb1804e3276c1 and final package installed. Earlier isolated/pending statements below are preserved historical checkpoints, superseded by the final closure at the end of this record.

## Direction contract

THESIS: Preserve the existing numbering/progress work while combining portable figures; no replacement visual world.

OWN-WORLD: Incumbent Cicero dark brown panels, salmon accent, native fields, flat secondary actions and inherited type.

STORY: Choose numbers, progress and main-slide count; save and export the same settings. Later slides remain an appendix.

FIRST VIEWPORT: A secondary panel between transitions and export actions, two desktop field columns and one mobile column; Save and Reset directly below.

FORM: Incumbent Operate extension; no concept tournament or approved comp. Preserve existing fields, bilingual labels and layout.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance

Combined task 1021 source remains in an isolated worktree. Formal combined review,
integration and installation remain pending. PRODUCT.md and DESIGN.md are absent
from this worktree. The incumbent implementation and docs/design/figures.md
provide the available visual evidence; this record introduces no new identity.

## Overview

**Creative North Star: "Existing Cicero slide workbench"**

This surface record applies Impeccable document to the incumbent Operate panel in `client/src/pages/deck/ChromeEditor.jsx`, its placement in `client/src/pages/deck/Export.jsx` and the shared settings in `cicero_hoard/chrome.py`. It captures existing behaviour and visual relationships within the isolated combination; it establishes no replacement world. The direction contract above is retained as local history. Its reference to a DESIGN.md deliverable does not establish an existing root file or require creating one for this scoped record.

The combination preserves the earlier WIP that Luis authorised keeping alongside figures. Formal combined review, integration and installation remain pending; the evidence below does not establish every retained WIP feature as newly verified. The companion `.impeccable/surfaces/export-chrome.json` is surface-scoped. No root PRODUCT.md, DESIGN.md or design sidecar is created.

**Key Characteristics:**

- Numbering, progress and appendix settings share one compact panel.
- The panel stays between transitions and export actions.
- Two desktop field columns become one on mobile; appendix guidance and Save/Reset follow the fields.
- Settings use the existing bilingual labels, native selects, number inputs, checkboxes and secondary buttons.
- Figure import/source controls remain in the image editor with their ordinary caption and crop controls.

## Colors

### Primary

The inherited muted salmon accent marks established actions and focus. Save and Reset retain the secondary action treatment; this panel introduces no competing accent.

### Neutral

Dark warm panels, pale text and muted labels/helper text preserve the Cicero shell. The actual cascade is authoritative: unlayered `index.css` gives secondary buttons a transparent resting background and fields the Hoard surface. The existing figure brief's earlier token extraction remains historical; it is not a new root theme.

## Typography

Body copy inherits the Hoard sans stack beginning with Source Sans 3 and system fallbacks. Section headings use the existing compact semibold heading; field labels and appendix guidance use the incumbent smaller text. The bilingual copy describes the same operations. The author browser receipt records `loaded: []` in every desktop/mobile view, so no loaded-webfont claim follows from the CSS stack.

## Layout

The Export content retains its existing bounded vertical flow: transitions, numbering/progress, export actions, motion and previous exports. The numbering/progress field grid has an 8px gap and two columns at the incumbent small breakpoint, collapsing to one below it. Supplied captures cover desktop (1440px) and mobile (390px). Position and thickness occupy the same grid only when progress is enabled. The appendix explanation follows the grid; the Save button and icon-only Reset sit together immediately after that help text. No modal, overlay or additional navigation is introduced by these controls.

## Elevation & Depth

The panel remains flat with a thin inherited border and tonal separation. There is no panel-specific shadow. Secondary button hover uses the existing raised neutral surface and border; background/border transitions retain 0.16s. The source implements inherited focus and busy/disabled treatments; the supplied finish does not certify those unseen states.

## Shapes

Panels retain the Hoard large radius (10px); fields and buttons use its standard radius (8px) through the unlayered overrides. Native selects and checkboxes remain native controls. The Reset action keeps its compact square silhouette and refresh-arrow icon rather than adding a second text-heavy action.

## Components

### Numbering and progress fields

`number` offers `auto`, `n_total`, `n` and `none`. Automatic mode keeps the theme footer or template's two-digit numbering. `progress` offers `none`, `bar` and `segments`; selecting a visible indicator exposes `position` (`bottom`/`top`) and `thickness` (2–20 slide pixels, scaled from a 1280px slide reference). Defaults are automatic numbering, no progress, bottom position and thickness 6.

`main_slides` is optional: empty includes all slides; a count limits the main total. Following slides are appendix material, excluded from that total and from progress. Numbered appendix slides retain their own number without a misleading main-total denominator. The API rejects a main count exceeding the deck's slide count. The help text explains the appendix behaviour beside this setting flow.

`show_title` controls the deck title in the built-in footer and defaults to true. `on_cover` also permits numbering on title, section and closing layouts and defaults to false. These settings reuse the shared native representation; they do not alter the imported figure source.

### Save and Reset

Save persists the draft with `api.chromeSet`, updates the returned resolved settings and reloads the deck. Reset calls `api.chromeReset`, clears the stored custom settings and resolves the defaults before reloading. Both use the incumbent operation flow; controls are disabled while it is busy. Reset is icon-only with a translated accessible name and title. Reading settings can show an inherited `role=alert` error. These are source-observed behaviours; browser receipts demonstrate saving/reopening selected settings rather than every possible state.

**The Appendix Count Rule.** Keep the main total and progress bounded by the main-slide count while appendix slides remain available.

### Figure coexistence

`BlockEditor.jsx` retains figure title/revision, document/page and origin/download actions below the upload selector, followed by caption, fit and crop focus. Download preserves the imported revision/native source, independently of opening the origin. Ordinary images retain their original flow and omit the source group. Replacement updates only the asset on the current block, preserving its other fields. Full details and the earlier receipts remain in `docs/design/figures.md`.

### Evidence and limits — combined checkpoint, 20 October 2026

The five-section finish at `D:/LocalAI/research-inbox/expansiones-fusiones-20261020/qa1021-combined/FINISH.txt` records `disposition: ship` for the visible finish/coherence of the two combined extensions, with no material visual fixes. It reports inspecting all eight final captures in that directory: figures-desktop.png, figures-desktop-controls.png, figures-mobile.png, figures-mobile-controls.png, chrome-desktop.png, chrome-desktop-controls.png, chrome-mobile.png and chrome-mobile-controls.png. Full captures show the real UI sequence; detail captures temporarily hide sticky/Faustus overlays only for the capture. This documentation pass read that review and the source/receipts; it did not independently rerun visual or functional QA.

`D:/LocalAI/research-inbox/expansiones-fusiones-20261020/qa1021-combined/browser-results.json` is an author receipt: figures/chrome reopen, retained-source download is exact, manual notes/crop/text remain, all four desktop/mobile views have no overflow, and JS/HTTP error arrays are empty. Its loaded-font arrays are empty. Focus, hover, error, empty, loading and all translation states remain outside the supplied finish certification.

`D:/LocalAI/research-inbox/expansiones-fusiones-20261020/qa1021-combined/native-results.json` is also an author receipt: 69 MCP tools, immutable figure source/deduplication, selective undo preserving manual edits, numbering/appendix exports, template snapshot after moving the template, 90-second rehearsal reserve and zero model calls. It records actual PPTX (44,136 bytes), HTML (198,592 bytes) and PDF (32,526 bytes) outputs. These scoped receipts establish neither independent functional review nor LLM-generated-content quality.

The author suite at `D:/LocalAI/research-inbox/expansiones-fusiones-20261020/cicero1021-combined-suite-r1.log` reports 493 passed/8 skipped; `D:/LocalAI/research-inbox/expansiones-fusiones-20261020/cicero1021-combined-build-r1.log` records a successful build. The supplied detector at `D:/LocalAI/research-inbox/expansiones-fusiones-20261020/cicero1021-combined-detector.json` returns `[]`. This documenter ran no context loader, detector, browser, server, functional tests, model calls or further polish. Combined review, integration and installation are still pending; this is no claim about Main or whole-app capability.

## Do's and Don'ts

### Do:

- **Do** retain the panel between transitions and export actions.
- **Do** keep appendix guidance and Save/Reset directly after the settings.
- **Do** preserve the two-column desktop and one-column mobile field flow.
- **Do** keep figure source and image controls together in their existing editor flow.

### Don't:

- **Don't** count appendix slides in the main total or progress.
- **Don't** treat imported source as live synchronization with its origin.
- **Don't** turn author receipts into independent functional, font-loading, installed or LLM-quality certification.

## Final closure — 20 October 2026

The reviewed combination is integrated in Main at `be7769bfe0750b17eba5ab2e692bb1804e3276c1` and its final package is installed. The incumbent UI/code for figures and ChromeEditor retains the relationships shown by the earlier eight captures and scoped SHIP finish; this closure adds no visual changes or polish. Earlier isolated/pending checkpoints remain as history, not the current release state. PRODUCT.md and DESIGN.md remain absent; the incumbent implementation and surface briefs retain authority.

Independent review is recorded in `D:/LocalAI/research-inbox/expansiones-fusiones-20261020/review-r1021/REPORT-R2.txt`, `D:/LocalAI/research-inbox/expansiones-fusiones-20261020/review-r1021/REPORT-R3.txt` and `D:/LocalAI/research-inbox/expansiones-fusiones-20261020/review-r1021/REPORT-R4.txt`, each APPROVE for its pinned submission. CAS2 reviewed the combined `3d62b578792c690d754f07b35432b2f6cabc4192` source with 105 area tests, independent native/API/MCP/browser and export checks, plus a real synthetic data-directory move recovering the template snapshot. CAS3 reviewed the package-only `881fd9ee00e8440c64d2f4ff74baa4bf57c61695` delta with a fresh independent installed wheel. CAS4 reviewed the final one-line package-data change at the Main hash above, rebuilding independently and verifying all 189 tracked package paths with no bytecode/cache extras. CAS4 did not repeat the CAS2 functional/visual matrix; those earlier receipts and their limits remain distinct.

Integration preservation is recorded in `D:/LocalAI/research-inbox/expansiones-fusiones-20261020/cicero1021-combined-integration.json`: all 36 original WIP paths were checked before integration, and the recoverable stash `ebd688ae7d966d4f8691b672041f34ab4996321f` is retained. The definitive author wheel in `D:/LocalAI/research-inbox/expansiones-fusiones-20261020/cicero1021-combined-wheels-r5/` has SHA256 `2543583a91574fbd03522f37485fbdbc6785216f34aceabd561cafb3b97549ef`. `D:/LocalAI/research-inbox/expansiones-fusiones-20261020/cicero1021-wheel-preflight-r5.json` records all 189 Git package paths complete/equal, with text EOL normalization only and zero generated bytecode. `D:/LocalAI/research-inbox/expansiones-fusiones-20261020/cicero1021-installed-final-exact.json` records 189 installed members raw-exact to that wheel and 162 Python sources equal to Git after LF normalization. Final before/after distribution and dependency versions are unchanged; pip check reports no broken requirements.

The final installed-package functional receipts remain attributed to the author: `D:/LocalAI/research-inbox/expansiones-fusiones-20261020/qa1021-installed-final/native-results.json` and `D:/LocalAI/research-inbox/expansiones-fusiones-20261020/qa1021-installed-final/browser-results.json`, with logs `D:/LocalAI/research-inbox/expansiones-fusiones-20261020/cicero1021-installed-final-native.log` and `D:/LocalAI/research-inbox/expansiones-fusiones-20261020/cicero1021-installed-final-browser.log`. The root reports these PASS runs used the installed package with isolated `-I` interpreters: 69 MCP tools, exact figure PNG/source, deduplication/selective undo, Chrome/appendix, PPTX/HTML/PDF exports, retained template after moving it, a 90-second rehearsal reserve, and save/reopen/download in desktop 1440px and mobile 390px UI without overflow or JS/HTTP errors. Export sizes remain PPTX 44,136 bytes, HTML 198,592 bytes and PDF 32,526 bytes. The native log retains a Pydantic unresolved-forward-reference warning; it does not turn the recorded PASS into model-quality evidence. These final author runs complement, rather than replace, the separately identified independent reviews.

Failed intermediate steps remain failed historical evidence. The R2 wheel omitted `family-services.json`. The first distribution-inventory comparison failed because `cicero-hoard` 0.1.0 had been newly registered, while existing dependencies/versions were unchanged (`D:/LocalAI/research-inbox/expansiones-fusiones-20261020/cicero1021-installed-first-check.txt`). The R3 build reused historical build/cache content and exposed the rejected 42-tool catalogue. R4 included four `.pyc` caches which pip recompiles, so raw installed-member comparison failed. R5 used a fresh build and the narrowed vendor resource glob to remove those caches, then passed the unchanged strict comparison. No failed R2/R3/R4 artifact is relabelled PASS and no checker was relaxed to accept the definitive wheel.

The root reports its private QA ports 54566/54567/54576/54578/54579 stopped; default port 5194 has no listener and was not started. Installed does not mean the user's default application was launched. `D:/LocalAI/research-inbox/expansiones-fusiones-20261020/manual-cicero1021-proof.json` records functional-manual updates to paragraphs 87/99, with all other 188 paragraphs' text/styles/links exact; the catalogue count moves from 67 to 69. The manual does not claim aesthetic or generated-content quality. Final loaded-font arrays remain empty and model calls remain zero. Webfont loading, LLM quality, unseen UI states and measured oral rehearsal remain uncertified. This documentation closure performed no context loader, detector, browser, app/server, tests, model calls or new visual round.
