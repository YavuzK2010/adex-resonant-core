#!/usr/bin/env python3
"""Clear all routing tracks/vias from the board (keep placement)."""
import sys, os
sys.path.insert(0, "/usr/lib64/python3.14/site-packages")
import pcbnew
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOARD = os.path.join(ROOT, "hardware", "adex_resonant_core.kicad_pcb")
board = pcbnew.LoadBoard(BOARD)
n = 0
for t in list(board.GetTracks()):
    try:
        board.Remove(t)
        n += 1
    except:
        pass
board.Save(BOARD)
print(f"Cleared {n} tracks from board.")
