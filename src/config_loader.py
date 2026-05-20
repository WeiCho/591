from __future__ import annotations
import json
import sys
from pathlib import Path
from typing import Any

# Sentinel values recognised as "search the entire city, no region filter"
_ALL_REGION_TOKENS = {"全區", "全部", "不限", ""}


def is_all_regions(target_regions: list[str]) -> bool:
    """Return True when the region list means 'no restriction'.

    Triggers when the list is empty OR when any element matches a known
    all-region token (case-insensitive, whitespace-stripped).
    """
    if not target_regions:
        return True
    return any(r.strip() in _ALL_REGION_TOKENS for r in target_regions)


def _require(cfg: dict, key: str, expected_type: type, default: Any) -> Any:
    val = cfg.get(key, default)
    if not isinstance(val, expected_type):
        print(
            f"[Config警告] '{key}' 應為 {expected_type.__name__}，"
            f"收到 {type(val).__name__}，使用預設值 {default!r}",
            file=sys.stderr,
        )
        return default
    return val


def parse_config(raw: dict) -> dict:
    """Validate and normalise raw JSON config into a typed dict."""
    target_regions: list[str] = _require(raw, "target_regions", list, [])
    all_regions = is_all_regions(target_regions)

    return {
        "target_cities": _require(raw, "target_cities", list, []),
        # Cleared to [] when all_regions is True so callers never need to
        # check two separate fields.
        "target_regions": [] if all_regions else target_regions,
        "all_regions": all_regions,
        "price_min": _require(raw, "price_min", int, 0),
        "price_max": _require(raw, "price_max", int, 999_999),
        "room_types": _require(raw, "room_types", list, []),
        "pet_friendly": _require(raw, "pet_friendly", bool, False),
        "floor_min": _require(raw, "floor_min", int, 1),
        "exclude_rooftop_addition": _require(raw, "exclude_rooftop_addition", bool, False),
        "exclude_top_floor": _require(raw, "exclude_top_floor", bool, False),
        "area_min": float(raw["area_min"]) if isinstance(raw.get("area_min"), (int, float)) else 0.0,
    }


def load_config(path: str | Path = "config.json") -> dict:
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(
            f"找不到設定檔：{config_path.absolute()}\n"
            "請複製 config.json.example 並填入您的搜尋條件。"
        )
    with open(config_path, encoding="utf-8") as fh:
        try:
            raw = json.load(fh)
        except json.JSONDecodeError as exc:
            raise ValueError(f"config.json 格式錯誤：{exc}") from exc

    return parse_config(raw)
