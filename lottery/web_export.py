"""Export lottery analytics and recommendations to JSON for GitHub Pages UI."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from typing import Any

from lottery.fetcher import DrawRecord, GAME_CONFIGS
from lottery.recommender import TicketRecommendation
from lottery.stats import GameStats


TZ_TAIPEI = timezone(timedelta(hours=8))


def _serialize_draw(d: DrawRecord) -> dict[str, Any]:
    return {
        "period": d.period,
        "lottery_date": d.lottery_date,
        "main_numbers": list(d.main_numbers),
        "special": d.special,
        "appear_order": [int(x) for x in d.appear_order.split(",") if x],
        "sell_amount": d.sell_amount,
        "total_amount": d.total_amount,
        "jackpot_winners": d.jackpot_winners,
        "jackpot_per_prize": d.jackpot_per_prize,
    }


def build_web_data(
    game_entries: list[tuple[GameStats, list[TicketRecommendation], list[DrawRecord]]],
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    """Build JSON-serializable payload consumed by docs/index.html."""
    now = generated_at or datetime.now(TZ_TAIPEI)
    games_payload: dict[str, Any] = {}

    for stats, tickets, draws in game_entries:
        cfg = GAME_CONFIGS[stats.game]
        recent_draws = [_serialize_draw(d) for d in reversed(draws[-10:])]
        games_payload[stats.game] = {
            "game": stats.game,
            "name_zh": stats.name_zh,
            "main_max": cfg["main_max"],
            "main_count": cfg["main_count"],
            "special_max": cfg["special_max"],
            "special_label": cfg["special_label"],
            "total_draws": stats.total_draws,
            "first_date": stats.first_date,
            "last_date": stats.last_date,
            "latest_draw": _serialize_draw(stats.latest_draw),
            "recent_draws": recent_draws,
            "chi_square": {
                "main_chi2": round(stats.main_chi2, 4),
                "main_pvalue": round(stats.main_pvalue, 6),
                "special_chi2": round(stats.special_chi2, 4),
                "special_pvalue": round(stats.special_pvalue, 6),
            },
            "hot_main": [asdict(s) for s in stats.hot_main],
            "cold_main": [asdict(s) for s in stats.cold_main],
            "overdue_main": [asdict(s) for s in stats.overdue_main],
            "main_stats": [asdict(s) for s in stats.main_stats],
            "special_stats": [asdict(s) for s in stats.special_stats],
            "recommendations": [
                {
                    "strategy": t.strategy,
                    "strategy_label": t.strategy_label,
                    "main_numbers": list(t.main_numbers),
                    "special": t.special,
                    "note": t.note,
                }
                for t in tickets
            ],
        }

    return {
        "generated_at": now.strftime("%Y-%m-%d %H:%M (%Z)"),
        "generated_iso": now.isoformat(),
        "games": games_payload,
    }


def write_web_data(
    game_entries: list[tuple[GameStats, list[TicketRecommendation], list[DrawRecord]]],
    out_path: Path,
    generated_at: datetime | None = None,
) -> Path:
    """Write web JSON snapshot to disk."""
    payload = build_web_data(game_entries, generated_at=generated_at)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_path
