"""Exact statevector simulation for small circuits.

This is a deterministic simulator, not quantum hardware and not a speedup.
It exists so a request can be checked against real gate mathematics with a
bounded memory ceiling (8 qubits = 256 amplitudes).
"""

from __future__ import annotations

import cmath
import math
from typing import Any

MAX_QUBITS = 8
MAX_GATES = 64
MAX_GROVER_QUBITS = 6
MAX_GROVER_ITERATIONS = 10

Matrix = tuple[tuple[complex, complex], tuple[complex, complex]]


def _single(matrix: Matrix, target: int, qubits: int, state: list[complex]) -> None:
    step = 1 << target
    for base in range(0, 1 << qubits, step << 1):
        for offset in range(step):
            i = base + offset
            j = i + step
            a, b = state[i], state[j]
            state[i] = matrix[0][0] * a + matrix[0][1] * b
            state[j] = matrix[1][0] * a + matrix[1][1] * b


def _controlled_single(
    matrix: Matrix, target: int, control: int, qubits: int, state: list[complex]
) -> None:
    step = 1 << target
    for base in range(0, 1 << qubits, step << 1):
        for offset in range(step):
            i = base + offset
            j = i + step
            if not (i >> control) & 1:
                continue
            a, b = state[i], state[j]
            state[i] = matrix[0][0] * a + matrix[0][1] * b
            state[j] = matrix[1][0] * a + matrix[1][1] * b


def _matrix(name: str, theta: float) -> Matrix:
    if name == "x":
        return ((0, 1), (1, 0))
    if name == "y":
        return ((0, -1j), (1j, 0))
    if name == "z":
        return ((1, 0), (0, -1))
    if name == "h":
        scale = 1 / math.sqrt(2)
        return ((scale, scale), (scale, -scale))
    if name == "s":
        return ((1, 0), (0, 1j))
    if name == "t":
        return ((1, 0), (0, cmath.exp(1j * math.pi / 4)))
    if name == "rx":
        c, s = math.cos(theta / 2), math.sin(theta / 2)
        return ((c, -1j * s), (-1j * s, c))
    if name == "ry":
        c, s = math.cos(theta / 2), math.sin(theta / 2)
        return ((c, -s), (s, c))
    if name == "rz":
        return ((cmath.exp(-1j * theta / 2), 0), (0, cmath.exp(1j * theta / 2)))
    raise ValueError(f"unknown gate {name!r}")


def _probability(state: list[complex]) -> list[float]:
    return [round(abs(amplitude) ** 2, 12) for amplitude in state]


def simulate_circuit(qubits: int, gates: list[dict[str, Any]]) -> dict[str, Any]:
    if isinstance(qubits, bool) or not isinstance(qubits, int) or not 1 <= qubits <= MAX_QUBITS:
        raise ValueError(f"qubits must be an integer from 1 to {MAX_QUBITS}")
    if not isinstance(gates, list) or len(gates) > MAX_GATES:
        raise ValueError(f"gates must be a list of at most {MAX_GATES} items")
    state = [0j] * (1 << qubits)
    state[0] = 1 + 0j
    for index, gate in enumerate(gates):
        if not isinstance(gate, dict):
            raise ValueError(f"gate {index} must be an object")
        name = str(gate.get("gate", "")).lower()
        if name in {"cx", "cnot", "cz", "swap"}:
            control = gate.get("control")
            target = gate.get("target")
            for label, value in (("control", control), ("target", target)):
                if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value < qubits:
                    raise ValueError(f"gate {index} has invalid {label}")
            if control == target:
                raise ValueError(f"gate {index} needs distinct control and target")
            for basis in range(1 << qubits):
                if not (basis >> control) & 1:
                    continue
                if name == "cz":
                    if (basis >> target) & 1:
                        state[basis] = -state[basis]
                elif name == "swap":
                    other = basis ^ (1 << target) ^ (1 << control)
                    if basis < other:
                        state[basis], state[other] = state[other], state[basis]
                else:
                    _controlled_single(_matrix("x", 0), target, control, qubits, state)
                    break
            continue
        target = gate.get("target")
        if isinstance(target, bool) or not isinstance(target, int) or not 0 <= target < qubits:
            raise ValueError(f"gate {index} has invalid target")
        theta = float(gate.get("theta", 0.0))
        if not math.isfinite(theta):
            raise ValueError(f"gate {index} has a non-finite theta")
        _single(_matrix(name, theta), target, qubits, state)
    probabilities = _probability(state)
    return {
        "qubits": qubits,
        "gates": len(gates),
        "probabilities": probabilities,
        "nonzero": sum(1 for value in probabilities if value > 1e-12),
        "unit_norm": round(sum(probabilities), 12),
    }


def grover_search(
    qubits: int, marked: list[int], iterations: int | None = None
) -> dict[str, Any]:
    if isinstance(qubits, bool) or not isinstance(qubits, int) or not 1 <= qubits <= MAX_GROVER_QUBITS:
        raise ValueError(f"qubits must be an integer from 1 to {MAX_GROVER_QUBITS}")
    size = 1 << qubits
    targets = {int(item) for item in marked}
    if not targets or any(item < 0 or item >= size for item in targets):
        raise ValueError("marked must contain at least one valid basis-state index")
    if iterations is None:
        iterations = max(1, int(math.pi / 4 * math.sqrt(size)))
    if isinstance(iterations, bool) or not isinstance(iterations, int):
        raise ValueError("iterations must be an integer")
    if not 1 <= iterations <= MAX_GROVER_ITERATIONS:
        raise ValueError(f"iterations must be from 1 to {MAX_GROVER_ITERATIONS}")
    state = [1 / math.sqrt(size)] * size
    for _ in range(iterations):
        for index in targets:
            state[index] = -state[index]
        mean = sum(state) / size
        state = [2 * mean - amplitude for amplitude in state]
    probabilities = _probability(state)
    return {
        "qubits": qubits,
        "marked": sorted(targets),
        "iterations": iterations,
        "probabilities": probabilities,
        "marked_probability": round(sum(probabilities[i] for i in targets), 12),
        "unit_norm": round(sum(probabilities), 12),
    }
