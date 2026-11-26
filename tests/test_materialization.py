from fastapi.testclient import TestClient

from sovereign.api import create_app
from sovereign.contract import REQUIREMENTS
from sovereign.materialization import Materialization


def test_blueprint_is_a_design_not_a_built_robot():
    plan = Materialization().blueprint(
        "build a small robot arm", quantity=2, site="workshop", budget_usd=1000
    )
    assert plan["archetype"] == "mobile robot cell"
    assert plan["quantity"] == 2
    assert plan["bom"]
    assert plan["totals"]["cost_usd"] > 0
    assert plan["totals"]["mass_kg"] > 0
    assert plan["budget"]["status"] == "shortfall"
    assert plan["physical_built"] is False
    assert plan["physical_effect"] is False
    assert plan["requires_facility"] is True
    assert plan["requires_human_oversight"] is True
    assert plan["self_manufacturing_ready"] is False
    assert plan["materialization_status"] == "design_and_digital_twin_only"
    assert {"printer", "robot", "feedstock", "facility", "energy", "capital"} <= set(
        plan["blocked_by"]
    )
    assert plan["digital_twin"]["measured"] is False


def test_readiness_does_not_turn_configured_interfaces_into_verified_hardware(monkeypatch):
    monkeypatch.setenv("SOVEREIGN_PRINTER_ENDPOINT", "http://printer.invalid")
    monkeypatch.setenv("SOVEREIGN_ROBOT_ENDPOINT", "http://robot.invalid")
    readiness = Materialization().readiness()
    assert readiness["interfaces"]["printer"]["configured"] is True
    assert readiness["interfaces"]["printer"]["verified"] is False
    assert readiness["physical_sovereignty"] is False
    assert readiness["self_manufacturing_ready"] is False
    assert readiness["verified_physical_effect"] is False


def test_economy_models_break_even_without_claiming_revenue():
    economy = Materialization().economy(
        "build a small robot arm", quantity=2, budget_usd=1000, unit_price_usd=1500
    )
    assert economy["unit_cost_usd"] > 0
    assert economy["unit_margin_usd"] > 0
    assert economy["break_even_units"] >= 1
    assert economy["capital_gap_usd"] >= 0
    assert economy["sovereign"] is False
    assert economy["revenue_claim"] is False
    assert "No revenue, capital, customer" in economy["note"]


def test_closure_maps_every_requirement_and_refuses_zero_weakness():
    closure = Materialization().closure()
    assert closure["summary"]["total"] == len(REQUIREMENTS)
    assert closure["summary"]["zero_weakness_claim"] is False
    assert closure["summary"]["physical_sovereignty"] is False
    ids = {item["id"] for item in closure["items"]}
    assert {"digital_physical", "physical_materialization", "self_manufacturing"} <= ids
    assert {"sovereign_economy", "weakness_closure", "zero_weakness"} <= ids
    for item in closure["items"]:
        assert item["status"] in {"met", "partial", "false"}
        if item["status"] != "met":
            assert item["blocker"]
            assert item["next_action"]


def test_contract_records_physical_and_economic_gaps():
    by_id = {item["id"]: item for item in REQUIREMENTS}
    assert by_id["physical_materialization"]["status"] == "partial"
    assert by_id["self_manufacturing"]["status"] == "false"
    assert by_id["sovereign_economy"]["status"] == "partial"
    assert by_id["weakness_closure"]["status"] == "met"
    assert by_id["zero_weakness"]["status"] == "false"


def test_materialization_api_exposes_plan_economy_and_closure():
    client = TestClient(create_app())
    blueprint = client.post(
        "/materialization/blueprint",
        json={"intent": "build a sensor node", "quantity": 1, "budget_usd": 200},
    )
    assert blueprint.status_code == 200
    body = blueprint.json()
    assert body["physical_built"] is False
    assert body["archetype"] == "environmental sensor node"

    economy = client.post(
        "/materialization/economy",
        json={"intent": "build a sensor node", "quantity": 1, "unit_price_usd": 120},
    )
    assert economy.status_code == 200
    assert economy.json()["sovereign"] is False

    readiness = client.get("/materialization/readiness")
    assert readiness.status_code == 200
    assert readiness.json()["physical_sovereignty"] is False

    closure = client.get("/materialization/closure")
    assert closure.status_code == 200
    assert closure.json()["summary"]["zero_weakness_claim"] is False
