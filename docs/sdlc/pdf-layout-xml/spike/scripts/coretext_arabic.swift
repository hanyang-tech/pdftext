import Foundation
import CoreText
import CoreGraphics
let text = "مرحبا بالعالم Hello 123"
var box = CGRect(x: 0, y: 0, width: 612, height: 792)
let url = URL(fileURLWithPath: "coretext_arabic.pdf") as CFURL
let ctx = CGContext(url, mediaBox: &box, nil)!
ctx.beginPDFPage(nil)
let font = CTFontCreateWithName("Geeza Pro" as CFString, 24, nil)
let attrs: [NSAttributedString.Key: Any] = [NSAttributedString.Key(kCTFontAttributeName as String): font]
let line = CTLineCreateWithAttributedString(NSAttributedString(string: text, attributes: attrs))
ctx.textPosition = CGPoint(x: 72, y: 700)
CTLineDraw(line, ctx)
ctx.endPDFPage()
ctx.closePDF()
