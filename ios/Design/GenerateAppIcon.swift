import AppKit

let size = 1024
guard let bitmap = NSBitmapImageRep(
    bitmapDataPlanes: nil,
    pixelsWide: size,
    pixelsHigh: size,
    bitsPerSample: 8,
    samplesPerPixel: 3,
    hasAlpha: false,
    isPlanar: false,
    colorSpaceName: .deviceRGB,
    bytesPerRow: 0,
    bitsPerPixel: 0
), let context = NSGraphicsContext(bitmapImageRep: bitmap) else { fatalError("Could not create icon canvas") }

NSGraphicsContext.saveGraphicsState()
NSGraphicsContext.current = context
NSColor(calibratedRed: 250 / 255, green: 57 / 255, blue: 57 / 255, alpha: 1).setFill()
NSBezierPath(rect: NSRect(x: 0, y: 0, width: size, height: size)).fill()

NSColor.white.setFill()
NSBezierPath(roundedRect: NSRect(x: 286, y: 208, width: 452, height: 608), xRadius: 58, yRadius: 58).fill()

let red = NSColor(calibratedRed: 250 / 255, green: 57 / 255, blue: 57 / 255, alpha: 1)
red.setStroke()
for (y, width) in [(640.0, 244.0), (550.0, 244.0), (460.0, 174.0)] {
    let line = NSBezierPath(); line.lineWidth = 34; line.lineCapStyle = .round
    line.move(to: NSPoint(x: 390, y: y)); line.line(to: NSPoint(x: 390 + width, y: y)); line.stroke()
}

NSColor.white.setStroke()
let brackets = NSBezierPath(); brackets.lineWidth = 42; brackets.lineCapStyle = .round; brackets.lineJoinStyle = .round
let segments = [
    (NSPoint(x: 228, y: 676), NSPoint(x: 228, y: 796), NSPoint(x: 348, y: 796)),
    (NSPoint(x: 676, y: 796), NSPoint(x: 796, y: 796), NSPoint(x: 796, y: 676)),
    (NSPoint(x: 796, y: 348), NSPoint(x: 796, y: 228), NSPoint(x: 676, y: 228)),
    (NSPoint(x: 348, y: 228), NSPoint(x: 228, y: 228), NSPoint(x: 228, y: 348))
]
for segment in segments { brackets.move(to: segment.0); brackets.line(to: segment.1); brackets.line(to: segment.2) }
brackets.stroke()
context.flushGraphics()
NSGraphicsContext.restoreGraphicsState()

guard let png = bitmap.representation(using: .png, properties: [:]) else { fatalError("Could not encode icon") }
let output = URL(fileURLWithPath: CommandLine.arguments[1])
try png.write(to: output, options: .atomic)
