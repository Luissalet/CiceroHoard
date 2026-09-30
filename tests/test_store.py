"""The deck store: decks, status transitions, revisions, slides, sources, assets."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from cicero_hoard import decks
from cicero_hoard.errors import CiceroError, NotFound
from cicero_hoard.models import (ChartBlock, ChartSeries, DeckCreate, DeckPatch, ImageBlock, BulletsBlock, OutlineItemIn, SlidePatch, TextBlock)
from conftest import new_deck, png_bytes


def test_create_list_update_delete(services):
    d = new_deck(services, title="Uno", language="en")
    assert d["status"] == "draft" and d["language"] == "en" and d["theme"] == "claro" and d["ref"] == f"hoard://cicero/deck/{d['id']}"
    assert d["sources"] == [] and d["outline"] == [] and d["slides"] == [] and d["model_used"] is None
    assert decks.list_decks(services)["items"][0] == {"id": d["id"], "title": "Uno", "status": "draft", "language": "en", "slides": 0, "approved": 0,
                                                       "updated_at": d["updated_at"], "theme": "claro"}
    upd = decks.update_deck(services, d["id"], DeckPatch(tone="cercano", slide_count=12, theme="oscuro"))
    assert upd["tone"] == "cercano" and upd["slide_count"] == 12 and upd["theme"] == "oscuro"
    with pytest.raises(CiceroError):
        decks.update_deck(services, d["id"], DeckPatch(theme="nope"))
    with pytest.raises(NotFound):
        decks.get_slide(services, d["id"], "missing")
    with pytest.raises(NotFound):
        decks.deck_view(services, "missing")


def test_default_language_comes_from_settings(services):
    services.update_settings({"default_language": "en"})
    assert new_deck(services, language=None)["language"] == "en"


def test_input_validation():
    with pytest.raises(ValidationError):
        DeckCreate(title="")
    with pytest.raises(ValidationError):
        DeckCreate(title="x", slide_count=2)
    with pytest.raises(ValidationError):
        DeckCreate(title="x", slide_count=41)
    with pytest.raises(ValidationError):
        DeckCreate(title="x", language="fr")
    with pytest.raises(ValidationError):
        DeckCreate(title="x", unknown="y")
    with pytest.raises(ValidationError):
        ChartBlock(chart="bar", categories=["a"], series=[ChartSeries(name="s", values=[float("nan")])])
    with pytest.raises(ValidationError):
        ChartBlock(chart="donut")
    with pytest.raises(ValidationError):
        BulletsBlock(items=["x"] * 13)
    with pytest.raises(ValidationError):
        SlidePatch(layout="poster")
    with pytest.raises(ValidationError):
        OutlineItemIn(title="")


def test_delete_requires_confirm_and_removes_files(services):
    d = new_deck(services)
    asset = decks.add_asset(services, d["id"], png_bytes())
    decks.add_slide(services, d["id"], title="s")
    services.export(d["id"], "md")
    export = decks.list_exports(services, d["id"])["items"][0]
    with pytest.raises(CiceroError) as info:
        decks.delete_deck(services, d["id"], False)
    assert info.value.code == "confirm_required"
    assert (services.config.assets_dir / f"{asset['asset_id']}.png").is_file()
    assert decks.delete_deck(services, d["id"], True) == {"deleted": True, "id": d["id"]}
    assert not (services.config.assets_dir / f"{asset['asset_id']}.png").exists()
    assert not (services.config.exports_dir / export["id"]).exists()
    assert services.db.one("SELECT COUNT(*) c FROM slides")["c"] == 0 and services.db.one("SELECT COUNT(*) c FROM revisions")["c"] == 0


def test_slide_revisions_and_revert(services):
    d = new_deck(services)
    s = decks.add_slide(services, d["id"], title="Original", blocks=[BulletsBlock(items=["a", "b"])], notes="nota")
    assert s["revision"] == 1 and s["status"] == "draft" and s["position"] == 1
    s2 = decks.patch_slide(services, d["id"], s["id"], {"title": "Editado", "blocks": [BulletsBlock(items=["c"])]})
    assert s2["revision"] == 2 and s2["title"] == "Editado" and s2["blocks"] == [{"type": "bullets", "items": ["c"]}]
    s3 = decks.patch_slide(services, d["id"], s["id"], {"notes": "otra nota"})
    revs = decks.list_revisions(services, d["id"], s["id"])["items"]
    assert [r["revision"] for r in revs] == [3, 2, 1] and [r["reason"] for r in revs] == ["edited", "edited", "edited"]
    assert revs[2]["snapshot"]["title"] == "Original" and revs[0]["snapshot"]["notes"] == "otra nota"
    back = decks.revert_slide(services, d["id"], s["id"], 1)
    assert back["revision"] == 4 and back["title"] == "Original" and back["blocks"] == [{"type": "bullets", "items": ["a", "b"]}] and back["notes"] == "nota"
    assert decks.list_revisions(services, d["id"], s["id"])["items"][0]["reason"] == "reverted"
    with pytest.raises(CiceroError):
        decks.revert_slide(services, d["id"], s["id"], 4)  # already current
    with pytest.raises(NotFound):
        decks.revert_slide(services, d["id"], s["id"], 99)
    with pytest.raises(CiceroError):
        decks.patch_slide(services, d["id"], s["id"], {})


def test_status_transitions_and_approval_flow(services):
    d = new_deck(services)
    assert decks.deck_view(services, d["id"])["status"] == "draft"
    decks.set_outline(services, d["id"], [OutlineItemIn(title="A", points=["x"]), OutlineItemIn(title="B")])
    assert decks.deck_view(services, d["id"])["status"] == "outline"
    a = decks.add_slide(services, d["id"], title="A")
    b = decks.add_slide(services, d["id"], title="B")
    assert decks.deck_view(services, d["id"])["status"] == "review"
    decks.set_approval(services, d["id"], a["id"], True)
    assert decks.deck_view(services, d["id"])["status"] == "review"
    approved = decks.set_approval(services, d["id"], b["id"], True)
    assert approved["status"] == "approved" and approved["revision"] == 1  # approving is not an edit
    assert decks.deck_view(services, d["id"])["status"] == "ready"
    edited = decks.patch_slide(services, d["id"], a["id"], {"title": "A2"})
    assert edited["status"] == "draft" and decks.deck_view(services, d["id"])["status"] == "review"
    assert decks.list_decks(services)["items"][0]["approved"] == 1
    decks.set_approval(services, d["id"], a["id"], True)
    decks.set_approval(services, d["id"], b["id"], False)
    assert decks.get_slide(services, d["id"], b["id"])["status"] == "draft"
    decks.delete_slide(services, d["id"], a["id"])
    decks.delete_slide(services, d["id"], b["id"])
    assert decks.deck_view(services, d["id"])["status"] == "outline"


def test_add_reorder_delete_keep_positions_contiguous(services):
    d = new_deck(services)
    s1 = decks.add_slide(services, d["id"], title="1")
    s3 = decks.add_slide(services, d["id"], title="3")
    s2 = decks.add_slide(services, d["id"], title="2", after_id=s1["id"])
    view = decks.deck_view(services, d["id"])
    assert [(s["title"], s["position"]) for s in view["slides"]] == [("1", 1), ("2", 2), ("3", 3)]
    view = decks.reorder_slides(services, d["id"], [s3["id"], s1["id"], s2["id"]])
    assert [s["title"] for s in view["slides"]] == ["3", "1", "2"]
    with pytest.raises(CiceroError):
        decks.reorder_slides(services, d["id"], [s3["id"], s1["id"]])
    with pytest.raises(CiceroError):
        decks.reorder_slides(services, d["id"], [s3["id"], s3["id"], s1["id"]])
    decks.delete_slide(services, d["id"], s1["id"])
    assert [(s["title"], s["position"]) for s in decks.deck_view(services, d["id"])["slides"]] == [("3", 1), ("2", 2)]
    with pytest.raises(NotFound):
        decks.add_slide(services, d["id"], after_id="nope")


def test_slide_fields_are_validated_against_the_deck(services):
    d, other = new_deck(services), new_deck(services, title="Otra")
    foreign = decks.add_asset(services, other["id"], png_bytes())
    s = decks.add_slide(services, d["id"], title="s")
    with pytest.raises(CiceroError):
        decks.patch_slide(services, d["id"], s["id"], {"blocks": [ImageBlock(asset_id=foreign["asset_id"])]})
    with pytest.raises(CiceroError):
        decks.patch_slide(services, d["id"], s["id"], {"sources": [999]})
    own = decks.add_asset(services, d["id"], png_bytes())
    ok = decks.patch_slide(services, d["id"], s["id"], {"blocks": [ImageBlock(asset_id=own["asset_id"], caption="c"), TextBlock(text="t")]})
    assert ok["blocks"][0] == {"type": "image", "asset_id": own["asset_id"], "caption": "c"}


def test_sources_text_and_removal_clears_slide_references(services):
    d = new_deck(services)
    src = decks.add_source_text(services, d["id"], "  Notas ", "Hola\r\n\r\n\r\n\r\nmundo", "markdown")
    assert src["title"] == "Notas" and src["kind"] == "markdown" and src["chars"] == len("Hola\n\nmundo")
    assert decks.get_source(services, d["id"], src["id"], offset=6, max_chars=100)["text"] == "mundo"
    s = decks.add_slide(services, d["id"], title="s", sources=[src["id"]])
    assert s["sources"] == [src["id"]]
    with pytest.raises(CiceroError):
        decks.add_source_text(services, d["id"], "vacío", "   ")
    decks.remove_source(services, d["id"], src["id"])
    assert decks.get_slide(services, d["id"], s["id"])["sources"] == []
    with pytest.raises(NotFound):
        decks.get_source(services, d["id"], src["id"])


def test_local_file_sources_follow_the_allowed_folders(tmp_path):
    from conftest import make_services
    allowed = tmp_path / "docs"
    allowed.mkdir()
    (allowed / "a.md").write_text("# Título\nCuerpo con texto suficiente.", encoding="utf-8")
    outside = tmp_path / "b.txt"
    outside.write_text("fuera", encoding="utf-8")
    svc = make_services(tmp_path, file_roots=(allowed,))
    d = new_deck(svc)
    assert decks.add_source_path(svc, d["id"], str(allowed / "a.md"))["title"] == "a"
    from cicero_hoard.errors import Refused
    with pytest.raises(Refused):
        decks.add_source_path(svc, d["id"], str(outside))
    (allowed / "x.exe").write_bytes(b"MZ")
    with pytest.raises(Refused):
        decks.add_source_path(svc, d["id"], str(allowed / "x.exe"))
    with pytest.raises(CiceroError):
        decks.add_source_path(svc, d["id"], str(allowed / "missing.md"))
    svc.stop()


def test_assets_are_verified_with_pillow(services):
    d = new_deck(services)
    png = decks.add_asset(services, d["id"], png_bytes(80, 40), "logo.png")
    assert (png["width"], png["height"], png["mime"]) == (80, 40, "image/png")
    assert decks.asset_info(services, png["asset_id"])["path"].is_file()
    assert decks.add_asset(services, d["id"], png_bytes(10, 10, fmt="JPEG"))["mime"] == "image/jpeg"
    assert decks.add_asset(services, d["id"], png_bytes(10, 10, fmt="WEBP"))["mime"] == "image/webp"
    with pytest.raises(CiceroError):
        decks.add_asset(services, d["id"], b"not an image at all")
    with pytest.raises(CiceroError):
        decks.add_asset(services, d["id"], b"")
    with pytest.raises(CiceroError):
        decks.add_asset(services, d["id"], png_bytes(10, 10, fmt="GIF"))
    services.config.max_image_bytes = 100
    with pytest.raises(CiceroError):
        decks.add_asset(services, d["id"], png_bytes(200, 200))


def test_exif_rotation_is_baked_in(services):
    import io
    from PIL import Image
    d = new_deck(services)
    img = Image.new("RGB", (40, 20), (10, 200, 10))
    exif = Image.Exif()
    exif[0x0112] = 6  # rotate 90 clockwise when displayed
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif)
    asset = decks.add_asset(services, d["id"], buf.getvalue())
    assert (asset["width"], asset["height"]) == (20, 40)
