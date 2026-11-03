"""Deck design audit: the audited document, mapping findings to slides, storage, staleness, the studio being down, routes and tool."""
from __future__ import annotations

import copy

import pytest

from cicero_hoard import agent_tools as at
from cicero_hoard import decks as store
from cicero_hoard import design_audit as da
from cicero_hoard.errors import CiceroError
from cicero_hoard.render import CSS
from conftest import make_services, new_deck
from vitruvius_fixtures import StudioHub, recorded

BULLETS = [("Gasto frente a plan", ["Gasto total 1,2 M", "Marketing un 8 % por debajo"]), ("Ahorros conseguidos", ["Licencias", "Viajes"]),
           ("Prioridades", ["Compras", "Nube"])]


def four_slides(svc):
    deck = new_deck(svc, title="Revisión trimestral de presupuesto", brief="Quarterly budget review for the finance team")
    store.add_slide(svc, deck["id"], layout="title", title="Revisión trimestral de presupuesto", subtitle="T3")
    for title, items in BULLETS:
        store.add_slide(svc, deck["id"], title=title, blocks=[{"type": "bullets", "items": items}])
    return store.deck_view(svc, deck["id"])


@pytest.fixture
def studio(tmp_path, monkeypatch):
    hub = StudioHub()
    monkeypatch.setattr(da, "hub_post", hub.start)
    svc = make_services(tmp_path, hub=hub)
    yield svc
    svc.stop()


def test_the_pinned_layout_matches_the_preview_css():
    # The mapping relies on these numbers; a change to the preview layout must change both.
    assert ".deck{padding:24px 16px}" in CSS and "width:min(100%,1280px);aspect-ratio:16/9;margin:0 auto 28px" in CSS
    assert (da.TOP, da.SIDE, da.SLIDE_MAX_W, da.GAP) == (24, 16, 1280, 28)


def test_boxes_map_to_the_stacked_slides():
    # 1440 wide: slides are 1280x720 at y = 24, 772, 1520, 2268 (the recorded audit's page is 3040 tall for four slides)
    assert [da.slide_index_for_box(b, 1440, 4) for b in ([176, 342, 1088, 74], [152, 854, 1136, 46], [152, 1602, 1136, 46], [152, 2350, 1136, 46])] == [0, 1, 2, 3]
    assert da.slide_index_for_box([0, 0, 10, 10], 1440, 4) is None             # above the first slide
    assert da.slide_index_for_box([0, 750, 10, 10], 1440, 4) is None           # in the gap between slides 1 and 2
    assert da.slide_index_for_box([0, 5000, 10, 10], 1440, 4) is None          # below the last
    assert da.slide_index_for_box([0, 24 + 200, 10, 10], 1440, 4, ratio=4 / 3) == 0  # 1280x960 slides
    assert da.slide_index_for_box([0, 24 + 1000, 10, 10], 1440, 4, ratio=4 / 3) == 1
    assert da.slide_index_for_box([0, 300, 10, 10], 400, 2) == 1               # 368 wide: 207 tall, pitch 235
    assert da.slide_index_for_box(["x"], 1440, 4) is None


def test_the_audit_document_is_stacked_inline_and_pinned(studio):
    deck = four_slides(studio)
    html, ratio = da.audit_document(studio, deck)
    assert ratio == pytest.approx(16 / 9) and 'id="cicero-audit-layout"' in html and '<meta name="description" content="Quarterly budget' in html
    assert html.count('class="slide"') == 4 and 'data-mode="stacked"' in html
    assert all(f'id="s-{s["id"]}"' in html for s in deck["slides"])


def test_recorded_findings_map_to_slides_deck_and_page(studio):
    deck = four_slides(studio)
    issues = da.map_findings(recorded("design_slop_audit")["result"]["findings"], deck["slides"])
    ids = [s["id"] for s in deck["slides"]]
    balance = [i for i in issues if i["rule"] == "craft/no-text-balance"]
    assert [i["slide_id"] for i in balance] == ids and all(i["scope"] == "slide" and i["fix"] == "text-wrap: balance on display heads." for i in balance)
    sans = [i for i in issues if i["rule"] == "unslop/single-default-sans"]
    assert len(sans) == 1 and sans[0]["slide_id"] == ids[0] and sans[0]["slide_number"] == 1 and sans[0]["severity"] == "warning" and sans[0]["slop"]
    assert sans[0]["widths"] == [320, 375, 414, 768, 1024, 1280, 1440, 1920]
    by_rule = {i["rule"]: i for i in issues if i["slide_id"] is None}
    assert by_rule["craft/title-meta"]["scope"] == "page" and by_rule["layout.no-max-width"]["scope"] == "page"
    assert by_rule["slop/pure-black-white"]["scope"] == "page"                   # only html, body and .slide literals
    assert by_rule["font.generic-only"]["scope"] == "deck" and by_rule["type.line-length"]["scope"] == "deck"
    assert all(i["source"] == "design" for i in issues)


def test_a_quoted_finding_without_boxes_goes_to_the_slide_that_says_it(studio):
    deck = four_slides(studio)
    finding = {"check_id": "unslop/generic-copy", "title": "Generic copy", "detail": "x", "fix": "Say what it does.", "level": "warning",
               "evidence": ["li: “Marketing un 8 % por debajo”"], "boxes": [], "box_width": 1440, "pass": "copy", "slop": True}
    [issue] = da.map_findings([finding], deck["slides"])
    assert issue["slide_id"] == deck["slides"][1]["id"] and issue["scope"] == "slide"


def test_run_keeps_the_audit_and_marks_it_stale_after_an_edit(studio):
    deck = four_slides(studio)
    audit = studio.design_audit(deck["id"])
    assert audit["slop_score"] == 32 and audit["mode"] == "light" and audit["stale"] is False and audit["render_id"] == "37eca19311f7"
    assert audit["studio_url"].endswith("/design/#/critique/37eca19311f7") and audit["summary"].startswith("A light polish")
    assert audit["counts"] == {"slide": 5, "deck": 2, "page": 3} and audit["per_slide"][deck["slides"][0]["id"]] == 2
    sent = [c for c in studio.hub.calls if c[1] == "design_slop_audit"][0][2]
    assert sent["full"] is True and 'id="cicero-audit-layout"' in sent["html"]
    assert "cicero.design_audit.done" in studio._emit.types()
    assert studio.hub.links[-1][:3] == (f"hoard://cicero/deck/{deck['id']}", "hoard://vitruvius/render/37eca19311f7", "reviewed_by")
    again = studio.design_audit_latest(deck["id"])
    assert again["stale"] is False and again["slop_score"] == 32 and len(again["issues"]) == len(audit["issues"])
    store.update_deck(studio, deck["id"], {"theme": "oscuro"})
    assert studio.design_audit_latest(deck["id"])["stale"] is True
    assert studio.design_audit_latest(new_deck(studio)["id"]) is None


def test_big_decks_go_to_the_studio_as_a_local_file(studio, monkeypatch):
    deck = four_slides(studio)
    monkeypatch.setattr(da, "MAX_INLINE_HTML", 100)
    studio.design_audit(deck["id"])
    sent = [c for c in studio.hub.calls if c[1] == "design_slop_audit"][-1][2]
    assert "html" not in sent and sent["path"].endswith(f"{deck['id']}.html")
    assert 'id="cicero-audit-layout"' in open(sent["path"], encoding="utf-8").read()


def test_an_empty_deck_is_refused(studio):
    with pytest.raises(CiceroError) as caught:
        studio.design_audit(new_deck(studio)["id"])
    assert caught.value.code == "no_slides"


def test_the_studio_down_says_so_and_prepare_starts_it_through_the_hub(studio):
    deck = four_slides(studio)
    studio.hub.state = "down"
    with pytest.raises(CiceroError) as caught:
        studio.design_audit(deck["id"])
    assert caught.value.code == "vitruvius_down" and "Start it through the Hub" in str(caught.value) and studio.hub.starts == 0
    assert studio.design_audit_latest(deck["id"]) is None
    audit = studio.design_audit(deck["id"], prepare=True)
    assert studio.hub.starts == 1 and audit["prepared"]["started"] is True and audit["prepared"]["design_module"] == "on" and audit["slop_score"] == 32


def test_the_design_module_off_is_switched_on_with_prepare(studio):
    deck = four_slides(studio)
    studio.hub.state = "off"
    with pytest.raises(CiceroError) as caught:
        studio.design_audit(deck["id"])
    assert caught.value.code == "design_module_off"
    audit = studio.design_audit(deck["id"], prepare=True)
    assert audit["prepared"] == {"design_module": "on"} and studio.hub.starts == 0
    assert ("vitruvius", "software_module_set", {"module": "design", "enabled": True}) in studio.hub.calls


def test_error_codes():
    assert da.unavailable({"ok": False, "error": "hub not reachable at http://127.0.0.1:8810"}, "x").code == "hub_down"
    assert da.unavailable({"ok": False, "status": None, "error": "URLError: "}, "x").code == "vitruvius_down"
    assert da.unavailable({"ok": False, "status": 400, "error": "Unknown tool"}, "x").code == "vitruvius_outdated"
    assert da.unavailable({"ok": False, "status": 400, "error": "boom"}, "x").code == "family_unavailable"


def test_vitruvius_prepare_when_running_only_checks_the_module(studio):
    assert studio.vitruvius_prepare() == {"started": False, "running": True, "design_module": "on"}
    assert studio.hub.starts == 0
    studio.hub.state = "down"
    assert studio.vitruvius_prepare()["started"] is True and studio.hub.starts == 1


def test_routes_and_tool(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from cicero_hoard.main import create_app

    hub = StudioHub()
    monkeypatch.setattr(da, "hub_post", hub.start)
    svc = make_services(tmp_path, hub=hub)
    deck = four_slides(svc)
    with TestClient(create_app(svc.config, svc), base_url="http://127.0.0.1") as client:
        assert client.get(f"/api/decks/{deck['id']}/design-audit").json() == {"audit": None}
        ran = client.post(f"/api/decks/{deck['id']}/design-audit", json={}).json()["audit"]
        assert ran["slop_score"] == 32 and ran["counts"]["slide"] == 5
        assert client.get(f"/api/decks/{deck['id']}/design-audit").json()["audit"]["render_id"] == "37eca19311f7"
        hub.state = "down"
        down = client.post(f"/api/decks/{deck['id']}/design-audit", json={})
        assert down.status_code == 400 and down.json()["code"] == "vitruvius_down"
        assert client.post("/api/design/vitruvius/start").json()["started"] is True
        assert client.post(f"/api/decks/{deck['id']}/design-audit", json={"bogus": 1}).status_code == 400
        out = at.call_tool(svc, "deck_design_audit", {"deck_id": deck["id"]})
        assert out["slop_score"] == 32 and out["stale"] is False and {i["scope"] for i in out["issues"]} == {"slide", "deck", "page"}
        one = at.call_tool(svc, "deck_design_audit", {"deck_id": deck["id"], "action": "latest", "slide_id": deck["slides"][0]["id"]})
        assert len(one["issues"]) == 2 and all(i["fix"] for i in one["issues"])
        assert at.call_tool(svc, "deck_design_audit", {"deck_id": new_deck(svc)["id"], "action": "latest"})["audit"] is None


def _in_spanish(answer):
    """What the studio answers for the same render in Spanish: the same findings and rule ids with Spanish titles, fixes and summary."""
    es = copy.deepcopy(answer)
    es["result"]["lang"] = "es"
    es["result"]["plan"]["summary"] = "Un pulido ligero: 4 cambios, sin rediseño."
    es["result"]["credit"] = "Lista de indicios y método: unslop, de Damir Sokolovsky (CC BY 4.0)."
    for f in es["result"]["findings"]:
        f["title"], f["fix"], f["detail"] = f"ES {f['check_id']}", "Arreglo en castellano.", "Detalle en castellano."
    return es


def test_the_audit_is_asked_for_and_kept_in_the_ui_language(studio):
    deck = four_slides(studio)
    assert da.norm_lang(None, None) == "es" and da.norm_lang("en") == "en" and da.norm_lang(None, "en-US,en;q=0.9") == "en"
    english = studio.design_audit(deck["id"], lang="en")
    assert [c for c in studio.hub.calls if c[1] == "design_slop_audit"][-1][2]["lang"] == "en"
    assert english["lang"] == "en" and english["summary"].startswith("A light polish")
    studio.hub.audit = _in_spanish(recorded("design_slop_audit"))
    spanish = studio.design_audit_latest(deck["id"], "es")                 # re-read, not re-audited
    asked = [c for c in studio.hub.calls if c[1] == "design_slop_audit"][-1][2]
    assert asked["lang"] == "es" and asked["render_id"] == english["render_id"] and "html" not in asked
    assert spanish["lang"] == "es" and spanish["summary"].startswith("Un pulido ligero") and "CC BY 4.0" in spanish["credit"]
    assert spanish["slop_score"] == english["slop_score"] and spanish["counts"] == english["counts"]
    assert all(i["title"].startswith("ES ") and i["fix"] == "Arreglo en castellano." for i in spanish["issues"])
    calls = len(studio.hub.calls)
    again = studio.design_audit_latest(deck["id"], "es")                   # kept in Spanish: no new call
    assert len(studio.hub.calls) == calls and again["lang"] == "es"
    studio.hub.audit = recorded("design_slop_audit")
    studio.hub.audit["result"]["lang"] = "en"
    back = studio.design_audit_latest(deck["id"], "en")                    # and back, from the studio's English
    assert back["lang"] == "en" and back["summary"].startswith("A light polish")


SAME_START = "Resultados del primer trimestre por region: "


def similar_titles(svc, regions=("norte", "sur", "este", "oeste", "centro, todos sus canales", "islas, canales y clientes")):
    deck = new_deck(svc, title="Ventas", brief="Ventas regionales")
    for region in regions:
        store.add_slide(svc, deck["id"], title=SAME_START + region, blocks=[{"type": "bullets", "items": ["Margen estable"]}])
    return store.deck_view(svc, deck["id"])


def test_every_slide_element_carries_its_slide_number(studio):
    deck = similar_titles(studio)
    html, _ = da.audit_document(studio, deck)
    assert 'id="cs1-1"' in html and 'id="cs6-1"' in html and 'id="cs7-1"' not in html
    assert all(f'id="s-{s["id"]}"' in html for s in deck["slides"])            # the slides keep their own ids
    assert '<h2 id="cs5-' in html and '<main class="deck">' in html            # nothing outside the slides is touched
    assert da.mark_slides('<section class="slide" id="s-a"><script>var x="<b>";</script><p id="keep">x</p><i>y</i></section>') == \
        '<section class="slide" id="s-a"><script>var x="<b>";</script><p id="keep">x</p><i id="cs1-1">y</i></section>'


def test_similar_titles_map_by_the_element_the_studio_names_not_by_its_words(studio):
    # The studio quotes only the first ~32 characters, the same on every slide here, and its box for a quote is the first slide
    # with those words; the marks name the slide (live: stubs on slides 5 and 6 were shown on slides 1 and 2).
    deck = similar_titles(studio)
    finding = {"check_id": "quality/unbalanced-heading", "title": "Unbalanced heading", "detail": "2 heading(s) leave a stub.", "level": "warning",
               "evidence": ["h2#cs5-3 “Resultados del primer trimestre ” last line 130px of 1136px",
                            "h2#cs6-3 “Resultados del primer trimestre ” last line 135px of 1136px"],
               "boxes": [[152, 102, 1136, 46], [152, 850, 1136, 46]], "box_width": 1440, "pass": "type"}
    issues = da.map_findings([finding], deck["slides"])
    assert [i["slide_number"] for i in issues] == [5, 6] and [i["slide_id"] for i in issues] == [s["id"] for s in deck["slides"][4:6]]
    assert issues[0]["items"][0] == "h2 “Resultados del primer trimestre ” last line 130px of 1136px"   # shown without the mark
    section = {**finding, "evidence": [f"section#s-{deck['slides'][3]['id']}.slide overflow"], "boxes": []}
    assert [i["slide_number"] for i in da.map_findings([section], deck["slides"])] == [4]
    unmarked = {**finding, "evidence": ["h2 “Resultados del primer trimestre ”"], "boxes": [[152, 102, 1136, 46]]}
    assert [i["slide_number"] for i in da.map_findings([unmarked], deck["slides"])] == [1]   # without a mark the box still decides
