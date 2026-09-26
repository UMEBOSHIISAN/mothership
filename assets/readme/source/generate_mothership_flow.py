"""Generate bilingual Mothership Core explainer GIFs and static posters.

These are explanatory presentation assets, not execution evidence. The font,
dimensions, frame rate, and output paths are explicit build inputs.
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import sys
from textwrap import wrap

try:
    import tomllib
except ModuleNotFoundError as exc:  # pragma: no cover - build-host preflight
    raise SystemExit("README asset generation requires Python 3.12 or newer") from exc

from PIL import Image, ImageDraw, ImageFont


MIN_PYTHON = (3, 12)
if sys.version_info < MIN_PYTHON:  # pragma: no cover - build-host preflight
    raise SystemExit("README asset generation requires Python 3.12 or newer")

CONTRACT_PATH = Path(__file__).with_name("asset-build.toml")
CONTRACT = tomllib.loads(CONTRACT_PATH.read_text("utf-8"))
if CONTRACT.get("schema") != "mothership-readme-assets.v1":
    raise SystemExit("unsupported README asset contract")

WIDTH, HEIGHT = int(CONTRACT["width"]), int(CONTRACT["height"])
POSTER_WIDTH, POSTER_HEIGHT = int(CONTRACT["poster_width"]), int(CONTRACT["poster_height"])
FPS = int(CONTRACT["fps"])
SCENES = 6
FRAME_COUNT = int(CONTRACT["frame_count"])
DURATION_MS = int(CONTRACT["duration_ms"])
NORMAL_WEIGHT = int(CONTRACT["normal_weight"])
BOLD_WEIGHT = int(CONTRACT["bold_weight"])
if FRAME_COUNT % SCENES:
    raise SystemExit("frame_count must divide evenly across scenes")
if FRAME_COUNT * 1000 != FPS * DURATION_MS:
    raise SystemExit("frame_count, duration_ms, and fps are inconsistent")
FRAMES_PER_SCENE = FRAME_COUNT // SCENES

BG = "#f7faf9"
PAPER = "#ffffff"
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
LINE = "#c6d5d1"

COPY = {
    "ja": {
        "title": "現在のMothership Coreと接続境界",
        "subtitle": "人間の判断・実行・確認を分離して扱う",
        "context": ("提案・証拠", "権限を与えない判断材料", "v0.4.2では未結合"),
        "parameters": ("正確な実行項目", "呼び出し側が別に用意"),
        "core": "公開Mothership Core",
        "freeze": ("具体的な操作", "5項目を固定"),
        "decision": ("人間の判断", "承認 / 拒否"),
        "consume": ("ローカル台帳", "同じ履歴内で一度"),
        "consume_poster": ("ローカル台帳", "同じ履歴内で一度"),
        "executor": ("任意GitHub companion", "明示transport / retryなし"),
        "adapter": ("純粋adapter → Receipt", "finish欠落: reject", "UNKNOWNはUNKNOWNのまま"),
        "verifier": ("独立した確認系", "別途構成 / 同梱なし"),
        "profile": "現在の最初の参照プロファイル：github.merge_pr",
        "explain": "仕組みの図解です。実行・認証・独立確認の証拠ではありません。",
        "scenes": (
            ("人間とAIが仕事を分ける", "提案・証拠は権限を与えない判断材料です。正確な実行項目は呼び出し側が別に用意します。"),
            ("具体的な操作を固定", "リポジトリ・PR番号・元の変更・対象ブランチ・統合方法を固定します。"),
            ("表示された操作を人間が判断", "呼び出し側が提示した承認または拒否を、操作IDとダイジェストへ照合します。"),
            ("判断を記録し、一度だけ取り出す", "同じ信頼されたローカル台帳履歴内で二度目の取り出しを拒否します。"),
            ("companion試行 → adapter → Core Receipt", "任意companionは明示transportで最大1回のPUTを試みます。純粋adapterはfinish欠落をrejectし、terminal pairをCore Receiptへ投影します。retry / reconsumeはありません。"),
            ("独立確認は別経路で扱う", "Receipt SUCCESSは独立確認ではありません。Verificationは別途供給し、確認不能や曖昧さはUNKNOWNのまま扱います。"),
        ),
    },
    "en": {
        "title": "Mothership Core + companion",
        "subtitle": "Keep human judgment, execution, and verification separate",
        "context": ("Proposal / evidence", "Non-authorizing context", "Not bound in v0.4.2"),
        "parameters": ("Execution fields", "Caller-supplied"),
        "core": "Public Mothership Core",
        "freeze": ("Exact operation", "Freeze five fields"),
        "decision": ("Human decision", "Approve / Reject"),
        "consume": ("Local ledger", "One use per", "ledger history"),
        "consume_poster": ("Local ledger", "One use / ledger history"),
        "executor": ("Optional GitHub companion", "Explicit transport / no retry"),
        "adapter": ("Pure adapter → Receipt", "Missing finish: reject", "UNKNOWN stays UNKNOWN"),
        "verifier": ("Independent verifier", "Separate producer / not bundled"),
        "profile": "First current reference profile: github.merge_pr",
        "explain": "An explainer, not execution, authentication, or independent-verification evidence.",
        "scenes": (
            ("Humans and AI divide the work", "Proposal and evidence do not grant authority; the caller separately supplies exact execution fields."),
            ("Freeze one exact supported operation", "Repository, PR, head, base name, and merge method are fixed."),
            ("The human judges the displayed operation", "A caller-attested approve or reject is checked against its action ID and digest."),
            ("Record the decision and consume once", "A second consume is rejected within the same trusted local ledger history."),
            ("Companion attempt → adapter → Core Receipt", "Optional companion uses explicit transport for at most one PUT. Pure adapter rejects missing finish and maps the terminal pair to Core Receipt; no retry or reconsume."),
            ("Independent verification stays separate", "Receipt SUCCESS is not independent verification. Verification is supplied separately; unclear observations remain UNKNOWN."),
        ),
    },
}

FONT_PATH: Path


def load_font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont:
    result = ImageFont.truetype(str(FONT_PATH), size)
    result.set_variation_by_axes([BOLD_WEIGHT if bold else NORMAL_WEIGHT])
    return result


def centered(draw: ImageDraw.ImageDraw, x: int, y: int, value: str, size: int, *, color: str = INK, bold: bool = False) -> None:
    current = load_font(size, bold=bold)
    box = draw.textbbox((0, 0), value, font=current)
    draw.text((x - (box[2] - box[0]) / 2, y - (box[3] - box[1]) / 2), value, font=current, fill=color)


def centered_lines(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    lines: tuple[str, ...] | list[str],
    size: int,
    *,
    color: str = INK,
    bold: bool = False,
    gap: int = 5,
) -> None:
    current = load_font(size, bold=bold)
    heights = [draw.textbbox((0, 0), value, font=current)[3] for value in lines]
    total = sum(heights) + gap * max(0, len(lines) - 1)
    x0, y0, x1, y1 = box
    y = (y0 + y1 - total) / 2
    for value, height in zip(lines, heights, strict=True):
        text_box = draw.textbbox((0, 0), value, font=current)
        x = (x0 + x1 - (text_box[2] - text_box[0])) / 2
        draw.text((x, y), value, font=current, fill=color)
        y += height + gap


def wrap_to_pixel_width(
    draw: ImageDraw.ImageDraw,
    value: str,
    size: int,
    max_width: int,
    *,
    locale: str,
) -> list[str]:
    """Wrap copy by rendered width so bilingual panels never crop text."""
    font = load_font(size)
    units = list(value) if locale == "ja" else value.split()
    lines: list[str] = []
    current = ""
    for unit in units:
        candidate = unit if not current else (current + unit if locale == "ja" else f"{current} {unit}")
        if current and draw.textbbox((0, 0), candidate, font=font)[2] > max_width:
            lines.append(current)
            current = unit
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines or [""]


def solid_box(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], fill: str, outline: str, *, active: bool = False) -> None:
    draw.rounded_rectangle(box, radius=18, fill=fill, outline=outline, width=6 if active else 3)


def dashed_box(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], fill: str, outline: str, *, active: bool = False) -> None:
    x0, y0, x1, y1 = box
    draw.rounded_rectangle(box, radius=18, fill=fill)
    width = 6 if active else 3
    dash, gap = 14, 9
    for start in range(x0 + 15, x1 - 15, dash + gap):
        draw.line((start, y0, min(start + dash, x1 - 15), y0), fill=outline, width=width)
        draw.line((start, y1, min(start + dash, x1 - 15), y1), fill=outline, width=width)
    for start in range(y0 + 15, y1 - 15, dash + gap):
        draw.line((x0, start, x0, min(start + dash, y1 - 15)), fill=outline, width=width)
        draw.line((x1, start, x1, min(start + dash, y1 - 15)), fill=outline, width=width)


def arrow(draw: ImageDraw.ImageDraw, start: tuple[int, int], end: tuple[int, int], color: str, *, active: bool = False) -> None:
    width = 6 if active else 3
    draw.line((*start, *end), fill=color, width=width)
    x, y = end
    draw.polygon(((x, y), (x - 13, y - 8), (x - 13, y + 8)), fill=color)


def down_arrow(draw: ImageDraw.ImageDraw, x: int, start_y: int, end_y: int, color: str) -> None:
    draw.line((x, start_y, x, end_y), fill=color, width=4)
    draw.polygon(((x, end_y), (x - 8, end_y - 13), (x + 8, end_y - 13)), fill=color)


def dotted_segment(draw: ImageDraw.ImageDraw, start: tuple[int, int], end: tuple[int, int], color: str) -> None:
    x0, y0 = start
    x1, y1 = end
    distance = max(abs(x1 - x0), abs(y1 - y0))
    for step in range(0, distance + 1, 12):
        ratio = step / max(1, distance)
        x = round(x0 + (x1 - x0) * ratio)
        y = round(y0 + (y1 - y0) * ratio)
        draw.ellipse((x - 2, y - 2, x + 2, y + 2), fill=color)


def draw_map(draw: ImageDraw.ImageDraw, copy: dict[str, object], scene: int | None) -> None:
    context = (35, 110, 245, 195)
    parameters = (35, 215, 245, 305)
    core = (265, 105, 820, 315)
    freeze = (285, 155, 445, 280)
    decision = (465, 155, 625, 280)
    consume = (645, 155, 800, 280)
    companion = (855, 105, 1165, 168)
    adapter = (855, 178, 1165, 241)
    verifier = (855, 251, 1165, 315)

    dashed_box(draw, context, PAPER, BLUE, active=scene == 0)
    centered_lines(draw, context, copy["context"], 16, color=BLUE, bold=scene == 0, gap=2)
    solid_box(draw, parameters, BLUE_LIGHT, BLUE, active=scene == 0)
    centered_lines(draw, parameters, copy["parameters"], 17, color=BLUE, bold=scene == 0, gap=3)

    draw.rounded_rectangle(core, radius=24, fill="#eef7f3", outline=GREEN, width=5)
    centered(draw, 542, 130, str(copy["core"]), 23, color=GREEN, bold=True)
    solid_box(draw, freeze, PAPER, GREEN, active=scene == 1)
    solid_box(draw, decision, ORANGE_LIGHT, ORANGE, active=scene == 2)
    solid_box(draw, consume, GREEN_LIGHT, GREEN, active=scene == 3)
    centered_lines(draw, freeze, copy["freeze"], 18, bold=scene == 1)
    centered_lines(draw, decision, copy["decision"], 18, color=ORANGE, bold=scene == 2)
    centered_lines(draw, consume, copy["consume"], 17, color=GREEN, bold=scene == 3)

    solid_box(draw, companion, PURPLE_LIGHT, PURPLE, active=scene == 4)
    solid_box(draw, adapter, GREEN_LIGHT, GREEN, active=scene == 4)
    solid_box(draw, verifier, CYAN_LIGHT, CYAN, active=scene == 5)
    centered_lines(draw, companion, copy["executor"], 15, color=PURPLE, bold=scene == 4, gap=1)
    centered_lines(draw, adapter, copy["adapter"], 13, color=GREEN, bold=scene == 4, gap=0)
    centered_lines(draw, verifier, copy["verifier"], 15, color=CYAN, bold=scene == 5, gap=1)

    dotted_segment(draw, (245, 150), (255, 150), BLUE)
    dotted_segment(draw, (255, 150), (255, 325), BLUE)
    dotted_segment(draw, (255, 325), (545, 325), BLUE)
    dotted_segment(draw, (545, 325), (545, 285), BLUE)
    arrow(draw, (250, 260), (280, 260), BLUE, active=scene in (0, 1))
    arrow(draw, (450, 218), (460, 218), GREEN, active=scene == 2)
    arrow(draw, (630, 218), (640, 218), ORANGE, active=scene == 3)
    arrow(draw, (805, 136), (850, 136), GREEN, active=scene == 4)
    down_arrow(draw, 1010, 168, 176, GREEN)


def draw_scene(locale: str, scene: int, progress: float) -> Image.Image:
    copy = COPY[locale]
    image = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(image)
    centered(draw, WIDTH // 2, 36, str(copy["title"]), 34, bold=True)
    centered(draw, WIDTH // 2, 78, str(copy["subtitle"]), 22, color=MUTED)
    draw_map(draw, copy, scene)

    panel = (35, 350, 1165, 555)
    draw.rounded_rectangle(panel, radius=22, fill=PAPER, outline=LINE, width=2)
    title, detail = copy["scenes"][scene]
    centered(draw, WIDTH // 2, 390, title, 34, bold=True)
    detail_size = 25
    lines = wrap_to_pixel_width(draw, detail, detail_size, 980, locale=locale)
    if len(lines) >= 3:
        detail_size = 22
        lines = wrap_to_pixel_width(draw, detail, detail_size, 980, locale=locale)
    if len(lines) > 3:
        detail_size = 19
        lines = wrap_to_pixel_width(draw, detail, detail_size, 980, locale=locale)
    centered_lines(draw, (80, 415, 1120, 505), lines, detail_size, color=MUTED, gap=3)

    start, end, y = 170, 1030, 530
    draw.line((start, y, end, y), fill=LINE, width=3)
    for index in range(SCENES):
        x = start + int((end - start) * index / (SCENES - 1))
        fill = GREEN if index <= scene else PAPER
        draw.ellipse((x - 7, y - 7, x + 7, y + 7), fill=fill, outline=GREEN, width=2)
    cursor = start + int((end - start) * progress)
    draw.ellipse((cursor - 8, y - 8, cursor + 8, y + 8), fill=GREEN, outline=PAPER, width=2)

    draw.rounded_rectangle((265, 580, 935, 620), radius=12, fill=GREEN_LIGHT, outline=GREEN, width=2)
    centered(draw, WIDTH // 2, 600, str(copy["profile"]), 23, color=GREEN, bold=True)
    centered(draw, WIDTH // 2, 649, str(copy["explain"]), 19, color=MUTED)
    return image


def draw_poster(locale: str) -> Image.Image:
    copy = COPY[locale]
    image = Image.new("RGB", (POSTER_WIDTH, POSTER_HEIGHT), BG)
    draw = ImageDraw.Draw(image)
    center_x = POSTER_WIDTH // 2
    centered(draw, center_x, 35, str(copy["title"]), 30, bold=True)
    subtitle = wrap(str(copy["subtitle"]), width=46 if locale == "en" else 27, break_long_words=False)
    centered_lines(draw, (45, 60, 675, 108), subtitle, 20, color=MUTED, gap=3)

    context = (45, 120, 675, 220)
    dashed_box(draw, context, PAPER, BLUE)
    centered_lines(draw, context, copy["context"], 21, color=BLUE, gap=2)

    parameters = (45, 250, 675, 330)
    solid_box(draw, parameters, BLUE_LIGHT, BLUE)
    centered_lines(draw, parameters, copy["parameters"], 22, color=BLUE, bold=True, gap=3)
    down_arrow(draw, center_x, 330, 355, BLUE)

    core = (35, 360, 685, 690)
    draw.rounded_rectangle(core, radius=24, fill="#eef7f3", outline=GREEN, width=5)
    centered(draw, center_x, 385, str(copy["core"]), 25, color=GREEN, bold=True)
    boxes = (
        ((65, 410, 655, 485), copy["freeze"], PAPER, GREEN),
        ((65, 510, 655, 585), copy["decision"], ORANGE_LIGHT, ORANGE),
        ((65, 610, 655, 675), copy["consume_poster"], GREEN_LIGHT, GREEN),
    )
    for box, values, fill, outline in boxes:
        solid_box(draw, box, fill, outline)
        centered_lines(draw, box, values, 22, color=outline, bold=True, gap=3)
    down_arrow(draw, center_x, 485, 505, GREEN)
    down_arrow(draw, center_x, 585, 605, ORANGE)

    draw.line((360, 690, 360, 715), fill=GREEN, width=4)
    draw.line((360, 715, 190, 715), fill=GREEN, width=4)
    down_arrow(draw, 190, 715, 728, GREEN)
    down_arrow(draw, 190, 825, 840, GREEN)
    companion = (45, 730, 335, 825)
    adapter = (45, 850, 335, 945)
    verifier = (385, 730, 675, 945)
    solid_box(draw, companion, PURPLE_LIGHT, PURPLE)
    solid_box(draw, adapter, GREEN_LIGHT, GREEN)
    solid_box(draw, verifier, CYAN_LIGHT, CYAN)
    centered_lines(draw, companion, copy["executor"], 16, color=PURPLE, bold=True, gap=2)
    centered_lines(draw, adapter, copy["adapter"], 16, color=GREEN, bold=True, gap=2)
    centered_lines(draw, verifier, copy["verifier"], 17, color=CYAN, bold=True, gap=3)

    draw.rounded_rectangle((45, 970, 675, 1015), radius=12, fill=GREEN_LIGHT, outline=GREEN, width=2)
    centered(draw, center_x, 992, str(copy["profile"]), 19, color=GREEN, bold=True)
    explanation = wrap(str(copy["explain"]), width=54 if locale == "en" else 34, break_long_words=False)
    centered_lines(draw, (45, 1020, 675, 1073), explanation, 17, color=MUTED, gap=3)
    return image


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--locale", choices=tuple(COPY), required=True)
    parser.add_argument("--font", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def frame_durations() -> list[int]:
    """Distribute whole GIF centiseconds while preserving the exact duration."""
    if DURATION_MS % 10:
        raise SystemExit("duration_ms must be representable in GIF centiseconds")
    total_ticks = DURATION_MS // 10
    base, remainder = divmod(total_ticks, FRAME_COUNT)
    durations = []
    accumulator = 0
    for _ in range(FRAME_COUNT):
        accumulator += remainder
        extra = 0
        if accumulator >= FRAME_COUNT:
            extra = 1
            accumulator -= FRAME_COUNT
        durations.append((base + extra) * 10)
    return durations


def main() -> None:
    global FONT_PATH
    args = parse_args()
    FONT_PATH = args.font.resolve()
    if not FONT_PATH.is_file():
        raise SystemExit("font input is missing or is not a regular file")
    expected_font = (CONTRACT_PATH.parent / str(CONTRACT["font"])).resolve()
    if FONT_PATH != expected_font:
        raise SystemExit(f"font input must match the asset contract: {expected_font}")
    actual_font_sha256 = hashlib.sha256(FONT_PATH.read_bytes()).hexdigest()
    if actual_font_sha256 != CONTRACT["font_sha256"]:
        raise SystemExit("font input digest does not match the asset contract")

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    gif_path = output_dir / "mothership-flow.gif"
    poster_path = output_dir / "mothership-flow-poster.png"

    frames = []
    for frame_index in range(FRAME_COUNT):
        scene = min(SCENES - 1, frame_index // FRAMES_PER_SCENE)
        frames.append(draw_scene(args.locale, scene, frame_index / max(1, FRAME_COUNT - 1)))

    draw_poster(args.locale).save(poster_path, format="PNG", optimize=True)
    palette = [
        frame.quantize(colors=128, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
        for frame in frames
    ]
    palette[0].save(
        gif_path,
        format="GIF",
        save_all=True,
        append_images=palette[1:],
        duration=frame_durations(),
        loop=0,
        optimize=True,
        disposal=2,
    )
    if gif_path.stat().st_size >= int(CONTRACT["max_gif_bytes"]):
        raise SystemExit("generated GIF exceeds the asset contract size ceiling")
    print(f"generated {gif_path} ({gif_path.stat().st_size} bytes)")
    print(f"generated {poster_path} ({poster_path.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
