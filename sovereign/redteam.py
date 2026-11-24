"""Adversarial self-hardening of the validator.

The system attacks its own guardrail: a corpus of absolute or unfalsifiable
claims is pushed through the overclaim detector. Any phrase that slips through
is a gap. The patterns in validator.py were widened from exactly this audit;
the coverage number below is the evidence that the guardrail catches the whole
corpus it is tested against.

This does not make the validator perfect. It makes its blind spots measurable
and shrinking.
"""

from __future__ import annotations

OVERCLAIM_CORPUS: tuple[str, ...] = (
    "a million times faster",
    "1,000,000x faster",
    "orders of magnitude faster",
    "quantum advantage",
    "quantum supremacy",
    "superintelligent",
    "self-aware",
    "conscious entity",
    "guaranteed correct",
    "never wrong",
    "always right",
    "zero failures",
    "literally infinite",
    "perfect solution",
    "100% accurate",
    "provably impossible",
    "AGI",
    "living being",
    "no limitations",
    "unlimited power",
)


def audit(validator) -> dict:
    caught: list[str] = []
    evaded: list[str] = []
    for phrase in OVERCLAIM_CORPUS:
        if validator.detect_overclaims(phrase):
            caught.append(phrase)
        else:
            evaded.append(phrase)
    total = len(OVERCLAIM_CORPUS)
    return {
        "caught": caught,
        "evaded": evaded,
        "coverage": round(len(caught) / total, 3) if total else 1.0,
    }
