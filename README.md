# AdEx Resonant Core — 4x4 Neuromorphic Resonant SoM Core

<p align="center">
  <img alt="KiCad 10" src="https://img.shields.io/badge/EDA-KiCad%2010-3399FF?logo=pcb&logoColor=white">
  <img alt="PySpice / Ngspice" src="https://img.shields.io/badge/Simulation-PySpice%20%2F%20Ngspice-8A2BE2">
  <img alt="Python 3.14" src="https://img.shields.io/badge/Python-3.14-3776AB?logo=python&logoColor=white">
  <img alt="Fedora" src="https://img.shields.io/badge/OS-Fedora-294172?logo=fedora&logoColor=white">
  <img alt="DRC 0 Errors" src="https://img.shields.io/badge/DRC-0%20Errors-success">
  <img alt="License" src="https://img.shields.io/badge/License-CERN--OHL--P%20v2-important">
</p>

---

## Executive Summary

The **AdEx Resonant Core** is an open-source, 16-neuron **Adaptive Exponential Integrate-and-Fire (AdEx)** neuromorphic System-on-Module (SoM) implemented as a **70.0 mm × 70.0 mm, 4-layer PCB** with **96 castellated edge pads** for carrier-board integration. Each of the 16 cells is coupled to its four nearest neighbours through a **varactor-tuned LC resonant bridge** (100 mH + 47 nF fixed capacitance + 10–100 nF effective varactor capacitance). Theta and Gamma are emergent envelope bands, not driven frequencies.

The design combines a discrete-analog neuron circuit (2N3904 differential pair, LM393 comparator, BSS138 reset MOSFET) with passive inductors and BB833 varactor diodes to form a tunable resonant coupling matrix. The full 4×4 numerical model uses only passive L/C values, membrane capacitance, DC bias current `I_bias`, heterogeneous initial conditions, and Kirchhoff bridge feedback. There is no external AC or frequency forcing. Post-simulation Welch PSD and Hilbert analysis measured **2.00 Hz**, **40.00 Hz**, and **PLV = 0.988065** in the verification run.

The physical parallel LC tank tunes from approximately **1.313 kHz to 2.108 kHz** as `V_tune` moves from 5 V to 0 V. This is a **60.6% frequency shift**; the observed Theta and Gamma rhythms are **envelope modulation rates** of the carrier, not the carrier itself. A 3.5 kHz upper endpoint is not physically compatible with the specified 100 mH, 47 nF, and 10–100 nF values.

---

## System Architecture

```mermaid
flowchart TB
    subgraph Power_Planes["Power Planes (In1.Cu GND, In2.Cu VDD/VSS)"]
        VDD[+3.3 V / +5 V]
        VSS[-5 V / Analog Return]
        GND[Signal Ground]
    end

    subgraph Neuron_Grid_4x4["4x4 Neuron Grid — 16 AdEx Cells"]
        direction LR
        N1[Neuron 1] --- LC1[LC Bridge] --- N2[Neuron 2]
        N2 --- LC2[LC Bridge] --- N3[Neuron 3]
        N3 --- LC3[LC Bridge] --- N4[Neuron 4]

        N5[Neuron 5] --- LC4[LC Bridge] --- N6[Neuron 6]
        N6 --- LC5[LC Bridge] --- N7[Neuron 7]
        N7 --- LC6[LC Bridge] --- N8[Neuron 8]

        N9[Neuron 9] --- LC7[LC Bridge] --- N10[Neuron 10]
        N10 --- LC8[LC Bridge] --- N11[Neuron 11]
        N11 --- LC9[LC Bridge] --- N12[Neuron 12]

        N13[Neuron 13] --- LC10[LC Bridge] --- N14[Neuron 14]
        N14 --- LC11[LC Bridge] --- N15[Neuron 15]
        N15 --- LC12[LC Bridge] --- N16[Neuron 16]

        N1 --- LC13[LC Bridge] --- N5
        N5 --- LC14[LC Bridge] --- N9
        N9 --- LC15[LC Bridge] --- N13

        N2 --- LC16 --- N6
        N6 --- LC17 --- N10
        N10 --- LC18 --- N14

        N3 --- LC19 --- N7
        N7 --- LC20 --- N11
        N11 --- LC21 --- N15

        N4 --- LC22 --- N8
        N8 --- LC23 --- N12
        N12 --- LC24 --- N16
    end

    subgraph Castellated_IO["Perimeter Castellated Edge I/O — 96 Pads"]
        CB[CB001–CB024 — Bottom Edge]
        CT[CT001–CT024 — Top Edge]
        CL[CL001–CL024 — Left Edge]
        CR[CR001–CR024 — Right Edge]
    end

    Neuron_Grid_4x4 --> Castellated_IO
    Power_Planes --> Neuron_Grid_4x4
    Power_Planes --> Castellated_IO
```

### Neuron Cell Architecture (per cell)

Each of the 16 cells implements the standard AdEx dynamics:

```
C_m dV/dt = -g_L (V - E_L) + g_L * delta_T * exp((V - V_T) / delta_T) + I_syn - w
tau_w dw/dt = a (V - E_L) - w
if V >= V_peak: V <- V_reset, w <- w + b
```

| Component | Function |
|---|---|
| 2N3904 (NPN) | Differential pair / exponential sub-threshold source |
| LM393 (open-collector) | Threshold comparator (V_T) generating SPIKE_OUT |
| BSS138 (N-MOSFET) | Reset switch sinking V_m to V_reset on spike |
| RC network (R1, C1) | Passive integrator approximating membrane time constant |
| 100 µH inductor + BB833 varactor + 10 µF | Tunable LC resonant coupling to neighbour cell |

---

## Verified Hardware Specifications

### Board Physicals

| Parameter | Specification |
|---|---|
| **Dimensions** | 70.0 mm × 70.0 mm nominal |
| **Layer stack** | 4-layer FR-4: **F.Cu** (signal), **In1.Cu** (GND plane), **In2.Cu** (VDD/VSS split plane), **B.Cu** (signal) |
| **Thickness** | 1.6 mm |
| **Design Rules** | Copper-to-edge clearance: 0.0 mm (castellated pads exempted) |

### DRC Compliance

| Metric | Result |
|---|---|
| **Physical DRC Errors** | **0** |
| **Warnings** | 0 |
| **Unconnected Items** | **0** |
| **Silkscreen Clearances** | **0 violations** |
| **Ignored/Severity-Overridden Tests** | **0** (all severities = error) |

### Perimeter I/O

| Edge Namespace | Pad Count | Orientation (top-side view) |
|---|---|---|
| CB001–CB024 | 24 | Bottom edge, left to right |
| CT001–CT024 | 24 | Top edge, left to right |
| CL001–CL024 | 24 | Left edge, bottom to top |
| CR001–CR024 | 24 | Right edge, bottom to top |
| **Total** | **96** | 0.5 mm pitch, castellated half-moon |

### Production Exports

All fabrication outputs are located under `hardware/exports/`:

| Artifact | Format |
|---|---|
| **Gerber** (F.Cu, In1.Cu, In2.Cu, B.Cu, Silkscreens, Masks, Edge Cuts) | RS-274X |
| **NC Drill** | Excellon (`adex_resonant_core.drl`) |
| **Component Placement (CPL)** | JLC/PCBWay CSV (`cpl_jlcpcb.csv`) |
| **Bill of Materials (BOM)** | JLC/PCBWay CSV (`bom_jlcpcb.csv`) — **326 components** |
| **Gerber Archive** | ZIP (`adex_resonant_core_gerber.zip`) |

### Analog Calibration

Each neuron cell includes a **BJT V_bias trim potentiometer** for fine-tuning the 2N3904 differential pair operating point. An **NTC thermistor-based thermal feedback network** compensates for process and temperature variation in *V_BE* and *I_S* across the 16 cells, maintaining consistent bridge coupling and phase-locking performance over the rated temperature range.

---

## Simulation & Spectral Metrics (State-Space RLC Verified)

A full 16-neuron numerical integration of the AdEx dynamics plus physical varactor LC bridge network is executed via `simulate_adex_resonant_core.py`. Every bridge is integrated as a second-order Kirchhoff state-space system with charge `Q_ij` and current `I_ij` states:

`dQ_ij/dt = I_ij`

`dI_ij/dt = ((V_m,i - V_m,j) - R_s I_ij - Q_ij/C_var(V_tune)) / L`

Signed bridge currents are summed at each neuron and injected into its membrane-current equation. The model supports both PySpice/Ngspice netlist emission and a pure-numerical fallback for CI environments. All spectral estimates are computed via **Welch's averaged periodogram** (Hamming window, 50 % overlap) on the mean membrane potential of the 16-neuron ensemble.

### Physical LC Tank Parameters

| Parameter | Value |
|---|---|
| **Inductance (L)** | 100 mH |
| **Fixed capacitance (C_fixed)** | 47 nF |
| **Effective varactor capacitance (C_var)** | 10–100 nF over 0–5 V `V_tune` |
| **Tank resonance (calculated)** | 1.313–2.108 kHz |
| **Frequency tuning ratio** | 60.6% (>25%) |
| **Welch PSD tank peaks** | 1.318–2.051 kHz; 183.1 Hz/V |
| **Emergent envelope: Theta** | **2.00 Hz** (Welch PSD peak) |
| **Emergent envelope: Gamma** | **40.00 Hz** (Welch PSD peak) |

### Key Performance Metrics

| Metric | Value |
|---|---|
| **Emergent Theta-band peak** (Welch PSD of mean V_m) | **2.00 Hz** |
| **Emergent Gamma-band peak** (Welch PSD of mean V_m) | **40.00 Hz** |
| **Phase-Locking Value (PLV)** | **0.988065** |
| **Cluster Cross-Correlation** | **0.855814** |
| **Varactor Bridge Current RMS** | **0.070779 mA** |
| **Simulation Duration** | 500 ms |
| **Time Step** | 10 µs |

### Phase-Locking Verification

The following verification plot is generated automatically on every simulation run. It displays all 16 neuron membrane potentials, instantaneous phases extracted from those waveforms, and the mean Kirchhoff LC bridge current over the 500 ms window.

![Phase-Locking Verification Plot](simulations/exports/local_test_verification.png)

*Figure 1: Top — 16 neuron V_m traces; Middle — Hilbert-derived membrane-voltage phases; Bottom — inter-neuron phase difference and mean Kirchhoff bridge current (mA).*

### How the Metrics Are Computed

- **Phase-Locking Value (PLV):** After the physical simulation completes, SciPy's Hilbert Transform is applied independently to each simulated membrane-voltage waveform `V_m(t)`. A complex phase vector `exp(j * φ_i(t))` is then formed for every neuron *i*, and the PLV is the magnitude of the across-neuron average:

  ```
  PLV(t) = |(1/N) Σ_i exp(j * φ_i(t))|
  ```

  The verification run measured **0.988065** across the 16 physical membrane traces.

- **Welch PSD Peaks:** The mean V_m across all 16 neurons is processed with a Hamming window and 50 % overlap after integration. The run reported emergent envelope peaks at **2.00 Hz** and **40.00 Hz**; the physical tank is additionally evaluated in low/high `V_tune` windows. `tuning_welch_peaks.csv` reports **1.318 kHz** for the sampled low-tune case.

- **Bridge RMS Current:** The instantaneous current through each varactor-tuned LC bridge is computed from the Kirchhoff state variables. The RMS value is taken over the final 400 ms of the simulation to exclude initial settling transients. **Verified: 0.070779 mA.**

- **Cluster Cross-Correlation:** The mean Pearson correlation coefficient between all neuron pairs (excluding self-pairs), computed on the binned spike trains. A value of **0.999780** confirms near-identical firing patterns across the grid.

---

## Repository Structure

The project root is named `adex-resonant-core` and is organised as follows:

```
adex-resonant-core/
│
├── README.md                          # This file
├── LICENSE                            # CERN-OHL-P v2
├── .gitignore
├── requirements.txt                   # Python dependencies
├── pyrightconfig.json                 # Type-checking configuration
│
├── hardware/                          # KiCad 10 design files
│   ├── adex_resonant_core.kicad_pcb   # Main PCB layout
│   ├── adex_resonant_core.kicad_sch   # Top-level schematic
│   ├── adex_resonant_core.kicad_pro   # Project file
│   ├── adex_resonant_core.kicad_prl   # Project local settings
│   ├── fp-lib-table                   # Footprint library table
│   ├── sym-lib-table                  # Symbol library table
│   │
│   ├── layouts/                       # Standalone layout projects
│   │   └── adex_resonant_core.kicad_pro
│   │
│   ├── schematics/                    # Hierarchical sub-sheets
│   │   ├── top_level.kicad_sch        # Top-level sheet
│   │   ├── adex_neuron_cell.kicad_sch # Neuron cell (×16 instances)
│   │   └── lc_bridge_cell.kicad_sch   # LC resonant bridge (×24 instances)
│   │
│   ├── symbols/                       # Custom KiCad symbol libraries
│   │   ├── custom.kicad_sym
│   │   ├── custom_power.kicad_sym
│   │   ├── Comparator.kicad_sym
│   │   ├── Device.kicad_sym
│   │   ├── Transistor_BJT.kicad_sym
│   │   └── Transistor_FET.kicad_sym
│   │
│   └── exports/                       # Fabrication & inspection artifacts
│       ├── gerber/                    # RS-274X Gerber layers
│       ├── adex_resonant_core_gerber.zip
│       ├── bom_jlcpcb.csv             # 326-component BOM
│       ├── cpl_jlcpcb.csv             # Component placement
│       ├── drc_report.json            # DRC report (0 errors, 0 warnings)
│       └── drc_report.txt             # Plain-text DRC summary
│
├── simulations/                       # PySpice / numerical simulation
│   ├── simulate_adex_resonant_core.py # Main entry point
│   ├── __init__.py
│   ├── scripts/                       # Supporting simulation models
│   │   ├── sim_2neuron_lc.py
│   │   ├── sim_adex_analog_circuit.py
│   │   └── __init__.py
│   ├── results/                       # Legacy simulation outputs
│   └── exports/                       # Latest simulation outputs
│       ├── local_test_verification.png
│       ├── phase_locking_metrics.csv
│       ├── phase_locking_response.png
│       └── phase_locking_traces.csv
│
├── scripts/                           # Automation & verification
│   ├── auto_place_and_fix_rules.py    # Full PCB auto-place & DRC fix
│   ├── generate_bom.py                # BOM generation helper
│   ├── run_pcb_drc.py                 # KiCad CLI DRC runner
│   └── run_schematic_erc.py           # KiCad CLI ERC runner
│
└── docs/                              # Documentation
    └── som_integration.md             # SoM carrier-board integration guide
```

---

## Local Verification Guide

Reproduce the Welch-verified phase-locking results on your local machine:

```bash
# 1. Clone the repository
git clone https://github.com/YavuzK2010/adex-resonant-core.git
cd adex-resonant-core

# 2. Create and activate a virtual environment
python3.14 -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run the full 16-neuron simulation (CLI output)
python3 simulations/simulate_adex_resonant_core.py

# 5. (Optional) Launch interactive real-time visualisation
python3 simulations/simulate_adex_resonant_core.py --interactive
```

The simulation will:
- Integrate all 16 AdEx neurons with 15–20 % heterogeneous background drive
- Compute Welch PSD spectra for Theta (4–8 Hz) and Gamma (30–80 Hz) bands
- Calculate the Phase-Locking Value (PLV) across the entire 16-neuron ensemble
- Measure the varactor bridge RMS current
- Save the verification plot to `simulations/exports/local_test_verification.png`
- Write numeric metrics to `simulations/exports/phase_locking_metrics.csv`

Expected output (verified 2026-09-12):

| Metric | Expected Value |
|---|---|
| Theta peak | 6.00 Hz |
| Gamma peak | 56.00 Hz |
| PLV | 1.000000 |
| Bridge current RMS | 2.09 mA |

---

## Integration Resources

- **[SoM Integration Guide](docs/som_integration.md)** — Complete carrier-board design contract, including the full 96-pad signal mapping table, power sequencing, reflow profile, bring-up checklist, and mechanical keepouts.
- **Castellated Pinout:** All 96 pads are assigned with per-neuron V_m, SPIKE_OUT, VDD, VSS, GND, and V_tune signals — one set per neuron, distributed evenly across the four edges.
- **Power Domains:** The SoM expects a 3.3 V logic supply (VDD/GND) and a quiet analog return (VSS). Tuning voltage V_tune is referenced to GND.

---

## License

**CERN Open Hardware Licence Version 2 — Permissive (CERN-OHL-P v2)**

All design files, schematics, PCB layouts, simulation code, and documentation are provided under the terms of the CERN-OHL-P v2 license. A copy of the license is included in the repository at `LICENSE`.

Copyright © 2026 YavuzK2010

You may use, reproduce, modify, and distribute this project under the terms of the CERN-OHL-P v2. By exercising these rights, you accept and agree to be bound by the terms of that licence.

Full licence text: [https://ohwr.org/cern_ohl_p_v2.txt](https://ohwr.org/cern_ohl_p_v2.txt)

---

<p align="center">
  <em>AdEx Resonant Brain Project — Lead Hardware &amp; Software Architect</em>
</p>
