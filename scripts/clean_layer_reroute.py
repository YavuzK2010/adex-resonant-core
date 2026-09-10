#!/usr/bin/env python3
# pyright: basic
"""AdEx Resonant Core - Clean Layer-Isolated Reroute & DRC Sweep."""
import os, re, sys
PCB_EXTRA_PATH = "/usr/lib64/python3.14/site-packages"
if os.path.isdir(PCB_EXTRA_PATH): sys.path.insert(0, PCB_EXTRA_PATH)
import pcbnew
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HW = os.path.join(ROOT, "hardware")
BOARD_FILE = os.path.join(HW, "adex_resonant_core.kicad_pcb")
PRO_FILE = os.path.join(HW, "adex_resonant_core.kicad_pro")
def mm_to_nm(v): return int(round(v * 1_000_000))
def nm_to_mm(v): return v / 1_000_000.0
