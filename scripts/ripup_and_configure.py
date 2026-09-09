#!/usr/bin/env python3
# pyright: basic
"""
AdEx Resonant Core — Complete Trace Ripup & Netclass Configuration.
Removes ALL tracks/vias, configures rules, assigns power nets to plane classes.
"""

import os, sys
PCB_EXTRA_PATH = "/usr/lib64/python3.14/site-packages"
if os.path.isdir(PCB_EXTRA_PATH):
    sys.path.insert(0, PCB_EXTRA_PATH)
import pcbnew  # type: ignore[import-untyped]

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOARD_FILE = os.path.join(ROOT, "hardware", "adex_resonant_core.kicad_pcb")

removed_t, removed_v = 0, 0


def ripup(board):
    global removed_t, removed_v
    for item in list(board.GetTracks()):
        try:
            board.Remove(item)
            if type(item).__name__ == "PCB_VIA":
                removed_v += 1
            else:
                removed_t += 1
        except Exception:
            pass
    print(f"  [RIPUP] Removed {removed_t} tracks, {removed_v} vias.")


def rules(board):
    ds = board.GetDesignSettings()
    for attr, val in [("m_TrackMinWidth", 0.20), ("m_TrackWidth", 0.20),
                       ("m_TrackClearance", 0.18), ("m_TrackMinClearance", 0.18),
                       ("m_ViaMinSize", 0.4), ("m_ViaMinDrill", 0.2),
                       ("m_ViaSize", 0.5), ("m_ViaDrill", 0.25)]:
        try:
            setattr(ds, attr, pcbnew.FromMM(val))
        except Exception:
            pass
    print("  [RULES] Track: 0.20mm, Clearance: 0.18mm, Via: 0.5/0.25mm")


def netclasses(board):
    nm = board.GetNetClasses()
    # Default class
    if nm.find("Default") != nm.end():
        dc = nm["Default"]
        try:
            dc.SetDescription("Default signal nets")
            dc.SetClearance(pcbnew.FromMM(0.18))
            dc.SetTrackWidth(pcbnew.FromMM(0.20))
            dc.SetViaDiameter(pcbnew.FromMM(0.50))
            dc.SetViaDrill(pcbnew.FromMM(0.25))
        except Exception:
            pass
    # Create/update GND, VDD, VSS
    nc_map = {}
    for cn in ["GND", "VDD", "VSS"]:
        if nm.find(cn) != nm.end():
            nc_map[cn] = nm[cn]
        else:
            try:
                nc_map[cn] = nm.Add(cn)
            except Exception:
                pass
    descs = {"GND": "Ground plane nets (In1.Cu)",
             "VDD": "Power plane nets (In2.Cu)",
             "VSS": "Negative supply plane nets (In2.Cu)"}
    for cn, obj in nc_map.items():
        try:
            obj.SetClearance(pcbnew.FromMM(0.20))
            obj.SetTrackWidth(pcbnew.FromMM(0.30))
            obj.SetViaDiameter(pcbnew.FromMM(0.50))
            obj.SetViaDrill(pcbnew.FromMM(0.25))
            obj.SetDescription(descs.get(cn, ""))
        except Exception:
            pass
    # Assign nets to classes
    ni = board.GetNetInfo()
    gnd = vdd = vss = 0
    for nc in range(ni.GetNetCount()):
        item = ni.GetNetItem(nc)
        if item is None or item.GetNetCode() <= 0:
            continue
        name = str(item.GetNetname())
        try:
            if name.endswith("_GND") and "GND" in nc_map:
                item.SetNetClass("GND"); gnd += 1
            elif name.endswith("_VDD") and "VDD" in nc_map:
                item.SetNetClass("VDD"); vdd += 1
            elif name.endswith("_VSS") and "VSS" in nc_map:
                item.SetNetClass("VSS"); vss += 1
        except Exception:
            pass
    print(f"  [NETS] Assigned {gnd} GND, {vdd} VDD, {vss} VSS nets.")


def main():
    print("=" * 60)
    print("  AdEx Resonant Core — Trace Ripup & Netclass Config")
    print("=" * 60)
    if not os.path.exists(BOARD_FILE):
        print(f"[ERROR] Missing {BOARD_FILE}"); return 1
    board = pcbnew.LoadBoard(BOARD_FILE)
    print(f"  Footprints: {len(list(board.GetFootprints()))}")
    print("\n[1] Netclasses..."); netclasses(board)
    print("\n[2] Ripup tracks/vias..."); ripup(board)
    print("\n[3] Design rules..."); rules(board)
    print(f"\n[4] Saving to {BOARD_FILE}...")
    try:
        board.Save(BOARD_FILE)
        print("  [OK] Saved.")
    except Exception as e:
        print(f"  [ERROR] {e}"); return 1
    print("\n" + "=" * 60)
    print(f"  DONE: {removed_t} tracks, {removed_v} vias removed.")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())