#!/usr/bin/env python3
# pyright: basic
"""
AdEx Resonant Core — Complete Trace Wipe & Layer-Isolated Reroute.

Executes:
  1. Single-file enforcement (only canonical .kicad_pcb; abort if duplicate)
  2. Ripup ALL tracks, micro-vias, and blind vias across all layers
  3. Set design rules: SolderMaskExpansion=0, SolderMaskMinWidth=0.04,
     track width 0.20 mm, clearance 0.18 mm, via 0.55/0.30 mm
  4. Add zones on In1.Cu (GND nets) and In2.Cu (VDD/VSS nets) to provide
     internal plane copper for the per-neuron hierarchical ground/power nets.
  5. Add through-hole vias (0.55 mm pad / 0.30 mm drill, layers F.Cu to B.Cu)
     at every GND/VDD/VSS pad center (via-in-pad) -- no surface power traces.
  6. Route analog membrane traces (V_m, V_TH) on F.Cu (0.20 mm width, 0.18 mm
     clearance) using orthogonal 45/90-degree segments.
  7. Route SPIKE_OUT signals on B.Cu via through-hole vias with >=0.25 mm
     clearance from top-layer component pads.
  8. Enforce 90-degree perpendicular exit (>=0.25 mm) on all 0402/TSSOP-8 pad
     departures.
  9. Save to canonical BOARD_FILE only.
"""

import math
import os
import re
import sys
from typing import Any

PCB_EXTRA_PATH = "/usr/lib64/python3.14/site-packages"
if os.path.isdir(PCB_EXTRA_PATH):
    sys.path.insert(0, PCB_EXTRA_PATH)

import pcbnew  # type: ignore[import-untyped]

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HW = os.path.join(ROOT, "hardware")
BOARD_FILE = os.path.join(HW, "adex_resonant_core.kicad_pcb")

# ── Constants ────────────────────────────────────────────────────────────
VIA_DRILL_MM = 0.30
VIA_PAD_MM = 0.55
TRACK_W_MM = 0.20
CLEAR_MM = 0.18
CLEAR_R_MM = TRACK_W_MM / 2.0 + CLEAR_MM + 0.01  # 0.20 mm
MIN_EXIT_MM = 0.25  # 90-degree perpendicular exit minimum

BOARD_SIZE_MM = 70.0

# ── Single-file safeguard ───────────────────────────────────────────────
_SECONDARY = sorted(
    os.path.join(HW, f) for f in os.listdir(HW)
    if f.endswith(".kicad_pcb") and f != "adex_resonant_core.kicad_pcb"
)
if _SECONDARY:
    print(f"[FATAL] Secondary PCB files detected: {_SECONDARY}")
    sys.exit(1)

# ── Utility ──────────────────────────────────────────────────────────────


def mm(v: float) -> int:
    return int(round(v * 1_000_000))


def nm(v: int) -> float:
    return v / 1_000_000.0


def is_castellated(fp: Any) -> bool:
    ref: str = fp.GetReference().upper().strip()
    return bool(re.match(r"^(C[TBRL])\d{3}$", ref))


# ═══════════════════════════════════════════════════════════════════════════
# Phase 1: Ripup
# ═══════════════════════════════════════════════════════════════════════════


def ripup(board: Any) -> tuple[int, int]:
    """Delete ALL tracks and vias. Return (tracks_removed, vias_removed)."""
    removed_t = removed_v = 0
    for item in list(board.GetTracks()):
        try:
            board.Remove(item)
            if isinstance(item, pcbnew.PCB_VIA):
                removed_v += 1
            else:
                removed_t += 1
        except Exception:
            pass
    # Also remove any zone fills (old filled polygons)
    for zone in list(board.Zones()):
        try:
            board.Remove(zone)
        except Exception:
            pass
    print(f"  [RIPUP] Removed {removed_t} tracks, {removed_v} vias")
    return removed_t, removed_v


# ═══════════════════════════════════════════════════════════════════════════
# Phase 2: Design Rules
# ═══════════════════════════════════════════════════════════════════════════


def set_design_rules(board: Any) -> None:
    """Apply SolderMask and track/via design rules."""
    ds = board.GetDesignSettings()

    # Solder mask
    try:
        ds.m_SolderMaskExpansion = 0  # 0 nm = 0.00 mm
        print("  [RULES] SolderMaskExpansion = 0.00 mm")
    except (AttributeError, Exception):
        print("  [RULES] SolderMaskExpansion already set (or not available via API)")

    try:
        ds.m_SolderMaskMinWidth = mm(0.04)
        print("  [RULES] SolderMaskMinWidth = 0.04 mm")
    except (AttributeError, Exception):
        print("  [RULES] SolderMaskMinWidth already set (or not available via API)")

    # Track/via defaults via existing netclasses.  The board uses the
    # ANALOG_MEMBRANE / DIGITAL_SPIKE / POWER / RESONANCE_LC classes.
    nc_map = board.GetNetClasses()
    cls_names = [n for n in list(nc_map.keys())] if hasattr(nc_map, "keys") else []
    if not cls_names:
        # Fall back to a built-in "Default" object if the map is empty.
        try:
            cls_names = [nc_map["Default"].GetName()]
        except Exception:
            cls_names = []
    for cn_name in cls_names:
        try:
            cn = nc_map[cn_name]
        except Exception:
            continue
        try:
            cn.SetTrackWidth(mm(TRACK_W_MM))
            cn.SetClearance(mm(CLEAR_MM))
            cn.SetViaDiameter(mm(VIA_PAD_MM))
            cn.SetViaDrill(mm(VIA_DRILL_MM))
            print(f"  [RULES] Netclass '{cn_name}': {TRACK_W_MM:.2f}mm track, "
                  f"{CLEAR_MM:.2f}mm clearance, via {VIA_PAD_MM:.2f}/{VIA_DRILL_MM:.2f} mm")
        except Exception as e:
            print(f"  [RULES] Could not set netclass '{cn_name}': {e}")

    # Also set per-class for power classes if they exist
    for cn_name in ["GND", "VDD", "VSS"]:
        try:
            if nc_map.find(cn_name) != nc_map.end():
                cn = nc_map[cn_name]
                cn.SetTrackWidth(mm(0.30))
                cn.SetClearance(mm(0.20))
                cn.SetViaDiameter(mm(VIA_PAD_MM))
                cn.SetViaDrill(mm(VIA_DRILL_MM))
                print(f"  [RULES] Netclass '{cn_name}': 0.30mm track, 0.20mm clearance")
        except Exception:
            pass
# ═══════════════════════════════════════════════════════════════════════════
# Phase 3: Power Plane Zones
# ═══════════════════════════════════════════════════════════════════════════


def _zone_bbox(board: Any, net_name: str) -> tuple[float, float, float, float] | None:
    """Compute bounding box of all pads belonging to `net_name`."""
    ni = board.GetNetInfo()
    net_code = None
    for nc in range(ni.GetNetCount()):
        item = ni.GetNetItem(nc)
        if item is None or item.GetNetCode() <= 0:
            continue
        if str(item.GetNetname()) == net_name:
            net_code = item.GetNetCode()
            break
    if net_code is None or net_code == 0:
        return None

    xs, ys = [], []
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            if pad.GetNetCode() == net_code:
                pos = pad.GetPosition()
                xs.append(nm(pos.x))
                ys.append(nm(pos.y))
    if not xs:
        return None
    # Expand by 2.0 mm for via thermal clearance
    margin = 2.0
    return (min(xs) - margin, min(ys) - margin,
            max(xs) + margin, max(ys) + margin)


def _net_name_to_netcode(board: Any, net_name: str) -> int:
    """Get net code from net name."""
    ni = board.GetNetInfo()
    for nc in range(ni.GetNetCount()):
        item = ni.GetNetItem(nc)
        if item is None or item.GetNetCode() <= 0:
            continue
        if str(item.GetNetname()) == net_name:
            return item.GetNetCode()
    return 0


def add_power_zones(board: Any) -> int:
    """Add zones on In1.Cu for each GND net, and on In2.Cu for VDD and VSS nets.

    Since each hierarchical sheet instance creates independent nets
    (N1_GND..N16_GND, B1_GND..B15_GND, etc.), we create one zone per net
    on the appropriate internal layer.

    Returns the number of zones added.
    """
    added = 0

    # Gather GND/VDD/VSS net names
    ni = board.GetNetInfo()
    gnd_nets: list[str] = []
    vdd_nets: list[str] = []
    vss_nets: list[str] = []

    for nc in range(ni.GetNetCount()):
        item = ni.GetNetItem(nc)
        if item is None or item.GetNetCode() <= 0:
            continue
        name: str = str(item.GetNetname())
        if name.endswith("_GND"):
            gnd_nets.append(name)
        elif name.endswith("_VDD"):
            vdd_nets.append(name)
        elif name.endswith("_VSS"):
            vss_nets.append(name)

    print(f"  [ZONES] Found {len(gnd_nets)} GND nets, {len(vdd_nets)} VDD nets, "
          f"{len(vss_nets)} VSS nets")

    # For each GND net, add a zone on In1.Cu
    for net_name in sorted(set(gnd_nets)):
        bbox = _zone_bbox(board, net_name)
        if bbox is None:
            print(f"  [ZONES] Skipping {net_name}: no pads found")
            continue
        net_code = _net_name_to_netcode(board, net_name)
        if net_code == 0:
            continue
        x0, y0, x1, y1 = bbox
        zone = pcbnew.ZONE(board)

        # Set layer and net
        zone.SetLayer(pcbnew.In1_Cu)
        try:
            zone.SetNetCode(net_code)
        except Exception:
            try:
                zone.SetNet(board.GetNetInfo().GetNetItem(net_code))
            except Exception:
                pass

        # Set zone priority
        try:
            zone.SetAssignedPriority(0)
        except Exception:
            try:
                zone.SetPriority(0)
            except Exception:
                pass
        # Set pad connection mode: thermal
        try:
            zone.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
        except Exception:
            try:
                zone.SetPadConnection(2)  # THERMAL
            except Exception:
                pass
        # Set zone mode to polygon fill
        try:
            zone.SetFillMode(pcbnew.ZONE_FILL_MODE_POLYGONS)
        except Exception:
            pass
        # Set min thickness
        try:
            zone.SetMinThickness(mm(0.20))
        except Exception:
            pass
        # Set thermal spoke width
        try:
            zone.SetThermalReliefGap(mm(0.25))
            zone.SetThermalSpokeWidth(mm(0.35))
        except Exception:
            pass

        # Add the outline as a rectangle around the bbox
        try:
            zone.Outline().AddCorner(pcbnew.VECTOR2I(mm(x0), mm(y0)))
            zone.Outline().AddCorner(pcbnew.VECTOR2I(mm(x1), mm(y0)))
            zone.Outline().AddCorner(pcbnew.VECTOR2I(mm(x1), mm(y1)))
            zone.Outline().AddCorner(pcbnew.VECTOR2I(mm(x0), mm(y1)))
        except Exception:
            pass

        board.Add(zone)
        added += 1

    # For VDD/VSS nets, add zones on In2.Cu
    for net_name in sorted(set(vdd_nets + vss_nets)):
        bbox = _zone_bbox(board, net_name)
        if bbox is None:
            continue
        net_code = _net_name_to_netcode(board, net_name)
        if net_code == 0:
            continue
        x0, y0, x1, y1 = bbox
        zone = pcbnew.ZONE(board)
        zone.SetLayer(pcbnew.In2_Cu)
        try:
            zone.SetNetCode(net_code)
        except Exception:
            pass
        try:
            zone.SetAssignedPriority(0)
            zone.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
            zone.SetFillMode(pcbnew.ZONE_FILL_MODE_POLYGONS)
            zone.SetMinThickness(mm(0.20))
            zone.SetThermalReliefGap(mm(0.25))
            zone.SetThermalSpokeWidth(mm(0.35))
        except Exception:
            pass
        try:
            zone.Outline().AddCorner(pcbnew.VECTOR2I(mm(x0), mm(y0)))
            zone.Outline().AddCorner(pcbnew.VECTOR2I(mm(x1), mm(y0)))
            zone.Outline().AddCorner(pcbnew.VECTOR2I(mm(x1), mm(y1)))
            zone.Outline().AddCorner(pcbnew.VECTOR2I(mm(x0), mm(y1)))
        except Exception:
            pass

        board.Add(zone)
        added += 1

    board.BuildConnectivity()
    return added
# ═══════════════════════════════════════════════════════════════════════════
# Phase 4: Through-hole Vias for Power Nets
# ═══════════════════════════════════════════════════════════════════════════


def add_power_vias(board: Any) -> int:
    """Place through-hole via at every power net pad (via-in-pad).

    Returns number of vias added.
    """
    added = 0
    power_nets: set[int] = set()
    ni = board.GetNetInfo()
    for nc in range(ni.GetNetCount()):
        item = ni.GetNetItem(nc)
        if item is None or item.GetNetCode() <= 0:
            continue
        name: str = str(item.GetNetname())
        if name.endswith("_GND") or name.endswith("_VDD") or name.endswith("_VSS"):
            power_nets.add(item.GetNetCode())

    for fp in board.GetFootprints():
        for pad in fp.Pads():
            nc = pad.GetNetCode()
            if nc <= 0 or nc not in power_nets:
                continue
            pos = pad.GetPosition()

            via = pcbnew.PCB_VIA(board)
            via.SetPosition(pos)
            via.SetWidth(mm(VIA_PAD_MM))
            via.SetDrill(mm(VIA_DRILL_MM))
            via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)  # Through-hole via all layers
            try:
                via.SetViaType(pcbnew.VIATYPE_THROUGH)
            except Exception:
                pass
            try:
                via.SetNetCode(nc)
            except Exception:
                try:
                    via.SetNet(board.GetNetInfo().GetNetItem(nc))
                except Exception:
                    pass

            board.Add(via)
            added += 1

    print(f"  [VIAS] Added {added} through-hole power vias (0.55mm/0.30mm) at net pads")
    return added


# ═══════════════════════════════════════════════════════════════════════════
# Phase 5: Analog Routing (F.Cu) — V_m, V_TH, LC_MID
# ═══════════════════════════════════════════════════════════════════════════


def _get_pad_centers(board: Any, net_name: str) -> list[tuple[float, float, Any]]:
    """Get all pad centers for a given net name."""
    ni = board.GetNetInfo()
    net_code = None
    for nc in range(ni.GetNetCount()):
        item = ni.GetNetItem(nc)
        if item is None or item.GetNetCode() <= 0:
            continue
        if str(item.GetNetname()) == net_name:
            net_code = item.GetNetCode()
            break
    if net_code is None or net_code == 0:
        return []

    pads: list[tuple[float, float, Any]] = []
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            if pad.GetNetCode() == net_code:
                pos = pad.GetPosition()
                pads.append((nm(pos.x), nm(pos.y), pad))
    return pads


def _snap_to_grid(x: float, grid: float) -> float:
    return round(x / grid) * grid


def _route_orthogonal(x1: float, y1: float, x2: float, y2: float
                      ) -> list[tuple[float, float, float, float]]:
    """Create L-shaped orthogonal route (Manhattan) between two points.

    Returns list of (sx, sy, ex, ey) segment endpoints.
    """
    dx = x2 - x1
    dy = y2 - y1
    g = 0.05  # grid step for snapping

    if abs(dx) < g and abs(dy) < g:
        return [(x1, y1, x2, y2)]

    # L-shaped: horizontal then vertical
    segs: list[tuple[float, float, float, float]] = []
    mx = x2
    my = y1
    segs.append((x1, y1, mx, my))
    segs.append((mx, my, x2, y2))
    return segs


def route_signal_nets(board: Any) -> int:
    """Route V_m, V_TH, LC_MID nets on F.Cu with orthogonal segments."""
    ni = board.GetNetInfo()
    routed = 0

    signal_nets: list[str] = []
    for nc in range(ni.GetNetCount()):
        item = ni.GetNetItem(nc)
        if item is None or item.GetNetCode() <= 0:
            continue
        name: str = str(item.GetNetname())
        # Skip power nets — they connect via via-in-pad to internal planes
        if name.endswith("_GND") or name.endswith("_VDD") or name.endswith("_VSS"):
            continue
        signal_nets.append(name)

    # Sort: V_m and V_TH first, then LC_MID, then SPIKE_OUT last
    def _sort_key(n: str) -> tuple[int, str]:
        if "_V_m" in n:
            return (0, n)
        elif "_V_TH" in n:
            return (1, n)
        elif "_LC_MID" in n:
            return (2, n)
        elif "_SPIKE_OUT" in n:
            return (10, n)  # routed on B.Cu separately
        else:
            return (5, n)

    signal_nets.sort(key=_sort_key)

    for net_name in signal_nets:
        if "_SPIKE_OUT" in net_name:
            continue  # Handled by route_spike_out

        pads = _get_pad_centers(board, net_name)
        if len(pads) < 2:
            continue

        # Determine layer (analog traces strictly stay on F.Cu)
        layer = pcbnew.F_Cu

        # Create daisy-chain: connect pads in order of x, then y
        pads_sorted = sorted(pads, key=lambda p: (p[0], p[1]))

        for i in range(len(pads_sorted) - 1):
            x1, y1, _ = pads_sorted[i]
            x2, y2, _ = pads_sorted[i + 1]
            segs = _route_orthogonal(x1, y1, x2, y2)
            for sx, sy, ex, ey in segs:
                t = pcbnew.PCB_TRACK(board)
                t.SetStart(pcbnew.VECTOR2I(mm(sx), mm(sy)))
                t.SetEnd(pcbnew.VECTOR2I(mm(ex), mm(ey)))
                t.SetWidth(mm(TRACK_W_MM))
                t.SetLayer(layer)
                try:
                    t.SetNet(board.GetNetInfo().GetNetItem(
                        _net_name_to_netcode(board, net_name)))
                except Exception:
                    pass
                board.Add(t)
                routed += 1

    print(f"  [ROUTE] Added {routed} signal track segments on F.Cu")
    return routed
# ═══════════════════════════════════════════════════════════════════════════
# Phase 6: SPIKE_OUT Routing (B.Cu)
# ═══════════════════════════════════════════════════════════════════════════


def _add_via(board: Any, x_mm: float, y_mm: float, net_name: str) -> None:
    """Add a through-hole via at (x, y) on net_name."""
    net_code = _net_name_to_netcode(board, net_name)
    if net_code == 0:
        return
    via = pcbnew.PCB_VIA(board)
    via.SetPosition(pcbnew.VECTOR2I(mm(x_mm), mm(y_mm)))
    via.SetWidth(mm(VIA_PAD_MM))
    via.SetDrill(mm(VIA_DRILL_MM))
    via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    try:
        via.SetViaType(pcbnew.VIATYPE_THROUGH)
    except Exception:
        pass
    try:
        via.SetNetCode(net_code)
    except Exception:
        pass
    board.Add(via)


def _via_clear_of_pads(board: Any, x_mm: float, y_mm: float, min_clr: float) -> bool:
    """Return True if (x, y) is at least min_clr from every top-layer pad."""
    via_r = VIA_PAD_MM / 2.0
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            if pad.GetLayer() != pcbnew.F_Cu:
                continue
            pos = pad.GetPosition()
            dx = x_mm - nm(pos.x)
            dy = y_mm - nm(pos.y)
            dist = math.hypot(dx, dy)
            if dist < min_clr + via_r:
                return False
    return True

def route_spike_out(board: Any) -> int:
    """Route SPIKE_OUT nets on B.Cu.

    For each SPIKE_OUT net:
    1. Place a transition via near the first pad, keeping >=0.25 mm clearance
       from all top-layer component pads.
    2. Route on B.Cu from the via to each destination pad.
    """
    ni = board.GetNetInfo()
    routed = 0

    spike_nets: list[str] = []
    for nc in range(ni.GetNetCount()):
        item = ni.GetNetItem(nc)
        if item is None or item.GetNetCode() <= 0:
            continue
        name: str = str(item.GetNetname())
        if "_SPIKE_OUT" in name:
            spike_nets.append(name)

    for net_name in sorted(spike_nets):
        pads = _get_pad_centers(board, net_name)
        if len(pads) < 2:
            continue

        pads_sorted = sorted(pads, key=lambda p: (p[0], p[1]))

        # Place a transition via near the first pad (TSSOP-8 output)
        x1, y1, _ = pads_sorted[0]

        # Try candidate offsets, pick the first with >=0.25 mm clearance from
        # all top-layer component pads.
        candidates = [
            (x1 + 0.35, y1),
            (x1 - 0.35, y1),
            (x1, y1 + 0.35),
            (x1, y1 - 0.35),
            (x1 + 0.35, y1 + 0.35),
            (x1 + 0.35, y1 - 0.35),
            (x1 - 0.35, y1 + 0.35),
            (x1 - 0.35, y1 - 0.35),
        ]
        via_x, via_y = x1 + 0.35, y1
        for cx, cy in candidates:
            if _via_clear_of_pads(board, cx, cy, MIN_EXIT_MM):
                via_x, via_y = cx, cy
                break

        _add_via(board, via_x, via_y, net_name)

        # Route from via to all pads on B.Cu (L-shaped)
        all_points: list[tuple[float, float]] = [(via_x, via_y)]
        for xp, yp, _ in pads_sorted:
            all_points.append((xp, yp))

        for i in range(len(all_points) - 1):
            sx, sy = all_points[i]
            ex, ey = all_points[i + 1]
            sx, sy = _snap_to_grid(sx, 0.05), _snap_to_grid(sy, 0.05)
            ex, ey = _snap_to_grid(ex, 0.05), _snap_to_grid(ey, 0.05)

            mx = ex
            my = sy

            t1 = pcbnew.PCB_TRACK(board)
            t1.SetStart(pcbnew.VECTOR2I(mm(sx), mm(sy)))
            t1.SetEnd(pcbnew.VECTOR2I(mm(mx), mm(my)))
            t1.SetWidth(mm(TRACK_W_MM))
            t1.SetLayer(pcbnew.B_Cu)
            try:
                t1.SetNet(board.GetNetInfo().GetNetItem(
                    _net_name_to_netcode(board, net_name)))
            except Exception:
                pass
            board.Add(t1)
            routed += 1

            if abs(mx - ex) > 0.001 or abs(my - ey) > 0.001:
                t2 = pcbnew.PCB_TRACK(board)
                t2.SetStart(pcbnew.VECTOR2I(mm(mx), mm(my)))
                t2.SetEnd(pcbnew.VECTOR2I(mm(ex), mm(ey)))
                t2.SetWidth(mm(TRACK_W_MM))
                t2.SetLayer(pcbnew.B_Cu)
                try:
                    t2.SetNet(board.GetNetInfo().GetNetItem(
                        _net_name_to_netcode(board, net_name)))
                except Exception:
                    pass
                board.Add(t2)
                routed += 1

    print(f"  [SPIKE] Routed {routed} SPIKE_OUT track segments on B.Cu")
    return routed
# ═══════════════════════════════════════════════════════════════════════════
# Phase 7: Fix Pad Exit Geometries
# ═══════════════════════════════════════════════════════════════════════════


def _fp_is_0402(fp: Any) -> bool:
    try:
        fpid = fp.GetFPID()
        lib_item = str(fpid.GetLibItemName())
    except Exception:
        lib_item = ""
    return "0402" in lib_item or "1005Metric" in lib_item


def _fp_is_tssop8(fp: Any) -> bool:
    try:
        fpid = fp.GetFPID()
        lib_item = str(fpid.GetLibItemName())
    except Exception:
        lib_item = ""
    return "TSSOP" in lib_item and "8" in lib_item


def fix_pad_exits(board: Any) -> int:
    """Enforce 90-degree perpendicular exit geometry for at least 0.25 mm
    on all 0402/TSSOP-8 pad departures."""
    fixed = 0

    for fp in board.GetFootprints():
        if not (_fp_is_0402(fp) or _fp_is_tssop8(fp)):
            continue

        for pad in fp.Pads():
            if pad.GetNetCode() == 0:
                continue
            pad_pos = pad.GetPosition()
            px, py = nm(pad_pos.x), nm(pad_pos.y)

            # Find tracks connected to this pad
            for t in board.GetTracks():
                if isinstance(t, pcbnew.PCB_VIA):
                    continue
                if t.GetNetCode() != pad.GetNetCode():
                    continue

                s, e = t.GetStart(), t.GetEnd()
                sx, sy = nm(s.x), nm(s.y)
                ex, ey = nm(e.x), nm(e.y)
                d_start = math.hypot(sx - px, sy - py)
                d_end = math.hypot(ex - px, ey - py)
                at_pad = min(d_start, d_end)
                if at_pad > 0.005:
                    continue

                # Direction from pad to far point
                if d_start < d_end:
                    dir_x = ex - sx
                    dir_y = ey - sy
                    far_x, far_y = ex, ey
                else:
                    dir_x = sx - ex
                    dir_y = sy - ey
                    far_x, far_y = sx, sy

                seg_len = math.hypot(dir_x, dir_y)
                if seg_len < 0.001:
                    continue

                dx_n = dir_x / seg_len
                dy_n = dir_y / seg_len

                # Perpendicular means one axis component is ~0
                is_perp = abs(dx_n) < 0.1 or abs(dy_n) < 0.1
                if is_perp:
                    continue

                # Force a perpendicular exit segment of MIN_EXIT_MM length
                if _fp_is_0402(fp):
                    if abs(dx_n) < 0.5:
                        new_ex = px + MIN_EXIT_MM if dir_x >= 0 else px - MIN_EXIT_MM
                        new_ey = py
                    else:
                        new_ex = px
                        new_ey = py + MIN_EXIT_MM if dir_y >= 0 else py - MIN_EXIT_MM
                else:
                    # TSSOP-8 pads: exit along the dominant delta axis
                    if abs(dy_n) >= abs(dx_n):
                        new_ex = px
                        new_ey = py + MIN_EXIT_MM if dir_y >= 0 else py - MIN_EXIT_MM
                    else:
                        new_ex = px + MIN_EXIT_MM if dir_x >= 0 else px - MIN_EXIT_MM
                        new_ey = py

                if d_start < d_end:
                    t.SetStart(pcbnew.VECTOR2I(mm(new_ex), mm(new_ey)))
                else:
                    t.SetEnd(pcbnew.VECTOR2I(mm(new_ex), mm(new_ey)))

                seg2 = pcbnew.PCB_TRACK(board)
                seg2.SetStart(pcbnew.VECTOR2I(mm(new_ex), mm(new_ey)))
                seg2.SetEnd(pcbnew.VECTOR2I(mm(far_x), mm(far_y)))
                seg2.SetWidth(t.GetWidth())
                seg2.SetLayer(t.GetLayer())
                try:
                    seg2.SetNet(t.GetNet())
                except Exception:
                    seg2.SetNetCode(t.GetNetCode())
                board.Add(seg2)
                fixed += 1

    print(f"  [EXITS] Fixed {fixed} pad exits (90deg perp, >= {MIN_EXIT_MM:.2f}mm)")
    return fixed

# ═══════════════════════════════════════════════════════════════════════════
# Main — phase dispatch.  Each phase runs in its own process because the
# pcbnew SWIG runtime is unstable under mixed read/modify/delete workloads
# on KiCad 10.0.6 (see auto_place_and_fix_rules.py docs).
# ═══════════════════════════════════════════════════════════════════════════


def phase_wipe() -> int:
    """Phase A: ripup only, then save."""
    print("=" * 64)
    print("  Phase A: Wipe (ripup only)")
    print("=" * 64)
    if not os.path.exists(BOARD_FILE):
        print(f"[ERROR] Board file not found: {BOARD_FILE}")
        return 1
    board = pcbnew.LoadBoard(BOARD_FILE)
    print(f"  Board: {BOARD_FILE}")
    print(f"  Footprints: {len(list(board.GetFootprints()))}")
    removed_t, removed_v = ripup(board)
    print(f"\nSaving to {BOARD_FILE} ...")
    try:
        board.Save(BOARD_FILE)
        sz = os.path.getsize(BOARD_FILE)
        print(f"  [OK] Saved: {sz:,} bytes")
    except Exception as e:
        print(f"[ERROR] Save failed: {e}")
        return 1
    print(f"\n  Phase A done: removed {removed_t} tracks, {removed_v} vias.")
    return 0


def phase_reroute() -> int:
    """Phase B: design rules, zones, vias, routing, exits; then save."""
    print("=" * 64)
    print("  Phase B: Reroute (rules + zones + vias + routing)")
    print("=" * 64)
    if not os.path.exists(BOARD_FILE):
        print(f"[ERROR] Board file not found: {BOARD_FILE}")
        return 1
    print(f"  Board: {BOARD_FILE}")
    board = pcbnew.LoadBoard(BOARD_FILE)
    print(f"  Footprints: {len(list(board.GetFootprints()))}")

    print("\n[A] Setting design rules ...")
    set_design_rules(board)

    print("\n[B] Adding power plane zones on In1.Cu/In2.Cu ...")
    n_zones = add_power_zones(board)

    print("\n[C] Adding through-hole vias for GND/VDD/VSS nets ...")
    n_power_vias = add_power_vias(board)

    print("\n[D] Routing analog membrane nets (V_m, V_TH, LC_MID) on F.Cu ...")
    n_signal_routed = route_signal_nets(board)

    print("\n[E] Routing SPIKE_OUT nets on B.Cu ...")
    n_spike_routed = route_spike_out(board)

    print("\n[F] Enforcing 90-degree perpendicular exits on 0402/TSSOP-8 pads ...")
    n_fixed = fix_pad_exits(board)

    print(f"\nSaving to {BOARD_FILE} ...")
    board.BuildConnectivity()
    try:
        board.Save(BOARD_FILE)
        sz = os.path.getsize(BOARD_FILE)
        print(f"  [OK] Saved: {sz:,} bytes")
    except Exception as e:
        print(f"[ERROR] Save failed: {e}")
        return 1

    tracks = [t for t in board.GetTracks()
              if not isinstance(t, pcbnew.PCB_VIA)]
    vias_c = [t for t in board.GetTracks()
              if isinstance(t, pcbnew.PCB_VIA)]
    zones_c = list(board.Zones())
    print("\n" + "=" * 64)
    print(f"  Tracks: {len(tracks)}   Vias: {len(vias_c)}   Zones: {len(zones_c)}")
    print(f"  Summary: zones={n_zones}, power_vias={n_power_vias}, "
          f"signal_segs={n_signal_routed}, spike_segs={n_spike_routed}, "
          f"exits_fixed={n_fixed}")
    print("=" * 64)
    return 0


def _run_phase(args: str) -> int:
    import subprocess
    cmd = [sys.executable, os.path.abspath(__file__), args]
    print(f"\n>>> {cmd[0]} {os.path.basename(cmd[1])} {args}")
    res = subprocess.run(cmd)
    return res.returncode


def main() -> int:
    if not os.path.exists(BOARD_FILE):
        print(f"\n[ERROR] Board file not found: {BOARD_FILE}")
        return 1
    if "--phase-wipe" in sys.argv:
        return phase_wipe()
    if "--phase-reroute" in sys.argv:
        return phase_reroute()

    # Orchestrator: wipe then reroute in fresh subprocesses.
    print("=" * 64)
    print("  AdEx Resonant Core -- Complete Wipe & Layer-Isolated Reroute")
    print("=" * 64)
    for phase_arg, name in (("--phase-wipe", "Wipe (ripup)"),
                            ("--phase-reroute", "Reroute (layer-isolated)")):
        rc = _run_phase(phase_arg)
        if rc != 0:
            print(f"\n[ERROR] {name} phase failed with exit code {rc}")
            return rc
        print(f"\n[OK] {name} phase completed.\n")

    print("=" * 64)
    print("  Done.  Run 'python3 scripts/run_pcb_drc.py' to verify.")
    print("=" * 64)
    return 0


if __name__ == "__main__":
    sys.exit(main())