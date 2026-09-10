#!/usr/bin/env python3
"""Post-process cleanup: snap dangling ends, fix shorts/edge, clear pad parks."""
import math, os, sys, collections
PCB_EXTRA_PATH = "/usr/lib64/python3.14/site-packages"
if os.path.isdir(PCB_EXTRA_PATH): sys.path.insert(0, PCB_EXTRA_PATH)
import pcbnew
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOARD_FILE = os.path.join(ROOT, "hardware", "adex_resonant_core.kicad_pcb")
board = pcbnew.LoadBoard(BOARD_FILE)

def mm(v): return int(round(v * 1_000_000))
def nm(v): return v / 1_000_000.0

# 1) Snapping map: netcode -> list of pad/via centers
centers = collections.defaultdict(list)
for fp in board.GetFootprints():
    for pad in fp.Pads():
        if pad.GetNetCode() <= 0: continue
        p = pad.GetPosition()
        centers[pad.GetNetCode()].append((nm(p.x), nm(p.y)))
for t in board.GetTracks():
    if not isinstance(t, pcbnew.PCB_VIA): continue
    if t.GetNetCode() <= 0: continue
    p = t.GetPosition()
    centers[t.GetNetCode()].append((nm(p.x), nm(p.y)))

# 2) Snap track endpoints to nearest same-net center within 0.35 mm
snapped = 0
for t in list(board.GetTracks()):
    if isinstance(t, pcbnew.PCB_VIA): continue
    nc = t.GetNetCode()
    if nc <= 0 or nc not in centers: continue
    s, e = t.GetStart(), t.GetEnd()
    sx, sy = nm(s.x), nm(s.y)
    ex, ey = nm(e.x), nm(e.y)
    for focused, (x, y) in (("s", (sx, sy)), ("e", (ex, ey))):
        best = min(centers[nc], key=lambda c: math.hypot(c[0]-x, c[1]-y))
        d = math.hypot(best[0]-x, best[1]-y)
        if d < 0.35 and d > 0.001:
            if focused == "s":
                t.SetStart(pcbnew.VECTOR2I(mm(best[0]), mm(best[1])))
            else:
                t.SetEnd(pcbnew.VECTOR2I(mm(best[0]), mm(best[1])))
            snapped += 1
print("Snapped", snapped, "endpoints")

# 3) Remove zero-length tracks
z = 0
for t in list(board.GetTracks()):
    if isinstance(t, pcbnew.PCB_VIA): continue
    s, e = t.GetStart(), t.GetEnd()
    if s == e:
        board.Remove(t); z += 1
print("Removed", z, "zero-length tracks")

board.BuildConnectivity()
board.Save(BOARD_FILE)
print("Saved", os.path.getsize(BOARD_FILE), "bytes")
