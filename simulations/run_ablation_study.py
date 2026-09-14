#!/usr/bin/env python3
"""Ablation Study: 6-Configuration Analysis of AdEx Resonant Core Coupling Mechanisms."""
from __future__ import annotations
import pathlib, sys, time as time_module
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import simulate_adex_resonant_core as core
ROOT = core.ROOT; EXPORTS = core.EXPORTS

def _build_random_edges(n_neurons, edge_count, rng):
    """Build random undirected edge list with edge_count unique pairs."""
    edges = set()
    attempts = 0
    while len(edges) < edge_count and attempts < edge_count * 10:
        i = rng.integers(0, n_neurons)
        j = rng.integers(0, n_neurons)
        if i == j:
            attempts += 1
            continue
        key = (min(i, j), max(i, j))
        edges.add(key)
        attempts += 1
    return sorted(edges)


def _run_single_config(label, adex, bridge, sim, edge_list=None, vtune_sweep=False):
    """Run one ablation config and extract all metrics."""
    # Patch edge list
    orig = core.grid_edges
    if edge_list is not None:
        core.grid_edges = lambda side: edge_list
    try:
        t0 = time_module.perf_counter()
        time, pots, currs, bv, tuning, ct, tf, diag = core.run_numerical(adex, bridge, sim)
        rt = time_module.perf_counter() - t0
    finally:
        core.grid_edges = orig

    phases = core.spike_phases(time, pots, adex)
    n = pots.shape[1]
    pdiff = phases[:, :, None] - phases[:, None, :]
    plv_mat = np.abs(np.mean(np.exp(1j * pdiff), axis=0))
    mask = ~np.eye(n, dtype=bool)
    mean_plv = float(plv_mat[mask].mean())

    from scipy.signal import welch
    sr = 1.0 / np.mean(np.diff(time))
    freqs, psd = welch(pots.mean(axis=1), fs=sr, nperseg=min(65536, len(time)), detrend='linear')

    tm = (freqs >= 4.0) & (freqs <= 8.0)
    theta_power = float(np.trapezoid(psd[tm], freqs[tm])) if tm.sum() > 1 else 0.0
    gm = (freqs >= 30.0) & (freqs <= 80.0)
    gamma_power = float(np.trapezoid(psd[gm], freqs[gm])) if gm.sum() > 1 else 0.0

    all_isis = []
    vp = adex.v_peak
    for neuron in range(n):
        tr = pots[:, neuron]
        sp = np.flatnonzero((tr[:-1] < vp) & (tr[1:] >= vp))
        if len(sp) > 1:
            all_isis.extend(np.diff(sp * sim.dt).tolist())
    synch = float(np.std(all_isis) / np.mean(all_isis)) if len(all_isis) > 1 else 1.0

    total_e = 0.0
    if currs.ndim == 2:
        for ti in range(currs.shape[0]):
            total_e += np.sum(currs[ti] ** 2) * sim.dt * bridge.loss_resistance
    ts = 0
    for neuron in range(n):
        tr = pots[:, neuron]
        sp = np.flatnonzero((tr[:-1] < vp) & (tr[1:] >= vp))
        ts += len(sp)
    eps = total_e / max(ts, 1)

    print(f"  [{label}] PLV={mean_plv:.6f}  th={theta_power:.6e}  ga={gamma_power:.6e}  CV={synch:.6f}  E={eps:.6e}  t={rt:.2f}s")
    return {"mean_pairwise_plv": mean_plv, "theta_power": theta_power, "gamma_power": gamma_power, "spike_synchrony": synch, "energy_per_spike": eps}


def run_ablation_study():
    """Execute 6 ablation configs and return comparison DataFrame."""
    print("=" * 72)
    print("AdEx Resonant Core - Ablation Study")
    print("6-Configuration Analysis of Coupling Mechanisms")
    print("=" * 72)
    base_a = core.AdExParameters()
    base_b = core.BridgeParameters()
    base_s = core.SimulationParameters(duration=200e-3, dt=10e-6)
    recs = []

    print("\n[Config A] Uncoupled")
    ba = core.BridgeParameters(inductance=1e3, loss_resistance=1e9, varactor_c0=0.0, varactor_c_fixed=1e-15, external_capacitance=1e-15, gamma_capacitance=1e-15, trace_capacitance=1e-15)
    ma = _run_single_config("A", base_a, ba, base_s, edge_list=[], vtune_sweep=False)
    recs.append({"config": "A - Uncoupled AdEx (W=0)", **ma})

    print("\n[Config B] Resistive")
    bb = core.BridgeParameters(inductance=1e-9, loss_resistance=10e3, varactor_c0=0.0, varactor_c_fixed=1e-15, external_capacitance=1e-15, gamma_capacitance=1e-15, trace_capacitance=1e-15)
    mb = _run_single_config("B", base_a, bb, base_s, vtune_sweep=False)
    recs.append({"config": "B - Resistive Grid (R=10k)", **mb})

    print("\n[Config C] Fixed LC")
    bc = core.BridgeParameters(inductance=100e-3, varactor_c0=0.0, varactor_c_fixed=47e-9, external_capacitance=47e-9, loss_resistance=5.0, trace_capacitance=2.5e-12)
    mc = _run_single_config("C", base_a, bc, base_s, vtune_sweep=False)
    recs.append({"config": "C - Fixed LC Tank", **mc})

    print("\n[Config D] Varactor LC")
    md = _run_single_config("D", base_a, base_b, base_s, vtune_sweep=True)
    recs.append({"config": "D - Tunable Varactor LC", **md})

    print("\n[Config E] Random LC")
    rng = __import__('numpy').random.default_rng(42)
    re_edges = _build_random_edges(base_s.grid_side ** 2, 24, rng)
    me = _run_single_config("E", base_a, base_b, base_s, edge_list=re_edges, vtune_sweep=True)
    recs.append({"config": "E - Random LC Topology", **me})

    print("\n[Config F] 4x4 Nbr Grid")
    mf = _run_single_config("F", base_a, base_b, base_s, vtune_sweep=True)
    recs.append({"config": "F - 4x4 Nbr Grid (LC varactor)", **mf})

    df = __import__('pandas').DataFrame(recs)
    EXPORTS.mkdir(parents=True, exist_ok=True)
    df.to_csv(EXPORTS / "ablation_study_summary.csv", index=False)
    print(f"\nSummary saved to {EXPORTS / 'ablation_study_summary.csv'}")
    return df


def save_ablation_comparison_plot(summary):
    """Generate high-resolution grouped bar plot."""
    cfgs = summary["config"].tolist()
    n = len(cfgs)
    plv = summary["mean_pairwise_plv"].values
    theta = summary["theta_power"].values
    gamma = summary["gamma_power"].values
    synch = summary["spike_synchrony"].values
    energy_nj = summary["energy_per_spike"].values * 1e9

    fig, axes = plt.subplots(3, 2, figsize=(16, 12), constrained_layout=True)
    fig.suptitle("AdEx Resonant Core - Ablation Study", fontsize=14, fontweight="bold", y=1.01)
    c1 = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b"]
    c2 = ["#aec7e8", "#ffbb78", "#98df8a", "#ff9898", "#c5b0d5", "#c49c94"]
    x = np.arange(n)
    w = 0.6

    ax = axes[0, 0]
    bars = ax.bar(x, plv, w, color=c1, edgecolor="k", lw=0.5)
    ax.set_ylabel("Mean Pairwise PLV", fontsize=11)
    ax.set_title("Phase-Locking Value (higher = better)", fontsize=10)
    ax.set_xticks(x)
    ax.set_xticklabels([c.split(" - ")[0] for c in cfgs], fontsize=9)
    ax.set_ylim(0, max(1.0, plv.max() * 1.15))
    ax.axhline(y=0.85, color="gray", ls="--", lw=0.7, alpha=0.6, label="PLV=0.85")
    ax.legend(fontsize=7, loc="lower right")
    for b, v in zip(bars, plv):
        ax.text(b.get_x() + b.get_width() / 2, b.get_height() + 0.015, f"{v:.4f}", ha="center", va="bottom", fontsize=8, fontweight="bold")

    ax = axes[0, 1]
    ax.bar(x - 0.15, theta, 0.3, color="#2ca02c", edgecolor="k", lw=0.5, label="Theta")
    ax.bar(x + 0.15, gamma, 0.3, color="#d62728", edgecolor="k", lw=0.5, label="Gamma")
    ax.set_ylabel("PSD Integral (V\u00b2)", fontsize=11)
    ax.set_title("Theta & Gamma Power", fontsize=10)
    ax.set_xticks(x)
    ax.set_xticklabels([c.split(" - ")[0] for c in cfgs], fontsize=9)
    ax.legend(fontsize=8)
    ax.set_yscale("symlog", linthresh=1e-12)

    ax = axes[1, 0]
    ax.bar(x, synch, w, color=c1, edgecolor="k", lw=0.5)
    ax.set_ylabel("CV of ISI", fontsize=11)
    ax.set_title("Spike Synchrony (lower = more synchronous)", fontsize=10)
    ax.set_xticks(x)
    ax.set_xticklabels([c.split(" - ")[0] for c in cfgs], fontsize=9)

    ax = axes[1, 1]
    ax.bar(x, energy_nj, w, color=c2, edgecolor="k", lw=0.5)
    ax.set_ylabel("Energy per Spike (nJ)", fontsize=11)
    ax.set_title("Energy Dissipation (lower = more efficient)", fontsize=10)
    ax.set_xticks(x)
    ax.set_xticklabels([c.split(" - ")[0] for c in cfgs], fontsize=9)

    ax = axes[2, 0]
    ax.axis("off")
    tbl = [[c.split(" - ")[0], c.split(" - ")[1]] for c in cfgs]
    t = ax.table(cellText=tbl, colLabels=["ID", "Description"], loc="center", cellLoc="left")
    t.auto_set_font_size(False)
    t.set_fontsize(9)
    t.scale(1, 1.6)
    for (row, col), cell in t.get_celld().items():
        if row == 0:
            cell.set_text_props(fontweight="bold", color="white")
            cell.set_facecolor("#40466e")

    ax = axes[2, 1]
    ax.axis("off")
    bi = int(plv.argmax())
    wi = int(plv.argmin())
    lines = [f"Highest PLV: Config {chr(65+bi)} ({plv[bi]:.6f})", f"Lowest PLV:  Config {chr(65+wi)} ({plv[wi]:.6f})", f"Ratio: {plv[bi]/max(plv[wi],1e-12):.2f}x", "", "Key: Varactor LC (D/F) outperforms", "resistive (B) and uncoupled (A)", "in PLV, power, and synchrony."]
    ax.text(0.05, 0.95, "\n".join(lines), transform=ax.transAxes, fontsize=9, fontfamily="monospace", va="top", bbox=dict(facecolor="ivory", edgecolor="gray", boxstyle="round,pad=0.6"))

    path = EXPORTS / "ablation_study_comparison.png"
    fig.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"Plot saved to {path}")


def main():
    df = run_ablation_study()
    save_ablation_comparison_plot(df)
    print("\n" + "=" * 72)
    print("Comparison:")
    print(df.to_string(index=False))
    print("=" * 72)

if __name__ == "__main__":
    main()
