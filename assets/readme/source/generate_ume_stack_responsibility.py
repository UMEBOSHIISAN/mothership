"""Generate the bilingual UME Stack responsibility map as accessible SVG."""

from __future__ import annotations

import argparse
from html import escape
from pathlib import Path


COPY = {
    "ja": {
        "title": "人間とAIが仕事を分け合うための責務分担",
        "human": "人間",
        "human_detail": "目的を持ち、何を任せるかを決める",
        "harness": "UME-HARNESS",
        "harness_lines": ("曖昧な日本語を整理", "やる / 確認 / しない", "PC内の作業範囲"),
        "bridge": "DIRECTION — reviewed runtime bridge / NOT_SHIPPED",
        "bridge_detail": "作業結果・証拠を受け渡す責務上の接続候補",
        "mothership": "Mothership",
        "mothership_lines": ("具体的な外部操作を固定", "人間の判断と照合", "同じ台帳履歴内で一度だけ"),
        "executor": "別途構成する実行系",
        "verifier": "別経路の確認系",
        "caption": "現在の公開release同士に自動runtime bridgeはありません。破線部分は未実装です。",
        "legend": "実線 = 現在実装済み　　破線 = 現在未接続　　外枠 = 別途構成",
    },
    "en": {
        "title": "Responsibility split for humans and AI sharing work",
        "human": "Human",
        "human_detail": "Holds the purpose and decides what to entrust",
        "harness": "UME-HARNESS",
        "harness_lines": ("Organize ambiguous Japanese intent", "Will do / confirm / will not do", "Bound local work"),
        "bridge": "DIRECTION — reviewed runtime bridge / NOT_SHIPPED",
        "bridge_detail": "Candidate responsibility link for local results and evidence",
        "mothership": "Mothership",
        "mothership_lines": ("Freeze one concrete external action", "Check the human decision", "Consume once in one ledger history"),
        "executor": "Separately configured executor",
        "verifier": "Separate verification path",
        "caption": "The current public releases have no automatic runtime bridge. The dashed connection is not implemented.",
        "legend": "Solid = implemented now    Dashed = not connected    Outline = separately configured",
    },
}


def line_text(lines: tuple[str, ...], start_y: int) -> str:
    return "\n".join(
        f'<text class="body" x="600" y="{start_y + index * 42}" text-anchor="middle">{escape(line)}</text>'
        for index, line in enumerate(lines)
    )


def render(locale: str) -> str:
    copy = COPY[locale]
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 1120" role="img" aria-labelledby="title desc">
  <title id="title">{escape(copy["title"])}</title>
  <desc id="desc">{escape(copy["caption"])}</desc>
  <style>
    .title {{ font: 700 34px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; fill: #17332d; }}
    .label {{ font: 700 28px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; fill: #17332d; }}
    .state {{ font: 700 18px ui-monospace, SFMono-Regular, Consolas, monospace; fill: #176b58; }}
    .body {{ font: 23px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; fill: #314d47; }}
    .small {{ font: 18px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; fill: #55706a; }}
  </style>
  <rect width="1200" height="1120" fill="#f7faf9"/>
  <text class="title" x="600" y="58" text-anchor="middle">{escape(copy["title"])}</text>

  <rect x="250" y="95" width="700" height="112" rx="22" fill="#fff0d7" stroke="#b66a17" stroke-width="4"/>
  <text class="label" x="600" y="139" text-anchor="middle">{escape(copy["human"])}</text>
  <text class="body" x="600" y="178" text-anchor="middle">{escape(copy["human_detail"])}</text>

  <path d="M600 207 V247" stroke="#2b67a7" stroke-width="5"/>
  <path d="M590 235 L600 250 L610 235" fill="#2b67a7"/>

  <rect x="190" y="250" width="820" height="235" rx="26" fill="#e1edf9" stroke="#2b67a7" stroke-width="5"/>
  <text class="state" x="225" y="287">CURRENT</text>
  <text class="label" x="600" y="323" text-anchor="middle">{escape(copy["harness"])}</text>
  {line_text(copy["harness_lines"], 370)}

  <path d="M600 485 V615" stroke="#7356a8" stroke-width="5" stroke-dasharray="14 12"/>
  <path d="M590 600 L600 618 L610 600" fill="#7356a8"/>
  <rect x="225" y="515" width="750" height="78" rx="18" fill="#eee8fb" stroke="#7356a8" stroke-width="3" stroke-dasharray="12 10"/>
  <text class="state" x="600" y="546" text-anchor="middle">{escape(copy["bridge"])}</text>
  <text class="small" x="600" y="577" text-anchor="middle">{escape(copy["bridge_detail"])}</text>

  <rect x="190" y="620" width="820" height="235" rx="26" fill="#d9efe8" stroke="#176b58" stroke-width="5"/>
  <text class="state" x="225" y="657">CURRENT</text>
  <text class="label" x="600" y="693" text-anchor="middle">{escape(copy["mothership"])}</text>
  {line_text(copy["mothership_lines"], 740)}

  <path d="M600 855 V900" stroke="#176b58" stroke-width="5"/>
  <path d="M590 885 L600 903 L610 885" fill="#176b58"/>
  <rect x="100" y="905" width="470" height="92" rx="20" fill="#ffffff" stroke="#7356a8" stroke-width="4" stroke-dasharray="13 10"/>
  <rect x="630" y="905" width="470" height="92" rx="20" fill="#ffffff" stroke="#237e91" stroke-width="4" stroke-dasharray="13 10"/>
  <text class="body" x="335" y="960" text-anchor="middle">{escape(copy["executor"])}</text>
  <text class="body" x="865" y="960" text-anchor="middle">{escape(copy["verifier"])}</text>

  <text class="small" x="600" y="1040" text-anchor="middle">{escape(copy["caption"])}</text>
  <text class="small" x="600" y="1080" text-anchor="middle">{escape(copy["legend"])}</text>
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
