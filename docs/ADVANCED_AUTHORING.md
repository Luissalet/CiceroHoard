# Advanced Local Authoring

The 67-tool native catalog is shared by MCP and the bundled editor. No external account is needed for the visual lab, Three scenes, polls, local files or SQLite. Build bundles before running from source.

## Agent Design Loop

1. Read the deck, visual catalog and source content.
2. Call `deck_visual_lab` with `action: variants` and a slide ID. Eight frame presets and eight content-led archetypes preserve blocks, values, citations and notes. `visual_catalog kind=compositions` exposes the proposal grammar and narrative recommendations.
3. Render with `include_image: true`. The MCP result contains a native image, not merely a filesystem path.
4. Compare measured overlap, clipping, contrast and type size. Inspect the actual images for hierarchy and evidence visibility; the numeric constraint score is not an aesthetic grade.
5. Submit `action: candidate` with corrected frames/font sizes. Evidence changes are rejected for comparison candidates; ordinary slide editing remains available for deliberate content changes.
6. Render again and apply the selected variant. Revision conflicts preserve later edits. Applying a variant supports the existing session undo and slide revisions.

`critique` sends actual image content to the configured global multimodal chat route. A separate `vision` registry entry is not necessary for a multimodal global model. Unsupported image input returns an explicit error, never an invented critique. The requesting LLM can instead inspect native images itself.

`deck_design` starts a durable model-driven cycle, seeds content-led alternatives, requests geometry/style proposals, renders them and supplies actual findings to the next round. `critic=structured` uses measurements, not an aesthetic judgement. `critic=vision` also sends the PNG to the global model for proposals and critique. `critic=external` pauses for the calling LLM or a person to inspect the native image. `feedback` must match the run, variant, source revision and PNG hash. `review` selects another rendered image for its own bound judgement. `step` or `run` with `run_id` resumes; `status`, `list`, `cancel` and explicit `apply` are available. Cancellation is cooperative: an in-flight model request finishes before its result is discarded. Selective undo refuses to overwrite later edits to a changed slide, but leaves unrelated slides alone.

## Comparative Evaluation

`benchmark` requires `baseline_id` in `variant_ids`, all from the same source slide/revision. Author the baseline independently with the same content and constraints. Record paired error/warning/score deltas, inspect both images, and report ties and regressions. This evaluates composition with a common renderer, not end-to-end superiority over every authoring harness. A stronger claim needs repeated independently authored decks and blinded preference ratings.

`deck_benchmark` is the end-to-end protocol. Create an evaluation, register multiple `case` briefs with independently authored local `baseline_path` PPTX files and workflow evidence, then `render`. Both arms use the same native slide engine and size. Exact declared text, units, title order and supported categorical chart caches are checked; unsupported analytic semantics require review and are not silently certified. `blind` returns an A/B PNG with randomized identities and the fixed five-criterion rubric. `rate` requires its image hash plus explicit source checks for both sides. `summary` includes every failed/pending case, source mismatch, regression, win and tie. Execution times must state what they measure; export time is not LLM authoring time. A registered Cicero export cannot masquerade as an independent baseline. Actual visual preference and measured constraints remain separate.

## Scenes And Motion

`scene3d` blocks use Three, editable box/sphere/cylinder/cone/torus objects and imported models, stable IDs, transforms, materials, configurable ambient/hemisphere/directional/point/spot lights, exposure and shadows. Camera keyframes contain time, position and target; motion interpolates smoothly, can loop, pauses on hidden slides and respects reduced motion. Orbit interaction takes over from the authored path. `scene_model_import` reads GLB, glTF or a ZIP containing the complete resource graph. Local buffers and textures are embedded into an immutable glTF asset; source files may disappear without breaking offline HTML. Objects with `shape=model` use `asset_id`, optional fit, material override and animation clip/speed. Meshopt and packaged Draco/Basis decoders require no external CDN. Missing dependencies fail explicitly. Remote resource URLs must first be packaged locally; this importer does not claim to retrieve arbitrary remote models.

Chart `animation` supports `none`, `series`, `points`, `update`, duration and explicit validated data `states` for all14 chart kinds. Static and animated options share one builder; custom dumbbell, band and waterfall geometry interpolates with stable child identities, while null observations retain gaps. Entrances start when the slide becomes present and replay on re-entry; hidden slides retain their static evidence until activated. Titles, legends, units, highlights, annotations and reference lines follow the shared analytical representation. State changes do not alter saved source data; automatic linked refresh preserves animation settings.

## Audience And Collaboration

Block `font_size` controls text, chart labels, tables, diagram labels and timeline headings across preview and native export. Measured fonts include SVG/table text; very small labels contribute explicit legibility defects instead of becoming a high-scoring clipped alternative. Optional scene `auto_frame` fits camera keyframes to actual mesh bounds while preserving each view direction; authored camera coordinates remain unchanged when it is off.

`deck_poll` stores local polls and one replaceable vote per participant. Open/close controls voting. Reset archives the prior round; `rounds` and `restore` recover it without overwriting newer votes. Audience HTML connected to the running service updates counts and permits voting. Remote participants need a reachable host address; sharing only a screen does not give them network access to localhost.

`slide_collaborate` and the collaboration editor use persistent Yjs documents over local WebSockets. Title, subtitle, notes and object text merge at character level. Blocks have durable IDs, nested shared maps and identity ordering; nested scene objects and chart cells merge independently. Operations are `set`, `text`, `insert`, `delete`, `move`, with `block_id` and a typed `path` for nested fields. Deletion tombstones win concurrent field edits; an explicit insert can restore the identity. Reordering does not replace the object's shared map. Legacy documents migrate idempotently; assigning missing block IDs creates one normal slide revision. Ordinary/manual/linked-data/undo changes reconcile into the document. Invalid snapshots roll back atomically. Presence is ephemeral; no blanket undo of other collaborators is offered.

## Format Differences

- Local web audience: camera paths, orbit controls, chart state animation and live polls.
- HTML: bundled Three/ECharts code, scene and chart interaction work offline; live poll requests still require the running service.
- PPTX/PDF: rendered 3D posters and current poll count tables. Chart exports retain base data; native charts stay editable. Export responses explicitly describe these differences.
- SQL/CSV/JSON sources: immutable snapshots and the existing automatic refresh/binding worker. Database queries read data. Cloud adapters are optional; credentialed cloud access has not been verified with a real account.
