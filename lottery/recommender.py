"""Weekly number combination generators with transparent strategies."""

from __future__ import annotations

from dataclasses import dataclass
import random
import secrets

from lottery.fetcher import GAME_CONFIGS
from lottery.stats import GameStats


@dataclass(frozen=True)
class TicketRecommendation:
    """Single recommended lottery ticket."""

    strategy: str
    strategy_label: str
    main_numbers: tuple[int, ...]
    special: int | None
    note: str


def _max_consecutive_run(nums: tuple[int, ...]) -> int:
    """Return length of longest consecutive integer run in sorted tuple."""
    if not nums:
        return 0
    best = 1
    cur = 1
    for a, b in zip(nums, nums[1:]):
        if b == a + 1:
            cur += 1
            best = max(best, cur)
        else:
            cur = 1
    return best


def _passes_anti_popular_filters(nums: tuple[int, ...], main_max: int) -> bool:
    """Filter out patterns commonly over-bet by humans to reduce split-jackpot risk."""
    # Avoid >= 5 numbers falling in the 1-31 calendar birthday range.
    birthday_count = sum(1 for n in nums if n <= 31)
    if birthday_count >= 5:
        return False
    # Avoid 3 or more consecutive numbers (e.g. 12, 13, 14).
    if _max_consecutive_run(nums) >= 3:
        return False
    # Avoid all numbers sharing few last digits (<= 3 unique trailing digits).
    if len({n % 10 for n in nums}) <= 3:
        return False
    # Avoid pure arithmetic progression or constant gaps.
    diffs = {b - a for a, b in zip(nums, nums[1:])}
    if len(diffs) <= 1:
        return False
    # Keep a reasonable spread across low and high halves.
    midpoint = main_max / 2.0
    low_count = sum(1 for n in nums if n <= midpoint)
    if low_count < 1 or low_count > 5:
        return False
    return True


def _weighted_sample_without_replacement(
    items: list[int], weights: list[float], k: int, rng: random.Random
) -> tuple[int, ...]:
    """Sample k distinct items without replacement proportional to positive weights."""
    pool = list(items)
    w = list(weights)
    chosen: list[int] = []
    for _ in range(k):
        pick = rng.choices(pool, weights=w, k=1)[0]
        idx = pool.index(pick)
        chosen.append(pick)
        pool.pop(idx)
        w.pop(idx)
    return tuple(sorted(chosen))


def generate_anti_popular_tickets(
    game: str, count: int = 3, rng: random.Random | None = None
) -> list[TicketRecommendation]:
    """Uniform random picks filtered to avoid popular human patterns (reduces split risk)."""
    cfg = GAME_CONFIGS[game]
    sys_rng = rng or secrets.SystemRandom()
    main_pool = list(range(1, cfg["main_max"] + 1))
    tickets: list[TicketRecommendation] = []
    seen: set[tuple[tuple[int, ...], int | None]] = set()

    attempts = 0
    while len(tickets) < count and attempts < 5000:
        attempts += 1
        main_nums = tuple(sorted(sys_rng.sample(main_pool, cfg["main_count"])))
        if not _passes_anti_popular_filters(main_nums, cfg["main_max"]):
            continue
        special = (
            sys_rng.randint(1, cfg["special_max"]) if game == "super638" else None
        )
        # For Super Lotto Zone 2, slightly prefer less birthday/lucky numbers when anti-popular?
        # Keep Zone 2 uniform so it remains unbiased.
        key = (main_nums, special)
        if key in seen:
            continue
        seen.add(key)
        tickets.append(
            TicketRecommendation(
                strategy="anti_popular",
                strategy_label="理性避撞號（均勻隨機＋避開生日連號）",
                main_numbers=main_nums,
                special=special,
                note="與所有組合中獎率相同，但避開 1-31 集中與連號，降低頭獎多人平分機率",
            )
        )
    return tickets


def generate_statistical_tickets(
    stats: GameStats, count: int = 2, rng: random.Random | None = None
) -> list[TicketRecommendation]:
    """Generate tickets weighted by historical frequency, recent trend, and overdue draws.

    Note: Purely for statistical preference / entertainment; does not increase true win odds.
    """
    cfg = GAME_CONFIGS[stats.game]
    rand = rng or secrets.SystemRandom()
    items = [s.number for s in stats.main_stats]

    max_total = max(s.total_count for s in stats.main_stats) or 1
    max_recent = max(s.recent_count for s in stats.main_stats) or 1
    max_overdue = max(s.overdue_draws for s in stats.main_stats) or 1

    # Blend normalized long-term frequency (40%), recent-100 frequency (35%), overdue (25%).
    weights = [
        0.5
        + 0.40 * (s.total_count / max_total)
        + 0.35 * (s.recent_count / max_recent)
        + 0.25 * (s.overdue_draws / max_overdue)
        for s in stats.main_stats
    ]

    special_items = [s.number for s in stats.special_stats]
    max_sp = max(s.total_count for s in stats.special_stats) or 1
    special_weights = [0.5 + 0.5 * (s.total_count / max_sp) for s in stats.special_stats]

    tickets: list[TicketRecommendation] = []
    seen: set[tuple[tuple[int, ...], int | None]] = set()
    attempts = 0
    while len(tickets) < count and attempts < 2000:
        attempts += 1
        main_nums = _weighted_sample_without_replacement(items, weights, cfg["main_count"], rand)
        # Keep odd/even balance (2:4, 3:3, or 4:2).
        odds = sum(1 for n in main_nums if n % 2 == 1)
        if odds not in (2, 3, 4):
            continue
        special = (
            rand.choices(special_items, weights=special_weights, k=1)[0]
            if stats.game == "super638"
            else None
        )
        key = (main_nums, special)
        if key in seen:
            continue
        seen.add(key)
        tickets.append(
            TicketRecommendation(
                strategy="statistical",
                strategy_label="統計權重選號（熱號＋近期＋遺漏加權＋奇偶平衡）",
                main_numbers=main_nums,
                special=special,
                note="依歷史頻率與奇偶平衡抽樣（僅供統計偏好參考，實際中獎率與機選相同）",
            )
        )
    return tickets


def build_weekly_recommendations(
    stats: GameStats, anti_popular_count: int = 3, statistical_count: int = 2
) -> list[TicketRecommendation]:
    """Build combined weekly recommendations for one lottery game."""
    return generate_anti_popular_tickets(stats.game, count=anti_popular_count) + (
        generate_statistical_tickets(stats, count=statistical_count)
    )
