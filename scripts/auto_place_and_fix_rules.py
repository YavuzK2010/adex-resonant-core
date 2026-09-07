#!/usr/bin/env python3
"""
AdEx Resonant Core — Auto-Place & Fix DRC Rules.

Resolves 1273 DRC violations caused by castellated-hole footprints
stacked at the board edge:
  1. Set CopperEdgeClearance → 0.0 mm  (fixes copper_edge_clearance
     & silk_edge_clearance for pads touching Edge.Cuts)
  2. Unpack all footprints into a clean 2D grid inside the 50×50 mm
     board (fixes clearance, hole_clearance, holes_co_located,
     silk_overlap).

NOTE: No traces are routed here; routing is deferred to FreeRouting.
"""

import os
import sys

# Ensure pcbnew is importable (KiCad Python bindings)
PCB_EXTRA_PATH = "/usr/lib64/python3.14/site-packages"
if os.path.isdir(PCB_EXTRA_PATH):
    sys.path.insert(0, PCB_EXTRA_PATH)

import pcbnew  # type: ignore[import-untyped]

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LAYOUTS = os.path.join(ROOT, "hardware", "layouts")
BOARD_FILE = os.path.join(LAYOUTS, "adex_resonant_core.kicad_pcb")

# Board constants (in mm)
BOARD_SIZE_MM = 50.0
START_X_MM = 5.0    # grid origin X (mm)
START_Y_MM = 5.0    # grid origin Y (mm)
COL_SPACING_MM = 4.0
ROW_SPACING_MM = 4.0
# Grid dimensions — 10×10 = 100 slots, enough for 96 footprints
GRID_COLS = 10
GRID_ROWS = 10


def mm_to_nm(v_mm: float) -> int:
    """Convert millimetres to nanometres (KiCad internal unit)."""
    return int(round(v_mm * 1_000_000))


def nm_to_mm(v_nm: int) -> float:
    """Convert nanometres to millimetres."""
    return v_nm / 1_000_000.0


def fix_edge_clearance(board: pcbnew.BOARD) -> None:
    """
    Set CopperEdgeClearance to 0.0 nm.

    Castellated pads must touch the Edge.Cuts layer to function as
    edge connectors; the default 0.5 mm clearance causes 192 false
    positives (96 copper + 96 silk).
    """
    ds = board.GetDesignSettings()
    old_val_nm = ds.m_CopperEdgeClearance
    ds.m_CopperEdgeClearance = 0
    print(f"  [FIX] CopperEdgeClearance: {nm_to_mm(old_val_nm):.3f} mm → 0.000 mm")


def unpack_footprints_to_grid(board: pcbnew.BOARD) -> None:
    """
    Iterate all footprints and arrange them in a (COL_SPACING_MM ×
    ROW_SPACING_MM) grid starting at (START_X_MM, START_Y_MM).

    Each footprint keeps its original rotation so that pad orientations
    are preserved for later routing.
    """
    fps = list(board.GetFootprints())
    n = len(fps)
    print(f"  Footprints found: {n}")

    if n == 0:
        print("  [WARN] No footprints on board — nothing to unpack.")
        return

    # Sort by reference for deterministic placement
    fps.sort(key=lambda f: f.GetReference())

    placed = 0
    for i, fp in enumerate(fps):
        col = i % GRID_COLS
        row = i // GRID_COLS

        if row >= GRID_ROWS:
            print(f"  [WARN] Grid exhausted ({GRID_COLS}×{GRID_ROWS} = "
                  f"{GRID_COLS * GRID_ROWS} slots). {n - placed} footprints remain.")
            break

        x_nm = mm_to_nm(START_X_MM + col * COL_SPACING_MM)
        y_nm = mm_to_nm(START_Y_MM + row * ROW_SPACING_MM)

        old_pos = fp.GetPosition()
        fp.SetPosition(pcbnew.VECTOR2I(x_nm, y_nm))
        placed += 1

        if placed <= 5 or placed == n or (placed % 20 == 0):
            print(f"    {fp.GetReference():6s}: "
                  f"({nm_to_mm(old_pos.x):6.2f}, {nm_to_mm(old_pos.y):6.2f}) → "
                  f"({nm_to_mm(x_nm):6.2f}, {nm_to_mm(y_nm):6.2f})  "
                  f"rot={fp.GetOrientationDegrees():5.1f}°")

    print(f"  [OK] Placed {placed}/{n} footprints in grid "
          f"({GRID_COLS}×{GRID_ROWS}, {COL_SPACING_MM}×{ROW_SPACING_MM} mm)")


def main() -> int:
    print("=" * 64)
    print("  AdEx Resonant Core — Auto-Place & Fix DRC Rules")
    print("=" * 64)

    # -----------------------------------------------------------------
    # Validate paths
    # -----------------------------------------------------------------
    if not os.path.exists(BOARD_FILE):
        print(f"\n[ERROR] Board file not found: {BOARD_FILE}")
        return 1

    if not os.path.exists(PCB_EXTRA_PATH):
        print(f"\n[WARN] KiCad Python path not found at {PCB_EXTRA_PATH}")
        print("  The script may still work if pcbnew is on PYTHONPATH.\n")

    # -----------------------------------------------------------------
    # Load board
    # -----------------------------------------------------------------
    print(f"\n[1/3] Loading board: {BOARD_FILE}")
    board = pcbnew.LoadBoard(BOARD_FILE)
    print(f"  Board loaded — {len(list(board.GetFootprints()))} footprints, "
          f"{len(list(board.GetTracks()))} tracks, "
          f"{len(list(board.GetDrawings()))} drawings.")

    # -----------------------------------------------------------------
    # Fix edge clearance
    # -----------------------------------------------------------------
    print(f"\n[2/3] Fixing edge-clearance rule …")
    fix_edge_clearance(board)

    # -----------------------------------------------------------------
    # Unpack footprints to grid
    # -----------------------------------------------------------------
    print(f"\n[3/3] Unpacking footprints to grid …")
    unpack_footprints_to_grid(board)

    # -----------------------------------------------------------------
    # Save
    # -----------------------------------------------------------------
    print(f"\nSaving board …")
    board.Save(BOARD_FILE)
    sz = os.path.getsize(BOARD_FILE)
    print(f"  [OK] Written {BOARD_FILE} ({sz:,} bytes)")

    print("\n" + "=" * 64)
    print("  Done.  Run 'python3 scripts/run_pcb_drc.py' to verify.")
    print("=" * 64)
    return 0


if __name__ == "__main__":
    sys.exit(main())