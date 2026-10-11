"""Visual review: rule bookkeeping with a fake measurement, the allowed fix, the tool and routes, and one real browser run."""

from __future__ import annotations

import pytest

from cicero_hoard import decks, visual_review as vr
from cicero_hoard.agent_tools import call_tool
from cicero_hoard.errors import PdfUnavailable
from conftest import new_deck


def fake_rows(found_by_index):
    def measure(deck, *, assets, png_dir=None):
        rows = []
        for i, s in enumerate(deck["slides"]):
            rows.append({"id": s["id"], "found": [dict(f) for f in found_by_index.get(i, [])], "hasTitle": bool(s.get("title")),
                         "hasChart": False, "hasImage": False})
        return rows
    return measure


def test_review_classifies_and_adds_layout_checks():
    deck = {"slides": [{"id": "a", "title": "T", "layout": "chart", "blocks": []},
                       {"id": "b", "title": "", "layout": "bullets", "blocks": []}]}
    out = vr.review(deck, assets=lambda _: None, measure_fn=fake_rows({1: [{"rule": "contrast", "where": "x", "detail": "2.1:1 < 4.5:1"},
                                                                           {"rule": "overlap", "where": "a / b", "detail": "30%"}]}))
    assert not out["ok"] and out["errors"] == 1 and out["warnings"] == 2
    assert [f["rule"] for f in out["slides"][0]["findings"]] == ["missing_chart"]
    contrast = out["slides"][1]["findings"][0]
    assert contrast["severity"] == "error" and contrast["fix"] and contrast["auto_fix"] is False


def test_shrink_patch_only_touches_text_without_a_smaller_size():
    slide = {"blocks": [{"type": "text", "text": "x"}, {"type": "bullets", "items": ["a"], "font_size": 14},
                        {"type": "image", "asset_id": "z"}]}
    blocks = vr.shrink_patch(slide)
    assert blocks[0]["font_size"] == 14 and blocks[1]["font_size"] == 14 and "font_size" not in blocks[2]
    assert vr.shrink_patch({"blocks": [{"type": "text", "text": "x", "font_size": 14}]}) is None


def test_fix_applies_minimum_font_and_reviews_again(services):
    deck = new_deck(services)
    slide = decks.add_slide(services, deck["id"], title="Long", blocks=[{"type": "text", "text": "Mucho texto"}])
    calls = []

    def measure(d, *, assets, png_dir=None):
        calls.append(1)
        s = d["slides"][0]
        small = (s["blocks"][0].get("font_size") == vr.MIN_FONT)
        return [{"id": s["id"], "found": [] if small else [{"rule": "text_overflow", "where": "Mucho", "detail": "needs 900px", "need": 900, "have": 500}],
                 "hasTitle": True, "hasChart": False, "hasImage": False}]

    services._visual_measure_fn = measure
    first = call_tool(services, "deck_visual_review", {"deck_id": deck["id"]})
    assert not first["ok"] and first["slides"][0]["findings"][0]["auto_fix"] is True
    fixed = call_tool(services, "deck_visual_review", {"deck_id": deck["id"], "fix": True})
    assert fixed["ok"] and fixed["fixed"][0]["slide_id"] == slide["id"] and fixed["before"]["errors"] == 1
    assert decks.get_slide(services, deck["id"], slide["id"])["blocks"][0]["font_size"] == vr.MIN_FONT
    assert len(calls) == 3


def test_real_browser_review_writes_pngs_and_finds_real_problems(services, client):
    deck = new_deck(services)
    decks.add_slide(services, deck["id"], title="Fine", blocks=[{"type": "bullets", "items": ["Uno", "Dos"]}])
    decks.add_slide(services, deck["id"], title="Crowded", layout="freeform",
                    blocks=[{"type": "text", "text": "palabra " * 300, "frame": [0, 0, 0.2, 0.08]},
                            {"type": "text", "text": "encima", "frame": [0.1, 0.0, 0.5, 0.3]},
                            {"type": "text", "text": "fuera", "frame": [0.9, 0.5, 0.3, 0.1]}])
    try:
        out = services.visual_review(deck["id"])
    except PdfUnavailable:
        pytest.skip("no browser here")
    assert len(out["slides"]) == 2 and all(s["png_url"].endswith(".png") for s in out["slides"])
    assert not [f for f in out["slides"][0]["findings"] if f["severity"] == "error"]
    rules = {f["rule"] for f in out["slides"][1]["findings"]}
    # the long text grew past the bottom: overflow with the automatic fix; the box past the right edge is off the slide
    assert {"off_slide", "overlap", "text_overflow"} <= rules, out["slides"][1]["findings"]
    grown = next(f for f in out["slides"][1]["findings"] if f["rule"] == "text_overflow")
    assert grown["auto_fix"] and "the slide leaves" in grown["detail"]
    off = [f for f in out["slides"][1]["findings"] if f["rule"] == "off_slide"]
    assert [f["where"] for f in off] == ["fuera"], off
    assert (services.visual_review_dir(deck["id"]) / "slide-01.png").is_file()


def test_routes(client):
    d = client.post("/api/decks", json={"title": "HTTP review"}).json()
    client.post(f"/api/decks/{d['id']}/slides", json={"title": "A", "blocks": [{"type": "text", "text": "x"}]})
    try:
        out = client.post(f"/api/decks/{d['id']}/visual-review", json={}).json()
    except PdfUnavailable:
        pytest.skip("no browser here")
    if "slides" not in out:
        pytest.skip(out.get("error", "no browser here"))
    png = client.get(out["slides"][0]["png_url"])
    assert png.status_code == 200 and png.headers["content-type"] == "image/png" and png.content[:4] == b"\x89PNG"
    assert client.get(f"/api/decks/{d['id']}/visual-review/../../secret").status_code == 404
    assert client.get(f"/api/decks/{d['id']}/visual-review/slide-99.png").status_code == 404
