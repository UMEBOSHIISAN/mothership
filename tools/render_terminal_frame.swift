import AppKit
import Foundation

guard CommandLine.arguments.count == 5 else {
    fputs("usage: render_terminal_frame.swift MODE TITLE INPUT OUTPUT\n", stderr)
    exit(64)
}

let mode = CommandLine.arguments[1]
let title = CommandLine.arguments[2]
let input = CommandLine.arguments[3]
let output = CommandLine.arguments[4]
let transcript = try String(contentsOfFile: input, encoding: .utf8)
let size = NSSize(width: 1280, height: 720)
let image = NSImage(size: size)

let accent = mode == "safe"
    ? NSColor(calibratedRed: 0.32, green: 0.84, blue: 0.82, alpha: 1)
    : NSColor(calibratedRed: 0.96, green: 0.43, blue: 0.47, alpha: 1)

image.lockFocus()
NSColor(calibratedRed: 0.025, green: 0.047, blue: 0.078, alpha: 1).setFill()
NSBezierPath(rect: NSRect(origin: .zero, size: size)).fill()

let terminal = NSBezierPath(
    roundedRect: NSRect(x: 36, y: 38, width: 1208, height: 644),
    xRadius: 22,
    yRadius: 22
)
NSColor(calibratedRed: 0.045, green: 0.083, blue: 0.122, alpha: 1).setFill()
terminal.fill()
NSColor(calibratedRed: 0.15, green: 0.28, blue: 0.35, alpha: 1).setStroke()
terminal.lineWidth = 2
terminal.stroke()

for (index, color) in [
    NSColor(calibratedRed: 0.97, green: 0.38, blue: 0.40, alpha: 1),
    NSColor(calibratedRed: 0.96, green: 0.67, blue: 0.24, alpha: 1),
    NSColor(calibratedRed: 0.32, green: 0.79, blue: 0.45, alpha: 1),
].enumerated() {
    color.setFill()
    NSBezierPath(ovalIn: NSRect(x: 70 + (index * 28), y: 638, width: 12, height: 12)).fill()
}

let titleAttributes: [NSAttributedString.Key: Any] = [
    .font: NSFont.monospacedSystemFont(ofSize: 18, weight: .semibold),
    .foregroundColor: NSColor(calibratedRed: 0.73, green: 0.83, blue: 0.87, alpha: 1),
]
title.draw(at: NSPoint(x: 184, y: 632), withAttributes: titleAttributes)

accent.setFill()
NSBezierPath(roundedRect: NSRect(x: 68, y: 574, width: 7, height: 30), xRadius: 3, yRadius: 3).fill()
let verdict = mode == "safe" ? "COMPLETE · supplied records agree" : "DRIFTED · action class mismatch"
let verdictAttributes: [NSAttributedString.Key: Any] = [
    .font: NSFont.monospacedSystemFont(ofSize: 24, weight: .bold),
    .foregroundColor: accent,
]
verdict.draw(at: NSPoint(x: 94, y: 574), withAttributes: verdictAttributes)

let paragraph = NSMutableParagraphStyle()
paragraph.lineBreakMode = .byCharWrapping
paragraph.lineSpacing = 8
let bodyAttributes: [NSAttributedString.Key: Any] = [
    .font: NSFont.monospacedSystemFont(ofSize: 20, weight: .regular),
    .foregroundColor: NSColor(calibratedRed: 0.88, green: 0.95, blue: 0.96, alpha: 1),
    .paragraphStyle: paragraph,
]
transcript.draw(
    in: NSRect(x: 68, y: 124, width: 1144, height: 414),
    withAttributes: bodyAttributes
)

let boundary = "explicitly supplied records · no ambient capture · no execution authority"
let boundaryAttributes: [NSAttributedString.Key: Any] = [
    .font: NSFont.monospacedSystemFont(ofSize: 15, weight: .regular),
    .foregroundColor: NSColor(calibratedRed: 0.48, green: 0.65, blue: 0.70, alpha: 1),
]
boundary.draw(at: NSPoint(x: 68, y: 76), withAttributes: boundaryAttributes)
image.unlockFocus()

guard
    let tiff = image.tiffRepresentation,
    let bitmap = NSBitmapImageRep(data: tiff),
    let png = bitmap.representation(using: .png, properties: [:])
else {
    fputs("failed to encode terminal frame\n", stderr)
    exit(70)
}
try png.write(to: URL(fileURLWithPath: output), options: .atomic)
