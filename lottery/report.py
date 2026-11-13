"""Markdown report generator for weekly lottery stats and recommendations."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from lottery.fetcher import GAME_CONFIGS
from lottery.recommender import TicketRecommendation
from lottery.stats import GameStats


TZ_TAIPEI = timezone(timedelta(hours=8))


def _fmt_nums(nums: tuple[int, ...] | list[int]) -> str:
    return " ".join(f"{n:02d}" for n in nums)


def _fmt_ticket(t: TicketRecommendation, game: str) -> str:
    main_str = _fmt_nums(t.main_numbers)
    if game == "super638" and t.special is not None:
        return f"`{main_str}` + 第二區 `{t.special:02d}`"
    return f"`{main_str}`"


def _randomness_verdict(pvalue: float) -> str:
    if pvalue >= 0.05:
        return f"p = {pvalue:.4f} (≥ 0.05，符合均勻隨機分布，無顯著偏差)"
    return f"p = {pvalue:.4f} (< 0.05，統計上存在輕微偏移，建議持續觀察)"


def render_game_section(stats: GameStats, tickets: list[TicketRecommendation]) -> str:
    """Render Markdown section for a single game."""
    cfg = GAME_CONFIGS[stats.game]
    latest = stats.latest_draw
    special_label = cfg["special_label"]

    hot_str = "、".join(f"{s.number:02d}({s.total_count}次)" for s in stats.hot_main)
    cold_str = "、".join(f"{s.number:02d}({s.total_count}次)" for s in stats.cold_main)
    overdue_str = "、".join(f"{s.number:02d}(連{s.overdue_draws}期未開)" for s in stats.overdue_main)

    lines = [
        f"## {stats.name_zh}（{stats.game}）",
        "",
        f"- **資料庫涵蓋範圍**：`{stats.first_date}` ～ `{stats.last_date}`（共 **{stats.total_draws:,}** 期）",
        (
            f"- **最新開獎（第 {latest.period} 期，{latest.lottery_date}）**："
            f"`{_fmt_nums(latest.main_numbers)}` ＋ {special_label} `{latest.special:02d}`"
        ),
        (
            f"- **隨機性卡方檢定（主號）**："
            f"χ² = {stats.main_chi2:.2f}, {_randomness_verdict(stats.main_pvalue)}"
        ),
        (
            f"- **隨機性卡方檢定（{special_label}）**："
            f"χ² = {stats.special_chi2:.2f}, {_randomness_verdict(stats.special_pvalue)}"
        ),
        f"- **歷史最常開（前 6）**：{hot_str}",
        f"- **歷史最少開（前 6）**：{cold_str}",
        f"- **目前最久未開（前 6）**：{overdue_str}",
        "",
        "### 本週選號建議",
        "",
        "| # | 策略 | 建議號碼 | 說明 |",
        "|---|---|---|---|",
    ]
    for idx, t in enumerate(tickets, start=1):
        lines.append(f"| {idx} | {t.strategy_label} | {_fmt_ticket(t, stats.game)} | {t.note} |")

    lines.append("")
    return "\n".join(lines)


def render_full_report(
    game_sections: list[tuple[GameStats, list[TicketRecommendation]]],
    generated_at: datetime | None = None,
) -> str:
    """Render complete weekly Markdown report across all configured games."""
    now = generated_at or datetime.now(TZ_TAIPEI)
    ts = now.strftime("%Y-%m-%d %H:%M (%Z)")
    parts = [
        f"# 台灣彩券每週開獎統計與選號報告",
        "",
        f"產生時間：`{ts}`",
        "",
        "> **數學提醒**：樂透為獨立隨機事件，過去開獎紀錄無法提升下一期的實際中獎機率。"
        "本報告提供卡方隨機檢定與兩種選號邏輯：「理性避撞號」旨在降低中頭獎時與他人平分獎金的風險；"
        "「統計權重選號」僅供個人偏好與娛樂參考，請量力而為。",
        "",
    ]
    for stats, tickets in game_sections:
        parts.append(render_game_section(stats, tickets))
    return "\n".join(parts)
