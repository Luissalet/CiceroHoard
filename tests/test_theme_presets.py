"""Themes from the design studio's presets: listing, picking for a brief, the token mapping, idempotence, exports, routes and tool."""
from __future__ import annotations

import io

import pytest
from pptx import Presentation

from cicero_hoard import agent_tools as at
from cicero_hoard import custom_themes, decks as store, themes
from cicero_hoard.errors import CiceroError
from conftest import make_services, new_deck
from vitruvius_fixtures import StudioHub, recorded


@pytest.fixture
def svc(tmp_path):
    s = make_services(tmp_path, hub=StudioHub())
    yield s
    s.stop()


def ledger_tokens():
    return recorded("design_preset_ledger_ink")["result"]["preset"]["tokens"]


def test_preset_tokens_map_to_a_readable_theme_in_both_modes():
    tokens = ledger_tokens()
    light, warnings = themes.theme_from_preset(tokens, theme_id="vp-a", name="Ledger Ink (claro)", mode="light")
    c = tokens["colors"]["light"]
    assert light["colors"]["background"] == c["background"] and light["colors"]["surface"] == c["secondary"] and light["colors"]["text"] == c["foreground"]
    # the primary green reads on the page but not 4.5:1 on the secondary card, so it is pulled darker and the change is reported
    assert themes.contrast(c["primary"], c["secondary"]) < 4.5 and any(w.startswith(f"accent changed from {c['primary']}") for w in warnings)
    assert light["radius"] == 4
    assert light["fonts"] == {"heading": "Georgia", "body": "Segoe UI"} and any("IBM Plex Serif" in w for w in warnings)
    assert any("accent2" in w for w in warnings) and light["colors"]["accent2"] not in (light["colors"]["accent"],)
    assert themes.contrast_issues(light) == []
    dark, _ = themes.theme_from_preset(tokens, theme_id="vp-b", name="Ledger Ink (oscuro)", mode="dark")
    assert dark["colors"]["background"] == tokens["colors"]["dark"]["background"] and themes.contrast_issues(dark) == []
    with pytest.raises(CiceroError):
        themes.theme_from_preset(tokens, theme_id="x", name="x", mode="sepia")
    with pytest.raises(CiceroError):
        themes.theme_from_preset({"colors": {}}, theme_id="x", name="x")


def test_a_preset_with_a_second_chart_colour_uses_it():
    tokens = ledger_tokens()
    tokens["colors"]["light"]["chart-2"] = "#7a3b00"
    theme, warnings = themes.theme_from_preset(tokens, theme_id="vp-c", name="c", mode="light")
    assert theme["colors"]["accent2"] == "#7a3b00" and not any("accent2" in w for w in warnings)


def test_rotate_hue_keeps_lightness():
    assert themes.rotate_hue("#ff0000", 120) == "#00ff00" and themes.rotate_hue("#808080", 90) == "#808080"


def test_the_second_accent_borrows_the_page_hue_or_turns_on_grey():
    import colorsys
    hue = lambda c: colorsys.rgb_to_hls(*(v / 255 for v in themes.hex_to_rgb(c)))[0]  # noqa: E731
    warm = themes.paper_accent("#267b4c", "#f7f3eb")                       # ledger green on warm stock: an ochre
    assert abs(hue(warm) - hue("#f7f3eb")) < 0.02 and warm != "#267b4c"
    assert themes.paper_accent("#267b4c", "#f5f5f5") == themes.rotate_hue("#267b4c", 150)  # grey page: no hue to borrow
    assert themes.paper_accent("#267b4c", None) == themes.rotate_hue("#267b4c", 150)


def test_list_and_pick(svc):
    listed = svc.design_presets(query="ledger", limit=10)
    assert listed["total"] == 112 and listed["count"] == 4 and listed["items"][0]["swatches"]["light"][0].startswith("#")
    assert svc.hub.calls[-1] == ("vitruvius", "design_preset_list", {"limit": 10, "query": "ledger"})
    picked = svc.pick_presets("Quarterly budget review for the finance team")
    assert picked["recommended"] == "ledger-ink" and len(picked["items"]) == 3 and picked["items"][0]["why"] and picked["ranked_by"] == "keywords"
    with pytest.raises(CiceroError) as caught:
        svc.pick_presets(" ")
    assert caught.value.code == "brief_required"


def test_from_preset_saves_links_and_is_idempotent(svc):
    made = svc.theme_from_preset("ledger-ink", "light")
    theme = made["theme"]
    assert made["created"] is True and theme["id"].startswith("vp-ledger-ink-light-") and theme["name"] == "Ledger Ink (claro)" and theme["custom"] is True
    assert theme["source_ref"] == "hoard://vitruvius/preset/ledger-ink" and made["contrast_issues"] == []
    assert svc.hub.links[-1] == (f"hoard://cicero/theme/{theme['id']}", "hoard://vitruvius/preset/ledger-ink", "derived_from",
                                 {"from_label": "Ledger Ink (claro)", "to_label": "Ledger Ink"})
    again = svc.theme_from_preset("ledger-ink", "light")
    assert again["created"] is False and again["theme"]["id"] == theme["id"] and len(custom_themes.list_custom(svc)) == 1
    dark = svc.theme_from_preset("ledger-ink", "dark")
    assert dark["created"] is True and dark["theme"]["id"].startswith("vp-ledger-ink-dark-")
    with pytest.raises(CiceroError) as caught:
        svc.theme_from_preset("nope", "light")
    assert caught.value.code == "family_unavailable"


def test_the_studio_down_gives_a_clear_error(tmp_path):
    s = make_services(tmp_path, hub=StudioHub(state="down"))
    with pytest.raises(CiceroError) as caught:
        s.design_presets()
    assert caught.value.code == "family_unavailable" and "linked to the hub" in str(caught.value)


def test_exports_use_the_preset_theme(svc):
    theme_id = svc.theme_from_preset("ledger-ink", "dark")["theme"]["id"]
    deck = new_deck(svc, theme=theme_id)
    store.add_slide(svc, deck["id"], title="Gasto", blocks=[{"type": "columns", "left_title": "A", "left": ["uno"], "right_title": "B", "right": ["dos"]}])
    html = svc.preview_html(deck["id"])
    assert "--background:#120f08" in html and "border-radius:4px" in html
    exported = svc.export(deck["id"], "html")
    path, _ = store.export_file(svc, exported["id"])
    assert "--background:#120f08" in path.read_text(encoding="utf-8")
    pptx = svc.export(deck["id"], "pptx")
    ppath, _ = store.export_file(svc, pptx["id"])
    prs = Presentation(io.BytesIO(ppath.read_bytes()))
    fonts = {r.font.name for slide in prs.slides for s in slide.shapes if s.has_text_frame for p in s.text_frame.paragraphs for r in p.runs}
    assert "Georgia" in fonts
    assert {str(slide.background.fill.fore_color.rgb).lower() for slide in prs.slides} == {"120f08"}


def test_routes(tmp_path):
    from fastapi.testclient import TestClient
    from cicero_hoard.main import create_app

    s = make_services(tmp_path, hub=StudioHub())
    deck = new_deck(s, brief="Quarterly budget review for the finance team")
    with TestClient(create_app(s.config, s), base_url="http://127.0.0.1") as client:
        assert client.get("/api/themes/presets?limit=5").json()["total"] == 112
        picked = client.post("/api/themes/presets/pick", json={"deck_id": deck["id"]}).json()
        assert picked["recommended"] == "ledger-ink" and "finance team" in picked["brief"]
        made = client.post("/api/themes/from-preset", json={"preset": "ledger-ink", "mode": "dark"})
        assert made.status_code == 201 and made.json()["created"] is True
        assert any(t["id"] == made.json()["theme"]["id"] for t in client.get("/api/themes").json()["items"])
        assert client.post("/api/themes/from-preset", json={"preset": "ledger-ink", "mode": "sepia"}).status_code == 400
        assert client.post("/api/themes/presets/pick", json={}).json()["code"] == "brief_required"


def test_tool_lists_picks_makes_and_applies(svc):
    deck = new_deck(svc, brief="Quarterly budget review for the finance team")
    listed = at.call_tool(svc, "deck_theme_from_preset", {"query": "ledger"})
    assert listed["total"] == 112 and listed["presets"][0]["name"] and "hint" in listed
    picked = at.call_tool(svc, "deck_theme_from_preset", {"deck_id": deck["id"], "pick": True})
    assert picked["recommended"] == "ledger-ink" and len(picked["presets"]) == 3
    made = at.call_tool(svc, "deck_theme_from_preset", {"deck_id": deck["id"], "preset": "ledger-ink", "mode": "dark"})
    assert made["applied_to"] == deck["id"] and store.deck_view(svc, deck["id"])["theme"] == made["theme_id"] and made["contrast_issues"] == []


def test_table_headers_read_on_a_dark_preset_accent(svc):
    # A dark preset's accent is pulled light to read on the page; white header text on it fell to about 2:1 (HTML and PPTX).
    theme = svc.theme_from_preset("ledger-ink", "dark")["theme"]
    on = themes.on_accent(theme)
    assert themes.contrast("#ffffff", theme["colors"]["accent"]) < 4.5 and themes.contrast(on, theme["colors"]["accent"]) >= 4.5
    assert themes.on_accent(themes.theme_of({"theme": "claro"})) == "#ffffff"         # a dark accent keeps white
    deck = new_deck(svc, theme=theme["id"])
    store.add_slide(svc, deck["id"], layout="table", title="Gasto", blocks=[{"type": "table", "headers": ["Area", "Gasto"], "rows": [["Nube", "12"], ["Viajes", "4"]]}])
    assert f"--on-accent:{on}" in svc.preview_html(deck["id"])
    pptx = svc.export(deck["id"], "pptx")
    ppath, _ = store.export_file(svc, pptx["id"])
    prs = Presentation(io.BytesIO(ppath.read_bytes()))
    tables = [s.table for slide in prs.slides for s in slide.shapes if s.has_table]
    assert tables and str(tables[0].cell(0, 0).text_frame.paragraphs[0].runs[0].font.color.rgb).lower() == on.lstrip("#")


def test_deleting_a_saved_theme_moves_its_decks_to_a_builtin_and_exports_still_work(svc):
    dark = svc.theme_from_preset("ledger-ink", "dark")["theme"]["id"]
    light = svc.theme_from_preset("ledger-ink", "light")["theme"]["id"]
    on_dark, on_light, other = new_deck(svc, theme=dark), new_deck(svc, theme=light), new_deck(svc, theme="editorial")
    store.add_slide(svc, on_dark["id"], title="Gasto", blocks=[{"type": "bullets", "items": ["uno"]}])
    gone = svc.theme_delete(dark)
    assert gone == {"deleted": dark, "name": "Ledger Ink (oscuro)", "decks_moved": [on_dark["id"]], "fallback": "oscuro"}
    assert custom_themes.get_custom(svc, dark) is None and store.deck_view(svc, on_dark["id"])["theme"] == "oscuro"
    assert "cicero.theme.deleted" in svc._emit.types()
    assert svc.theme_delete(light)["fallback"] == "claro" and store.deck_view(svc, on_light["id"])["theme"] == "claro"
    assert store.deck_view(svc, other["id"])["theme"] == "editorial"
    pptx = svc.export(on_dark["id"], "pptx")                                    # the moved deck still exports, in the built-in
    ppath, _ = store.export_file(svc, pptx["id"])
    assert {str(s.background.fill.fore_color.rgb).lower() for s in Presentation(io.BytesIO(ppath.read_bytes())).slides} == {"12151c"}
    with pytest.raises(CiceroError) as caught:
        svc.theme_delete("claro")
    assert caught.value.code == "builtin_theme"
    from cicero_hoard.errors import NotFound
    with pytest.raises(NotFound):
        svc.theme_delete(dark)
    again = svc.theme_from_preset("ledger-ink", "dark")                         # can be made again afterwards
    assert again["created"] is True and again["theme"]["id"] == dark


def test_theme_delete_route_and_tool(tmp_path):
    from fastapi.testclient import TestClient
    from cicero_hoard.main import create_app

    s = make_services(tmp_path, hub=StudioHub())
    made = s.theme_from_preset("ledger-ink", "light")["theme"]["id"]
    deck = new_deck(s, theme=made)
    with TestClient(create_app(s.config, s), base_url="http://127.0.0.1") as client:
        assert client.delete("/api/themes/claro").status_code == 400
        out = client.delete(f"/api/themes/{made}")
        assert out.status_code == 200 and out.json()["decks_moved"] == [deck["id"]]
        assert client.delete(f"/api/themes/{made}").status_code == 404
        assert all(t["id"] != made for t in client.get("/api/themes").json()["items"])
        again = s.theme_from_preset("ledger-ink", "dark")["theme"]["id"]
        assert at.call_tool(s, "theme_delete", {"theme_id": again}) == {"ok": True, "deleted": again, "name": "Ledger Ink (oscuro)", "decks_moved": [], "fallback": "oscuro"}
        with pytest.raises(CiceroError):
            at.call_tool(s, "theme_delete", {"theme_id": "oscuro"})
