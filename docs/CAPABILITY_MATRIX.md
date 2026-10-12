# Capability Matrix

Research snapshot: 2026-10-12. This compares documented workflows, not visual quality scores or full product parity.
Research sources describe inspiration; only verified Cicero behavior is counted as implemented.

| Capability | Cicero status | Verification / Remaining scope |
| --- | --- | --- |
| Editable specialist charts | Implemented | 14 chart kinds, native opening integration test; export differences in visual catalog |
| Labels, axes, annotations, references | Implemented with format differences | Web analytical objects; some native analytical captions instead of plot geometry |
| CSV/TSV/XLSX data sources | Implemented | Typed snapshots, explicit decimal profiles, selected worksheet, formula-cache warnings |
| Grouping/filtering/aggregation/sorting | Implemented | Reproducible derived snapshots; full API/MCP, subset in UI |
| External live data synchronization | Implemented locally; optional cloud adapter | File/HTTP and SQL snapshot worker; real SQLite scheduled refresh verified. Credentialed cloud access untested and deprioritized |
| Tables, metrics and graph layouts | Implemented | Shared scene; native editable shapes and cells |
| Timelines and staged milestones | Implemented | Native/web grouped entrances, completed PDF state |
| Frame composition and crop focus | Implemented | Normalized body frames, explicit text size, cover/contain and native image crop |
| Presenter notes and timer | Implemented | Separate audience/state and speaker endpoints, current/next console |
| Agent remote control of a local session | Implemented | Versioned commands and browser keyboard synchronization; local screen sharing |
| Offline staged presentation | Implemented | Self-contained HTML runtime, no live session dependency |
| Inter-slide matched-object morphing | Implemented | Stable block/node IDs, matched objects in web and native transitions |
| Embedded audio/video | Implemented | Playback controls, trim/rate/loop/volume, video captions, offline HTML and native media; PDF static |
| Rich 3D and camera paths | Implemented for primitives and imported models | Offline complete GLB/glTF/ZIP resource graph, textures, materials, lights, clips, camera paths and orbit. Native/PDF posters |
| Authored slide branching | Implemented | Typed object actions, stable destinations, nested origin/stage return in HTML and live sessions, native slide links |
| Audience polls | Implemented locally | Persistent replaceable votes, open/close, archived rounds and recovery, live audience counts; remote voters require a reachable host |
| Auto refresh linked charts | Implemented | Persisted mappings update charts/tables and audience content without losing navigation |
| Real collaborative editing | Implemented with granular objects/fields/order | Yjs text, nested object maps, identity order and deletion tombstones; independent point/object edits, manual reconciliation and undo tests |
| Varied compositions and agent correction loop | Implemented | Eight frame presets, eight content-led archetypes and native model-driven proposals; structured, image-model or external critique; image-bound review, resume/cancel/apply/undo |
| Series, points and data-state motion | Implemented for all14 chart kinds | Shared ECharts builder; custom series interpolate stable geometry, nulls retain gaps; native files keep base data |
| Paired composition evaluation | Implemented; superiority not established | Explicit independent baseline, preserved source/revision, measured deltas. Demonstration ties the direct composition and detects a regressing layout; not end-to-end harness superiority |
| End-to-end workflow evaluation | Implemented; empirical outcome is corpus-specific | Independent actual PPTX baselines, common native rasterizer, source checks, randomized A/B images and fixed rubric. All failed cases, ties and regressions retained |
| Full parity or superiority over references | Not established | Requires a wider versioned inventory and comparative task evaluation |

## Local Evaluation

The 2026-10-12 pilot uses four synthetic briefs, three slides each, independently authored with the direct artifact-tool harness and Cicero public MCP. Both PPTX arms are rasterized by the same local native Office engine and checked for exact values, units, labels, citations and order. The configured global GLM model inspects randomized actual A/B PNGs with a fixed five-criterion rubric, without an arm mapping.

Initial results: Cicero 7 preferences, direct harness 5. The review exposed native chart labels/units and direct-harness metric/donut defects. Both workflows were corrected; original files, ratings and intermediate unrated rendering remain preserved. Final results: Cicero 8, direct harness 4, no ties; all12 pairs passed source checks. This is an exploratory single-judge pilot, not a statistical or universal superiority claim. Runtime receipts measure execution/export only, not total LLM planning time.

Final source verification: 468 passed, 8 optional external-tool tests skipped, independent cross-review and real MCP/browser/native exports. Real global image input was confirmed separately and in two-round design runs; registry modality labels are not proof of model capability. Native exports preserve editable charts, sparse value labels and explicit axis captions; HTML retains 3D, polls and chart motion, while PPTX/PDF use static scene posters, vote snapshots and base data.

## Primary Research

- [Gamma chart and diagram workflow](https://help.gamma.app/en/articles/11029098-how-can-i-generate-charts-and-diagrams-in-gamma):
  data-based chart creation and customization motivate typed visual mappings and richer analytical controls.
- [Datawrapper tabular upload](https://www.datawrapper.de/academy/upload-data): CSV, spreadsheet and pasted-data
  workflows motivate imports with worksheet selection and preview before mapping.
- [Datawrapper external data](https://www.datawrapper.de/developer/connecting-to-external-data-sources): linked tabular sources
  motivate reusable scheduled refresh, with immutable snapshots alongside live synchronization.
- [Slidev presenter workflow](https://sli.dev/guide/ui#presenter-mode): separate notes/audience windows and synchronized navigation motivate
  separate live surfaces.
- [Internal slide links](https://revealjs.com/links/) motivate stable destinations and clickable object routes.
- [Slide linking workflow](https://help.pitch.com/en/articles/5599765-link-to-slides) motivates links that survive slide reorder.

Reuse: ECharts, ELK and Reveal runtimes retain their packaged licenses. Tabular loading uses the existing
MIT-licensed openpyxl dependency. No reference application's proprietary UI/assets or code were copied.
