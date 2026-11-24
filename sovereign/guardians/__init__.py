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
    GithubGuardian,
    HackerNewsGuardian,
    HuggingFaceGuardian,
    LocalGuardian,
    NpmGuardian,
    OpenAlexGuardian,
    PyPIGuardian,
    SemanticScholarGuardian,
)

__all__ = [
    "ConsultationResult",
    "Guardian",
    "GuardianRegistry",
    "HttpGuardian",
    "default_fetch",
    "ArxivGuardian",
    "CrossrefGuardian",
    "GithubGuardian",
    "HackerNewsGuardian",
    "HuggingFaceGuardian",
    "LocalGuardian",
    "NpmGuardian",
    "OpenAlexGuardian",
    "PyPIGuardian",
    "SemanticScholarGuardian",
]


def default_registry(store=None) -> GuardianRegistry:
    """Ten sources, including an offline corpus. A dead network still answers."""
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
            LocalGuardian(),
        ]
    )
