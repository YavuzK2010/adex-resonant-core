#!/usr/bin/env python3
"""Import freerouting.ses Specctra session routing into the committed board.

Restores the original F.Cu routing and vias, reproducing the board state
before the 8 B.Cu connections were missing.
"""
import os
import sys
import subprocess
from typing import Any

sys.path.insert(0, '/usr/lib64/python3.14/site-packages')
import pcbnew  # type: ignore[import-untyped]

ROOT = '/home/yavuzkemalinan/adex-resonant-brain'
HW = os.path.join(ROOT, 'hardware')
BOARD_FILE = os.path.join(HW, 'adex_resonant_core.kicad_pcb')
SES_FILE = os.path.join(HW, 'freerouting.ses')

LAYER_MAP = {'F.Cu': pcbnew.F_Cu, 'B.Cu': pcbnew.B_Cu}


def specctra_to_nm(x: int) -> int:
    """Convert Specctra coord (resolution um 10 = 100nm/unit) to KiCad nm."""
    return x * 100


def parse_ses(path: str) -> list[dict]:
    """Parse the .ses file and return list of net entries (wires + vias)."""
    with open(path, encoding='utf-8') as fh:
        text = fh.read()

    wiring_start = text.find('(routes')
    if wiring_start < 0:
        print('[ERROR] No (routes section in .ses')
        return []

    # Compute wiring section boundary
    depth = 0
    wiring_end = None
    for i in range(wiring_start, len(text)):
        if text[i] == '(':
            depth += 1
        elif text[i] == ')':
            depth -= 1
            if depth == 0:
                wiring_end = i + 1
                break
    wiring_text = text[wiring_start:wiring_end]

    results = []
    net_pos = 0
    while True:
        net_start = wiring_text.find('(net "', net_pos)
        if net_start < 0:
            break
        depth = 0
        net_end = None
        for i in range(net_start, len(wiring_text)):
            if wiring_text[i] == '(':
                depth += 1
            elif wiring_text[i] == ')':
                depth -= 1
                if depth == 0:
                    net_end = i + 1
                    break
        if net_end is None:
            break
        net_block = wiring_text[net_start:net_end]
        net_pos = net_end

        q1 = net_block.find('(net "')
        q2 = net_block.find('"', q1 + 6)
        name = net_block[q1+6:q2]

        entry = {'net': name, 'wires': [], 'vias': []}

        # wires
        wpos = 0
        while True:
            ws = net_block.find('(wire', wpos)
            if ws < 0:
                break
            cstart = net_block.find('(path', ws)
            if cstart < 0:
                break
            line_end = net_block.find(')', cstart)
            parts = net_block[cstart:line_end].strip().split()
            # parts: ['(path', 'LAYER', 'WIDTH', 'x1','y1','x2','y2', ...]
            if len(parts) >= 5:
                layer = parts[1]
                width_nm = int(parts[2]) * 100
                coords_raw = [int(p) for p in parts[3:]]
                coords = [(coords_raw[i]*100, -coords_raw[i+1]*100)
                          for i in range(0, len(coords_raw)-1, 2)]
                entry['wires'].append({'layer': layer, 'width_nm': width_nm,
                                       'coords': coords})
            wpos = line_end

        # vias
        vpos = 0
        while True:
            vs = net_block.find('(via "', vpos)
            if vs < 0:
                break
            q1 = net_block.find('"', vs + 6)
            if q1 < 0:
                break
            via_name = net_block[vs+6:q1]
            rest = net_block[q1+1:net_block.find(')', q1)].strip().split()
            if len(rest) >= 2:
                entry['vias'].append({
                    'name': via_name,
                    'x_nm': int(rest[0]) * 100,
                    'y_nm': -int(rest[1]) * 100,
                    'pad_mm': 0.60, 'drill_mm': 0.30,
                })
            vpos = q1 + 1

        results.append(entry)

    wires = sum(len(n['wires']) for n in results)
    vias = sum(len(n['vias']) for n in results)
    print(f'  Parsed {len(results)} nets, {wires} wires, {vias} vias')
    return results


def apply_routing(board: Any, nets: list[dict]) -> tuple[int, int]:
    """Apply .ses routing tracks and vias to the board."""
    segments = 0
    vias_added = 0

    for net_entry in nets:
        netname = net_entry['net']
        net_obj = board.FindNet(netname)
        if net_obj is None:
            print(f'    [SKIP] net {netname}: not found on board')
            continue

        for wire in net_entry['wires']:
            layer = LAYER_MAP.get(wire['layer'])
            if layer is None:
                continue
            width_nm = wire['width_nm']
            coords = wire['coords']
            for i in range(len(coords) - 1):
                x1, y1 = coords[i]
                x2, y2 = coords[i+1]
                t = pcbnew.PCB_TRACK(board)
                t.SetStart(pcbnew.VECTOR2I(int(x1), int(y1)))
                t.SetEnd(pcbnew.VECTOR2I(int(x2), int(y2)))
                t.SetWidth(int(width_nm))
                t.SetLayer(layer)
                t.SetNet(net_obj)
                board.Add(t)
                segments += 1

        for via_info in net_entry['vias']:
            v = pcbnew.PCB_VIA(board)
            v.SetPosition(pcbnew.VECTOR2I(int(via_info['x_nm']), int(via_info['y_nm'])))
            v.SetDrill(int(via_info['drill_mm'] * 1e6))
            v.SetWidth(int(via_info['pad_mm'] * 1e6))
            v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
            v.SetNet(net_obj)
            board.Add(v)
            vias_added += 1

    return segments, vias_added


def main() -> int:
    print('=' * 64)
    print('  AdEx Resonant Core - Import .ses Routing')
    print('=' * 64)

    subprocess.run(['git', 'checkout', '--', 'hardware/adex_resonant_core.kicad_pcb'],
                   cwd=ROOT)

    board = pcbnew.LoadBoard(BOARD_FILE)
    print(f'  Board: {len(list(board.GetFootprints()))} footprints, '
          f'{len(list(board.GetTracks()))} tracks')

    nets = parse_ses(SES_FILE)
    segs, vias = apply_routing(board, nets)
    print(f'  Added {segs} track segment(s) and {vias} via(s)')

    board.Save(BOARD_FILE)
    sz = os.path.getsize(BOARD_FILE)
    print(f'\n  [OK] Saved: {BOARD_FILE} ({sz:,} bytes)')
    print(f'  Total tracks now: {len(list(board.GetTracks()))}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
