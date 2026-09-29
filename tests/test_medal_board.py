import xml.etree.ElementTree as ET
from dataclasses import replace
from pathlib import Path

import make_medal_board as mb
from medals import load

FIXTURE = Path(__file__).parent / "fixtures" / "mini_medals.json"
SVG = "{http://www.w3.org/2000/svg}"


def test_svg_is_well_formed_and_has_one_plot_dot_per_medal():
    board = load(FIXTURE)
    for theme in (mb.LIGHT, mb.DARK):
        root = ET.fromstring(mb.render_svg(board, theme))
        assert root.tag == f"{SVG}svg"
        circles = root.findall(f"{SVG}circle")
        # 3 legend dots + (medal-column dot + plot dot) per row
        assert len(circles) == 3 + 2 * len(board.medals)
        texts = "".join(t.text or "" for t in root.iter(f"{SVG}text"))
        assert "A & Co" in texts  # escaped on write, round-trips on parse


def test_render_is_deterministic_and_themes_differ():
    board = load(FIXTURE)
    light = mb.render_svg(board, mb.LIGHT)
    assert light == mb.render_svg(board, mb.LIGHT)
    assert light != mb.render_svg(board, mb.DARK)


def test_plot_scale_is_clamped():
    assert mb.x_of(0) == mb.X_PLOT0
    assert mb.x_of(mb.PLOT_MAX) == mb.X_PLOT1
    assert mb.x_of(50) == mb.X_PLOT1


def test_domain_labels_wrap_after_ampersand():
    assert mb.wrap("Vision & 3D imaging") == ["Vision &", "3D imaging"]
    assert mb.wrap("LLM & NLP") == ["LLM & NLP"]
    assert mb.wrap("Tabular") == ["Tabular"]


def test_readme_blocks_replacement_is_idempotent_and_keeps_outer_text():
    board = load(FIXTURE)
    doc = (
        f"intro\n{mb.BOARD_START}\nold board\n{mb.BOARD_END}\nmiddle\n"
        f"{mb.TABLE_START}\nold table\n{mb.TABLE_END}\noutro\n"
    )
    once = mb.readme_with_blocks(doc, board)
    assert "old board" not in once and "old table" not in once
    assert once.startswith("intro\n") and "\nmiddle\n" in once and once.endswith("outro\n")
    assert mb.readme_with_blocks(once, board) == once


def test_picture_alt_text_comes_from_the_data():
    board = load(FIXTURE)
    pic = mb.picture(board)
    assert "1 gold, 1 silver, 1 bronze" in pic
    assert "rank 500 of about 100k, peak 400, checked 2000-01-31" in pic
    assert pic.count("<source") == 2 and 'width="830"' in pic


def test_svg_footnote_explains_top_pct_and_desc_lists_medals():
    root = ET.fromstring(mb.render_svg(load(FIXTURE), mb.LIGHT))
    texts = " ".join(t.text or "" for t in root.iter(f"{SVG}text"))
    assert "Top % = private-leaderboard rank" in texts
    desc = root.find(f"{SVG}desc")
    assert desc is not None and len((desc.text or "").split("; ")) == len(load(FIXTURE).medals)


def test_plot_dot_uses_exact_placement_not_rounded_text():
    # 366 / 3677 = 9.954 %: the text says 10.0 %, the dot sits just inside the 10 % line
    m = replace(load(FIXTURE).medals[0], rank=366, teams=3677)
    assert m.top_pct == 10.0
    exact = mb.x_of(100 * 366 / 3677)
    assert exact < mb.x_of(10.0)
    plot_dot = mb.row(m, 0, mb.LIGHT)[5]
    assert f'cx="{exact:.1f}"' in plot_dot


def test_committed_outputs_are_up_to_date():
    assert mb.main(["--check"]) == 0
