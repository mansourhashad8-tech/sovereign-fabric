"""Sovereign fabric: an honest self-evolving cognitive-executive system.

It consults external sources (guardianship), absorbs what it learns into one
fabric of knowledge and executable capabilities, plans with classical search,
extends itself only through a verification gate, and refuses to report a
result the validator has not passed.
"""

from .absorption import absorb, propose_capabilities
from .autonomy import assess, reward_ledger
from .capabilities import CapabilityRegistry, bootstrap_native
from .collective import collective_status, export_bundle, import_bundle
from .diagnostics import diagnose
from .extras import bootstrap_extras
from .feedback import feedback_scores, feedback_summary, record_feedback
from .metrics import Metrics
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
from .graphalg import pagerank, shortest_path
from .immunity import ImmuneSystem
from .pathfinder import Operator, PathFinder, operators_from
from .media import image_info, wav_info
from .pipeline import run_pipeline
from .protocol import DeterministicProtocol, audit_language
from .quantum import grover_search, simulate_circuit
from .repair import repair
from .store import FabricStore
from .toolbox import TOOLBOX, bootstrap_toolbox
from .synthesis import SynthesisResult, Synthesizer
from .validator import HolisticValidator

__version__ = "0.1.0"

__all__ = [
    "absorb",
    "propose_capabilities",
    "ImmuneSystem",
    "assess",
    "reward_ledger",
    "collective_status",
    "export_bundle",
    "import_bundle",
    "DeterministicProtocol",
    "TOOLBOX",
    "bootstrap_toolbox",
    "audit_language",
    "CapabilityRegistry",
    "bootstrap_native",
    "bootstrap_extras",
    "diagnose",
    "Metrics",
    "run_pipeline",
    "image_info",
    "wav_info",
    "pagerank",
    "shortest_path",
    "grover_search",
    "simulate_circuit",
    "feedback_scores",
    "feedback_summary",
    "record_feedback",
    "repair",
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
