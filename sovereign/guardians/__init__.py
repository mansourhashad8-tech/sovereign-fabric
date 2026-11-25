from .base import (
    ConsultationResult,
    Guardian,
    GuardianRegistry,
    HttpGuardian,
    default_fetch,
)
from .sources import (
    ArxivGuardian,
    CrossrefGuardian,
    DataCiteGuardian,
    GithubGuardian,
    HackerNewsGuardian,
    HuggingFaceGuardian,
    LocalGuardian,
    NpmGuardian,
    PubMedGuardian,
    OpenAlexGuardian,
    PyPIGuardian,
    SemanticScholarGuardian,
    StackExchangeGuardian,
    WikipediaGuardian,
    ZenodoGuardian,
)

__all__ = [
    "ConsultationResult",
    "Guardian",
    "GuardianRegistry",
    "HttpGuardian",
    "default_fetch",
    "ArxivGuardian",
    "CrossrefGuardian",
    "DataCiteGuardian",
    "GithubGuardian",
    "HackerNewsGuardian",
    "HuggingFaceGuardian",
    "LocalGuardian",
    "NpmGuardian",
    "PubMedGuardian",
    "OpenAlexGuardian",
    "PyPIGuardian",
    "SemanticScholarGuardian",
    "StackExchangeGuardian",
    "WikipediaGuardian",
    "ZenodoGuardian",
]


def default_registry(store=None) -> GuardianRegistry:
    """Fifteen sources, including an offline corpus. A dead network still answers."""
    return GuardianRegistry(
        [
            ArxivGuardian(store=store),
            OpenAlexGuardian(store=store),
            SemanticScholarGuardian(store=store),
            CrossrefGuardian(store=store),
            GithubGuardian(store=store),
            HackerNewsGuardian(store=store),
            HuggingFaceGuardian(store=store),
            PyPIGuardian(store=store),
            NpmGuardian(store=store),
            WikipediaGuardian(store=store),
            StackExchangeGuardian(store=store),
            ZenodoGuardian(store=store),
            DataCiteGuardian(store=store),
            PubMedGuardian(store=store),
            LocalGuardian(),
        ]
    )
