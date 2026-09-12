#!/usr/bin/env python3
"""Reference-based PCB netlist refresh and orphaned-route purge."""
from __future__ import annotations

import importlib.util
import gc
import os
import re
import sys

PCB_EXTRA_PATH = "/usr/lib64/python3.14/site-packages"
if os.path.isdir(PCB_EXTRA_PATH):
    sys.path.insert(0, PCB_EXTRA_PATH)

import pcbnew  # type: ignore[import-untyped]

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOARD_FILE = os.path.join(ROOT, "hardware", "adex_resonant_core.kicad_pcb")
SYNC_FILE = os.path.join(ROOT, "scripts", "sync_schematic_to_pcb.py")


def load_sync_module():
    spec = importlib.util.spec_from_file_location("sync_schematic_to_pcb", SYNC_FILE)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load schematic synchronizer")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def schematic_paths(sync) -> dict[str, tuple[str, str, str]]:
    repair_file = os.path.join(ROOT, "scripts", "repair_schematic_parity.py")
    spec = importlib.util.spec_from_file_location("repair_schematic_parity", repair_file)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load schematic instance-path parser")
    repair = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(repair)
    paths: dict[str, tuple[str, str, str]] = {}
    for reference, path in repair.schematic_paths().items():
        sheet = reference.split("_", 1)[0]
        sheetfile = "adex_neuron_cell.kicad_sch" if sheet.startswith("N") else "lc_bridge_cell.kicad_sch"
        paths[reference.upper()] = (path, f"/{sheet}/", sheetfile)
    return paths


def apply_instance_paths(board, paths: dict[str, tuple[str, str, str]], uuids: dict[str, str]) -> int:
    updated = 0
    for footprint in list(board.GetFootprints()):
        if not hasattr(footprint, "GetReference"):
            continue
        metadata = paths.get(footprint.GetReference().upper())
        if metadata is None:
            continue
        path, sheetname, sheetfile = metadata
        footprint.SetPath(pcbnew.KIID_PATH(path))
        footprint.SetSheetname(sheetname)
        footprint.SetSheetfile(sheetfile)
        component_uuid = uuids.get(footprint.GetReference().upper())
        if component_uuid:
            footprint.SetLink(pcbnew.KIID(component_uuid))
        updated += 1
    return updated


def purge_routes(board) -> int:
    removed = 0
    for item in list(board.GetTracks()):
        board.RemoveNative(item)
        removed += 1
    return removed


def purge_orphan_footprints(board, netlist) -> int:
    expected = {component.full_ref.upper() for component in netlist.components}
    removed = 0
    for footprint in list(board.GetFootprints()):
        if footprint.GetReference().upper() not in expected:
            board.RemoveNative(footprint)
            removed += 1
    return removed


def main() -> int:
    sync = load_sync_module()
    netlist = sync.build_netlist()
    paths = schematic_paths(sync)
    uuids = {
        f"{sheet.instance}_{component.reference}".upper(): component.uuid
        for sheet in sync.KiCadSch(sync.TOP_SCH).sheets
        for schematic in (sync.KiCadSch(sync.NEURON_SCH) if sheet.file == "adex_neuron_cell.kicad_sch" else sync.KiCadSch(sync.BRIDGE_SCH),)
        for component in schematic.components
    }
    board = pcbnew.LoadBoard(BOARD_FILE)
    removed = purge_routes(board)
    orphaned = purge_orphan_footprints(board, netlist)
    sync.apply_netlist(board, netlist)
    board.Save(BOARD_FILE)
    del board
    gc.collect()
    board = pcbnew.LoadBoard(BOARD_FILE)
    linked = apply_instance_paths(board, paths, uuids)
    board.BuildConnectivity()
    board.Save(BOARD_FILE)
    print(f"sync_lvs: components={len(netlist.components)} nets={len(netlist.nets)} routes_purged={removed} orphan_footprints={orphaned} instance_paths={linked}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())