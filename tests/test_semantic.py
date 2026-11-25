from sovereign.semantic import SemanticIndex


def test_ppmi_index_ranks_shared_context_above_unrelated():
    index = SemanticIndex(
        {
            "a": "sqlite write ahead logging",
            "b": "planning state space search",
            "c": "write ahead log",
        }
    )
    scores = index.scores("logging")
    assert scores["a"] > scores["b"]
    assert scores["c"] > scores["b"]


def test_unknown_query_returns_zeroes_not_a_crash():
    index = SemanticIndex({"a": "sqlite write ahead logging"})
    assert index.scores("zzzz") == {"a": 0.0}


def test_index_is_deterministic():
    documents = {"a": "alpha beta gamma", "b": "beta gamma delta"}
    first = SemanticIndex(documents).scores("beta")
    second = SemanticIndex(documents).scores("beta")
    assert first == second
