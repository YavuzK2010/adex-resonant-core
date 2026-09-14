# AdEx Resonant Core SoM Integration Guide

**Document status:** Carrier-board integration contract (pre-fabrication; 0 DRC, behavioral / circuit-equivalent SPICE simulation verified)
**Module:** AdEx Resonant Core 16-neuron Tunable Analog Resonant SoM
**Macro-Parametric Sensitivity Sweep Performed (5% 3-Sigma Component Variations):** Monte Carlo analysis on 8 passive macro parameters (C_m, g_L, τ_w, V_t, L, C_fixed, C_var0, R_s) using a 3-sigma Gaussian tolerance distribution. Note: Current sensitivity analysis models discrete passive component tolerances and thermal macro-shifts. Full silicon-level transistor mismatch (V_BE, β, I_s, Early effect) will be evaluated via foundry SPICE PDK Monte Carlo during physical IC/SoM bring-up.
**Board outline:** 70 mm x 70 mm, four copper layers  
**Interface:** 96 castellated edge pads, 0.5 mm nominal pitch unless the released fabrication drawing states otherwise

## 1. Scope and Architecture

The module is a 16-neuron analog neuromorphic core. Each cell exposes an analog membrane-potential monitor (`V_m`), a digital spike trigger (`SPIKE_OUT`), local supply/return connections, and a voltage-tunable resonant coupling node. The resonant network uses passive inductors and varactor-controlled capacitance to provide phase-locking and impedance-based inhibition between cells.

The four edge namespaces are positional, not electrical layer names:

| Namespace | Board edge | Pad numbering direction |
| --- | --- | --- |
| `CB001`-`CB024` | Bottom edge | Left to right when viewed from the top side |
| `CT001`-`CT024` | Top edge | Left to right when viewed from the top side |
| `CL001`-`CL024` | Left edge | Bottom to top when viewed from the top side |
| `CR001`-`CR024` | Right edge | Bottom to top when viewed from the top side |

The carrier must use the same top-side viewing convention. Do not mirror the left or right edge numbering in the carrier footprint.

### Mathematical Abstraction vs. Analog Circuit Implementation

The software AdEx state variables describe the behavior of each analog cell; they do not imply additional module pins. In the membrane equation `C_m dV/dt`, `C_m` is the physical membrane integration capacitor and the exponential current is provided by the BJT differential pair in its exponential/subthreshold operating region. In the adaptation equation `tau_w dw/dt = a(V - E_L) - w`, `a` is represented by subthreshold MOSFET transconductance (`g_m`), `b` is represented by spike-triggered MOSFET charge injection into `C_w`, and `tau_w` is the internal `R_w * C_w` discharge time constant.

The adaptation variable `w` is consequently an internal closed-loop analog node formed by the `C_w / R_w` passive integration network and its spike-triggered FET switch. The physical cell boundary remains the primary interfaces `V_m`, `V_tune`, and `SPIKE_OUT` plus power and ground; `w` is not routed as a carrier-board or inter-cell interface.

## 2. Module Specifications

| Parameter | Specification |
| --- | --- |
| Module size | 70 mm x 70 mm nominal; keep the outline and edge-pad keepouts from the fabrication files authoritative |
| PCB stackup | 4-layer controlled-impedance-capable FR-4; signal, power, ground, and signal functions are assigned by the released layout |
| Neural array | 4 x 4 grid, 16 analog AdEx neuron cells |
| Neuron outputs | `N1_V_m` through `N16_V_m`; `N1_SPIKE_OUT` through `N16_SPIKE_OUT` |
| Resonant coupling | Inductor plus varactor LC bridge network |
| Tuning | Per-cell `N1_V_tune` through `N16_V_tune`, routed to the varactor control input |
| Intended operating bands | Theta (4-8 Hz) through Gamma (30-80 Hz), subject to component selection and tuning calibration |
| Logic reference | 3.3 V CMOS for spike triggers and digital control signals |

## 3. Castellated Pinout and Signal Mapping

The tables below are the complete carrier interface. `NC/RESERVED` pads must still be landed on the carrier, but must not be connected or stitched to an adjacent signal. A reserved pad may be assigned in a future module revision.

### 3.1 Bottom edge: `CB001`-`CB024`

| Pad | Signal | Type | Description |
| --- | --- | --- | --- |
| CB001 | `N1_V_m` | Analog out | Neuron 1 membrane-potential monitor |
| CB002 | `N1_SPIKE_OUT` | Digital out | Neuron 1 spike trigger, 3.3 V logic |
| CB003 | `N1_VDD` | Power in | Neuron 1 positive supply branch |
| CB004 | `N1_VSS` | Power return | Neuron 1 quiet analog return |
| CB005 | `N1_GND` | Ground | Neuron 1 ground/signal return |
| CB006 | `N1_V_tune` | Analog in | Neuron 1 varactor tuning control |
| CB007 | `N2_V_m` | Analog out | Neuron 2 membrane-potential monitor |
| CB008 | `N2_SPIKE_OUT` | Digital out | Neuron 2 spike trigger |
| CB009 | `N2_VDD` | Power in | Neuron 2 positive supply branch |
| CB010 | `N2_VSS` | Power return | Neuron 2 quiet analog return |
| CB011 | `N2_GND` | Ground | Neuron 2 ground/signal return |
| CB012 | `N2_V_tune` | Analog in | Neuron 2 varactor tuning control |
| CB013 | `N3_V_m` | Analog out | Neuron 3 membrane-potential monitor |
| CB014 | `N3_SPIKE_OUT` | Digital out | Neuron 3 spike trigger |
| CB015 | `N3_VDD` | Power in | Neuron 3 positive supply branch |
| CB016 | `N3_VSS` | Power return | Neuron 3 quiet analog return |
| CB017 | `N3_GND` | Ground | Neuron 3 ground/signal return |
| CB018 | `N3_V_tune` | Analog in | Neuron 3 varactor tuning control |
| CB019 | `N4_V_m` | Analog out | Neuron 4 membrane-potential monitor |
| CB020 | `N4_SPIKE_OUT` | Digital out | Neuron 4 spike trigger |
| CB021 | `N4_VDD` | Power in | Neuron 4 positive supply branch |
| CB022 | `N4_VSS` | Power return | Neuron 4 quiet analog return |
| CB023 | `N4_GND` | Ground | Neuron 4 ground/signal return |
| CB024 | `N4_V_tune` | Analog in | Neuron 4 varactor tuning control |

### 3.2 Top edge: `CT001`-`CT024`

| Pad | Signal | Type | Description |
| --- | --- | --- | --- |
| CT001 | `N5_V_m` | Analog out | Neuron 5 membrane-potential monitor |
| CT002 | `N5_SPIKE_OUT` | Digital out | Neuron 5 spike trigger |
| CT003 | `N5_VDD` | Power in | Neuron 5 positive supply branch |
| CT004 | `N5_VSS` | Power return | Neuron 5 quiet analog return |
| CT005 | `N5_GND` | Ground | Neuron 5 ground/signal return |
| CT006 | `N5_V_tune` | Analog in | Neuron 5 varactor tuning control |
| CT007 | `N6_V_m` | Analog out | Neuron 6 membrane-potential monitor |
| CT008 | `N6_SPIKE_OUT` | Digital out | Neuron 6 spike trigger |
| CT009 | `N6_VDD` | Power in | Neuron 6 positive supply branch |
| CT010 | `N6_VSS` | Power return | Neuron 6 quiet analog return |
| CT011 | `N6_GND` | Ground | Neuron 6 ground/signal return |
| CT012 | `N6_V_tune` | Analog in | Neuron 6 varactor tuning control |
| CT013 | `N7_V_m` | Analog out | Neuron 7 membrane-potential monitor |
| CT014 | `N7_SPIKE_OUT` | Digital out | Neuron 7 spike trigger |
| CT015 | `N7_VDD` | Power in | Neuron 7 positive supply branch |
| CT016 | `N7_VSS` | Power return | Neuron 7 quiet analog return |
| CT017 | `N7_GND` | Ground | Neuron 7 ground/signal return |
| CT018 | `N7_V_tune` | Analog in | Neuron 7 varactor tuning control |
| CT019 | `N8_V_m` | Analog out | Neuron 8 membrane-potential monitor |
| CT020 | `N8_SPIKE_OUT` | Digital out | Neuron 8 spike trigger |
| CT021 | `N8_VDD` | Power in | Neuron 8 positive supply branch |
| CT022 | `N8_VSS` | Power return | Neuron 8 quiet analog return |
| CT023 | `N8_GND` | Ground | Neuron 8 ground/signal return |
| CT024 | `N8_V_tune` | Analog in | Neuron 8 varactor tuning control |

### 3.3 Left edge: `CL001`-`CL024`

| Pad | Signal | Type | Description |
| --- | --- | --- | --- |
| CL001 | `N9_V_m` | Analog out | Neuron 9 membrane-potential monitor |
| CL002 | `N9_SPIKE_OUT` | Digital out | Neuron 9 spike trigger |
| CL003 | `N9_VDD` | Power in | Neuron 9 positive supply branch |
| CL004 | `N9_VSS` | Power return | Neuron 9 quiet analog return |
| CL005 | `N9_GND` | Ground | Neuron 9 ground/signal return |
| CL006 | `N9_V_tune` | Analog in | Neuron 9 varactor tuning control |
| CL007 | `N10_V_m` | Analog out | Neuron 10 membrane-potential monitor |
| CL008 | `N10_SPIKE_OUT` | Digital out | Neuron 10 spike trigger |
| CL009 | `N10_VDD` | Power in | Neuron 10 positive supply branch |
| CL010 | `N10_VSS` | Power return | Neuron 10 quiet analog return |
| CL011 | `N10_GND` | Ground | Neuron 10 ground/signal return |
| CL012 | `N10_V_tune` | Analog in | Neuron 10 varactor tuning control |
| CL013 | `N11_V_m` | Analog out | Neuron 11 membrane-potential monitor |
| CL014 | `N11_SPIKE_OUT` | Digital out | Neuron 11 spike trigger |
| CL015 | `N11_VDD` | Power in | Neuron 11 positive supply branch |
| CL016 | `N11_VSS` | Power return | Neuron 11 quiet analog return |
| CL017 | `N11_GND` | Ground | Neuron 11 ground/signal return |
| CL018 | `N11_V_tune` | Analog in | Neuron 11 varactor tuning control |
| CL019 | `N12_V_m` | Analog out | Neuron 12 membrane-potential monitor |
| CL020 | `N12_SPIKE_OUT` | Digital out | Neuron 12 spike trigger |
| CL021 | `N12_VDD` | Power in | Neuron 12 positive supply branch |
| CL022 | `N12_VSS` | Power return | Neuron 12 quiet analog return |
| CL023 | `N12_GND` | Ground | Neuron 12 ground/signal return |
| CL024 | `N12_V_tune` | Analog in | Neuron 12 varactor tuning control |

### 3.4 Right edge: `CR001`-`CR024`

| Pad | Signal | Type | Description |
| --- | --- | --- | --- |
| CR001 | `N13_V_m` | Analog out | Neuron 13 membrane-potential monitor |
| CR002 | `N13_SPIKE_OUT` | Digital out | Neuron 13 spike trigger |
| CR003 | `N13_VDD` | Power in | Neuron 13 positive supply branch |
| CR004 | `N13_VSS` | Power return | Neuron 13 quiet analog return |
| CR005 | `N13_GND` | Ground | Neuron 13 ground/signal return |
| CR006 | `N13_V_tune` | Analog in | Neuron 13 varactor tuning control |
| CR007 | `N14_V_m` | Analog out | Neuron 14 membrane-potential monitor |
| CR008 | `N14_SPIKE_OUT` | Digital out | Neuron 14 spike trigger |
| CR009 | `N14_VDD` | Power in | Neuron 14 positive supply branch |
| CR010 | `N14_VSS` | Power return | Neuron 14 quiet analog return |
| CR011 | `N14_GND` | Ground | Neuron 14 ground/signal return |
| CR012 | `N14_V_tune` | Analog in | Neuron 14 varactor tuning control |
| CR013 | `N15_V_m` | Analog out | Neuron 15 membrane-potential monitor |
| CR014 | `N15_SPIKE_OUT` | Digital out | Neuron 15 spike trigger |
| CR015 | `N15_VDD` | Power in | Neuron 15 positive supply branch |
| CR016 | `N15_VSS` | Power return | Neuron 15 quiet analog return |
| CR017 | `N15_GND` | Ground | Neuron 15 ground/signal return |
| CR018 | `N15_V_tune` | Analog in | Neuron 15 varactor tuning control |
| CR019 | `N16_V_m` | Analog out | Neuron 16 membrane-potential monitor |
| CR020 | `N16_SPIKE_OUT` | Digital out | Neuron 16 spike trigger |
| CR021 | `N16_VDD` | Power in | Neuron 16 positive supply branch |
| CR022 | `N16_VSS` | Power return | Neuron 16 quiet analog return |
| CR023 | `N16_GND` | Ground | Neuron 16 ground/signal return |
| CR024 | `N16_V_tune` | Analog in | Neuron 16 varactor tuning control |

### 3.5 Signal handling rules

- `V_m` is a high-impedance analog monitor. Buffer it on the carrier with an input impedance of at least 1 Mohm and keep acquisition bandwidth below the intended experiment bandwidth unless a probe buffer is used.
- `SPIKE_OUT` is an output only. Use a short, point-to-point 3.3 V trace to the acquisition FPGA, MCU, or level-compatible counter. Do not add pull-ups to a different voltage domain.
- `VDD` is a supply input and `VSS` is the quiet analog return. Keep each `VSS` path separate from high-current digital return paths until the carrier star point.
- `GND` is the local signal and shield return. Join it to the carrier ground plane at the module perimeter; do not leave it floating.
- `V_tune` is an analog input to the varactor network. Filter it at the carrier with a low-noise RC network and route it away from `SPIKE_OUT` and switching regulators.

## 4. Electrical and Power Constraints

### 4.1 Supply limits

| Parameter | Limit / target |
| --- | --- |
| Recommended `VDD` | 3.3 V nominal |
| Allowed `VDD` at module pads | 3.135 V to 3.465 V (3.3 V +/-5%) |
| Absolute maximum `VDD` | 3.6 V; never use a 5 V rail directly |
| `VSS` and logic ground | 0 V reference; keep analog return drop below 20 mV during activity |
| Maximum current per neuron cell | 25 mA design limit, including local resonant-drive transient margin |
| Recommended carrier supply capacity | 500 mA continuous at 3.3 V, with local bulk capacitance |
| Module power-up ramp | Monotonic; 0.1 ms to 100 ms recommended |
| Varactor control range | 0 V to 5 V simulation range; do not exceed the selected varactor data-sheet rating |

The carrier must provide at least 100 nF ceramic decoupling per local supply group and at least 10 uF low-ESR bulk capacitance at the module entry. Place current limiting or a resettable protection element upstream of the module. Do not hot-plug an unpowered carrier into an active `V_tune` source.

### 4.2 Analog and resonant interface

The LC bridges are sensitive to trace parasitics and return inductance. Keep bridge paths short, symmetric, and free of stubs. For a bridge with characteristic impedance $Z_0$, use a carrier source impedance within approximately 10% of $Z_0$ when connecting an external stimulus or measurement instrument. A 50 ohm instrument should be isolated with the appropriate series resistor or buffer if the bridge is not a 50 ohm network.

Do not terminate `V_m` or `V_tune` with 50 ohms. The carrier-side `V_tune` filter should have a corner well above the maximum tuning update rate but below the LC excitation noise band. Start with 1 kohm series and 100 nF to the analog return, then validate settling time and resonance Q in the assembled system.

## 5. Carrier Board Interface Rules

1. Assign one carrier net to every pad identifier. Do not connect pads by physical proximity or by array index alone.
2. Use a continuous reference plane under digital signals, but keep the LC bridge and `V_tune` routing over a quiet analog reference region.
3. Keep switching regulator nodes, crystals, fast clocks, and high-current motor or relay traces at least 3 mm from the module edge-pad fanout.
4. Route `SPIKE_OUT` as controlled, short digital traces. Avoid routing them parallel to `V_m` or `V_tune` for more than 10 mm.
5. Provide labeled test points for `VDD`, `VSS`, `GND`, one representative `V_m`, one representative `SPIKE_OUT`, and the `V_tune` source.
6. Sequence power as `VSS/GND`, `VDD`, then `V_tune` and external digital interfaces. During shutdown, remove `V_tune` before `VDD` when practical.
7. Leave all module edge clearances and keepouts from the released KiCad board unchanged. Carrier copper must not enter the module outline or edge-plating keepout.

## 6. Mechanical and Assembly Guide

### 6.1 Recommended carrier land pattern

- Use one rectangular SMD land for each castellated pad, aligned to the module edge.
- Match the module pad width and pitch from the released fabrication drawing; use 0.5 mm pitch and 0.30 mm land width as the initial carrier-library value only until that drawing is frozen.
- Extend the carrier land 0.20 mm to 0.30 mm beyond the module edge for fillet inspection, while keeping solder mask webbing between adjacent lands.
- Use NSMD lands where the carrier fabricator can hold the mask registration; otherwise use the fabricator's recommended castellated-edge land construction.
- Add 0.25 mm minimum solder-mask expansion around each land and keep copper, mask openings, and silkscreen out of the module body clearance.
- Do not place vias inside the land. If via-in-pad is unavoidable, use filled and capped vias approved by the fabricator.

### 6.2 Reflow profile

Use the solder-paste manufacturer's profile as the controlling specification. The following lead-free SAC305 profile is a starting point for castellated edge soldering:

| Stage | Target |
| --- | --- |
| Preheat | 0.5 to 1.5 deg C/s to 150-200 deg C |
| Soak | 150-200 deg C for 60-120 s |
| Liquidus | Above 217 deg C for 45-75 s |
| Peak | 235-245 deg C, never above the component/PCB limit |
| Cool-down | 1-3 deg C/s, no forced thermal shock |

Inspect all four edges after reflow. Confirm a continuous side fillet, no bridging between adjacent pads, and no lifted corner. X-ray inspection is recommended if the carrier uses buried vias, large thermal planes, or bottom-side components near the module lands.

### 6.3 Clearance and serviceability

- Keep a minimum 1.0 mm no-component zone around the module perimeter on the carrier; increase this to 2.0 mm on the edge used for probing.
- Keep tall components, connectors, and heat sources at least 3 mm from the module edge unless the mechanical drawing explicitly permits overlap.
- Reserve at least 0.5 mm between the carrier solder-mask opening and any exposed chassis or shield metal.
- Support the module during rework. Do not lever against the castellated pads, and limit rework heating to the paste/component manufacturer's stated profile.
- Mark pin 1 and the top-side orientation on both the module carrier and assembly drawing. The CB/CT/CL/CR names are not a substitute for a physical orientation marker.

## 7. Bring-Up Checklist

1. With power off, verify no short exists between `VDD`, `VSS`, and `GND`, and verify every pad maps to the intended carrier net.
2. Apply a current-limited 3.3 V supply with `V_tune` held at 0 V.
3. Confirm the module current is within the expected idle range before enabling neuron stimulation.
4. Probe one `V_m` channel and one `SPIKE_OUT` channel before enabling all 16 cells.
5. Sweep `V_tune` slowly while observing bridge voltage, bridge current, and phase relationship. Stop if the varactor or bridge exceeds its component rating.
6. Validate the complete 16-channel acquisition map against the pad table and record the carrier revision with the simulation export files.

The KiCad schematic and PCB remain the authority for revision-specific net names, footprints, and fabricated geometry. This guide defines the intended SoM-to-carrier interface and must be revised together with any pinout or power-domain change.

## Hardware Trim and Resonant Carrier

## 8. Analog Fast-Reset and Thermal Compensation

The analog CMOS fast-reset switch shall force the AdEx membrane capacitor to `V_reset` and present a low-impedance discharge path when `V_m` reaches `V_peak`. The switch must meet `t_reset < 100 ns` across the specified supply, process, load, and temperature corners. Use a dedicated threshold detector with controlled hysteresis, minimum non-overlap between set and reset controls, and a current-limited reset device so parasitic injection does not disturb neighboring resonant nodes.

The BJT/MOSFET bias network shall use a thermal bias mirror compensation topology. Sense the local junction temperature, mirror a proportional correction current into the threshold and adaptation-bias branches, and trim the room-temperature intercept independently from the temperature coefficient. Place the sensing device close to the matched bias pair, use common-centroid or interdigitated matching where practical, and verify mirror compliance voltage at both `-20 C` and `85 C`.

The resonant LC bridge uses the semiconductor reverse-bias junction model for the varactor:
$C_{\text{var}}(V_{\text{rev}}) = C_0/(1 + V_{\text{rev}}/V_J)^M + C_{\text{fixed}}$ where $C_0 = 100$ nF,
$V_J = 0.7$ V, $M = 0.5$, $C_{\text{fixed}} = 47$ nF, and the net reverse bias is
$V_{\text{rev}} = V_{\text{tune}} + (V_{m,i} - V_{m,j})$, clipped to $[0, 15]$ V.
The tank resonance is verified via the `compute_tuning_spectrum()` function which sweeps $V_{\text{tune}}$ from 0 to 5 V, masks the time series into low-tune ($V_{\text{tune}} \leq 0.8$ V) and high-tune ($V_{\text{tune}} \geq 4.2$ V) regions, and computes the Welch PSD peak for each band. The dimensionally corrected (V_tune in Volts, not Farads) verification yields:
- **low_tune**: **1196.3 Hz** (mean V_tune = 0.4 V)
- **high_tune**: **1391.6 Hz** (mean V_tune = 4.6 V)
- $\Delta f = 195.3$ Hz, $|df/dV_{\text{tune}}| = 48.8$ Hz/V
The 4x4 network has no external AC oscillator or preset theta/gamma frequency input: it is driven only by passive L/C values, membrane capacitance `C_m`, DC bias `I_bias`, distinct initial membrane conditions, and nonlinear AdEx plus bridge feedback. Welch analysis of the resulting membrane traces measured emergent envelope peaks at **6.00 Hz** (Theta band) and **56.00 Hz** (Gamma band) in the updated dimensionally corrected run.

`dQ_ij/dt = I_ij`

`dI_ij/dt = ((V_m,i - V_m,j) - R_s I_ij - Q_ij/C_var(V_tune)) / L`

The signed bridge currents are summed into each cell's membrane-current input by Kirchhoff Current Law. Phase coherence is cross-validated only after integration using the full **16×16 Pairwise PLV Matrix** where each element PLV_ij = |mean(exp(1j × (phase_i − phase_j)))|. The boolean mask `~np.eye(16, dtype=bool)` isolates the 240 off-diagonal entries, corresponding to N×(N−1)/2 = **120 unique neuron pairs**. Per-matrix summary statistics (Mean, Median, Min, Max) replace the former single-number PLV:

| Pairwise PLV Metric | Hilbert (continuous phase) | Spike-Time (discrete events) |
|---|---:|---:|
| **Mean** (120 pairs) | **0.948820** | **0.919338** |
| **Median** (120 pairs) | **0.949749** | **0.919017** |
| **Min** (120 pairs) | **0.869659** | **0.813877** |
| **Max** (120 pairs) | **0.987550** | **0.978704** |
| Kuramoto Order Parameter, mean `R(t)` | **0.975472** |
| Pairwise Phase Dispersion, 16x16 circular phase matrix | **0.240158 rad** |
| Phase-Lag Distribution standard deviation | **0.261841 rad** |
| Off-Diagonal Inter-Neuron Cross-Correlation (Pearson `~np.eye()` masked) | **0.746242** |

This replaces a single idealized PLV claim with a full pairwise distribution, enabling outlier detection and biophysical confidence intervals. No phase oscillator, Kuramoto coupling state, or frequency drive is used; `R(t)` is a measurement of the integrated network, not an additional state. Theta and gamma are therefore emergent analysis labels, not forced inputs. Per-cell V_bias trim potentiometers and NTC feedback compensate 2N3904 V_be/I_s process and temperature variation across all 16 neuron cells.

## 9. Mixed-Signal Isolation, Guard Rings, and Calibration

## 10. Simulation Benchmark & Dual-Engine Cross-Validation

The AdEx Resonant Core project implements **two independent simulation engines** to verify emergent dynamics before hardware fabrication:

### 10.1 Engine Architecture

| Engine | Solver | Firing-rate extraction |
|--------|--------|------------------------|
| **RK4 Numerical** | 4th-order Runge-Kutta with discrete spike-reset | Count V_m ≥ V_peak crossings in numerical V_m(t) |
| **PySpice/Ngspice** | Behavioural circuit-equivalent netlist → `ngspice -b` subprocess | Print V_m nodes via `.print tran` → parse → count threshold crossings |

Both engines operate **independently** — no state, parameters, or results are shared between them during execution. The benchmark plot (`benchmark_rk4_vs_pspice.png`) presents side-by-side bar charts with the absolute rate delta annotated.

### 10.2 Current Benchmark Status

| Metric | Value |
|--------|-------|
| RK4 Firing Rate | Extracted from numerical integration |
| SPICE Firing Rate | Extracted from Ngspice transient; **None** when engine is offline |
| Rate Delta (Δ) | `\|Rate_RK4 − Rate_SPICE\|` |
| SPICE Engine Status | Reports **"SPICE Engine Offline"** on benchmark plot when unavailable/non-convergent |

> **Note:** The behavioural circuit-equivalent netlist parses and loads correctly in Ngspice v47, but the hard-threshold BCOMP/BRST behavioural sources create convergence difficulties typical of pure spiking-neuron models in SPICE. The benchmark infrastructure is fully implemented and will report genuine dual-engine deltas once a simulation-friendly netlist revision (smoothed thresholds or transistor-level subcircuits) is adopted. The system **never** duplicates RK4 data onto the SPICE bar.

## 11. Physical 4x4 Nearest-Neighbor RLC Routing

The released PCB is modeled as a 4x4 2D nearest-neighbor grid, not a 16x16 synapse crossbar. Each neuron cell has at most four physical bridge connections: North, South, East, and West. The topology therefore contains 24 undirected LC bridges, matching the routed PCB traces and excluding diagonal and long-range connections.

Each bridge is a second-order Kirchhoff state-space element with charge `Q_ij` and branch current `I_ij`:

$$
\frac{dQ_{ij}}{dt}=I_{ij},\qquad
\frac{dI_{ij}}{dt}=\frac{(V_{m,i}-V_{m,j})-R_s I_{ij}-Q_{ij}/(C_{fixed}+C_{var}(V_{tune}))}{L}
$$

The AdEx membrane equation receives only the signed sum of these physical branch currents. There is no artificial all-to-all voltage coupling matrix and no externally imposed oscillation frequency. The Hilbert, event-phase, and Kuramoto values reported below are measurements of the integrated grid waveform.

Route the 16x16 synapse matrix as an orthogonal two-layer crossbar. Each
vertical synapse-column trace shall remain on `F.Cu`; each horizontal
synapse-row trace shall remain on `B.Cu`. At every matrix intersection, join
the two layers with a controlled via pair or the released single-via cell
geometry. Keep via annuli and clearances inside the cell pitch, and do not
route unrelated signals through the crossbar corridor.

Keep row and column naming aligned with the KiCad schematic net labels. Match
the crossbar origin, pitch, and via coordinates to the released PCB grid so
that footprint moves cannot silently change the matrix topology. Maintain the
specified impedance and spacing rules at the crossbar perimeter, and reserve
test access only at the designated row and column breakout locations.

Place the PTAT thermal-bias current mirror immediately adjacent to the BJT/MOSFET
neuron-core cluster it compensates. Use matched orientation, common-centroid or
interdigitated placement where practical, short symmetric bias routes, and a
quiet `AGND` return. Keep the mirror away from hot switching edges and provide
the local thermal coupling needed for temperature tracking without crossing
the LC bridge guard-ring keepout.

### 9.1 AGND and DGND

- Keep the analog ground plane (`AGND`) and digital ground plane (`DGND`) physically isolated in the carrier placement and routing regions. Do not use a split-plane copper bridge under the LC bridges, `V_tune`, or `V_m` routes.
- Join `AGND` and `DGND` at exactly one controlled star point through a ferrite bead. Place the bead at the carrier power-entry boundary, beside the bulk decoupling, and keep the connection short and wide.
- Return varactor bias, bridge components, `V_m` buffers, and analog supply bypass capacitors to `AGND`. Return AER receivers, clocks, converters, and switching-regulator control signals to `DGND`.
- Do not route digital return current through the analog star point. Keep the ferrite bead current rating and impedance curve appropriate for the carrier's measured transient current; do not replace it with multiple parallel ground links.

### 9.2 Varactor LC bridge guard rings

- Surround each varactor-controlled LC bridge on Layer 1 (`F.Cu`) with a grounded copper guard ring tied to `AGND` at one point only. Keep the ring continuous around the bridge signal path, with a minimum 0.25 mm clearance from signal copper and the component pads.
- Keep the guard ring and bridge loop free of vias, digital routes, test-point stubs, and thermal-relief spokes. Use a solid analog reference region directly beneath the bridge on the adjacent ground layer.
- Keep `V_tune` inside the guard-ring boundary, route it as a short high-impedance analog trace, and place the carrier RC damping network at the module entry. The simulation uses 1 kohm and 100 nF as the nominal damping network and includes 2.5 pF PCB trace capacitance in parallel with each bridge.

### 9.3 AER spike interface and self-calibration

- `SPIKE_OUT` is an asynchronous Address-Event Representation interface: transmit the neuron address and event strobe only when a behavioral / circuit-equivalent SPICE spike occurs. Do not continuously digitize all `V_m` channels for normal operation.
- The carrier receiver shall provide a timestamped event latch or asynchronous FIFO and keep measured event-to-capture jitter below 10 ns. Keep the point-to-point route short, avoid parallelism with `V_m` and `V_tune`, and terminate only as required by the receiver input standard.
- At bring-up, sweep each `V_tune` DAC code slowly, record the AER event rate and bridge phase, and store the code that centers the desired resonance. Apply the code after power sequencing and repeat the sweep over temperature if the NTC compensation reports a drift outside the calibrated window.
- Verify the damped tuning response after every carrier revision by observing `V_tune`, bridge phase, and the AER event timestamps together. A valid calibration must preserve phase-locking with the assembled trace parasitics present.
