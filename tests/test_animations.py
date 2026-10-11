"""Native slide animations and transitions: settings, planning per element kind, OOXML validated by the vendored
PPT Master read-back, the export, the tool and the HTTP routes."""

from __future__ import annotations

import io
import zipfile

import pytest
from pptx import Presentation

from cicero_hoard import animations as motion, decks
from cicero_hoard.agent_tools import call_tool
from cicero_hoard.export_pptx import build_pptx
from conftest import new_deck

CHART = {"type": "chart", "chart": "bar", "categories": ["T1", "T2", "T3"], "unit": "k",
         "series": [{"name": "2026", "values": [3, 5, 4]}]}


def staged_deck() -> dict:
    return {"title": "Motion", "language": "es", "theme": "claro", "slides": [
        {"id": "cover", "position": 1, "layout": "title", "title": "Portada", "subtitle": "Sub", "blocks": [], "notes": ""},
        {"id": "s2", "position": 2, "layout": "bullets", "title": "Puntos", "notes": "",
         "blocks": [{"type": "text", "text": "Primero", "build": 1, "effect": "fade"},
                    {"type": "text", "text": "Segundo", "build": 2, "effect": "wipe"}]},
        {"id": "s3", "position": 3, "layout": "bullets", "title": "Lista", "notes": "",
         "blocks": [{"type": "bullets", "items": ["uno", "dos"]}]},
    ]}


def rows(pptx: bytes) -> list[dict]:
    return motion.read_back(pptx)


def test_catalogue_has_native_effects_and_transitions():
    cat = motion.catalogue()
    assert len(cat["effects"]["entrance"]) >= 50 and "entrance_fly" in cat["effects"]["entrance"]
    assert {"fade", "push", "morph"} <= set(cat["transitions"]) and cat["transitions"][0] == "none"
    assert cat["modes"] == ["builds", "auto", "mixed", "none"]


def test_normalize_validates_and_explains():
    assert motion.normalize({})["mode"] == "builds"
    assert motion.normalize({"mode": "fly"})["mode"] == "entrance_fly"           # legacy alias -> canonical preset
    for bad, msg in (({"mode": "wobble"}, "unknown animation effect"), ({"transition": "spin3d"}, "unknown transition"),
                     ({"duration": 30}, "between"), ({"trigger": "later"}, "trigger"), ({"colour": 1}, "unknown animation setting")):
        with pytest.raises(ValueError, match=msg):
            motion.normalize(bad)
    with pytest.raises(ValueError, match="not in this deck"):
        motion.normalize({"slides": {"zzz": {"mode": "none"}}}, {"a"})


def test_builds_mode_turns_click_stages_into_native_animations():
    deck = staged_deck()
    data, report = motion.apply(build_pptx(deck, assets=lambda _: None), {}, [s["id"] for s in deck["slides"]])
    back = rows(data)
    assert back[0]["animations"] == [] and back[2]["animations"] == []
    assert back[1]["animations"] == ["entrance_fade", "entrance_wipe"]
    assert report["slides"][1]["clicks"] == 2 and report["transitions"] == 0
    motion.validate(data)                                      # PPT Master's own package validation
    Presentation(io.BytesIO(data))                             # and python-pptx still opens it


def test_auto_mode_by_kind_cover_zoom_and_transitions():
    deck = staged_deck()
    deck["slides"][2]["blocks"].append(CHART)
    settings = {"mode": "auto", "transition": "push", "transition_duration": 0.7,
                "slides": {"s3": {"transition": "morph"}}}
    data, report = motion.apply(build_pptx(deck, assets=lambda _: None), settings, [s["id"] for s in deck["slides"]])
    back = rows(data)
    assert set(back[0]["animations"]) == {"entrance_zoom"}                   # cover
    assert back[1]["animations"][0] == "entrance_fade" and back[1]["animations"][-2:] == ["entrance_fade", "entrance_wipe"]
    assert "entrance_wipe" in back[2]["animations"]                          # the chart
    assert [b["transition"] for b in back] == ["push", "push", "morph"]
    assert report["transitions"] == 3
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        s1 = z.read("ppt/slides/slide1.xml").decode()
    assert s1.index("<p:transition") < s1.index("<p:timing")               # schema order: transition before timing


def test_none_mode_and_per_slide_override():
    deck = staged_deck()
    data, report = motion.apply(build_pptx(deck, assets=lambda _: None),
                                {"mode": "none", "slides": {"s3": {"mode": "entrance_fly", "trigger": "on-click"}}},
                                [s["id"] for s in deck["slides"]])
    back = rows(data)
    assert back[1]["animations"] == [] and back[2]["animations"] and set(back[2]["animations"]) == {"entrance_fly"}
    assert report["slides"][2]["clicks"] == report["slides"][2]["animated"]


def test_footer_and_decorations_never_animate():
    deck = staged_deck()
    pptx = build_pptx(deck, assets=lambda _: None)
    with zipfile.ZipFile(io.BytesIO(pptx)) as z:
        from lxml import etree
        shapes = motion._shapes(etree.fromstring(z.read("ppt/slides/slide3.xml")))
    targets = motion.plan_slide(shapes, motion.normalize({"mode": "auto"}), index=2)
    skipped = {s["id"] for s in shapes if s["skip"]}
    assert skipped and not skipped & {t["shape_id"] for t in targets}


def test_store_tool_export_and_routes(services, client):
    deck = new_deck(services)
    slide = decks.add_slide(services, deck["id"], title="Staged", blocks=[{"type": "text", "text": "Uno", "build": 1, "effect": "fade"}])
    assert call_tool(services, "deck_animations", {"deck_id": deck["id"]})["mode"] == "builds"
    saved = call_tool(services, "deck_animations", {"deck_id": deck["id"], "action": "set", "mode": "auto", "transition": "fade",
                                                    "slides": {slide["id"]: {"transition": "morph"}}})
    assert saved["mode"] == "auto" and saved["slides"][slide["id"]] == {"transition": "morph"}
    again = call_tool(services, "deck_animations", {"deck_id": deck["id"], "action": "set", "duration": 0.8})
    assert again["mode"] == "auto" and again["duration"] == 0.8                # merges, does not reset
    preview = call_tool(services, "deck_animations", {"deck_id": deck["id"], "action": "preview"})
    assert preview["animated"] >= 2 and preview["slides"][0]["transition"] == "morph"
    out = services.export(deck["id"], "pptx")
    assert out["animations"]["animated"] >= 2 and "warnings" not in out
    path, _ = decks.export_file(services, out["id"])
    assert rows(path.read_bytes())[0]["transition"] == "morph"
    with pytest.raises(Exception, match="unknown transition"):
        call_tool(services, "deck_animations", {"deck_id": deck["id"], "action": "set", "transition": "spin3d"})
    assert call_tool(services, "deck_animations", {"deck_id": deck["id"], "action": "reset"})["mode"] == "builds"
    assert len(call_tool(services, "deck_animations", {"deck_id": deck["id"], "action": "list"})["transitions"]) > 40

    d2 = client.post("/api/decks", json={"title": "HTTP"}).json()
    client.post(f"/api/decks/{d2['id']}/slides", json={"title": "A", "blocks": [{"type": "text", "text": "x"}]})
    assert client.get("/api/animations/catalogue").json()["modes"][0] == "builds"
    assert client.put(f"/api/decks/{d2['id']}/animations", json={"mode": "mixed"}).json()["mode"] == "mixed"
    assert client.get(f"/api/decks/{d2['id']}/animations").json()["mode"] == "mixed"
    assert client.get(f"/api/decks/{d2['id']}/animations/preview").json()["animated"] >= 1
    assert client.put(f"/api/decks/{d2['id']}/animations", json={"mode": "wobble"}).status_code == 400
    assert client.delete(f"/api/decks/{d2['id']}/animations").json()["mode"] == "builds"
