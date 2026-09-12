#!/usr/bin/env python3
# pyright: basic
"""
AdEx Resonant Core — Fix Board Edge Clearance Violations for Castellated Pads.

For each pad on castellated-edge footprints (CL*, CR*, CT*, CB*):
  1. Converts the pad attribute from NPTH → PTH (castellated half-holes
     are plated copper around the board edge).
  2. Sets PAD_PROP_CASTELLATED to flag the KiCad DRC that this pad is
     intentionally at the board edge.

Together these resolve both "Board edge clearance violation" and
"Padstack is questionable" DRC errors for castellated half-holes.

Usage:
    python3 scripts/fix_edge_clearance.py
"""

import os
import re
import sys
from typing import Final

PCB_EXTRA_PATH: Final[str] = "/usr/lib64/python3.14/site-packages"
if os.path.isdir(PCB_EXTRA_PATH) and PCB_EXTRA_PATH not in sys.path:
    sys.path.insert(0, PCB_EXTRA_PATH)

import pcbnew  # type: ignore[import-untyped]

ROOT: Final[str] = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HW: Final[str] = os.path.join(ROOT, "hardware")
BOARD_FILE: Final[str] = os.path.join(HW, "adex_resonant_core.kicad_pcb")

# Regex matching castellated-edge footprint references
#   CL001..CL030  — Left edge
#   CR001..CR030  — Right edge
#   CT001..CT030  — Top edge
#   CB001..CB030  — Bottom edge
CASTELLATED_RE: Final[re.Pattern[str]] = re.compile(r"^C[LRTB]\d{2,3}$")


def fix_edge_clearance(board_file: str) -> int:
    if not os.path.exists(board_file):
        print(f"[ERROR] Board file not found: {board_file}")
        return 1

    print(f"  Board:  {board_file}")
    board = pcbnew.LoadBoard(board_file)

    cast_footprints: list[pcbnew.FOOTPRINT] = []
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        if CASTELLATED_RE.match(ref):
            cast_footprints.append(fp)

    if not cast_footprints:
        print("[WARN] No castellated-edge footprints found — nothing to fix.")
        return 0

    print(f"\n  Found {len(cast_footprints)} castellated footprint(s).")

    modified_pad_count = 0
    for fp in cast_footprints:
        ref = fp.GetReference()
        for pad in fp.Pads():
            need_save = False
            actions = []

            # ── 1. Convert NPTH → PTH ──────────────────────────────────────────
            # Castellated half-holes are plated copper at the board edge.
            if pad.GetAttribute() != pcbnew.PAD_ATTRIB_PTH and pad.HasHole():
                pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
                actions.append("NPTH→PTH")
                need_save = True

            # ── 2. Set castellated property ────────────────────────────────────
            if pad.GetProperty() != pcbnew.PAD_PROP_CASTELLATED and pad.HasHole():
                pad.SetProperty(pcbnew.PAD_PROP_CASTELLATED)
                actions.append("PAD_PROP_CASTELLATED")
                need_save = True

            if need_save:
                modified_pad_count += 1
                drill_nm = pad.GetDrillSize()
                print(f"    [{ref}] Pad {pad.GetNumber()} → "
                      f"{{{', '.join(actions)}}} "
                      f"(drill={drill_nm})")

    if modified_pad_count == 0:
        print("\n  No pads needed modification (all already correctly configured).")
    else:
        print(f"\n  Modified {modified_pad_count} pad(s): NPTH→PTH + "
              f"PAD_PROP_CASTELLATED.")

    board.Save(board_file)
    sz = os.path.getsize(board_file)
    print(f"\n  [OK] Saved {board_file} ({sz:,} bytes)")
    return 0


def main() -> int:
    print("=" * 60)
    print("  AdEx Resonant Core — Fix Board Edge Clearance (Castellated)")
    print("=" * 60)
    exit_code = fix_edge_clearance(BOARD_FILE)
    if exit_code == 0:
        print("  [OK] Board edge clearance fix applied successfully.")
    print("=" * 60)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())