import { createRequire } from 'node:module';
import { writeFileSync } from 'node:fs';
const req = createRequire(process.argv[2] + '/');
const { PDFDocument, StandardFonts, rgb } = req('pdf-lib');
const OUT = process.argv[3];
async function mk(name, draw) {
  const doc = await PDFDocument.create(); const font = await doc.embedFont(StandardFonts.Helvetica);
  const p = doc.addPage([612, 792]);
  const T = (s, x, y, size = 10) => p.drawText(s, { x, y, size, font });
  const L = (a, b, c, d) => p.drawLine({ start: { x: a, y: b }, end: { x: c, y: d }, thickness: 0.75 });
  const grid = (xs, ys) => { for (const y of ys) L(xs[0], y, xs.at(-1), y); for (const x of xs) L(x, ys[0], x, ys.at(-1)); };
  draw({ T, L, grid, p, rgb });
  writeFileSync(`${OUT}/${name}.pdf`, await doc.save());
}
// A: nested table floating inside a cell, with a gap around it
await mk('A_floating', ({ T, grid }) => { grid([50, 250, 560], [680, 620, 500]); T('Outer A1', 60, 650); T('Outer B1', 260, 650); T('Outer A2', 60, 560);
  grid([270, 400, 530], [600, 560, 520]); T('Nest 1,1', 280, 575); T('Nest 1,2', 410, 575); T('Nest 2,1', 280, 535); T('Nest 2,2', 410, 535); });
// B: nested table edge-to-edge: its lines touch the parent cell's borders
await mk('B_edge_to_edge', ({ T, grid }) => { grid([50, 250, 560], [680, 620, 500]); T('Outer A1', 60, 650); T('Outer B1', 260, 650); T('Outer A2', 60, 560);
  grid([250, 405, 560], [620, 560, 500]); T('Nest 1,1', 260, 585); T('Nest 1,2', 415, 585); T('Nest 2,1', 260, 525); T('Nest 2,2', 415, 525); });
// C: three levels, each floating
await mk('C_three_levels', ({ T, grid }) => { grid([40, 200, 572], [700, 650, 300]); T('Level1 A1', 50, 670); T('Level1 B1', 210, 670); T('Level1 A2', 50, 470);
  grid([215, 340, 560], [630, 590, 320]); T('Level2 A1', 225, 605); T('Level2 B1', 350, 605); T('Level2 A2', 225, 450);
  grid([355, 450, 545], [570, 530, 490]); T('Level3 1,1', 365, 545); T('Level3 1,2', 460, 545); T('Level3 2,1', 365, 505); T('Level3 2,2', 460, 505); });
// D: nested table with short numeric cells (under 10 characters in total)
await mk('D_short_cells', ({ T, grid }) => { grid([50, 250, 560], [680, 620, 500]); T('Outer A1', 60, 650); T('Outer B1', 260, 650); T('Outer A2', 60, 560);
  grid([270, 400, 530], [600, 560, 520]); T('1', 280, 575); T('2', 410, 575); T('3', 280, 535); T('4', 410, 535); });
// E: merged header (colspan 2) and rowspan
await mk('E_merged', ({ T, L }) => { L(50, 680, 450, 680); L(50, 640, 450, 640); L(150, 600, 450, 600); L(50, 560, 450, 560);
  L(50, 680, 50, 560); L(150, 640, 150, 560); L(300, 640, 300, 560); L(450, 680, 450, 560); T('Merged header', 200, 655); T('Rowspan', 60, 595); T('b1', 160, 615); T('c1', 310, 615); T('b2', 160, 575); T('c2', 310, 575); });
// F: borderless nested: outer has lines, inner is aligned text only
await mk('F_borderless_nested', ({ T, grid }) => { grid([50, 250, 560], [680, 620, 480]); T('Outer A1', 60, 650); T('Outer B1', 260, 650); T('Outer A2', 60, 550);
  for (let r = 0; r < 4; r++) { T(`Item ${r}`, 270, 595 - r * 22); T(`${100 + r}.50`, 400, 595 - r * 22); T(`Note${r}`, 490, 595 - r * 22); } });
