"""Slides as a demanding reader sees them: stacked visuals fit, metrics share a row, titles outrank the body."""
from __future__ import annotations

from cicero_hoard import themes
from cicero_hoard.layouts import BODY_MAX, CONTENT_BOTTOM, build_plan


def plan_for(slide):
    return build_plan(slide, deck_title="Deck", theme=themes.get_theme("claro"), number=2, total=5, lang="es")


def metrics(n, detail=True):
    return {"type": "metrics", "items": [{"value": f"{10 + i},5 %", "label": f"Indicador {i}", **({"detail": f"{i} en 2025"} if detail else {})}
                                         for i in range(n)]}


def content_boxes(plan):
    return [b for b in plan.boxes if b.role not in ("title", "footer") and b.kind not in ("rect",)]


def test_four_metrics_share_one_row():
    plan = plan_for({"layout": "bullets", "title": "Cifras clave", "blocks": [metrics(4)]})
    values = [b for b in plan.boxes if b.kind == "text" and b.paras and b.paras[0].text.endswith("%")]
    assert len(values) == 4 and len({round(b.y) for b in values}) == 1
    assert not plan.overflow


def test_six_metrics_make_two_rows_of_three():
    plan = plan_for({"layout": "bullets", "title": "Cifras", "blocks": [metrics(6, detail=False)]})
    rows = sorted({round(b.y) for b in plan.boxes if b.kind == "text" and b.paras and b.paras[0].text.endswith("%")})
    assert len(rows) == 2


def test_table_metrics_and_sentence_fit_together():
    table = {"type": "table", "headers": ["Trimestre", "2025", "2026"], "rows": [["T1", "10,1", "10,9"], ["T2", "10,8", "11,7"],
                                                                              ["T3", "11,2", "12,4"], ["T4", "12,3", "13,6"]]}
    two = {"type": "metrics", "items": [{"value": "10,7 %", "label": "Crecimiento del T3", "detail": "Mayor crecimiento del año, por la campaña de verano"},
                                        {"value": "28 %", "label": "Peso del T4", "detail": "El cuarto trimestre concentró el 28 % de las ventas"}]}
    text = {"type": "text", "text": "Las ventas crecen en los cuatro trimestres respecto a 2025, con una progresión ascendente."}
    plan = plan_for({"layout": "table", "title": "Evolución trimestral", "blocks": [table, two, text]})
    assert not plan.overflow, plan.overflow_where
    boxes = content_boxes(plan)
    assert max(b.y + b.h for b in boxes) <= CONTENT_BOTTOM + 1
    ordered = sorted(boxes, key=lambda b: b.y)
    table_box = next(b for b in boxes if b.kind == "table")
    assert all(b.y >= table_box.y + table_box.h for b in ordered if b is not table_box and b.y > table_box.y)


def test_value_repeated_as_label_is_not_drawn_twice():
    plan = plan_for({"layout": "bullets", "title": "Métricas", "blocks": [{"type": "metrics", "items": [
        {"value": "Calidad", "label": "Calidad", "detail": "Incidencias"}, {"value": "12", "label": "Equipos"}]}]})
    texts = [b.paras[0].text for b in plan.boxes if b.kind == "text" and b.paras]
    assert texts.count("Calidad") == 1


def test_title_outranks_body():
    plan = plan_for({"layout": "bullets", "title": "Riesgos", "blocks": [{"type": "bullets", "items": ["Uno", "Dos"]}]})
    title = next(b for b in plan.boxes if b.role == "title")
    body = next(b for b in plan.boxes if b.kind == "text" and b.paras and b.paras[0].bullet)
    assert title.paras[0].size >= body.paras[0].size * 1.4 and body.paras[0].size <= BODY_MAX


def test_cover_line_separates_its_parts():
    plan = plan_for({"layout": "title", "title": "Portada", "blocks": [{"type": "text", "text": "Empresa de 80 personas"},
                                                                      {"type": "text", "text": "Piloto de seis meses"}]})
    line = next(b for b in plan.boxes if b.kind == "text" and b.paras and "Empresa" in b.paras[0].text)
    assert line.paras[0].text == "Empresa de 80 personas · Piloto de seis meses"
