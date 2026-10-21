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
        "title": "Mothership：操作と結果を引き継ぐ",
        "subtitle": "8つのbounded route / 結果は読取専用で渡す",
        "context": ("8 routes", "local checks", "live hostは別"),
        "parameters": ("Core action", "操作 + expires_at"),
        "core": "Mothership Core（ソース候補）",
        "freeze": ("正確な操作", "github.merge_pr"),
        "decision": ("Review request", "操作・期限・host"),
        "consume": ("検証 → 台帳", "同じ履歴で一度"),
        "consume_poster": ("検証 → 台帳", "履歴内で一度"),
        "executor": ("GitHub companion", "max 1 PUT / no retry"),
        "adapter": ("Receipt adapter", "finish欠落: reject", "UNKNOWNを保持"),
        "verifier": ("read-back Verification", "Receiptと別記録", "別経路"),
        "profile": "Core 0.5.0.dev0 / adapters 0.1.0.dev0",
        "handoff": ("保存結果 → inspect-result --human", "UNKNOWN・欠落を保持 / 権限は渡さない"),
        "explain": "ソース候補の説明図。閲覧は権限・出所認証・実運用の証明を作りません。",
        "scenes": (
            ("8つの入口、同じrequest", "Agents・LangGraph・OpenClaw・Lobster・MCP・Dots・Harness・Evidence。local checksとlive hostを分けます。"),
            ("正確な操作と期限を固定", "Coreのlive FrozenActionが操作とexpires_atを供給し、helperがrequest digestを計算します。"),
            ("host contextを照合", "responseは保持したrequest、action、期限、host_id・session・actor・generation・scopeへ照合します。期限切れと変更は止まります。"),
            ("Reviewと一度だけconsume", "responseはrequest/action/expiry/contextへ照合され、consumeは同じtrusted historyで一度です。"),
            ("ReceiptとVerificationを分離", "companion attemptからReceiptを作り、read-back Verificationは別記録。finish欠落はrejectします。"),
            ("引き継ぐのは記録、権限ではない", "保存物を別の人・AIへ渡し、実行報告・独立観測・欠落・次の確認を読む。UNKNOWNは成功にせず、再実行もしません。"),
        ),
    },
    "en": {
        "title": "Mothership: actions and evidence",
        "subtitle": "Eight bounded routes / read-only result handoff",
        "context": ("8 routes", "Local checks", "Live host separate"),
        "parameters": ("Core-issued action", "Action + expiry"),
        "core": "Mothership Core (source candidate)",
        "freeze": ("Exact operation", "github.merge_pr"),
        "decision": ("Review request", "Action + expiry"),
        "consume": ("Validate → ledger", "One use per", "trusted history"),
        "consume_poster": ("Validate → ledger", "One use / history"),
        "executor": ("GitHub companion", "Max 1 PUT / no retry"),
        "adapter": ("Receipt adapter", "Missing finish: reject", "UNKNOWN preserved"),
        "verifier": ("Read-back Verification", "Separate from Receipt", "Independent record"),
        "profile": "Core 0.5.0.dev0 / adapters 0.1.0.dev0",
        "handoff": ("Saved results → inspect-result --human", "UNKNOWN stays unknown; no authority transfer"),
        "explain": "Source candidate. Reading grants no authority. Not proof of origin or live effects.",
        "scenes": (
            ("Eight paths, one request", "Agents, LangGraph, OpenClaw, Lobster, MCP, Dots, Harness, and Evidence stay bounded; local checks are separate from live hosts."),
            ("Freeze the exact operation and expiry", "The live FrozenAction supplies the operation and expires_at; the helper computes the request digest."),
            ("Bind the host context", "The response is checked against the retained request, action, expiry, and host ID, session, actor, generation, and scope. Drift stops."),
            ("Review, then consume once", "The response is checked against request, action, expiry, and context; consume remains one use per trusted history."),
            ("Keep Receipt and Verification separate", "The companion attempt becomes Receipt; read-back Verification is separate. Missing finish is rejected."),
            ("Hand over records, never authority", "Another person or AI reads reports, observations, missing records and next checks. UNKNOWN is not success; reading never re-executes."),
        ),
    },
}

if any(len(copy["scenes"]) != SCENES for copy in COPY.values()):
    raise SystemExit("every scene must have bilingual copy")

FONT_PATH: Path


def load_font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont:
    result = ImageFont.truetype(str(FONT_PATH), size)
    result.set_variation_by_axes([BOLD_WEIGHT if bold else NORMAL_WEIGHT])
    return result


def centered(draw: ImageDraw.ImageDraw, x: int, y: int, value: str, size: int, *, color: str = INK, bold: bool = False) -> None:
    current = load_font(size, bold=bold)
    box = draw.textbbox((0, 0), value, font=current)
    draw.text((x - (box[2] - box[0]) / 2 - box[0], y - (box[3] - box[1]) / 2 - box[1]), value, font=current, fill=color)


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
    bounds = [draw.textbbox((0, 0), value, font=current) for value in lines]
    heights = [bottom - top for _left, top, _right, bottom in bounds]
    total = sum(heights) + gap * max(0, len(lines) - 1)
    x0, y0, x1, y1 = box
    y = (y0 + y1 - total) / 2
    for value, height, text_box in zip(lines, heights, bounds, strict=True):
        x = (x0 + x1 - (text_box[2] - text_box[0])) / 2 - text_box[0]
        draw.text((x, y - text_box[1]), value, font=current, fill=color)
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
    solid_box(draw, verifier, CYAN_LIGHT, CYAN, active=scene == 4)
    centered_lines(draw, companion, copy["executor"], 15, color=PURPLE, bold=scene == 4, gap=1)
    centered_lines(draw, adapter, copy["adapter"], 13, color=GREEN, bold=scene == 4, gap=0)
    centered_lines(draw, verifier, copy["verifier"], 15, color=CYAN, bold=scene == 4, gap=1)

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

    handoff = (35, 335, 1165, 379)
    solid_box(draw, handoff, CYAN_LIGHT, CYAN, active=scene == 5)
    centered_lines(draw, handoff, copy["handoff"], 14, color=CYAN, bold=scene == 5, gap=1)

    panel = (35, 390, 1165, 555)
    draw.rounded_rectangle(panel, radius=22, fill=PAPER, outline=LINE, width=2)
    title, detail = copy["scenes"][scene]
    centered(draw, WIDTH // 2, 420, title, 30, bold=True)
    detail_size = 25
    lines = wrap_to_pixel_width(draw, detail, detail_size, 980, locale=locale)
    if len(lines) >= 3:
        detail_size = 22
        lines = wrap_to_pixel_width(draw, detail, detail_size, 980, locale=locale)
    if len(lines) > 3:
        detail_size = 19
        lines = wrap_to_pixel_width(draw, detail, detail_size, 980, locale=locale)
    centered_lines(draw, (80, 443, 1120, 516), lines, detail_size, color=MUTED, gap=3)

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
    centered_lines(draw, (45, 970, 675, 1015), copy["handoff"], 16, color=GREEN, bold=True, gap=2)
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
