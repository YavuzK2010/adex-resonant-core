#!/usr/bin/env python3
# pyright: basic
"""Inspect actual courtyard sizes of footprints on the PCB."""
import os, sys
PCB_EXTRA_PATH = "/usr/lib64/python3.14/site-packages"
if os.path.isdir(PCB_EXTRA_PATH):
    sys.path.insert(0, PCB_EXTRA_PATH)
import pcbnew

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HW = os.path.join(ROOT, "hardware")
board = pcbnew.LoadBoard(os.path.join(HW, "adex_resonant_core.kicad_pcb"))

def mm(v): return v / 1_000_000.0

targets = ["N1_C1", "N1_R1", "N1_R2", "N1_Q1", "N1_Q2", "N1_U1"]
for ref in targets:
    for fp in board.GetFootprints():
        if fp.GetReference() == ref:
            pos = fp.GetPosition()
            print(f"\n{ref} at ({mm(pos.x):.3f}, {mm(pos.y):.3f})")
            for item in fp.GraphicalItems():
                try:
                    if item.GetLayer() in (pcbnew.F_CrtYd, pcbnew.B_CrtYd):
                        bb = item.GetBoundingBox()
                        x0 = mm(bb.GetLeft())
                        y0 = mm(bb.GetTop())
                        x1 = mm(bb.GetRight())
                        y1 = mm(bb.GetBottom())
                        layer = "F_CrtYd" if item.GetLayer() == pcbnew.F_CrtYd else "B_CrtYd"
                        print(f"  Courtyard ({layer}): X=[{x0:.3f}, {x1:.3f}] Y=[{y0:.3f}, {y1:.3f}] w={x1-x0:.3f} h={y1-y0:.3f}")
                except:
                    pass
            break