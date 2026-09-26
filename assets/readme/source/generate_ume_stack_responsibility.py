"""Generate the bilingual UME Stack responsibility map as accessible SVG."""

from __future__ import annotations

import argparse
from html import escape
from pathlib import Path
import sys

try:
    import tomllib
except ModuleNotFoundError as exc:  # pragma: no cover - build-host preflight
    raise SystemExit("README asset generation requires Python 3.12 or newer") from exc


MIN_PYTHON = (3, 12)
if sys.version_info < MIN_PYTHON:  # pragma: no cover - build-host preflight
    raise SystemExit("README asset generation requires Python 3.12 or newer")

CONTRACT_PATH = Path(__file__).with_name("asset-build.toml")
CONTRACT = tomllib.loads(CONTRACT_PATH.read_text("utf-8"))
WIDTH = int(CONTRACT["responsibility_width"])
HEIGHT = int(CONTRACT["responsibility_height"])
CENTER = WIDTH // 2


COPY = {
    "ja": {
        "title": "人間とAIが仕事を分け合うための責務分担",
        "human": "人間",
        "human_detail": "目的を持ち、何を任せるかを決める",
        "harness": "UME-HARNESS",
        "harness_lines": ("曖昧な日本語を整理", "確認範囲 / 承認要求", "ローカル作業のプレビュー"),
        "state_current": "現在の実装",
        "bridge": "方向性・未実装",
        "bridge_detail": ("明示adapterの境界候補", "自動runtime bridgeは未実装"),
        "mothership": "Mothership",
        "mothership_lines": ("具体的な外部操作を固定", "人間の判断と照合", "台帳履歴内で一度だけ"),
        "executor": ("任意GitHub", "companion", "明示transport"),
        "adapter": ("Receipt adapter", "finish欠落: reject", "UNKNOWNを保持"),
        "verifier": ("独立した確認系", "別途構成", "同梱なし"),
        "caption": ("任意companion / adapterはCoreと自動接続しません。", "独立確認は別経路。Receipt成功は外部真実ではありません。"),
        "legend": ("実線 = 現在実装済み", "破線 = 自動接続なし", "外枠 = 任意・別途構成"),
    },
    "en": {
        "title": "Responsibility split for humans and AI sharing work",
        "human": "Human",
        "human_detail": "Holds the purpose and decides what to entrust",
        "harness": "UME-HARNESS",
        "harness_lines": ("Organize ambiguous Japanese intent", "Visible scope / confirmation", "Local-work preview"),
        "state_current": "CURRENT",
        "bridge": "DIRECTION / NOT_SHIPPED",
        "bridge_detail": ("Explicit adapter boundary candidate", "No automatic runtime bridge"),
        "mothership": "Mothership",
        "mothership_lines": ("Freeze one concrete external action", "Check the human decision", "Consume once per ledger history"),
        "executor": ("Optional GitHub", "companion", "Explicit transport"),
        "adapter": ("Receipt adapter", "Missing finish: reject", "UNKNOWN preserved"),
        "verifier": ("Independent verifier", "Separate producer", "Not bundled"),
        "caption": ("Companion and adapter are opt-in; no automatic Core bridge.", "Independent verification is separate; receipt success is not external truth."),
        "legend": ("Solid = implemented now", "Dashed = no automatic bridge", "Outline = opt-in / separately configured"),
    },
}


def line_text(lines: tuple[str, ...], start_y: int) -> str:
    return "\n".join(
        f'<text class="body" x="{CENTER}" y="{start_y + index * 42}" text-anchor="middle">{escape(line)}</text>'
        for index, line in enumerate(lines)
    )


def centered_tspans(
    lines: tuple[str, ...],
    x: int,
    center_y: int,
    *,
    gap: int = 28,
    css_class: str = "body",
) -> str:
    start_y = center_y - (len(lines) - 1) * gap // 2
    spans = "".join(
        f'<tspan x="{x}" y="{start_y + index * gap}">{escape(line)}</tspan>'
        for index, line in enumerate(lines)
    )
    return f'<text class="{css_class}" x="{x}" text-anchor="middle">{spans}</text>'


def render(locale: str) -> str:
    copy = COPY[locale]
    caption = " ".join(copy["caption"])
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {HEIGHT}" role="img" aria-labelledby="title desc">
  <title id="title">{escape(copy["title"])}</title>
  <desc id="desc">{escape(caption)}</desc>
  <style>
    .title {{ font: 700 28px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; fill: #17332d; }}
    .label {{ font: 700 28px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; fill: #17332d; }}
    .state {{ font: 700 20px ui-monospace, SFMono-Regular, Consolas, monospace; fill: #176b58; }}
    .body {{ font: 23px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; fill: #314d47; }}
    .small {{ font: 20px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; fill: #55706a; }}
    .boxbody {{ font: 18px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; fill: #314d47; }}
    .legend {{ font: 18px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; fill: #55706a; }}
  </style>
  <rect width="{WIDTH}" height="{HEIGHT}" fill="#f7faf9"/>
  <text class="title" x="{CENTER}" y="58" text-anchor="middle">{escape(copy["title"])}</text>

  <rect x="60" y="95" width="600" height="112" rx="22" fill="#fff0d7" stroke="#b66a17" stroke-width="4"/>
  <text class="label" x="{CENTER}" y="139" text-anchor="middle">{escape(copy["human"])}</text>
  <text class="body" x="{CENTER}" y="178" text-anchor="middle">{escape(copy["human_detail"])}</text>

  <path d="M{CENTER} 207 V247" stroke="#2b67a7" stroke-width="5"/>
  <path d="M350 235 L360 250 L370 235" fill="#2b67a7"/>

  <rect x="45" y="250" width="630" height="235" rx="26" fill="#e1edf9" stroke="#2b67a7" stroke-width="5"/>
  <text class="state" x="75" y="287">{escape(copy["state_current"])}</text>
  <text class="label" x="{CENTER}" y="323" text-anchor="middle">{escape(copy["harness"])}</text>
  {line_text(copy["harness_lines"], 370)}

  <g data-role="bridge">
    <path d="M{CENTER} 485 V625" stroke="#7356a8" stroke-width="5" stroke-dasharray="14 12"/>
    <path d="M350 610 L360 628 L370 610" fill="#7356a8"/>
    <rect x="60" y="510" width="600" height="105" rx="18" fill="#eee8fb" stroke="#7356a8" stroke-width="3" stroke-dasharray="12 10"/>
    <text class="state" x="{CENTER}" y="542" text-anchor="middle">{escape(copy["bridge"])}</text>
    <text class="small" x="{CENTER}" y="574" text-anchor="middle">{escape(copy["bridge_detail"][0])}</text>
    <text class="small" x="{CENTER}" y="602" text-anchor="middle">{escape(copy["bridge_detail"][1])}</text>
  </g>

  <rect x="45" y="630" width="630" height="225" rx="26" fill="#d9efe8" stroke="#176b58" stroke-width="5"/>
  <text class="state" x="75" y="667">{escape(copy["state_current"])}</text>
  <text class="label" x="{CENTER}" y="703" text-anchor="middle">{escape(copy["mothership"])}</text>
  {line_text(copy["mothership_lines"], 750)}

  <path d="M{CENTER} 855 V875 H137 V895" fill="none" stroke="#176b58" stroke-width="5"/>
  <path d="M137 899 L129 886 L145 886 Z" fill="#176b58"/>
  <path d="M245 956 H262" stroke="#7356a8" stroke-width="4"/>
  <path d="M262 956 L250 948 L250 964 Z" fill="#7356a8"/>
  <rect data-role="external" x="30" y="900" width="215" height="112" rx="20" fill="#ffffff" stroke="#7356a8" stroke-width="4"/>
  <rect data-role="adapter" x="262" y="900" width="215" height="112" rx="20" fill="#d9efe8" stroke="#176b58" stroke-width="4"/>
  <rect data-role="external" x="485" y="900" width="205" height="112" rx="20" fill="#ffffff" stroke="#237e91" stroke-width="4"/>
  {centered_tspans(copy["executor"], 137, 956, gap=25, css_class="boxbody")}
  {centered_tspans(copy["adapter"], 369, 956, gap=25, css_class="boxbody")}
  {centered_tspans(copy["verifier"], 587, 956, gap=25, css_class="boxbody")}

  {centered_tspans(copy["legend"], CENTER, 1068, gap=30, css_class="legend")}
</svg>
'''


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--locale", choices=tuple(COPY), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render(args.locale), encoding="utf-8")
    print(f"generated {args.output}")


if __name__ == "__main__":
    main()
