---
name: cicero-presentations
description: Create, revise, inspect and export source-grounded presentations with the local Cicero MCP tools, including charts, editable diagrams, templates and click stages. Use when Cicero is available or the user asks to author through Cicero.
---

# Cicero Presentations

Treat Cicero as a visual authoring capability, not only a UI to operate. Prefer its typed MCP tools over
writing per-deck drawing code. Start with `visual_catalog` summary and fetch the relevant visual schema.
The live tool catalogue is the authority for supported arguments and export differences.

Create a deck, attach sources, and author an outline or slide batch. Preserve the user's template and speaker
notes. Use `slide_visual_update` with a current revision to edit one block without losing other content.
`slide_variants` proposes compositions without changing content. `deck_scene` exposes object frames, text sizes
and stage groups; `deck_check` checks evidence and fit. Estimates cannot judge visual quality: inspect the
rendered preview and native export before delivery.

Choose visuals by purpose: paired comparisons use dumbbells, irregular times use numeric X coordinates,
uncertainty uses supplied bounds, exact comparisons use tables, and processes use graph nodes and edges.
Coordinates and routes are computed by the engine. Null values are missing observations, not zeros.
Never fabricate intervals, values or relationships to fill a diagram.

For tabular files, use `dataset_import`, inspect `dataset_get`, optionally derive `dataset_transform`,
then map `dataset_visual`. Attach the returned source IDs when applying the block. Resolve ambiguous decimal
separators explicitly; preserve missing cells and formula-cache warnings. Reimport is explicit, not live sync.
Use timeline blocks for milestones. Freeform frames are fractions of the body area, not absolute slide pixels.
Check overlaps and text fit; image cover/contain and crop focus preserve the original asset.

Use motion to pace an explanation. `build`, `effect` and `duration_ms` stage individual blocks; diagram
`effect: stages` reveals nodes and incoming connectors. `deck_present` returns a local playback URL;
`deck_export` HTML embeds the runtime for offline use. No publishing is needed for screen sharing.
PDF is static. Native entrances need the optional local office engine; unavailable motion exports a static
editable PPTX with a warning. Read export notes for bands, numeric areas, annotations and reference lines.

For remote screen sharing, `deck_live_start` returns distinct presenter/audience URLs. Share the audience only.
`deck_live_state` and `deck_live_control` operate normalized stages, slide jumps, blackout and a paused/resumable
timer. Use the expected version for concurrent control. Sessions are local in-memory state; restart adopts edits.
Speaker notes are confined to the console. Offline HTML stays independent of session polling.

Use existing connected tools when exposed. If tools are not connected, the user's Cicero installation can
serve the same catalogue through its authenticated agent bridge or local stdio MCP server. Do not change
global credentials or agent configuration simply to make a deck. Report an unavailable connection clearly.
