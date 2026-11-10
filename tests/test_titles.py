"""Conclusion titles: telling a label from a statement, proposing from the slide's own data, applying and going back."""
from __future__ import annotations

import json
import re

import pytest

from cicero_hoard import decks, titles
from cicero_hoard.agent_tools import call_tool, tool_catalog
from conftest import FakeLink, make_services, new_deck

CHART = {"type": "chart", "chart": "line", "categories": ["2023", "2024"], "series": [{"name": "Ventas", "values": [100, 112]}]}
PIE = {"type": "chart", "chart": "pie", "title": "Ventas por canal", "categories": ["Online", "Tienda"], "series": [{"name": "", "values": [60, 40]}]}
BULLETS = {"type": "bullets", "items": ["El canal online aporta la mitad del crecimiento", "La tienda física se mantiene"]}
TOPICS = {"type": "bullets", "items": ["Contexto", "Resultados", "Riesgos"]}


def build(svc):
    """A deck with a cover, a chart slide, a text slide, a list of topics and a closing slide."""
    d = new_deck(svc)
    add = lambda **kw: decks.add_slide(svc, d["id"], **kw)["id"]  # noqa: E731
    ids = {"cover": add(layout="title", title="Revisión trimestral"),
           "chart": add(layout="chart", title="Resultados del trimestre", blocks=[CHART], notes="El crecimiento viene del canal online."),
           "text": add(layout="bullets", title="Canales de venta", blocks=[BULLETS]),
           "agenda": add(layout="bullets", title="Agenda", blocks=[TOPICS]),
           "closing": add(layout="closing", title="Gracias")}
    return d["id"], ids


def titles_model(answers):
    """A model that answers each request for titles with the next dict of {slide key or id: title}."""
    state = {"n": 0}

    def responder(messages):
        assert "conclusion titles" in messages[0]["content"]
        answer = answers[min(state["n"], len(answers) - 1)]
        state["n"] += 1
        asked = re.findall(r'"id":"([^"]+)"', messages[-1]["content"])
        return json.dumps({"titles": [{"id": sid, "title": answer[sid]} for sid in asked if sid in answer]}, ensure_ascii=False)
    return responder


@pytest.mark.parametrize("title", ["Resultados del trimestre", "Agenda", "Próximos pasos", "¿Por qué crecemos?", "Mejora de procesos",
                                   "Plan 2024-2025", "Market overview", "Análisis de la competencia en Europa", "Updated roadmap for Europe",
                                   "Una pared de carga"])
def test_labels_name_a_topic(title):
    assert titles.is_label(title)


@pytest.mark.parametrize("title", ["Las ventas crecieron un 12 % por el canal online", "El canal online aporta la mitad del crecimiento",
                                   "Ventas: +12 % interanual", "Sales grew 12% on the online channel", "El coste se reduce a la mitad",
                                   "Online drives half of the growth", "La plantilla mejora su productividad", "Las ventas crecen",
                                   "Twelve unseen mixes passed the test"])
def test_conclusions_state_something(title):
    assert not titles.is_label(title)


def test_chart_arithmetic_gives_the_facts_and_the_numbers_a_title_may_use():
    slide = {"id": "s", "title": "Resultados del trimestre", "blocks": [CHART], "notes": ""}
    assert titles.rule_proposal(slide, "es") == "Ventas sube de 100 a 112 entre 2023 y 2024 (+12 %)"
    assert titles.rule_proposal(slide, "en") == "Ventas rises from 100 to 112 between 2023 and 2024 (+12%)"
    ev = titles.evidence(slide, "es")
    assert titles.unbacked("Las ventas crecieron un 12 % hasta 112", ev) == []
    assert titles.unbacked("Las ventas crecieron un 15 % por el canal online", ev) == ["15%"]
    assert titles.unbacked("Las ventas llegaron a 1.250.000 euros", ev) == ["1.250.000"]
    falling = {"id": "f", "title": "Costes", "blocks": [{**CHART, "series": [{"name": "Costes", "values": [80, 60]}]}]}
    assert titles.rule_proposal(falling, "es") == "Costes baja de 80 a 60 entre 2023 y 2024 (−25 %)"
    assert titles.rule_proposal({"id": "p", "title": "Canales", "blocks": [PIE]}, "es") == "Online concentra el 60 % de ventas por canal"
    metrics = {"type": "metrics", "items": [{"value": "8.400", "label": "Clientes activos"}, {"value": "4,3", "label": "Satisfacción", "emphasis": True}]}
    assert titles.rule_proposal({"id": "m", "title": "Clientes", "blocks": [metrics]}, "es") == "Satisfacción se sitúa en 4,3"
    assert titles.rule_proposal({"id": "t", "title": "Canales de venta", "blocks": [BULLETS]}, "es") == "El canal online aporta la mitad del crecimiento"
    assert titles.rule_proposal({"id": "a", "title": "Agenda", "blocks": [TOPICS]}, "es") is None


def test_the_review_marks_label_titles_and_proposes(tmp_path):
    svc = make_services(tmp_path)
    svc.start()
    deck_id, ids = build(svc)
    issues = [i for i in svc.check(deck_id)["issues"] if i["kind"] == "label_title"]
    assert {i["slide_id"] for i in issues} == {ids["chart"], ids["text"], ids["agenda"]}, "the cover and the closing slide are exempt"
    by_slide = {i["slide_id"]: i for i in issues}
    assert by_slide[ids["chart"]]["severity"] == "info"
    assert by_slide[ids["chart"]]["proposal"] == "Ventas sube de 100 a 112 entre 2023 y 2024 (+12 %)"
    assert "Propuesta: «Ventas sube de 100 a 112" in by_slide[ids["chart"]]["message"]
    assert "proposal" not in by_slide[ids["agenda"]] and "rótulo" in by_slide[ids["agenda"]]["message"]
    svc.stop()


def test_proposals_from_the_model_are_checked_against_the_slide(tmp_path):
    first = {}
    second = {}
    link = FakeLink()
    svc = make_services(tmp_path, link=link)
    svc.start()
    deck_id, ids = build(svc)
    first.update({ids["chart"]: "Las ventas crecieron un 15 % gracias a la campaña de Navidad",       # 15 is not on the slide
                  ids["text"]: "El canal online aporta la mitad del crecimiento.", ids["agenda"]: ""})
    second.update({ids["chart"]: "Las ventas crecieron un 12 % entre 2023 y 2024"})
    link.responder = titles_model([first, second])
    out = call_tool(svc, "titles_propose", {"deck_id": deck_id})
    got = {p["slide_id"]: p for p in out["proposals"]}
    assert got[ids["chart"]]["proposal"] == "Las ventas crecieron un 12 % entre 2023 y 2024" and got[ids["chart"]]["by"] == "model"
    assert got[ids["text"]]["proposal"] == "El canal online aporta la mitad del crecimiento"
    assert out["generator"] == "model" and out["model"] == "fake-model"
    assert {(s["slide_id"], s["reason"]) for s in out["skipped"]} == {(ids["cover"], "exempt_layout"), (ids["closing"], "exempt_layout"),
                                                                      (ids["agenda"], "nothing_to_conclude")}
    assert len(link.calls) == 2 and "these figures are not on the slide: 15%" in link.calls[1][-1]["content"]
    sent = link.calls[0][-1]["content"]
    assert '"computed_facts":["Ventas sube de 100 a 112 entre 2023 y 2024 (+12 %)"]' in sent and "El crecimiento viene del canal online." in sent
    # nothing changed on the slides; the proposals wait in the deck view and in the review
    view = decks.deck_view(svc, deck_id)
    slide = next(s for s in view["slides"] if s["id"] == ids["chart"])
    assert slide["title"] == "Resultados del trimestre" and slide["revision"] == 1
    assert slide["titling"]["proposal"] == "Las ventas crecieron un 12 % entre 2023 y 2024" and slide["titling"]["is_label"]
    issue = next(i for i in svc.check(deck_id)["issues"] if i["kind"] == "label_title" and i["slide_id"] == ids["chart"])
    assert issue["proposal"] == "Las ventas crecieron un 12 % entre 2023 y 2024"
    # a model that keeps inventing: the rule-made title is used instead
    link.responder = titles_model([{ids["chart"]: "Las ventas crecieron un 40 % por la campaña"}])
    again = call_tool(svc, "titles_propose", {"deck_id": deck_id, "slide_ids": [ids["chart"]]})
    assert again["proposals"] == [{"slide_id": ids["chart"], "position": 2, "title": "Resultados del trimestre",
                                   "proposal": "Ventas sube de 100 a 112 entre 2023 y 2024 (+12 %)", "by": "rule"}]
    svc.stop()


def test_apply_to_the_whole_deck_and_undo(tmp_path):
    link = FakeLink()
    svc = make_services(tmp_path, link=link)
    svc.start()
    deck_id, ids = build(svc)
    link.responder = titles_model([{ids["chart"]: "Las ventas crecieron un 12 % entre 2023 y 2024", ids["text"]: "El canal online aporta la mitad del crecimiento"}])
    out = call_tool(svc, "titles_apply", {"deck_id": deck_id})
    assert out["mode"] == "conclusion"
    assert [(a["slide_id"], a["from"], a["to"]) for a in out["applied"]] == [
        (ids["chart"], "Resultados del trimestre", "Las ventas crecieron un 12 % entre 2023 y 2024"),
        (ids["text"], "Canales de venta", "El canal online aporta la mitad del crecimiento")]
    assert (ids["agenda"], "nothing_to_conclude") in {(s["slide_id"], s["reason"]) for s in out["skipped"]}
    view = decks.deck_view(svc, deck_id)
    by_id = {s["id"]: s for s in view["slides"]}
    assert view["title_mode"] == "conclusion"
    assert by_id[ids["chart"]]["title"] == "Las ventas crecieron un 12 % entre 2023 y 2024" and by_id[ids["chart"]]["revision"] == 2
    assert by_id[ids["chart"]]["titling"] == {"mode": "conclusion", "own_mode": None, "exempt": False, "is_label": False, "proposal": None,
                                               "proposal_by": None, "label": "Resultados del trimestre", "applied": True}
    assert by_id[ids["cover"]]["title"] == "Revisión trimestral" and by_id[ids["closing"]]["title"] == "Gracias"
    assert decks.list_revisions(svc, deck_id, ids["chart"])["items"][0]["reason"] == "conclusion title"
    # in conclusion mode a title that is still a label is a warning
    marks = {i["slide_id"]: i["severity"] for i in svc.check(deck_id)["issues"] if i["kind"] == "label_title"}
    assert marks == {ids["agenda"]: "warning"}
    overview = call_tool(svc, "titles_overview", {"deck_id": deck_id})
    assert (overview["mode"], overview["labels"], overview["applied"]) == ("conclusion", 1, 2)

    # the text slide is edited by hand afterwards: undo leaves it alone, and puts the other label back
    decks.patch_slide(svc, deck_id, ids["text"], {"title": "El online ya es la mitad del crecimiento"})
    back = call_tool(svc, "titles_restore", {"deck_id": deck_id})
    assert back["mode"] == "label"
    assert [(r["slide_id"], r["to"]) for r in back["restored"]] == [(ids["chart"], "Resultados del trimestre")]
    assert [(s["slide_id"], s["reason"]) for s in back["skipped"]] == [(ids["text"], "edited_since")]
    view = decks.deck_view(svc, deck_id)
    by_id = {s["id"]: s for s in view["slides"]}
    assert by_id[ids["chart"]]["title"] == "Resultados del trimestre" and by_id[ids["chart"]]["revision"] == 3
    assert by_id[ids["chart"]]["titling"]["proposal"] == "Las ventas crecieron un 12 % entre 2023 y 2024", "the conclusion stays as a proposal"
    assert by_id[ids["text"]]["title"] == "El online ya es la mitad del crecimiento"
    forced = call_tool(svc, "titles_restore", {"deck_id": deck_id, "force": True})
    assert [(r["slide_id"], r["to"]) for r in forced["restored"]] == [(ids["text"], "Canales de venta")]
    # applying again reuses the kept proposal without asking the model
    calls = len(link.calls)
    again = call_tool(svc, "titles_apply", {"deck_id": deck_id, "slide_ids": [ids["chart"]]})
    assert again["applied"][0]["to"] == "Las ventas crecieron un 12 % entre 2023 y 2024" and len(link.calls) == calls
    assert again["mode"] == "label", "one slide does not change the deck's mode"
    svc.stop()


def test_your_own_wording_is_checked_and_a_slide_can_keep_its_label(tmp_path):
    svc = make_services(tmp_path, link=FakeLink(available=False))
    svc.start()
    deck_id, ids = build(svc)
    out = call_tool(svc, "titles_apply", {"deck_id": deck_id, "titles": {ids["chart"]: "Las ventas crecieron un 30 % en un año",
                                                                        ids["text"]: "La tienda física se mantiene y el online crece"}})
    assert [(a["slide_id"], a["to"]) for a in out["applied"]] == [(ids["text"], "La tienda física se mantiene y el online crece")]
    assert (ids["chart"], "invented_figures: 30%") in {(s["slide_id"], s["reason"]) for s in out["skipped"]}
    assert out["mode"] == "label"
    assert decks.get_slide(svc, deck_id, ids["chart"])["title"] == "Resultados del trimestre"
    # the chart slide is told to keep its label: the review stops marking it and a deck-wide apply skips it
    kept = call_tool(svc, "titles_mode", {"deck_id": deck_id, "slide_id": ids["chart"], "mode": "label"})
    assert kept["restored"] == []
    assert ids["chart"] not in {i["slide_id"] for i in svc.check(deck_id)["issues"] if i["kind"] == "label_title"}
    whole = call_tool(svc, "titles_mode", {"deck_id": deck_id, "mode": "conclusion"})
    assert (ids["chart"], "kept_as_label") in {(s["slide_id"], s["reason"]) for s in whole["skipped"]} and whole["mode"] == "conclusion"
    assert decks.get_slide(svc, deck_id, ids["chart"])["title"] == "Resultados del trimestre"
    # ...until it follows the deck again
    follow = call_tool(svc, "titles_mode", {"deck_id": deck_id, "slide_id": ids["chart"]})
    assert follow["slide_mode"] == "conclusion"
    one = call_tool(svc, "titles_mode", {"deck_id": deck_id, "slide_id": ids["chart"], "mode": "conclusion"})
    assert one["applied"][0]["to"] == "Ventas sube de 100 a 112 entre 2023 y 2024 (+12 %)"
    with pytest.raises(LookupError):
        call_tool(svc, "titles_apply", {"deck_id": deck_id, "slide_ids": ["nope"]})
    svc.stop()


def test_without_a_model_the_rules_write_what_the_data_says(tmp_path):
    svc = make_services(tmp_path, link=FakeLink(available=False))
    svc.start()
    deck_id, ids = build(svc)
    out = call_tool(svc, "titles_propose", {"deck_id": deck_id})
    assert out["generator"] == "rules" and out["model"] is None and out["note"]
    assert {p["slide_id"]: (p["proposal"], p["by"]) for p in out["proposals"]} == {
        ids["chart"]: ("Ventas sube de 100 a 112 entre 2023 y 2024 (+12 %)", "rule"),
        ids["text"]: ("El canal online aporta la mitad del crecimiento", "rule")}
    quiet = call_tool(svc, "titles_propose", {"deck_id": deck_id, "use_model": False})
    assert "note" not in quiet and len(quiet["proposals"]) == 2
    svc.stop()


def test_rest_routes_and_catalog(client):
    svc = client.svc
    deck_id, ids = build(svc)
    svc.link_sync.responder = titles_model([{ids["chart"]: "Las ventas crecieron un 12 % entre 2023 y 2024"}])
    seen = client.get(f"/api/decks/{deck_id}/titles").json()
    assert seen["mode"] == "label" and seen["labels"] == 3 and [s["exempt"] for s in seen["slides"]] == [True, False, False, False, True]
    proposed = client.post(f"/api/decks/{deck_id}/titles/propose", json={"slide_ids": [ids["chart"]]}).json()
    assert proposed["proposals"][0]["proposal"] == "Las ventas crecieron un 12 % entre 2023 y 2024"
    applied = client.post(f"/api/decks/{deck_id}/titles/apply", json={"slide_ids": [ids["chart"]]}).json()
    assert applied["applied"][0]["from"] == "Resultados del trimestre"
    deck = client.get(f"/api/decks/{deck_id}").json()
    assert deck["title_mode"] == "label" and deck["slides"][1]["titling"]["applied"] is True
    restored = client.post(f"/api/decks/{deck_id}/titles/restore", json={"slide_ids": [ids["chart"]]}).json()
    assert restored["restored"][0]["to"] == "Resultados del trimestre"
    mode = client.post(f"/api/decks/{deck_id}/titles/mode", json={"mode": "conclusion", "use_model": False}).json()
    assert mode["mode"] == "conclusion" and len(mode["applied"]) == 1, "the chart slide keeps the label it was restored to by name"
    assert client.post(f"/api/decks/{deck_id}/titles/mode", json={"mode": "nope"}).status_code in (400, 422)
    assert client.post(f"/api/decks/nope/titles/propose", json={}).status_code == 404
    names = {t["name"]: t for t in tool_catalog()}
    assert {"titles_overview", "titles_propose", "titles_apply", "titles_restore", "titles_mode"} <= set(names)
    assert names["titles_overview"]["annotations"]["readOnlyHint"] is True and names["titles_apply"]["annotations"]["readOnlyHint"] is False
    # deleting the deck forgets its title state
    client.delete(f"/api/decks/{deck_id}?confirm=true")
    assert svc.db.get_setting("titles:" + deck_id, None) is None
