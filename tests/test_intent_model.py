from sovereign.intent import parse_intent
from sovereign.intent_model import IntentModel


def test_held_out_accuracy_is_measured():
    model = IntentModel()
    result = model.evaluate(
        [
            ("ما هي لغة النص", "language"),
            ("remove private data", "redact"),
            ("recognize named entities", "entities"),
            ("pretty print this json", "json"),
            ("how many words", "counts"),
            ("tokenize the sentence", "tokens"),
            ("write a markdown report", "markdown"),
            ("calculate 8 + 9", "math"),
            ("parse the link", "url"),
            ("summarize the article", "summary"),
        ]
    )
    assert result["examples"] == 10
    assert result["accuracy"] >= 0.8


def test_online_learning_changes_the_status():
    model = IntentModel()
    before = model.status()
    assert model.learn("please produce a concise summary", "summary") is True
    after = model.status()
    assert after["documents"] == before["documents"] + 1
    assert after["updates"] == before["updates"] + 1
    assert model.learn("", "summary") is False


def test_classifier_fallback_routes_a_phrase_the_rules_miss():
    intent = parse_intent("show key phrases")
    assert intent["goal_type"] == "keywords"
    assert intent["matched"] == "model:keywords"


def test_unknown_request_stays_markdown():
    intent = parse_intent("hello there")
    assert intent["goal_type"] == "markdown"
    assert intent["matched"] is None
