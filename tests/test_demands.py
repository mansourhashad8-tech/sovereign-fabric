from fastapi.testclient import TestClient

from sovereign.api import create_app
from sovereign.contract import REQUIREMENTS
from sovereign.demands import DemandLedger


def test_demand_ledger_covers_every_contract_requirement():
    report = DemandLedger().report()
    ids = {item["id"] for item in report["items"]}
    assert {item["id"] for item in REQUIREMENTS} <= ids
    assert report["summary"]["total"] == len(report["items"])
    assert report["summary"]["sources"]["protocol_1"] > 0
    assert report["summary"]["sources"]["protocol_2"] > 0
    assert report["summary"]["sources"]["protocol_3"] > 0
    assert report["summary"]["sources"]["prior_build"] > 0


def test_demand_ledger_keeps_literal_absolute_claims_unmet():
    report = DemandLedger().report()
    literal = [item for item in report["items"] if item["literal_claim"]]
    assert literal
    assert report["summary"]["literal_claims_met"] == 0
    assert report["summary"]["all_literal_claims_met"] is False
    by_id = {item["id"]: item for item in report["items"]}
    assert by_id["absolute_sovereignty"]["status"] == "false"
    assert by_id["cosmic_determinism"]["status"] == "false"
    assert by_id["ontological_perfection"]["status"] == "false"
    assert by_id["prior_legacy_commerce"]["status"] == "external"


def test_every_unresolved_demand_has_a_blocker_and_next_action():
    report = DemandLedger().report()
    for item in report["unresolved"]:
        assert item["blocker"]
        assert item["next_action"]


def test_demand_api_filters_and_finds_one_item():
    client = TestClient(create_app())
    response = client.get("/demands")
    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["all_literal_claims_met"] is False

    filtered = client.get("/demands?source=protocol_3")
    assert filtered.status_code == 200
    assert filtered.json()["items"]
    assert all(item["source"] == "protocol_3" for item in filtered.json()["items"])

    item = client.get("/demands/absolute_sovereignty")
    assert item.status_code == 200
    assert item.json()["status"] == "false"

    missing = client.get("/demands/not-a-demand")
    assert missing.status_code == 404
