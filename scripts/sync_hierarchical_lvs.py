#!/usr/bin/env python3
"""Flatten the project hierarchy for KiCad parity and update PCB pads in place."""
from __future__ import annotations

import gc
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

PCB_EXTRA_PATH = "/usr/lib64/python3.14/site-packages"
if os.path.isdir(PCB_EXTRA_PATH) and PCB_EXTRA_PATH not in sys.path:
    sys.path.insert(0, PCB_EXTRA_PATH)

import pcbnew  # type: ignore[import-untyped]

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HW = os.path.join(ROOT, "hardware")
BOARD_FILE = os.path.join(HW, "adex_resonant_core.kicad_pcb")
ROOT_SCH = os.path.join(HW, "adex_resonant_core.kicad_sch")
TOP_SCH = os.path.join(HW, "schematics", "top_level.kicad_sch")
NEURON_SCH = os.path.join(HW, "schematics", "adex_neuron_cell.kicad_sch")
BRIDGE_SCH = os.path.join(HW, "schematics", "lc_bridge_cell.kicad_sch")
NETLIST_SCRIPT = os.path.join(ROOT, "scripts", "sync_schematic_to_pcb.py")
PATH_SCRIPT = os.path.join(ROOT, "scripts", "sync_lvs.py")


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def board_nets(board):
    info = board.GetNetInfo()
    return {
        str(info.GetNetItem(index).GetNetname()): info.GetNetItem(index)
        for index in range(info.GetNetCount())
        if str(info.GetNetItem(index).GetNetname())
    }


def ensure_net(board, nets, name):
    net = nets.get(name)
    if net is None:
        net = pcbnew.NETINFO_ITEM(board, name)
        board.Add(net)
        nets[name] = net
    return net


def flattened_components():
    with tempfile.TemporaryDirectory() as directory:
        output = os.path.join(directory, "netlist.xml")
        subprocess.run(
            ["kicad-cli", "sch", "export", "netlist", "--format", "kicadxml",
             "--output", output, ROOT_SCH],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        root = ET.parse(output).getroot()

    components = {}
    for component in root.findall("./components/comp"):
        ref = component.get("ref", "").upper()
        properties = {
            prop.get("name", ""): prop.get("value", "")
            for prop in component.findall("property")
        }
        components[ref] = {
            "footprint": component.findtext("footprint", ""),
            "description": properties.get("ki_description", ""),
            "filters": properties.get("ki_fp_filters", ""),
            "nets": {},
        }
    for net in root.findall("./nets/net"):
        name = net.get("name", "")
        for node in net.findall("node"):
            ref = node.get("ref", "").upper()
            if ref in components:
                components[ref]["nets"][node.get("pin", "")] = name
    return components


def main() -> int:
    sync = load_module("sync_schematic_to_pcb", NETLIST_SCRIPT)
    path_sync = load_module("sync_lvs", PATH_SCRIPT)
    top = sync.KiCadSch(TOP_SCH)
    if len(top.sheets) != 31:
        raise RuntimeError(f"Expected 31 hierarchical sheets, found {len(top.sheets)}")

    # The PCB parity command loads this adjacent file, while the valid
    # hierarchical source lives under hardware/schematics.
    shutil.copyfile(TOP_SCH, ROOT_SCH)
    for source in (NEURON_SCH, BRIDGE_SCH):
        shutil.copyfile(source, os.path.join(HW, os.path.basename(source)))

    netlist = sync.build_netlist()
    flattened = flattened_components()
    expected_refs = {component.full_ref.upper() for component in netlist.components}
    physical_refs = {
        reference for reference, metadata in flattened.items()
        if metadata["footprint"]
    }
    if not expected_refs.issubset(physical_refs):
        missing = sorted(expected_refs - physical_refs)
        raise RuntimeError(f"Flattened netlist is missing physical references: {missing}")
    board = pcbnew.LoadBoard(BOARD_FILE)
    footprints = {fp.GetReference().upper(): fp for fp in board.GetFootprints()}
    nets = board_nets(board)
    schematic_components = {
        component.full_ref.upper(): component for component in netlist.components
    }
    pads_updated = 0
    for reference, metadata in flattened.items():
        footprint = footprints.get(reference)
        if footprint is None:
            continue
        if metadata["footprint"]:
            footprint.SetFPIDAsString(metadata["footprint"])
        if metadata["description"]:
            footprint.SetLibDescription(metadata["description"])
        if metadata["filters"]:
            footprint.SetFilters(metadata["filters"])
        component = schematic_components.get(reference)
        if component is None:
            continue
        for pad in footprint.Pads():
            suffix = component.pad_nets.get(pad.GetNumber().strip())
            if suffix is not None:
                name = f"{component.instance}_{suffix}"
                pad.SetNet(ensure_net(board, nets, name))
                pads_updated += 1

    paths = path_sync.schematic_paths(sync)
    path_sync.apply_instance_paths(board, paths, {})
    board.BuildConnectivity()
    board.Save(BOARD_FILE)
    del board
    gc.collect()
    print(f"sync_hierarchical_lvs: sheets={len(top.sheets)} components={len(flattened)} pads_updated={pads_updated}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())