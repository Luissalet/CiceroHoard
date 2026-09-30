"""Deck review: numbers that no source contains, sizes, notes, charts."""
from __future__ import annotations

from cicero_hoard import check, decks
from conftest import new_deck, png_bytes


def kinds(issues, slide_id=None):
    return {i["kind"] for i in issues if slide_id is None or i["slide_id"] == slide_id}


def test_number_variants_match_regional_formats():
    assert 1234.0 in check.number_variants("1.234") and 1234.0 in check.number_variants("1,234")
    assert 1234.5 in check.number_variants("1.234,5") and 1.5 in check.number_variants("1,5")
    assert 12.0 in check.number_variants("12")


def test_significant_numbers_skip_single_digits():
    text = "En 2021 abrimos. Somos 45 empleados y crecimos un 12%. Hay 3 tiendas."
    found = [t for t, _ in check.significant_numbers(text)]
    assert "45" in found and any("12" in t for t in found)
    assert "3" not in found


def test_unsourced_detects_only_missing_numbers():
    ref = check.all_number_values(["Las ventas fueron de 1.250.000 euros y crecieron un 12%."])
    assert check.unsourced("Ventas de 1.250.000", ref) == []
    assert check.unsourced("Ventas de 1,25 millones", ref) == ["1,25"]  # derived figures are flagged too
    assert check.unsourced("Ventas de 999 euros", ref) == ["999"]
    assert check.unsourced("Un 12,0% más", ref) == []


def test_deck_check_flags_invented_numbers(services):
    from conftest import SOURCE_TEXT

    d = new_deck(services)
    decks.add_source_text(services, d["id"], "Informe", SOURCE_TEXT)
    ok = decks.add_slide(services, d["id"], title="Ventas", blocks=[{"type": "bullets", "items": ["Ventas de 1.250.000 euros", "Un 12% más"]}], notes="n")
    bad = decks.add_slide(services, d["id"], title="Inventado", blocks=[{"type": "bullets", "items": ["Ventas de 987.654 euros"]}], notes="n")
    issues = services.check(d["id"])["issues"]
    assert "unsourced_numbers" not in kinds(issues, ok["id"]) and "unsourced_numbers" in kinds(issues, bad["id"])
    msg = next(i for i in issues if i["kind"] == "unsourced_numbers")["message"]
    assert "987" in msg


def test_no_source_means_no_number_check(services):
    d = new_deck(services)
    s = decks.add_slide(services, d["id"], title="x", blocks=[{"type": "bullets", "items": ["Cifra 987.654"]}], notes="n")
    assert "unsourced_numbers" not in kinds(services.check(d["id"])["issues"], s["id"])


def test_chart_values_must_be_sourced(services):
    from conftest import SOURCE_TEXT

    d = new_deck(services)
    decks.add_source_text(services, d["id"], "Informe", SOURCE_TEXT)
    chart = {"type": "chart", "chart": "bar", "title": "T", "categories": ["A", "B"], "series": [{"name": "s", "values": [8400, 4242]}]}
    s = decks.add_slide(services, d["id"], layout="chart", title="Gráfico", blocks=[chart], notes="n")
    issues = services.check(d["id"])["issues"]
    msg = next(i for i in issues if i["kind"] == "unsourced_chart" and i["slide_id"] == s["id"])["message"]
    assert "4242" in msg and "8400" not in msg


def test_structure_issues(services):
    d = new_deck(services, language="en")
    assert kinds(services.check(d["id"])["issues"]) == {"no_slides"}
    empty = decks.add_slide(services, d["id"], title="", blocks=[])
    many = decks.add_slide(services, d["id"], title="Many", blocks=[{"type": "bullets", "items": [f"item {i}" for i in range(8)]}] if False else [{"type": "bullets", "items": ["a"] * 6}])
    long_bullet = decks.add_slide(services, d["id"], title="Long", blocks=[{"type": "bullets", "items": ["y" * 140]}], notes="n")
    quote_missing = decks.add_slide(services, d["id"], layout="quote", title="Q", blocks=[{"type": "text", "text": "hi"}], notes="n")
    mismatch = decks.add_slide(services, d["id"], layout="chart", title="C", notes="n",
                               blocks=[{"type": "chart", "chart": "bar", "title": "t", "categories": ["a", "b"], "series": [{"name": "s", "values": [1]}]}])
    img = decks.add_slide(services, d["id"], layout="image_text", title="I", notes="n", image_prompt="a bridge", blocks=[{"type": "bullets", "items": ["a"]}])
    issues = services.check(d["id"])["issues"]
    assert {"empty_slide", "missing_notes"} <= kinds(issues, empty["id"])
    assert "long_bullet" in kinds(issues, long_bullet["id"])
    assert "layout_content" in kinds(issues, quote_missing["id"])
    assert "chart_mismatch" in kinds(issues, mismatch["id"])
    assert "image_prompt_only" in kinds(issues, img["id"])
    assert "not_approved" in kinds(issues, many["id"])
    assert all(i["message"] for i in issues)
    assert any("Not approved" in i["message"] for i in issues)  # English deck, English messages


def test_approved_slide_with_notes_is_clean(services):
    d = new_deck(services)
    s = decks.add_slide(services, d["id"], title="Limpia", blocks=[{"type": "bullets", "items": ["Uno", "Dos"]}], notes="Notas.")
    decks.set_approval(services, d["id"], s["id"], True)
    assert kinds(services.check(d["id"])["issues"], s["id"]) == set()


def test_overflow_is_reported(services):
    d = new_deck(services)
    s = decks.add_slide(services, d["id"], title="Denso", blocks=[{"type": "text", "text": "palabra " * 1200}], notes="n")
    issues = services.check(d["id"])["issues"]
    assert kinds(issues, s["id"]) & {"overflow", "overflow_risk"}


def test_missing_image_is_reported(services):
    d = new_deck(services)
    asset = decks.add_asset(services, d["id"], png_bytes())
    s = decks.add_slide(services, d["id"], layout="image_text", title="Foto", notes="n",
                        blocks=[{"type": "bullets", "items": ["a"]}, {"type": "image", "asset_id": asset["asset_id"]}])
    assert "image_missing" not in kinds(services.check(d["id"])["issues"], s["id"])
    services.db.execute("DELETE FROM assets WHERE id = ?", (asset["asset_id"],))
    assert "image_missing" in kinds(services.check(d["id"])["issues"], s["id"])
