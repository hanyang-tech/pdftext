import { readFileSync, writeFileSync } from 'node:fs';
const deps = process.argv[2]; const pdfjs = await import(deps + '/node_modules/pdfjs-dist/legacy/build/pdf.mjs');
const base = deps + '/node_modules/pdfjs-dist/'; const out = {};
for (const f of readFileSync(process.argv[3], 'utf8').trim().split('\n')) {
  const task = pdfjs.getDocument({ data: new Uint8Array(readFileSync(f)), disableFontFace: true, verbosity: 0, cMapUrl: base + 'cmaps/', cMapPacked: true, standardFontDataUrl: base + 'standard_fonts/' });
  const d = await task.promise; let s = '';
  for (let i = 1; i <= Math.min(30, d.numPages); i++) { const p = await d.getPage(i); for (const it of (await p.getTextContent()).items) s += it.str ?? ''; p.cleanup(); }
  out[f] = s; await task.destroy();
}
writeFileSync(process.argv[4], JSON.stringify(out));
