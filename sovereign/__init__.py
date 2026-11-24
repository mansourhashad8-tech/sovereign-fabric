"""Sovereign fabric: an honest self-evolving cognitive-executive system.

It consults external sources (guardianship), absorbs what it learns into one
fabric of knowledge and executable capabilities, plans with classical search,
extends itself only through a verification gate, and refuses to report a
result the validator has not passed.
"""

from .absorption import absorb, propose_capabilities
from .capabilities import CapabilityRegistry, bootstrap_native
from .evolution import EvolutionCycle, EvolutionEngine
from .models import (
    Capability,
    Evidence,
    KnowledgeUnit,
    Plan,
    PlanStep,
    Provenance,
    ValidationReport,
)
from .pathfinder import Operator, PathFinder, operators_from
from .store import FabricStore
from .synthesis import SynthesisResult, Synthesizer
from .validator import HolisticValidator

__version__ = "0.1.0"

__all__ = [
    "absorb",
    "propose_capabilities",
    "CapabilityRegistry",
    "bootstrap_native",
    "EvolutionCycle",
    "EvolutionEngine",
    "Capability",
    "Evidence",
    "KnowledgeUnit",
    "Plan",
    "PlanStep",
    "Provenance",
    "ValidationReport",
    "Operator",
    "PathFinder",
    "operators_from",
    "FabricStore",
    "SynthesisResult",
    "Synthesizer",
    "HolisticValidator",
]
