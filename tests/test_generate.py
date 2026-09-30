"""Generation: model path, repair, strict rules, no invented numbers, and the rule-based fallback."""
from __future__ import annotations

import json

import pytest

from cicero_hoard import decks, generate
from cicero_hoard.errors import CiceroError, GenerationFailed, ModelUnavailable
from conftest import SOURCE_TEXT, FakeLink, make_services, new_deck, outline_json, slide_json


def _with_source(svc, **kw):
    d = new_deck(svc, **kw)
    decks.add_source_text(svc, d["id"], "Informe", SOURCE_TEXT)
    return d


def test_json_from_text_variants():
    assert generate.json_from_text('{"a": 1}') == {"a": 1}
    assert generate.json_from_text('```json\n{"a": 1}\n```') == {"a": 1}
    assert generate.json_from_text('Claro, aquí está: {"a": [1, 2]} Espero que sirva.') == {"a": [1, 2]}
    assert generate.json_from_text("[1, 2]") == [1, 2]
    with pytest.raises(ValueError):
        generate.json_from_text("sin json")
    with pytest.raises(ValueError):
        generate.json_from_text('{"a": ')


def test_outline_from_model(services):
    d = _with_source(services)
    out = generate.generate_outline(services, d["id"])
    assert out["generator"] == "model" and out["model_used"] == "fake-model" and len(out["outline"]) == 6
    assert out["outline"][0]["layout_hint"] == "title" and out["outline"][-1]["layout_hint"] == "closing"
    assert out["status"] == "outline" and all(len(o["id"]) == 12 for o in out["outline"])
    assert "cicero.outline.generated" in services._emit.types()
    user = services.link_sync.calls[0][-1]["content"]
    assert "Number of slides: exactly 6" in user and "[S1]" in user and "Spanish" in user


def test_outline_repair_retry_then_success(tmp_path):
    link = FakeLink([ "esto no es json", outline_json(6)])
    svc = make_services(tmp_path, link=link)
    d = _with_source(svc)
    out = generate.generate_outline(svc, d["id"])
    assert out["generator"] == "model" and len(link.calls) == 2
    assert "cannot be used" in link.calls[1][-1]["content"]


def test_outline_failure_after_repair_raises(tmp_path):
    link = FakeLink(["nada", "tampoco"])
    svc = make_services(tmp_path, link=link)
    d = _with_source(svc)
    with pytest.raises(GenerationFailed) as info:
        generate.generate_outline(svc, d["id"])
    assert info.value.code == "generation_failed"
    assert decks.deck_view(svc, d["id"])["outline"] == []


def test_outline_wrong_count_is_repaired_leniently(tmp_path):
    link = FakeLink([outline_json(4), outline_json(4)])  # both answers have 4 items where 6 are asked
    svc = make_services(tmp_path, link=link)
    d = _with_source(svc)
    out = generate.generate_outline(svc, d["id"])
    assert len(out["outline"]) == 4 and any("instead of 6" in w for w in out["warnings"])


def test_outline_too_many_items_trimmed(tmp_path):
    link = FakeLink([outline_json(9), outline_json(9)])
    svc = make_services(tmp_path, link=link)
    d = _with_source(svc)
    out = generate.generate_outline(svc, d["id"])
    assert len(out["outline"]) == 6 and out["outline"][-1]["title"] == "Cierre"


def test_outline_fallback_without_model(fallback_services):
    svc = fallback_services
    d = _with_source(svc)
    out = generate.generate_outline(svc, d["id"])
    assert out["generator"] == "fallback" and len(out["outline"]) >= 3
    assert any("No model is reachable" in w for w in out["warnings"])
    assert out["outline"][0]["layout_hint"] == "title" and out["outline"][-1]["layout_hint"] == "closing"
    assert out["model_used"] is None


def test_outline_fallback_from_brief_only(fallback_services):
    svc = fallback_services
    d = new_deck(svc, brief="Explicar el plan de mudanza de la oficina. Fechas y responsables. Presupuesto aprobado.")
    out = generate.generate_outline(svc, d["id"])
    assert out["generator"] == "fallback" and out["outline"]


def test_outline_fallback_with_nothing(fallback_services):
    svc = fallback_services
    d = new_deck(svc, brief="")
    with pytest.raises(CiceroError) as info:
        generate.generate_outline(svc, d["id"])  # nothing to work from: a clear error, no invented outline
    assert info.value.code == "no_material"


def test_slides_from_model_keep_sources_and_status(services):
    d = _with_source(services)
    generate.generate_outline(services, d["id"])
    out = generate.generate_slides(services, d["id"])
    assert out["generator"] == "model" and out["generated"] == 6 and out["kept"] == 0
    assert out["status"] == "review" and [s["position"] for s in out["slides"]] == [1, 2, 3, 4, 5, 6]
    assert all(s["status"] == "draft" and s["revision"] == 1 for s in out["slides"])
    assert out["slides"][1]["sources"] == [1]
    assert out["slides"][1]["outline_id"] == out["outline"][1]["id"]


def test_generate_slides_requires_outline(services):
    d = new_deck(services)
    with pytest.raises(CiceroError) as info:
        generate.generate_slides(services, d["id"])
    assert info.value.code == "outline_required"


def test_slides_fallback_uses_source_sentences(fallback_services):
    svc = fallback_services
    d = _with_source(svc)
    generate.generate_outline(svc, d["id"])
    out = generate.generate_slides(svc, d["id"])
    assert out["generator"] == "fallback" and len(out["slides"]) == len(out["outline"])
    assert all(s["title"] for s in out["slides"])
    assert out["slides"][0]["layout"] == "title" and out["slides"][-1]["layout"] == "closing"
    text = " ".join(json.dumps(s["blocks"], ensure_ascii=False) for s in out["slides"])
    assert "1.250.000" in text or "1,25" in text or "45" in text  # content comes from the sources


def test_approved_slides_are_kept_on_regeneration(services):
    d = _with_source(services)
    generate.generate_outline(services, d["id"])
    first = generate.generate_slides(services, d["id"])
    sid = first["slides"][1]["id"]
    decks.patch_slide(services, d["id"], sid, {"title": "Mi título"})
    decks.set_approval(services, d["id"], sid, True)
    again = generate.generate_slides(services, d["id"])
    assert again["kept"] == 1 and again["generated"] == 5
    kept = next(s for s in again["slides"] if s["id"] == sid)
    assert kept["title"] == "Mi título" and kept["status"] == "approved"
    other = next(s for s in again["slides"] if s["id"] != sid and s["outline_id"])
    assert other["revision"] == 2  # regenerated slides get a new revision
    revs = decks.list_revisions(services, d["id"], other["id"])["items"]
    assert [r["reason"] for r in revs] == ["regenerated", "generated"]


def test_only_missing_generates_new_outline_items(services):
    d = _with_source(services)
    generate.generate_outline(services, d["id"])
    generate.generate_slides(services, d["id"])
    view = decks.deck_view(services, d["id"])
    outline = view["outline"] + [{"id": "", "title": "Extra", "purpose": "", "points": ["a"]}]
    outline[-1].pop("id")
    decks.set_outline(services, d["id"], outline)
    out = generate.generate_slides(services, d["id"], only_missing=True)
    assert out["generated"] == 1 and out["kept"] == 6 and len(out["slides"]) == 7


def test_hand_made_slides_survive_and_keep_place(services):
    d = _with_source(services)
    generate.generate_outline(services, d["id"])
    first = generate.generate_slides(services, d["id"])
    hand = decks.add_slide(services, d["id"], after_id=first["slides"][2]["id"], title="A mano")
    out = generate.generate_slides(services, d["id"])
    titles = [s["title"] for s in out["slides"]]
    assert "A mano" in titles and titles.index("A mano") == 3 and len(titles) == 7
    assert next(s for s in out["slides"] if s["id"] == hand["id"])["revision"] == 1


def test_draft_of_removed_outline_item_is_deleted(services):
    d = _with_source(services)
    generate.generate_outline(services, d["id"])
    first = generate.generate_slides(services, d["id"])
    decks.set_outline(services, d["id"], first["outline"][:4])
    out = generate.generate_slides(services, d["id"])
    assert len(out["slides"]) == 4


def test_slide_repair_then_fallback_flag(tmp_path):
    def responder(messages):
        user = messages[-1]["content"]
        if "Number of slides" in user:
            return outline_json(4)
        return "no es json"  # always broken: the fallback builds the slide
    svc = make_services(tmp_path, link=FakeLink(responder))
    d = _with_source(svc, slide_count=4)
    generate.generate_outline(svc, d["id"])
    out = generate.generate_slides(svc, d["id"])
    assert out["generator"] == "fallback" and len(out["slides"]) == 4
    assert any("Built by the fallback" in w for w in out["warnings"])


def test_mixed_generator_when_model_dies_midway(tmp_path):
    state = {"n": 0}

    def responder(messages):
        user = messages[-1]["content"]
        if "Number of slides" in user:
            return outline_json(4)
        state["n"] += 1
        if state["n"] > 2:
            raise RuntimeError("connection refused")
        return slide_json("Sección", sources=[1])
    svc = make_services(tmp_path, link=FakeLink(responder))
    d = _with_source(svc, slide_count=4)
    generate.generate_outline(svc, d["id"])
    out = generate.generate_slides(svc, d["id"])
    assert out["generator"] == "mixed" and len(out["slides"]) == 4


def test_strict_rules_shorten_and_limit_bullets(tmp_path):
    long_items = ["x" * 300] + [f"punto {i}" for i in range(9)]
    answer = slide_json("Muchos", blocks=[{"type": "bullets", "items": long_items}], sources=[1])
    # the first answer breaks the rules (strict), the repair answer breaks them too: mechanical repair applies
    svc = make_services(tmp_path, link=FakeLink(lambda m: outline_json(3) if "Number of slides" in m[-1]["content"] else answer))
    d = _with_source(svc, slide_count=3)
    generate.generate_outline(svc, d["id"])
    out = generate.generate_slides(svc, d["id"])
    bullets = out["slides"][1]["blocks"][0]["items"]
    assert len(bullets) == 6 and max(len(b) for b in bullets) <= generate.MAX_BULLET_CHARS
    assert any("shortened" in w for w in out["warnings"])


def test_invented_chart_is_dropped(tmp_path):
    invented = {"type": "chart", "chart": "bar", "title": "Ventas", "categories": ["A", "B"], "series": [{"name": "s", "values": [777, 999]}]}
    answer = slide_json("Ventas", layout="chart", blocks=[invented], sources=[1])
    svc = make_services(tmp_path, link=FakeLink(lambda m: outline_json(3) if "Number of slides" in m[-1]["content"] else answer))
    d = _with_source(svc, slide_count=3)
    generate.generate_outline(svc, d["id"])
    out = generate.generate_slides(svc, d["id"])
    slide = out["slides"][1]
    assert all(b["type"] != "chart" for b in slide["blocks"]) and slide["layout"] != "chart"
    assert any("not in the sources" in w for w in out["warnings"])


def test_sourced_chart_is_kept(tmp_path):
    real = {"type": "chart", "chart": "bar", "title": "Ventas", "categories": ["Clientes", "Incidencias"], "series": [{"name": "s", "values": [8400, 310]}]}
    answer = slide_json("Cifras", layout="chart", blocks=[real], sources=[1])
    svc = make_services(tmp_path, link=FakeLink(lambda m: outline_json(3) if "Number of slides" in m[-1]["content"] else answer))
    d = _with_source(svc, slide_count=3)
    generate.generate_outline(svc, d["id"])
    out = generate.generate_slides(svc, d["id"])
    slide = out["slides"][1]
    assert slide["layout"] == "chart" and slide["blocks"][0]["type"] == "chart"


def test_chart_without_any_source_is_dropped(tmp_path):
    chart = {"type": "chart", "chart": "bar", "title": "T", "categories": ["A"], "series": [{"name": "s", "values": [5]}]}
    answer = slide_json("Datos", layout="chart", blocks=[chart])
    svc = make_services(tmp_path, link=FakeLink(lambda m: outline_json(3) if "Number of slides" in m[-1]["content"] else answer))
    d = new_deck(svc, slide_count=3)
    generate.generate_outline(svc, d["id"])
    out = generate.generate_slides(svc, d["id"])
    assert all(b["type"] != "chart" for s in out["slides"] for b in s["blocks"])


def test_unknown_source_ids_are_removed(tmp_path):
    answer = slide_json("Con fuentes", sources=[1, 99])
    svc = make_services(tmp_path, link=FakeLink(lambda m: outline_json(3) if "Number of slides" in m[-1]["content"] else answer))
    d = _with_source(svc, slide_count=3)
    generate.generate_outline(svc, d["id"])
    out = generate.generate_slides(svc, d["id"])
    assert out["slides"][1]["sources"] == [1]


def test_excerpts_respect_budget_and_number_sources():
    sources = [{"id": 1, "text": "\n\n".join(f"Párrafo {i} sobre ventas y clientes. " * 20 for i in range(30))},
               {"id": 2, "text": "Otro documento breve sobre riesgos."}]
    text, ids = generate.excerpts(sources, "riesgos", 3000)
    assert len(text) <= 3000 + 200 and "[S1]" in text and "[S2]" in text and ids == [1, 2]
    assert generate.excerpts([], "x", 100) == ("", [])


def test_excerpts_prefer_matching_chunks():
    filler = "\n\n".join(f"Texto de relleno número {i} sin relación alguna. " * 25 for i in range(12))
    text = filler + "\n\nLa rotación de personal subió al nueve por ciento este año. " * 3
    out, _ = generate.excerpts([{"id": 1, "text": text}], "rotación de personal", 2600)
    assert "rotación de personal" in out


def test_chunk_text_splits_long_paragraphs():
    chunks = generate.chunk_text("Una frase. " * 500, size=1100)
    assert len(chunks) > 3 and all(len(c) <= 1650 for c in chunks)


def test_regenerate_slide_with_feedback(services, deck):
    sid = deck["slides"][1]["id"]
    services.link_sync.responder = lambda m: slide_json("Nuevo título", sources=[1])
    out = generate.regenerate_slide(services, deck["id"], sid, "más corto")
    assert out["title"] == "Nuevo título" and out["revision"] == 2 and out["generator"] == "model"
    assert "más corto" in services.link_sync.calls[-1][-1]["content"]
    assert decks.list_revisions(services, deck["id"], sid)["items"][0]["reason"] == "regenerated"


def test_regenerate_keeps_pictures(services, deck):
    from conftest import png_bytes

    sid = deck["slides"][1]["id"]
    asset = decks.add_asset(services, deck["id"], png_bytes())
    decks.patch_slide(services, deck["id"], sid, {"blocks": [{"type": "bullets", "items": ["a"]}, {"type": "image", "asset_id": asset["asset_id"]}]})
    out = generate.regenerate_slide(services, deck["id"], sid, "otra cosa")
    assert any(b["type"] == "image" and b["asset_id"] == asset["asset_id"] for b in out["blocks"])


def test_regenerate_without_model_is_an_honest_error(fallback_services):
    svc = fallback_services
    d = _with_source(svc)
    generate.generate_outline(svc, d["id"])
    out = generate.generate_slides(svc, d["id"])
    with pytest.raises(ModelUnavailable) as info:
        generate.regenerate_slide(svc, d["id"], out["slides"][1]["id"], "otro enfoque")
    assert info.value.code == "model_unavailable"


def test_revert_after_regenerate(services, deck):
    sid = deck["slides"][1]["id"]
    original = deck["slides"][1]["title"]
    services.link_sync.responder = lambda m: slide_json("Otro", sources=[1])
    generate.regenerate_slide(services, deck["id"], sid, "x")
    back = decks.revert_slide(services, deck["id"], sid, 1)
    assert back["title"] == original and back["revision"] == 3
    assert decks.list_revisions(services, deck["id"], sid)["items"][0]["reason"] == "reverted"


def test_fallback_slides_never_carry_charts(fallback_services):
    svc = fallback_services
    d = _with_source(svc)
    generate.generate_outline(svc, d["id"])
    out = generate.generate_slides(svc, d["id"])
    assert all(b["type"] != "chart" for s in out["slides"] for b in s["blocks"])


def test_slides_are_written_a_few_at_a_time_and_keep_their_order(services, monkeypatch):
    import threading
    import time

    monkeypatch.setenv("CICERO_PARALLEL_SLIDES", "3")
    d = _with_source(services)
    generate.generate_outline(services, d["id"])
    state = {"now": 0, "peak": 0}
    lock = threading.Lock()
    base = services.link_sync.responder

    def slow(messages):
        with lock:
            state["now"] += 1
            state["peak"] = max(state["peak"], state["now"])
        time.sleep(0.05)
        with lock:
            state["now"] -= 1
        return base(messages)

    services.link_sync.responder = slow
    out = generate.generate_slides(services, d["id"])
    assert out["generator"] == "model" and out["generated"] == 6
    assert state["peak"] == 3  # the first slide alone, then three at once
    assert [s["title"] for s in out["slides"]] == [o["title"] for o in out["outline"]]


def test_a_model_that_is_down_is_asked_once_not_once_per_slide(services):
    d = _with_source(services)
    generate.generate_outline(services, d["id"])
    services.link_sync.available = False
    before = len(services.link_sync.calls)
    out = generate.generate_slides(services, d["id"])
    assert out["generator"] == "fallback" and len(services.link_sync.calls) - before == 1
