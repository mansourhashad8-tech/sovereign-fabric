from sovereign.acquire import ExpertAcquirer
from sovereign.capabilities import CapabilityRegistry, bootstrap_native
from sovereign.expert import (
    EnsembleExpert,
    ExpertError,
    GroqExpert,
    OpenAICompatExpert,
    code_prompt,
    extract_code,
)
from sovereign.store import FabricStore
from sovereign.synthesis import Synthesizer

GOOD = (
    "```python\n"
    "def run(payload):\n"
    "    return {\"value\": payload[\"value\"].lower().replace(\" \", \"-\")}\n"
    "```"
)
BAD = "```python\ndef run(payload):\n    return {\"value\": payload[\"value\"]}\n```"

EXAMPLES = [
    ({"value": "Hello World"}, {"value": "hello-world"}),
    ({"value": "A B"}, {"value": "a-b"}),
]


class FakeExpert:
    def __init__(self, replies, name="fake"):
        self.replies = list(replies)
        self.name = name
        self.calls = 0

    def complete(self, system, user):
        reply = self.replies[min(self.calls, len(self.replies) - 1)]
        self.calls += 1
        return reply


class BrokenExpert:
    name = "broken"

    def complete(self, system, user):
        raise ExpertError("down")


def _synth():
    store = FabricStore()
    registry = CapabilityRegistry(store)
    bootstrap_native(registry)
    return store, Synthesizer(registry)


def test_extract_code_handles_fences_and_raw():
    assert extract_code("```python\nx = 1\n```") == "x = 1"
    assert extract_code("plain code") == "plain code"
    assert extract_code("") == ""


def test_code_prompt_contains_examples():
    system, user = code_prompt("slugify text", EXAMPLES)
    assert "slugify text" in user
    assert "Hello World" in user
    assert "system" in system.lower() or "python" in system.lower()


def test_openai_compat_expert_parses_response():
    captured = {}

    def fake_post(url, headers, payload):
        captured["url"] = url
        captured["model"] = payload["model"]
        return {"choices": [{"message": {"content": "hello"}}]}

    expert = OpenAICompatExpert("x", "https://example/v1", "key", "m", post=fake_post)
    assert expert.complete("s", "u") == "hello"
    assert captured["url"] == "https://example/v1/chat/completions"
    assert captured["model"] == "m"


def test_expert_without_key_raises():
    try:
        GroqExpert(api_key="").complete("s", "u")
    except ExpertError as exc:
        assert "api key" in str(exc)
    else:
        raise AssertionError("expected ExpertError")


def test_ensemble_falls_back_to_a_working_expert():
    ensemble = EnsembleExpert([BrokenExpert(), FakeExpert([GOOD], name="good")])
    assert ensemble.complete("s", "u") == GOOD
    results = ensemble.complete_all("s", "u")
    assert ("broken", "") in results


def test_acquire_without_experts_is_honest():
    store, synth = _synth()
    result = ExpertAcquirer(synth, []).acquire(
        "text.slug", "slug", ("text",), ("slug",), EXAMPLES, use_program_search=False
    )
    assert result.admitted is False
    assert "no external expert" in result.reason
    store.close()


def test_acquire_admits_a_verified_candidate():
    store, synth = _synth()
    acquirer = ExpertAcquirer(synth, [FakeExpert([GOOD])])
    result = acquirer.acquire(
        "text.slug", "slugify text", ("text",), ("slug",), EXAMPLES, use_program_search=False
    )
    assert result.admitted is True
    assert result.capability.status == "admitted"
    assert synth.registry.invoke("text.slug", {"value": "Hi There"}) == {"value": "hi-there"}
    store.close()


def test_acquire_rejects_a_wrong_candidate():
    store, synth = _synth()
    result = ExpertAcquirer(synth, [FakeExpert([BAD])]).acquire(
        "text.slug",
        "slugify text",
        ("text",),
        ("slug",),
        EXAMPLES,
        rounds=1,
        use_program_search=False,
    )
    assert result.admitted is False
    assert result.attempts[0]["admitted"] is False
    store.close()


def test_acquire_repairs_after_a_failed_round():
    store, synth = _synth()
    expert = FakeExpert([BAD, GOOD])
    result = ExpertAcquirer(synth, [expert]).acquire(
        "text.slug",
        "slugify text",
        ("text",),
        ("slug",),
        EXAMPLES,
        rounds=2,
        use_program_search=False,
    )
    assert result.admitted is True
    assert expert.calls == 2
    assert [a["admitted"] for a in result.attempts] == [False, True]
    store.close()


def test_acquire_synthesizes_without_any_expert():
    store, synth = _synth()
    result = ExpertAcquirer(synth, []).acquire(
        "text.slug", "slugify text", ("text",), ("slug",), EXAMPLES
    )
    assert result.admitted is True
    assert result.source == "enumerative"
    assert result.attempts[0]["program"] == "slug"
    assert synth.registry.invoke("text.slug", {"value": "Hi There"}) == {"value": "hi-there"}
    store.close()
