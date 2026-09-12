#!/usr/bin/env python3
# pyright: basic
"""Inspect footprint library info and design rules."""
import os, sys
PCB_EXTRA_PATH = "/usr/lib64/python3.14/site-packages"
if os.path.isdir(PCB_EXTRA_PATH):
    sys.path.insert(0, PCB_EXTRA_PATH)
import pcbnew

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HW = os.path.join(ROOT, "hardware")
BOARD_FILE = os.path.join(HW, "adex_resonant_core.kicad_pcb")
board = pcbnew.LoadBoard(BOARD_FILE)

def mm(v): return v / 1_000_000.0

# Check design rules
ds = board.GetDesignSettings()
print("=== Design Rules ===")
for attr in dir(ds):
    if 'courtyard' in attr.lower() or 'clearance' in attr.lower():
        try:
            val = getattr(ds, attr)
            print(f"  {attr}: {val}")
        except:
            pass

# Check footprint library assignments
print("\n=== Footprint Libs for First Neuron ===")
targets = ["N1_C1", "N1_R1", "N1_R2", "N1_Q1", "N1_Q2", "N1_U1"]
for ref in targets:
    for fp in board.GetFootprints():
        if fp.GetReference() == ref:
            fp_id_lib = str(fp.GetFPID().GetLibNickname().c_str()) if hasattr(fp.GetFPID().GetLibNickname(), 'c_str') else str(fp.GetFPID())
            lib = fp.GetFPID().GetLibNickname() if hasattr(fp.GetFPID(), 'GetLibNickname') else str(fp.GetFPID())
            print(f"  {ref}: {fp_id}")

# Print positions of all components in N1 cell for verification
print("\n=== N1 Cell Component Positions ===")
n1_cx, n1_cy = 11.0, 10.0  # Row 0, Col 0
for fp in board.GetFootprints():
    if fp.GetReference().startswith("N1_"):
        p = fp.GetPosition()
        print(f"  {fp.GetReference()}: ({mm(p.x):.3f}, {mm(p.y):.3f})  expected dx={mm(p.x)-n1_cx:.2f}, dy={mm(p.y)-n1_cy:.2f}")

# Print positions for N5 cell as well
print("\n=== N5 Cell Component Positions ===")
n5_cx, n5_cy = 11.0, 22.5  # Row 1, Col 0
for fp in board.GetFootprints():
    if fp.GetReference().startswith("N5_"):
        p = fp.GetPosition()
        print(f"  {fp.GetReference()}: ({mm(p.x):.3f}, {mm(p.y):.3f})  expected dx={mm(p.x)-n5_cx:.2f}, dy={mm(p.y)-n5_cy:.2f}")

# Check courtyard clearance rule
print("\n=== Checking courtyard_clearance in PCB file ===")
import re
with open(BOARD_FILE) as f:
    content = f.read()
    for line in content.split('\n'):
        if 'courtyard' in line.lower():
            print(f"  {line.strip()}")

# Compute actual overlap for N1_R3 and N5_C1
print("\n=== Overlap Analysis: N1_R3 vs N5_C1 ===")
for fp in board.GetFootprints():
    if fp.GetReference() == "N1_R3":
        p = fp.GetPosition()
        print(f"  N1_R3 center: ({mm(p.x):.3f}, {mm(p.y):.3f})")
        for item in fp.GraphicalItems():
            try:
                if item.GetLayer() == pcbnew.F_CrtYd:
                    bb = item.GetBoundingBox()
                    print(f"    F_CrtYd item: X=[{mm(bb.GetLeft()):.3f}, {mm(bb.GetRight()):.3f}] Y=[{mm(bb.GetTop()):.3f}, {mm(bb.GetBottom()):.3f}]")
            except: pass
    if fp.GetReference() == "N5_C1":
        p = fp.GetPosition()
        print(f"  N5_C1 center: ({mm(p.x):.3f}, {mm(p.y):.3f})")
        for item in fp.GraphicalItems():
            try:
                if item.GetLayer() == pcbnew.F_CrtYd:
                    bb = item.GetBoundingBox()
                    print(f"    F_CrtYd item: X=[{mm(bb.GetLeft()):.3f}, {mm(bb.GetRight()):.3f}] Y=[{mm(bb.GetTop()):.3f}, {mm(bb.GetBottom()):.3f}]")
            except: pass