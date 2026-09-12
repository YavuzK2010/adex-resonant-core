#!/usr/bin/env python3
"""Make the root schematic resolve its hierarchical child sheets in-place."""
from __future__ import annotations

import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEMATIC = os.path.join(ROOT, "hardware", "adex_resonant_core.kicad_sch")

SHEET_PATHS = {
    "adex_neuron_cell.kicad_sch": "schematics/adex_neuron_cell.kicad_sch",
    "lc_bridge_cell.kicad_sch": "schematics/lc_bridge_cell.kicad_sch",
}


def main() -> int:
    with open(SCHEMATIC, encoding="utf-8") as handle:
        text = handle.read()
    for filename, relative_path in SHEET_PATHS.items():
        text = re.sub(
            rf'("Sheetfile"\s+"){re.escape(relative_path)}("\s*\))',
            rf'\g<1>{filename}\g<2>',
            text,
        )
    with open(SCHEMATIC, "w", encoding="utf-8") as handle:
        handle.write(text)
    print("align_schematic_nets: resolved hierarchical sheet paths")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())