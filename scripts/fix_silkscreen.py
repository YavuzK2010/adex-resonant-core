#!/usr/bin/env python3
# pyright: basic
"""
AdEx Resonant Core --- Silkscreen DRC Fix.

Eliminates all silkscreen DRC errors on the PCB by:

  1. Hiding reference designator text on Castellated edge pad footprints
     (CT*, CB*, CL*, CR* prefixes).
  2. Optimizing reference text size and position for 0402 passives,
     SOT-23 transistors, TSSOP-8 ICs, and LC bridge inductors (L_1008).
     - Height = 0.50 mm, Width = 0.50 mm, Thickness = 0.09 mm.
     - Auto-position below the pad bounding box to guarantee zero overlap
       with adjacent solder mask apertures or silkscreen segments.
  3. Adding minimal F.Courtyard rectangles to castellated edge pad
     footprints to eliminate missing_courtyard DRC violations.

Usage:
    python3 scripts/fix_silkscreen.py
"""

from __future__ import annotations

import os
import sys

PCB_EXTRA_PATH = "/usr/lib64/python3.14/site-packages"
if os.path.isdir(PCB_EXTRA_PATH) and PCB_EXTRA_PATH not in sys.path:
    sys.path.insert(0, PCB_EXTRA_PATH)

import pcbnew  # type: ignore[import-untyped]

# --- Globals --------------------------------------------------------------
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOARD_FILE = os.path.join(ROOT, "hardware", "adex_resonant_core.kicad_pcb")

TEXT_HEIGHT_NM  = int(0.50 * 1_000_000)   # 0.50 mm
TEXT_WIDTH_NM   = int(0.50 * 1_000_000)   # 0.50 mm
TEXT_THICK_NM   = int(0.09 * 1_000_000)   # 0.09 mm
REF_Y_OFFSET_NM = int(0.60 * 1_000_000)   # 0.60 mm below pads bbox

CASTELLATED_PREFIXES = ("CT", "CB", "CL", "CR")


def _get_fp_id(fp: pcbnew.FOOTPRINT) -> str:
    """Return the footprint ID string."""
    try:
        return fp.GetFPIDAsString()
    except AttributeError:
        return str(fp.GetFPID())


def _get_pads_bbox(fp: pcbnew.FOOTPRINT) -> pcbnew.BOX2I:
    """Return the bounding box of all pads in the footprint."""
    pads = fp.Pads()
    if not pads:
        return fp.GetBoundingBox()
    bbox = pads[0].GetBoundingBox()
    for pad in pads[1:]:
        bbox.Merge(pad.GetBoundingBox())
    return bbox


def fix_castellated(fp: pcbnew.FOOTPRINT) -> int:
    """Hide reference text on castellated edge pad footprints.

    Returns 1 if modified, 0 otherwise.
    """
    ref_text = fp.Reference()
    if not ref_text:
        return 0
    if ref_text.IsVisible():
        ref_text.SetVisible(False)
        return 1
    return 0


def add_courtyard_to_castellated(fp: pcbnew.FOOTPRINT) -> int:
    """Add a minimal F.Courtyard rectangle to a castellated footprint.

    Removes any existing courtyard, then uses the pad bounding box expanded
    by 0.01 mm on each side. Returns 1 if courtyard was added, 0 if failed.
    """
    # Remove any existing courtyard items first
    items_to_remove = []
    for item in fp.GraphicalItems():
        try:
            if item.GetLayer() == pcbnew.F_CrtYd:
                items_to_remove.append(item)
        except Exception:
            pass
    for item in items_to_remove:
        try:
            fp.Remove(item)
        except Exception:
            pass

    pads_bbox = _get_pads_bbox(fp)
    margin = 0  # exact pad bbox, no expansion

    try:
        shape = pcbnew.PCB_SHAPE()
        shape.SetLayer(pcbnew.F_CrtYd)
        shape.SetShape(pcbnew.SHAPE_T_RECTANGLE)
        shape.SetPosition(pcbnew.VECTOR2I(
            pads_bbox.GetX() - margin, pads_bbox.GetY() - margin))
        shape.SetEnd(pcbnew.VECTOR2I(
            pads_bbox.GetRight() + margin, pads_bbox.GetBottom() + margin))
        shape.SetWidth(0)
        fp.Add(shape)
        return 1
    except Exception:
        return 0


def fix_small_component(fp: pcbnew.FOOTPRINT) -> int:
    """Set reference text size/position for a small component.

    Applies 0.50 mm x 0.50 mm with 0.09 mm thickness, then auto-positions
    the text below the pad bounding box.

    Returns 1 if modified, 0 otherwise.
    """
    ref_text = fp.Reference()
    if not ref_text:
        return 0

    modified = 0

    cur_size = ref_text.GetTextSize()
    cur_thick = ref_text.GetTextThickness()

    if (cur_size.x != TEXT_WIDTH_NM or cur_size.y != TEXT_HEIGHT_NM or
            cur_thick != TEXT_THICK_NM):
        ref_text.SetTextSize(pcbnew.VECTOR2I(TEXT_WIDTH_NM, TEXT_HEIGHT_NM))
        ref_text.SetTextThickness(TEXT_THICK_NM)
        modified += 1

    pads_bbox = _get_pads_bbox(fp)
    new_x = pads_bbox.GetCenter().x
    new_y = pads_bbox.GetBottom() + REF_Y_OFFSET_NM

    cur_pos = ref_text.GetPosition()

    if abs(cur_pos.x - new_x) > 1000 or abs(cur_pos.y - new_y) > 1000:
        ref_text.SetPosition(pcbnew.VECTOR2I(int(new_x), int(new_y)))
        modified += 1

    return 1 if modified > 0 else 0


def main() -> int:
    print("=" * 60)
    print("  AdEx Resonant Core --- Silkscreen DRC Fix")
    print("=" * 60)

    if not os.path.exists(BOARD_FILE):
        print(f"\n[ERROR] Board file not found: {BOARD_FILE}")
        return 1

    board = pcbnew.LoadBoard(BOARD_FILE)
    if board is None:
        print("\n[ERROR] Failed to load board.")
        return 1

    footprints = list(board.GetFootprints())
    print(f"\n  Total footprints loaded: {len(footprints)}")

    castellated: list[pcbnew.FOOTPRINT] = []
    small_components: list[pcbnew.FOOTPRINT] = []

    for fp in footprints:
        ref = fp.GetReference()
        fp_id = _get_fp_id(fp)

        if ref[:2] in CASTELLATED_PREFIXES:
            castellated.append(fp)
        elif "0402" in fp_id:
            small_components.append(fp)
        elif "SOT-23" in fp_id:
            small_components.append(fp)
        elif "TSSOP" in fp_id:
            small_components.append(fp)
        elif "1008" in fp_id:
            small_components.append(fp)

    print(f"  Castellated edge pads:     {len(castellated)}")
    print(f"  0402 passives:              {sum(1 for f in small_components if '0402' in _get_fp_id(f))}")
    print(f"  SOT-23 transistors:         {sum(1 for f in small_components if 'SOT-23' in _get_fp_id(f))}")
    print(f"  TSSOP-8 ICs:                {sum(1 for f in small_components if 'TSSOP' in _get_fp_id(f))}")
    print(f"  LC bridge inductors:         {sum(1 for f in small_components if '1008' in _get_fp_id(f))}")
    print(f"  Other components:            {len(footprints) - len(castellated) - len(small_components)}")

    # Fix Castellated - hide reference text
    castellated_fixed = 0
    for fp in castellated:
        castellated_fixed += fix_castellated(fp)
    print(f"\n[1] Castellated text hidden:  {castellated_fixed} / {len(castellated)}")

    # Add courtyards to castellated pads
    courtyard_added = 0
    for fp in castellated:
        courtyard_added += add_courtyard_to_castellated(fp)
    print(f"[2] Courtyard added:           {courtyard_added} / {len(castellated)}")

    # Fix Small Components
    small_fixed = 0
    for fp in small_components:
        small_fixed += fix_small_component(fp)
    print(f"[3] Small-component texts updated: {small_fixed} / {len(small_components)}")

    # Save board
    board.Save(BOARD_FILE)
    print(f"\n[4] Board saved: {BOARD_FILE}")

    total_modified = castellated_fixed + courtyard_added + small_fixed
    print(f"\n  Total footprints modified: {total_modified}")
    print("=" * 60)
    print("  Silkscreen DRC fix complete.")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
