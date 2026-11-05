import sys, io, logging, pdfplumber, pypdfium2
logging.disable(logging.CRITICAL)
d = sys.argv[1]
for n in ['badxref', 'trunc90', 'trunc50', 'garbage']:
    try:
        doc = pypdfium2.PdfDocument(f'{d}/{n}.pdf'); pages = len(doc); buf = io.BytesIO(); doc.save(buf); doc.close(); buf.seek(0)
        with pdfplumber.open(buf) as pdf:
            print(n, 'pdfium pages', pages, 'pdfplumber pages', len(pdf.pages), 'p1 chars', len(pdf.pages[0].chars), 'lines', len(pdf.pages[0].lines), 'tables', len(pdf.pages[0].find_tables()))
    except Exception as e:
        print(n, 'ERROR', type(e).__name__, str(e)[:80])
