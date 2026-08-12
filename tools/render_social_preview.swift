import AppKit
import Foundation

guard CommandLine.arguments.count == 3 else {
    FileHandle.standardError.write(Data("usage: render_social_preview.swift INPUT_IMAGE OUTPUT.png\n".utf8))
    exit(64)
}

let input = CommandLine.arguments[1]
let output = CommandLine.arguments[2]
guard let source = NSImage(contentsOfFile: input), source.size.width > 0, source.size.height > 0 else {
    FileHandle.standardError.write(Data("error: input is not a readable image\n".utf8))
    exit(1)
}

let width = 1280
let height = 640
guard let bitmap = NSBitmapImageRep(
    bitmapDataPlanes: nil,
    pixelsWide: width,
    pixelsHigh: height,
    bitsPerSample: 8,
    samplesPerPixel: 4,
    hasAlpha: true,
    isPlanar: false,
    colorSpaceName: .deviceRGB,
    bytesPerRow: 0,
    bitsPerPixel: 0
) else {
    exit(1)
}
bitmap.size = NSSize(width: width, height: height)

NSGraphicsContext.saveGraphicsState()
guard let context = NSGraphicsContext(bitmapImageRep: bitmap) else {
    exit(1)
}
NSGraphicsContext.current = context
NSColor(calibratedRed: 7 / 255, green: 17 / 255, blue: 31 / 255, alpha: 1).setFill()
NSRect(x: 0, y: 0, width: width, height: height).fill()

let maximum = NSSize(width: 1180, height: 540)
let scale = min(maximum.width / source.size.width, maximum.height / source.size.height)
let drawn = NSSize(width: source.size.width * scale, height: source.size.height * scale)
let destination = NSRect(
    x: (CGFloat(width) - drawn.width) / 2,
    y: (CGFloat(height) - drawn.height) / 2,
    width: drawn.width,
    height: drawn.height
)
source.draw(in: destination, from: .zero, operation: .sourceOver, fraction: 1)
context.flushGraphics()
NSGraphicsContext.restoreGraphicsState()

guard let png = bitmap.representation(using: .png, properties: [:]) else {
    exit(1)
}
try png.write(to: URL(fileURLWithPath: output), options: .atomic)
