from sovereign.guardians import (
    ArxivGuardian,
    GithubGuardian,
    HackerNewsGuardian,
    LocalGuardian,
    OpenAlexGuardian,
    PyPIGuardian,
)
from sovereign.guardians.base import GuardianRegistry
from sovereign.store import FabricStore

ARXIV_XML = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2401.00001v1</id>
    <published>2026-01-02T00:00:00Z</published>
    <title>Planning   as   Graph   Search</title>
    <summary>We study forward search over state spaces.</summary>
    <category term="cs.AI"/>
    <category term="cs.LO"/>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2401.00002v1</id>
    <title> </title>
    <summary>empty title entry should be skipped</summary>
  </entry>
</feed>"""

OPENALEX_JSON = """{
  "results": [
    {
      "id": "https://openalex.org/W1",
      "title": "A Study of Planners",
      "publication_date": "2026-02-01",
      "abstract_inverted_index": {"We": [0], "plan": [1], "ahead.": [2]},
      "topics": [{"display_name": "Automated Planning"}, {"display_name": "Search"}]
    }
  ]
}"""

GITHUB_JSON = """{
  "items": [
    {
      "full_name": "acme/planner",
      "html_url": "https://github.com/acme/planner",
      "description": "A fast planner",
      "stargazers_count": 1000,
      "topics": ["planning", "search"],
      "license": {"spdx_id": "MIT"}
    }
  ]
}"""

HN_JSON = """{
  "hits": [
    {"title": "Show HN: planner", "url": "https://example.com/p", "points": 100,
     "objectID": "42", "created_at": "2026-03-01T00:00:00Z"}
  ]
}"""

PYPI_JSON = """{
  "info": {"name": "planner", "summary": "Plan things", "home_page": "https://pypi.org/project/planner/",
           "keywords": "planning, search", "license": "MIT"}
}"""


def _fixed(body):
    return lambda url: body


def test_arxiv_parsing():
    g = ArxivGuardian(fetch=_fixed(ARXIV_XML), min_interval=0)
    units = g.search("planning", limit=5)
    assert len(units) == 1
    unit = units[0]
    assert unit.title == "Planning as Graph Search"
    assert unit.provenance.source == "arxiv"
    assert unit.provenance.url.endswith("2401.00001v1")
    assert "cs.AI" in unit.concepts
    assert unit.provenance.retrieved_at.startswith("2026-01-02")


def test_openalex_abstract_reconstruction():
    g = OpenAlexGuardian(fetch=_fixed(OPENALEX_JSON), min_interval=0)
    units = g.search("planner", limit=5)
    assert len(units) == 1
    assert units[0].summary == "We plan ahead."
    assert units[0].provenance.license == "CC0"
    assert "Automated Planning" in units[0].concepts


def test_github_parsing_and_confidence():
    g = GithubGuardian(fetch=_fixed(GITHUB_JSON), min_interval=0)
    units = g.search("planner", limit=5)
    assert units[0].title == "acme/planner"
    assert units[0].provenance.license == "MIT"
    assert units[0].provenance.confidence > 0.5


def test_hackernews_parsing():
    g = HackerNewsGuardian(fetch=_fixed(HN_JSON), min_interval=0)
    units = g.search("planner", limit=5)
    assert units[0].title == "Show HN: planner"
    assert units[0].provenance.url == "https://example.com/p"


def test_pypi_parsing_and_404_returns_empty():
    g = PyPIGuardian(fetch=_fixed(PYPI_JSON), min_interval=0)
    units = g.search("planner", limit=5)
    assert units[0].title == "planner"
    assert "planning" in units[0].concepts

    def boom(url):
        raise ValueError("404")

    failing = PyPIGuardian(fetch=boom, min_interval=0)
    assert failing.search("missing", limit=5) == []


def test_local_guardian_matches_by_meaning():
    g = LocalGuardian()
    units = g.search("priority queue heuristic search", limit=3)
    assert units
    assert any("Best-first" in u.title for u in units)
    assert g.search("qqqq wwww eeee", limit=3) == []


def test_guardian_cache_avoids_second_fetch():
    calls = {"n": 0}

    def fetch(url):
        calls["n"] += 1
        return OPENALEX_JSON

    store = FabricStore()
    g = OpenAlexGuardian(fetch=fetch, store=store, min_interval=0)
    g.search("planner")
    g.search("planner")
    assert calls["n"] == 1
    store.close()


def test_registry_degrades_when_a_source_fails():
    class Boom:
        name = "boom"

        def search(self, query, limit=5):
            raise RuntimeError("network down")

    registry = GuardianRegistry([Boom(), LocalGuardian()])
    result = registry.consult("planning search", limit=3)
    assert result.sources["boom"].startswith("error:")
    assert result.sources["local"] == "ok"
    assert result.units  # local still answered


def test_registry_dedupes_by_url():
    from sovereign.models import KnowledgeUnit, Provenance

    def make(title, url):
        return KnowledgeUnit(
            id=title, title=title, summary="", provenance=Provenance(source="s", url=url)
        )

    class Dup:
        name = "dup"

        def search(self, query, limit=5):
            return [make("A", "http://x"), make("A again", "http://x")]

    registry = GuardianRegistry([Dup()])
    result = registry.consult("q")
    assert len(result.units) == 1


S2_JSON = """{"data":[{"title":"Planner Paper","abstract":"We plan ahead.",
 "url":"https://s2/1","year":2026,"venue":"ICML","fieldsOfStudy":["Computer Science"]}]}"""

CROSSREF_JSON = """{"message":{"items":[{"title":["Crossref Paper"],"URL":"https://doi/1",
 "abstract":"<jats:p>Abstract text.</jats:p>","issued":{"date-parts":[[2025,3,1]]},
 "container-title":["Journal of Planning"],"license":[{"URL":"https://lic"}]}]}}"""

HF_JSON = """[{"modelId":"org/model","downloads":1000,"pipeline_tag":"text-generation",
 "tags":["nlp","transformer"]}]"""

NPM_JSON = """{"objects":[{"package":{"name":"planner","description":"Plan things",
 "links":{"npm":"https://npm/planner"},"keywords":["planning"]},"score":{"final":0.9}}]}"""


def test_semantic_scholar_parsing():
    from sovereign.guardians import SemanticScholarGuardian
    g = SemanticScholarGuardian(fetch=_fixed(S2_JSON), min_interval=0)
    units = g.search("planner", limit=5)
    assert units[0].title == "Planner Paper"
    assert units[0].provenance.source == "semanticscholar"
    assert units[0].provenance.retrieved_at.startswith("2026")
    assert "Computer Science" in units[0].concepts


def test_crossref_parsing_strips_jats():
    from sovereign.guardians import CrossrefGuardian
    g = CrossrefGuardian(fetch=_fixed(CROSSREF_JSON), min_interval=0)
    units = g.search("planner", limit=5)
    assert units[0].title == "Crossref Paper"
    assert units[0].summary == "Abstract text."
    assert units[0].provenance.retrieved_at.startswith("2025")
    assert units[0].provenance.license == "https://lic"


def test_huggingface_parsing():
    from sovereign.guardians import HuggingFaceGuardian
    g = HuggingFaceGuardian(fetch=_fixed(HF_JSON), min_interval=0)
    units = g.search("planner", limit=5)
    assert units[0].title == "org/model"
    assert units[0].summary == "text-generation"
    assert units[0].provenance.url == "https://huggingface.co/org/model"
    assert units[0].provenance.confidence > 0.5


def test_npm_parsing():
    from sovereign.guardians import NpmGuardian
    g = NpmGuardian(fetch=_fixed(NPM_JSON), min_interval=0)
    units = g.search("planner", limit=5)
    assert units[0].title == "planner"
    assert units[0].provenance.url == "https://npm/planner"
    assert "planning" in units[0].concepts


def test_default_registry_has_ten_sources():
    from sovereign.guardians import default_registry
    names = default_registry().names()
    assert len(names) == 10
    assert {"arxiv", "openalex", "semanticscholar", "crossref", "github",
            "hackernews", "huggingface", "pypi", "npm", "local"} == set(names)
