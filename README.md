<img src="app-icon.png" width="96" alt="">

# Cicero's Hoard

A local workspace that turns a brief and source documents into an editable presentation, for a person and an assistant working together. [Español](README.es.md)

## What it is

You give Cicero an objective, an audience and the material. It proposes an outline, writes the slides with speaker notes, lets you review and approve each slide one by one, applies a theme and exports the result. Everything is available as a REST API for the bundled interface and as MCP tools built from the same code, so the two cannot disagree.

Sources are read on your computer; only short numbered excerpts go to the model, through Hoard Link, to whatever backend you configured (a local one by default). With no model reachable, the outline and slides are built from the sources by fixed rules and the result says `"generator": "fallback"`.

## What it does

### Decks, sources and slides
- Decks with title, brief, audience, tone, language (Spanish or English), 3 to 40 slides and a theme. The status is derived: draft, outline, review or ready (every slide approved).
- Sources: pasted text or `.txt`, `.md`, `.pdf`, `.docx` and `.pptx` files; scanned PDFs are read by the family document service when it runs. Sources are numbered and slides cite them.
- Outline generated from the brief and source excerpts, or written by hand.
- Fifteen layouts (including evidence, comparison and freeform composition) built from text, image, chart, diagram, metric, table and timeline blocks; every slide has speaker notes.
- Per-slide review: approve, regenerate with feedback, edit by hand. Every change is a revision; reverting restores an old revision as a new one. Regenerating keeps approved slides and rewrites drafts.
- Duplicate a slide, edit one title, note or bullet without rebuilding the rest, add draft slides in idempotent batches, and swap an existing figure.
- Import a `.pptx` into an editable deck (text, tables, charts with data, pictures, notes) with a Cicero layout and theme.
- Titles that state the conclusion: label titles are flagged and a conclusion is proposed from the slide's own content, applied per slide or per deck and undoable back to the labels.

### Checks and trust
- No invented numbers: the model may only use figures from the sources, a chart is kept only if all its values appear in them, and `deck_check` lists every figure that no source contains (comparing notations such as `1.234` and `1,5`).
- Automatic text fitting in preview, HTML and PPTX from one geometry; text that cannot fit is reported rather than clipped.
- Visual review: renders every slide in the browser and measures off-slide objects, overflowing text, overlaps, contrast, missing images and missing titles, with an automatic minimum-font fix.
- Design review through Vitruvius's Hoard: scores the generated look 0-100 and places each finding on its slide.
- Per-slide source checking, plus a benchmark that compares complete PPTX workflows with a common rasteriser and a fixed rubric.

### Themes and templates
- Seven built-in themes with at least 4.5:1 contrast, custom themes from a design system or from one of Vitruvius's presets (light or dark, with a "pick three for this brief" suggestion), and deletion of saved themes.
- Your own PPTX templates: masters, layouts, backgrounds, logos and fonts are kept, with layout-to-slide bindings for unusual templates.
- Slide numbering and a progress bar (top or bottom), with an appendix excluded from the total.

### Visuals, motion and media
- Typed visuals: 14 chart types, diagrams, metrics and tables with versioned schemas; replace one block while keeping the others; compare three compositions.
- Click stages, native PPTX animations and transitions, interactive routes between slides, audio and video blocks, and offline import of 3D scene models.
- Local VectorCraft and DesignCraft integration for editable vector figures and A4 handouts, and editable-source figures from Vitruvius.
- Images: upload your own or ask Prospero's Hoard for one per slide.

### Data and live presentation
- Import CSV, TSV and XLSX as immutable datasets, filter, group and sort them reproducibly, map them to charts and tables, and link them to local or URL sources that refresh as snapshots.
- Live presentation with separate presenter and audience URLs, stages, blackout, timer, audience polls and shared editing presence; the audience view never shows speaker notes.
- Timed rehearsal planning from the speaker notes, and measured rehearsals from the presenter console compared with the plan.

### Exports
- PPTX with real text boxes, speaker notes and native editable charts (16:9 or the template's size).
- PDF, one page per slide, rendered by a local Chromium.
- One self-contained HTML file with arrow-key navigation (no speaker notes).
- Markdown, with slides separated by `---`.

## Responsible use

- **Figures.** A generated deck is a draft. The number check finds figures that are not in the sources; it cannot tell whether a source is right. Read the notes and the figures before presenting.
- **Sources stay local.** Documents are read on this computer. Only short numbered excerpts are sent to the model, through Hoard Link.
- **Local files.** Adding a file by path only accepts document types (`.txt`, `.md`, `.pdf`, `.docx`, `.pptx`) and can be limited to folders with `CICERO_FILE_ROOTS`.
- **Quotes.** A quote block should reproduce a quote that appears in a source. The check does not verify quotations.
- **Deletes** (a deck, a slide, a source) need an explicit confirmation, also over MCP.

## How to run it

Requires Python 3.11+ and Node.js 22+ only to rebuild the client.

```bash
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
python -m playwright install chromium     # only for the PDF export
python -m cicero_hoard            # http://127.0.0.1:5194
```

The built client is committed under `cicero_hoard/static`; `npm install` and `npm run build` are only needed to change the UI. `python scripts/dev.py` starts the API and Vite together; `python scripts/launch.py` starts the app and opens the browser.

| Variable | Default | Meaning |
| --- | --- | --- |
| `CICERO_PORT` / `PORT` | `5194` | Port; with `PORT_STRICT=1` the app fails instead of moving |
| `CICERO_DATA_DIR` | `./data` | Database, `assets/`, `exports/`, `mcp-token`, `url`, `backend.json` |
| `CICERO_ALLOWED_HOSTS` | local only | Extra host names the server accepts |
| `CICERO_FILE_ROOTS` | empty | Folders local-file sources may come from |
| `CICERO_IMAGE_STUDIO_URL` | discovered | Address of the image studio |
| `CICERO_IMAGE_TIMEOUT` | `600` | Seconds to wait for one image render |
| `CICERO_PARALLEL_SLIDES` | `3` | Slides written at the same time after the first one (1-8) |
| `CICERO_SLIDE_EFFORT` | `low` | Reasoning effort for each slide and rewrite (`off`, `low`, `medium`, `high`) |
| `CICERO_VECTORCRAFT_CLI`, `CICERO_DESIGNCRAFT_CLI` | unset | Paths of the optional vector and handout apps |

The model comes from Hoard Link (`data/backend.json` or the Hoard environment variables) and can also be chosen in Settings.

Limits: the PDF export needs Chromium (or a system Edge or Chrome); without it exporting `pdf` fails with `pdf_unavailable` and the other formats keep working. Template preview and HTML need a local office slide engine on Windows, or they report the same code. Fonts are the theme's; a machine without them substitutes another. Text fitting is an estimate from character widths. Scanned PDFs without OCR are refused. Speaker notes are never in the HTML export.

## Connection with Faustus and Hoard Hub

- `faustus-plugin.json` describes the plugin. `mcp_server.py` is the shared Hoard Link stdio bridge: it reads `data/mcp-token`, fetches the tool list from the running app, forwards each call and starts the app if it is not running (`CICERO_BRIDGE_AUTOSTART=0` turns that off). Register it with `CICERO_URL` (default `http://127.0.0.1:5194`) and `CICERO_TOKEN_FILE`.
- Accountable agent writes: every non-read tool needs a `reason` of 3 to 300 characters, each write is journalled in `data/agent_journal.jsonl`, a whole agent session can be previewed and undone, and tokens can be minted with `read_only`, `drafts` or `all` profiles.
- Decks are addressable as `hoard://cicero/deck/<id>`. Events for deck, outline, slides, export and theme creation go to the hub bus. Themes from a design system are linked to it. Images come from Prospero's Hoard when it runs; only loopback addresses are contacted.
- The Faustus button mounts the shared assistant panel; Cicero supplies its data-space identity and the current deck, slide and unsaved editor state.
- The app carries skills for connected agents (`presentation-from-brief`, `diagram-authoring`, `image-composition`, `deep-research`); the portable entry point is `agent-skill/SKILL.md`.

<details>
<summary>MCP tools by group</summary>

- Status and decks: `cicero_status`, `deck_list`, `deck_create`, `deck_get`, `deck_update`, `deck_delete`, `deck_import_pptx`.
- Sources and outline: `source_add`, `source_list`, `source_get`, `source_remove`, `outline_generate`, `outline_update`.
- Slides: `slides_generate`, `slide_get`, `slide_add`, `slides_add`, `slide_update`, `slide_edit_text`, `slide_set_image`, `slide_image`, `slide_regenerate`, `slide_approve`, `slide_revert`, `slide_delete`, `slides_reorder`, `asset_import`, `figure_get`.
- Review and design: `deck_check`, `deck_visual_review`, `deck_design`, `deck_design_audit`, `deck_visual_lab`, `deck_benchmark`, `titles_overview`, `titles_propose`, `titles_apply`, `titles_restore`, `titles_mode`.
- Themes and templates: `deck_theme`, `theme_from_tokens`, `deck_theme_from_preset`, `theme_delete`, `template_inspect`, `deck_template`, `deck_chrome`.
- Visuals: `visual_catalog`, `slide_visual_update`, `slide_variants`, `deck_scene`, `deck_present`.
- Motion, navigation and media: `deck_animations`, `deck_transitions`, `deck_navigation`, `deck_media_control`, `media_import`, `media_get`, `scene_model_import`.
- Data: `dataset_import`, `dataset_get`, `dataset_transform`, `dataset_visual`, `dataset_link`, `dataset_links`, `dataset_link_control`, `dataset_bind`, `dataset_connect`.
- Live and collaboration: `deck_live_start`, `deck_live_state`, `deck_live_control`, `deck_poll`, `slide_collaborate`.
- Rehearsal and export: `deck_rehearsal`, `deck_rehearsal_runs`, `deck_export`, `deck_handout_designcraft`.
- Craft apps: `craft_discover`, `craft_call`, `vector_figure_create`.

</details>

## Project layout

| Path | Contents |
| --- | --- |
| `cicero_hoard/` | Python package: API, generation, checks, exports, live sessions, vendored Hoard Link |
| `client/` | React/Vite interface (built into `cicero_hoard/static`) |
| `mcp_server.py` | MCP stdio bridge |
| `faustus-plugin.json` | Faustus plugin manifest |
| `agent-skill/` | Portable agent skill |
| `docs/` | API and feature references ([API](docs/API.md), [agent visuals](docs/AGENT_VISUALS.md), [data and presentation](docs/DATA_PRESENTATION.md), [live media](docs/LIVE_MEDIA.md), [interactive navigation](docs/INTERACTIVE_NAVIGATION.md), [advanced authoring](docs/ADVANCED_AUTHORING.md)) |
| `scripts/` | `dev.py`, `launch.py`, visual gallery |
| `tests/` | Test suite |

## Development

```bash
pip install -r requirements.txt
python -m pytest -q      # no network: the model and the image studio are faked
```

The PDF tests run only when a Chromium is available. Licence: see `LICENSE`.
