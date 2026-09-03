"""Generate the Japanese Mothership README explainer GIF and poster.

This is a deterministic explanatory asset.  It intentionally contains no
runtime output, credentials, browser capture, or external evidence.
"""

from __future__ import annotations

from pathlib import Path
from textwrap import wrap

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[3]
OUT_DIR = ROOT / "assets" / "readme" / "ja"
GIF_PATH = OUT_DIR / "mothership-flow.gif"
POSTER_PATH = OUT_DIR / "mothership-flow-poster.png"

WIDTH, HEIGHT = 1200, 675
FPS = 8
STAGE_SECONDS = 1.25
STAGES = 8
FRAME_COUNT = int(FPS * STAGE_SECONDS * STAGES)

FONT_PATH = "/System/Library/Fonts/ヒラギノ角ゴシック W5.ttc"
FONT_BOLD_PATH = "/System/Library/Fonts/ヒラギノ角ゴシック W7.ttc"

BG = "#f7faf9"
INK = "#17332d"
MUTED = "#55706a"
GREEN = "#176b58"
GREEN_LIGHT = "#d9efe8"
BLUE = "#2b67a7"
BLUE_LIGHT = "#e1edf9"
ORANGE = "#b66a17"
ORANGE_LIGHT = "#fff0d7"
PURPLE = "#7356a8"
PURPLE_LIGHT = "#eee8fb"
CYAN = "#237e91"
CYAN_LIGHT = "#def3f6"
RED = "#bd3d3d"
RED_LIGHT = "#fde7e7"
LINE = "#c6d5d1"
WHITE = "#ffffff"


def font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(FONT_BOLD_PATH if bold else FONT_PATH, size)


def centered(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, fnt, fill=INK) -> None:
    box = draw.textbbox((0, 0), text, font=fnt)
    draw.text((xy[0] - (box[2] - box[0]) / 2, xy[1] - (box[3] - box[1]) / 2), text, font=fnt, fill=fill)


def multiline_center(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    lines: list[str],
    fnt,
    *,
    fill=INK,
    gap: int = 7,
) -> None:
    x0, y0, x1, y1 = box
    heights = [draw.textbbox((0, 0), line, font=fnt)[3] for line in lines]
    total = sum(heights) + gap * max(0, len(lines) - 1)
    y = (y0 + y1 - total) / 2
    for line, height in zip(lines, heights):
        centered(draw, ((x0 + x1) // 2, int(y + height / 2)), line, fnt, fill)
        y += height + gap


def rounded_box(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    *,
    fill: str,
    outline: str,
    width: int = 3,
    radius: int = 22,
    dashed: bool = False,
) -> None:
    if not dashed:
        draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)
        return
    x0, y0, x1, y1 = box
    draw.rounded_rectangle(box, radius=radius, fill=fill)
    # A dashed outline keeps external integration visually distinct without
    # depending on a particular rendering backend.
    dash = 15
    gap = 10
    for start in range(x0 + radius, x1 - radius, dash + gap):
        draw.line((start, y0, min(start + dash, x1 - radius), y0), fill=outline, width=width)
        draw.line((start, y1, min(start + dash, x1 - radius), y1), fill=outline, width=width)
    for start in range(y0 + radius, y1 - radius, dash + gap):
        draw.line((x0, start, x0, min(start + dash, y1 - radius)), fill=outline, width=width)
        draw.line((x1, start, x1, min(start + dash, y1 - radius)), fill=outline, width=width)


def arrow(draw: ImageDraw.ImageDraw, start: tuple[int, int], end: tuple[int, int], *, fill=GREEN, active=False) -> None:
    width = 6 if active else 3
    draw.line((*start, *end), fill=fill, width=width)
    x, y = end
    draw.polygon([(x, y), (x - 15, y - 9), (x - 15, y + 9)], fill=fill)


def draw_header(draw: ImageDraw.ImageDraw) -> None:
    centered(draw, (WIDTH // 2, 40), "Mothershipの役割", font(28, bold=True), INK)
    centered(draw, (WIDTH // 2, 78), "AIに「できる」を渡しても、「やってよい」は人間に残す。", font(22), MUTED)


def draw_flow(draw: ImageDraw.ImageDraw, stage: int) -> None:
    boxes = {
        "ai": (45, 130, 255, 255),
        "m": (290, 110, 650, 285),
        "x": (700, 130, 920, 255),
        "v": (965, 130, 1155, 255),
    }

    rounded_box(draw, boxes["ai"], fill=BLUE_LIGHT, outline=BLUE, width=4 if stage == 0 else 3)
    multiline_center(draw, (55, 145, 245, 240), ["AI・呼び出し側", "操作案を用意"], font(25, bold=stage == 0), fill=BLUE)

    rounded_box(draw, boxes["m"], fill=GREEN_LIGHT, outline=GREEN, width=5 if 1 <= stage <= 4 else 3)
    centered(draw, (470, 136), "公開Mothership", font(25, bold=True), GREEN)
    multiline_center(
        draw,
        (310, 160, 630, 270),
        ["操作内容を固定", "人間が 承認 / 拒否", "台帳へ記録"],
        font(24, bold=stage in (1, 2, 3, 4)),
        fill=INK,
        gap=5,
    )

    rounded_box(draw, boxes["x"], fill=PURPLE_LIGHT, outline=PURPLE, dashed=True, width=4 if stage == 5 else 3)
    multiline_center(draw, (715, 145, 905, 240), ["別途構成する", "実行系", "外部状態を変更"], font(23, bold=stage == 5), fill=PURPLE, gap=4)

    rounded_box(draw, boxes["v"], fill=CYAN_LIGHT, outline=CYAN, dashed=True, width=4 if stage == 6 else 3)
    multiline_center(draw, (975, 145, 1145, 240), ["別経路の", "確認系", "外部状態を読む"], font(22, bold=stage == 6), fill=CYAN, gap=4)

    arrow(draw, (260, 192), (285, 192), fill=BLUE, active=stage >= 1)
    arrow(draw, (655, 192), (695, 192), fill=GREEN, active=stage >= 5)
    arrow(draw, (925, 192), (960, 192), fill=PURPLE, active=stage >= 6)

    # The dotted return path is deliberately outside the public box: it
    # describes a separately configured observation path, not a shipped tool.
    draw.line((810, 260, 810, 320, 1060, 320, 1060, 260), fill=CYAN, width=3)
    draw.polygon([(1060, 260), (1051, 275), (1069, 275)], fill=CYAN)


def draw_stage_panel(draw: ImageDraw.ImageDraw, stage: int) -> None:
    panel = (45, 350, 1155, 535)
    draw.rounded_rectangle(panel, radius=24, fill=WHITE, outline=LINE, width=2)

    captions = [
        ("AIが操作案を用意", "提案と、実行したい操作の材料を用意します。"),
        ("実行する内容を固定", "リポジトリ・PR番号・headの識別子・baseブランチ名・merge方法。"),
        ("決めるのは人間", "承認または拒否を、表示されたこの操作へ照合します。"),
        ("台帳へ記録", "判断を信頼されたローカル台帳へ記録します。"),
        ("同じ台帳履歴内で一度だけ", "二度目の取り出しは停止します。"),
        ("実行系は別途構成", "公開パッケージは外部の実行系を同梱しません。"),
        ("結果は別経路で確認", "実行側の結果報告だけで終わらせず、外部状態を読み取ります。"),
        ("現在の対応：github.merge_pr のみ", "参照実装。汎用の実行系は非同梱。本番安全性は未主張。"),
    ]
    title, detail = captions[stage]
    centered(draw, (600, 385), title, font(30, bold=True), INK)
    # Keep the explanatory sentence readable even on a narrow README view.
    lines = wrap(detail, width=39, break_long_words=False, break_on_hyphens=False)
    multiline_center(draw, (85, 410, 1115, 475), lines, font(23), fill=MUTED, gap=3)

    if stage == 2:
        draw.rounded_rectangle((400, 490, 545, 525), radius=10, fill=GREEN, outline=GREEN)
        centered(draw, (472, 507), "承認", font(21, bold=True), WHITE)
        draw.rounded_rectangle((560, 490, 705, 525), radius=10, fill=RED_LIGHT, outline=RED, width=2)
        centered(draw, (632, 507), "拒否", font(21, bold=True), RED)
    elif stage == 4:
        draw.rounded_rectangle((480, 490, 720, 525), radius=10, fill=RED_LIGHT, outline=RED, width=2)
        centered(draw, (600, 507), "二度目は停止", font(21, bold=True), RED)
    elif stage == 7:
        draw.rounded_rectangle((235, 490, 965, 525), radius=10, fill=GREEN_LIGHT, outline=GREEN, width=2)
        centered(draw, (600, 507), "操作を限定して示す。広い安全性は主張しない。", font(20, bold=True), GREEN)


def draw_frame(stage: int, progress: float = 1.0) -> Image.Image:
    image = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(image)
    draw_header(draw)
    draw_flow(draw, stage)
    # Keep a real 10 fps timeline in the GIF rather than collapsing each
    # storyboard scene into a single long frame during palette optimization.
    timeline_start, timeline_end, timeline_y = 140, 1060, 316
    draw.line((timeline_start, timeline_y, timeline_end, timeline_y), fill=LINE, width=3)
    for index in range(STAGES):
        x = timeline_start + int((timeline_end - timeline_start) * index / (STAGES - 1))
        fill = GREEN if index <= stage else WHITE
        draw.ellipse((x - 7, timeline_y - 7, x + 7, timeline_y + 7), fill=fill, outline=GREEN, width=2)
    cursor = timeline_start + int((timeline_end - timeline_start) * max(0.0, min(1.0, progress)))
    draw.ellipse((cursor - 8, timeline_y - 8, cursor + 8, timeline_y + 8), fill=GREEN, outline=WHITE, width=2)
    draw_stage_panel(draw, stage)
    centered(draw, (WIDTH // 2, 610), "ひとつの判断。ひとつの具体的な操作。一度だけ。", font(24, bold=True), GREEN)
    centered(draw, (WIDTH // 2, 642), "これは仕組みの図解です。実行系・確認系の提供や本番安全性を証明するものではありません。", font(16), MUTED)
    return image


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    frames: list[Image.Image] = []
    for index in range(FRAME_COUNT):
        stage = min(STAGES - 1, index // int(FPS * STAGE_SECONDS))
        frames.append(draw_frame(stage, index / max(1, FRAME_COUNT - 1)))

    # The poster is a complete, non-animated explanation.  It remains useful
    # for readers who disable animation and as a thumbnail for the GIF.
    poster = draw_frame(STAGES - 1, 1.0)
    poster.save(POSTER_PATH, format="PNG", optimize=True)

    palette_frames = [frame.quantize(colors=128, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE) for frame in frames]
    palette_frames[0].save(
        GIF_PATH,
        format="GIF",
        save_all=True,
        append_images=palette_frames[1:],
        duration=int(1000 / FPS),
        loop=0,
        optimize=True,
        disposal=2,
    )
    print(f"generated {GIF_PATH} ({GIF_PATH.stat().st_size} bytes)")
    print(f"generated {POSTER_PATH} ({POSTER_PATH.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
