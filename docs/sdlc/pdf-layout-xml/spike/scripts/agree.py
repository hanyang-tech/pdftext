import sys, json, re, logging, collections, unicodedata, pdfplumber
logging.disable(logging.CRITICAL)
js = json.load(open(sys.argv[1], encoding='utf-8'))
norm = lambda s: collections.Counter(c for c in unicodedata.normalize('NFKC', s) if not c.isspace())
tot = agree = same = 0; rows = []
for f, a in js.items():
    with pdfplumber.open(f) as pdf:
        b = ''.join(ch['text'] for p in pdf.pages[:30] for ch in p.chars)
    A, B = norm(a), norm(b); inter = sum((A & B).values()); n = max(sum(A.values()), sum(B.values()))
    cid = b.count('(cid:'); cjk = sum(1 for c in b if '぀' <= c <= '鿿' or '가' <= c <= '힣')
    tot += 1
    if n == 0: same += 1; continue
    r = inter / n; agree += r
    rows.append((r, f.split('/')[-2][:22], f.split('/')[-1][:22], sum(A.values()), sum(B.values()), cid, cjk))
print('files', tot, 'both empty', same, 'mean char agreement', round(agree / max(1, len(rows)), 4))
for r in sorted(rows)[:8]: print('  ', round(r[0], 4), *r[1:3], 'pdfjs', r[3], 'plumber', r[4], 'cid', r[5], 'cjk', r[6])
