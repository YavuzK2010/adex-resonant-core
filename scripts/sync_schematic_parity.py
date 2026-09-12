#!/usr/bin/env python3
"""Assign schematic-derived nets to existing PCB pads without changing layout."""
from __future__ import annotations

import gc
import importlib.util
import os
import sys

PCB_EXTRA_PATH = "/usr/lib64/python3.14/site-packages"
if os.path.isdir(PCB_EXTRA_PATH) and PCB_EXTRA_PATH not in sys.path:
    sys.path.insert(0, PCB_EXTRA_PATH)

import pcbnew  # type: ignore[import-untyped]

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOARD_FILE = os.path.join(ROOT, "hardware", "adex_resonant_core.kicad_pcb")
NETLIST_SCRIPT = os.path.join(ROOT, "scripts", "sync_schematic_to_pcb.py")
PATH_SCRIPT = os.path.join(ROOT, "scripts", "sync_lvs.py")


def load_netlist_module():
    spec = importlib.util.spec_from_file_location("sync_schematic_to_pcb", NETLIST_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load schematic netlist builder")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_path_module():
    spec = importlib.util.spec_from_file_location("sync_lvs", PATH_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load schematic instance-path synchronizer")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def board_nets(board):
    net_info = board.GetNetInfo()
    return {
        str(net_info.GetNetItem(index).GetNetname()): net_info.GetNetItem(index)
        for index in range(net_info.GetNetCount())
        if str(net_info.GetNetItem(index).GetNetname())
    }


def ensure_net(board, nets, name):
    net = nets.get(name)
    if net is None:
        net = pcbnew.NETINFO_ITEM(board, name)
        board.Add(net)
        nets[name] = net
    return net


def main() -> int:
    sync = load_netlist_module()
    path_sync = load_path_module()
    netlist = sync.build_netlist()
    board = pcbnew.LoadBoard(BOARD_FILE)
    nets = board_nets(board)
    components = {
        footprint.GetReference().upper(): footprint
        for footprint in board.GetFootprints()
    }
    updated = 0
    missing = []

    for component in netlist.components:
        footprint = components.get(component.full_ref.upper())
        if footprint is None:
            missing.append(component.full_ref)
            continue
        for pad in footprint.Pads():
            suffix = component.pad_nets.get(pad.GetNumber().strip())
            if suffix is None:
                continue
            pad.SetNet(ensure_net(board, nets, f"{component.instance}_{suffix}"))
            updated += 1

    if missing:
        raise RuntimeError("Missing PCB footprints: " + ", ".join(sorted(missing)))

    paths = path_sync.schematic_paths(sync)
    path_uuids = {
        reference: metadata[0].rsplit("/", 1)[-1]
        for reference, metadata in paths.items()
    }
    linked = path_sync.apply_instance_paths(board, paths, path_uuids)
    board.BuildConnectivity()
    board.Save(BOARD_FILE)
    del board
    gc.collect()
    print(f"sync_schematic_parity: components={len(netlist.components)} pads_updated={updated} instance_paths={linked}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())