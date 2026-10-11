# Data And Presentation Workflow

These capabilities are reusable across decks. They contain no domain-specific figures or slide counts.

## Data To Visual

1. Call `dataset_import` with a local CSV/TSV/XLSX path or pasted CSV. For a workbook, select the worksheet.
2. Call `dataset_get` and examine columns, sample rows, warnings and numeric/missing profiles.
3. Set the decimal profile explicitly if a value such as `1.234` is ambiguous.
4. Optionally call `dataset_transform` with filters, group columns, named aggregates and sort order.
5. Call `dataset_visual` with category and value columns. XY charts also require numeric X;
   bands require observed lower/upper columns; bubbles require explicit sizes.
6. Pass the returned `block` and `source_ids` to `slide_visual_update` with the current revision.
7. Check evidence, inspect composition and export through the ordinary deck workflow.

Each import or transform is an immutable source. Transforms record their parent ID and definition.
Reimporting an identical snapshot reuses it, including on concurrent retries. Reimport changed data to
create a new snapshot, inspect it and explicitly remap visuals. There is no automatic background refresh.
Missing observations stay missing. XLSX formula caches are used; formulas are not calculated here.
Numerical comparisons require unambiguous numbers; mixed-type sorting is deterministic with nulls last.
Counts and last values work with categorical columns. Empty sums are zero; other empty numeric aggregates are null.
Mapped numeric blocks bypass the ordinary agent result cap so long arrays cannot be silently shortened.
Import/transform writes have agent undo hooks. A reused snapshot is not removed by undo.
A cited snapshot is protected by the existing source undo conflict handling.

The UI offers file/pasted import, profiles, sample rows, grouping/aggregation and chart/table mapping.
All filtering and sorting options are exposed through REST/MCP; the current UI does not expose every transform argument.
Tables contain at most 30 selected rows, with a truncation warning. Charts can map up to 2,000 rows and six series.
Workbook imports and explicit locale conversion are supported, not external database connectors.

## Composition

`freeform` gives agents and people normalized block placement without drawing per-deck code.
Frames are fractions inside the body area, not the title/footer or entire slide. Existing automatic layouts
remain unchanged. Blocks without explicit frames receive equal-height rows.
Text `font_size` is explicit and does not silently shrink in freeform mode. The fit checker reports overflow.
Stable block IDs propagate to scene IDs and web object attributes. They do not yet enable inter-slide morphing.
Templates map the shared body geometry to their configured body slot.

`timeline` milestones become editable text, circular markers and connecting rules in native export.
Web and native entrance stages reveal milestone groups; PDF shows the completed state.
Contain retains the complete image. Cover crops to its frame, with normalized horizontal/vertical focus;
the native image crop and web object position use the same geometry. Sources are never destructively cropped.

## Presenter

Call `deck_live_start` and open its presenter URL. Open the separate audience URL in the window
that will be shared. The console contains current slide, next slide, private notes, a slide selector,
stage controls, blackout, elapsed/remaining time and main/support boundary.

`deck_live_control` allows another agent to navigate or operate the timer. The same local session
is used by browser keyboard input and console commands. The browser polls locally every 500 ms;
the console polls every second. This is not a frame-synchronized broadcast or audio narration.
Notes are fetched only by the separate speaker endpoint and never embedded in the audience document/state.

The clock starts paused. Pause/resume exclude paused time; reset leaves it paused at zero.
Setting a target does not change elapsed time. The support boundary labels reserve slides but does not hide them.
Sessions survive page refresh while the server runs, not server restart. Restart adopts edits and resets navigation;
old audience URLs must be reopened using the replacement session URL. PDF/offline HTML are independent artifacts.

## Verification

Focused tests cover decimal ambiguity, missing cells, cached formulas, worksheets, concurrent retries,
immutable provenance, targeted citation attachment, undo conflicts, stage navigation, timer semantics,
speaker/audience separation, optimistic state conflicts, frame validity, overlaps, crop focus,
editable timelines, static text export and optional native animation opening.
Browser and actual MCP smoke checks are recorded with the delivery rather than inferred from unit tests.
