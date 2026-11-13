"""Pure-Python statistical analysis and chi-square randomness testing."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import math

from lottery.fetcher import DrawRecord, GAME_CONFIGS


def _gammaincc(a: float, x: float) -> float:
    """Compute regularized upper incomplete gamma Q(a, x) = 1 - P(a, x) for p-values."""
    if x <= 0.0:
        return 1.0
    if a <= 0.0:
        raise ValueError("Parameter 'a' must be positive.")

    eps = 1e-12
    fpmin = 1e-30
    gln = math.lgamma(a)

    if x < a + 1.0:
        # Series representation for P(a, x)
        ap = a
        total = 1.0 / a
        delta = total
        for _ in range(500):
            ap += 1.0
            delta *= x / ap
            total += delta
            if abs(delta) < abs(total) * eps:
                break
        p_val = total * math.exp(-x + a * math.log(x) - gln)
        return max(0.0, min(1.0, 1.0 - p_val))

    # Lentz's continued fraction for Q(a, x)
    b = x + 1.0 - a
    c = 1.0 / fpmin
    d = 1.0 / b if abs(b) > fpmin else 1.0 / fpmin
    h = d
    for i in range(1, 500):
        an = -i * (i - a)
        b += 2.0
        d = an * d + b
        if abs(d) < fpmin:
            d = fpmin
        c = b + an / c
        if abs(c) < fpmin:
            c = fpmin
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < eps:
            break
    q_val = math.exp(-x + a * math.log(x) - gln) * h
    return max(0.0, min(1.0, q_val))


def chi_square_pvalue(chi2_stat: float, df: int) -> float:
    """Return right-tail p-value for a chi-square statistic with df degrees of freedom."""
    if df <= 0:
        raise ValueError("Degrees of freedom must be positive.")
    return _gammaincc(df / 2.0, chi2_stat / 2.0)


@dataclass(frozen=True)
class NumberStat:
    """Per-number historical statistics."""

    number: int
    total_count: int
    recent_count: int
    overdue_draws: int
    expected_count: float
    z_score: float


@dataclass(frozen=True)
class GameStats:
    """Aggregated statistics and uniformity test results for one lottery game."""

    game: str
    name_zh: str
    total_draws: int
    first_date: str
    last_date: str
    latest_draw: DrawRecord
    main_stats: list[NumberStat]
    special_stats: list[NumberStat]
    main_chi2: float
    main_pvalue: float
    special_chi2: float
    special_pvalue: float
    hot_main: list[NumberStat]
    cold_main: list[NumberStat]
    overdue_main: list[NumberStat]


def _compute_number_stats(
    draws: list[DrawRecord],
    pool_max: int,
    picks_per_draw: int,
    recent_window: int,
    is_special: bool,
) -> tuple[list[NumberStat], float, float]:
    n_draws = len(draws)
    counts: Counter[int] = Counter()
    recent_counts: Counter[int] = Counter()
    last_seen_idx: dict[int, int] = {}

    recent_start = max(0, n_draws - recent_window)
    for idx, draw in enumerate(draws):
        nums = (draw.special,) if is_special else draw.main_numbers
        for num in nums:
            counts[num] += 1
            last_seen_idx[num] = idx
            if idx >= recent_start:
                recent_counts[num] += 1

    expected = n_draws * picks_per_draw / pool_max
    # Exact variance of frequency when drawing k balls without replacement from M:
    # Var = N * p * (1 - p), where p = k / M.
    p = picks_per_draw / pool_max
    std_dev = math.sqrt(n_draws * p * (1.0 - p)) if n_draws > 0 else 1.0

    stats: list[NumberStat] = []
    raw_pearson = 0.0
    for num in range(1, pool_max + 1):
        cnt = counts[num]
        overdue = (n_draws - 1 - last_seen_idx[num]) if num in last_seen_idx else n_draws
        z = (cnt - expected) / std_dev if std_dev > 0 else 0.0
        if expected > 0:
            raw_pearson += ((cnt - expected) ** 2) / expected
        stats.append(
            NumberStat(
                number=num,
                total_count=cnt,
                recent_count=recent_counts[num],
                overdue_draws=overdue,
                expected_count=expected,
                z_score=z,
            )
        )

    # Finite-population correction for sampling k balls without replacement per draw:
    # Eigenvalue on sum(delta)=0 is N * k*(M-k) / (M*(M-1)), so multiply Pearson sum by (M-1)/(M-k).
    fpc = (pool_max - 1) / (pool_max - picks_per_draw) if pool_max > picks_per_draw else 1.0
    chi2_stat = raw_pearson * fpc
    p_val = chi_square_pvalue(chi2_stat, pool_max - 1) if n_draws > 0 else 1.0
    return stats, chi2_stat, p_val


def analyze_game(game: str, draws: list[DrawRecord], recent_window: int = 100) -> GameStats:
    """Compute complete historical statistics and chi-square tests for a game."""
    if not draws:
        raise ValueError(f"No draw records available for {game}.")
    cfg = GAME_CONFIGS[game]

    main_stats, main_chi2, main_p = _compute_number_stats(
        draws=draws,
        pool_max=cfg["main_max"],
        picks_per_draw=cfg["main_count"],
        recent_window=recent_window,
        is_special=False,
    )
    special_stats, special_chi2, special_p = _compute_number_stats(
        draws=draws,
        pool_max=cfg["special_max"],
        picks_per_draw=1,
        recent_window=recent_window,
        is_special=True,
    )

    hot_main = sorted(main_stats, key=lambda s: (-s.total_count, s.number))[:6]
    cold_main = sorted(main_stats, key=lambda s: (s.total_count, s.number))[:6]
    overdue_main = sorted(main_stats, key=lambda s: (-s.overdue_draws, s.number))[:6]

    return GameStats(
        game=game,
        name_zh=cfg["name_zh"],
        total_draws=len(draws),
        first_date=draws[0].lottery_date,
        last_date=draws[-1].lottery_date,
        latest_draw=draws[-1],
        main_stats=main_stats,
        special_stats=special_stats,
        main_chi2=main_chi2,
        main_pvalue=main_p,
        special_chi2=special_chi2,
        special_pvalue=special_p,
        hot_main=hot_main,
        cold_main=cold_main,
        overdue_main=overdue_main,
    )
