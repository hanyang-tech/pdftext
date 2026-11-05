import sys, glob, os, json, pdfplumber
d = sys.argv[1]
for f in sorted(glob.glob(d + '/[A-F]_*.pdf')):
    with pdfplumber.open(f) as pdf:
        p = pdf.pages[0]
        print('\n==', os.path.basename(f), 'chars', len(p.chars), 'lines', len(p.lines), 'rects', len(p.rects))
        ts = p.find_tables()
        for t in ts: print('  lines-strategy', [round(v) for v in t.bbox], json.dumps(t.extract()))
        if not ts: print('  lines-strategy: none')
        if f.endswith('F_borderless_nested.pdf'):
            for t in p.find_tables({'vertical_strategy': 'text', 'horizontal_strategy': 'text'}): print('  text-strategy', [round(v) for v in t.bbox], json.dumps(t.extract())[:300])
