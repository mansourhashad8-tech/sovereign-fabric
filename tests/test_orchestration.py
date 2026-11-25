from fastapi.testclient import TestClient

from sovereign.api import create_app
from sovereign.orchestration import Orchestrator, Task
from sovereign.providers import Provider, ProviderRegistry
from sovereign.quality import QualityGate
from sovereign.store import FabricStore


def _provider(provider_id, capabilities, heavy=True, status="ready", cost=0.0):
    return Provider(
        id=provider_id,
        name=provider_id,
        capabilities=tuple(capabilities),
        credential_env="",
        endpoint="test",
        status=status,
        heavy=heavy,
        cost_per_min=cost,
    )


class FakeAdapter:
    def __init__(self, result):
        self.result = result
        self.calls = 0

    def run(self, task):
        self.calls += 1
        return dict(self.result)


def test_discovery_never_marks_missing_credentials_ready():
    registry = ProviderRegistry.discover(probe=False)
    by_id = {provider.id: provider for provider in registry.providers}
    assert by_id["local-control"].status == "ready"
    assert by_id["github-actions"].status in {"configured", "missing_credential"}
    assert by_id["huggingface-hub"].status in {"configured", "missing_credential"}
    assert by_id["groq"].status in {"configured", "missing_credential"}


def test_heavy_task_is_blocked_when_only_local_control_exists():
    registry = ProviderRegistry(
        providers=[_provider("local-control", ["compute.python"], heavy=False)]
    )
    store = FabricStore()
    orchestrator = Orchestrator(store, registry=registry, adapters={})
    plan = orchestrator.plan(
        [Task(id="t1", capability="compute.python", payload={"task": "tests"})]
    )
    assert plan["ok"] is False
    assert plan["blocked"][0]["reasons"][0]["reason"] == (
        "local provider is not allowed for heavy work"
    )
    store.close()


def test_plan_orders_dependencies_and_rejects_cycles():
    registry = ProviderRegistry(
        providers=[_provider("remote", ["compute.python", "hub.metadata"])]
    )
    store = FabricStore()
    orchestrator = Orchestrator(store, registry=registry, adapters={})
    tasks = [
        Task(id="second", capability="hub.metadata", depends_on=("first",), heavy=False),
        Task(id="first", capability="compute.python", payload={"task": "tests"}),
    ]
    plan = orchestrator.plan(tasks)
    assert plan["ok"] is True
    assert plan["order"] == ["first", "second"]
    cyclic = [
        Task(id="a", capability="compute.python", depends_on=("b",)),
        Task(id="b", capability="compute.python", depends_on=("a",)),
    ]
    assert "dependency cycle detected" in orchestrator.plan(cyclic)["errors"]
    store.close()


def test_quality_gate_rejects_missing_acid_evidence_and_accepts_complete_evidence():
    gate = QualityGate()
    task = {"standard": "ACID", "payload": {"task": "db"}}
    missing = gate.evaluate(task, {"status": "ok", "evidence": {"atomic": True}})
    assert missing.passed is False
    complete = gate.evaluate(
        task,
        {
            "status": "ok",
            "evidence": {
                "atomic": True,
                "consistent": True,
                "isolated": True,
                "durable": True,
            },
        },
    )
    assert complete.passed is True


def test_quality_gate_requires_a_real_zkp_verifier_result():
    gate = QualityGate()
    task = {"standard": "ZKP", "payload": {}}
    structural = gate.evaluate(
        task,
        {
            "status": "ok",
            "evidence": {"proof": "0xabc", "public_signals": ["1", "2"]},
        },
    )
    assert structural.passed is False
    verified = gate.evaluate(
        task,
        {
            "status": "ok",
            "evidence": {
                "proof": "0xabc",
                "public_signals": ["1", "2"],
                "verifier_result": {"verified": True},
            },
        },
    )
    assert verified.passed is True


def test_quality_gate_rejects_overclaims():
    gate = QualityGate()
    result = {
        "status": "ok",
        "evidence": {"note": "we achieved a million times speedup"},
    }
    report = gate.evaluate({"standard": "schema"}, result)
    assert report.passed is False
    assert any("overclaim" in failure for failure in report.failures)


def test_orchestrator_runs_and_records_an_accepted_remote_result():
    registry = ProviderRegistry(providers=[_provider("remote", ["compute.python"])])
    adapter = FakeAdapter(
        {
            "task_id": "t1",
            "provider": "remote",
            "status": "ok",
            "conclusion": "success",
            "run_id": 42,
            "evidence": {"remote_run": 42, "conclusion": "success"},
            "command": "remote-task:tests",
        }
    )
    store = FabricStore()
    orchestrator = Orchestrator(
        store, registry=registry, adapters={"remote": adapter}
    )
    report = orchestrator.run(
        [Task(id="t1", capability="compute.python", payload={"task": "tests"})]
    )
    assert report["status"] == "ok"
    assert report["accepted"] == 1
    assert report["results"][0]["quality"]["passed"] is True
    assert store.list_events("orchestration.run")
    store.close()


def test_orchestrator_reassigns_after_a_failed_provider():
    registry = ProviderRegistry(
        providers=[
            _provider("first", ["compute.python"], cost=1.0),
            _provider("second", ["compute.python"], cost=2.0),
        ]
    )
    bad = FakeAdapter(
        {
            "task_id": "t1",
            "provider": "first",
            "status": "failed",
            "conclusion": "failed",
            "evidence": {"remote_run": 1},
            "command": "remote-task:tests",
        }
    )
    good = FakeAdapter(
        {
            "task_id": "t1",
            "provider": "second",
            "status": "ok",
            "conclusion": "success",
            "run_id": 2,
            "evidence": {"remote_run": 2, "conclusion": "success"},
            "command": "remote-task:tests",
        }
    )
    store = FabricStore()
    orchestrator = Orchestrator(
        store, registry=registry, adapters={"first": bad, "second": good}
    )
    report = orchestrator.run(
        [Task(id="t1", capability="compute.python", payload={"task": "tests"})]
    )
    assert report["status"] == "ok"
    assert report["results"][0]["provider"] == "second"
    assert report["results"][0]["reassignment"]["tried"] == ["first"]
    store.close()


def test_provisioning_is_honest_about_account_creation():
    registry = ProviderRegistry(
        providers=[
            _provider("github-actions", ["compute.python"]),
            _provider("huggingface-inference", ["inference.chat"], heavy=False),
        ]
    )
    store = FabricStore()
    orchestrator = Orchestrator(store, registry=registry, adapters={})
    gh = orchestrator.provision("github-actions")
    assert gh["provisioned"] is True
    assert gh["account_creation"] is False
    hf = orchestrator.provision("huggingface-inference")
    assert hf["provisioned"] is False
    assert "human" in hf["reason"]
    store.close()


def test_orchestration_api_exposes_plan_and_standards():
    client = TestClient(create_app())
    standards = client.get("/orchestration/standards")
    assert standards.status_code == 200
    assert {item["name"] for item in standards.json()["standards"]} >= {
        "schema",
        "reproducibility",
        "ACID",
        "ISO_25010_subset",
        "ZKP",
    }
    plan = client.post(
        "/orchestration/plan",
        json={
            "tasks": [
                {
                    "id": "remote-tests",
                    "capability": "compute.python",
                    "payload": {"task": "tests"},
                    "standard": "reproducibility",
                }
            ]
        },
    )
    assert plan.status_code == 200
    assert plan.json()["ok"] is True
