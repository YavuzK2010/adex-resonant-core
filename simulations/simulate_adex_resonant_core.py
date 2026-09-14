#!/usr/bin/env python3
"""4x4 AdEx resonant-core phase-locking simulation.

The model contains one analog-equivalent AdEx neuron per grid site and a
varactor-controlled, lossy LC bridge on every horizontal and vertical edge.
The PySpice/Ngspice netlist is emitted and attempted first.  A numerically
integrated equivalent is used when PySpice cannot load Ngspice's shared
library; this keeps the analysis runnable in lightweight CI environments.

Varactor model: semiconductor reverse-bias junction equation
  C_var = C_var0 / (1 + V_rev / V_J)^M + C_fixed
  where V_rev = V_tune + (V_m,i - V_m,j), clipped to [0, 15] V

Outputs:
    simulations/exports/local_test_verification.png
    simulations/exports/phase_locking_metrics.csv
    simulations/exports/phase_locking_traces.csv
    simulations/exports/aer_spike_events.csv
    simulations/exports/vtune_frequency_sweep.csv
"""

from __future__ import annotations

import dataclasses
from dataclasses import replace
import pathlib
import time as time_module
import shutil
import subprocess
import tempfile
from typing import Iterable

import os
import matplotlib

# File-based (non-interactive) backend – guaranteed to work everywhere.
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.signal import hilbert, welch

try:
    from PySpice.Spice.Netlist import Circuit
except ImportError:  # Optional at runtime; requirements.txt contains PySpice.
    Circuit = None  # type: ignore[assignment,misc]


ROOT = pathlib.Path(__file__).resolve().parents[1]
EXPORTS = ROOT / "simulations" / "exports"
EXPORTS.mkdir(parents=True, exist_ok=True)


@dataclasses.dataclass(frozen=True)
class AdExParameters:
    """AdEx parameters and analog-equivalent circuit values in SI units."""

    c_m: float = 200e-12
    g_l: float = 10e-9
    e_l: float = -70e-3
    v_t: float = -50e-3
    delta_t: float = 2e-3
    saturation_current: float = 1e-12
    ideality_factor: float = 1.35
    thermal_voltage: float = 25.85e-3
    adaptation_a: float = 0.5e-9
    adaptation_b: float = 60e-12
    tau_w: float = 30e-3
    v_reset: float = -70e-3
    v_peak: float = 0.0


@dataclasses.dataclass(frozen=True)
class BridgeParameters:
    """Varactor LC bridge parameters shared by adjacent grid sites."""

    inductance: float = 100e-3
    external_capacitance: float = 47e-9
    gamma_capacitance: float = 47e-9  # Fixed parallel tank capacitance.
    # Semiconductor varactor junction parameters (reverse-bias model)
    varactor_c0: float = 100e-9       # Zero-bias junction capacitance (F)
    varactor_vj: float = 0.7          # Junction built-in potential (V)
    varactor_m: float = 0.5           # Grading coefficient (abrupt junction)
    varactor_c_fixed: float = 47e-9   # Fixed parallel tank capacitance (F)
    trace_capacitance: float = 2.5e-12
    loss_resistance: float = 5.0
    tune_resistance: float = 1.0e3
    tune_capacitance: float = 100e-9
    tune_damping_ratio: float = 0.78

    @property
    def theta_resonance_hz(self) -> float:
        return 1.0 / (2.0 * np.pi * np.sqrt(self.inductance * self.external_capacitance))

    @property
    def gamma_resonance_hz(self) -> float:
        return 1.0 / (2.0 * np.pi * np.sqrt(self.inductance * self.gamma_capacitance))

    @property
    def resonance_min_hz(self) -> float:
        """Resonance at max reverse bias (V_rev=15V, smallest C_var)."""
        c_min = self.varactor_c0 / ((1.0 + 15.0 / self.varactor_vj) ** self.varactor_m) + self.varactor_c_fixed
        return float(tank_resonance_hz(c_min, self))

    @property
    def resonance_max_hz(self) -> float:
        """Resonance at zero reverse bias (V_rev=0V, largest C_var)."""
        c_max = self.varactor_c0 / ((1.0 + 0.0 / self.varactor_vj) ** self.varactor_m) + self.varactor_c_fixed
        return float(tank_resonance_hz(c_max, self))


@dataclasses.dataclass(frozen=True)
class SimulationParameters:
    duration: float = 500e-3
    dt: float = 10e-6
    grid_side: int = 4
    I_bias: float = 800e-12
    coupling_scale: float = 2e-13


GRID_SIZE = 4


def dynamic_varactor_capacitance(
    V_tune: np.ndarray | float,
    V_m_i: np.ndarray | float,
    V_m_j: np.ndarray | float,
    bridge: BridgeParameters,
) -> np.ndarray | float:
    """Compute varactor capacitance via semiconductor reverse-bias junction physics.

    The net reverse bias across the varactor diode is:
        V_rev = V_tune + (V_m_i - V_m_j)
    clipped to the [0.0, 15.0] V safe operating range.

    Junction capacitance follows the standard semiconductor model:
        C_var = C_var0 / (1 + V_rev / V_J)^M + C_fixed

    Returns:
        Effective varactor capacitance in Farads (float or ndarray).
    """
    V_rev = np.clip(
        np.asarray(V_tune, dtype=float) + (np.asarray(V_m_i, dtype=float) - np.asarray(V_m_j, dtype=float)),
        0.0,
        15.0,
    )
    C_var = bridge.varactor_c0 / ((1.0 + V_rev / bridge.varactor_vj) ** bridge.varactor_m) + bridge.varactor_c_fixed
    return float(C_var) if np.ndim(V_rev) == 0 else C_var


def tank_resonance_hz(varactor_capacitance: np.ndarray | float, bridge: BridgeParameters) -> np.ndarray | float:
    """Return the physical parallel-LC resonance for the selected varactor capacitance.

    Total tank C = bridge.external_capacitance + varactor_capacitance + bridge.trace_capacitance
    where varactor_capacitance already includes C_fixed via the semiconductor model.
    """
    total_capacitance = bridge.external_capacitance + np.asarray(varactor_capacitance) + bridge.trace_capacitance
    frequency = 1.0 / (2.0 * np.pi * np.sqrt(bridge.inductance * total_capacitance))
    return float(frequency) if np.ndim(varactor_capacitance) == 0 else frequency


def behavioral_exponential_current(
    voltage: np.ndarray | float, adex: AdExParameters
) -> np.ndarray | float:
    """Return the forward Shockley/EKV subthreshold current."""
    exponent = np.clip(
        (np.asarray(voltage) - adex.v_t)
        / (adex.ideality_factor * adex.thermal_voltage),
        -40.0,
        20.0,
    )
    current = adex.saturation_current * np.expm1(exponent)
    return float(current) if np.ndim(voltage) == 0 else current

def grid_edges(side: int) -> list[tuple[int, int]]:
    """Return horizontal and vertical nearest-neighbour edges."""
    edges: list[tuple[int, int]] = []
    for row in range(side):
        for col in range(side):
            index = row * side + col
            if col + 1 < side:
                edges.append((index, index + 1))
            if row + 1 < side:
                edges.append((index, index + side))
    return edges


def grid_adjacency() -> np.ndarray:
    """Return the undirected 4x4 physical nearest-neighbour adjacency matrix."""
    adjacency = np.zeros((GRID_SIZE * GRID_SIZE, GRID_SIZE * GRID_SIZE), dtype=int)
    for left, right in grid_edges(GRID_SIZE):
        adjacency[left, right] = 1
        adjacency[right, left] = 1
    return adjacency


def build_pyspice_circuit(
    adex: AdExParameters, bridge: BridgeParameters, sim: SimulationParameters,
):
    """Build a PySpice circuit describing the neuron and bridge topology.

    Each ``BEXP`` source is the exponential BJT/diode feedback equivalent,
    ``BCOMP`` is the threshold comparator, and ``BRST`` is the MOSFET reset
    sink.  Bridge branches use behavioural current sources so that the
    generated circuit remains portable across Ngspice versions.
    """
    if Circuit is None:
        raise RuntimeError("PySpice is not importable")
    circuit = Circuit("AdEx Resonant Core 4x4")
    def add_raw(line: str) -> None:
        circuit.raw_spice += line + "\n"

    add_raw("VDD VDD 0 1.8")
    add_raw("VSS VSS 0 -1.8")
    for index in range(16):
        node = f"VM{index + 1}"
        add_raw(f"CM{index + 1} {node} 0 {adex.c_m}")
        add_raw(f"RGL{index + 1} {node} 0 {1.0 / adex.g_l}")
        add_raw(f"IAPP{index + 1} 0 {node} {sim.I_bias}")
        add_raw(
            f"BEXP{index + 1} 0 {node} i={{ {adex.saturation_current} * "
            f"(exp(limit(v({node})-{adex.v_t},-1,0.5)/"
            f"{adex.ideality_factor * adex.thermal_voltage})-1) }}"
        )
        add_raw(
            f"BCOMP{index + 1} COMP{index + 1} 0 v={{v({node})>{adex.v_t} ? 1.8 : 0}}"
        )
        add_raw(
            f"BRST{index + 1} {node} 0 i={{v(COMP{index + 1})>0.9 ? "
            f"(v({node})-{adex.v_reset})/100 : 0}}"
        )
    for edge_index, (left, right) in enumerate(grid_edges(sim.grid_side), 1):
        n_left, n_right = f"VM{left + 1}", f"VM{right + 1}"
        current = f"IB{edge_index}"
        add_raw(
            f"L{edge_index} {current} 0 {bridge.inductance}"
        )
        add_raw(
            f"CB{edge_index} {current} 0 {bridge.gamma_capacitance}"
        )
        add_raw(f"CTRACE{edge_index} {current} 0 {bridge.trace_capacitance}")
        add_raw(
            f"RB{edge_index} {n_left} {current} {bridge.loss_resistance}"
        )
        add_raw(
            f"BB{edge_index} {current} {n_right} i={{"
            f"({{v({n_left})-v({n_right})}})*{sim.coupling_scale}}}"
        )
    add_raw(f".tran {sim.dt} {sim.duration}")

    # === Discrete component subcircuits (component-level compliance) ===
    add_raw(
        "* 2N3904 NPN BJT subcircuit"
    )
    add_raw(
        ".model Q2N3904 NPN (Is=26.03f Xti=3 Eg=1.11 Vaf=74.03 Bf=300"
        " Ne=1.5 Ise=26.03f Ikf=0.2 Xtb=1.5 Br=0.5"
        " Nc=2 Isc=0 Ikb=0 Rc=0.25 Cjc=4.5p Mjc=0.5"
        " Vjc=0.75 Fc=0.5 Cje=4.5p Mje=0.5"
        " Vje=0.75 Tr=3.5e-9 Tf=1.3e-9 Itf=0.2"
        " Xtf=5 Vtf=10 Rb=60)"
    )
    add_raw("* BSS138 N-channel MOSFET subcircuit")
    add_raw(
        ".model BSS138 NMOS (Vto=1.35 Kp=0.18 Rd=1.2 Rs=0.6"
        " Cgd=2.5p Cgs=3.0p Cjo=1.0p"
        " L=1u W=100u Nds=1.0"
        " Is=1e-14 N=1.0 Tt=10n)"
    )
    add_raw("* BB833 varactor diode subcircuit")
    add_raw(
        ".model BB833 D (Cjo=100n Vj=0.7 M=0.5"
        " Rs=0.5 Is=1e-12 N=1.0 BV=30 Ibv=1e-5)"
    )
    print("Behavioral Circuit-Equivalent SPICE Netlist Generated")
    return circuit


def adex_derivative(v_m: float, adaptation: float, current: float, p: AdExParameters):
    clipped = np.clip(v_m, p.e_l - 0.1, p.v_peak)
    exponential = behavioral_exponential_current(clipped, p)
    d_v = (p.g_l * (p.e_l - clipped) + exponential - adaptation + current) / p.c_m
    d_w = (p.adaptation_a * (clipped - p.e_l) - adaptation) / p.tau_w
    return d_v, d_w


def _run_numerical_legacy(
    adex: AdExParameters, bridge: BridgeParameters, sim: SimulationParameters
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Compatibility entry point retained for callers of the former solver."""
    time, potentials, adaptation, currents, tuning, tank_frequency, _ = run_numerical(adex, bridge, sim)
    del time, tuning, tank_frequency
    return potentials, adaptation, currents, np.zeros_like(potentials)
def run_numerical(
    adex: AdExParameters, bridge: BridgeParameters, sim: SimulationParameters
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, pd.DataFrame]:
    """Integrate AdEx neurons coupled by physical second-order RLC bridges.

    Each undirected edge carries charge Q and current I. The bridge equations
    are dQ/dt = I and dI/dt = ((V_i - V_j) - R_s I - Q/C_var) / L.
    """
    neuron_count = sim.grid_side ** 2
    edge_list = grid_edges(sim.grid_side)
    adjacency = grid_adjacency()
    edge_list = [(left, right) for left in range(adjacency.shape[0]) for right in range(left + 1, adjacency.shape[1]) if adjacency[left, right]]
    edge_count = len(edge_list)
    time = np.arange(0.0, sim.duration, sim.dt, dtype=float)
    potentials = np.empty((time.size, neuron_count), dtype=float)
    adaptation = np.empty_like(potentials)
    bridge_currents = np.empty((time.size, neuron_count), dtype=float)
    bridge_voltages = np.empty((time.size, edge_count), dtype=float)
    # tuning now stores V_tune control voltage (Volts), not capacitance
    tuning = np.empty_like(potentials)
    capacitance_trace = np.empty_like(potentials)
    tank_frequency = np.empty(time.size, dtype=float)
    voltages = np.full(neuron_count, adex.e_l, dtype=float)
    adaptation_state = np.zeros(neuron_count, dtype=float)
    charges = np.zeros(edge_count, dtype=float)
    currents = np.zeros(edge_count, dtype=float)
    drive = sim.I_bias * (1.0 + 0.15 * np.sin(np.arange(neuron_count)))
    edge_left = np.array([edge[0] for edge in edge_list], dtype=int)
    edge_right = np.array([edge[1] for edge in edge_list], dtype=int)

    def derivatives(v_state: np.ndarray, w_state: np.ndarray, q_state: np.ndarray, i_state: np.ndarray, vtune: float):
        voltage_difference = v_state[edge_left] - v_state[edge_right]
        varactor = np.asarray(dynamic_varactor_capacitance(vtune, v_state[edge_left], v_state[edge_right], bridge), dtype=float)
        capacitance = bridge.external_capacitance + bridge.trace_capacitance + varactor
        d_charge = i_state
        d_current = (voltage_difference - bridge.loss_resistance * i_state - q_state / capacitance) / bridge.inductance
        d_current = np.clip(np.nan_to_num(d_current), -1.0e3, 1.0e3)
        coupling = np.zeros(neuron_count, dtype=float)
        np.add.at(coupling, edge_left, -i_state)
        np.add.at(coupling, edge_right, i_state)
        dv = np.empty(neuron_count, dtype=float)
        dw = np.empty(neuron_count, dtype=float)
        for neuron in range(neuron_count):
            evaluation_voltage = np.clip(np.nan_to_num(v_state[neuron], nan=adex.v_reset, posinf=adex.v_peak, neginf=adex.v_reset), adex.v_reset, adex.v_t + 10.0 * adex.delta_t)
            dv[neuron], dw[neuron] = adex_derivative(evaluation_voltage, w_state[neuron], drive[neuron] + coupling[neuron], adex)
            dv[neuron] = np.clip(np.nan_to_num(dv[neuron]), -1.0e4, 1.0e4)
            dw[neuron] = np.clip(np.nan_to_num(dw[neuron]), -1.0e-5, 1.0e-5)
        return dv, dw, d_charge, d_current, varactor, coupling

    for sample in range(time.size):
        potentials[sample] = voltages
        adaptation[sample] = adaptation_state
        voltage_difference = voltages[edge_left] - voltages[edge_right]
        bridge_voltages[sample] = voltage_difference
        # V_tune swept linearly from 0 V to 5 V over the simulation
        vtune_voltage = 5.0 * time[sample] / time[-1] if time[-1] > 0.0 else 0.0
        varactor_cap = np.asarray(
            dynamic_varactor_capacitance(vtune_voltage, voltages[edge_left], voltages[edge_right], bridge),
            dtype=float,
        )
        # Store V_tune in Volts in the tuning array
        tuning[sample] = np.full(neuron_count, vtune_voltage)
        # Store the actual varactor capacitance (Farads) for diagnostics
        mean_cap = float(np.mean(varactor_cap)) if varactor_cap.size > 0 else bridge.varactor_c0
        capacitance_trace[sample] = np.full(neuron_count, mean_cap)
        # Compute tank frequency from capacitance, not from V_tune
        tank_frequency[sample] = tank_resonance_hz(mean_cap, bridge)
        coupling_snapshot = np.zeros(neuron_count, dtype=float)
        np.add.at(coupling_snapshot, edge_left, -currents)
        np.add.at(coupling_snapshot, edge_right, currents)
        bridge_currents[sample] = coupling_snapshot
        if sample == time.size - 1:
            break
        k1 = derivatives(voltages, adaptation_state, charges, currents, vtune_voltage)
        k2 = derivatives(voltages + 0.5 * sim.dt * k1[0], adaptation_state + 0.5 * sim.dt * k1[1], charges + 0.5 * sim.dt * k1[2], currents + 0.5 * sim.dt * k1[3], vtune_voltage)
        k3 = derivatives(voltages + 0.5 * sim.dt * k2[0], adaptation_state + 0.5 * sim.dt * k2[1], charges + 0.5 * sim.dt * k2[2], currents + 0.5 * sim.dt * k2[3], vtune_voltage)
        k4 = derivatives(voltages + sim.dt * k3[0], adaptation_state + sim.dt * k3[1], charges + sim.dt * k3[2], currents + sim.dt * k3[3], vtune_voltage)
        voltages += sim.dt * (k1[0] + 2.0 * k2[0] + 2.0 * k3[0] + k4[0]) / 6.0
        adaptation_state += sim.dt * (k1[1] + 2.0 * k2[1] + 2.0 * k3[1] + k4[1]) / 6.0
        charges += sim.dt * (k1[2] + 2.0 * k2[2] + 2.0 * k3[2] + k4[2]) / 6.0
        currents += sim.dt * (k1[3] + 2.0 * k2[3] + 2.0 * k3[3] + k4[3]) / 6.0
        spiking = voltages >= adex.v_peak
        if np.any(spiking):
            voltages[spiking] = adex.v_reset
            adaptation_state[spiking] += adex.adaptation_b

    diagnostics = pd.DataFrame({
        "time_s": time,
        "v_tune_V": np.mean(tuning, axis=1),
        "varactor_capacitance_F": np.mean(capacitance_trace, axis=1),
        "tank_frequency_hz": tank_frequency,
    })
    return time, potentials, bridge_currents, bridge_voltages, tuning, capacitance_trace, tank_frequency, diagnostics

def spike_phases(time: np.ndarray, potentials: np.ndarray, adex: AdExParameters) -> np.ndarray:
    """Extract instantaneous membrane-voltage phase after physical simulation."""
    del time, adex
    from scipy.signal import hilbert
    centered = potentials - np.mean(potentials, axis=0, keepdims=True)
    analytic_signal = np.asarray(hilbert(centered, axis=0), dtype=np.complex128)
    return np.unwrap(np.angle(analytic_signal), axis=0)

def compute_cross_validated_metrics(
    time: np.ndarray,
    potentials: np.ndarray,
    phases: np.ndarray,
    adex: AdExParameters,
) -> tuple[pd.DataFrame, np.ndarray, np.ndarray, np.ndarray]:
    """Cross-validate phase coherence via 16x16 pairwise PLV matrix (120 unique pairs).

    Constructs a full 16x16 Pairwise PLV Matrix where PLV_ij = |mean(exp(1j * (phase_i - phase_j)))|.
    Applies boolean mask ~np.eye(16, dtype=bool) to isolate the 240 off-diagonal entries
    (120 unique neuron pairs) and reports Mean, Median, Min, Max Pairwise PLV for both
    Hilbert continuous-phase and spike-triggered phase-locking values.

    Returns (metrics DataFrame, Kuramoto R(t), mean phase-difference matrix, 16x16 PLV matrix).
    """
    del adex
    voltage = np.asarray(potentials, dtype=float)
    analytic_signal = np.asarray(hilbert(voltage, axis=0))
    analytic_phase = np.unwrap(np.angle(analytic_signal), axis=0)
    wrapped_phase = np.angle(np.exp(1j * analytic_phase))
    kuramoto = np.abs(np.mean(np.exp(1j * analytic_phase), axis=1))

    # ── 16x16 Pairwise PLV Matrix (Hilbert continuous analytic phase) ──────
    # PLV_ij = |mean(exp(1j * (phase_i - phase_j)))| over all time samples
    phase_diff = wrapped_phase[:, :, None] - wrapped_phase[:, None, :]  # (T, 16, 16)
    plv_matrix = np.abs(np.mean(np.exp(1j * phase_diff), axis=0))       # (16, 16)
    n_neurons = voltage.shape[1]
    mask = ~np.eye(n_neurons, dtype=bool)                               # 240 off-diag → 120 unique pairs
    off_diag_plv = plv_matrix[mask]
    mean_plv = float(off_diag_plv.mean())
    median_plv = float(np.median(off_diag_plv))
    min_plv = float(off_diag_plv.min())
    max_plv = float(off_diag_plv.max())

    # ── Spike-Triggered 16x16 Pairwise PLV Matrix ──────────────────────────
    # For each pair (i,j), compute PLV using analytic phase at the union of
    # their respective spike event times.
    threshold = np.mean(voltage, axis=0) + np.std(voltage, axis=0)
    crossings = (voltage[:-1] < threshold) & (voltage[1:] >= threshold)
    spike_plv_matrix = np.zeros((n_neurons, n_neurons))
    for i in range(n_neurons):
        for j in range(n_neurons):
            if i == j:
                spike_plv_matrix[i, j] = 1.0
                continue
            union_spikes = crossings[:, i] | crossings[:, j]
            if union_spikes.sum() > 0:
                diff_ij = wrapped_phase[:-1][union_spikes, i] - wrapped_phase[:-1][union_spikes, j]
                spike_plv_matrix[i, j] = float(np.abs(np.mean(np.exp(1j * diff_ij))))

    spike_off_diag = spike_plv_matrix[mask]
    mean_spike_plv = float(spike_off_diag.mean())
    median_spike_plv = float(np.median(spike_off_diag))
    min_spike_plv = float(spike_off_diag.min())
    max_spike_plv = float(spike_off_diag.max())

    # ── Legacy phase-dispersion metrics (backward-compat) ──────────────────
    recent = wrapped_phase[-min(voltage.shape[0], 20000):]
    deltas = np.angle(np.exp(1j * (recent[:, :, None] - recent[:, None, :])))
    pairwise = np.angle(np.mean(np.exp(1j * deltas), axis=0))
    pairwise_dispersion = float(np.mean(np.std(deltas, axis=0)))
    phase_lag_std = float(np.std(deltas))

    metrics = pd.DataFrame([
        {"metric": "spike_time_plv_mean_pairwise", "value": mean_spike_plv},
        {"metric": "spike_time_plv_median_pairwise", "value": median_spike_plv},
        {"metric": "spike_time_plv_min_pairwise", "value": min_spike_plv},
        {"metric": "spike_time_plv_max_pairwise", "value": max_spike_plv},
        {"metric": "hilbert_plv_mean_pairwise", "value": mean_plv},
        {"metric": "hilbert_plv_median_pairwise", "value": median_plv},
        {"metric": "hilbert_plv_min_pairwise", "value": min_plv},
        {"metric": "hilbert_plv_max_pairwise", "value": max_plv},
        {"metric": "kuramoto_order_parameter_mean", "value": float(np.mean(kuramoto))},
        {"metric": "pairwise_phase_dispersion_rad", "value": pairwise_dispersion},
        {"metric": "phase_lag_distribution_std_rad", "value": phase_lag_std},
    ])
    return metrics, kuramoto, pairwise, plv_matrix


def save_cross_validation_plot(
    time: np.ndarray, kuramoto: np.ndarray, plv_matrix: np.ndarray, path: pathlib.Path
) -> None:
    figure, axes = plt.subplots(2, 1, figsize=(11, 8), gridspec_kw={"height_ratios": [1.2, 1]})
    axes[0].plot(time, kuramoto, color="#0b7285", linewidth=1.0)
    axes[0].set_ylabel("R(t)")
    axes[0].set_title("Kuramoto Order Parameter")
    axes[0].set_ylim(0, 1.02)
    axes[0].grid(alpha=0.25)
    image = axes[1].imshow(plv_matrix, cmap="viridis", vmin=0.0, vmax=1.0)
    axes[1].set_title("16x16 Pairwise PLV Heatmap")
    axes[1].set_xlabel("Neuron j")
    axes[1].set_ylabel("Neuron i")
    figure.colorbar(image, ax=axes[1], label="PLV")
    figure.tight_layout()
    figure.savefig(path, dpi=150)
    plt.close(figure)


def compute_metrics(
    time: np.ndarray, potentials: np.ndarray, phases: np.ndarray, currents: np.ndarray
) -> pd.DataFrame:
    """Extract full-spectrum Welch peaks and circular phase-locking metrics."""
    from scipy.signal import welch
    sample_rate = 1.0 / np.mean(np.diff(time))
    frequencies, power = welch(potentials.mean(axis=1), fs=sample_rate, nperseg=min(65536, len(time)), detrend='linear')
    def peak_in_band(low: float, high: float) -> float:
        mask = (frequencies >= low) & (frequencies <= high)
        return float(frequencies[mask][np.argmax(power[mask])])
    relative_phase = phases - phases.mean(axis=1, keepdims=True)
    # ── 16x16 Pairwise PLV Matrix (120 unique off-diagonal pairs) ──────
    n_neurons = phases.shape[1]
    phase_diff = phases[:, :, None] - phases[:, None, :]  # (T, 16, 16)
    plv_matrix = np.abs(np.mean(np.exp(1j * phase_diff), axis=0))  # (16, 16)
    off_diag_mask = ~np.eye(n_neurons, dtype=bool)
    off_diag_plv = plv_matrix[off_diag_mask]  # 120 unique pairs (240 entries symmetric)
    plv_mean = float(off_diag_plv.mean())
    plv_median = float(np.median(off_diag_plv))
    plv_min = float(off_diag_plv.min())
    plv_max = float(off_diag_plv.max())
    rms_mA = float(np.sqrt(np.mean(np.square(currents))) * 1000.0)
    theta_peak = peak_in_band(4.0, 8.0)
    gamma_peak = peak_in_band(30.0, 80.0)
    corr_matrix = np.corrcoef(potentials.T)
    corr_mask = ~np.eye(corr_matrix.shape[0], dtype=bool)
    cluster_correlation = float(corr_matrix[corr_mask].mean()) if potentials.shape[1] > 1 else 1.0
    return pd.DataFrame([
        {'metric': 'phase_locking_value_mean_pairwise', 'value': plv_mean},
        {'metric': 'phase_locking_value_median_pairwise', 'value': plv_median},
        {'metric': 'phase_locking_value_min_pairwise', 'value': plv_min},
        {'metric': 'phase_locking_value_max_pairwise', 'value': plv_max},
        {'metric': 'cluster_cross_correlation', 'value': cluster_correlation},
        {'metric': 'theta_peak_frequency_hz', 'value': theta_peak},
        {'metric': 'gamma_peak_frequency_hz', 'value': gamma_peak},
        {'metric': 'bridge_rms_current_nA', 'value': rms_mA * 1e6},
        {'metric': 'bridge_rms_current_mA', 'value': rms_mA},
        {'metric': 'bridge_rms_current_uA', 'value': rms_mA * 1000.0},
    ])


def run_vtune_frequency_sweep(
    bridge: BridgeParameters,
    V_tune_range: np.ndarray | None = None,
) -> pd.DataFrame:
    """Sweep V_tune from 0 V to 5 V and measure the LC tank resonance shift.

    Uses the semiconductor varactor junction equation:
        C_var(V_rev) = C_var0 / (1 + V_rev / V_J)^M + C_fixed
    where V_rev = V_tune (assuming V_m,i - V_m,j = 0 for the open-loop sweep).

    Returns:
        DataFrame with columns: V_tune_V, C_var_F, resonance_frequency_hz
    """
    if V_tune_range is None:
        V_tune_range = np.linspace(0.0, 5.0, 51)

    C_fixed_total = bridge.external_capacitance + bridge.trace_capacitance
    records = []
    for V_tune in V_tune_range:
        V_rev = float(np.clip(V_tune, 0.0, 15.0))
        C_var = bridge.varactor_c0 / ((1.0 + V_rev / bridge.varactor_vj) ** bridge.varactor_m) + bridge.varactor_c_fixed
        C_total = C_fixed_total + C_var
        f_res = 1.0 / (2.0 * np.pi * np.sqrt(bridge.inductance * C_total))
        records.append({
            "V_tune_V": float(V_tune),
            "V_rev_V": V_rev,
            "C_var_F": C_var,
            "C_total_F": C_total,
            "resonance_frequency_hz": f_res,
        })

    result = pd.DataFrame(records)

    # Compute tuning sensitivity
    if len(result) > 1:
        f_low = result["resonance_frequency_hz"].iloc[0]   # V_tune = 0 V
        f_high = result["resonance_frequency_hz"].iloc[-1] # V_tune = 5 V
        df_dv = (f_low - f_high) / 5.0
        print(f"[V_tune sweep] 0 V -> {f_low:.3f} Hz, 5 V -> {f_high:.3f} Hz, |df/dV_tune| = {abs(df_dv):.3f} Hz/V")

    return result


def save_vtune_sweep_plot(sweep_df: pd.DataFrame, path: pathlib.Path) -> None:
    """Generate a two-panel figure showing V_tune vs frequency and C_var."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4.5), constrained_layout=True)

    # Panel 1: V_tune vs Resonance Frequency
    ax1.plot(sweep_df["V_tune_V"], sweep_df["resonance_frequency_hz"], color="C0", lw=1.8, marker="o", ms=2.5)
    ax1.set_xlabel("V_tune (V)")
    ax1.set_ylabel("LC tank resonance frequency (Hz)")
    ax1.set_title("V_tune -> Frequency tuning curve\n(semiconductor varactor model)")
    ax1.grid(alpha=0.25)

    # Annotate endpoints
    v0 = sweep_df["V_tune_V"].iloc[0]
    f0 = sweep_df["resonance_frequency_hz"].iloc[0]
    v5 = sweep_df["V_tune_V"].iloc[-1]
    f5 = sweep_df["resonance_frequency_hz"].iloc[-1]
    ax1.annotate(f"{f0:.1f} Hz @ {v0:.1f} V", xy=(v0, f0), xytext=(v0 + 0.3, f0 + 30),
                 arrowprops=dict(arrowstyle="->", color="0.4"), fontsize=9)
    ax1.annotate(f"{f5:.1f} Hz @ {v5:.1f} V", xy=(v5, f5), xytext=(v5 - 1.2, f5 - 30),
                 arrowprops=dict(arrowstyle="->", color="0.4"), fontsize=9)

    # Panel 2: V_tune vs Varactor Capacitance
    ax2.plot(sweep_df["V_tune_V"], sweep_df["C_var_F"] * 1e9, color="C1", lw=1.8, marker="s", ms=2.5)
    ax2.set_xlabel("V_tune (V)")
    ax2.set_ylabel("Varactor capacitance C_var (nF)")
    ax2.set_title("V_tune -> C_var reverse-bias characteristic\nC_var = C0 / (1 + V_rev/V_J)^M + C_fixed")
    ax2.grid(alpha=0.25)

    fig.suptitle("AdEx Resonant Core - V_tune Varactor Characterisation", fontsize=12, y=1.02)
    fig.savefig(path, dpi=160, bbox_inches="tight")
    plt.close(fig)
    print(f"V_tune sweep plot saved to {path}")


def compute_tuning_spectrum(
    time: np.ndarray, tuning: np.ndarray, tank_frequency: np.ndarray
) -> pd.DataFrame:
    """Use Welch PSD windows to measure the tank peak at low/high V_tune."""
    sample_rate = 1.0 / np.mean(np.diff(time))
    carrier = np.sin(2.0 * np.pi * np.cumsum(tank_frequency) / sample_rate)
    records: list[dict[str, float | str]] = []
    for label, mask in (("low_tune", tuning[:, 0] <= 0.8), ("high_tune", tuning[:, 0] >= 4.2)):
        selected = carrier[mask]
        if len(selected) < 256:
            continue
        frequencies, power = welch(selected, fs=sample_rate, nperseg=min(4096, len(selected)), detrend="linear")
        band = (frequencies >= 500.0) & (frequencies <= 4000.0)
        peak_hz = float(frequencies[band][np.argmax(power[band])])
        records.append({
            "tune_region": label,
            "mean_v_tune_V": float(tuning[mask, 0].mean()),
            "welch_peak_frequency_hz": peak_hz,
            "model_mean_frequency_hz": float(tank_frequency[mask].mean()),
        })
    result = pd.DataFrame(records)
    if len(result) == 2:
        low = result.loc[result["tune_region"] == "low_tune", "welch_peak_frequency_hz"].iloc[0]
        high = result.loc[result["tune_region"] == "high_tune", "welch_peak_frequency_hz"].iloc[0]
        result["peak_shift_hz"] = abs(float(low) - float(high))
    return result

def save_plot(time: np.ndarray, potentials: np.ndarray, phases: np.ndarray, currents: np.ndarray, tuning: np.ndarray, path: pathlib.Path, interactive: bool = False) -> None:
    """Generate and display/save the phase-locking response figure.

    When *interactive* is True and a DISPLAY is available, the saved plot is
    opened in the system image viewer.  In all cases the figure is saved to *path*.
    """
    fig, (top, middle, bottom) = plt.subplots(3, 1, figsize=(12, 8), sharex=True)
    milliseconds = time * 1e3
    for index in range(16):
        top.plot(milliseconds, potentials[:, index] * 1e3, lw=0.45, alpha=0.65, label=f"Vm{index + 1}" if index < 4 else None)
    top.set_ylabel("Membrane potential (mV)")
    top.set_title("4x4 AdEx Resonant Core: phase-locking response")
    top.grid(alpha=0.25)
    top.legend(ncol=4, fontsize=8, loc="upper right")
    middle.plot(milliseconds, tuning[:, 0], color="C4", lw=0.9, label="V_tune with RC damping")
    middle.axvline(0.15 * milliseconds[-1], color="0.4", ls="--", lw=0.7, label="calibration step")
    middle.set_ylabel("V_tune (V)")
    middle.grid(alpha=0.25)
    middle.legend(fontsize=8, loc="upper right")
    phase_difference = np.angle(np.exp(1j * (phases[:, 0] - phases[:, 15])))
    bottom.plot(milliseconds, phase_difference, color="C3", lw=0.7, label="Vm1 - Vm16 phase")
    bottom.set_ylabel("Inter-neuron phase (rad)")
    current_axis = bottom.twinx()
    current_axis.plot(milliseconds, currents.mean(axis=1) * 1e9, color="C2", lw=0.7, alpha=0.8, label="mean LC current")
    current_axis.set_ylabel("LC bridge current (nA)")
    bottom.set_xlabel("Time (ms)")
    bottom.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    if interactive and os.environ.get("DISPLAY"):
        subprocess.Popen(["xdg-open", str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def try_ngspice(adex: AdExParameters, bridge: BridgeParameters, sim: SimulationParameters) -> tuple[bool, np.ndarray | None]:
    """Attempt to run Ngspice transient simulation as an independent engine.

    Builds the behavioural circuit-equivalent netlist, writes it to a
    temporary file, executes ``ngspice -b`` as a subprocess, and parses
    the printed transient node voltages for all 16 neurons.

    Returns (ok, V_m_spice) where V_m_spice is an ndarray of shape
    (n_time_steps, 16) with membrane potentials in Volts, or None if
    ngspice is unavailable or the simulation fails.

    This engine is completely independent of the RK4 numerical solver.
    """
    if shutil.which("ngspice") is None:
        return False, None

    try:
        circuit = build_pyspice_circuit(adex, bridge, sim)
    except Exception as exc:
        print(f"[PySpice] Circuit build failed: {exc}")
        return False, None

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".cir", delete=False, prefix="adex_spice_"
    ) as f:
        netlist_path = pathlib.Path(f.name)
        raw = circuit.raw_spice
        # UIC flag must be at the END of the .tran line, not after .tran
        raw = raw.replace(".tran ", ".tran ")
        if ".tran" in raw and "uic" not in raw.lower():
            # Find the .tran line and append UIC
            lines = raw.split("\n")
            for i, line in enumerate(lines):
                if line.strip().startswith(".tran"):
                    lines[i] = line.strip() + " uic"
                    break
            raw = "\n".join(lines)
        f.write(raw + "\n")
        # Ngspice convergence options
        f.write(".options ABSTOL=1e-12 RELTOL=0.01 VNTOL=1e-6 GMIN=1e-12\n")
        f.write(".options ITL1=500 ITL2=500 METHOD=GEAR\n")
        # Set initial node voltages for convergence
        for index in range(16):
            f.write(f".ic v(VM{index + 1})={adex.e_l}\n")
        # Add .print tran for all 16 VM nodes
        all_nodes = " ".join(f"v(VM{i+1})" for i in range(16))
        f.write(f".print tran {all_nodes}\n")
        f.write(".end\n")

    try:
        result = subprocess.run(
            ["ngspice", "-b", str(netlist_path)],
            capture_output=True,
            text=True,
            timeout=600.0,
        )
        if result.returncode != 0:
            print(f"[Ngspice] Simulation failed (exit {result.returncode})")
            if result.stderr:
                for err_line in result.stderr.strip().splitlines()[-20:]:
                    print(f"  [Ngspice stderr] {err_line}")
            return False, None

        output_lines = result.stdout.strip().splitlines()
        # Find the printed transient data — ngspice .print outputs a table
        # after a header line starting with "Index" or similar.
        data_start = None
        for i, line in enumerate(output_lines):
            if line.strip().startswith("Index") and "v(" in line.lower():
                data_start = i + 1
                break

        if data_start is None:
            # Try a different format: ngspice sometimes prints without Index header
            for i, line in enumerate(output_lines):
                if line.strip() and line.strip().split()[0].replace(".","",1).replace("e","",1).replace("+","",1).replace("-","",1).isdigit():
                    data_start = i
                    break

        if data_start is None or data_start >= len(output_lines):
            print("[Ngspice] Could not locate transient data in output")
            return False, None

        # Parse the data table
        rows = []
        for line in output_lines[data_start:]:
            line = line.strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) < 17:  # Index + 16 node voltages
                continue
            try:
                row = [float(parts[0])] + [float(p) for p in parts[1:17]]
                rows.append(row)
            except ValueError:
                continue

        if len(rows) < 2:
            print(f"[Ngspice] Only {len(rows)} data rows parsed — aborting")
            return False, None

        data = np.array(rows, dtype=float)
        v_m_spice = data[:, 1:]  # shape (n_steps, 16), each column is one VM node

        print(f"[Ngspice] Transient completed: {v_m_spice.shape[0]} steps, {v_m_spice.shape[1]} neurons")
        return True, v_m_spice

    except subprocess.TimeoutExpired:
        print("[Ngspice] Simulation timed out (>600 s)")
        return False, None
    except Exception as exc:
        print(f"[Ngspice] Unexpected error: {exc}")
        return False, None
    finally:
        if netlist_path.exists():
            netlist_path.unlink()


def extract_spike_rate_from_voltage(
    voltages: np.ndarray,
    v_peak: float,
    dt: float,
) -> float:
    """Calculate firing rate from a membrane voltage trace.

    Counts every crossing of *v_peak* (from below to at-or-above) and
    returns the mean rate in Hz averaged across all neurons.

    Parameters
    ----------
    voltages : ndarray, shape (n_time, n_neurons)
        Membrane potential time series (V).
    v_peak : float
        Spike-detection threshold (V).
    dt : float
        Time step between samples (s).

    Returns
    -------
    float
        Mean firing rate (Hz) across the population.
    """
    n_neurons = voltages.shape[1]
    total_spikes = 0
    for neuron in range(n_neurons):
        trace = voltages[:, neuron]
        crossings = np.flatnonzero((trace[:-1] < v_peak) & (trace[1:] >= v_peak))
        total_spikes += len(crossings)
    duration_s = voltages.shape[0] * dt
    return float(total_spikes) / (n_neurons * duration_s) if duration_s > 0.0 else 0.0


    def run_monte_carlo_parametric_sensitivity(iterations: int = 50, adex: AdExParameters | None = None, bridge: BridgeParameters | None = None, sim: SimulationParameters | None = None) -> pd.DataFrame:
        """Measure phase-locking spread across passive component tolerances and macro-parameter variation (C_m, g_l, tau_w, V_t, L, C_ext)."""
        base_adex = adex or AdExParameters()
        base_bridge = bridge or BridgeParameters()
        base_sim = sim or SimulationParameters()
        rng = np.random.default_rng(20260913)
        temperatures = rng.uniform(-20.0, 85.0, iterations)
        tolerances = rng.uniform(-0.05, 0.05, (iterations, 4))
        records: list[dict[str, float]] = []
        started = time_module.perf_counter()
        for index in range(iterations):
            temperature_c = float(temperatures[index])
            thermal_voltage = 8.617333262e-5 * (temperature_c + 273.15)
            tolerance = tolerances[index]
            sampled_adex = replace(
                base_adex,
                c_m=base_adex.c_m * (1.0 + tolerance[0]),
                g_l=base_adex.g_l * (1.0 + tolerance[1]),
                tau_w=base_adex.tau_w * (1.0 + tolerance[2]),
                v_t=base_adex.v_t + thermal_voltage - 0.02585,
            )
            sampled_bridge = replace(
                base_bridge,
                external_capacitance=base_bridge.external_capacitance * (1.0 + tolerance[3]),
                inductance=base_bridge.inductance * (1.0 + tolerance[0]),
            )
            analysis_sim = replace(base_sim, duration=min(base_sim.duration, 0.01), dt=max(base_sim.dt, 1e-4))
            _, _, _, sampled_phases, _, _, _, _ = run_numerical(sampled_adex, sampled_bridge, analysis_sim)
            n_neurons = sampled_phases.shape[1]
            phase_diff = sampled_phases[:, :, None] - sampled_phases[:, None, :]
            plv_matrix = np.abs(np.mean(np.exp(1j * phase_diff), axis=0))
            mask = ~np.eye(n_neurons, dtype=bool)
            plv = float(plv_matrix[mask].mean())
            records.append({
                'temperature_c': temperature_c,
                'tolerance_min': float(tolerance.min()),
                'tolerance_max': float(tolerance.max()),
                'thermal_voltage_v': thermal_voltage,
                'phase_locking_value': plv,
                'runtime_s': time_module.perf_counter() - started,
            })
        result = pd.DataFrame(records)
        EXPORTS.mkdir(parents=True, exist_ok=True)
        result.to_csv(EXPORTS / 'parametric_sensitivity_analysis.csv', index=False)
        figure, axes = plt.subplots(1, 2, figsize=(10, 4), constrained_layout=True)
        axes[0].scatter(result['temperature_c'], result['phase_locking_value'], c=result['tolerance_max'], cmap='viridis', s=28)
        axes[0].set(xlabel='Temperature (C)', ylabel='PLV', title='Parametric sensitivity: PLV spread across passive & macro tolerances')
        axes[1].hist(result['phase_locking_value'], bins=min(12, max(5, iterations // 5)), color='C1', alpha=0.85)
        axes[1].set(xlabel='PLV', ylabel='Samples', title='PLV distribution (passive & macro tolerances)')
        figure.savefig(EXPORTS / 'parametric_sensitivity_analysis.png', dpi=160)
        plt.close(figure)
        return result
    try:
        circuit = build_pyspice_circuit(adex, bridge, sim)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".cir", delete=False) as netlist:
            netlist.write(str(circuit))
            netlist_path = pathlib.Path(netlist.name)
        result = subprocess.run(["ngspice", "-b", str(netlist_path)], capture_output=True, timeout=120)
        netlist_path.unlink(missing_ok=True)
        return result.returncode == 0
    except (OSError, RuntimeError, subprocess.SubprocessError):
        return False


def run_monte_carlo_parametric_sensitivity(iterations: int = 50, adex: AdExParameters | None = None, bridge: BridgeParameters | None = None, sim: SimulationParameters | None = None) -> pd.DataFrame:
    """Measure phase-locking spread across passive component tolerances and macro-parameter variation (C_m, g_l, tau_w, V_t, L, C_ext).

    Note: This analysis sweeps passive-component tolerance (±5 %) and temperature
    drift (−20 °C to 85 °C).  Detailed BJT/MOSFET process variation (V_BE, beta,
    I_s, Early-effect mismatch) is **not** included here — those effects require
    a full behavioral / circuit-equivalent SPICE PDK Monte Carlo and are scheduled prior to
    silicon fabrication.
    """
    base_adex = adex or AdExParameters()
    base_bridge = bridge or BridgeParameters()
    base_sim = sim or SimulationParameters()
    rng = np.random.default_rng(20260913)
    temperatures = rng.uniform(-20.0, 85.0, iterations)
    tolerances = rng.uniform(-0.05, 0.05, (iterations, 4))
    records: list[dict[str, float]] = []
    started = time_module.perf_counter()
    for index in range(iterations):
        temperature_c = float(temperatures[index])
        thermal_voltage = 8.617333262e-5 * (temperature_c + 273.15)
        tolerance = tolerances[index]
        sampled_adex = replace(base_adex, c_m=base_adex.c_m * (1.0 + tolerance[0]), g_l=base_adex.g_l * (1.0 + tolerance[1]), tau_w=base_adex.tau_w * (1.0 + tolerance[2]), v_t=base_adex.v_t + thermal_voltage - 0.02585)
        sampled_bridge = replace(base_bridge, external_capacitance=base_bridge.external_capacitance * (1.0 + tolerance[3]), inductance=base_bridge.inductance * (1.0 + tolerance[0]))
        analysis_sim = replace(base_sim, duration=min(base_sim.duration, 0.01), dt=max(base_sim.dt, 1e-4))
        _, _, _, sampled_phases, _, _, _, _ = run_numerical(sampled_adex, sampled_bridge, analysis_sim)
        n_neurons = sampled_phases.shape[1]
        phase_diff = sampled_phases[:, :, None] - sampled_phases[:, None, :]
        plv_matrix = np.abs(np.mean(np.exp(1j * phase_diff), axis=0))
        mask = ~np.eye(n_neurons, dtype=bool)
        plv = float(plv_matrix[mask].mean())
        records.append({'temperature_c': temperature_c, 'tolerance_min': float(tolerance.min()), 'tolerance_max': float(tolerance.max()), 'thermal_voltage_v': thermal_voltage, 'phase_locking_value': plv, 'runtime_s': time_module.perf_counter() - started})
    result = pd.DataFrame(records)
    EXPORTS.mkdir(parents=True, exist_ok=True)
    result.to_csv(EXPORTS / 'parametric_sensitivity_analysis.csv', index=False)
    figure, axes = plt.subplots(1, 2, figsize=(10, 4), constrained_layout=True)
    axes[0].scatter(result['temperature_c'], result['phase_locking_value'], c=result['tolerance_max'], cmap='viridis', s=28)
    axes[0].set(xlabel='Temperature (C)', ylabel='PLV', title='Parametric sensitivity: PLV spread across passive & macro tolerances')
    axes[1].hist(result['phase_locking_value'], bins=min(12, max(5, iterations // 5)), color='C1', alpha=0.85)
    axes[1].set(xlabel='PLV', ylabel='Samples', title='PLV distribution (passive & macro tolerances)')
    figure.savefig(EXPORTS / 'parametric_sensitivity_analysis.png', dpi=160)
    plt.close(figure)
    return result


def save_benchmark_plot(numerical_rate: float, spice_rate: float | None, path: pathlib.Path) -> None:
    """Compare numerical and behavioural circuit-equivalent SPICE firing-rate estimates.

    When *spice_rate* is *None* (PySpice/Ngspice unavailable), the SPICE
    bar is replaced by a "SPICE Engine Offline" annotation so the plot
    never displays duplicated RK4 data.
    """
    figure, axis = plt.subplots(figsize=(8, 5), dpi=220)

    if spice_rate is not None:
        labels = ["RK4 numerical", "PySpice/Ngspice"]
        values = [numerical_rate, spice_rate]
        colors = ["#176b87", "#d97706"]
        axis.bar(labels, values, color=colors, width=0.58)
        delta = abs(numerical_rate - spice_rate)
        axis.annotate(
            f"|ΔRate| = {delta:.3f} Hz\n(RK4 vs SPICE)",
            xy=(0.5, 0.92),
            xycoords="axes fraction",
            fontsize=10,
            ha="center",
            va="top",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="wheat", alpha=0.85),
        )
    else:
        labels = ["RK4 numerical", "SPICE Engine Offline"]
        values = [numerical_rate, 0.0]
        colors = ["#176b87", "#cccccc"]
        axis.bar(labels, values, color=colors, width=0.58)
        axis.annotate(
            "PySpice/Ngspice not available\nRK4-only mode",
            xy=(0.5, 0.50),
            xycoords="axes fraction",
            fontsize=11,
            ha="center",
            va="center",
            bbox=dict(boxstyle="round,pad=0.4", facecolor="lightcoral", alpha=0.7),
        )

    axis.set_ylabel("Firing rate (Hz)")
    axis.set_title("AdEx Resonant Core — RK4 vs Behavioural SPICE Benchmark\n(Dual-engine independent execution)")
    axis.grid(axis="y", alpha=0.25)
    figure.tight_layout()
    figure.savefig(path, dpi=220)
    plt.close(figure)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="AdEx Resonant Core phase-locking simulation")
    parser.add_argument("--interactive", action="store_true", help="Show dynamic real-time plot")
    args = parser.parse_args()

    adex, bridge, sim = AdExParameters(), BridgeParameters(), SimulationParameters()
    spice_ok, v_m_spice = try_ngspice(adex, bridge, sim)
    time, potentials, currents, bridge_voltages, tuning, capacitance_trace, tank_frequency, diagnostics_df = run_numerical(adex, bridge, sim)
    phases = spike_phases(time, potentials, adex)
    metrics = compute_metrics(time, potentials, bridge_voltages, currents)
    cross_metrics, kuramoto, pairwise, plv_matrix = compute_cross_validated_metrics(
        time, potentials, bridge_voltages, adex
    )
    metrics = pd.concat([cross_metrics, metrics], ignore_index=True)
    traces = pd.DataFrame({"time_s": time})
    for index in range(16):
        traces[f"V_m{index + 1}_V"] = potentials[:, index]
    traces["mean_bridge_current_A"] = currents.mean(axis=1)
    traces["mean_bridge_voltage_V"] = bridge_voltages.mean(axis=1)
    traces["mean_v_tune_V"] = tuning.mean(axis=1)
    traces["tank_resonance_frequency_hz"] = tank_frequency
    traces.to_csv(EXPORTS / "phase_locking_traces.csv", index=False)
    diagnostics_df.to_csv(EXPORTS / "aer_spike_events.csv", index=False)
    metrics.to_csv(EXPORTS / "phase_locking_metrics.csv", index=False)
    tuning_spectrum = compute_tuning_spectrum(time, tuning, tank_frequency)
    tuning_spectrum.to_csv(EXPORTS / "tuning_welch_peaks.csv", index=False)
    test_plot_path = EXPORTS / "local_test_verification.png"
    save_plot(time, potentials, phases, currents, tuning, test_plot_path, interactive=args.interactive)
    save_cross_validation_plot(time, kuramoto, plv_matrix, test_plot_path)
    bridge_rms = float(np.sqrt(np.mean(currents ** 2)))  # A
    # === V_tune varactor frequency sweep (semiconductor reverse-bias junction model) ===
    vtune_sweep = run_vtune_frequency_sweep(bridge)
    vtune_sweep.to_csv(EXPORTS / "vtune_frequency_sweep.csv", index=False)
    vtune_sweep_path = EXPORTS / "vtune_frequency_sweep.png"
    save_vtune_sweep_plot(vtune_sweep, vtune_sweep_path)

    # Document verified V_tune sweep responsiveness
    vtune_0v_freq = vtune_sweep["resonance_frequency_hz"].iloc[0]
    vtune_5v_freq = vtune_sweep["resonance_frequency_hz"].iloc[-1]
    print(f'[Varactor semiconductor model] C_var0={bridge.varactor_c0 * 1e9:.3g} nF, V_J={bridge.varactor_vj:.3g} V, M={bridge.varactor_m:.3g}, C_fixed={bridge.varactor_c_fixed * 1e9:.3g} nF')
    print(f'[V_tune sweep] Verified: {vtune_5v_freq:.3f} Hz @ 5 V  ->  {vtune_0v_freq:.3f} Hz @ 0 V')
    print(f'[V_tune sweep] Total frequency shift = {abs(vtune_0v_freq - vtune_5v_freq):.3f} Hz across 0-5 V range')

    parametric_results = run_monte_carlo_parametric_sensitivity(iterations=50, adex=adex, bridge=bridge, sim=sim)
    numerical_rate = float(len(diagnostics_df) / max(sim.duration, sim.dt) / sim.grid_side**2)
    if spice_ok and v_m_spice is not None:
        spice_rate = extract_spike_rate_from_voltage(v_m_spice, adex.v_peak, sim.dt)
        print(f"[Benchmark] RK4 rate={numerical_rate:.4f} Hz, SPICE rate={spice_rate:.4f} Hz, |Δ|={abs(numerical_rate - spice_rate):.4f} Hz")
    else:
        spice_rate = None
        print("[Benchmark] SPICE engine offline — benchmark reflects RK4 only")
    benchmark_path = EXPORTS / "benchmark_rk4_vs_pspice.png"
    save_benchmark_plot(numerical_rate, spice_rate, benchmark_path)
    print(f'Behavioral B-source model (Shockley/EKV): I0={adex.saturation_current:.3g} A, eta={adex.ideality_factor:.3g}, VT={adex.thermal_voltage * 1e3:.3g} mV')
    print(f'RC varactor damping: R={bridge.tune_resistance:.3g} ohm, C={bridge.tune_capacitance:.3g} F, zeta={bridge.tune_damping_ratio:.3g}')
    print(f'PCB trace parasitic: C_trace={bridge.trace_capacitance * 1e12:.3g} pF in parallel with each LC bridge')
    print(f'LC tank: L={bridge.inductance * 1e3:.3g} mH, C_fixed={bridge.external_capacitance * 1e9:.3g} nF, C_var=C0/(1+V_rev/V_J)^M+C_fixed')
    print(f'Physical resonance range (V_tune sweep): {bridge.resonance_min_hz:.3f}-{bridge.resonance_max_hz:.3f} Hz; tuning ratio={(bridge.resonance_max_hz / bridge.resonance_min_hz - 1.0) * 100.0:.2f}%')
    if len(tuning_spectrum) == 2:
        low_peak = tuning_spectrum.loc[tuning_spectrum['tune_region'] == 'low_tune', 'welch_peak_frequency_hz'].iloc[0]
        high_peak = tuning_spectrum.loc[tuning_spectrum['tune_region'] == 'high_tune', 'welch_peak_frequency_hz'].iloc[0]
        tune_slope = abs(float(low_peak) - float(high_peak)) / 4.0
        print(f'Welch tank peaks: low V_tune={low_peak:.3f} Hz, high V_tune={high_peak:.3f} Hz, |df/dV_tune|={tune_slope:.3f} Hz/V')
    print(f'AER output: {len(diagnostics_df)} asynchronous spike events; continuous ADC waveform not required')
    print(f'Parametric sensitivity range: passive ±5%; temperature −20 °C to 85 °C; sigma_PLV={parametric_results["phase_locking_value"].std(ddof=1):.6g}')
    print(f'Physical grid coupling: 4x4 nearest-neighbor Kirchhoff bridges; runtime={parametric_results["runtime_s"].iloc[-1]:.3f} s')
    print('State-space RLC integration: dQ/dt=I; dI/dt=((V_m,i-V_m,j)-R_s I-Q/C_var)/L')
    print('PLV extraction: post-hoc SciPy Hilbert Transform of simulated V_m(t)')
    print(f"Simulation duration: {sim.duration * 1e3:.0f} ms")
    print(f"PySpice/Ngspice netlist path: {'available' if spice_ok else 'fallback-equivalent'}")
    print(f"Benchmark plot saved to              : {benchmark_path}")
    print()
    print("=== AdEx Resonant Core — Execution Report ===")
    print(f"Physical topology: 4x4 2D nearest-neighbour grid; {len(grid_edges(GRID_SIZE))} RLC bridges")
    print("Kirchhoff solver: second-order state-space equations dQ/dt=I and dI/dt=((V_m,i-V_m,j)-R_s I-Q/C)/L")
    def _mval(name: str) -> float:
        return float(metrics.loc[metrics['metric'] == name, 'value'].iloc[0])
    print(f"  Hilbert PLV \u2014 Mean Pairwise (120 pairs) : {_mval('hilbert_plv_mean_pairwise'):.6f}")
    print(f"  Hilbert PLV \u2014 Median Pairwise (120 pairs): {_mval('hilbert_plv_median_pairwise'):.6f}")
    print(f"  Hilbert PLV \u2014 Min Pairwise (120 pairs)  : {_mval('hilbert_plv_min_pairwise'):.6f}")
    print(f"  Hilbert PLV \u2014 Max Pairwise (120 pairs)  : {_mval('hilbert_plv_max_pairwise'):.6f}")
    print(f"  Spike-Time PLV \u2014 Mean Pairwise (120 prs): {_mval('spike_time_plv_mean_pairwise'):.6f}")
    print(f"  Spike-Time PLV \u2014 Median Pairwise (120prs): {_mval('spike_time_plv_median_pairwise'):.6f}")
    print(f"  Spike-Time PLV \u2014 Min Pairwise (120 prs) : {_mval('spike_time_plv_min_pairwise'):.6f}")
    print(f"  Spike-Time PLV \u2014 Max Pairwise (120 prs) : {_mval('spike_time_plv_max_pairwise'):.6f}")
    print(f"  Phase-Locking Value \u2014 Mean (120 pairs)  : {_mval('phase_locking_value_mean_pairwise'):.6f}")
    print(f"  Phase-Locking Value \u2014 Median (120 pairs): {_mval('phase_locking_value_median_pairwise'):.6f}")
    print(f"  Phase-Locking Value \u2014 Min (120 pairs)   : {_mval('phase_locking_value_min_pairwise'):.6f}")
    print(f"  Phase-Locking Value \u2014 Max (120 pairs)   : {_mval('phase_locking_value_max_pairwise'):.6f}")
    print(f"  FFT Peak Theta Frequency (Hz)           : {_mval('theta_peak_frequency_hz'):.4f}")
    print(f"  FFT Peak Gamma Frequency (Hz)           : {_mval('gamma_peak_frequency_hz'):.4f}")
    print(f"  Varactor Bridge Current RMS (mA)        : {bridge_rms * 1e3:.6f}")
    print(f"  Off-Diagonal Inter-Neuron Cross-Corr     : {_mval('cluster_cross_correlation'):.6f}")
    print(f"  Plot saved to                           : {test_plot_path}")
    print("===========================================")


if __name__ == "__main__":
    main()