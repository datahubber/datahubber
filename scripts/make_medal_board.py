"""Render the Kaggle medal board as light and dark SVGs, plus its README blocks.

    python scripts/make_medal_board.py          # write assets/*.svg and the README blocks
    python scripts/make_medal_board.py --check  # exit 1 if any output is stale (CI)

The README blocks are the <picture> element (with alt text built from the data) and the
medal table. Each sits between marker comments; text outside the markers is left alone.

Standard library only. The SVG is hand-written so the output is small, deterministic
and renders the same through GitHub's image proxy (no scripts, no web fonts).
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from xml.sax.saxutils import escape

from medals import Board, Medal, compact_count, load, markdown_table

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "kaggle_medals.json"
README = ROOT / "README.md"
BOARD_START, BOARD_END = "<!-- medal-board:start -->", "<!-- medal-board:end -->"
TABLE_START, TABLE_END = "<!-- medal-table:start -->", "<!-- medal-table:end -->"

FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI','Noto Sans',Helvetica,Arial,sans-serif"


@dataclass(frozen=True)
class Theme:
    name: str
    surface: str  # page background the transparent SVG sits on (used for dot rings)
    ink: str  # primary text
    ink2: str  # secondary text
    ink3: str  # muted text: headers, ticks, footnote
    rule: str  # header underline and group separators
    grid: str  # plot gridlines
    medal: dict[str, str]


LIGHT = Theme(
    name="light",
    surface="#ffffff",
    ink="#1f2328",
    ink2="#59636e",
    ink3="#6e7781",
    rule="#d1d9e0",
    grid="#e3e8ed",
    medal={"gold": "#bf8a0b", "silver": "#8a939d", "bronze": "#a04e2a"},
)
DARK = Theme(
    name="dark",
    surface="#0d1117",
    ink="#e6edf3",
    ink2="#9198a1",
    ink3="#7d8590",
    rule="#3d444d",
    grid="#262c36",
    medal={"gold": "#d6a21c", "silver": "#a7b0bb", "bronze": "#c8643a"},
)

# Layout in px. The board is drawn for an 830 px wide README column.
W = 830
X_DOMAIN, X_DOT, X_NAME, X_YEAR, X_ENTRY = 0, 112, 176, 402, 440
X_RANK_END, X_TOP_END = 578, 632
X_PLOT0, X_PLOT1, PLOT_MAX = 656, 812, 10.0  # x of 0 % and of PLOT_MAX %
ROW_H, GROUP_GAP, HEADER_Y, ROWS_TOP = 24, 10, 80, 92
DOMAIN_WRAP = 12  # characters per line before a domain label wraps


def x_of(pct: float) -> float:
    return X_PLOT0 + (X_PLOT1 - X_PLOT0) * min(pct, PLOT_MAX) / PLOT_MAX


def wrap(label: str, width: int = DOMAIN_WRAP) -> list[str]:
    """Two-line domain labels break after '&' ("Vision &" / "3D imaging")."""
    if len(label) <= width:
        return [label]
    head, amp, tail = label.partition(" & ")
    return [head + " &", tail] if amp else [label]


def text(x: float, y: float, s: str, cls: str, anchor: str = "start") -> str:
    a = "" if anchor == "start" else f' text-anchor="{anchor}"'
    return f'<text x="{x:g}" y="{y:g}" class="{cls}"{a}>{escape(s)}</text>'


def line(x1: float, y1: float, x2: float, y2: float, color: str) -> str:
    return (
        f'<line x1="{x1:g}" y1="{y1:g}" x2="{x2:g}" y2="{y2:g}" '
        f'stroke="{color}" stroke-width="1" shape-rendering="crispEdges"/>'
    )


def dot(cx: float, cy: float, r: float, fill: str, ring: str | None = None) -> str:
    stroke = f' stroke="{ring}" stroke-width="2"' if ring else ""
    return f'<circle cx="{cx:.1f}" cy="{cy:g}" r="{r:g}" fill="{fill}"{stroke}/>'


def style(t: Theme) -> str:
    return (
        "<style>"
        f"text{{font-family:{FONT};fill:{t.ink};font-size:12.5px}}"
        ".h1{font-size:18px;font-weight:600}"
        f".sub{{fill:{t.ink2}}}"
        f".hd{{fill:{t.ink3};font-size:10.5px;font-weight:600;letter-spacing:.06em}}"
        ".dom{font-size:12px;font-weight:600}"
        f".s2{{fill:{t.ink2};font-size:12px}}"
        ".num{font-variant-numeric:tabular-nums}"
        f".tick,.foot{{fill:{t.ink3};font-size:11px}}"
        ".cnt{font-weight:600}"
        "</style>"
    )


def header(board: Board, t: Theme) -> list[str]:
    total = len(board.medals)
    sub = (
        f"{total} medals · global competitions rank {board.rank_current} of "
        f"~{compact_count(board.rank_of_about)}, peak {board.rank_peak} · "
        f"live profile checked {board.as_of}"
    )
    out = [text(X_DOMAIN, 22, f"Kaggle {board.tier}", "h1"), text(X_DOMAIN, 44, sub, "sub")]
    # Medal counts double as the colour legend. Fixed slots, right-aligned block.
    for x, medal in ((602, "gold"), (674, "silver"), (752, "bronze")):
        out.append(dot(x, 17.5, 5, t.medal[medal]))
        out.append(
            f'<text x="{x + 10}" y="22"><tspan class="cnt">{board.count(medal)}'
            f"</tspan> {medal}</text>"
        )
    cols = [
        (X_DOMAIN, "DOMAIN", "start"),
        (X_DOT - 5, "MEDAL", "start"),
        (X_NAME, "COMPETITION", "start"),
        (X_YEAR, "YEAR", "start"),
        (X_ENTRY, "ENTRY", "start"),
        (X_RANK_END, "RANK / TEAMS", "end"),
        (X_TOP_END, "TOP %", "end"),
        (X_PLOT0, "PLACEMENT, 0–10%", "start"),
    ]
    out += [text(x, HEADER_Y, s, "hd", a) for x, s, a in cols]
    out.append(line(0, HEADER_Y + 8, W, HEADER_Y + 8, t.rule))
    return out


def row(m: Medal, y: float, t: Theme) -> list[str]:
    base, mid = y + 16, y + ROW_H / 2
    return [
        dot(X_DOT, mid, 5, t.medal[m.medal]),
        text(X_DOT + 10, base, m.medal.capitalize(), "s2"),
        text(X_NAME, base, m.short, ""),
        text(X_YEAR, base, str(m.year), "s2 num"),
        text(X_ENTRY, base, m.entry.capitalize(), "s2"),
        # exact placement for the dot; the text column shows the rounded-up value
        dot(x_of(100 * m.rank / m.teams), mid, 5.5, t.medal[m.medal], ring=t.surface),
        text(X_RANK_END, base, f"{m.rank:,} / {m.teams:,}", "num", "end"),
        text(X_TOP_END, base, f"{m.top_pct:.1f}%", "s2 num", "end"),
    ]


def render_svg(board: Board, t: Theme) -> str:
    body = header(board, t)
    rows: list[str] = []
    y: float = ROWS_TOP
    for i, (label, medals) in enumerate(board.grouped()):
        if i:
            y += GROUP_GAP / 2
            body.append(line(0, y, W, y, t.rule))
            y += GROUP_GAP / 2
        for j, part in enumerate(wrap(label)):
            body.append(text(X_DOMAIN, y + 16 + 15 * j, part, "dom"))
        for m in medals:
            rows += row(m, y, t)
            y += ROW_H
    rows_bottom = y
    grid = [line(x_of(p), ROWS_TOP - 2, x_of(p), rows_bottom + 2, t.grid) for p in (0, 5, 10)]
    ticks = [text(x_of(p), rows_bottom + 16, f"{p}%", "tick num", "middle") for p in (0, 5, 10)]
    foot_y = rows_bottom + 42
    foot = [
        text(
            X_DOMAIN,
            foot_y,
            "Top % = private-leaderboard rank ÷ teams, rounded up. Lines at 5% and 10%: "
            "Kaggle's silver and bronze cutoffs for competitions with 1,000+ teams.",
            "foot",
        ),
    ]
    h = foot_y + 10
    desc = "; ".join(
        f"{m.medal} {m.title} {m.rank}/{m.teams} {m.entry} {m.year}"
        for _, ms in board.grouped()
        for m in ms
    )
    return "\n".join(
        [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{h:g}" '
            f'viewBox="0 0 {W} {h:g}" role="img" aria-labelledby="t d">',
            f'<title id="t">Kaggle {escape(board.tier)}: {len(board.medals)} medals</title>',
            f'<desc id="d">{escape(desc)}</desc>',
            style(t),
            *grid,
            *body,
            *rows,
            *ticks,
            *foot,
            "</svg>",
            "",
        ]
    )


def alt_text(board: Board) -> str:
    counts = ", ".join(f"{board.count(m)} {m}" for m in ("gold", "silver", "bronze"))
    return (
        f"Kaggle {board.tier}: {counts}. Global competitions rank {board.rank_current} of "
        f"about {compact_count(board.rank_of_about)}, peak {board.rank_peak}, checked "
        f"{board.as_of}. Full table below."
    )


def picture(board: Board) -> str:
    """The README <picture> element: dark and light boards, alt text from the data."""
    alt = escape(alt_text(board), {'"': "&quot;"})
    sources = [
        f'  <source media="(prefers-color-scheme: {name})" srcset="assets/medal-board-{name}.svg">'
        for name in ("dark", "light")
    ]
    img = f'  <img alt="{alt}" src="assets/medal-board-light.svg" width="{W}">'
    return "\n".join(["<picture>", *sources, img, "</picture>"])


def replace_block(doc: str, start_marker: str, end_marker: str, content: str) -> str:
    """Replace the text between two marker comments (markers kept, blank line padding)."""
    start, end = doc.index(start_marker), doc.index(end_marker)
    return doc[: start + len(start_marker)] + "\n\n" + content + "\n\n" + doc[end:]


def readme_with_blocks(readme: str, board: Board) -> str:
    readme = replace_block(readme, BOARD_START, BOARD_END, picture(board))
    return replace_block(readme, TABLE_START, TABLE_END, markdown_table(board))


def outputs(board: Board) -> dict[Path, str]:
    out = {
        ROOT / "assets" / f"medal-board-{t.name}.svg": render_svg(board, t) for t in (LIGHT, DARK)
    }
    if README.exists():
        out[README] = readme_with_blocks(README.read_text(encoding="utf-8"), board)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="fail if outputs are stale")
    args = ap.parse_args(argv)
    stale = []
    for path, content in outputs(load(DATA)).items():
        current = path.read_text(encoding="utf-8") if path.exists() else None
        if current == content:
            continue
        if args.check:
            stale.append(path.relative_to(ROOT).as_posix())
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            print(f"wrote {path.relative_to(ROOT).as_posix()}")
    if stale:
        print("stale, run scripts/make_medal_board.py:", ", ".join(stale), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
