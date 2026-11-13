"""CLI entry point for Taiwan Lottery automatic sync, analysis, and weekly picks."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path

from lottery.db import connect_db, export_csv, get_known_periods, load_draws, upsert_draws
from lottery.fetcher import GAME_CONFIGS, fetch_all_draws
from lottery.notifier import send_email_if_configured, send_webhook_if_configured
from lottery.recommender import build_weekly_recommendations
from lottery.report import render_full_report
from lottery.stats import analyze_game


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_DB = PROJECT_ROOT / "data" / "lottery.db"
DEFAULT_REPORT = PROJECT_ROOT / "reports" / "latest_report.md"
TZ_TAIPEI = timezone(timedelta(hours=8))


def cmd_sync(db_path: Path, full: bool = False, export_csv_files: bool = True) -> dict[str, int]:
    """Sync historical and latest draw records into SQLite."""
    end_month = datetime.now(TZ_TAIPEI).strftime("%Y-%m")
    conn = connect_db(db_path)
    counts: dict[str, int] = {}
    try:
        for game in GAME_CONFIGS:
            known = set() if full else get_known_periods(conn, game)
            new_records = fetch_all_draws(game, end_month=end_month, known_periods=known)
            written = upsert_draws(conn, new_records)
            counts[game] = written
            if export_csv_files:
                export_csv(conn, game, db_path.parent / f"{game}.csv")
    finally:
        conn.close()
    return counts


def cmd_report(
    db_path: Path,
    report_path: Path,
    anti_popular_count: int = 3,
    statistical_count: int = 2,
    recent_window: int = 100,
) -> str:
    """Analyze stored draws, generate recommendations, and write Markdown report."""
    conn = connect_db(db_path)
    try:
        sections = []
        for game in GAME_CONFIGS:
            draws = load_draws(conn, game)
            if not draws:
                raise RuntimeError(f"資料庫尚無 {game} 開獎資料，請先執行 sync。")
            stats = analyze_game(game, draws, recent_window=recent_window)
            tickets = build_weekly_recommendations(
                stats,
                anti_popular_count=anti_popular_count,
                statistical_count=statistical_count,
            )
            sections.append((stats, tickets))
    finally:
        conn.close()

    report_md = render_full_report(sections)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report_md, encoding="utf-8")
    return report_md


def main() -> None:
    parser = argparse.ArgumentParser(description="台灣大樂透 & 威力彩自動蒐集與每週統計選號工具")
    parser.add_argument(
        "action",
        choices=["sync", "report", "run"],
        nargs="?",
        default="run",
        help="sync: 僅更新資料; report: 僅產出報告; run: 更新資料＋產出報告＋選用通知",
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="SQLite 資料庫路徑")
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT, help="Markdown 報告輸出路徑")
    parser.add_argument("--full", action="store_true", help="強制全量重新抓取歷史資料")
    parser.add_argument("--anti-popular", type=int, default=3, help="每種彩券產出的避撞號組數")
    parser.add_argument("--statistical", type=int, default=2, help="每種彩券產出的統計權重組數")
    parser.add_argument("--recent-window", type=int, default=100, help="近期熱門統計期數")
    parser.add_argument("--notify", action="store_true", help="依環境變數寄出 Email 或 Webhook 通知")
    args = parser.parse_args()

    if args.action in ("sync", "run"):
        counts = cmd_sync(args.db, full=args.full)
        print(f"資料同步完成：大樂透新增/更新 {counts['lotto649']} 期、威力彩新增/更新 {counts['super638']} 期")

    if args.action in ("report", "run"):
        report_md = cmd_report(
            db_path=args.db,
            report_path=args.report,
            anti_popular_count=args.anti_popular,
            statistical_count=args.statistical,
            recent_window=args.recent_window,
        )
        print(f"報告已寫入：{args.report}\n")
        print(report_md)

        if args.notify:
            today = datetime.now(TZ_TAIPEI).strftime("%Y-%m-%d")
            emailed = send_email_if_configured(f"台彩每週統計與選號報告 ({today})", report_md)
            hooked = send_webhook_if_configured(report_md)
            print(f"通知狀態：Email={'已寄出' if emailed else '未設定'}, Webhook={'已發送' if hooked else '未設定'}")


if __name__ == "__main__":
    main()
