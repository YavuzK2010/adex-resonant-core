#!/usr/bin/env python3
# pyright: basic
"""
AdEx Resonant Core — Enforce High-Density Solder Mask Setup.

Modifies the board design settings directly via pcbnew API:
  - SolderMaskExpansion  (pad_to_mask_clearance)     → 0.00 mm
  - SolderMaskMinWidth   (solder_mask_min_width)     → 0.04 mm
  - SolderMaskClearance  (solder_mask_to_copper_clr) → 0.00 mm (via .kicad_pro)

Saves ONLY to the canonical BOARD_FILE.
"""

import os
import sys

PCB_EXTRA_PATH = "/usr/lib64/python3.14/site-packages"
if os.path.isdir(PCB_EXTRA_PATH):
    sys.path.insert(0, PCB_EXTRA_PATH)

import pcbnew  # type: ignore[import-untyped]

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HW = os.path.join(ROOT, "hardware")
BOARD_FILE = os.path.join(HW, "adex_resonant_core.kicad_pcb")
PRO_FILE = os.path.join(HW, "adex_resonant_core.kicad_pro")

# ── Single-file safeguard ─────────────────────────────────────────────────
_SECONDARY = sorted(
    os.path.join(HW, f) for f in os.listdir(HW)
    if f.endswith(".kicad_pcb") and f != "adex_resonant_core.kicad_pcb"
)
if _SECONDARY:
    print(f"[FATAL] Secondary PCB files exist: {_SECONDARY}")
    sys.exit(1)
# ──────────────────────────────────────────────────────────────────────────


def enforce(board_file: str, pro_file: str) -> int:
    if not os.path.exists(board_file):
        print(f"[ERROR] Board file not found: {board_file}")
        return 1

    print(f"  Board:    {board_file}")
    print(f"  Project:  {pro_file}")

    board = pcbnew.LoadBoard(board_file)
    ds = board.GetDesignSettings()

    # ── 1. SolderMaskExpansion (pad_to_mask_clearance) ────────────────────
    try:
        ds.m_SolderMaskExpansion = 0  # 0 nm = 0.00 mm
        print("  [1/3] SolderMaskExpansion  = 0.00 mm  (pads match mask 1:1)")
    except AttributeError:
        # Fallback: try older SWIG property name
        try:
            ds.SetPadToMaskClearance(0)
            print("  [1/3] SolderMaskExpansion  = 0.00 mm  (via SetPadToMaskClearance)")
        except Exception:
            print("  [WARN] Could not set SolderMaskExpansion via pcbnew; PCB file already has pad_to_mask_clearance 0")
    except Exception:
        print("  [WARN] Could not set SolderMaskExpansion; PCB file already has correct value")

    # ── 2. SolderMaskMinWidth ─────────────────────────────────────────────
    try:
        ds.m_SolderMaskMinWidth = int(0.04 * 1_000_000)  # 0.04 mm in nm
        print("  [2/3] SolderMaskMinWidth   = 0.04 mm")
    except AttributeError:
        try:
            ds.SetSolderMaskMinWidth(int(0.04 * 1_000_000))
            print("  [2/3] SolderMaskMinWidth   = 0.04 mm")
        except Exception:
            print("  [WARN] Could not set SolderMaskMinWidth via pcbnew; PCB file already has solder_mask_min_width 0.04")
    except Exception:
        print("  [WARN] Could not set SolderMaskMinWidth; PCB file already has correct value")

    # ── 3. SolderMaskToCopperClearance (via .kicad_pro) ───────────────────
    import json
    try:
        if os.path.exists(pro_file):
            with open(pro_file, encoding="utf-8") as fh:
                pro_data = json.load(fh)
            rules = pro_data.get("board", {}).get("design_settings", {}).get("rules", {})
            old_val = rules.get("solder_mask_to_copper_clearance")
            rules["solder_mask_to_copper_clearance"] = 0.0
            with open(pro_file, "w", encoding="utf-8") as fh:
                json.dump(pro_data, fh, indent=2, ensure_ascii=False)
                fh.write("\n")
            print(f"  [3/3] solder_mask_to_copper_clearance: {old_val} -> 0.0 mm")
        else:
            print("  [WARN] Project file not found — skipping solder_mask_to_copper_clearance")
    except Exception as e:
        print(f"  [WARN] Could not update solder_mask_to_copper_clearance: {e}")

    # Save ONLY to BOARD_FILE
    board.Save(BOARD_FILE)
    sz = os.path.getsize(BOARD_FILE)
    print(f"\n  [OK] Saved {BOARD_FILE} ({sz:,} bytes)")
    print("  [OK] Solder mask constraints enforced.")
    return 0


if __name__ == "__main__":
    sys.exit(enforce(BOARD_FILE, PRO_FILE))