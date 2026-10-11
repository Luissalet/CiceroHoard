# Interactive Navigation

Blocks accept `action`: `kind` is `slide`, `url`, `next`, `previous` or `return`.
A slide target uses its stable `slide_id`; an external target uses an HTTP, HTTPS or mailto `url`.
An optional `label` names the accessible link and native tooltip. Geometry, text, citations and notes are preserved.
The block editor exposes the same destination selector. These are ordinary clickable objects, not a new slide type.

`deck_navigation` supports `inspect`, `set` and `clear`. Editing requires the source `slide_id`, zero-based
`block_index`, and an optional `expected_revision`. Set requires `target`; clear removes only the action.
Inspect returns slide IDs, destinations, validity and format differences. REST uses GET/PUT `/api/decks/{id}/navigation`.
The full registry contains 59 tools. `slide_visual_update` and ordinary slide editing also preserve typed actions.

HTML presentations maintain a nested origin stack and restore the original click stage on return.
Live presentations use the authoritative session: `deck_live_control(action='branch', slide_id=...)` pushes the origin;
`action='return'` pops it. The timer does not restart. State includes `return_depth`, without speaker notes.
The existing session/revision contract still applies. Deleting or manually changing slides requires restarting a live session.
Missing destinations are reported by inspection and `deck_check`; clicking one in HTML shows an error instead of navigating.

PPTX contains native internal slide relationships, external hyperlinks, next/previous slide actions and last-slide-viewed
return. Native return does not restore a click stage or implement the HTML nested stack. Missing destinations are omitted
from native hyperlinks, without discarding their visible content. PDF remains a static presentation, not an interactive route.
Actions use the same scene boxes for generic and user-template exports and retain morph IDs and animation stamps.
