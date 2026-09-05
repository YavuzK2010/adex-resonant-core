# AdEx Resonant Brain Network (16-Neuron Hybrid Neuromorphic Core)

An open-source hardware implementation of a 16-neuron Adaptive Exponential Integrate-and-Fire (AdEx) matrix coupled via a voltage-tunable LC resonant interconnection network.

## Architecture
- **Neuron Core:** 16 Analog AdEx Neurons ($V_m$ and $COMP\_OUT$ outputs)
- **Resonant Bridge:** Passive SMD Inductors ($L$) + Variable Capacitance ($C_{var}$) Varactor Diodes
- **Coupling Mechanism:** Phase-Locking (In-Phase sync) & Impedance Inhibition (Out-of-Phase suppression)
- **Bandwidth Control:** External analog tuning voltage ($V_{tune}$) covering Theta (4-8 Hz) to Gamma (30-80 Hz) bands.

## Toolchain
- **OS:** Linux Fedora Workstation
- **Simulation:** PySpice / Ngspice / LTspice
- **EDA:** KiCad 10
- **Automation:** Python PCB API & Freerouting
