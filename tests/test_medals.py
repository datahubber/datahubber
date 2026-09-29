import json
from pathlib import Path

import pytest

from medals import compact_count, load, markdown_table, md_cell, top_pct

FIXTURE = Path(__file__).parent / "fixtures" / "mini_medals.json"
REAL = Path(__file__).parent.parent / "data" / "kaggle_medals.json"


def test_top_pct_rounds_up_never_flatters():
    assert top_pct(5, 950) == 0.6  # 0.526 % -> 0.6 %
    assert top_pct(366, 3677) == 10.0  # 9.954 % -> 10.0 %
    assert top_pct(100, 1000) == 10.0  # exact values stay exact
    assert top_pct(1, 1000) == 0.1


@pytest.mark.parametrize("rank,teams", [(0, 10), (11, 10)])
def test_top_pct_rejects_impossible_rank(rank, teams):
    with pytest.raises(ValueError):
        top_pct(rank, teams)


def test_compact_count():
    assert compact_count(217_000) == "217k"
    assert compact_count(950) == "950"


def test_load_groups_in_domain_order_strongest_first():
    board = load(FIXTURE)
    groups = board.grouped()
    assert [label for label, _ in groups] == ["Text & speech", "Vision"]  # empty domain dropped
    assert [m.slug for m in groups[0][1]] == ["comp-a", "comp-b"]  # gold before bronze
    assert (board.count("gold"), board.count("silver"), board.count("bronze")) == (1, 1, 1)
    assert groups[0][1][0].year == 1999


@pytest.mark.parametrize(
    "field,value",
    [
        ("medal", "platinum"),
        ("entry", "duo"),
        ("domain", "audio"),
        ("end_date", "1999-13-01"),
        ("rank", 2000),
    ],
)
def test_validate_rejects_bad_rows(tmp_path, field, value):
    raw = json.loads(FIXTURE.read_text())
    raw["medals"][0][field] = value
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(raw))
    with pytest.raises(ValueError):
        load(bad)


def test_markdown_table_links_repo_only_where_given():
    table = markdown_table(load(FIXTURE))
    rows = table.splitlines()[2:]
    assert len(rows) == 3
    assert "[repo](https://github.com/datahubber/comp-a-solution)" in rows[0]
    assert "[repo]" not in rows[1] + rows[2]
    assert "| Gold | 3&nbsp;/&nbsp;500 |" in rows[0]


def test_markdown_table_has_eight_columns_and_escapes_text():
    rows = markdown_table(load(FIXTURE)).splitlines()
    for row in rows:
        assert row.count("|") - row.count("\\|") == 9
    assert any("Built the &lt;post-processor&gt; \\| tuned it |" in r for r in rows)
    assert md_cell("a & b") == "a &amp; b"


def test_real_data_matches_profile_summary():
    board = load(REAL)
    assert len(board.medals) == 11
    assert (board.count("gold"), board.count("silver"), board.count("bronze")) == (1, 3, 7)
    assert sum(m.entry == "solo" for m in board.medals) == 7
    assert {m.domain for m in board.medals} == {d for d, _ in board.domains}
    assert all(m.contribution for m in board.medals if m.repo)
    with_repo = sorted(m.slug for m in board.medals if m.repo)
    assert with_repo == ["hull-tactical-market-prediction", "wsdm-cup-multilingual-chatbot-arena"]
