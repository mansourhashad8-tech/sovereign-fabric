import pytest

from sovereign.capabilities import CapabilityRegistry
from sovereign.extras import bootstrap_extras
from sovereign.extras import quantum_grover, quantum_simulate
from sovereign.quantum import grover_search, simulate_circuit
from sovereign.store import FabricStore


def test_hadamard_and_interference():
    assert simulate_circuit(1, [{"gate": "h", "target": 0}])["probabilities"] == [0.5, 0.5]
    assert simulate_circuit(
        1, [{"gate": "h", "target": 0}, {"gate": "h", "target": 0}]
    )["probabilities"] == [1.0, 0.0]


def test_bell_state_is_entangled():
    result = simulate_circuit(
        2,
        [
            {"gate": "h", "target": 0},
            {"gate": "cx", "control": 0, "target": 1},
        ],
    )
    assert result["probabilities"] == [0.5, 0.0, 0.0, 0.5]


def test_rotation_and_swap_gates():
    result = simulate_circuit(1, [{"gate": "rx", "target": 0, "theta": 3.141592653589793}])
    assert result["probabilities"][1] > 0.999999
    swapped = simulate_circuit(
        2,
        [
            {"gate": "x", "target": 0},
            {"gate": "swap", "control": 0, "target": 1},
        ],
    )
    assert swapped["probabilities"] == [0.0, 0.0, 1.0, 0.0]


def test_grover_amplifies_one_marked_state():
    result = grover_search(2, [3], iterations=1)
    assert result["marked_probability"] == 1.0
    assert result["probabilities"][3] == 1.0


def test_quantum_capabilities_are_registered_and_bounded():
    registry = CapabilityRegistry(FabricStore())
    bootstrap_extras(registry)
    assert registry.active("quantum.simulate") is not None
    assert registry.active("quantum.grover") is not None
    assert quantum_simulate(
        {"qubits": 1, "gates": [{"gate": "x", "target": 0}]}
    )["value"]["probabilities"] == [0.0, 1.0]
    assert quantum_grover({"qubits": 2, "marked": [2], "iterations": 1})["value"][
        "probabilities"
    ][2] == 1.0
    with pytest.raises(ValueError):
        simulate_circuit(9, [])
    with pytest.raises(ValueError):
        simulate_circuit(1, [{"gate": "unknown", "target": 0}])
    with pytest.raises(ValueError):
        grover_search(7, [0])
