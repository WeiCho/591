"""台灣租房監控機器人 — 主程式

Usage:
  python main.py                 # full run
  python main.py --dry-run       # skip real fetchers; use cached history only
  python main.py --platforms 591 sinyi   # only run specific platforms
  python main.py --config my_config.json
"""
from __future__ import annotations
import argparse
import io
import logging
import sys
from pathlib import Path

# UTF-8 console output (prevents UnicodeEncodeError on cp950/cp936 Windows)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# ── logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("main")

# ── src imports ───────────────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent))

from src.config_loader import load_config
from src.diff_engine import run_diff
from src.filter_engine import apply_filters, dedup_properties
from src.report_generator import render_report

ALL_PLATFORMS = ("591", "sinyi", "yungching")


def _import_fetchers(platforms: list[str]):
    """Lazy-import fetchers so the CLI stays responsive without Playwright."""
    fetchers = {}
    if "591" in platforms:
        from src.fetchers.fetcher_591 import fetch_591
        fetchers["591"] = fetch_591
    if "sinyi" in platforms:
        from src.fetchers.sinyi import fetch_sinyi
        fetchers["sinyi"] = fetch_sinyi
    if "yungching" in platforms:
        from src.fetchers.yungching import fetch_yungching
        fetchers["yungching"] = fetch_yungching
    return fetchers


def _print_banner(text: str) -> None:
    bar = "─" * 60
    print(f"\n{bar}\n  {text}\n{bar}")


def run(config_path: str, platforms: list[str], dry_run: bool) -> None:
    # ── 0. Load config ────────────────────────────────────────────────────────
    _print_banner("Step 0 │ 讀取設定檔")
    config = load_config(config_path)
    logger.info("Cities: %s | Price: %d–%d | All regions: %s",
                config["target_cities"], config["price_min"], config["price_max"],
                config["all_regions"])

    # ── 1. Fetch ──────────────────────────────────────────────────────────────
    _print_banner("Step 1 │ 抓取租屋資料")
    from src.models import Property
    all_raw: list[Property] = []

    if dry_run:
        logger.info("--dry-run: skipping all network fetchers")
    else:
        fetchers = _import_fetchers(platforms)
        for name, fn in fetchers.items():
            logger.info("Fetching %s …", name)
            try:
                props = fn(config)
                logger.info("  %s: %d listings", name, len(props))
                all_raw.extend(props)
            except Exception as exc:
                logger.error("  %s fetch failed: %s", name, exc)

    logger.info("Total raw listings: %d", len(all_raw))

    # ── 2. Filter ─────────────────────────────────────────────────────────────
    _print_banner("Step 2 │ 套用過濾條件")
    all_raw, dedup_removed = dedup_properties(all_raw)
    if dedup_removed:
        logger.info("Deduped: removed %d duplicate listings", dedup_removed)
    result = apply_filters(all_raw, config)

    logger.info("Passed filters: %d", len(result.kept))
    if result.excluded:
        logger.info("Excluded: %d", len(result.excluded))
        for prop, reasons in result.excluded:
            logger.debug("  DROP [%s] %s — %s", prop.platform, prop.title, "; ".join(reasons))

    # ── 3. Diff ───────────────────────────────────────────────────────────────
    _print_banner("Step 3 │ 歷史比對")
    entries = run_diff(result.kept)

    new_entries      = [e for e in entries if e.status == "new"]
    drop_entries     = [e for e in entries if e.status == "price_drop"]
    active_entries   = [e for e in entries if e.status == "unchanged"]
    delisted_entries = [e for e in entries if e.status == "delisted"]
    logger.info("New: %d | Price drop: %d | Active: %d | Delisted: %d",
                len(new_entries), len(drop_entries),
                len(active_entries), len(delisted_entries))

    # ── 4. Report ─────────────────────────────────────────────────────────────
    _print_banner("Step 4 │ 產出 HTML 報表")
    report_path = render_report(entries, output_dir="reports", config=config)
    logger.info("Report written: %s", report_path.resolve())
    print(f"\n  報表已產出：{report_path.resolve()}\n")

    # ── Summary ───────────────────────────────────────────────────────────────
    _print_banner("完成")
    print(f"  新上架：{len(new_entries)} 筆")
    print(f"  降  價：{len(drop_entries)} 筆")
    print(f"  在架中：{len(active_entries)} 筆")
    print(f"  下  架：{len(delisted_entries)} 筆")
    print(f"  報  表：{report_path}\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="台灣三大租房平台監控機器人",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--config", default="config.json",
        help="設定檔路徑 (預設: config.json)",
    )
    parser.add_argument(
        "--platforms", nargs="+", choices=list(ALL_PLATFORMS),
        default=list(ALL_PLATFORMS),
        help="指定平台 (預設: 全部)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="跳過網路抓取，只跑 Filter + Diff + 報表 (適合測試)",
    )
    args = parser.parse_args()

    run(
        config_path=args.config,
        platforms=args.platforms,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
