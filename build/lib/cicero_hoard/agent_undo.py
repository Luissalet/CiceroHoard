"""Accountable agents: what each write tool captures before it runs, what it reports after it, and how to take it back.

Three hooks per tool (see ``hoard_link.agentkit.Tool``):

* ``capture(svc, args)`` runs just before the write and returns the state that would be lost (a slide as it was, the outline, a
  deleted source). It is kept in the agent journal as ``before``.
* ``track(svc, args, result)`` runs just after and says which objects the write touched and a fingerprint (``etag``) of what the
  object looks like now. It reads the database, not the result: the result an agent gets is cut to ~20 KB.
* ``undo(svc, record, dry_run=False)`` puts ``before`` back. It first compares the object with ``etag``; when it differs (somebody edited
  it in the web interface, which the journal never sees) it raises a ``conflict`` and nothing changes.

Objects are slash-separated paths, and two writes conflict when the paths are equal or one contains the other::

    deck:D                 the whole presentation (deck_create)
    deck:D/meta            title, brief, audience, tone, language, slide count, theme
    deck:D/outline         the outline
    deck:D/sources/ID      one source
    deck:D/slides/S        one slide (text, blocks, notes, sources, approval)
    deck:D/slides          every slide (generating them, removing a source that slides cite)
    deck:D/order           the order of the slides

Not undoable (no handler, reported as such): deck_delete, deck_export, asset_import, slide_image, vector_figure_create, craft_call,
deck_handout_designcraft, deck_template, theme_from_tokens.
"""

from __future__ import annotations

import json
from typing import Any, Callable, Optional

from . import decks as store
from .errors import CiceroError, NotFound
from .hoard_link.agentkit import AppError
from .util import jload, sha256_hex


def _digest(value: Any) -> str:
    return sha256_hex(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str))[:16]


def _conflict(message: str) -> AppError:
    return AppError("conflict", message, hint="Look at the presentation as it is now before undoing anything else.")


def _id_of(record: dict[str, Any], key: str) -> str:
    for item in record.get("ids") or []:
        name, _, value = str(item).partition("=")
        if name == key:
            return value
    return ""


def _before(record: dict[str, Any]) -> dict[str, Any]:
    before = record.get("before")
    return before if isinstance(before, dict) else {}


def _deck_path(deck_id: str, *parts: str) -> str:
    return "/".join([f"deck:{deck_id}", *parts])


def _slide_ids(svc: Any, deck_id: str) -> list[str]:
    return [r["id"] for r in svc.db.query("SELECT id FROM slides WHERE deck_id = ? ORDER BY position", (deck_id,))]


def _slides_signature(svc: Any, deck_id: str) -> str:
    return _digest([(s["id"], store.slide_etag(s)) for s in store.deck_view(svc, deck_id)["slides"]])


# ------------------------------------------------------------------------------------------------ deck_create

def track_deck_create(svc: Any, args: Any, result: dict) -> dict:
    return {"objects": [f"deck:{result['id']}"], "ids": [f"deck_id={result['id']}"], "etag": ""}


def undo_deck_create(svc: Any, record: dict, dry_run: bool = False) -> dict:
    deck_id = _id_of(record, "deck_id")
    try:
        deck = store.deck_view(svc, deck_id)
    except NotFound:
        return {"already_gone": True}
    leftovers = [name for name, items in (("sources", deck["sources"]), ("slides", deck["slides"]), ("outline", deck["outline"])) if items]
    if leftovers:
        raise _conflict(f"The presentation has {', '.join(leftovers)} that this session did not remove, so it is not deleted.")
    if dry_run:
        return {"would_delete": deck_id, "title": deck["title"]}
    store.delete_deck(svc, deck_id, True)
    return {"deleted": deck_id}


# ------------------------------------------------------------------------------------------------ deck fields

def _deck_fields(deck: dict, keys: Any) -> dict:
    return {k: deck[k] for k in keys if k in deck}


def capture_deck_update(svc: Any, args: Any) -> dict:
    keys = list(args.model_dump(exclude={"deck_id"}, exclude_none=True))
    return {"deck_id": args.deck_id, "fields": _deck_fields(store.deck_view(svc, args.deck_id), keys)}


def track_deck_update(svc: Any, args: Any, result: dict) -> dict:
    fields = _deck_fields(store.deck_view(svc, args.deck_id), args.model_dump(exclude={"deck_id"}, exclude_none=True))
    return {"objects": [_deck_path(args.deck_id, "meta")], "ids": [f"deck_id={args.deck_id}"], "etag": _digest(fields)}


def capture_deck_theme(svc: Any, args: Any) -> dict:
    if args.theme is None or not args.deck_id:
        return {"noop": True}
    return {"deck_id": args.deck_id, "fields": _deck_fields(store.deck_view(svc, args.deck_id), ["theme"])}


def track_deck_theme(svc: Any, args: Any, result: dict) -> dict:
    if args.theme is None or not args.deck_id:
        return {"objects": [], "etag": ""}
    return {"objects": [_deck_path(args.deck_id, "meta")], "ids": [f"deck_id={args.deck_id}"],
            "etag": _digest(_deck_fields(store.deck_view(svc, args.deck_id), ["theme"]))}


def undo_deck_fields(svc: Any, record: dict, dry_run: bool = False) -> dict:
    before = _before(record)
    if before.get("noop") or not before.get("fields"):
        return {"unchanged": True}
    deck_id, fields = before["deck_id"], before["fields"]
    try:
        deck = store.deck_view(svc, deck_id)
    except NotFound:
        raise _conflict("The presentation no longer exists.") from None
    if _digest(_deck_fields(deck, fields)) != record.get("etag"):
        raise _conflict("The presentation's title, brief, audience, tone, language, slide count or theme changed after this write.")
    if dry_run:
        return {"would_restore": fields}
    store.update_deck(svc, deck_id, fields)
    return {"restored": fields}


# ------------------------------------------------------------------------------------------------ outline

def capture_outline(svc: Any, args: Any) -> dict:
    deck = store.deck_view(svc, args.deck_id)
    return {"deck_id": args.deck_id, "outline": deck["outline"], "model_used": deck["model_used"]}


def track_outline(svc: Any, args: Any, result: dict) -> dict:
    return {"objects": [_deck_path(args.deck_id, "outline")], "ids": [f"deck_id={args.deck_id}"],
            "etag": _digest(store.deck_view(svc, args.deck_id)["outline"])}


def undo_outline(svc: Any, record: dict, dry_run: bool = False) -> dict:
    before = _before(record)
    try:
        deck = store.deck_view(svc, before["deck_id"])
    except (NotFound, KeyError):
        raise _conflict("The presentation no longer exists.") from None
    if _digest(deck["outline"]) != record.get("etag"):
        raise _conflict("The outline changed after this write.")
    if dry_run:
        return {"would_restore_items": len(before["outline"])}
    store.set_outline(svc, before["deck_id"], before["outline"], model_used=before.get("model_used"), set_model=True)
    return {"restored_items": len(before["outline"])}


# ------------------------------------------------------------------------------------------------ sources

def track_source_add(svc: Any, args: Any, result: dict) -> dict:
    return {"objects": [_deck_path(args.deck_id, "sources", str(result["id"]))], "ids": [f"deck_id={args.deck_id}", f"source_id={result['id']}"],
            "etag": _digest({k: result.get(k) for k in ("id", "title", "kind", "chars", "truncated")})}


def _session_clears_slides(svc: Any, record: dict, deck_id: str) -> bool:
    """A dry run checks each write on its own, but a real undo goes newest first: slides the same session made after this
    write are gone by the time it is reached. True when such a write exists on this deck and has not been undone."""
    from .hoard_link.agent_journal import Journal
    try:
        rows = Journal(svc.config.data_dir).query(session=str(record.get("session") or ""), kind="write", limit=1000)
    except Exception:  # noqa: BLE001 - a preview only
        return False
    return any(r.get("ok") and not r.get("undone") and float(r.get("ts") or 0) >= float(record.get("ts") or 0) and r.get("id") != record.get("id")
               and r.get("tool") in ("slides_generate", "slide_add", "slides_add") and any(str(o).startswith(f"deck:{deck_id}/") for o in r.get("objects") or [])
               for r in rows)


def undo_source_add(svc: Any, record: dict, dry_run: bool = False) -> dict:
    deck_id, source_id = _id_of(record, "deck_id"), int(_id_of(record, "source_id") or 0)
    row = svc.db.one("SELECT * FROM sources WHERE id = ? AND deck_id = ?", (source_id, deck_id))
    if row is None:
        return {"already_gone": True}
    shown = store._source_dict(row)
    if _digest({k: shown.get(k) for k in ("id", "title", "kind", "chars", "truncated")}) != record.get("etag"):
        raise _conflict("The source changed after this write.")
    citing = [s["id"] for s in store.deck_view(svc, deck_id)["slides"] if source_id in s["sources"]]
    if citing:
        if dry_run and _session_clears_slides(svc, record, deck_id):
            return {"would_remove": source_id, "after": "the slides this session made are taken back first"}
        raise _conflict("Slides cite this source, so it is not removed.")
    if dry_run:
        return {"would_remove": source_id}
    store.remove_source(svc, deck_id, source_id)
    return {"removed": source_id}


def capture_source_remove(svc: Any, args: Any) -> dict:
    row = svc.db.one("SELECT * FROM sources WHERE id = ? AND deck_id = ?", (args.source_id, args.deck_id))
    if row is None:
        raise NotFound(f"Source {args.source_id} not found in this deck.")
    citing = {s["id"]: s["sources"] for s in store.deck_view(svc, args.deck_id)["slides"] if args.source_id in s["sources"]}
    return {"deck_id": args.deck_id, "source": {k: row[k] for k in row.keys()}, "citing": citing}


def track_source_remove(svc: Any, args: Any, result: dict) -> dict:
    return {"objects": [_deck_path(args.deck_id, "sources", str(args.source_id)), _deck_path(args.deck_id, "slides")],
            "ids": [f"deck_id={args.deck_id}", f"source_id={args.source_id}"], "etag": "removed"}


def undo_source_remove(svc: Any, record: dict, dry_run: bool = False) -> dict:
    before = _before(record)
    source = before["source"]
    if svc.db.one("SELECT 1 FROM sources WHERE id = ?", (source["id"],)) is not None:
        raise _conflict("A source with that id exists again.")
    try:
        store.deck_view(svc, before["deck_id"])
    except NotFound:
        raise _conflict("The presentation no longer exists.") from None
    if dry_run:
        return {"would_restore_source": source["id"], "slides_citing": len(before.get("citing") or {})}
    store.reinsert_source(svc, before["deck_id"], source, before.get("citing") or {})
    return {"restored_source": source["id"]}


# ------------------------------------------------------------------------------------------------ one slide

def capture_slide(svc: Any, args: Any) -> dict:
    return {"deck_id": args.deck_id, "slide_id": args.slide_id, "state": store.get_slide(svc, args.deck_id, args.slide_id)}


def capture_slide_revert(svc: Any, args: Any) -> dict:
    return {"noop": True} if args.revision is None else capture_slide(svc, args)


def _slide_track(svc: Any, deck_id: str, slide_id: str) -> dict:
    return {"objects": [_deck_path(deck_id, "slides", slide_id)], "ids": [f"deck_id={deck_id}", f"slide_id={slide_id}"],
            "etag": store.slide_etag(store.get_slide(svc, deck_id, slide_id))}


def track_slide(svc: Any, args: Any, result: dict) -> dict:
    return _slide_track(svc, args.deck_id, args.slide_id)


def track_slide_revert(svc: Any, args: Any, result: dict) -> dict:
    return {"objects": [], "etag": ""} if args.revision is None else _slide_track(svc, args.deck_id, args.slide_id)


def undo_slide(svc: Any, record: dict, dry_run: bool = False) -> dict:
    before = _before(record)
    if before.get("noop"):
        return {"unchanged": True}
    try:
        current = store.get_slide(svc, before["deck_id"], before["slide_id"])
    except NotFound:
        raise _conflict("The slide no longer exists.") from None
    if store.slide_etag(current) != record.get("etag"):
        raise _conflict("The slide was edited after this write (in the web interface or by another session).")
    if store.slide_etag(before["state"]) == record.get("etag"):
        return {"unchanged": True}
    if dry_run:
        return {"would_restore_slide": before["slide_id"], "title": before["state"].get("title", "")}
    restored = store.restore_slide(svc, before["deck_id"], before["slide_id"], before["state"], reason="undo of an agent session")
    return {"restored_slide": before["slide_id"], "revision": restored["revision"]}


# ------------------------------------------------------------------------------------------------ adding and removing slides

def track_slide_add(svc: Any, args: Any, result: dict) -> dict:
    tracked = _slide_track(svc, args.deck_id, result["id"])
    tracked["objects"].append(_deck_path(args.deck_id, "order"))
    return tracked


def undo_slide_add(svc: Any, record: dict, dry_run: bool = False) -> dict:
    deck_id, slide_id = _id_of(record, "deck_id"), _id_of(record, "slide_id")
    try:
        current = store.get_slide(svc, deck_id, slide_id)
    except NotFound:
        return {"already_gone": True}
    if store.slide_etag(current) != record.get("etag"):
        raise _conflict("The slide was edited after it was added.")
    if dry_run:
        return {"would_delete_slide": slide_id}
    store.delete_slide(svc, deck_id, slide_id)
    return {"deleted_slide": slide_id}


def track_slides_add(svc: Any, args: Any, result: dict) -> dict:
    if result.get("replayed"):
        return {"objects": [], "ids": [f"deck_id={args.deck_id}"], "etag": "replayed"}
    ids = [s["id"] for s in result["slides"]]
    objects = [_deck_path(args.deck_id, "slides", i) for i in ids] if len(ids) <= 20 else [_deck_path(args.deck_id, "slides")]
    current = [store.slide_etag(store.get_slide(svc, args.deck_id, i)) for i in ids]
    return {"objects": [*objects, _deck_path(args.deck_id, "order")], "ids": [f"deck_id={args.deck_id}", f"batch_key={args.batch_key}",
                                                                              *[f"slide_id={i}" for i in ids]], "etag": _digest(current)}


def undo_slides_add(svc: Any, record: dict, dry_run: bool = False) -> dict:
    if record.get("etag") == "replayed":
        return {"unchanged": True}
    deck_id = _id_of(record, "deck_id")
    ids = [str(i).partition("=")[2] for i in record.get("ids") or [] if str(i).startswith("slide_id=")]
    present = []
    for slide_id in ids:
        try:
            present.append((slide_id, store.slide_etag(store.get_slide(svc, deck_id, slide_id))))
        except NotFound:
            continue
    if not present:
        return {"already_gone": True}
    if len(present) != len(ids) or _digest([e for _, e in present]) != record.get("etag"):
        raise _conflict("Some of the slides of this batch were edited or removed afterwards.")
    if dry_run:
        return {"would_delete_slides": len(present)}
    batch_key = _id_of(record, "batch_key")
    with svc.db.transaction():
        for slide_id, _ in present:
            store.delete_slide(svc, deck_id, slide_id)
        if batch_key:
            store.delete_batch_receipt(svc, deck_id, batch_key)
    return {"deleted_slides": len(present)}


def capture_slide_delete(svc: Any, args: Any) -> dict:
    return capture_slide(svc, args)


def track_slide_delete(svc: Any, args: Any, result: dict) -> dict:
    return {"objects": [_deck_path(args.deck_id, "slides", args.slide_id), _deck_path(args.deck_id, "order")],
            "ids": [f"deck_id={args.deck_id}", f"slide_id={args.slide_id}"], "etag": "deleted"}


def undo_slide_delete(svc: Any, record: dict, dry_run: bool = False) -> dict:
    before = _before(record)
    if svc.db.one("SELECT 1 FROM slides WHERE id = ?", (before["slide_id"],)) is not None:
        raise _conflict("A slide with that id exists again.")
    try:
        store.deck_view(svc, before["deck_id"])
    except NotFound:
        raise _conflict("The presentation no longer exists.") from None
    if dry_run:
        return {"would_restore_slide": before["slide_id"], "title": before["state"].get("title", "")}
    store.reinsert_slide(svc, before["deck_id"], before["state"], reason="undo of an agent session")
    return {"restored_slide": before["slide_id"], "note": "its older revisions were deleted with it"}


# ------------------------------------------------------------------------------------------------ order and bulk generation

def capture_reorder(svc: Any, args: Any) -> dict:
    return {"deck_id": args.deck_id, "order": _slide_ids(svc, args.deck_id)}


def track_reorder(svc: Any, args: Any, result: dict) -> dict:
    return {"objects": [_deck_path(args.deck_id, "order")], "ids": [f"deck_id={args.deck_id}"], "etag": _digest(_slide_ids(svc, args.deck_id))}


def undo_reorder(svc: Any, record: dict, dry_run: bool = False) -> dict:
    before = _before(record)
    try:
        current = _slide_ids(svc, before["deck_id"])
    except NotFound:
        raise _conflict("The presentation no longer exists.") from None
    if _digest(current) != record.get("etag"):
        raise _conflict("The slides were reordered, added or removed after this write.")
    if current == before["order"]:
        return {"unchanged": True}
    if dry_run:
        return {"would_restore_order": len(before["order"])}
    store.reorder_slides(svc, before["deck_id"], before["order"])
    return {"restored_order": len(before["order"])}


def capture_generate(svc: Any, args: Any) -> dict:
    deck = store.deck_view(svc, args.deck_id)
    return {"deck_id": args.deck_id, "slides": deck["slides"], "model_used": deck["model_used"]}


def track_generate(svc: Any, args: Any, result: dict) -> dict:
    return {"objects": [_deck_path(args.deck_id, "slides"), _deck_path(args.deck_id, "order")], "ids": [f"deck_id={args.deck_id}"],
            "etag": _slides_signature(svc, args.deck_id)}


def undo_generate(svc: Any, record: dict, dry_run: bool = False) -> dict:
    before = _before(record)
    deck_id = before["deck_id"]
    try:
        if _slides_signature(svc, deck_id) != record.get("etag"):
            raise _conflict("Slides were edited, added or removed after they were generated.")
    except NotFound:
        raise _conflict("The presentation no longer exists.") from None
    snapshot = {s["id"]: s for s in before["slides"]}
    current = {s["id"]: s for s in store.deck_view(svc, deck_id)["slides"]}
    to_restore = [i for i, s in snapshot.items() if i in current and store.slide_etag(current[i]) != store.slide_etag(s)]
    to_bring_back = [i for i in snapshot if i not in current]
    to_delete = [i for i in current if i not in snapshot]
    if dry_run:
        return {"would_restore": len(to_restore), "would_bring_back": len(to_bring_back), "would_delete": len(to_delete)}
    with svc.db.transaction():
        for slide_id in to_delete:
            store.delete_slide(svc, deck_id, slide_id)
        for slide_id in to_restore:
            store.restore_slide(svc, deck_id, slide_id, snapshot[slide_id], reason="undo of an agent session")
        for slide_id in sorted(to_bring_back, key=lambda i: snapshot[i].get("position") or 0):
            store.reinsert_slide(svc, deck_id, snapshot[slide_id], reason="undo of an agent session")
        wanted = [s["id"] for s in before["slides"]]
        if _slide_ids(svc, deck_id) != wanted:
            store.reorder_slides(svc, deck_id, wanted)
        svc.db.execute("UPDATE decks SET model_used = ? WHERE id = ?", (before.get("model_used"), deck_id))
    return {"restored": len(to_restore), "brought_back": len(to_bring_back), "deleted": len(to_delete)}


# ------------------------------------------------------------------------------------------------ the table

#: tool name -> the hooks to attach (``dataclasses.replace(tool, **HOOKS[name])``)
HOOKS: dict[str, dict[str, Callable[..., Any]]] = {
    "deck_create": {"track": track_deck_create, "undo": undo_deck_create},
    "deck_update": {"capture": capture_deck_update, "track": track_deck_update, "undo": undo_deck_fields},
    "deck_theme": {"capture": capture_deck_theme, "track": track_deck_theme, "undo": undo_deck_fields},
    "outline_generate": {"capture": capture_outline, "track": track_outline, "undo": undo_outline},
    "outline_update": {"capture": capture_outline, "track": track_outline, "undo": undo_outline},
    "source_add": {"track": track_source_add, "undo": undo_source_add},
    "source_remove": {"capture": capture_source_remove, "track": track_source_remove, "undo": undo_source_remove},
    "slide_update": {"capture": capture_slide, "track": track_slide, "undo": undo_slide},
    "slide_edit_text": {"capture": capture_slide, "track": track_slide, "undo": undo_slide},
    "slide_set_image": {"capture": capture_slide, "track": track_slide, "undo": undo_slide},
    "slide_regenerate": {"capture": capture_slide, "track": track_slide, "undo": undo_slide},
    "slide_approve": {"capture": capture_slide, "track": track_slide, "undo": undo_slide},
    "slide_revert": {"capture": capture_slide_revert, "track": track_slide_revert, "undo": undo_slide},
    "slide_add": {"track": track_slide_add, "undo": undo_slide_add},
    "slides_add": {"track": track_slides_add, "undo": undo_slides_add},
    "slide_delete": {"capture": capture_slide_delete, "track": track_slide_delete, "undo": undo_slide_delete},
    "slides_reorder": {"capture": capture_reorder, "track": track_reorder, "undo": undo_reorder},
    "slides_generate": {"capture": capture_generate, "track": track_generate, "undo": undo_generate},
}

#: writes that create or edit drafts and never delete or publish: what a token with the ``drafts`` profile may call
DRAFT_SAFE = {"deck_create", "deck_update", "deck_theme", "theme_from_tokens", "source_add", "slide_add", "slides_add", "slide_update",
              "slide_edit_text", "slide_set_image", "slide_regenerate", "slide_image", "asset_import", "slides_reorder"}
