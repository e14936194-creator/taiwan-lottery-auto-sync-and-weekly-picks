"""SQLite persistence and CSV export for lottery draw records."""

from __future__ import annotations

import csv
from pathlib import Path
import sqlite3

from lottery.fetcher import DrawRecord


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS draws (
    game TEXT NOT NULL,
    period INTEGER NOT NULL,
    lottery_date TEXT NOT NULL,
    n1 INTEGER NOT NULL,
    n2 INTEGER NOT NULL,
    n3 INTEGER NOT NULL,
    n4 INTEGER NOT NULL,
    n5 INTEGER NOT NULL,
    n6 INTEGER NOT NULL,
    special INTEGER NOT NULL,
    appear_order TEXT NOT NULL,
    sell_amount INTEGER NOT NULL DEFAULT 0,
    total_amount INTEGER NOT NULL DEFAULT 0,
    jackpot_winners INTEGER NOT NULL DEFAULT 0,
    jackpot_per_prize INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (game, period)
);

CREATE INDEX IF NOT EXISTS idx_draws_game_date
ON draws (game, lottery_date DESC, period DESC);
"""


def connect_db(db_path: Path) -> sqlite3.Connection:
    """Open SQLite database and ensure schema exists."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA_SQL)
    return conn


def get_known_periods(conn: sqlite3.Connection, game: str) -> set[int]:
    """Return all period IDs already stored for the given game."""
    rows = conn.execute("SELECT period FROM draws WHERE game = ?", (game,)).fetchall()
    return {int(row["period"]) for row in rows}


def upsert_draws(conn: sqlite3.Connection, records: list[DrawRecord]) -> int:
    """Insert or update draw records and return count written."""
    if not records:
        return 0
    sql = """
    INSERT INTO draws (
        game, period, lottery_date, n1, n2, n3, n4, n5, n6, special,
        appear_order, sell_amount, total_amount, jackpot_winners, jackpot_per_prize
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(game, period) DO UPDATE SET
        lottery_date = excluded.lottery_date,
        n1 = excluded.n1, n2 = excluded.n2, n3 = excluded.n3,
        n4 = excluded.n4, n5 = excluded.n5, n6 = excluded.n6,
        special = excluded.special,
        appear_order = excluded.appear_order,
        sell_amount = excluded.sell_amount,
        total_amount = excluded.total_amount,
        jackpot_winners = excluded.jackpot_winners,
        jackpot_per_prize = excluded.jackpot_per_prize
    """
    params = [
        (
            r.game,
            r.period,
            r.lottery_date,
            r.n1,
            r.n2,
            r.n3,
            r.n4,
            r.n5,
            r.n6,
            r.special,
            r.appear_order,
            r.sell_amount,
            r.total_amount,
            r.jackpot_winners,
            r.jackpot_per_prize,
        )
        for r in records
    ]
    with conn:
        conn.executemany(sql, params)
    return len(params)


def load_draws(conn: sqlite3.Connection, game: str) -> list[DrawRecord]:
    """Load all draws for a game ordered oldest to newest."""
    rows = conn.execute(
        """
        SELECT game, period, lottery_date, n1, n2, n3, n4, n5, n6, special,
               appear_order, sell_amount, total_amount, jackpot_winners, jackpot_per_prize
        FROM draws
        WHERE game = ?
        ORDER BY lottery_date ASC, period ASC
        """,
        (game,),
    ).fetchall()
    return [DrawRecord(**dict(row)) for row in rows]


def export_csv(conn: sqlite3.Connection, game: str, out_path: Path) -> int:
    """Export draws for a game (newest first) to CSV."""
    draws = list(reversed(load_draws(conn, game)))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "game",
        "period",
        "lottery_date",
        "n1",
        "n2",
        "n3",
        "n4",
        "n5",
        "n6",
        "special",
        "appear_order",
        "sell_amount",
        "total_amount",
        "jackpot_winners",
        "jackpot_per_prize",
    ]
    with out_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for d in draws:
            writer.writerow(
                {
                    "game": d.game,
                    "period": d.period,
                    "lottery_date": d.lottery_date,
                    "n1": d.n1,
                    "n2": d.n2,
                    "n3": d.n3,
                    "n4": d.n4,
                    "n5": d.n5,
                    "n6": d.n6,
                    "special": d.special,
                    "appear_order": d.appear_order,
                    "sell_amount": d.sell_amount,
                    "total_amount": d.total_amount,
                    "jackpot_winners": d.jackpot_winners,
                    "jackpot_per_prize": d.jackpot_per_prize,
                }
            )
    return len(draws)
