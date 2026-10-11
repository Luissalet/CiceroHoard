# Capability Matrix

Research snapshot: 2026-10-11. This compares documented workflows, not visual quality scores or full product parity.
Research sources describe inspiration; only verified Cicero behavior is counted as implemented.

| Capability | Cicero status | Verification / Remaining scope |
| --- | --- | --- |
| Editable specialist charts | Implemented | 14 chart kinds, native opening integration test; export differences in visual catalog |
| Labels, axes, annotations, references | Implemented with format differences | Web analytical objects; some native analytical captions instead of plot geometry |
| CSV/TSV/XLSX data sources | Implemented | Typed snapshots, explicit decimal profiles, selected worksheet, formula-cache warnings |
| Grouping/filtering/aggregation/sorting | Implemented | Reproducible derived snapshots; full API/MCP, subset in UI |
| External live data synchronization | Gap | Explicit reimport/remap only, no external cloud sheet/database synchronization |
| Tables, metrics and graph layouts | Implemented | Shared scene; native editable shapes and cells |
| Timelines and staged milestones | Implemented | Native/web grouped entrances, completed PDF state |
| Frame composition and crop focus | Implemented | Normalized body frames, explicit text size, cover/contain and native image crop |
| Presenter notes and timer | Implemented | Separate audience/state and speaker endpoints, current/next console |
| Agent remote control of a local session | Implemented | Versioned commands and browser keyboard synchronization; local screen sharing |
| Offline staged presentation | Implemented | Self-contained HTML runtime, no live session dependency |
| Inter-slide matched-object morphing | Gap | Stable IDs exist; transitions and point-by-point morphing not implemented |
| Rich 3D, camera paths, embedded videos | Gap | Not part of this batch; media playback lifecycle and exports need design |
| Slide branching and audience interactions | Gap | Direct reserve-slide jumps work; authored branching/polls do not |
| Auto refresh linked charts | Gap | Mapping receipts returned, but no persisted refresh recipes in blocks |
| Real collaborative editing | Gap | Revision conflict checks, not simultaneous multi-user composition |
| Full parity or superiority over references | Not established | Requires a wider versioned inventory and comparative task evaluation |

## Primary Research

- [Gamma chart and diagram workflow](https://help.gamma.app/en/articles/11029098-how-can-i-generate-charts-and-diagrams-in-gamma):
  data-based chart creation and customization motivate typed visual mappings and richer analytical controls.
- [Datawrapper tabular upload](https://www.datawrapper.de/academy/upload-data): CSV, spreadsheet and pasted-data
  workflows motivate imports with worksheet selection and preview before mapping.
- [Datawrapper external data](https://www.datawrapper.de/developer/connecting-to-external-data-sources): linked data
  is explicitly a remaining gap; immutable local snapshots are not advertised as live synchronization.
- [Slidev presenter workflow](https://sli.dev/guide/ui#presenter-mode): separate notes/audience windows and synchronized navigation motivate
  separate live surfaces; matched-object motion remains an unimplemented category here.

Reuse: ECharts, ELK and Reveal runtimes retain their packaged licenses. Tabular loading uses the existing
MIT-licensed openpyxl dependency. No reference application's proprietary UI/assets or code were copied.
