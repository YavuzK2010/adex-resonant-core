#!/usr/bin/env python3
"""Restore schematic instance paths on PCB footprints for KiCad parity DRC."""
from __future__ import annotations

import re
import sys
from pathlib import Path

PCB_EXTRA_PATH = "/usr/lib64/python3.14/site-packages"
if Path(PCB_EXTRA_PATH).is_dir():
    sys.path.insert(0, PCB_EXTRA_PATH)

import pcbnew  # type: ignore[import-untyped]


ROOT = Path(__file__).resolve().parents[1]
SCHEMATICS = ROOT / "hardware" / "schematics"
ROOT_SCHEMATIC = ROOT / "hardware" / "adex_resonant_core.kicad_sch"
BOARD = ROOT / "hardware" / "adex_resonant_core.kicad_pcb"


def schematic_paths() -> dict[str, str]:
    paths: dict[str, str] = {}
    for schematic in [ROOT_SCHEMATIC, *SCHEMATICS.glob("*.kicad_sch")]:
        text = schematic.read_text(encoding="utf-8")
        for match in re.finditer(
            r'\(path "([^"]+)"[\s\S]*?\(reference "([^"]+)"', text):
            paths[match.group(2)] = match.group(1)
    return paths


def main() -> int:
    paths = schematic_paths()
    board_text = BOARD.read_text(encoding="utf-8")
    if "--clean" in sys.argv:
        board_text = re.sub(r'\n\s*\(path "[^"]+"\)', "", board_text)
        board_text = re.sub(r'\n\s*\(sheetname "[^"]+"\)', "", board_text)
        board_text = re.sub(r'\n\s*\(sheetfile "[^"]+"\)', "", board_text)
        BOARD.write_text(board_text, encoding="utf-8")
        return 0
    board = pcbnew.LoadBoard(str(BOARD))
    repaired = 0
    missing: list[str] = []
    for footprint in board.GetFootprints():
        reference = footprint.GetReference()
        path = paths.get(reference)
        if path is None:
            missing.append(reference)
            continue
        repaired += 1

    def add_path(match: re.Match[str]) -> str:
        block = match.group(0)
        reference = re.search(r'\(property "Reference" "([^"]+)"', block)
        if reference is None or reference.group(1) not in paths:
            return block
        block = re.sub(r'\n\s*\(path "[^"]+"\)', "", block)
        block = re.sub(r'\n\s*\(sheetname "[^"]+"\)', "", block)
        block = re.sub(r'\n\s*\(sheetfile "[^"]+"\)', "", block)
        sheet = reference.group(1).split("_", 1)[0]
        sheetfile = "adex_neuron_cell.kicad_sch" if sheet.startswith("N") else "lc_bridge_cell.kicad_sch"
        metadata = (
            f'\n                (path "{paths[reference.group(1)]}")'
            f'\n                (sheetname "/{sheet}/")'
            f'\n                (sheetfile "{sheetfile}")'
        )
        return block.replace(
            re.search(r'\n\s*\(uuid "[^"]+"\)', block).group(0),
            re.search(r'\n\s*\(uuid "[^"]+"\)', block).group(0)
            + metadata,
            1,
        )

    board_text = re.sub(
        r'(?ms)^\s*\(footprint\s+.*?(?=^\s*\(footprint\s+|^\s*\(zone\s|\Z)',
        add_path,
        board_text,
    )
    BOARD.write_text(board_text, encoding="utf-8")
    print(f"Restored schematic paths on {repaired} footprints.")
    print(f"Skipped {len(missing)} non-schematic footprints.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())