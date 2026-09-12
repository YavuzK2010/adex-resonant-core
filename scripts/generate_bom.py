#!/usr/bin/env python3
"""
AdEx Resonant Core — BOM Export for JLCPCB / PCBWay.

Generates a JLCPCB-compatible BOM CSV from the pcbnew board data.

Usage:
    python3 scripts/generate_bom.py
"""

from __future__ import annotations

import csv
import os
import sys
from typing import Any

PCB_EXTRA_PATH = "/usr/lib64/python3.14/site-packages"
if os.path.isdir(PCB_EXTRA_PATH) and PCB_EXTRA_PATH not in sys.path:
    sys.path.insert(0, PCB_EXTRA_PATH)

import pcbnew  # type: ignore[import-untyped]

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOARD_FILE = os.path.join(ROOT, "hardware", "adex_resonant_core.kicad_pcb")
EXPORTS_DIR = os.path.join(ROOT, "hardware", "exports")
OUTPUT_CSV = os.path.join(EXPORTS_DIR, "bom_jlcpcb.csv")

# Map common KiCad footprint IDs to JLCPCB-compatible descriptions / LCSC codes
# This is a minimal mapping; users should verify and fill in LCSC part numbers.
FP_DESC: dict[str, tuple[str, str, str]] = {
    "R_0402_1005Metric": ("Resistor", "0402", ""),
    "C_0402_1005Metric": ("Capacitor", "0402", ""),
    "L_1008_2520Metric": ("Inductor", "1008", ""),
    "TSSOP-8_4.4x3mm_P0.65mm": ("IC", "TSSOP-8", ""),
    "SOT-23": ("Transistor", "SOT-23", ""),
}


def main() -> int:
    os.makedirs(EXPORTS_DIR, exist_ok=True)
    board = pcbnew.LoadBoard(BOARD_FILE)

    rows: list[dict[str, str]] = []
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        value = fp.GetValue()
        fp_id = fp.GetFPIDAsString() if hasattr(fp, "GetFPIDAsString") else ""
        # Extract the base footprint name after the last colon
        fp_name = fp_id.split(":")[-1] if ":" in fp_id else fp_id
        desc, pkg, lcsc = FP_DESC.get(fp_name, ("", fp_name, ""))
        if not desc:
            desc = fp_name

        row = {
            "Reference": ref,
            "Value": value,
            "Footprint": fp_name,
            "Description": desc,
            "Package": pkg,
            "LCSC": lcsc,
            "Qty": "1",
        }
        rows.append(row)

    # Sort by reference
    rows.sort(key=lambda r: (r["Reference"][0], int("".join(c for c in r["Reference"] if c.isdigit()) or 0)))

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["Reference", "Value", "Footprint",
                                                "Description", "Package", "LCSC", "Qty"])
        writer.writeheader()
        writer.writerows(rows)

    print(f"BOM written: {OUTPUT_CSV} ({len(rows)} components)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())