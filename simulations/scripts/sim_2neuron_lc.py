#!/usr/bin/env python3
"""
2-Neuron AdEx Model Coupled via an LC Resonant Bridge
=======================================================

Simulates two Adaptive Exponential Integrate-and-Fire (AdEx) neurons
connected through a series LC resonant circuit (L = 10 mH, C_var = 1.58 uF,
R_loss = 5.0 Ohm).  Integration: RK4 (AdEx) + Implicit Euler (LC) @ dt = 10 us.

Outputs:
  simulations/results/phase_locking_signals.png
  simulations/results/phase_locking_data.csv
"""

from __future__ import annotations
import dataclasses
import pathlib
from typing import Tuple

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

RESULTS_DIR = pathlib.Path(__file__).resolve().parents[1] / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


@dataclasses.dataclass(frozen=True)
class AdExParams:
    """Adaptive Exponential Integrate-and-Fire (SI units)."""
    C_m: float = 200e-12
    g_L: float = 10e-9
    E_L: float = -70e-3
    V_T: float = -50e-3
    Delta_T: float = 2e-3
    a: float = 0.5e-9
    b: float = 60e-12
    tau_w: float = 30e-3
    V_reset: float = -70e-3
    V_peak: float = 0.0


@dataclasses.dataclass(frozen=True)
class LCParams:
    """Series LC resonant bridge parameters (SI units)."""
    L: float = 10e-3
    C_var: float = 1.58e-6
    R_loss: float = 5.0


@dataclasses.dataclass(frozen=True)
class SolverParams:
    """Numerical integration settings."""
    dt: float = 10e-6
    t_max: float = 1.0

# ---------------------------------------------------------------------------
# AdEx derivative (single neuron)
# ---------------------------------------------------------------------------
def adex_derivatives(
    V_m: float, w: float, I_in: float, p: AdExParams,
) -> Tuple[float, float]:
    """Return dV_m/dt and dw/dt for one AdEx neuron."""
    V_ms = max(min(V_m, p.V_peak), p.E_L)
    ea = (V_ms - p.V_T) / p.Delta_T
    et = p.g_L * p.Delta_T * np.exp(ea)
    dv = (p.g_L * (p.E_L - V_ms) + et - w + I_in) / p.C_m
    dw = (p.a * (V_ms - p.E_L) - w) / p.tau_w
    return dv, dw


# ---------------------------------------------------------------------------
# Simulation loop -- IMEX: RK4 for AdEx, Implicit Euler for LC bridge
# ---------------------------------------------------------------------------
def simulate(
    adex_p: AdExParams = AdExParams(),
    lc_p: LCParams = LCParams(),
    solver_p: SolverParams = SolverParams(),
    I_app1: float = 400e-12,
    I_app2: float = 380e-12,
) -> pd.DataFrame:
    """Run the 2-neuron + LC bridge simulation.

    Returns a DataFrame with columns:
        time (s), V_m1 (V), w1 (A), V_m2 (V), w2 (A),
        I_couple (A), V_C (V)
    """
    dt = solver_p.dt
    n = int(solver_p.t_max / dt)
    t_arr = np.arange(n, dtype=np.float64) * dt
    data = np.zeros((n, 6))

    v1, w1, v2, w2 = adex_p.E_L, 0.0, adex_p.E_L, 0.0
    ic, vc = 0.0, 0.0

    denom = 1.0 + dt * lc_p.R_loss / lc_p.L + dt**2 / (lc_p.L * lc_p.C_var)

    for i in range(n):
        data[i, :] = (v1, w1, v2, w2, ic, vc)

        # --- RK4 for AdEx neurons (ic fixed during sub-steps) ---------------
        def nf(s: np.ndarray) -> np.ndarray:
            v1_: float = float(s[0])
            w1_: float = float(s[1])
            v2_: float = float(s[2])
            w2_: float = float(s[3])
            dv1, dw1 = adex_derivatives(v1_, w1_, I_app1 - ic, adex_p)
            dv2, dw2 = adex_derivatives(v2_, w2_, I_app2 + ic, adex_p)
            return np.array([dv1, dw1, dv2, dw2])

        ns = np.array([v1, w1, v2, w2])
        k1 = nf(ns)
        k2 = nf(ns + 0.5 * dt * k1)
        k3 = nf(ns + 0.5 * dt * k2)
        k4 = nf(ns + dt * k3)
        ns_new = ns + (dt / 6.0) * (k1 + 2.0 * k2 + 2.0 * k3 + k4)

        v1 = max(min(float(ns_new[0]), adex_p.V_peak), adex_p.E_L)
        w1 = float(ns_new[1])
        v2 = max(min(float(ns_new[2]), adex_p.V_peak), adex_p.E_L)
        w2 = float(ns_new[3])

        # --- Implicit Euler: LC bridge (unconditionally stable) ------------
        ic = (ic + dt / lc_p.L * (v1 - v2 - vc)) / denom
        vc += dt * ic / lc_p.C_var

        # --- Spike detection & reset ---------------------------------------
        if v1 >= adex_p.V_peak:
            v1 = adex_p.V_reset
            w1 += adex_p.b
        if v2 >= adex_p.V_peak:
            v2 = adex_p.V_reset
            w2 += adex_p.b

    df = pd.DataFrame(
        data,
        columns=["V_m1", "w1", "V_m2", "w2", "I_couple", "V_C"],
    )
    df.insert(0, "time", t_arr)
    return df

# ---------------------------------------------------------------------------
# Plotting
# ---------------------------------------------------------------------------
def plot_results(df: pd.DataFrame, save_path: pathlib.Path) -> None:
    """2-panel figure: membrane potentials + coupling current."""
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 6), sharex=True)
    t: np.ndarray = df["time"].to_numpy(dtype=np.float64) * 1e3

    ax1.plot(t, df["V_m1"].to_numpy(dtype=np.float64) * 1e3,
             label=r"$V_{m1}$", color="C0", lw=0.8)
    ax1.plot(t, df["V_m2"].to_numpy(dtype=np.float64) * 1e3,
             label=r"$V_{m2}$", color="C1", lw=0.8)
    ax1.set_ylabel("Membrane potential (mV)")
    ax1.legend(fontsize=9)
    ax1.grid(alpha=0.3)

    ax2.plot(t, df["I_couple"].to_numpy(dtype=np.float64) * 1e9,
             color="C2", lw=0.8)
    ax2.set_ylabel("Coupling current (nA)")
    ax2.set_xlabel("Time (ms)")
    ax2.grid(alpha=0.3)

    fig.suptitle(  # type: ignore[arg-type]
        "2-Neuron AdEx + LC Resonant Bridge - Phase-Locking Dynamics",
        fontsize=13,
    )
    fig.tight_layout()
    fig.savefig(str(save_path), dpi=150, bbox_inches="tight")  # type: ignore[arg-type]
    plt.close(fig)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    ap, lp, sp = AdExParams(), LCParams(), SolverParams()

    f0 = 1.0 / (2.0 * np.pi * np.sqrt(lp.L * lp.C_var))
    print(f"[INFO] LC resonant freq  f0 = {f0:.1f} Hz  "
          f"(T0 = {1e3 / f0:.1f} ms)")

    df = simulate(ap, lp, sp)

    csv = RESULTS_DIR / "phase_locking_data.csv"
    df.to_csv(csv, index=False, float_format="%.12g")
    print(f"[INFO] Data saved -> {csv}  ({len(df)} rows)")

    png = RESULTS_DIR / "phase_locking_signals.png"
    plot_results(df, png)

    n1 = int(max(df["w1"].to_numpy(dtype=np.float64)) / ap.b) if max(df["w1"].to_numpy(dtype=np.float64)) > 0 else 0
    n2 = int(max(df["w2"].to_numpy(dtype=np.float64)) / ap.b) if max(df["w2"].to_numpy(dtype=np.float64)) > 0 else 0
    print(f"[INFO] Neuron 1 spikes: {n1}")
    print(f"[INFO] Neuron 2 spikes: {n2}")


if __name__ == "__main__":
    main()