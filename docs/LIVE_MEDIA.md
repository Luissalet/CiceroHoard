# Motion, Multimedia And Linked Data

All authoring routes and MCP tools use the same typed models and domain code. No presentation-specific adapter,
remote account or inference provider is required. The ordinary file roots and configured upload size still apply.

## Object Morph

Set `block.id` to a semantic, stable identity and reuse it only for the same object on adjacent slides.
`deck_transitions(action="inspect")` lists matched, entering and leaving block IDs. Diagram node IDs remain
stable within a parent block. Duplicate block IDs within a slide are rejected.

`deck_transitions(action="set", default={...}, slides={slide_id:{...}})` merges overrides. Supported common
effects: none, fade, slide, convex, concave, zoom and morph. Duration is milliseconds; easing, group and unmatched
control web auto-animation. Optional `native_effect` selects any native transition from `deck_animations(action="list")`.
Explicit common/native transition settings take precedence over legacy native animation transition settings.
Reset clears the common transition settings, restoring the legacy configuration.

Native output uses the vendored transition writer and validated extension/fade fallback. Stable `!!` object names
force native matching. Build stamps are kept separately, so morph and click-stage timing coexist.
Web and native transitions are not pixel-identical. PDF shows the completed static scene. Reduced-motion preferences
disable web morph and entrance animation.

## Audio And Video

`media_import(deck_id,path=...)` or `media_import(deck_id,url=...,filename=...)` imports mp4, webm, mov, mp3, wav,
ogg, m4a or flac. Inspection requires ffprobe; ffmpeg supplies video posters and export compatibility conversion.
Metadata includes duration, size, streams, codecs, poster and origin. Original bytes are immutable and SHA-deduplicated.
`media_get` lists imported assets. The editor supports upload, URL import and choosing an existing deck asset.

Typed `audio`/`video` blocks support start/end seconds, playback_rate, volume, autoplay, loop, muted, controls,
caption, video poster/fit and WebVTT subtitles. Invalid ranges and cross-deck assets are rejected.
Native clips embed compatibility bytes, bake trim/rate, keep volume/loop/autoplay timing and preserve the original.
Video subtitles are burned into the native compatibility copy; HTML keeps switchable WebVTT tracks. Timed audio
captions remain HTML-only and native export explicitly reports this difference. PDF uses the video poster and captions.
Web controls and cover cropping are browser features, not a promise of identical native player chrome.

`deck_media_control` sends play/pause/seek/volume/mute to the selected media_index on the current live slide.
Commands carry the slide and asset identity and are cleared on navigation. The presenter console has equivalent controls.
Browsers can require a first user click for playback, particularly audio. The audience view keeps an actionable
playback notice with an activation/retry button until playback succeeds, is paused or the slide changes.
That button supplies the browser's required user gesture; subsequent commands still use the console/MCP.
Audience state contains no notes.

## Automatic Data

`dataset_link` reads a local CSV/TSV/XLSX or HTTP(S) URL, creates an immutable source snapshot and stores the
origin, import recipe and refresh interval in the database. The service worker refreshes enabled links while Cicero
runs, including after restart. No external scheduler is needed. Disabled links remain paused until resumed.

`dataset_bind` selects a slide/block position and a typed `dataset_visual` mapping, plus an optional typed
`dataset_transform` recipe. It assigns or retains the block identity and uses expected_revision for concurrent edits.
Updates preserve notes, layout, typography, frames and click stages. Manual edits to linked values produce a visible
conflict instead of being overwritten; rebind to adopt a new recipe. Deleted/reidentified blocks report a conflict.

Snapshots remain in source history. Current citations advance without accumulating every refresh; explicit citations
for static content added later remain pinned. Multiple bound visuals preserve one another's sources.
Failures retain the last successful source and visual, report the problem, and retry at the configured interval.
`dataset_links` exposes last check, last change, errors, mappings and schedule. `dataset_link_control` refreshes,
pauses, resumes or unlinks; unlink keeps all snapshots and the current slide contents.

Live web views refresh when content changes. Live sessions adopt only automatic data revisions and retain the
slide, stage and clock. Manual content edits still require restart. Offline HTML/PPTX/PDF freeze the current source
snapshot, with export metadata recording source IDs and check times; no network dependency is embedded in them.
Exports serialize against refreshes so a file cannot contain half of one update and half of another.

## Verification

Focused tests cover immutable snapshots, no-op refresh, file failures, manual edit conflicts, 52 refreshes,
static/manual citations, recipes, pause/resume/unlink, stale revisions, morph identity and native media/animation timing.
The public stdio path is exercised against the running app, including an actual worker-driven file change,
live navigation preservation and offline export. Native office read-back and browser playback are separate checks;
XML validity alone is not treated as playback verification.
