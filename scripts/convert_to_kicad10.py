#!/usr/bin/env python3
"""Convert schematics to KiCad 10 format."""
import os, re, sys

SCH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "hardware", "schematics")

def convert(fp):
    with open(fp) as f:
        text = f.read()
    orig = text

    def ex(p, s):
        m = re.search(p, s)
        return m.group(1) if m else None

    # Phase 1: Symbol instances -> multi-line format
    lines = text.split('\n')
    out = []
    buf = []
    insym = False
    for line in lines:
        s = line.strip()
        if s.startswith('(symbol'):
            if insym:
                out.extend(buf)
            insym = True
            buf = [line]
        elif insym:
            buf.append(line)
            if s == ')':
                insym = False
                raw = ' '.join(l.strip() for l in buf)
                d = {}
                d['lib'] = ex(r'\(lib_id "([^"]+)"\)', raw)
                d['unit'] = ex(r'\(unit (\d+)\)', raw)
                m = re.search(r'\(at ([\d.\-]+) ([\d.\-]+) ([\d.\-]+)\)', raw)
                if m:
                    d['at'] = '%s %s %s' % (m.group(1), m.group(2), m.group(3))
                d['uuid'] = ex(r'\(uuid "([^"]+)"\)', raw)
                d['bom'] = 'yes' if '(in_bom yes)' in raw else 'no'
                d['brd'] = 'yes' if '(on_board yes)' in raw else 'no'
                d['props'] = {}
                for m in re.finditer(
                    r'\(property \(name "([^"]+)"\)\s*\(value "([^"]*)"\)\s*\)', raw):
                    d['props'][m.group(1)] = m.group(2)
                if d.get('lib') and d.get('at'):
                    r = []
                    r.append('  (symbol')
                    r.append('    (lib_id "' + d['lib'] + '")')
                    r.append('    (at ' + d['at'] + ')')
                    r.append('    (unit ' + (d.get('unit') or '1') + ')')
                    r.append('    (exclude_from_sim no)')
                    r.append('    (in_bom ' + d['bom'] + ')')
                    r.append('    (on_board ' + d['brd'] + ')')
                    r.append('    (dnp no)')
                    if d.get('uuid'):
                        r.append('    (uuid "' + d['uuid'] + '")')
                    for pn, pv in d['props'].items():
                        hide = pn in ('Footprint', 'Datasheet', 'ki_keywords')
                        ax = d['at'].split()[0]
                        ay = d['at'].split()[1]
                        r.append('    (property "' + pn + '" "' + pv + '"')
                        r.append('      (at ' + ax + ' ' + ay + ' 0)')
                        if hide:
                            r.append('      (effects (font (size 1.27 1.27)) (hide yes))')
                        else:
                            r.append('      (effects (font (size 1.27 1.27)))')
                        r.append('    )')
                    r.append('  )')
                    out.extend(r)
                else:
                    out.extend(buf)
                buf = []
        else:
            out.append(line)
    if buf:
        out.extend(buf)
    text = '\n'.join(out)

    # Phase 2: Wires
    text = re.sub(
        r'\(wire \(pts \(([\d.\-]+) ([\d.\-]+)\) \(([\d.\-]+) ([\d.\-]+)\)',
        r'(wire (pts (xy \1 \2) (xy \3 \4)', text)
    text = text.replace('(type default)', '(type solid)')
    text = re.sub(r'\(color [\d.]+ [\d.]+ [\d.]+ [\d.]+\)\s*', '', text)

    # Phase 3: Sheet instances
    text = text.replace('sheet_instances', 'instances')
    text = re.sub(
        r'\(path "([^"]+)"\)\s*\(reference "[^"]*"\)\s*\(unit \d+\)\s*\(value "[^"]*"\)',
        r'(project "adex-core" (path "\1"))', text)
    text = text.replace('(fill )', '(fill (type none))')

    # Phase 4: Labels
    text = re.sub(r'\s*\(fields_autoplaced\)', '', text)
    text = re.sub(
        r'\(label "([^"]+)"\s*\(at ([^)]+)\)\s*\(uuid "([^"]+)"\)\s*\(font \(size ([\d.]+) ([\d.]+)\)(?:\s*\(thickness [\d.]+\))?\)\s*\)',
        r'(label "\1" (at \2) (effects (font (size \4 \5))) (uuid "\3"))',
        text)
    text = re.sub(
        r'\(hierarchical_label "([^"]+)"\s*\(shape ([^)]+)\)\s*\(at ([^)]+)\)\s*\(uuid "([^"]+)"\)\s*\(font \(size ([\d.]+) ([\d.]+)\)(?:\s*\(thickness [\d.]+\))?\)\s*\)',
        r'(hierarchical_label "\1" (shape \2) (at \3) (effects (font (size \5 \5))) (uuid "\4"))',
        text)

    # Phase 5: Sheet property names
    text = text.replace('(property "Sheet name"', '(property "Sheetname"')
    text = text.replace('(property "Sheet file"', '(property "Sheetfile"')

    # Phase 6: Remove stray pin lines
    text = re.sub(r'^\s*\(pin \([^)]*\) \([^)]*\)\)\s*$', '', text, flags=re.MULTILINE)

    if text != orig:
        with open(fp, 'w') as f:
            f.write(text)
        return True
    return False

def main():
    print('='*60)
    print('  KiCad 10 Schematic Conversion')
    print('='*60)
    for name in ['top_level.kicad_sch', 'adex_neuron_cell.kicad_sch', 'lc_bridge_cell.kicad_sch']:
        fp = os.path.join(SCH, name)
        if not os.path.exists(fp):
            print('  [SKIP] ' + name)
            continue
        sys.stdout.write('  ' + name + '... ')
        sys.stdout.flush()
        ok = convert(fp)
        print('OK' if ok else 'No changes')
        with open(fp) as f:
            t = f.read()
        ops = t.count('(')
        cls = t.count(')')
        print('    Balance: %d/%d %s' % (ops, cls, 'BALANCED' if ops == cls else 'FAIL'))
    print('  Done!')

if __name__ == '__main__':
    main()
