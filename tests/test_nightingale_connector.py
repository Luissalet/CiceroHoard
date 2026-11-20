"""A Nightingale chart or table becomes an editable chart block with its provenance, and follows the data when it changes."""
import json

import pytest

from cicero_hoard import connectors, data_links as dl, datasets, decks
from cicero_hoard.errors import CiceroError
from conftest import FakeHub, make_services, new_deck


class NightingaleHub(FakeHub):
    """Answers Nightingale's data_handoff like the real tool does, with rows the test can change."""

    def __init__(self):
        super().__init__()
        self.rows = [["writer", 5], ["cicero", 1], ["hypatia", 1]]
        self.version = 0

    def call(self, app, tool, arguments=None, *, timeout=120.0):
        self.calls.append((app, tool, dict(arguments or {})))
        if (app, tool) != ("nightingale", "data_handoff"):
            return super().call(app, tool, arguments, timeout=timeout)
        csv = "station,returns\n" + "".join(f"{s},{n}\n" for s, n in self.rows)
        return {"ok": True, "app": app, "tool": tool, "status": 200, "result": {
            "kind": "data-chart", "title": "Returns by station", "columns": ["station", "returns"], "rows": self.rows,
            "csv": csv, "chart": {"id": 4, "type": "bar", "x": "station", "y": "returns", "agg": "sum"},
            "provenance": {"app": "nightingale", "ref": "hoard://nightingale/chart/4", "dataset": "returns",
                           "version": self.version, "query": 'SELECT "station" AS x, SUM("returns") AS y FROM "returns"',
                           "fingerprint": f"print-{self.version}", "source": {"kind": "hoard", "path": "hoard://hoardhub/hub_agora_tasks"}}}}


@pytest.fixture
def ng(tmp_path):
    hub = NightingaleHub()
    svc = make_services(tmp_path, hub=hub)
    svc.start()
    yield svc, hub
    svc.stop()


def test_nightingale_chart_becomes_a_bound_chart_block_with_provenance(ng):
    svc, hub = ng
    deck = new_deck(svc)
    link = connectors.create(svc, connectors.ConnectorArgs(deck_id=deck["id"], kind="nightingale", chart_id=4, interval_s=10000))
    assert hub.calls[-1] == ("nightingale", "data_handoff", {"chart_id": 4})
    snapshot = datasets.load(svc, deck["id"], link["source_id"])
    assert snapshot["origin"]["connector"] == "nightingale" and snapshot["origin"]["ref"] == "hoard://nightingale/chart/4"
    assert snapshot["origin"]["version"] == 0 and snapshot["origin"]["fingerprint"] == "print-0"
    assert snapshot["origin"]["chart"]["type"] == "bar" and snapshot["number_format"] == "en"
    source = decks.get_source(svc, deck["id"], link["source_id"])
    assert source["title"] == "Returns by station"

    slide = decks.add_slide(svc, deck["id"], title="Devoluciones por puesto", blocks=[])
    bound = dl.bind(svc, dl.BindArgs(deck_id=deck["id"], link_id=link["link_id"], slide_id=slide["id"], block_index=0,
                                     mapping={"category_column": "station", "series_columns": ["returns"]}))["slide"]
    block = bound["blocks"][0]
    assert block["type"] == "chart" and block["categories"] == ["writer", "cicero", "hypatia"]
    assert block["series"][0]["values"] == [5, 1, 1]
    assert link["source_id"] in bound["sources"]

    # Nightingale's data moves on: a refresh brings the new figures and the new provenance, the old snapshot stays.
    hub.rows, hub.version = [["writer", 4], ["cicero", 2], ["hypatia", 1]], 1
    refreshed = dl.refresh(svc, deck["id"], link["link_id"])
    assert refreshed["changed"] and refreshed["bindings"][0]["changed"]
    after = decks.get_slide(svc, deck["id"], slide["id"])
    assert after["blocks"][0]["series"][0]["values"] == [4, 2, 1]
    assert datasets.load(svc, deck["id"], refreshed["source_id"])["origin"]["version"] == 1
    assert datasets.load(svc, deck["id"], link["source_id"])["origin"]["version"] == 0


def test_nightingale_table_connector_passes_the_selection(ng):
    svc, hub = ng
    deck = new_deck(svc)
    connectors.create(svc, connectors.ConnectorArgs(deck_id=deck["id"], kind="nightingale", dataset="returns",
                                                    columns=["station", "returns"], filter="returns > 1", interval_s=10000))
    assert hub.calls[-1] == ("nightingale", "data_handoff",
                             {"dataset": "returns", "columns": ["station", "returns"], "filter": "returns > 1"})


def test_nightingale_connector_needs_one_selection_and_says_when_nightingale_is_off(tmp_path):
    svc = make_services(tmp_path, hub=FakeHub(error="hub not reachable", status=None))
    svc.start()
    try:
        deck = new_deck(svc)
        with pytest.raises(CiceroError, match="chart_id or dataset"):
            connectors.create(svc, connectors.ConnectorArgs(deck_id=deck["id"], kind="nightingale"))
        # The link is kept (it retries on its schedule) and the answer says what to do.
        result = connectors.create(svc, connectors.ConnectorArgs(deck_id=deck["id"], kind="nightingale", chart_id=1))
        assert result["source_id"] is None and "Start Nightingale's Hoard from the Hub" in result["error"]
    finally:
        svc.stop()


def test_station_declaration_takes_nightingale_figures():
    from pathlib import Path

    manifest = json.loads((Path(__file__).resolve().parent.parent / "faustus-plugin.json").read_text(encoding="utf-8"))
    handoffs = manifest["x-family"]["production"]["handoffs"]
    accepted = {h["accepts"] for h in handoffs if "editable-deck" in h["produces"]}
    assert {"data-chart", "data-table"} <= accepted
    check = next(h for h in handoffs if h["accepts"] == "data-chart")["check"]
    assert "kind=nightingale" in check["en"] and "kind=nightingale" in check["es"]
