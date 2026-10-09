"""The deck store: decks, sources, outline, slides, revisions, assets, exports and status transitions.

Every function takes the ``Services`` object first. Nothing here calls a model; generation lives in ``generate.py``
and only uses these functions to read and save.

Slide positions are 1-based. Deck status is derived, never typed: ``draft`` (no outline), ``outline`` (an outline and
no slides), ``review`` (slides, not all approved) and ``ready`` (slides, all approved).
"""

from __future__ import annotations

import io
import json
import shutil
from pathlib import Path
from typing import Any, Optional

from .errors import CiceroError, NotFound, Refused
from .extract import extract_bytes, kind_for
from .models import Block, DeckCreate, DeckPatch, LAYOUTS, MAX_SLIDES, OutlineItemIn, dump_blocks
from . import custom_themes
from .themes import DEFAULT_THEME
from .hoard_link.atomic import write_bytes_atomic
from .hoard_link.ids import new_ulid as new_id
from .util import clip, iso_stamp, jdump, jload, sha256_hex, slugify

IMAGE_FORMATS = {"PNG": ("image/png", "png"), "JPEG": ("image/jpeg", "jpg"), "WEBP": ("image/webp", "webp")}
MAX_IMAGE_PIXELS = 50_000_000
FILE_SUFFIXES = (".txt", ".md", ".markdown", ".pdf", ".docx", ".pptx")
SLIDE_FIELDS = ("layout", "title", "subtitle", "blocks", "notes", "sources", "image_prompt")


# ---------------- row -> dict ----------------

def _slide_dict(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"], "position": row["position"], "layout": row["layout"], "title": row["title"], "subtitle": row["subtitle"],
        "blocks": jload(row["blocks"], []), "notes": row["notes"], "status": row["status"], "revision": row["revision"],
        "sources": jload(row["sources"], []), "image_prompt": row["image_prompt"], "outline_id": row["outline_id"],
    }


def _source_dict(row: Any) -> dict[str, Any]:
    return {"id": row["id"], "title": row["title"], "kind": row["kind"], "chars": row["chars"], "created_at": iso_stamp(row["created_ts"]),
            "truncated": bool(row["truncated"])}


def _deck_row(svc: Any, deck_id: str) -> Any:
    row = svc.db.one("SELECT * FROM decks WHERE id = ?", (deck_id,))
    if row is None:
        raise NotFound(f"Deck {deck_id} not found.")
    return row


def deck_ref(deck_id: str) -> str:
    return f"hoard://cicero/deck/{deck_id}"


def derive_status(has_outline: bool, slides: list[dict[str, Any]]) -> str:
    if slides:
        return "ready" if all(s["status"] == "approved" for s in slides) else "review"
    return "outline" if has_outline else "draft"


def _refresh_status(svc: Any, deck_id: str, *, touch: bool = True) -> str:
    row = _deck_row(svc, deck_id)
    outline = jload(row["outline"], [])
    slides = svc.db.query("SELECT status FROM slides WHERE deck_id = ?", (deck_id,))
    status = derive_status(bool(outline), [{"status": s["status"]} for s in slides])
    if touch:
        svc.db.execute("UPDATE decks SET status = ?, updated_ts = ? WHERE id = ?", (status, svc.clock(), deck_id))
    else:
        svc.db.execute("UPDATE decks SET status = ? WHERE id = ?", (status, deck_id))
    return status


def _renumber(svc: Any, deck_id: str) -> None:
    rows = svc.db.query("SELECT id FROM slides WHERE deck_id = ? ORDER BY position, created_ts, id", (deck_id,))
    for i, r in enumerate(rows, start=1):
        svc.db.execute("UPDATE slides SET position = ? WHERE id = ?", (i, r["id"]))


# ---------------- decks ----------------

def deck_view(svc: Any, deck_id: str) -> dict[str, Any]:
    row = _deck_row(svc, deck_id)
    sources = [_source_dict(r) for r in svc.db.query("SELECT * FROM sources WHERE deck_id = ? ORDER BY id", (deck_id,))]
    slides = [_slide_dict(r) for r in svc.db.query("SELECT * FROM slides WHERE deck_id = ? ORDER BY position", (deck_id,))]
    custom = custom_themes.get_custom(svc, row["theme"])
    view = {
        "id": row["id"], "ref": deck_ref(row["id"]), "title": row["title"], "brief": row["brief"], "audience": row["audience"], "tone": row["tone"],
        "language": row["language"], "slide_count": row["slide_count"], "theme": row["theme"], "status": row["status"],
        "created_at": iso_stamp(row["created_ts"]), "updated_at": iso_stamp(row["updated_ts"]), "model_used": row["model_used"],
        "sources": sources, "outline": jload(row["outline"], []), "slides": slides,
    }
    if custom:  # a theme made from a design system: the renderers read the definition from here
        view["theme_def"] = custom
    if row['template']:
        view['template'] = jload(row['template'], {})
    return view


def create_deck(svc: Any, data: DeckCreate) -> dict[str, Any]:
    language = data.language or svc.default_language()
    theme = custom_themes.require(svc, data.theme) if data.theme else DEFAULT_THEME
    deck_id, ts = new_id(), svc.clock()
    svc.db.execute(
        "INSERT INTO decks(id, title, brief, audience, tone, language, slide_count, theme, status, outline, created_ts, updated_ts) "
        "VALUES (?,?,?,?,?,?,?,?, 'draft', '[]', ?, ?)",
        (deck_id, data.title, data.brief, data.audience, data.tone, language, data.slide_count, theme, ts, ts))
    svc.emit("cicero.deck.created", {"id": deck_id, "title": clip(data.title, 80), "ref": deck_ref(deck_id)})
    return deck_view(svc, deck_id)


def list_decks(svc: Any) -> dict[str, Any]:
    rows = svc.db.query(
        "SELECT d.*, (SELECT COUNT(*) FROM slides s WHERE s.deck_id = d.id) AS n_slides, "
        "(SELECT COUNT(*) FROM slides s WHERE s.deck_id = d.id AND s.status = 'approved') AS n_approved "
        "FROM decks d ORDER BY d.updated_ts DESC, d.created_ts DESC")
    return {"items": [{"id": r["id"], "title": r["title"], "status": r["status"], "language": r["language"], "slides": r["n_slides"],
                       "approved": r["n_approved"], "updated_at": iso_stamp(r["updated_ts"]), "theme": r["theme"]} for r in rows]}


def update_deck(svc: Any, deck_id: str, patch: DeckPatch | dict[str, Any]) -> dict[str, Any]:
    _deck_row(svc, deck_id)
    fields = patch.model_dump(exclude_none=True) if hasattr(patch, "model_dump") else {k: v for k, v in patch.items() if v is not None}
    if "theme" in fields:
        custom_themes.require(svc, fields["theme"])
    if fields:
        cols = ", ".join(f"{k} = ?" for k in fields)
        svc.db.execute(f"UPDATE decks SET {cols}, updated_ts = ? WHERE id = ?", (*fields.values(), svc.clock(), deck_id))
    return deck_view(svc, deck_id)


def delete_deck(svc: Any, deck_id: str, confirm: bool) -> dict[str, Any]:
    row = _deck_row(svc, deck_id)
    if not confirm:
        raise CiceroError("Deleting a deck removes its sources, slides, revisions, images and exports: pass confirm=true.", code="confirm_required")
    assets = svc.db.query("SELECT id, ext FROM assets WHERE deck_id = ?", (deck_id,))
    exports = svc.db.query("SELECT id FROM exports WHERE deck_id = ?", (deck_id,))
    with svc.db.transaction() as conn:
        conn.execute("DELETE FROM decks WHERE id = ?", (deck_id,))
    for a in assets:
        (svc.config.assets_dir / f"{a['id']}.{a['ext']}").unlink(missing_ok=True)
        if a["ext"] == "svg":
            (svc.config.assets_dir / f"{a['id']}.png").unlink(missing_ok=True)
            (svc.config.assets_dir / f"{a['id']}.vectorcraft").unlink(missing_ok=True)
    for e in exports:
        shutil.rmtree(svc.config.exports_dir / e["id"], ignore_errors=True)
    svc.emit("cicero.deck.deleted", {"id": deck_id, "title": clip(row["title"], 80)})
    return {"deleted": True, "id": deck_id}


# ---------------- sources ----------------

def _insert_source(svc: Any, deck_id: str, title: str, kind: str, text: str, truncated: bool = False) -> dict[str, Any]:
    _deck_row(svc, deck_id)
    ts = svc.clock()
    cur = svc.db.execute(
        "INSERT INTO sources(deck_id, title, kind, chars, text, sha256, truncated, created_ts) VALUES (?,?,?,?,?,?,?,?)",
        (deck_id, title or "", kind, len(text), text, sha256_hex(text), 1 if truncated else 0, ts))
    svc.db.execute("UPDATE decks SET updated_ts = ? WHERE id = ?", (ts, deck_id))
    row = svc.db.one("SELECT * FROM sources WHERE id = ?", (cur.lastrowid,))
    return _source_dict(row)


def add_source_text(svc: Any, deck_id: str, title: str, text: str, kind: str = "text") -> dict[str, Any]:
    from .extract import MAX_TEXT_CHARS, normalize_text

    text = normalize_text(text)
    if not text:
        raise CiceroError("The source text is empty.")
    truncated = len(text) > MAX_TEXT_CHARS
    return _insert_source(svc, deck_id, title.strip() or "Text", kind if kind in ("text", "markdown") else "text", text[:MAX_TEXT_CHARS], truncated)


def add_source_file(svc: Any, deck_id: str, data: bytes, filename: str) -> dict[str, Any]:
    _deck_row(svc, deck_id)
    extracted = extract_bytes(data, filename, max_bytes=svc.config.max_upload_bytes)
    return _insert_source(svc, deck_id, extracted.title, extracted.kind, extracted.text, extracted.truncated)


def add_source_path(svc: Any, deck_id: str, path: str) -> dict[str, Any]:
    """A local file the user names explicitly; only the document types above, and only inside CICERO_FILE_ROOTS when set."""
    p = Path(path).expanduser()
    try:
        p = p.resolve(strict=True)
    except OSError:
        raise CiceroError(f"File not found: {path}") from None
    if not p.is_file():
        raise CiceroError(f"Not a file: {path}")
    if p.suffix.lower() not in FILE_SUFFIXES:
        raise Refused(f"Only {', '.join(FILE_SUFFIXES)} files can be added; got {p.suffix or 'no extension'}.")
    roots = svc.config.file_roots
    if roots and not any(root.resolve() in p.parents or root.resolve() == p for root in roots):
        raise Refused("That file is outside the folders allowed by CICERO_FILE_ROOTS.")
    if p.stat().st_size > svc.config.max_upload_bytes:
        raise CiceroError(f"The file is larger than {svc.config.max_upload_bytes // (1024 * 1024)} MB.")
    kind_for(p.name)
    return add_source_file(svc, deck_id, p.read_bytes(), p.name)


def list_sources(svc: Any, deck_id: str) -> dict[str, Any]:
    _deck_row(svc, deck_id)
    return {"items": [_source_dict(r) for r in svc.db.query("SELECT * FROM sources WHERE deck_id = ? ORDER BY id", (deck_id,))]}


def get_source(svc: Any, deck_id: str, source_id: int, *, offset: int = 0, max_chars: Optional[int] = None) -> dict[str, Any]:
    row = svc.db.one("SELECT * FROM sources WHERE id = ? AND deck_id = ?", (source_id, deck_id))
    if row is None:
        raise NotFound(f"Source {source_id} not found in this deck.")
    text = row["text"]
    out = _source_dict(row)
    chunk = text[offset:] if max_chars is None else text[offset: offset + max_chars]
    out.update(text=chunk, offset=offset, has_more=offset + len(chunk) < len(text))
    return out


def source_texts(svc: Any, deck_id: str) -> list[dict[str, Any]]:
    """Full text of every source (for generation and the number check)."""
    return [{"id": r["id"], "title": r["title"], "kind": r["kind"], "text": r["text"]}
            for r in svc.db.query("SELECT id, title, kind, text FROM sources WHERE deck_id = ? ORDER BY id", (deck_id,))]


def remove_source(svc: Any, deck_id: str, source_id: int) -> dict[str, Any]:
    row = svc.db.one("SELECT id FROM sources WHERE id = ? AND deck_id = ?", (source_id, deck_id))
    if row is None:
        raise NotFound(f"Source {source_id} not found in this deck.")
    with svc.db.transaction() as conn:
        conn.execute("DELETE FROM sources WHERE id = ?", (source_id,))
        for s in conn.execute("SELECT id, sources FROM slides WHERE deck_id = ?", (deck_id,)).fetchall():
            ids = jload(s["sources"], [])
            if source_id in ids:
                conn.execute("UPDATE slides SET sources = ? WHERE id = ?", (jdump([i for i in ids if i != source_id]), s["id"]))
        conn.execute("UPDATE decks SET updated_ts = ? WHERE id = ?", (svc.clock(), deck_id))
    return {"deleted": True, "id": source_id}


# ---------------- outline ----------------

def set_outline(svc: Any, deck_id: str, items: list[OutlineItemIn | dict[str, Any]], *, model_used: Optional[str] = None,
                set_model: bool = False) -> dict[str, Any]:
    _deck_row(svc, deck_id)
    clean: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        data = item.model_dump() if hasattr(item, "model_dump") else dict(item)
        item_id = data.get("id") or new_id()
        if item_id in seen:
            item_id = new_id()
        seen.add(item_id)
        entry = {"id": item_id, "title": data["title"], "purpose": data.get("purpose", ""), "points": list(data.get("points") or [])}
        if data.get("layout_hint") in LAYOUTS:
            entry["layout_hint"] = data["layout_hint"]
        clean.append(entry)
    with svc.db.transaction() as conn:
        conn.execute("UPDATE decks SET outline = ?, updated_ts = ? WHERE id = ?", (jdump(clean), svc.clock(), deck_id))
        if set_model:
            conn.execute("UPDATE decks SET model_used = ? WHERE id = ?", (model_used, deck_id))
    _refresh_status(svc, deck_id, touch=False)
    return deck_view(svc, deck_id)


# ---------------- slides ----------------

def _slide_row(svc: Any, deck_id: str, slide_id: str) -> Any:
    row = svc.db.one("SELECT * FROM slides WHERE id = ? AND deck_id = ?", (slide_id, deck_id))
    if row is None:
        raise NotFound(f"Slide {slide_id} not found in this deck.")
    return row


def get_slide(svc: Any, deck_id: str, slide_id: str) -> dict[str, Any]:
    return _slide_dict(_slide_row(svc, deck_id, slide_id))


def _write_revision(svc: Any, slide_id: str, reason: str) -> None:
    row = svc.db.one("SELECT * FROM slides WHERE id = ?", (slide_id,))
    snapshot = _slide_dict(row)
    svc.db.execute("INSERT OR REPLACE INTO revisions(slide_id, revision, created_ts, reason, snapshot) VALUES (?,?,?,?,?)",
                   (slide_id, row["revision"], svc.clock(), reason, jdump(snapshot)))


def _check_blocks(svc: Any, deck_id: str, blocks: list[dict[str, Any]]) -> None:
    for b in blocks:
        if b.get("type") == "image":
            if svc.db.one("SELECT 1 FROM assets WHERE id = ? AND deck_id = ?", (b["asset_id"], deck_id)) is None:
                raise CiceroError(f"Image asset {b['asset_id']} does not belong to this deck; upload it first.")


def _check_sources(svc: Any, deck_id: str, ids: list[int]) -> list[int]:
    known = {r["id"] for r in svc.db.query("SELECT id FROM sources WHERE deck_id = ?", (deck_id,))}
    bad = [i for i in ids if i not in known]
    if bad:
        raise CiceroError(f"Unknown source id(s) for this deck: {bad}.")
    return list(dict.fromkeys(ids))


def _norm_blocks(blocks: Optional[list[Any]]) -> list[dict[str, Any]]:
    return dump_blocks(blocks or [])


def add_slide(svc: Any, deck_id: str, *, after_id: Optional[str] = None, layout: str = "bullets", title: str = "", subtitle: Optional[str] = None,
              blocks: Optional[list[Any]] = None, notes: str = "", sources: Optional[list[int]] = None, image_prompt: Optional[str] = None,
              outline_id: Optional[str] = None, reason: str = "edited", position: Optional[int] = None) -> dict[str, Any]:
    _deck_row(svc, deck_id)
    dumped = _norm_blocks(blocks)
    _check_blocks(svc, deck_id, dumped)
    source_ids = _check_sources(svc, deck_id, sources or [])
    count = svc.db.one("SELECT COUNT(*) c FROM slides WHERE deck_id = ?", (deck_id,))["c"]
    if position is not None:
        pos = max(1, min(count + 1, position))
    elif after_id:
        pos = _slide_row(svc, deck_id, after_id)["position"] + 1
    else:
        pos = count + 1
    ts = svc.clock()
    slide_id = new_id()
    with svc.db.transaction() as conn:
        conn.execute("UPDATE slides SET position = position + 1 WHERE deck_id = ? AND position >= ?", (deck_id, pos))
        conn.execute(
            "INSERT INTO slides(id, deck_id, position, layout, title, subtitle, blocks, notes, status, revision, sources, image_prompt, outline_id, created_ts, updated_ts) "
            "VALUES (?,?,?,?,?,?,?,?, 'draft', 1, ?,?,?,?,?)",
            (slide_id, deck_id, pos, layout, title, subtitle, jdump(dumped), notes, jdump(source_ids), image_prompt, outline_id, ts, ts))
    _write_revision(svc, slide_id, reason)
    _refresh_status(svc, deck_id)
    return get_slide(svc, deck_id, slide_id)


def add_slide_batch(svc: Any, deck_id: str, batch_key: str, slides: list[dict[str, Any]]) -> dict[str, Any]:
    """Append drafts atomically; retrying the same batch returns its real IDs."""
    digest = sha256_hex(jdump(slides))
    with svc.db.transaction() as conn:
        _deck_row(svc, deck_id)
        receipt = conn.execute("SELECT * FROM slide_batches WHERE deck_id=? AND batch_key=?",
                               (deck_id, batch_key)).fetchone()
        if receipt:
            if receipt['payload_sha256'] != digest:
                raise CiceroError("This batch_key already names different content; choose a new batch_key.")
            ids = jload(receipt['slide_ids'], [])
            current = [get_slide(svc, deck_id, sid) for sid in ids]
            return {"deck_id": deck_id, "batch_key": batch_key, "replayed": True, "slides": current}
        count = conn.execute("SELECT COUNT(*) FROM slides WHERE deck_id=?", (deck_id,)).fetchone()[0]
        if not slides or count + len(slides) > MAX_SLIDES:
            raise CiceroError(f"A batch must be nonempty and the deck may contain at most {MAX_SLIDES} slides.")
        created = [add_slide(svc, deck_id, **slide) for slide in slides]
        conn.execute("INSERT INTO slide_batches VALUES (?,?,?,?)",
                     (deck_id, batch_key, digest, jdump([s['id'] for s in created])))
    return {"deck_id": deck_id, "batch_key": batch_key, "replayed": False, "slides": created}


def patch_slide(svc: Any, deck_id: str, slide_id: str, patch: dict[str, Any], *, reason: str = "edited") -> dict[str, Any]:
    """Apply a partial edit; the slide gets a new revision and goes back to draft."""
    row = _slide_row(svc, deck_id, slide_id)
    fields: dict[str, Any] = {}
    for key in SLIDE_FIELDS:
        if key in patch and patch[key] is not None:
            fields[key] = patch[key]
    if "blocks" in fields:
        fields["blocks"] = _norm_blocks(fields["blocks"])
        _check_blocks(svc, deck_id, fields["blocks"])
    if "sources" in fields:
        fields["sources"] = _check_sources(svc, deck_id, fields["sources"])
    if not fields:
        raise CiceroError("Nothing to change: pass at least one of title, subtitle, layout, blocks, notes, image_prompt.")
    if "layout" in fields and fields["layout"] not in LAYOUTS:
        raise CiceroError(f"Unknown layout {fields['layout']!r}.")
    sets, params = [], []
    for key, value in fields.items():
        sets.append(f"{key} = ?")
        params.append(jdump(value) if key in ("blocks", "sources") else value)
    with svc.db.transaction() as conn:
        conn.execute(f"UPDATE slides SET {', '.join(sets)}, status = 'draft', revision = revision + 1, updated_ts = ? WHERE id = ?",
                     (*params, svc.clock(), slide_id))
    _write_revision(svc, slide_id, reason)
    _refresh_status(svc, deck_id)
    return get_slide(svc, deck_id, slide_id)


def delete_slide(svc: Any, deck_id: str, slide_id: str) -> dict[str, Any]:
    _slide_row(svc, deck_id, slide_id)
    with svc.db.transaction() as conn:
        conn.execute("DELETE FROM slides WHERE id = ?", (slide_id,))
    _renumber(svc, deck_id)
    _refresh_status(svc, deck_id)
    return {"deleted": True, "id": slide_id}


def reorder_slides(svc: Any, deck_id: str, order: list[str]) -> dict[str, Any]:
    _deck_row(svc, deck_id)
    current = [r["id"] for r in svc.db.query("SELECT id FROM slides WHERE deck_id = ? ORDER BY position", (deck_id,))]
    if len(set(order)) != len(order):
        raise CiceroError("The order lists a slide more than once.")
    if set(order) != set(current):
        raise CiceroError("The order must list every slide of the deck exactly once.")
    with svc.db.transaction() as conn:
        for i, sid in enumerate(order, start=1):
            conn.execute("UPDATE slides SET position = ? WHERE id = ?", (i, sid))
        conn.execute("UPDATE decks SET updated_ts = ? WHERE id = ?", (svc.clock(), deck_id))
    return deck_view(svc, deck_id)


def set_approval(svc: Any, deck_id: str, slide_id: str, approved: bool) -> dict[str, Any]:
    _slide_row(svc, deck_id, slide_id)
    svc.db.execute("UPDATE slides SET status = ?, updated_ts = ? WHERE id = ?", ("approved" if approved else "draft", svc.clock(), slide_id))
    _refresh_status(svc, deck_id)
    return get_slide(svc, deck_id, slide_id)


def list_revisions(svc: Any, deck_id: str, slide_id: str) -> dict[str, Any]:
    _slide_row(svc, deck_id, slide_id)
    rows = svc.db.query("SELECT * FROM revisions WHERE slide_id = ? ORDER BY revision DESC", (slide_id,))
    return {"items": [{"slide_id": slide_id, "revision": r["revision"], "created_at": iso_stamp(r["created_ts"]), "reason": r["reason"],
                       "snapshot": jload(r["snapshot"], {})} for r in rows]}


def revert_slide(svc: Any, deck_id: str, slide_id: str, revision: int) -> dict[str, Any]:
    row = _slide_row(svc, deck_id, slide_id)
    target = svc.db.one("SELECT snapshot FROM revisions WHERE slide_id = ? AND revision = ?", (slide_id, revision))
    if target is None:
        raise NotFound(f"Revision {revision} of slide {slide_id} does not exist.")
    if revision == row["revision"]:
        raise CiceroError(f"Revision {revision} is already the current one.")
    snap = jload(target["snapshot"], {})
    patch = {k: snap.get(k) for k in ("layout", "title", "subtitle", "blocks", "notes", "image_prompt")}
    patch["sources"] = [i for i in snap.get("sources", []) if svc.db.one("SELECT 1 FROM sources WHERE id = ? AND deck_id = ?", (i, deck_id))]
    # a snapshot can name images or sources that no longer exist; keep only what is still there
    patch["blocks"] = [b for b in (patch["blocks"] or []) if b.get("type") != "image" or svc.db.one("SELECT 1 FROM assets WHERE id = ?", (b.get("asset_id"),))]
    with svc.db.transaction() as conn:
        conn.execute(
            "UPDATE slides SET layout = ?, title = ?, subtitle = ?, blocks = ?, notes = ?, sources = ?, image_prompt = ?, status = 'draft', "
            "revision = revision + 1, updated_ts = ? WHERE id = ?",
            (patch["layout"] or "bullets", patch["title"] or "", patch["subtitle"], jdump(patch["blocks"]), patch["notes"] or "",
             jdump(patch["sources"]), patch["image_prompt"], svc.clock(), slide_id))
    _write_revision(svc, slide_id, "reverted")
    _refresh_status(svc, deck_id)
    return get_slide(svc, deck_id, slide_id)


# ---------------- restoring state (undo of an agent session) ----------------

SLIDE_CONTENT_FIELDS = ("layout", "title", "subtitle", "blocks", "notes", "sources", "image_prompt", "status")


def slide_etag(slide: dict[str, Any]) -> str:
    """A fingerprint of what a slide says (not of its revision number or position): two states with the same text, blocks, sources
    and approval have the same etag, so undoing the newest of two edits gives back the etag the older one left."""
    content = {key: slide.get(key) for key in SLIDE_CONTENT_FIELDS}
    return sha256_hex(json.dumps(content, sort_keys=True, ensure_ascii=False, separators=(",", ":")))[:16]


def restore_slide(svc: Any, deck_id: str, slide_id: str, state: dict[str, Any], *, reason: str = "restored") -> dict[str, Any]:
    """Put a slide back to ``state`` (a slide as ``get_slide`` returned it earlier), as a new revision. Pictures and sources that
    no longer exist are left out, as ``revert_slide`` does."""
    _slide_row(svc, deck_id, slide_id)
    blocks = [b for b in (state.get("blocks") or [])
              if b.get("type") != "image" or svc.db.one("SELECT 1 FROM assets WHERE id = ?", (b.get("asset_id"),))]
    sources = [i for i in (state.get("sources") or []) if svc.db.one("SELECT 1 FROM sources WHERE id = ? AND deck_id = ?", (i, deck_id))]
    status = "approved" if state.get("status") == "approved" else "draft"
    with svc.db.transaction() as conn:
        conn.execute(
            "UPDATE slides SET layout = ?, title = ?, subtitle = ?, blocks = ?, notes = ?, sources = ?, image_prompt = ?, status = ?, "
            "revision = revision + 1, updated_ts = ? WHERE id = ?",
            (state.get("layout") or "bullets", state.get("title") or "", state.get("subtitle"), jdump(blocks), state.get("notes") or "",
             jdump(sources), state.get("image_prompt"), status, svc.clock(), slide_id))
    _write_revision(svc, slide_id, reason)
    _refresh_status(svc, deck_id)
    return get_slide(svc, deck_id, slide_id)


def reinsert_slide(svc: Any, deck_id: str, state: dict[str, Any], *, reason: str = "restored") -> dict[str, Any]:
    """Bring a deleted slide back with its id, at its old position (its older revisions are gone with the delete)."""
    _deck_row(svc, deck_id)
    if svc.db.one("SELECT 1 FROM slides WHERE id = ?", (state["id"],)) is not None:
        raise CiceroError(f"Slide {state['id']} exists already.", code="conflict")
    count = svc.db.one("SELECT COUNT(*) c FROM slides WHERE deck_id = ?", (deck_id,))["c"]
    position = max(1, min(count + 1, int(state.get("position") or count + 1)))
    sources = [i for i in (state.get("sources") or []) if svc.db.one("SELECT 1 FROM sources WHERE id = ? AND deck_id = ?", (i, deck_id))]
    blocks = [b for b in (state.get("blocks") or [])
              if b.get("type") != "image" or svc.db.one("SELECT 1 FROM assets WHERE id = ?", (b.get("asset_id"),))]
    ts = svc.clock()
    with svc.db.transaction() as conn:
        conn.execute("UPDATE slides SET position = position + 1 WHERE deck_id = ? AND position >= ?", (deck_id, position))
        conn.execute(
            "INSERT INTO slides(id, deck_id, position, layout, title, subtitle, blocks, notes, status, revision, sources, image_prompt, outline_id, created_ts, updated_ts) "
            "VALUES (?,?,?,?,?,?,?,?,?,1,?,?,?,?,?)",
            (state["id"], deck_id, position, state.get("layout") or "bullets", state.get("title") or "", state.get("subtitle"), jdump(blocks),
             state.get("notes") or "", "approved" if state.get("status") == "approved" else "draft", jdump(sources), state.get("image_prompt"),
             state.get("outline_id"), ts, ts))
    _write_revision(svc, state["id"], reason)
    _refresh_status(svc, deck_id)
    return get_slide(svc, deck_id, state["id"])


def reinsert_source(svc: Any, deck_id: str, row: dict[str, Any], citing: dict[str, list[int]]) -> dict[str, Any]:
    """Bring a removed source back with its id and text, and the references the slides that cited it had."""
    _deck_row(svc, deck_id)
    if svc.db.one("SELECT 1 FROM sources WHERE id = ?", (row["id"],)) is not None:
        raise CiceroError(f"Source {row['id']} exists already.", code="conflict")
    with svc.db.transaction() as conn:
        conn.execute("INSERT INTO sources(id, deck_id, title, kind, chars, text, sha256, truncated, created_ts) VALUES (?,?,?,?,?,?,?,?,?)",
                     (row["id"], deck_id, row["title"], row["kind"], row["chars"], row["text"], row["sha256"], row["truncated"], row["created_ts"]))
        for slide_id, ids in citing.items():
            current = conn.execute("SELECT sources FROM slides WHERE id = ? AND deck_id = ?", (slide_id, deck_id)).fetchone()
            if current is None:
                continue
            have = jload(current["sources"], [])
            if row["id"] not in have:
                known = {r["id"] for r in conn.execute("SELECT id FROM sources WHERE deck_id = ?", (deck_id,)).fetchall()}
                conn.execute("UPDATE slides SET sources = ? WHERE id = ?", (jdump([i for i in ids if i in known]), slide_id))
        conn.execute("UPDATE decks SET updated_ts = ? WHERE id = ?", (svc.clock(), deck_id))
    return _source_dict(svc.db.one("SELECT * FROM sources WHERE id = ?", (row["id"],)))


def delete_batch_receipt(svc: Any, deck_id: str, batch_key: str) -> None:
    """Forget a ``slides_add`` batch, so that a retry with its key adds the slides again instead of replaying ids that no longer exist."""
    svc.db.execute("DELETE FROM slide_batches WHERE deck_id = ? AND batch_key = ?", (deck_id, batch_key))


# ---------------- assets ----------------

def add_asset(svc: Any, deck_id: str, data: bytes, filename: str = "") -> dict[str, Any]:
    from PIL import Image, ImageOps, UnidentifiedImageError

    _deck_row(svc, deck_id)
    if not data:
        raise CiceroError("The image is empty.")
    if len(data) > svc.config.max_image_bytes:
        raise CiceroError(f"The image is larger than {svc.config.max_image_bytes // (1024 * 1024)} MB.")
    try:
        probe = Image.open(io.BytesIO(data))
        fmt = probe.format or ""
        probe.verify()
        img = Image.open(io.BytesIO(data))
        img.load()
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError, Image.DecompressionBombError) as error:
        raise CiceroError(f"The file is not a valid image: {error}") from error
    if fmt not in IMAGE_FORMATS:
        raise CiceroError(f"Only PNG, JPEG and WEBP images are accepted; got {fmt or 'an unknown format'}.")
    if img.width * img.height > MAX_IMAGE_PIXELS:
        raise CiceroError("The image has more than 50 megapixels.")
    mime, ext = IMAGE_FORMATS[fmt]
    orientation = img.getexif().get(0x0112, 1) if hasattr(img, "getexif") else 1
    if orientation not in (1, None):  # bake the EXIF rotation in: python-pptx ignores it
        fixed = ImageOps.exif_transpose(img)
        buf = io.BytesIO()
        fixed.save(buf, format=fmt, **({"quality": 92} if fmt in ("JPEG", "WEBP") else {}))
        data, img = buf.getvalue(), fixed
    digest = sha256_hex(data)
    with svc.db.transaction():
        existing = svc.db.one('SELECT * FROM assets WHERE deck_id=? AND sha256=? ORDER BY created_ts,id LIMIT 1', (deck_id, digest))
        if existing is not None and asset_info(svc, existing['id']) is not None:
            return {'asset_id':existing['id'], 'width':existing['width'], 'height':existing['height'],
                    'mime':existing['mime'], 'bytes':existing['bytes'], 'reused':True}
        asset_id = new_id()
        svc.config.assets_dir.mkdir(parents=True, exist_ok=True)
        write_bytes_atomic(svc.config.assets_dir / f"{asset_id}.{ext}", data, fsync=False)
        svc.db.execute("INSERT INTO assets(id, deck_id, filename, mime, ext, width, height, bytes, sha256, created_ts) VALUES (?,?,?,?,?,?,?,?,?,?)",
                       (asset_id, deck_id, clip(filename, 200), mime, ext, img.width, img.height, len(data), digest, svc.clock()))
    return {"asset_id": asset_id, "width": img.width, "height": img.height, "mime": mime, "bytes": len(data)}


def add_svg_asset(svc: Any, deck_id: str, data: bytes, filename: str = "vector.svg", *, fallback_png: bytes = b"", native_data: bytes = b"") -> dict[str, Any]:
    """Store a checked SVG as a normal deck image asset for browser and PPTX use."""
    import xml.etree.ElementTree as ET
    _deck_row(svc, deck_id)
    if not data or len(data) > svc.config.max_image_bytes:
        raise CiceroError("The SVG is empty or exceeds the image size limit.")
    try:
        root = ET.fromstring(data)
    except ET.ParseError as error:
        raise CiceroError(f"The SVG is not valid XML: {error}") from error
    if root.tag.rsplit("}", 1)[-1].lower() != "svg":
        raise CiceroError("The vector file must have an SVG root element.")
    if fallback_png:
        from PIL import Image, UnidentifiedImageError
        try:
            image = Image.open(io.BytesIO(fallback_png)); image.verify()
            if image.format != "PNG": raise CiceroError("The SVG fallback must be a PNG image.")
        except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as error:
            raise CiceroError(f"The SVG fallback is not a valid PNG: {error}") from error
    forbidden = {"script", "foreignobject", "iframe", "audio", "video"}
    for element in root.iter():
        tag = element.tag.rsplit("}", 1)[-1].lower()
        if tag in forbidden or any(k.lower().startswith("on") for k in element.attrib):
            raise CiceroError("The SVG contains active content and cannot be embedded.")
        for key, value in element.attrib.items():
            if key.rsplit("}", 1)[-1].lower() in {"href", "src"} and not value.startswith("#"):
                raise CiceroError("The SVG contains an external resource reference.")
    width = _svg_dimension(root.attrib.get("width"), 512)
    height = _svg_dimension(root.attrib.get("height"), 384)
    digest = sha256_hex(data)
    with svc.db.transaction():
        existing = svc.db.one("SELECT * FROM assets WHERE deck_id=? AND sha256=? ORDER BY created_ts,id LIMIT 1", (deck_id, digest))
        if existing is not None and asset_info(svc, existing["id"]) is not None:
            asset_path = svc.config.assets_dir / f"{existing['id']}.svg"
            if fallback_png and not asset_path.with_suffix(".png").is_file(): write_bytes_atomic(asset_path.with_suffix(".png"), fallback_png, fsync=False)
            if native_data and not asset_path.with_suffix(".vectorcraft").is_file(): write_bytes_atomic(asset_path.with_suffix(".vectorcraft"), native_data, fsync=False)
            return {"asset_id": existing["id"], "width": existing["width"], "height": existing["height"], "mime": existing["mime"], "bytes": existing["bytes"], "reused": True}
        asset_id = new_id()
        svc.config.assets_dir.mkdir(parents=True, exist_ok=True)
        asset_path = svc.config.assets_dir / f"{asset_id}.svg"
        try:
            write_bytes_atomic(asset_path, data, fsync=False)
            if fallback_png: write_bytes_atomic(asset_path.with_suffix(".png"), fallback_png, fsync=False)
            if native_data: write_bytes_atomic(asset_path.with_suffix(".vectorcraft"), native_data, fsync=False)
        except Exception:
            asset_path.unlink(missing_ok=True)
            asset_path.with_suffix(".png").unlink(missing_ok=True)
            asset_path.with_suffix(".vectorcraft").unlink(missing_ok=True)
            raise
        svc.db.execute("INSERT INTO assets(id,deck_id,filename,mime,ext,width,height,bytes,sha256,created_ts) VALUES (?,?,?,?,?,?,?,?,?,?)",
                       (asset_id, deck_id, clip(filename, 200), "image/svg+xml", "svg", width, height, len(data), digest, svc.clock()))
    return {"asset_id": asset_id, "width": width, "height": height, "mime": "image/svg+xml", "bytes": len(data)}


def _svg_dimension(value: Any, default: int) -> int:
    import re
    match = re.match(r"^\s*(\d+(?:\.\d+)?)", str(value or ""))
    number = float(match.group(1)) if match else float(default)
    if not 1 <= number <= 20000:
        raise CiceroError("The SVG dimensions must be between 1 and 20000.")
    return round(number)


def asset_info(svc: Any, asset_id: str) -> Optional[dict[str, Any]]:
    row = svc.db.one("SELECT * FROM assets WHERE id = ?", (asset_id,))
    if row is None:
        return None
    path = svc.config.assets_dir / f"{row['id']}.{row['ext']}"
    if not path.is_file():
        return None
    result = {"id": row["id"], "deck_id": row["deck_id"], "width": row["width"], "height": row["height"], "mime": row["mime"], "path": path}
    if row["ext"] == "svg":
        fallback = path.with_suffix(".png")
        if fallback.is_file(): result["fallback_path"] = fallback
        native = path.with_suffix(".vectorcraft")
        if native.is_file(): result["native_path"] = native
    return result


# ---------------- exports ----------------

def add_export(svc: Any, deck_id: str, fmt: str, data: bytes, title: str) -> dict[str, Any]:
    _deck_row(svc, deck_id)
    export_id = new_id()
    filename = f"{slugify(title)}.{fmt}"
    folder = svc.config.exports_dir / export_id
    folder.mkdir(parents=True, exist_ok=True)
    write_bytes_atomic(folder / filename, data, fsync=False)
    svc.db.execute("INSERT INTO exports(id, deck_id, format, filename, bytes, sha256, created_ts) VALUES (?,?,?,?,?,?,?)",
                   (export_id, deck_id, fmt, filename, len(data), sha256_hex(data), svc.clock()))
    return export_view(svc, svc.db.one("SELECT * FROM exports WHERE id = ?", (export_id,)))


def export_view(svc: Any, row: Any) -> dict[str, Any]:
    return {"id": row["id"], "deck_id": row["deck_id"], "format": row["format"], "filename": row["filename"], "bytes": row["bytes"],
            "sha256": row["sha256"], "created_at": iso_stamp(row["created_ts"]), "url": f"/api/exports/{row['id']}/file"}


def list_exports(svc: Any, deck_id: str) -> dict[str, Any]:
    _deck_row(svc, deck_id)
    rows = svc.db.query("SELECT * FROM exports WHERE deck_id = ? ORDER BY created_ts DESC, id", (deck_id,))
    return {"items": [export_view(svc, r) for r in rows]}


def export_file(svc: Any, export_id: str) -> tuple[Path, dict[str, Any]]:
    row = svc.db.one("SELECT * FROM exports WHERE id = ?", (export_id,))
    if row is None:
        raise NotFound(f"Export {export_id} not found.")
    path = svc.config.exports_dir / row["id"] / row["filename"]
    if not path.is_file():
        raise NotFound("The exported file is no longer on disk.")
    return path, export_view(svc, row)
