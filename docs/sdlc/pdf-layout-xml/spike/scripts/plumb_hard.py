import sys, json, pdfplumber
d = sys.argv[1]
for n in ['G_xobject', 'H_rotate90']:
    with pdfplumber.open(f'{d}/{n}.pdf') as pdf:
        p = pdf.pages[0]; print('==', n, 'size', p.width, p.height, 'rotation', p.rotation, 'chars', len(p.chars), 'lines', len(p.lines))
        c = p.chars[0]; print('  first char', c['text'], [round(c[k], 2) for k in ('x0', 'top', 'x1', 'bottom')], 'upright', c['upright'])
        if p.lines: l = p.lines[0]; print('  first line', [round(l[k], 2) for k in ('x0', 'top', 'x1', 'bottom')])
        print('  tables', [t.extract() for t in p.find_tables()])
with pdfplumber.open(f'{d}/I_unicode.pdf') as pdf: print('== I text', repr(pdf.pages[0].extract_text()))
with pdfplumber.open(f'{d}/A_floating.pdf') as pdf:
    p = pdf.pages[0]; c = [x for x in p.chars if x['text'] == 'N'][0]; print('== A char N', [round(c[k], 2) for k in ('x0', 'top', 'x1', 'bottom')])
