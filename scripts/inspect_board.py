#!/usr/bin/env python3
"""Inspect the PCB board - list all footprints with their references, positions, and footprint names."""

import os
import sys

PCB_EXTRA_PATH = "/usr/lib64/python3.14/site-packages"
if os.path.isdir(PCB_EXTRA_PATH):
    sys.path.insert(0, PCB_EXTRA_PATH)

import pcbnew

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HW = os.path.join(ROOT, "hardware")
BOARD_FILE = os.path.join(HW, "adex_resonant_core.kicad_pcb")

board = pcbnew.LoadBoard(BOARD_FILE)
fps = list(board.GetFootprints())
fps.sort(key=lambda f: f.GetReference())

print(f"Total footprints: {len(fps)}")
print()
print(f"{'Reference':<12} {'Footprint Name':<40} {'X (mm)':<12} {'Y (mm)':<12} {'Rotation':<10}")
print("-" * 90)
for fp in fps:
    ref = fp.GetReference()
    fname = fp.GetFPIDAsString() if hasattr(fp, 'GetFPIDAsString') else fp.GetPadCount()
    pos = fp.GetPosition()
    x = pcbnew.ToMM(pos.x)
    y = pcbnew.ToMM(pos.y)
    rot = fp.GetOrientationDegrees() if hasattr(fp, 'GetOrientationDegrees') else 0.0
    print(f"{ref:<12} {str(fname):<40} {x:<12.4f} {y:<12.4f} {rot:<10.2f}")