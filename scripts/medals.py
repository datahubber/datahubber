"""Load, validate and format the Kaggle medal data in data/kaggle_medals.json.

Only public facts live in the data file: medal, rank, team count, solo or team,
end date, a domain label and, where I made a notable
contribution, one line on what I did. Everything derived (top %, year, counts, sort order)
is computed here so there is one source of truth.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import date
from pathlib import Path

MEDALS = ("gold", "silver", "bronze")
ENTRIES = ("solo", "team")
GITHUB_USER = "datahubber"
COMPETITION_URL = "https://www.kaggle.com/competitions/{slug}"


@dataclass(frozen=True)
class Medal:
    slug: str
    title: str
    short: str
    medal: str
    rank: int
    teams: int
    entry: str
    end_date: str
    domain: str
    repo: str | None = None
    contribution: str = ""  # what I did; left empty when not notable

    @property
    def top_pct(self) -> float:
        return top_pct(self.rank, self.teams)

    @property
    def year(self) -> int:
        return int(self.end_date[:4])

    @property
    def url(self) -> str:
        return COMPETITION_URL.format(slug=self.slug)


@dataclass(frozen=True)
class Board:
    as_of: str
    kaggle_profile: str
    tier: str
    rank_current: int
    rank_of_about: int
    rank_peak: int
    domains: tuple[tuple[str, str], ...]  # (id, label), display order
    medals: tuple[Medal, ...]

    def count(self, medal: str) -> int:
        return sum(m.medal == medal for m in self.medals)

    def grouped(self) -> list[tuple[str, list[Medal]]]:
        """Medals grouped by domain (display order), strongest first inside a group."""
        groups = []
        for domain_id, label in self.domains:
            rows = [m for m in self.medals if m.domain == domain_id]
            rows.sort(key=lambda m: (MEDALS.index(m.medal), m.rank / m.teams))
            if rows:
                groups.append((label, rows))
        return groups


def top_pct(rank: int, teams: int) -> float:
    """Rank as a percentage of teams, rounded UP to 0.1 so it never flatters."""
    if not 1 <= rank <= teams:
        raise ValueError(f"rank {rank} outside 1..{teams}")
    return math.ceil(1000 * rank / teams - 1e-9) / 10


def compact_count(n: int) -> str:
    """217000 -> '217k'."""
    return f"{round(n / 1000)}k" if n >= 10_000 else f"{n:,}"


def load(path: str | Path) -> Board:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    board = Board(
        as_of=raw["as_of"],
        kaggle_profile=raw["kaggle_profile"],
        tier=raw["tier"],
        rank_current=raw["competitions_rank"]["current"],
        rank_of_about=raw["competitions_rank"]["of_about"],
        rank_peak=raw["competitions_rank"]["peak"],
        domains=tuple((d["id"], d["label"]) for d in raw["domains"]),
        medals=tuple(Medal(**m) for m in raw["medals"]),
    )
    validate(board)
    return board


def validate(board: Board) -> None:
    domain_ids = {d for d, _ in board.domains}
    slugs = [m.slug for m in board.medals]
    if len(set(slugs)) != len(slugs):
        raise ValueError("duplicate competition slug")
    for m in board.medals:
        if m.medal not in MEDALS:
            raise ValueError(f"{m.slug}: unknown medal {m.medal!r}")
        if m.entry not in ENTRIES:
            raise ValueError(f"{m.slug}: unknown entry {m.entry!r}")
        if m.domain not in domain_ids:
            raise ValueError(f"{m.slug}: unknown domain {m.domain!r}")
        top_pct(m.rank, m.teams)  # raises on an impossible rank
        try:
            date.fromisoformat(m.end_date)
        except ValueError as e:
            raise ValueError(f"{m.slug}: end_date must be YYYY-MM-DD") from e
    if not board.rank_peak <= board.rank_current <= board.rank_of_about:
        raise ValueError("competitions rank must satisfy peak <= current <= total")


def md_cell(s: str) -> str:
    """Escape free text for a GitHub markdown table cell."""
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("|", "\\|")


def markdown_table(board: Board) -> str:
    """Medal table for the profile README, grouped by domain in board order."""
    lines = [
        "| Domain | Competition | Medal | Rank / teams | Top % | Entry | Year | My contribution |",
        "|---|---|---|--:|--:|---|--:|---|",
    ]
    for domain, rows in board.grouped():
        for i, m in enumerate(rows):
            name = f"[{md_cell(m.short)}]({m.url})"
            if m.repo:
                name += f" · [repo](https://github.com/{GITHUB_USER}/{m.repo})"
            label = md_cell(domain) if i == 0 else ""
            result = f"{m.rank:,}&nbsp;/&nbsp;{m.teams:,}"
            lines.append(
                f"| {label} | {name} | {m.medal.capitalize()} | {result} | {m.top_pct:.1f}% "
                f"| {m.entry.capitalize()} | {m.year} | {md_cell(m.contribution)} |"
            )
    return "\n".join(lines)
