"""Phase 1 validation script — no real scrapers, no HTML output.

Verifies:
  Module 0  config.json loading + all-regions logic
  Module 2  diff engine (scenarios A-C)
  Module 2+  floor-string parser + filter engine (scenario D)
"""
from __future__ import annotations
import io
import json
import sys
from pathlib import Path

# Force UTF-8 so Chinese + box-drawing chars render on cp950/cp936 consoles.
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).parent))

from src.config_loader import load_config, is_all_regions
from src.diff_engine import run_diff
from src.filter_engine import apply_filters
from src.models import Property, parse_floor_string


# ── helpers ──────────────────────────────────────────────────────────────────

def header(title: str) -> None:
    bar = "─" * 60
    print(f"\n{bar}\n  {title}\n{bar}")


def prop_line(entry) -> str:
    prop, status, old_price = entry
    tag = {
        "new":        "[New]       ",
        "price_drop": "[Price Drop]",
        "unchanged":  "[Unchanged] ",
    }[status]
    price_str = f"NT${prop.price:,}/月"
    if old_price is not None:
        price_str = (
            f"NT${old_price:,} → NT${prop.price:,}/月  "
            f"(↓ NT${old_price - prop.price:,})"
        )
    floor_info = ""
    if prop.current_floor is not None:
        total = f"/{prop.total_floors}F" if prop.total_floors else ""
        floor_info = f"  {prop.current_floor}F{total}"
    return f"  {tag}  [{prop.platform:10s}] {prop.title}{floor_info}  |  {price_str}"


def make_prop(
    pid: str, platform: str, title: str, price: int,
    floor: str = "5F/12F", layout: str = "套房",
) -> Property:
    return Property(
        id=pid, platform=platform, title=title, price=price,
        area=20.0, layout=layout, address="新北市測試路1號",
        floor=floor, image_url=None,
        link=f"https://example.com/{platform}/{pid}",
    )


# ── Module 0 ─────────────────────────────────────────────────────────────────

def test_config() -> None:
    header("Module 0 │ 設定檔解析")
    cfg = load_config("config.json")
    print(json.dumps(cfg, ensure_ascii=False, indent=2))

    header("Module 0 │ 全區判斷邏輯單元測試")
    cases = [
        (["全區"],            True,  '["全區"]'),
        ([],                  True,  "[] (空陣列)"),
        (["大安區", "中山區"], False, '["大安區", "中山區"]'),
        (["全部"],            True,  '["全部"]'),
        (["不限"],            True,  '["不限"]'),
        (["信義區"],          False, '["信義區"]'),
    ]
    all_pass = True
    for regions, expected, label in cases:
        result = is_all_regions(regions)
        ok = result == expected
        icon = "[OK]  " if ok else "[FAIL]"
        print(f"  {icon}  is_all_regions({label}) = {result}  (期望: {expected})")
        if not ok:
            all_pass = False
    print(f"\n  {'所有測試通過 [OK]' if all_pass else '[FAIL] 有測試失敗'}")


# ── Floor parser unit tests ───────────────────────────────────────────────────

def test_floor_parser() -> None:
    header("Models │ parse_floor_string 單元測試")
    cases = [
        ("5F/12F",    (5,  12)),
        ("5樓/共12樓", (5,  12)),
        ("B1/8F",     (-1,  8)),
        ("3/5",       (3,   5)),
        ("5F",        (5, None)),
        ("頂樓/5F",   None),          # ambiguous — skip precise check
        (None,        (None, None)),
        ("",          (None, None)),
    ]
    all_pass = True
    for raw, expected in cases:
        if expected is None:   # skip unpredictable case
            continue
        result = parse_floor_string(raw)
        ok = result == expected
        icon = "[OK]  " if ok else "[FAIL]"
        print(f"  {icon}  parse_floor_string({raw!r}) = {result}  (期望: {expected})")
        if not ok:
            all_pass = False
    print(f"\n  {'所有測試通過 [OK]' if all_pass else '[FAIL] 有測試失敗'}")


# ── Module 2: diff engine ────────────────────────────────────────────────────

def test_diff() -> None:
    tmp_history = Path("history_test.jsonl")
    if tmp_history.exists():
        tmp_history.unlink()

    header("Module 2 │ Round 1 — 首次抓取 (全部應為 New)")
    round1 = [
        make_prop("101", "591",       "板橋區精品套房",  18_000, "5F/12F"),
        make_prop("202", "Sinyi",     "新莊區高樓整層",  45_000, "8F/20F"),
        make_prop("303", "Yungching", "中和區溫馨小套",  12_000, "3F/6F"),
    ]
    entries = run_diff(round1, history_path=tmp_history)
    for e in entries:
        print(prop_line(e))
    assert all(e.status == "new" for e in entries), "Round 1 應全為 new"

    header("Module 2 │ Round 2 — 差異比對三情境")
    round2 = [
        make_prop("404", "591",   "蘆洲區全新裝潢套房", 22_000, "7F/15F"),  # A: New
        make_prop("101", "591",   "板橋區精品套房",      15_000, "5F/12F"),  # B: Price Drop
        make_prop("202", "Sinyi", "新莊區高樓整層",      45_000, "8F/20F"),  # C: Unchanged
    ]
    entries2 = run_diff(round2, history_path=tmp_history)

    labels    = {"404": "情境 A", "101": "情境 B", "202": "情境 C"}
    expected  = {"404": "new", "101": "price_drop", "202": "unchanged"}
    all_pass = True
    for e in entries2:
        lbl = labels[e.property.id]
        print(f"  {lbl}: {prop_line(e)}")
        if e.status != expected[e.property.id]:
            print(f"    [FAIL] 期望 {expected[e.property.id]}，實際 {e.status}")
            all_pass = False
    print(f"\n  {'所有情境驗證通過 [OK]' if all_pass else '[FAIL] 有情境不符預期'}")
    tmp_history.unlink(missing_ok=True)


# ── Scenario D: floor filter ──────────────────────────────────────────────────

def test_filter_engine() -> None:
    header("Module 2+ │ 情境 D — 樓層過濾驗證")

    filter_cfg = {
        "floor_min": 3,
        "exclude_rooftop_addition": True,
        "exclude_top_floor": True,
    }

    candidates = [
        # Should PASS
        make_prop("P1", "591",   "正常物件 (5F/12F)",   20_000, "5F/12F"),
        # Should be EXCLUDED — floor_min=3, this is 2F
        make_prop("P2", "591",   "低樓層物件 (2F/8F)",  18_000, "2F/8F"),
        # Should be EXCLUDED — title contains 頂加
        make_prop("P3", "Sinyi", "頂加改建豪華套房",    16_000, "4F/4F"),
        # Should be EXCLUDED — top floor (5F/5F)
        make_prop("P4", "Sinyi", "頂樓景觀整層",        25_000, "5F/5F"),
        # Should PASS — 3F/10F meets floor_min=3
        make_prop("P5", "Yungching", "3樓優質整層",     22_000, "3F/10F"),
        # Should be EXCLUDED — top floor AND rooftop addition keyword
        make_prop("P6", "Yungching", "頂加違建套房",    10_000, "6F/6F"),
    ]

    # Verify floor parsing for our test data
    print("  [Floor解析確認]")
    for p in candidates:
        print(
            f"    {p.id}: \"{p.floor}\" "
            f"→ current={p.current_floor}, total={p.total_floors}"
        )

    result = apply_filters(candidates, filter_cfg)

    print(f"\n  [通過過濾器: {len(result.kept)} 筆]")
    for p in result.kept:
        print(f"    [PASS]  {p.id}: {p.title}  ({p.current_floor}F/{p.total_floors}F)")

    print(f"\n  [被排除: {len(result.excluded)} 筆]")
    for p, reasons in result.excluded:
        print(f"    [DROP]  {p.id}: {p.title}  → {', '.join(reasons)}")

    # Assertions
    passed_ids   = {p.id for p in result.kept}
    excluded_ids = {p.id for p, _ in result.excluded}
    expect_pass  = {"P1", "P5"}
    expect_excl  = {"P2", "P3", "P4", "P6"}

    ok = (passed_ids == expect_pass) and (excluded_ids == expect_excl)
    print(f"\n  {'情境 D 驗證通過 [OK]' if ok else '[FAIL] 過濾結果不符預期'}")
    if not ok:
        print(f"    期望通過: {expect_pass}，實際: {passed_ids}")
        print(f"    期望排除: {expect_excl}，實際: {excluded_ids}")


# ── entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n" + "═" * 60)
    print("  台灣租房監控機器人  ·  Phase 1 驗證腳本")
    print("═" * 60)

    test_config()
    test_floor_parser()
    test_diff()
    test_filter_engine()

    print("\n" + "═" * 60)
    print("  Phase 1 完成。全部邏輯驗證結束。")
    print("═" * 60 + "\n")
