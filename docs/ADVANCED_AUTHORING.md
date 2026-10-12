# Advanced Local Authoring

The 64-tool native catalog is shared by MCP and the bundled editor. No external account is needed for the visual lab, Three scenes, polls, local files or SQLite. Build bundles before running from source.

## Agent Design Loop

1. Read the deck, visual catalog and source content.
2. Call `deck_visual_lab` with `action: variants` and a slide ID. Eight compositions preserve blocks, values, citations and notes.
3. Render with `include_image: true`. The MCP result contains a native image, not merely a filesystem path.
4. Compare measured overlap, clipping, contrast and type size. Inspect the actual images for hierarchy and evidence visibility; the numeric constraint score is not an aesthetic grade.
5. Submit `action: candidate` with corrected frames/font sizes. Evidence changes are rejected for comparison candidates; ordinary slide editing remains available for deliberate content changes.
6. Render again and apply the selected variant. Revision conflicts preserve later edits. Applying a variant supports the existing session undo and slide revisions.

`critique` optionally uses the configured global vision route. An unavailable model returns an explicit error, never an invented critique. The requesting LLM can instead inspect native images itself.

## Comparative Evaluation

`benchmark` requires `baseline_id` in `variant_ids`, all from the same source slide/revision. Author the baseline independently with the same content and constraints. Record paired error/warning/score deltas, inspect both images, and report ties and regressions. This evaluates composition with a common renderer, not end-to-end superiority over every authoring harness. A stronger claim needs repeated independently authored decks and blinded preference ratings.

## Scenes And Motion

`scene3d` blocks use Three, editable box/sphere/cylinder/cone/torus objects, stable IDs, transforms, materials, optional grid and orbit interaction. Camera keyframes contain time, position and target; motion interpolates smoothly, can loop, pauses on hidden slides and respects reduced motion. Orbit interaction takes over from the authored path. Imported 3D mesh files are not supported in this version.

Chart `animation` supports `none`, `series`, `points`, `update`, duration and explicit validated data `states`. ECharts animates bars, horizontal bars, lines, areas, scatter and bubbles. Entrances start when the slide becomes present and replay on re-entry; hidden slides retain their static evidence until activated. Other chart types keep their ordinary static rendering. Titles, legends, units, highlights, annotations and reference lines remain visible. State changes do not alter saved source data; automatic linked refresh preserves animation settings.

## Audience And Collaboration

`deck_poll` stores local polls and one replaceable vote per participant. Open/close controls voting. Reset archives the prior round; `rounds` and `restore` recover it without overwriting newer votes. Audience HTML connected to the running service updates counts and permits voting. Remote participants need a reachable host address; sharing only a screen does not give them network access to localhost.

`slide_collaborate` and the collaboration editor use persistent Yjs documents over local WebSockets. Title, subtitle and notes merge at character level. Blocks are an atomic map value, not a granular simultaneous block editor. Presence is ephemeral. Ordinary slide changes are reconciled before the next collaborative update. Slide revisions provide recovery; a blanket undo of another collaborator's work is not offered.

## Format Differences

- Local web audience: camera paths, orbit controls, chart state animation and live polls.
- HTML: bundled Three/ECharts code, scene and chart interaction work offline; live poll requests still require the running service.
- PPTX/PDF: rendered 3D posters and current poll count tables. Chart exports retain base data; native charts stay editable. Export responses explicitly describe these differences.
- SQL/CSV/JSON sources: immutable snapshots and the existing automatic refresh/binding worker. Database queries read data. Cloud adapters are optional; credentialed cloud access has not been verified with a real account.
