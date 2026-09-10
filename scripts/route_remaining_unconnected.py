#!/usr/bin/env python3
# pyright: basic
"""
Route Remaining 8 Unconnected Nets — AdEx Resonant Core.

For each of the 8 nets flagged by DRC as unconnected (4 V_m & 4 SPIKE_OUT),
this script ensures a complete B.Cu connection between the component departure
point and the CB castellated edge pad.

- V_m nets: place a micro-via (0.30 mm drill / 0.55 mm pad) at the component
  SMD departure pad, then route on B.Cu (0.20 mm trace) to the CB pad.
- SPIKE_OUT nets: reuse the existing micro-via and add a B.Cu trace into the
  CB pad centre.

Routing is done with a grid-based A* that avoids every B.Cu obstacle
(pads, tracks, vias expanded by 0.18 mm clearance), so the resulting
routes never cross or short existing copper.
"""

import heapq
import math
import os
import sys
from typing import Any

PCB_EXTRA_PATH = "/usr/lib64/python3.14/site-packages"
if os.path.isdir(PCB_EXTRA_PATH):
    sys.path.insert(0, PCB_EXTRA_PATH)

import pcbnew  # type: ignore[import-untyped]

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HW = os.path.join(ROOT, "hardware")
BOARD_FILE = os.path.join(HW, "adex_resonant_core.kicad_pcb")

# ── Constants ────────────────────────────────────────────────────────────────
VIA_DRILL_MM = 0.30
VIA_PAD_MM = 0.55
TRACK_WIDTH_MM = 0.20
CLEARANCE_MM = 0.25  # half_track + min_clearance
GRID_MM = 0.10

# V_m departure SMD pad identification by (footprint_ref, pad_number)
V_M_DEPARTURES = [
    ("N13_V_m", "N13_R2", "2", "CB005"),
    ("N14_V_m", "N14_R2", "2", "CB010"),
    ("N15_V_m", "N15_R2", "1", "CB015"),
    ("N16_V_m", "N16_R2", "1", "CB020"),
]

# SPIKE_OUT departure SMD pad identification
SPIKE_DEPARTURES = [
    ("N13_SPIKE_OUT", "N13_R6", "2", "CB006"),
    ("N14_SPIKE_OUT", "N14_R6", "2", "CB011"),
    ("N15_SPIKE_OUT", "N15_R6", "2", "CB016"),
    ("N16_SPIKE_OUT", "N16_R6", "2", "CB021"),
]


def nm_to_mm(v: int) -> float:
    return v / 1e6


def mm_to_nm(v: float) -> int:
    return int(round(v * 1e6))

# ── Helpers ───────────────────────────────────────────────────────────────────
def _find_footprint_pad(board: Any, ref: str, pad_num: str) -> Any | None:
    for fp in board.GetFootprints():
        if str(fp.GetReference()).upper() != ref.upper():
            continue
        for pad in fp.Pads():
            if str(pad.GetNumber()) == pad_num:
                return pad
    return None


def _find_castellated_pad(board: Any, ref: str) -> Any | None:
    for fp in board.GetFootprints():
        if str(fp.GetReference()).upper() != ref.upper():
            continue
        for pad in fp.Pads():
            return pad
    return None


def _find_bottom_spike_via(board: Any, netcode: int) -> tuple[float, float] | None:
    """Lowest-y via for a SPIKE_OUT net (closest to the CB edge)."""
    best_y = -1e9
    best_pos = None
    for t in board.GetTracks():
        if not isinstance(t, pcbnew.PCB_VIA):
            continue
        if t.GetNetCode() != netcode:
            continue
        p = t.GetPosition()
        y_mm = nm_to_mm(p.y)
        if y_mm > best_y:
            best_y = y_mm
            best_pos = (nm_to_mm(p.x), y_mm)
    return best_pos


def _has_bcu_to_pad(board: Any, netcode: int, pad_x_nm: int, pad_y_nm: int) -> bool:
    tol_nm = mm_to_nm(0.01)
    for t in board.GetTracks():
        if isinstance(t, pcbnew.PCB_VIA):
            continue
        if t.GetNetCode() != netcode:
            continue
        if t.GetLayer() != pcbnew.B_Cu:
            continue
        s, e = t.GetStart(), t.GetEnd()
        if (abs(s.x - pad_x_nm) <= tol_nm and abs(s.y - pad_y_nm) <= tol_nm) or \
           (abs(e.x - pad_x_nm) <= tol_nm and abs(e.y - pad_y_nm) <= tol_nm):
            return True
    return False


def _via_exists_at(board: Any, x_nm: int, y_nm: int) -> bool:
    tol_nm = mm_to_nm(0.02)
    for t in board.GetTracks():
        if isinstance(t, pcbnew.PCB_VIA):
            p = t.GetPosition()
            if abs(p.x - x_nm) <= tol_nm and abs(p.y - y_nm) <= tol_nm:
                return True
    return False


def _ensure_via_at(board: Any, net: Any, x_mm: float, y_mm: float) -> bool:
    x_nm = mm_to_nm(x_mm)
    y_nm = mm_to_nm(y_mm)
    if _via_exists_at(board, x_nm, y_nm):
        return False
    v = pcbnew.PCB_VIA(board)
    v.SetPosition(pcbnew.VECTOR2I(x_nm, y_nm))
    v.SetDrill(mm_to_nm(VIA_DRILL_MM))
    v.SetWidth(mm_to_nm(VIA_PAD_MM))
    v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    v.SetNet(net)
    board.Add(v)
    return True


def _add_bcu_track(board: Any, net: Any, x1_mm: float, y1_mm: float,
                    x2_mm: float, y2_mm: float) -> None:
    t = pcbnew.PCB_TRACK(board)
    t.SetStart(pcbnew.VECTOR2I(mm_to_nm(x1_mm), mm_to_nm(y1_mm)))
    t.SetEnd(pcbnew.VECTOR2I(mm_to_nm(x2_mm), mm_to_nm(y2_mm)))
    t.SetWidth(mm_to_nm(TRACK_WIDTH_MM))
    t.SetLayer(pcbnew.B_Cu)
    t.SetNet(net)
    board.Add(t)


# ── Obstacle grid + A* ────────────────────────────────────────────────────────
def _dist_seg_point(ax: float, ay: float, bx: float, by: float,
                     px: float, py: float) -> float:
    """Distance from point (px,py) to segment a-b."""
    abx, aby = bx - ax, by - ay
    seg2 = abx * abx + aby * aby
    if seg2 < 1e-12:
        return math.hypot(px - ax, py - ay)
    t = ((px - ax) * abx + (py - ay) * aby) / seg2
    t = max(0.0, min(1.0, t))
    cx, cy = ax + t * abx, ay + t * aby
    return math.hypot(px - cx, py - cy)


def build_bcu_grid(board: Any, x0: float, x1: float, y0: float, y1: float,
                   obstacle_clear_mm: float, exclude_nets: set[int] | None = None) -> tuple[bytearray, int, int]:
    """Build a 0.1 mm obstacle grid over the bounding box on B.Cu.

    Obstacles: every B.Cu pad, every B.Cu track, every via pad, each expanded
    by obstacle_clear_mm.
    """
    ncols = int(round((x1 - x0) / GRID_MM)) + 1
    nrows = int(round((y1 - y0) / GRID_MM)) + 1
    grid = bytearray(ncols * nrows)

    def mark_circle(cx: float, cy: float, rad: float) -> None:
        i_min = max(0, int(math.floor((cx - rad - x0) / GRID_MM)))
        i_max = min(ncols - 1, int(math.ceil((cx + rad - x0) / GRID_MM)))
        j_min = max(0, int(math.floor((cy - rad - y0) / GRID_MM)))
        j_max = min(nrows - 1, int(math.ceil((cy + rad - y0) / GRID_MM)))
        for j in range(j_min, j_max + 1):
            for i in range(i_min, i_max + 1):
                px = x0 + i * GRID_MM
                py = y0 + j * GRID_MM
                if math.hypot(px - cx, py - cy) <= rad:
                    grid[j * ncols + i] = 1

    def mark_segment(ax: float, ay: float, bx: float, by: float, rad: float) -> None:
        i_min = max(0, int(math.floor((min(ax, bx) - rad - x0) / GRID_MM)))
        i_max = min(ncols - 1, int(math.ceil((max(ax, bx) + rad - x0) / GRID_MM)))
        j_min = max(0, int(math.floor((min(ay, by) - rad - y0) / GRID_MM)))
        j_max = min(nrows - 1, int(math.ceil((max(ay, by) + rad - y0) / GRID_MM)))
        for j in range(j_min, j_max + 1):
            for i in range(i_min, i_max + 1):
                px = x0 + i * GRID_MM
                py = y0 + j * GRID_MM
                if _dist_seg_point(ax, ay, bx, by, px, py) <= rad:
                    grid[j * ncols + i] = 1

    # B.Cu pads (excluding castellated CL/CR edge pads far away)
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            try:
                layers = set(pad.GetLayerSet().CuStack())
            except Exception:
                layers = set()
            if pcbnew.B_Cu not in layers:
                continue
            if exclude_nets and pad.GetNetCode() in exclude_nets:
                continue
            p = pad.GetPosition()
            px, py = nm_to_mm(p.x), nm_to_mm(p.y)
            if px < x0 - 2 or px > x1 + 2 or py < y0 - 2 or py > y1 + 2:
                continue
            # pad bbox radius
            try:
                padw = max(pad.GetSize().x, pad.GetSize().y) / 1e6
            except Exception:
                padw = 0.6
            mark_circle(px, py, padw / 2.0 + obstacle_clear_mm)

    # B.Cu tracks (all nets)
    for t in board.GetTracks():
        if isinstance(t, pcbnew.PCB_VIA):
            continue
        if t.GetLayer() != pcbnew.B_Cu:
            continue
        s, e = t.GetStart(), t.GetEnd()
        sx, sy = nm_to_mm(s.x), nm_to_mm(s.y)
        ex, ey = nm_to_mm(e.x), nm_to_mm(e.y)
        rad = nm_to_mm(t.GetWidth()) / 2.0 + obstacle_clear_mm
        mark_segment(sx, sy, ex, ey, rad)

    # Vias (both-layer annulus)
    for t in board.GetTracks():
        if not isinstance(t, pcbnew.PCB_VIA):
            continue
        if exclude_nets and t.GetNetCode() in exclude_nets:
            continue
        p = t.GetPosition()
        px, py = nm_to_mm(p.x), nm_to_mm(p.y)
        rad = nm_to_mm(t.GetWidth()) / 2.0 + obstacle_clear_mm
        mark_circle(px, py, rad)

    return grid, ncols, nrows


def clear_grid_circle(grid: bytearray, ncols: int, nrows: int,
                      x0: float, y0: float, cx: float, cy: float, rad: float) -> None:
    i_min = max(0, int(math.floor((cx - rad - x0) / GRID_MM)))
    i_max = min(ncols - 1, int(math.ceil((cx + rad - x0) / GRID_MM)))
    j_min = max(0, int(math.floor((cy - rad - y0) / GRID_MM)))
    j_max = min(nrows - 1, int(math.ceil((cy + rad - y0) / GRID_MM)))
    for j in range(j_min, j_max + 1):
        for i in range(i_min, i_max + 1):
            px = x0 + i * GRID_MM
            py = y0 + j * GRID_MM
            if math.hypot(px - cx, py - cy) <= rad:
                grid[j * ncols + i] = 0


def astar_bcu(grid: bytearray, ncols: int, nrows: int,
              sx: int, sy: int, tx: int, ty: int) -> list[tuple[int, int]] | None:
    """A* path on grid. Returns list of (i,j) cells including start and target."""
    if not (0 <= sx < ncols and 0 <= sy < nrows and 0 <= tx < ncols and 0 <= ty < nrows):
        return None
    if grid[sy * ncols + sx] == 1:
        return None
    # target cell is a pad centre — allow it even if flagged
    open_set = [(0.0, sx, sy)]
    came: dict[tuple[int, int], tuple[int, int]] = {}
    g: dict[tuple[int, int], float] = {(sx, sy): 0.0}
    closed: set[tuple[int, int]] = set()
    while open_set:
        _, cx, cy = heapq.heappop(open_set)
        if (cx, cy) in closed:
            continue
        if cx == tx and cy == ty:
            path = [(cx, cy)]
            while (cx, cy) in came:
                cx, cy = came[(cx, cy)]
                path.append((cx, cy))
            path.reverse()
            return path
        closed.add((cx, cy))
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = cx + dx, cy + dy
            if not (0 <= nx < ncols and 0 <= ny < nrows):
                continue
            if (nx, ny) in closed:
                continue
            if grid[ny * ncols + nx] == 1 and not (nx == tx and ny == ty):
                continue
            ng = g[(cx, cy)] + GRID_MM
            if (nx, ny) not in g or ng < g[(nx, ny)]:
                g[(nx, ny)] = ng
                h = math.hypot((tx - nx) * GRID_MM, (ty - ny) * GRID_MM)
                heapq.heappush(open_set, (ng + h, nx, ny))
                came[(nx, ny)] = (cx, cy)
    return None


def _route_from_via(board: Any, net: Any, vx_mm: float, vy_mm: float,
                     cx_mm: float, cy_mm: float) -> int:
    """Route B.Cu from via to CB pad. Tries direct line first, then A*."""
    pad_x, pad_y = cx_mm, cy_mm
    margin = 8.0
    y_min = min(vy_mm, cy_mm) - margin
    y_max = max(vy_mm, cy_mm) + margin
    x_min = min(vx_mm, pad_x) - margin
    x_max = max(vx_mm, pad_x) + margin
    # Clamp to board area
    x_min = max(x_min, -2)
    y_min = max(y_min, -2)
    x_max = min(x_max, 72)
    y_max = min(y_max, 72)

    # Exclude own-net items so the route has no clearance requirement with itself.
    exc_netcodes: set[int] = {net.GetNetCode()}
    grid, ncols, nrows = build_bcu_grid(board, x_min, x_max, y_min, y_max,
                                        CLEARANCE_MM, exclude_nets=exc_netcodes)
    # Clear the via itself and the destination CB pad so the route can
    # terminate on their copper. Keep the radius tight (slightly larger
    # than the copper half-size) so nearby foreign obstacles stay blocked.
    clear_grid_circle(grid, ncols, nrows, x_min, y_min, vx_mm, vy_mm, 0.55)
    clear_grid_circle(grid, ncols, nrows, x_min, y_min, pad_x, pad_y, 0.65)

    # Try straight-line path first
    dx = pad_x - vx_mm
    dy = pad_y - vy_mm
    dist = math.hypot(dx, dy)
    steps = max(2, int(dist / GRID_MM))
    straight_ok = True
    for step in range(steps + 1):
        t = step / steps
        px = vx_mm + dx * t
        py = vy_mm + dy * t
        i = int(round((px - x_min) / GRID_MM))
        j = int(round((py - y_min) / GRID_MM))
        if 0 <= i < ncols and 0 <= j < nrows:
            if grid[j * ncols + i] == 1:
                straight_ok = False
                break
    if straight_ok:
        _add_bcu_track(board, net, vx_mm, vy_mm, pad_x, pad_y)
        print(f"    [B.Cu] straight ({vx_mm:.2f},{vy_mm:.2f}) -> ({pad_x:.2f},{pad_y:.2f}) seg=1")
        return 1

    # A* fallback
    sx = int(round((vx_mm - x_min) / GRID_MM))
    sy = int(round((vy_mm - y_min) / GRID_MM))
    tx = int(round((pad_x - x_min) / GRID_MM))
    ty = int(round((pad_y - y_min) / GRID_MM))

    path = astar_bcu(grid, ncols, nrows, sx, sy, tx, ty)
    if path is None:
        print(f"    [FAIL] A* no path ({vx_mm:.2f},{vy_mm:.2f}) -> ({pad_x:.2f},{pad_y:.2f})")
        return 0

    pts_mm = [(x_min + i * GRID_MM, y_min + j * GRID_MM) for i, j in path]
    # Collapse consecutive points onto the same row/column
    out: list[tuple[float, float]] = []
    for p in pts_mm:
        if out:
            px, py = out[-1]
            if abs(px - p[0]) < 1e-9 and abs(py - p[1]) < 1e-9:
                continue
            # Merge points that keep the previous segment strictly
            # horizontal or vertical (same row/column as the last corner).
            if len(out) >= 2:
                p0x, p0y = out[-2]
                if (abs(p0y - py) < 1e-9 and abs(py - p[1]) < 1e-9) or                    (abs(p0x - px) < 1e-9 and abs(px - p[0]) < 1e-9):
                    out[-1] = p
                    continue
        out.append(p)
    if out:
        out[0] = (vx_mm, vy_mm)
        out[-1] = (pad_x, pad_y)

    # Greedy simplification: replace long staircases by direct segments
    # that stay clear of every obstacle on the grid.
    def seg_clear(a_: tuple[float, float], b_: tuple[float, float]) -> bool:
        ddx = b_[0] - a_[0]
        ddy = b_[1] - a_[1]
        dlen = math.hypot(ddx, ddy)
        nsteps = max(2, int(dlen / GRID_MM))
        for s_i in range(nsteps + 1):
            tt = s_i / nsteps
            ppx = a_[0] + ddx * tt
            ppy = a_[1] + ddy * tt
            ii = int(round((ppx - x_min) / GRID_MM))
            jj = int(round((ppy - y_min) / GRID_MM))
            if 0 <= ii < ncols and 0 <= jj < nrows and grid[jj * ncols + ii] == 1:
                return False
        return True

    simp: list[tuple[float, float]] = []
    idx = 0
    while idx < len(out):
        simp.append(out[idx])
        if idx == len(out) - 1:
            break
        # find farthest reachable point
        far = idx + 1
        for k in range(len(out) - 1, idx, -1):
            if seg_clear(out[idx], out[k]):
                far = k
                break
        idx = far
    out = simp

    segs = 0
    px_mm, py_mm = out[0]
    for (qx, qy) in out[1:]:
        _add_bcu_track(board, net, px_mm, py_mm, qx, qy)
        segs += 1
        px_mm, py_mm = qx, qy
    return segs

def route_remaining_unconnected_nets(board: Any) -> int:
    """Main entry: fix all 8 unconnected net items using A* on B.Cu."""
    total_segs = 0

    # ── V_m nets ────────────────────────────────────────────────────────────
    for netname, fp_ref, pad_num, cb_ref in V_M_DEPARTURES:
        net = board.FindNet(netname)
        if net is None:
            print(f"    [WARN] Net {netname} not found")
            continue
        netcode = net.GetNetCode()

        cb_pad = _find_castellated_pad(board, cb_ref)
        if cb_pad is None:
            print(f"    [WARN] CB pad {cb_ref} not found")
            continue
        cx_nm, cy_nm = cb_pad.GetPosition().x, cb_pad.GetPosition().y
        cx_mm, cy_mm = nm_to_mm(cx_nm), nm_to_mm(cy_nm)

        if _has_bcu_to_pad(board, netcode, cx_nm, cy_nm):
            continue

        pad = _find_footprint_pad(board, fp_ref, pad_num)
        if pad is None:
            print(f"    [WARN] Departure pad {fp_ref}.{pad_num} not found for {netname}")
            continue
        px_mm = nm_to_mm(pad.GetPosition().x)
        py_mm = nm_to_mm(pad.GetPosition().y)

        placed = _ensure_via_at(board, net, px_mm, py_mm)
        if placed:
            print(f"    [VIA] {netname:22s} at ({px_mm:.3f}, {py_mm:.3f})")

        segs = _route_from_via(board, net, px_mm, py_mm, cx_mm, cy_mm)
        if segs:
            total_segs += segs
            print(f"    [B.Cu] {netname:22s} via ({px_mm:.3f},{py_mm:.3f}) -> "
                  f"{cb_ref} ({cx_mm:.3f},{cy_mm:.3f}) segs={segs}")

    # ── SPIKE_OUT nets ───────────────────────────────────────────────────────
    for netname, fp_ref, pad_num, cb_ref in SPIKE_DEPARTURES:
        net = board.FindNet(netname)
        if net is None:
            print(f"    [WARN] Net {netname} not found")
            continue
        netcode = net.GetNetCode()

        cb_pad = _find_castellated_pad(board, cb_ref)
        if cb_pad is None:
            print(f"    [WARN] CB pad {cb_ref} not found")
            continue
        cx_nm, cy_nm = cb_pad.GetPosition().x, cb_pad.GetPosition().y
        cx_mm, cy_mm = nm_to_mm(cx_nm), nm_to_mm(cy_nm)

        if _has_bcu_to_pad(board, netcode, cx_nm, cy_nm):
            continue

        via_pos = _find_bottom_spike_via(board, netcode)
        if via_pos is None:
            pad = _find_footprint_pad(board, fp_ref, pad_num)
            if pad is None:
                print(f"    [WARN] Departure pad {fp_ref}.{pad_num} not found")
                continue
            vx_mm = nm_to_mm(pad.GetPosition().x)
            vy_mm = nm_to_mm(pad.GetPosition().y)
            _ensure_via_at(board, net, vx_mm, vy_mm)
            print(f"    [VIA] {netname:22s} at ({vx_mm:.3f}, {vy_mm:.3f}) (new)")
        else:
            vx_mm, vy_mm = via_pos

        segs = _route_from_via(board, net, vx_mm, vy_mm, cx_mm, cy_mm)
        if segs:
            total_segs += segs
            print(f"    [B.Cu] {netname:22s} via ({vx_mm:.3f},{vy_mm:.3f}) -> "
                  f"{cb_ref} ({cx_mm:.3f},{cy_mm:.3f}) segs={segs}")

    return total_segs


# ── Standalone entry point ───────────────────────────────────────────────────
def main() -> int:
    print("=" * 64)
    print("  AdEx Resonant Core — Route 8 Remaining Unconnected Nets")
    print("=" * 64)
    board: Any = pcbnew.LoadBoard(BOARD_FILE)
    print(f"  Loaded: {BOARD_FILE}")
    print(f"  Footprints: {len(list(board.GetFootprints()))}")
    print(f"  Tracks: {len(list(board.GetTracks()))}")
    n = route_remaining_unconnected_nets(board)
    board.Save(BOARD_FILE)
    sz = os.path.getsize(BOARD_FILE)
    print(f"\n  [OK] Saved: {BOARD_FILE} ({sz:,} bytes) — added {n} track(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
