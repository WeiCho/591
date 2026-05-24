from __future__ import annotations
import json
import sys
from pathlib import Path
from typing import Any

_ALL_REGION_TOKENS = {"全區", "全部", "不限", ""}


def is_all_regions(regions: list[str]) -> bool:
    if not regions:
        return True
    return any(r.strip() in _ALL_REGION_TOKENS for r in regions)


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
    """Validate and normalise raw JSON config into a typed dict.

    Supports nested city structure:
      "cities": [{"name": "新北市", "regions": ["板橋", ...]}, ...]

    Also supports legacy flat structure for backwards compat:
      "target_cities": [...], "target_regions": [...]
    """
    # ── nested cities structure ────────────────────────────────────────────
    if "cities" in raw:
        cities_raw: list[dict] = _require(raw, "cities", list, [])
        cities: list[dict] = []
        target_cities: list[str] = []
        all_regions: list[str] = []

        for entry in cities_raw:
            if not isinstance(entry, dict):
                continue
            name = str(entry.get("name", "")).strip()
            regions = [str(r).strip() for r in entry.get("regions", []) if str(r).strip()]
            if not name:
                continue
            cities.append({"name": name, "regions": regions})
            target_cities.append(name)
            all_regions.extend(regions)

        # flat target_regions = union of all cities' regions (for legacy callers)
        unique_regions = list(dict.fromkeys(all_regions))
        all_regions_flag = is_all_regions(unique_regions)

    # ── legacy flat structure ──────────────────────────────────────────────
    else:
        target_cities = _require(raw, "target_cities", list, [])
        target_regions: list[str] = _require(raw, "target_regions", list, [])
        all_regions_flag = is_all_regions(target_regions)
        unique_regions = [] if all_regions_flag else target_regions
        # wrap into nested cities structure with a single entry
        cities = [{"name": c, "regions": unique_regions} for c in target_cities]

    # github_publish is optional: {"repo": "user/repo", "token": "ghp_..."}
    gh_raw = raw.get("github_publish")
    github_publish: dict | None = None
    if isinstance(gh_raw, dict):
        repo  = str(gh_raw.get("repo",  "")).strip()
        token = str(gh_raw.get("token", "")).strip()
        if repo and token:
            github_publish = {"repo": repo, "token": token}

    return {
        # nested structure (primary)
        "cities": cities,
        # flat aliases (for fetchers / report that still use these)
        "target_cities": target_cities,
        "target_regions": unique_regions,
        "all_regions": all_regions_flag,
        # other settings
        "price_min":  _require(raw, "price_min",  int,  0),
        "price_max":  _require(raw, "price_max",  int,  999_999),
        "room_types": _require(raw, "room_types", list, []),
        "pet_friendly": _require(raw, "pet_friendly", bool, False),
        "floor_min":  _require(raw, "floor_min",  int,  1),
        "exclude_rooftop_addition": _require(raw, "exclude_rooftop_addition", bool, False),
        "exclude_top_floor":        _require(raw, "exclude_top_floor",        bool, False),
        "area_min": float(raw["area_min"]) if isinstance(raw.get("area_min"), (int, float)) else 0.0,
        "github_publish": github_publish,
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
