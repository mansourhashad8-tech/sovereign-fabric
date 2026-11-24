"""Multi-expert, multi-candidate acquisition with iterative repair.

Ask every configured expert for an implementation, verify each candidate
against the examples, and if none passes, feed the failures back and ask again.
The first candidate that reproduces every example is admitted through the same
gate as any other synthesized capability.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .expert import Expert, code_prompt, extract_code
from .models import Capability
from .synthesis import Synthesizer


@dataclass
class AcquireResult:
    admitted: bool
    reason: str
    source: str = ""
    capability: Capability | None = None
    attempts: list[dict[str, Any]] = field(default_factory=list)


class ExpertAcquirer:
    def __init__(self, synthesizer: Synthesizer, experts: list[Expert]) -> None:
        self.synthesizer = synthesizer
        self.experts = list(experts)

    def acquire(
        self,
        name: str,
        description: str,
        inputs: tuple[str, ...],
        outputs: tuple[str, ...],
        examples: list[Any],
        rounds: int = 2,
    ) -> AcquireResult:
        pairs = [(dict(given), dict(expected)) for given, expected in examples]
        if not self.experts:
            return AcquireResult(False, "no external expert is configured")
        if not pairs:
            return AcquireResult(False, "no examples to verify against")

        attempts: list[dict[str, Any]] = []
        failures: list[str] = []
        for round_index in range(max(1, rounds)):
            system, user = code_prompt(description, pairs, failures)
            produced = False
            for expert in self.experts:
                try:
                    text = expert.complete(system, user)
                except Exception as exc:
                    attempts.append(
                        {
                            "round": round_index,
                            "expert": expert.name,
                            "error": f"{type(exc).__name__}: {exc}",
                        }
                    )
                    continue
                source = extract_code(text)
                if not source:
                    attempts.append(
                        {"round": round_index, "expert": expert.name, "error": "empty output"}
                    )
                    continue
                produced = True
                result = self.synthesizer.verify(source, pairs)
                attempts.append(
                    {
                        "round": round_index,
                        "expert": expert.name,
                        "admitted": result.admitted,
                        "passed": result.passed,
                        "failed": result.failed,
                    }
                )
                if result.admitted:
                    synthesized = self.synthesizer.synthesize(
                        name=name,
                        description=description,
                        inputs=inputs,
                        outputs=outputs,
                        spec={"source": source},
                        examples=pairs,
                    )
                    return AcquireResult(
                        True,
                        synthesized.reason,
                        source,
                        synthesized.capability,
                        attempts,
                    )
                failures.extend(result.failures)
            if not produced:
                break

        return AcquireResult(
            False, "no expert candidate reproduced every example", "", None, attempts
        )
