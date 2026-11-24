from .base import (
    ConsultationResult,
    Guardian,
    GuardianRegistry,
    HttpGuardian,
    default_fetch,
)
from .sources import (
    ArxivGuardian,
    GithubGuardian,
    HackerNewsGuardian,
    LocalGuardian,
    OpenAlexGuardian,
    PyPIGuardian,
)

__all__ = [
    "ConsultationResult",
    "Guardian",
    "GuardianRegistry",
    "HttpGuardian",
    "default_fetch",
    "ArxivGuardian",
    "GithubGuardian",
    "HackerNewsGuardian",
    "LocalGuardian",
    "OpenAlexGuardian",
    "PyPIGuardian",
]


def default_registry(store=None) -> GuardianRegistry:
    """Network guardians plus the offline corpus. A dead network still answers."""
    return GuardianRegistry(
        [
            ArxivGuardian(store=store),
            OpenAlexGuardian(store=store),
            GithubGuardian(store=store),
            HackerNewsGuardian(store=store),
            PyPIGuardian(store=store),
            LocalGuardian(),
        ]
    )
