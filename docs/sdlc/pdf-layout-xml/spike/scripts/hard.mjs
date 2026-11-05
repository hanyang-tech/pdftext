import { createRequire } from 'node:module';
import { writeFileSync, readFileSync } from 'node:fs';
const req = createRequire(process.argv[2] + '/');
const { PDFDocument, StandardFonts, degrees } = req('pdf-lib');
const fontkit = req('@pdf-lib/fontkit');
const OUT = process.argv[3], FONT = process.argv[4];
const base = async () => { const doc = await PDFDocument.create(); const font = await doc.embedFont(StandardFonts.Helvetica); return { doc, font }; };
const grid = (p, xs, ys) => { for (const y of ys) p.drawLine({ start: { x: xs[0], y }, end: { x: xs.at(-1), y }, thickness: 0.75 }); for (const x of xs) p.drawLine({ start: { x, y: ys[0] }, end: { x, y: ys.at(-1) }, thickness: 0.75 }); };
const tbl = (p, font, x, y) => { grid(p, [x, x + 100, x + 200], [y, y - 30, y - 60]); ['A1', 'B1', 'A2', 'B2'].forEach((s, i) => p.drawText(s, { x: x + 10 + (i % 2) * 100, y: y - 20 - (i >> 1) * 30, size: 10, font })); };
// G: table inside a form XObject placed at (100,300) and scaled 1.5
{ const { doc, font } = await base(); const src = doc.addPage([300, 100]); tbl(src, font, 10, 90); const emb = await doc.embedPage(src); const p = doc.addPage([612, 792]); p.drawPage(emb, { x: 100, y: 300, xScale: 1.5, yScale: 1.5 }); doc.removePage(0); writeFileSync(`${OUT}/G_xobject.pdf`, await doc.save()); }
// H: page with /Rotate 90 holding a table
{ const { doc, font } = await base(); const p = doc.addPage([612, 792]); p.setRotation(degrees(90)); tbl(p, font, 100, 600); writeFileSync(`${OUT}/H_rotate90.pdf`, await doc.save()); }
// I: non-Latin text via embedded subset font with ToUnicode
if (FONT) { const doc = await PDFDocument.create(); doc.registerFontkit(fontkit); const font = await doc.embedFont(readFileSync(FONT), { subset: true }); const p = doc.addPage([612, 792]); p.drawText('Héllo Ωmega 日本語 مرحبا', { x: 50, y: 700, size: 12, font }); writeFileSync(`${OUT}/I_unicode.pdf`, await doc.save()); }
// J: 200 dense pages for speed and memory
{ const { doc, font } = await base(); for (let n = 0; n < 200; n++) { const p = doc.addPage([612, 792]); for (let t = 0; t < 4; t++) { const y = 760 - t * 190; const xs = [40, 170, 300, 430, 570], ys = [0, 1, 2, 3, 4, 5, 6, 7, 8].map(r => y - r * 20); grid(p, xs, ys); for (let r = 0; r < 8; r++) for (let c = 0; c < 4; c++) p.drawText(`p${n} t${t} r${r} c${c} value`, { x: xs[c] + 4, y: ys[r] - 14, size: 8, font }); } } writeFileSync(`${OUT}/J_200pages.pdf`, await doc.save()); }
