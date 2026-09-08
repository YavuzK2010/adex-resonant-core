#!/usr/bin/env python3
"""
Fix pad geometry in PCB for R_0603_1608Metric and C_0603_1608Metric footprints.
The footprint names were changed from 0805 to 0603 but the actual pad geometry
remained as 0805. This script updates pad dimensions to standard 0603.
"""
import re
import sys

PCB_FILE = "/home/yavuzkemalinan/adex-resonant-brain/hardware/adex_resonant_core.kicad_pcb"

# 0603 pad geometry
# Standard R_0603_1608Metric / C_0603_1608Metric pads:
#   Pad position: +/-0.75mm from centre
#   Pad size: 0.8 x 0.9mm
PAD_AT_0603 = 0.75
PAD_SIZE_X = 0.8
PAD_SIZE_Y = 0.9
PAD_RROUND = 0.25  # roundrect_rratio

# Old 0805 geometry
#   Pad position: +/-0.9125mm (or +/-0.95mm)
#   Pad size: 1.025 x 1.4mm (or 1.0 x 1.45mm)
#   roundrect_rratio: 0.243902 or 0.25


def fix_pcb_0603_pads():
    with open(PCB_FILE, 'r', encoding='utf-8') as f:
        content = f.read()

    lines = content.split('\n')
    fixed_count = 0
    i = 0
    in_0603 = False

    while i < len(lines):
        line = lines[i]

        # Track if we're inside a 0603 resistor or capacitor footprint
        if 'footprint "R_0603_1608Metric"' in line or 'footprint "C_0603_1608Metric"' in line:
            in_0603 = True
        elif line.strip().startswith('(footprint "') and not in_0603:
            pass
        elif line.strip().startswith('(footprint "') and in_0603:
            # next footprint without R_0603/C_0603 in line
            continue

        if in_0603:
            # Keep track of the last (at ... ) seen so we also fix pad sizes
            # Replace old 0805 pad sizes with standard 0603 sizes
            size_match = re.match(r'\s*\(size\s+([0-9.]+)\s+([0-9.]+)\)', line)
            if size_match:
                old_sx = float(size_match.group(1))
                old_sy = float(size_match.group(2))
                if abs(old_sx - PAD_SIZE_X) > 0.001 or abs(old_sy - PAD_SIZE_Y) > 0.001:
                    new_line = re.sub(
                        r'\(size\s+[0-9.]+\s+[0-9.]+\)',
                        f'(size {PAD_SIZE_X:.4f} {PAD_SIZE_Y:.4f})',
                        line
                    )
                    lines[i] = new_line
                    fixed_count += 1

            # Reset flag when leaving the 0603 footprint (next footprint block)
            if re.match(r'\s*\(footprint "', line) and 'R_0603_1608Metric' not in line and 'C_0603_1608Metric' not in line:
                in_0603 = False

        # Detect 0603 pad positions and fix them too
        if in_0603:
            pad_at_match = re.match(r'\s*\(at\s+(-?0\.\d+)\s+0\)', line)
            if pad_at_match:
                old_at = float(pad_at_match.group(1))
                new_at = PAD_AT_0603 if old_at > 0 else -PAD_AT_0603
                if abs(abs(old_at) - PAD_AT_0603) > 0.001:
                    lines[i] = re.sub(
                        r'\(at\s+(-?0\.\d+)\s+0\)',
                        f'(at {new_at:.4f} 0)',
                        line
                    )
                    fixed_count += 1
            # Fix roundrect ratios
            rratio_match = re.match(r'\s*\(roundrect_rratio\s+[0-9.]+\)', line)
            if rratio_match:
                old_rr = float(rratio_match.group(0).split()[-1].rstrip(')'))
                if abs(old_rr - PAD_RROUND) > 0.001:
                    lines[i] = re.sub(
                        r'\(roundrect_rratio\s+[0-9.]+\)',
                        f'(roundrect_rratio {PAD_RROUND})',
                        line
                    )
                    fixed_count += 1

        i += 1

    # Write back
    with open(PCB_FILE, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))

    print(f"[OK] Fixed {fixed_count} pad geometry entries in 0603 footprints.")
    return fixed_count


if __name__ == '__main__':
    sys.exit(0 if fix_pcb_0603_pads() else 1)