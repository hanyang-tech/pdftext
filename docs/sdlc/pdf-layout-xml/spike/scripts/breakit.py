import sys, re
src, out = sys.argv[1], sys.argv[2]
b = open(src, 'rb').read()
open(f'{out}/trunc90.pdf', 'wb').write(b[:int(len(b) * .9)])
open(f'{out}/trunc50.pdf', 'wb').write(b[:int(len(b) * .5)])
open(f'{out}/badxref.pdf', 'wb').write(re.sub(rb'startxref\s+\d+', b'startxref\n99999999', b))
open(f'{out}/noeof.pdf', 'wb').write(b.replace(b'%%EOF', b''))
open(f'{out}/garbage.pdf', 'wb').write(b'not a pdf at all' * 100)
