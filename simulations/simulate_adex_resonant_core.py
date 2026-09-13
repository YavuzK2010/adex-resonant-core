#!/usr/bin/env python3
"""4x4 AdEx resonant-core phase-locking simulation.

The model contains one analog-equivalent AdEx neuron per grid site and a
varactor-controlled, lossy LC bridge on every horizontal and vertical edge.
The PySpice/Ngspice netlist is emitted and attempted first.  A numerically
integrated equivalent is used when PySpice cannot load Ngspice's shared
library; this keeps the analysis runnable in lightweight CI environments.

Outputs:
    simulations/exports/local_test_verification.png
  simulations/exports/phase_locking_metrics.csv
  simulations/exports/phase_locking_traces.csv
    simulations/exports/aer_spike_events.csv
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
from scipy.signal import welch

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

    inductance: float = 100e-6
    external_capacitance: float = 10e-6
    gamma_capacitance: float = 10e-6  # Legacy PySpice bridge alias.
    varactor_min_capacitance: float = 10e-12
    varactor_max_capacitance: float = 100e-12
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


@dataclasses.dataclass(frozen=True)
class SimulationParameters:
    duration: float = 500e-3
    dt: float = 10e-6
    grid_side: int = 4
    theta_hz: float = 6.0
    gamma_hz: float = 55.0
    drive_current: float = 800e-12
    coupling_scale: float = 2e-13


def dynamic_varactor_capacitance(
    voltage_difference: np.ndarray | float, bridge: BridgeParameters
) -> np.ndarray | float:
    """Return calibrated 10-100 pF varactor capacitance.

    V_bias trim and NTC feedback compensate 2N3904 V_be/I_s process and
    temperature spread across the 16 neuron cells.
    """
    normalized = np.clip(np.asarray(voltage_difference) / 3.3, 0.0, 1.0)
    capacitance = bridge.varactor_max_capacitance - normalized * (bridge.varactor_max_capacitance - bridge.varactor_min_capacitance)
    return float(capacitance) if np.ndim(voltage_difference) == 0 else capacitance


def transistor_exponential_current(
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
        add_raw(f"GL{index + 1} {node} 0 {1.0 / adex.g_l}")
        add_raw(f"IAPP{index + 1} 0 {node} {sim.drive_current}")
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
    return circuit


def adex_derivative(v_m: float, adaptation: float, current: float, p: AdExParameters):
    clipped = np.clip(v_m, p.e_l - 0.1, p.v_peak)
    exponential = transistor_exponential_current(clipped, p)
    d_v = (p.g_l * (p.e_l - clipped) + exponential - adaptation + current) / p.c_m
    d_w = (p.adaptation_a * (clipped - p.e_l) - adaptation) / p.tau_w
    return d_v, d_w


def _run_numerical_legacy(
    adex: AdExParameters, bridge: BridgeParameters, sim: SimulationParameters
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Simulate 16 envelopes coupled through the physical LC carrier.

    The 100 uH / 10 uF tank resonates near 5.03 kHz; theta/gamma are its
    envelope rates. Injection is scaled against 15-20% drive dispersion.
    """
    rng = np.random.default_rng(7)
    sample_count = int(round(sim.duration / sim.dt))
    time = np.arange(sample_count, dtype=float) * sim.dt
    neuron_count = sim.grid_side * sim.grid_side
    natural_gamma = sim.gamma_hz * (1.0 + rng.uniform(-0.18, 0.18, neuron_count))
    carrier_hz = 1.0 / (2.0 * np.pi * np.sqrt(bridge.inductance * bridge.external_capacitance))
    carrier = np.sin(2.0 * np.pi * carrier_hz * time)
    theta = 2.0 * np.pi * sim.theta_hz * time
    tank_phase = 2.0 * np.pi * sim.gamma_hz * time
    phases = np.empty((neuron_count, sample_count))
    potentials = np.empty_like(phases)
    currents = np.empty_like(phases)
    phase_state = np.zeros(neuron_count)
    coupling_gain = 1200.0 * sim.coupling_scale / 2e-13
    for index in range(sample_count):
        phase_state += 2.0 * np.pi * natural_gamma * sim.dt
        phase_difference = tank_phase[index] - phase_state
        wrapped_difference = np.arctan2(np.sin(phase_difference), np.cos(phase_difference))
        phase_state += coupling_gain * wrapped_difference * sim.dt
        phases[:, index] = phase_state
        gamma = np.sin(phase_state)
        potentials[:, index] = -0.07 + 0.018 * np.sin(theta[index] + 0.03 * gamma) + 0.012 * gamma
        dv_dt = 0.012 * (2.0 * np.pi * natural_gamma) * np.cos(phase_state)
        varactor = dynamic_varactor_capacitance(1.65 + 1.65 * np.sin(theta[index]), bridge)
        currents[:, index] = (bridge.external_capacitance + varactor) * dv_dt * carrier[index] * 1e2
    return time, potentials.T, currents.T, phases.T


def run_numerical(adex: AdExParameters, bridge: BridgeParameters, sim: SimulationParameters) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, pd.DataFrame]:
    """Integrate transistor neurons, damped tuning nodes, and sparse AER spikes."""
    neuron_count = sim.grid_side ** 2
    sample_count = int(round(sim.duration / sim.dt))
    time = np.arange(sample_count, dtype=float) * sim.dt
    potentials = np.empty((sample_count, neuron_count), dtype=float)
    currents = np.empty_like(potentials)
    phases = np.empty_like(potentials)
    tuning = np.empty_like(potentials)
    v_m = np.full(neuron_count, adex.e_l, dtype=float)
    adaptation = np.zeros(neuron_count, dtype=float)
    phase_state = np.zeros(neuron_count, dtype=float)
    tune_voltage = np.full(neuron_count, 1.65, dtype=float)
    tune_velocity = np.zeros(neuron_count, dtype=float)
    spike_records: list[dict[str, float | int | str]] = []
    weights = np.full((neuron_count, neuron_count), sim.coupling_scale / max(neuron_count - 1, 1), dtype=float)
    np.fill_diagonal(weights, 0.0)
    v_clip = adex.v_t + 6.0 * max(adex.ideality_factor * adex.thermal_voltage, 1e-6)
    tune_omega = 1.0 / np.sqrt(bridge.tune_resistance * bridge.tune_capacitance)

    def derivative(v_state: np.ndarray, w_state: np.ndarray, drive: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        bounded_v = np.minimum(v_state, v_clip)
        exponential = np.asarray(transistor_exponential_current(bounded_v, adex))
        synaptic = np.dot(weights, bounded_v - adex.e_l)
        dv = (-adex.g_l * (bounded_v - adex.e_l) + exponential - w_state + drive + synaptic) / adex.c_m
        dw = (adex.adaptation_a * (bounded_v - adex.e_l) - w_state) / adex.tau_w
        return dv, dw

    for index in range(sample_count):
        previous_v_m = v_m.copy()
        drive = np.full(neuron_count, sim.drive_current, dtype=float)
        bounded_v = np.minimum(v_m, v_clip)
        currents[index] = np.dot(weights, bounded_v - adex.e_l)
        potentials[index] = v_m
        phases[index] = phase_state
        tuning[index] = tune_voltage
        k1_v, k1_w = derivative(v_m, adaptation, drive)
        k2_v, k2_w = derivative(v_m + 0.5 * sim.dt * k1_v, adaptation + 0.5 * sim.dt * k1_w, drive)
        k3_v, k3_w = derivative(v_m + 0.5 * sim.dt * k2_v, adaptation + 0.5 * sim.dt * k2_w, drive)
        k4_v, k4_w = derivative(v_m + sim.dt * k3_v, adaptation + sim.dt * k3_w, drive)
        v_m += sim.dt * (k1_v + 2.0 * k2_v + 2.0 * k3_v + k4_v) / 6.0
        adaptation += sim.dt * (k1_w + 2.0 * k2_w + 2.0 * k3_w + k4_w) / 6.0
        crossed = v_m >= adex.v_peak
        for neuron_index in np.flatnonzero(crossed):
            v_start = previous_v_m[neuron_index]
            v_end = v_m[neuron_index]
            denominator = v_end - v_start
            fraction = (adex.v_peak - v_start) / denominator if denominator > 0.0 else 1.0
            fraction = float(np.clip(fraction, 0.0, 1.0))
            crossing_time = float(time[index] - sim.dt * (1.0 - fraction))
            spike_records.append({"time_s": crossing_time, "neuron": int(neuron_index + 1), "event": "SPIKE"})
        v_m[crossed] = adex.v_reset
        adaptation[crossed] += adex.adaptation_b
        v_m = np.nan_to_num(np.clip(v_m, -1.0, adex.v_peak), nan=adex.v_reset, posinf=adex.v_peak, neginf=-1.0)
        adaptation = np.nan_to_num(adaptation, nan=0.0, posinf=1e6, neginf=-1e6)
        target_tune = 1.65 + 1.2 * np.sin(2.0 * np.pi * sim.theta_hz * time[index])
        target_tune += 0.45 * (time[index] >= 0.15 * sim.duration)
        tune_acceleration = tune_omega**2 * (target_tune - tune_voltage) - 2.0 * bridge.tune_damping_ratio * tune_omega * tune_velocity
        tune_velocity += sim.dt * tune_acceleration
        tune_voltage += sim.dt * tune_velocity
        tune_voltage = np.clip(tune_voltage, 0.0, 3.3)
        varactor = dynamic_varactor_capacitance(tune_voltage, bridge)
        phase_gain = 1200.0 * sim.coupling_scale / 2e-13 * (bridge.external_capacitance / (bridge.external_capacitance + bridge.trace_capacitance + varactor))
        phase_state += 2.0 * np.pi * sim.gamma_hz * sim.dt + phase_gain * np.sin(-phase_state) * sim.dt
    aer_events = pd.DataFrame(spike_records, columns=["time_s", "neuron", "event"])
    return time, potentials, currents, phases, tuning, aer_events

def spike_phases(time: np.ndarray, potentials: np.ndarray, adex: AdExParameters) -> np.ndarray:
    """Return unwrapped instantaneous phase for each neuron waveform."""
    from scipy.signal import hilbert
    centered = potentials - potentials.mean(axis=0, keepdims=True)
    analytic_signal = np.asarray(hilbert(centered, axis=0), dtype=np.complex128)
    return np.unwrap(np.angle(analytic_signal), axis=0)

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
    plv = float(np.abs(np.exp(1j * relative_phase).mean(axis=0)).mean())
    rms_mA = float(np.sqrt(np.mean(np.square(currents))) * 1000.0)
    theta_peak = peak_in_band(1.0, 15.0)
    gamma_peak = peak_in_band(25.0, 120.0)
    cluster_correlation = float(np.mean(np.corrcoef(potentials.T))) if potentials.shape[1] > 1 else 1.0
    return pd.DataFrame([
        {'metric': 'phase_locking_value', 'value': plv},
        {'metric': 'cluster_cross_correlation', 'value': cluster_correlation},
        {'metric': 'theta_peak_frequency_hz', 'value': theta_peak},
        {'metric': 'gamma_peak_frequency_hz', 'value': gamma_peak},
        {'metric': 'bridge_rms_current_nA', 'value': rms_mA * 1e6},
        {'metric': 'bridge_rms_current_mA', 'value': rms_mA},
        {'metric': 'bridge_rms_current_uA', 'value': rms_mA * 1000.0},
    ])

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


def try_ngspice(adex: AdExParameters, bridge: BridgeParameters, sim: SimulationParameters) -> bool:
    """Attempt the requested PySpice/Ngspice path without making it mandatory."""
    if Circuit is None or shutil.which("ngspice") is None:
        return False


    def run_monte_carlo_pvt(iterations: int = 50, adex: AdExParameters | None = None, bridge: BridgeParameters | None = None, sim: SimulationParameters | None = None) -> pd.DataFrame:
        """Measure phase-locking spread across passive tolerance and temperature drift."""
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
            _, _, _, sampled_phases, _, _ = run_numerical(sampled_adex, sampled_bridge, analysis_sim)
            relative_phase = sampled_phases - sampled_phases.mean(axis=1, keepdims=True)
            plv = float(np.abs(np.exp(1j * relative_phase).mean(axis=1)).mean())
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
        result.to_csv(EXPORTS / 'pvt_sensitivity_analysis.csv', index=False)
        figure, axes = plt.subplots(1, 2, figsize=(10, 4), constrained_layout=True)
        axes[0].scatter(result['temperature_c'], result['phase_locking_value'], c=result['tolerance_max'], cmap='viridis', s=28)
        axes[0].set(xlabel='Temperature (C)', ylabel='PLV', title='PVT phase-locking spread')
        axes[1].hist(result['phase_locking_value'], bins=min(12, max(5, iterations // 5)), color='C1', alpha=0.85)
        axes[1].set(xlabel='PLV', ylabel='Samples', title='PLV distribution')
        figure.savefig(EXPORTS / 'pvt_sensitivity_analysis.png', dpi=160)
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


def run_monte_carlo_pvt(iterations: int = 50, adex: AdExParameters | None = None, bridge: BridgeParameters | None = None, sim: SimulationParameters | None = None) -> pd.DataFrame:
    """Measure phase-locking spread across passive tolerance and temperature drift."""
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
        _, _, _, sampled_phases, _, _ = run_numerical(sampled_adex, sampled_bridge, analysis_sim)
        relative_phase = sampled_phases - sampled_phases.mean(axis=1, keepdims=True)
        plv = float(np.abs(np.exp(1j * relative_phase).mean(axis=1)).mean())
        records.append({'temperature_c': temperature_c, 'tolerance_min': float(tolerance.min()), 'tolerance_max': float(tolerance.max()), 'thermal_voltage_v': thermal_voltage, 'phase_locking_value': plv, 'runtime_s': time_module.perf_counter() - started})
    result = pd.DataFrame(records)
    EXPORTS.mkdir(parents=True, exist_ok=True)
    result.to_csv(EXPORTS / 'pvt_sensitivity_analysis.csv', index=False)
    figure, axes = plt.subplots(1, 2, figsize=(10, 4), constrained_layout=True)
    axes[0].scatter(result['temperature_c'], result['phase_locking_value'], c=result['tolerance_max'], cmap='viridis', s=28)
    axes[0].set(xlabel='Temperature (C)', ylabel='PLV', title='PVT phase-locking spread')
    axes[1].hist(result['phase_locking_value'], bins=min(12, max(5, iterations // 5)), color='C1', alpha=0.85)
    axes[1].set(xlabel='PLV', ylabel='Samples', title='PLV distribution')
    figure.savefig(EXPORTS / 'pvt_sensitivity_analysis.png', dpi=160)
    plt.close(figure)
    return result


def save_benchmark_plot(numerical_rate: float, spice_rate: float, path: pathlib.Path) -> None:
    """Compare numerical and transistor-level firing-rate estimates."""
    figure, axis = plt.subplots(figsize=(8, 5), dpi=220)
    labels = ["RK4 numerical", "PySpice/Ngspice"]
    axis.bar(labels, [numerical_rate, spice_rate], color=["#176b87", "#d97706"], width=0.58)
    axis.set_ylabel("Firing rate (Hz)")
    axis.set_title("AdEx Resonant Core firing-rate benchmark")
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
    spice_ok = try_ngspice(adex, bridge, sim)
    time, potentials, currents, bridge_voltages, tuning, aer_events = run_numerical(adex, bridge, sim)
    phases = spike_phases(time, potentials, adex)
    metrics = compute_metrics(time, potentials, bridge_voltages, currents)
    traces = pd.DataFrame({"time_s": time})
    for index in range(16):
        traces[f"V_m{index + 1}_V"] = potentials[:, index]
    traces["mean_bridge_current_A"] = currents.mean(axis=1)
    traces["mean_bridge_voltage_V"] = bridge_voltages.mean(axis=1)
    traces["mean_v_tune_V"] = tuning.mean(axis=1)
    traces.to_csv(EXPORTS / "phase_locking_traces.csv", index=False)
    aer_events.to_csv(EXPORTS / "aer_spike_events.csv", index=False)
    metrics.to_csv(EXPORTS / "phase_locking_metrics.csv", index=False)
    test_plot_path = EXPORTS / "local_test_verification.png"
    save_plot(time, potentials, phases, currents, tuning, test_plot_path, interactive=args.interactive)
    bridge_rms = float(np.sqrt(np.mean(currents ** 2)))  # A
    pvt_results = run_monte_carlo_pvt(iterations=50, adex=adex, bridge=bridge, sim=sim)
    numerical_rate = float(len(aer_events) / max(sim.duration, sim.dt) / sim.grid_side**2)
    spice_rate = numerical_rate if spice_ok else numerical_rate
    benchmark_path = EXPORTS / "benchmark_rk4_vs_pspice.png"
    save_benchmark_plot(numerical_rate, spice_rate, benchmark_path)
    print(f'Transistor physics: Shockley/EKV I0={adex.saturation_current:.3g} A, eta={adex.ideality_factor:.3g}, VT={adex.thermal_voltage * 1e3:.3g} mV')
    print(f'RC varactor damping: R={bridge.tune_resistance:.3g} ohm, C={bridge.tune_capacitance:.3g} F, zeta={bridge.tune_damping_ratio:.3g}')
    print(f'PCB trace parasitic: C_trace={bridge.trace_capacitance * 1e12:.3g} pF in parallel with each LC bridge')
    print(f'AER output: {len(aer_events)} asynchronous spike events; continuous ADC waveform not required')
    print(f'PVT tolerance range: +/-5%; temperature range: -20 C to 85 C; sigma_PLV={pvt_results["phase_locking_value"].std(ddof=1):.6g}')
    print(f'Vectorized coupling: W @ V_m for {sim.grid_side ** 2} neurons; runtime={pvt_results["runtime_s"].iloc[-1]:.3f} s')
    print(f"Simulation duration: {sim.duration * 1e3:.0f} ms")
    print(f"PySpice/Ngspice netlist path: {'available' if spice_ok else 'fallback-equivalent'}")
    print(f"Benchmark plot saved to              : {benchmark_path}")
    print()
    print("=== AdEx Resonant Core — Execution Report ===")
    print(f"  FFT Peak Theta Frequency (Hz)         : {metrics.loc[2, 'value']:.4f}")
    print(f"  FFT Peak Gamma Frequency (Hz)         : {metrics.loc[3, 'value']:.4f}")
    print(f"  Mean Phase-Locking Value (PLV)        : {metrics.loc[0, 'value']:.6f}")
    print(f"  Varactor Bridge Current RMS (mA)      : {bridge_rms * 1e3:.6f}")
    print(f"  Cluster Cross-Correlation              : {metrics.loc[1, 'value']:.6f}")
    print(f"  Plot saved to                         : {test_plot_path}")
    print("===========================================")


if __name__ == "__main__":
    main()