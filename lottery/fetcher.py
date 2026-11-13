"""Client for Taiwan Lottery official backend JSON API."""

from __future__ import annotations

from dataclasses import dataclass
import json
import time
import urllib.error
import urllib.request
from typing import Any


BASE_URL = "https://api.taiwanlottery.com/TLCAPIWeB/Lottery"

GAME_CONFIGS: dict[str, dict[str, Any]] = {
    "lotto649": {
        "name_zh": "大樂透",
        "endpoint": "Lotto649Result",
        "res_key": "lotto649Res",
        "jackpot_key": "jackpotAssign",
        "start_month": "2007-01",
        "main_max": 49,
        "main_count": 6,
        "special_max": 49,
        "special_label": "特別號",
    },
    "super638": {
        "name_zh": "威力彩",
        "endpoint": "SuperLotto638Result",
        "res_key": "superLotto638Res",
        "jackpot_key": "super638JackpotAssign",
        "start_month": "2008-01",
        "main_max": 38,
        "main_count": 6,
        "special_max": 8,
        "special_label": "第二區",
    },
}

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
    "Accept": "application/json, text/plain, */*",
}


@dataclass(frozen=True)
class DrawRecord:
    """Normalized representation of a single lottery draw."""

    game: str
    period: int
    lottery_date: str
    n1: int
    n2: int
    n3: int
    n4: int
    n5: int
    n6: int
    special: int
    appear_order: str
    sell_amount: int
    total_amount: int
    jackpot_winners: int
    jackpot_per_prize: int

    @property
    def main_numbers(self) -> tuple[int, ...]:
        return (self.n1, self.n2, self.n3, self.n4, self.n5, self.n6)


def _http_get_json(url: str, timeout: int = 15, retries: int = 3) -> dict[str, Any]:
    """Fetch JSON payload with simple exponential backoff."""
    last_err: Exception | None = None
    for attempt in range(retries):
        req = urllib.request.Request(url, headers=DEFAULT_HEADERS)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if data.get("rtCode") != 0:
                    raise RuntimeError(f"API error rtCode={data.get('rtCode')}: {data.get('rtMsg')}")
                return data
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, RuntimeError) as err:
            last_err = err
            if attempt < retries - 1:
                time.sleep(1.5 * (2**attempt))
    raise RuntimeError(f"Failed to fetch {url}: {last_err}")


def parse_draw_record(game: str, raw: dict[str, Any]) -> DrawRecord:
    """Convert raw API JSON entry into a normalized DrawRecord."""
    cfg = GAME_CONFIGS[game]
    nums_sorted = raw["drawNumberSize"]
    if len(nums_sorted) != 7:
        raise ValueError(f"Expected 7 numbers in drawNumberSize, got {nums_sorted}")
    jackpot = raw.get(cfg["jackpot_key"]) or {}
    appear = raw.get("drawNumberAppear") or nums_sorted
    return DrawRecord(
        game=game,
        period=int(raw["period"]),
        lottery_date=str(raw["lotteryDate"])[:10],
        n1=int(nums_sorted[0]),
        n2=int(nums_sorted[1]),
        n3=int(nums_sorted[2]),
        n4=int(nums_sorted[3]),
        n5=int(nums_sorted[4]),
        n6=int(nums_sorted[5]),
        special=int(nums_sorted[6]),
        appear_order=",".join(str(x) for x in appear),
        sell_amount=int(raw.get("sellAmount") or 0),
        total_amount=int(raw.get("totalAmount") or 0),
        jackpot_winners=int(jackpot.get("winnerCount") or 0),
        jackpot_per_prize=int(jackpot.get("perPrize") or 0),
    )


def fetch_page(
    game: str,
    start_month: str,
    end_month: str,
    page_num: int = 1,
    page_size: int = 500,
) -> tuple[int, list[DrawRecord]]:
    """Fetch one paginated page of draw results for a game."""
    cfg = GAME_CONFIGS[game]
    url = (
        f"{BASE_URL}/{cfg['endpoint']}"
        f"?period&startMonth={start_month}&endMonth={end_month}"
        f"&pageNum={page_num}&pageSize={page_size}"
    )
    payload = _http_get_json(url)
    content = payload.get("content") or {}
    total_size = int(content.get("totalSize") or 0)
    raw_items = content.get(cfg["res_key"]) or []
    records = [parse_draw_record(game, item) for item in raw_items]
    return total_size, records


def fetch_all_draws(
    game: str,
    end_month: str,
    known_periods: set[int] | None = None,
    page_size: int = 500,
) -> list[DrawRecord]:
    """Fetch draws for a game; stops early when all items on a page are already known."""
    cfg = GAME_CONFIGS[game]
    start_month = cfg["start_month"]
    known = known_periods or set()

    # Incremental runs only need small pages unless many draws are missing.
    effective_page_size = 50 if known else page_size
    total_size, first_records = fetch_page(
        game, start_month, end_month, page_num=1, page_size=effective_page_size
    )
    if total_size == 0 or not first_records:
        return []

    collected: list[DrawRecord] = []
    new_on_first = [r for r in first_records if r.period not in known]
    collected.extend(new_on_first)

    # API returns newest draws first; if every record on page 1 is already stored, we're synced.
    if known and len(new_on_first) < len(first_records):
        return collected

    total_pages = (total_size + effective_page_size - 1) // effective_page_size
    for page in range(2, total_pages + 1):
        _, records = fetch_page(
            game, start_month, end_month, page_num=page, page_size=effective_page_size
        )
        if not records:
            break
        new_items = [r for r in records if r.period not in known]
        collected.extend(new_items)
        if known and len(new_items) < len(records):
            break

    return collected
