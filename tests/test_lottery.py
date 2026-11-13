"""Unit tests for fetcher parsing, SQLite storage, chi-square math, and recommenders."""

from __future__ import annotations

from pathlib import Path
import json
import random
import tempfile
import unittest

from lottery.db import connect_db, export_csv, get_known_periods, load_draws, upsert_draws
from lottery.fetcher import DrawRecord, parse_draw_record
from lottery.recommender import (
    _passes_anti_popular_filters,
    generate_anti_popular_tickets,
    generate_statistical_tickets,
)
from lottery.report import render_full_report
from lottery.stats import analyze_game, chi_square_pvalue
from lottery.web_export import write_web_data


def _make_sample_draws(game: str, count: int = 80) -> list[DrawRecord]:
    rng = random.Random(42)
    max_main = 49 if game == "lotto649" else 38
    max_special = 49 if game == "lotto649" else 8
    draws: list[DrawRecord] = []
    for i in range(count):
        nums = sorted(rng.sample(range(1, max_main + 1), 6))
        sp = rng.randint(1, max_special)
        draws.append(
            DrawRecord(
                game=game,
                period=115000001 + i,
                lottery_date=f"2026-01-{(i % 28) + 1:02d}",
                n1=nums[0],
                n2=nums[1],
                n3=nums[2],
                n4=nums[3],
                n5=nums[4],
                n6=nums[5],
                special=sp,
                appear_order=",".join(str(x) for x in [*nums, sp]),
                sell_amount=100000000,
                total_amount=50000000,
                jackpot_winners=0,
                jackpot_per_prize=0,
            )
        )
    return draws


class TestLotteryPipeline(unittest.TestCase):
    def test_parse_draw_record(self) -> None:
        raw = {
            "period": 115000104,
            "lotteryDate": "2026-11-10T00:00:00",
            "drawNumberSize": [11, 23, 30, 32, 40, 41, 28],
            "drawNumberAppear": [23, 41, 40, 30, 32, 11, 28],
            "sellAmount": 94686000,
            "totalAmount": 54986601,
            "jackpotAssign": {"winnerCount": 0, "perPrize": 0},
        }
        rec = parse_draw_record("lotto649", raw)
        self.assertEqual(rec.period, 115000104)
        self.assertEqual(rec.lottery_date, "2026-11-10")
        self.assertEqual(rec.main_numbers, (11, 23, 30, 32, 40, 41))
        self.assertEqual(rec.special, 28)

    def test_db_roundtrip_and_csv_export(self) -> None:
        draws = _make_sample_draws("super638", count=10)
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.db"
            csv_path = Path(tmp) / "super638.csv"
            conn = connect_db(db_path)
            try:
                written = upsert_draws(conn, draws)
                self.assertEqual(written, 10)
                known = get_known_periods(conn, "super638")
                self.assertEqual(len(known), 10)
                loaded = load_draws(conn, "super638")
                self.assertEqual(len(loaded), 10)
                exported = export_csv(conn, "super638", csv_path)
                self.assertEqual(exported, 10)
                self.assertTrue(csv_path.exists())
            finally:
                conn.close()

    def test_chi_square_pvalue_known_critical_values(self) -> None:
        # Known 5% upper critical values: df=1 -> 3.8415, df=7 -> 14.0671, df=48 -> 65.1708
        self.assertAlmostEqual(chi_square_pvalue(3.8415, 1), 0.05, places=3)
        self.assertAlmostEqual(chi_square_pvalue(14.0671, 7), 0.05, places=3)
        self.assertAlmostEqual(chi_square_pvalue(65.1708, 48), 0.05, places=3)

    def test_anti_popular_filter_rejects_birthdays_and_runs(self) -> None:
        self.assertFalse(_passes_anti_popular_filters((1, 2, 3, 15, 22, 30), 49))
        self.assertFalse(_passes_anti_popular_filters((5, 10, 15, 20, 25, 30), 49))
        self.assertTrue(_passes_anti_popular_filters((4, 17, 29, 34, 41, 48), 49))

    def test_recommenders_and_report_generation(self) -> None:
        lotto_draws = _make_sample_draws("lotto649", count=120)
        super_draws = _make_sample_draws("super638", count=120)

        lotto_stats = analyze_game("lotto649", lotto_draws)
        super_stats = analyze_game("super638", super_draws)

        rng = random.Random(123)
        lotto_tickets = generate_anti_popular_tickets("lotto649", count=3, rng=rng) + (
            generate_statistical_tickets(lotto_stats, count=2, rng=rng)
        )
        super_tickets = generate_anti_popular_tickets("super638", count=3, rng=rng) + (
            generate_statistical_tickets(super_stats, count=2, rng=rng)
        )

        self.assertEqual(len(lotto_tickets), 5)
        self.assertEqual(len(super_tickets), 5)
        for t in lotto_tickets:
            self.assertEqual(len(set(t.main_numbers)), 6)
            self.assertIsNone(t.special)
        for t in super_tickets:
            self.assertEqual(len(set(t.main_numbers)), 6)
            self.assertIsNotNone(t.special)
            self.assertTrue(1 <= t.special <= 8)

        md = render_full_report([(lotto_stats, lotto_tickets), (super_stats, super_tickets)])
        self.assertIn("大樂透", md)
        self.assertIn("威力彩", md)
        self.assertIn("隨機性卡方檢定", md)

        with tempfile.TemporaryDirectory() as tmp:
            web_json = Path(tmp) / "data.json"
            write_web_data(
                [
                    (lotto_stats, lotto_tickets, lotto_draws),
                    (super_stats, super_tickets, super_draws),
                ],
                web_json,
            )
            payload = json.loads(web_json.read_text(encoding="utf-8"))
            self.assertIn("lotto649", payload["games"])
            self.assertIn("super638", payload["games"])
            self.assertEqual(len(payload["games"]["lotto649"]["recent_draws"]), 10)
            self.assertEqual(len(payload["games"]["lotto649"]["main_stats"]), 49)
            self.assertEqual(len(payload["games"]["super638"]["special_stats"]), 8)


if __name__ == "__main__":
    unittest.main()
