# Visual authoring for agents

Cicero computes composition, renders evidence and exports editable objects. An agent supplies source-grounded
content rather than generating presentation drawing code. All examples below use fictional demonstration data.
Read the live tool catalogue rather than assuming a schema from this document.

## Discovery and construction

1. `visual_catalog {"kind":"summary"}` lists supported visuals and export differences.
2. Fetch `kind: charts`, `diagrams`, `metrics` or `tables` for the complete JSON schema.
3. Create a deck, add its sources, and create slides with `slides_add` or ordinary slide tools.
4. Use `slide_visual_update` for one replacement or append. Pass the current `expected_revision`.
5. Compare `slide_variants`, inspect `deck_scene`, then run `deck_check`. Review a rendered preview too.
6. `deck_present` gives a local presentation URL. `deck_export` returns a file and a download URL.

Example interval block, with numeric X coordinates and a genuine missing observation:

```json
{
  "type": "chart", "chart": "band", "unit": "kPa", "x_label": "Minutes",
  "categories": ["2", "10", "30", "90"],
  "series": [{"name": "Measured", "values": [3, 4, null, 8],
    "x_values": [2, 10, 30, 90], "lower": [2, 3, null, 7], "upper": [4, 5, null, 9]}],
  "show_values": false
}
```

Do not synthesize bounds when the source only provides central estimates. Category order does not substitute
for numeric coordinates. A gap remains a gap, including in the interval region. Bubble `sizes` are explicit
nonnegative quantities and affect symbol area, not radius. A waterfall contains changes, not cumulative totals.

Example editable process with staged incoming connections:

```json
{
  "type": "diagram", "direction": "right", "effect": "stages", "duration_ms": 400,
  "nodes": [{"id": "input", "label": "Measurements"},
    {"id": "fit", "label": "Model", "detail": "Versioned training", "emphasis": true},
    {"id": "result", "label": "Evaluation"}],
  "edges": [{"source": "input", "target": "fit", "label": "Validated data"},
    {"source": "fit", "target": "result"}]
}
```

## Editing safely

`block_index` addresses the block list, not object geometry. Replace an existing index or append at its count.
Read a slide first and preserve its source references. Identical retries at the current revision are no-ops;
stale revisions still conflict. Targeted edits use the same revision journal and agent undo as other slide edits.
No tool runs caller-provided JavaScript or diagram-language code.

`deck_scene` gives versioned geometry, text, font sizes and build groups. Geometry is shared with export;
it is not a screenshot or an aesthetic score. `slide_variants` does not mutate the deck. Apply its returned
layout patch only after evaluating the result. Native text measurement is available after local rendering.

## Playback and export contract

| Visual | HTML | PPTX | PDF |
| --- | --- | --- | --- |
| Charts | Rendered vector evidence | Native data-backed charts, except heatmap/funnel objects | Final static state |
| Diagrams | Automatic layout, object stages | Editable nodes, text and connectors | Final static state |
| Metrics / tables | Separate text / table cells | Editable text / native table | Final static state |
| Band | Filled uncertainty region | Central and bounding curves | Native export appearance |
| Numeric area | Filled numeric area | Numeric line | Native export appearance |
| Annotations / references | Point labels / reference lines | Analytical value captions | Native export appearance |
| Motion | Click stages, reduced-motion support | Native entrances with local office engine | No motion |

`fade`, `wipe` and `draw` are entrance effects. Draw currently reveals the object horizontally, not a morph or
path-specific stroke animation. HTML embeds its runtime and assets for offline playback. Template furniture
needs the optional local office renderer; authored objects stay interactive. No publication or external account
is necessary for screen sharing. Rendering estimates do not replace desktop/mobile and native visual review.

## Evidence discipline

Add derived values explicitly with their calculation and source. `deck_check` verifies numeric presence, not
causal validity, statistical significance or provenance correctness. Never silently combine different experimental
protocols into one ranking. Use speaker notes for limitations and citations. Keep animations purposeful: reveal
an explanation or comparison, and avoid making the audience wait for decoration.
