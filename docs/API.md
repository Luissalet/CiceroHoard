# HTTP API

Base URL `http://127.0.0.1:5194`. The server accepts local requests only (see the guard below). Bodies and answers
are JSON unless stated. Ids of decks, slides, outline items, assets and exports are 12-character hex strings; source
ids are integers (per installation). Slide positions are 1-based.

Errors are `{"error": "message"}` with, when there is one, `"code": "..."`:

| status | meaning |
| --- | --- |
| 400 | invalid input or a rule of the domain (also validation errors, joined in `error`) |
| 401 | `/api/agent/call` without a valid token |
| 403 | refused: a foreign host or origin, or a local file that is not allowed |
| 404 | the deck, slide, source, asset or export does not exist |
| 503 | the client is not built (only the SPA routes) |

Codes in use: `pdf_unavailable`, `image_studio_unavailable`, `generation_failed`, `model_unavailable`, `no_slides`,
`no_material`, `outline_required`, `prompt_required`, `confirm_required`.

## Guard

Every request must have a local `Host` (`localhost`, `127.0.0.1`, `[::1]`, or a name in `CICERO_ALLOWED_HOSTS`). An
`Origin`, when present, must pass the same rule (the Vite dev origins are allowed). Cross-site requests are refused
unless they are top-level navigations, and state-changing methods are never accepted as navigations. Requests with no
`Sec-Fetch-*` headers (curl, the MCP bridge) pass.

## Health

| method and path | answer |
| --- | --- |
| `GET /api/health` | `{service: "cicero-hoard", version, dataDirConfigured, counts, hoard_link}`; cheap, polled by the launcher |
| `GET /api/status` | adds `model` (Hoard Link status), `pdf_available`, `family`, `uptime_s`, `db`, `schema` |

## Decks

| method and path | body | answer |
| --- | --- | --- |
| `GET /api/decks` | | `{items: [{id, title, status, language, slides, approved, updated_at, theme}]}` |
| `POST /api/decks` | `{title, brief?, audience?, tone?, language? ("es"\|"en"), slide_count? (3-40, default 10), theme?}` | 201, the deck |
| `GET /api/decks/{id}` | | the deck: `{id, ref, title, brief, audience, tone, language, slide_count, theme, status, created_at, updated_at, model_used, sources[], outline[], slides[]}` |
| `PATCH /api/decks/{id}` | any of the create fields | the deck |
| `DELETE /api/decks/{id}?confirm=true` | | `{deleted: true, id}`; without `confirm=true` it answers 400 |
| `GET /api/decks/{id}/check` | | `{issues: [{slide_id, position, kind, severity ("warning"\|"info"), message}]}` |
| `GET /api/decks/{id}/preview.html` | | the whole deck as one HTML page (stacked slides); CSP `default-src 'none'` |
| `GET /api/decks/{id}/slides/{slide}/preview.html` | | one slide as an HTML page |

`status` is derived: `draft`, `outline`, `review`, `ready`. `language` defaults to the setting `default_language`.
The message language of `check` follows the deck's language.

Issue kinds: `no_slides`, `empty_slide`, `overflow`, `overflow_risk`, `too_many_bullets`, `long_bullet`,
`unsourced_numbers`, `unsourced_chart`, `chart_empty`, `chart_mismatch`, `chart_pie_series`, `image_missing`,
`image_prompt_only`, `layout_content`, `missing_notes`, `not_approved`. The number check runs only when the deck has
at least one source; the deck's own title, brief, audience and tone count as sources of numbers.

## Sources

| method and path | body | answer |
| --- | --- | --- |
| `POST /api/decks/{id}/sources` | JSON `{title?, text, kind? ("text"\|"markdown")}` or multipart with a `file` part (and optional `title` field) | 201, `{id, title, kind, chars, created_at, truncated}` |
| `GET /api/decks/{id}/sources` | | `{items: [...]}` without the text |
| `GET /api/decks/{id}/sources/{source_id}?offset=0&max_chars=12000` | | the source with a slice of `text` and `offset` |
| `DELETE /api/decks/{id}/sources/{source_id}` | | `{deleted: true, id}`; slides that cited it lose the reference |

Files: `.txt`, `.md`, `.pdf`, `.docx`, `.pptx`, at most 20 MB and 400,000 characters of text (longer text is cut and
`truncated` is true). Kinds: `text`, `markdown`, `pdf`, `docx`, `pptx`.

## Outline

| method and path | body | answer |
| --- | --- | --- |
| `POST /api/decks/{id}/outline/generate` | | the deck plus `generator` (`model` or `fallback`) and `warnings[]` |
| `PUT /api/decks/{id}/outline` | `{items: [{id?, title, purpose?, points?, layout_hint?}]}` | the deck; items with a known `id` keep it (and the slide linked to it) |

`outline/generate` answers 400 `generation_failed` when the model returns unusable JSON twice, and 400 `no_material`
when there is no brief and no source to work from. When no model is reachable it builds the outline by rules.

## Slides

| method and path | body | answer |
| --- | --- | --- |
| `POST /api/decks/{id}/slides/generate` | `{only_missing?: false}` (optional) | the deck plus `generator` (`model`, `fallback`, `mixed`), `warnings[]`, `generated`, `kept` |
| `POST /api/decks/{id}/slides/reorder` | `{order: [slide ids]}`; every slide exactly once | the deck |
| `POST /api/decks/{id}/slides` | `{after_id?, layout?, title?, subtitle?, blocks?, notes?, image_prompt?, sources?}` (optional body) | 201, the slide |
| `GET /api/decks/{id}/slides/{slide}` | | the slide |
| `PATCH /api/decks/{id}/slides/{slide}` | any of `title, subtitle, layout, blocks, notes, image_prompt, sources` | the slide, new revision, back to draft |
| `DELETE /api/decks/{id}/slides/{slide}` | | `{deleted: true, id}` |
| `POST /api/decks/{id}/slides/{slide}/regenerate` | `{feedback?}` | the slide (new revision) plus `generator`, `warnings`; 400 `model_unavailable` without a model |
| `POST /api/decks/{id}/slides/{slide}/approve` | | the slide, `status: "approved"` |
| `POST /api/decks/{id}/slides/{slide}/unapprove` | | the slide, `status: "draft"` |
| `GET /api/decks/{id}/slides/{slide}/revisions` | | `{items: [{slide_id, revision, created_at, reason, snapshot}]}`, newest first |
| `POST /api/decks/{id}/slides/{slide}/revert` | `{revision}` | the slide, restored as a new revision with reason `reverted` |
| `POST /api/decks/{id}/slides/{slide}/image` | `{prompt?}` | the slide with the generated picture; 400 `image_studio_unavailable` without a studio |

A slide: `{id, position, layout, title, subtitle, blocks[], notes, status ("draft"|"approved"), revision, sources[],
image_prompt, outline_id}`. Revision reasons: `generated`, `edited`, `regenerated`, `reverted`.

Layouts: `title`, `section`, `bullets`, `two_column`, `image_text`, `quote`, `chart`, `closing`.

Blocks (at most 8 per slide; bullets at most 12 items of 400 characters):

```json
{"type": "bullets", "items": ["..."]}
{"type": "text", "text": "..."}
{"type": "image", "asset_id": "...", "caption": "..."}
{"type": "quote", "text": "...", "attribution": "..."}
{"type": "columns", "left_title": "...", "left": ["..."], "right_title": "...", "right": ["..."]}
{"type": "chart", "chart": "bar|line|pie", "title": "...", "categories": ["..."], "series": [{"name": "...", "values": [1, 2]}]}
```

An `image` block must reference an asset that exists.

## Assets

| method and path | body | answer |
| --- | --- | --- |
| `POST /api/decks/{id}/assets` | multipart, `file` part: PNG, JPEG or WEBP, at most 15 MB and 50 megapixels | 201, `{asset_id, width, height, mime, bytes}`; EXIF orientation is applied |
| `GET /api/assets/{asset_id}` | | the image (`nosniff`, private cache) |

## Exports

| method and path | body | answer |
| --- | --- | --- |
| `POST /api/decks/{id}/export` | `{format: "pptx"\|"pdf"\|"html"\|"md"}` | 201, `{id, deck_id, format, filename, bytes, sha256, created_at, url}` |
| `GET /api/decks/{id}/exports` | | `{items: [...]}` |
| `GET /api/exports/{export_id}/file` | | the file as an attachment; HTML is served with `Content-Security-Policy: sandbox` |

Errors: 400 `no_slides` when the deck has no slides; 400 `pdf_unavailable` when no Chromium can be started (the other
formats do not depend on it). Files live in `<data>/exports/<export id>/`. The HTML export leaves speaker notes out.

## Themes and settings

| method and path | body | answer |
| --- | --- | --- |
| `GET /api/themes` | | `{items: [{id, name, colors: {background, surface, text, muted, accent, accent2}, fonts: {heading, body}}]}` |
| `GET /api/settings` | | `{model, default_language, pdf_available, image_studio: {configured_url, timeout_s}, file_roots, max_upload_mb}` |
| `PATCH /api/settings` (also `PUT`) | `{model?, default_language?}` | the settings |

## Agent bridge

| method and path | answer |
| --- | --- |
| `GET /api/agent/tools` | `{instructions, tools: [{name, description, annotations, inputSchema}]}` |
| `POST /api/agent/call` | body `{name, arguments?, caller?}` with `Authorization: Bearer <contents of data/mcp-token>`; answers the tool result (trimmed to about 20 KB); 401 without the token, 404 for an unknown tool, 400 for invalid arguments or a domain error, 403 for a refused path |

The 25 tools are listed in `README.md`. The REST routes above and the tools share one implementation.

## PWA and client

`GET /manifest.webmanifest` and `GET /sw.js` serve the installable app. Any other path that is not under `/api/` is
served from `cicero_hoard/static` (the built client), falling back to `index.html`; when the client is not built the
answer is 503 `{"error": ...}`.
