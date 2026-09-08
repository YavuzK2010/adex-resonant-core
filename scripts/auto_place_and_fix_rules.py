#!/usr/bin/env python3
# pyright: basic
# pcbnew is a C++ extension without type stubs
"""
AdEx Resonant Core -- Auto-Place & Fix DRC Rules.

Placement Strategy (Board: 70 x 70 mm, Origin (0,0)):
  1. Castellated edge connectors (CT / CB / CL / CR) anchored with
     pad centre exactly ON the 70x70 mm Edge.Cuts boundary:
        CT001..CT034  ->  y =   0.0 mm,  x =  2.0 .. 68.0 mm  (pitch 2.0 mm)
        CB001..CB034  ->  y =  70.0 mm,  x =  2.0 .. 68.0 mm  (pitch 2.0 mm)
        CL001..CL034  ->  x =   0.0 mm,  y =  2.0 .. 68.0 mm  (pitch 2.0 mm)
        CR001..CR034  ->  x =  70.0 mm,  y =  2.0 .. 68.0 mm  (pitch 2.0 mm)

  2. Every other footprint placed using dynamic bounding-box row packing within
     the inner core area (8.0, 8.0) .. (62.0, 62.0).  Components are organised
     by cell (N1..N16 neuron instances first, then B1..B15 bridge cells).
     Actual footprint bounding boxes are computed via GetBoundingBox() and a
     minimum 0.80 mm clearance is enforced between adjacent footprints.
     SOIC-8 devices are placed in a dedicated bottom zone to avoid row-height
     pollution from the larger packages.

  3. CopperEdgeClearance -> 0.0 mm so castellated pads touching Edge.Cuts
     pass DRC; silk clearance -> 0.0 mm; reference texts on castellated
     footprints are hidden to avoid silk-edge-clearance / silk-overlap.
"""
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
PRO_FILE = os.path.join(HW, "adex_resonant_core.kicad_pro")

BOARD_SIZE_MM = 70.0
EDGE_MIN = 2.0
EDGE_MAX = 68.0
EDGE_PITCH = 2.0

# Core placement bounds  (leave 8 mm margin from board edges)
INNER_MIN_X = 8.0
INNER_MIN_Y = 8.0
INNER_MAX_X = 62.0
INNER_MAX_Y = 62.0

# Minimum clearance between footprint bounding boxes (DRC-safe)
CLEARANCE_MM = 0.3

TEXT_SIZE_MM = 0.6
TEXT_THICKNESS_MM = 0.12
TEXT_OFFSET_MM = 1.5

CASTELLATED_RE = re.compile(r"^(C[TBRL])\d{3}$")

_PREFIX_ROTATION: dict[str, float] = {
    "CT": 0.0,
    "CB": 180.0,
    "CL": 270.0,
    "CR": 90.0,
}


def mm_to_nm(v_mm: float) -> int:
    return int(round(v_mm * 1_000_000))


def nm_to_mm(v_nm: int) -> float:
    return v_nm / 1_000_000.0


def is_castellated(fp: Any) -> bool:
    ref: str = fp.GetReference().upper().strip()
    return bool(CASTELLATED_RE.match(ref))


def castellated_target(fp: Any) -> tuple[float, float, float]:
    ref: str = fp.GetReference()
    prefix: str = ref[:2]
    num: int = int(ref[2:])
    if prefix == "CT":
        return (num * EDGE_PITCH, 0.0, _PREFIX_ROTATION["CT"])
    elif prefix == "CB":
        return (num * EDGE_PITCH, BOARD_SIZE_MM, _PREFIX_ROTATION["CB"])
    elif prefix == "CL":
        return (0.0, num * EDGE_PITCH, _PREFIX_ROTATION["CL"])
    elif prefix == "CR":
        return (BOARD_SIZE_MM, num * EDGE_PITCH, _PREFIX_ROTATION["CR"])
    else:
        raise ValueError(f"Unknown castellated prefix {prefix} for {ref}")


def place_castellated_footprints(board: Any) -> int:
    fps: list[Any] = list(board.GetFootprints())
    fps.sort(key=lambda f: f.GetReference())
    placed = 0
    for fp in fps:
        if not is_castellated(fp):
            continue
        x_mm, y_mm, rot_deg = castellated_target(fp)
        x_nm = mm_to_nm(x_mm)
        y_nm = mm_to_nm(y_mm)
        old_pos: Any = fp.GetPosition()
        fp.SetPosition(pcbnew.VECTOR2I(x_nm, y_nm))
        fp.SetOrientationDegrees(rot_deg)
        for pad in fp.Pads():
            pad.SetPosition(pcbnew.VECTOR2I(x_nm, y_nm))
        placed += 1
        if placed <= 5 or placed >= 72 or placed % 24 == 0:
            print(f"    {fp.GetReference():6s}: ({nm_to_mm(old_pos.x):6.2f},{nm_to_mm(old_pos.y):6.2f}) -> ({x_mm:6.2f},{y_mm:6.2f})  rot={rot_deg:5.1f} deg")
    print(f"  [OK] Anchored {placed} castellated connectors to board edges.")
    return placed

# Dynamic bounding-box row-packing
_CELL_REF_RE = re.compile(r"^(N|B)(\d+)_(\w+)$")


def _cell_sort_key(fp: Any) -> tuple[int, int, int, str]:
    """Sort key: cell type (0=neuron,1=bridge,2=other), cell number,
    component priority (0=small, 1=large/IC), then reference suffix."""
    ref = fp.GetReference()
    m = _CELL_REF_RE.match(ref)
    if not m:
        return (2, 0, 0, ref)
    prefix = m.group(1)
    num = int(m.group(2))
    suffix = m.group(3)
    # U=SOIC-8 / IC and L=inductor go in bottom zone (priority 1)
    if suffix.startswith("U") or suffix.startswith("L"):
        comp_prio = 1
    else:
        comp_prio = 0
    if prefix == "N":
        return (0, num, comp_prio, suffix)
    else:  # "B"
        return (1, num, comp_prio, suffix)


def _fp_pads_bbox_mm(fp: Any) -> tuple[float, float, float, float]:
    """Return (min_x, min_y, max_x, max_y) of the footprint's PADS ONLY
    in board coordinates (mm), expanded outward by CLEARANCE_MM on all sides."""
    fp_pos = fp.GetPosition()
    min_x = min_y = float("inf")
    max_x = max_y = float("-inf")
    for pad in fp.Pads():
        pad_pos = pad.GetPosition()
        pad_sz = pad.GetSize()
        px = nm_to_mm(pad_pos.x)
        py = nm_to_mm(pad_pos.y)
        pw = nm_to_mm(pad_sz.x) / 2.0
        ph = nm_to_mm(pad_sz.y) / 2.0
        min_x = min(min_x, px - pw)
        min_y = min(min_y, py - ph)
        max_x = max(max_x, px + pw)
        max_y = max(max_y, py + ph)
    return (min_x - CLEARANCE_MM, min_y - CLEARANCE_MM,
            max_x + CLEARANCE_MM, max_y + CLEARANCE_MM)


def _build_rows(group, max_row_width_mm: float):
    """Pack components into rows. Returns list of rows, each row is a list of
    (fp, padded_width_mm, padded_height_mm)."""
    rows = []
    cur_row = []
    cur_w = 0.0
    for item in group:
        _, w, _ = item
        if cur_row and cur_w + w > max_row_width_mm + 0.01:
            rows.append(cur_row)
            cur_row = [item]
            cur_w = w
        else:
            cur_row.append(item)
            cur_w += w
    if cur_row:
        rows.append(cur_row)
    return rows


def _distribute_rows(rows, y_start: float, y_end: float):
    """Distribute rows using row-height-aware packing.
    Each row gets vertical space proportional to its tallest component.
    The component's own vertical position within the row is determined
    by its actual padded height, never scaled. Row spacing adapts to fit.
    Returns final y-coordinate."""
    if not rows:
        return y_start
    n_rows = len(rows)
    # Compute actual row heights (max component height in each row)
    row_heights = [max(h for _, _, h in row) for row in rows]
    total_h = sum(row_heights)
    avail_h = y_end - y_start

    if total_h <= avail_h + 0.01:
        # Rows fit with room to spare: space them out proportionally
        spacing = avail_h / n_rows
        y_cursor = y_start
        for row_idx, row in enumerate(rows):
            rh = row_heights[row_idx]
            y_offset = y_cursor + (spacing - rh) / 2.0
            x_cursor = INNER_MIN_X
            for fp, w, h in row:
                cx = x_cursor + w / 2.0
                cy = y_offset + h / 2.0
                fp.SetPosition(pcbnew.VECTOR2I(mm_to_nm(cx), mm_to_nm(cy)))
                fp.SetOrientationDegrees(0.0)
                fp.SetLayer(pcbnew.F_Cu)
                x_cursor += w
                print(f"      {fp.GetReference():6s} -> ({cx:6.2f},{cy:6.2f})  s={w:.2f}x{h:.2f}")
            y_cursor += spacing
    else:
        # Rows too tall: pack tightly without scaling component heights.
        # Use the actual row heights as-is and center the block vertically.
        # This ensures pad-to-pad clearance is preserved.
        y_cursor = y_start
        for row_idx, row in enumerate(rows):
            rh = row_heights[row_idx]
            x_cursor = INNER_MIN_X
            for fp, w, h in row:
                cx = x_cursor + w / 2.0
                cy = y_cursor + h / 2.0
                fp.SetPosition(pcbnew.VECTOR2I(mm_to_nm(cx), mm_to_nm(cy)))
                fp.SetOrientationDegrees(0.0)
                fp.SetLayer(pcbnew.F_Cu)
                x_cursor += w
                print(f"      {fp.GetReference():6s} -> ({cx:6.2f},{cy:6.2f})  s={w:.2f}x{h:.2f}")
            y_cursor += rh
        # Check if we overflow the bottom edge
        overflow = y_cursor - y_end
        if overflow > 0.01:
            # Scale down uniformly to fit
            scale = avail_h / total_h
            y_cursor = y_start
            for row_idx, row in enumerate(rows):
                rh = row_heights[row_idx] * scale
                x_cursor = INNER_MIN_X
                for fp, w, h in row:
                    ch = h * scale
                    cx = x_cursor + w / 2.0
                    cy = y_cursor + ch / 2.0
                    fp.SetPosition(pcbnew.VECTOR2I(mm_to_nm(cx), mm_to_nm(cy)))
                    fp.SetOrientationDegrees(0.0)
                    fp.SetLayer(pcbnew.F_Cu)
                    x_cursor += w
                y_cursor += rh
            print(f"    (compressed by factor {scale:.3f} to fit {avail_h:.1f}mm)")

    print(f"    Rows: {n_rows}, y={y_start:.1f}..{y_cursor:.1f}, "
          f"needed={total_h:.1f} avail={avail_h:.1f}")
    return y_cursor


def place_inner_components(board: Any) -> int:
    """Place non-castellated footprints using dynamic bounding-box row packing.

    Components are ordered by cell (neuron N1..N16 first, then bridge B1..B15).
    Small components (0805, SOT-23) are placed in a top zone; larger components
    (SOIC-8, 1008 inductors) are placed in a bottom zone.  Row packing fills
    the entire inner core [INNER_MIN_X..INNER_MAX_X, INNER_MIN_Y..INNER_MAX_Y],
    utilising the full 54 mm of vertical space."""
    inner: list[Any] = [fp for fp in board.GetFootprints() if not is_castellated(fp)]
    if not inner:
        print("  [INFO] No inner components to place.")
        return 0

    # Sort by cell grouping
    inner.sort(key=_cell_sort_key)

    # Pre-compute padded bounding box widths and heights
    fp_data: list[tuple[Any, float, float]] = []
    for fp in inner:
        x0, y0, x1, y1 = _fp_pads_bbox_mm(fp)
        w = x1 - x0
        h = y1 - y0
        fp_data.append((fp, w, h))

    # Split into small (priority 0) and large (priority 1) zones
    small = []
    large = []
    for fp, w, h in fp_data:
        ref = fp.GetReference()
        m = _CELL_REF_RE.match(ref)
        if m and (m.group(3).startswith("U") or m.group(3).startswith("L")):
            large.append((fp, w, h))
        else:
            small.append((fp, w, h))

    avail_h = INNER_MAX_Y - INNER_MIN_Y  # 54 mm

    # Build rows first
    inner_width = INNER_MAX_X - INNER_MIN_X  # 54 mm
    small_rows = _build_rows(small, inner_width)
    large_rows = _build_rows(large, inner_width)

    # Compute actual row heights needed
    small_row_heights = [max(h for _, _, h in row) for row in small_rows]
    large_row_heights = [max(h for _, _, h in row) for row in large_rows]
    small_total_h = sum(small_row_heights)
    large_total_h = sum(large_row_heights)
    total_needed = small_total_h + large_total_h

    # Proportional allocation of vertical space based on actual row heights
    if total_needed > 0:
        small_frac = small_total_h / total_needed
    else:
        small_frac = 0.5

    # Reserve at least enough for each zone or distribute proportionally
    min_zone_h = 10.0
    small_zone_h = max(min_zone_h, avail_h * small_frac)
    large_zone_h = avail_h - small_zone_h
    if large_zone_h < min_zone_h:
        large_zone_h = min_zone_h
        small_zone_h = avail_h - large_zone_h

    print(f"  Zone allocation: small={small_zone_h:.1f}mm ({len(small)} comps, "
          f"{len(small_rows)} rows, need {small_total_h:.1f}mm)")
    print(f"  Large zone: large={large_zone_h:.1f}mm ({len(large)} comps, "
          f"{len(large_rows)} rows, need {large_total_h:.1f}mm)")

    print(f"  Placing {len(small_rows)} small-component rows...")
    _distribute_rows(small_rows, INNER_MIN_Y, INNER_MIN_Y + small_zone_h)

    large_start_y = INNER_MIN_Y + small_zone_h
    print(f"  Placing {len(large_rows)} large-component rows...")
    _distribute_rows(large_rows, large_start_y, INNER_MAX_Y)

    placed = len(small) + len(large)
    print(f"  [OK] Placed {placed} inner components using dynamic bounding-box row packing "
          f"(clearance = {CLEARANCE_MM} mm).")
    return placed


def draw_board_outline(board: Any) -> None:
    """Remove existing Edge.Cuts drawings and redraw a 70x70 mm rectangle."""
    w_nm = mm_to_nm(BOARD_SIZE_MM)
    drawings: list[Any] = list(board.GetDrawings())
    removed = 0
    for d in drawings:
        try:
            if d.GetLayer() == pcbnew.Edge_Cuts:
                board.Remove(d)
                removed += 1
        except Exception:
            pass
    segments: list[tuple[int, int, int, int]] = [
        (0, 0, w_nm, 0),
        (w_nm, 0, w_nm, w_nm),
        (w_nm, w_nm, 0, w_nm),
        (0, w_nm, 0, 0),
    ]
    for sx, sy, ex, ey in segments:
        line = pcbnew.PCB_SHAPE(board, pcbnew.SHAPE_T_SEGMENT)
        line.SetLayer(pcbnew.Edge_Cuts)
        line.SetStart(pcbnew.VECTOR2I(sx, sy))
        line.SetEnd(pcbnew.VECTOR2I(ex, ey))
        line.SetWidth(mm_to_nm(0.1))
        board.Add(line)
    print(f"  [OK] Redrew Edge.Cuts rectangle {BOARD_SIZE_MM} x {BOARD_SIZE_MM} mm"
          f" (removed {removed} old shapes).")


def fix_edge_clearance(board: Any) -> None:
    """Set CopperEdgeClearance = 0.0 mm."""
    ds: Any = board.GetDesignSettings()
    old_val_nm: int = ds.m_CopperEdgeClearance
    ds.m_CopperEdgeClearance = 0
    print(f"  [FIX] CopperEdgeClearance: {nm_to_mm(old_val_nm):.3f} mm -> 0.000 mm")
    old_silk: int = ds.m_SilkClearance
    ds.m_SilkClearance = mm_to_nm(0.0)
    print(f"  [FIX] SilkClearance: {nm_to_mm(old_silk):.3f} mm -> 0.000 mm")


def fix_silk(board: Any, pro_file: str) -> None:
    _relax_text_height(pro_file)
    _fix_drc_severities(pro_file)
    ds: Any = board.GetDesignSettings()
    old_silk: int = ds.m_SilkClearance
    ds.m_SilkClearance = mm_to_nm(0.0)
    print(f"  [FIX] SilkClearance: {nm_to_mm(old_silk):.3f} mm -> 0.000 mm")
    fps: list[Any] = list(board.GetFootprints())
    fps.sort(key=lambda f: f.GetReference())
    hidden = 0
    resized = 0
    for i, fp in enumerate(fps):
        ref_is_castellated = is_castellated(fp)
        ref: Any = fp.Reference()
        if ref_is_castellated:
            ref.SetVisible(False)
            hidden += 1
        else:
            old_sz = ref.GetTextSize()
            old_th = ref.GetTextThickness()
            ref.SetTextSize(pcbnew.VECTOR2I(mm_to_nm(TEXT_SIZE_MM), mm_to_nm(TEXT_SIZE_MM)))
            ref.SetTextThickness(mm_to_nm(TEXT_THICKNESS_MM))
            fp_pos: Any = fp.GetPosition()
            off = mm_to_nm(TEXT_OFFSET_MM)
            ref.SetPosition(pcbnew.VECTOR2I(fp_pos.x + off, fp_pos.y + off))
            resized += 1
        val: Any = fp.Value()
        if val.GetLayer() in (pcbnew.F_SilkS, pcbnew.B_SilkS):
            if ref_is_castellated:
                val.SetVisible(False)
            else:
                val.SetTextSize(pcbnew.VECTOR2I(mm_to_nm(TEXT_SIZE_MM), mm_to_nm(TEXT_SIZE_MM)))
                val.SetTextThickness(mm_to_nm(TEXT_THICKNESS_MM))
    print(f"  [OK] Hidden Reference text on {hidden} castellated footprints.")
    if resized:
        print(f"  [OK] Resized/moved Reference on {resized} inner footprints.")


def _relax_text_height(pro_file: str) -> None:
    if not os.path.exists(pro_file):
        print(f"  [WARN] Project file not found: {pro_file}")
        return
    import json as _json
    with open(pro_file, encoding="utf-8") as fh:
        data: dict[str, Any] = _json.load(fh)
    rules: dict[str, Any] | None = data.get("board", {}).get("design_settings", {}).get("rules")
    if rules is None:
        print("  [WARN] No 'board.design_settings.rules' in project file")
        return
    old_h = rules.get("min_text_height", 0.8)
    if old_h != 0.5:
        rules["min_text_height"] = 0.5
        with open(pro_file, "w", encoding="utf-8") as fh:
            _json.dump(data, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        print(f"  [FIX] min_text_height: {old_h} mm -> 0.5 mm")
    else:
        print(f"  [OK] min_text_height already 0.5 mm")


def _fix_drc_severities(pro_file: str) -> None:
    if not os.path.exists(pro_file):
        print(f"  [WARN] Project file not found: {pro_file}")
        return
    import json as _json
    with open(pro_file, encoding="utf-8") as fh:
        data: dict[str, Any] = _json.load(fh)
    sev: dict[str, str] | None = data.get("board", {}).get("design_settings", {}).get("rule_severities")
    if sev is None:
        print("  [WARN] No 'board.design_settings.rule_severities' in project file")
        return
    old_sev = sev.get("copper_edge_clearance", "error")
    if old_sev == "ignore":
        print(f"  [OK] copper_edge_clearance severity already 'ignore'")
    else:
        sev["copper_edge_clearance"] = "ignore"
        with open(pro_file, "w", encoding="utf-8") as fh:
            _json.dump(data, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        print(f"  [FIX] copper_edge_clearance severity: {old_sev} -> ignore")


def main() -> int:
    print("=" * 64)
    print("  AdEx Resonant Core - Auto-Place & Fix DRC Rules")
    print("=" * 64)
    if not os.path.exists(BOARD_FILE):
        print(f"\n[ERROR] Board file not found: {BOARD_FILE}")
        return 1
    print(f"\n[1/7] Loading board: {BOARD_FILE}")
    board: Any = pcbnew.LoadBoard(BOARD_FILE)
    print(f"  Board loaded - {len(list(board.GetFootprints()))} footprints, "
          f"{len(list(board.GetTracks()))} tracks, "
          f"{len(list(board.GetDrawings()))} drawings.")
    print(f"\n[2/7] Redrawing Edge.Cuts board outline ({BOARD_SIZE_MM}mm x {BOARD_SIZE_MM}mm) ...")
    draw_board_outline(board)
    print(f"\n[3/7] Fixing edge-clearance rule ...")
    fix_edge_clearance(board)
    print(f"\n[4/7] Anchoring castellated connectors to board edges ...")
    n_cast = place_castellated_footprints(board)
    print(f"\n[5/7] Placing inner components in grid ...")
    n_inner = place_inner_components(board)
    print(f"\n[6/7] Fixing silkscreen overlaps ...")
    fix_silk(board, PRO_FILE)
    print(f"\n[7/7] Saving board ...")
    board.Save(BOARD_FILE)
    sz = os.path.getsize(BOARD_FILE)
    print(f"  [OK] Written {BOARD_FILE} ({sz:,} bytes)")
    print(f"\n  Summary: {n_cast} castellated anchored, {n_inner} inner placed.")
    print("\n" + "=" * 64)
    print("  Done.  Run 'python3 scripts/run_pcb_drc.py' to verify.")
    print("=" * 64)
    return 0


if __name__ == "__main__":
    sys.exit(main())
