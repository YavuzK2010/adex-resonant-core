# AdEx Resonant Core SoM Integration Guide

**Document status:** Carrier-board integration contract  
**Module:** AdEx Resonant Core 16-neuron SoM  
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
| Varactor control range | 0 V to 3.3 V nominal; do not exceed the selected varactor data-sheet rating |

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