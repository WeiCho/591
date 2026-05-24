from __future__ import annotations
from typing import NamedTuple

from .models import Property

_ROOFTOP_KEYWORDS  = ("頂加", "頂樓加蓋", "頂加物件")
_SOCIAL_HOUSING_KEYWORDS = ("社宅", "社會住宅")



def dedup_properties(properties: list[Property]) -> tuple[list[Property], int]:
    """Remove duplicates: same address + price + area, and overlapping title.

    Groups by (address, price, area), then within each group keeps only the
    first listing whose title doesn't partially match an already-kept one.

    Returns (deduped list, number of duplicates removed).
    """
    seen_keys: set[str] = set()
    kept_flat: list[Property] = []

    for prop in properties:
        address = (prop.address or "").strip()
        area    = round(prop.area, 1) if prop.area is not None else ""
        floor   = (prop.floor or "").strip()
        # Same address + price + area + floor → same physical unit regardless of title
        key = f"{address}|{prop.price}|{area}|{floor}"

        if key in seen_keys:
            continue  # duplicate — skip
        seen_keys.add(key)
        kept_flat.append(prop)

    removed = len(properties) - len(kept_flat)
    return kept_flat, removed


class FilterResult(NamedTuple):
    kept: list[Property]
    excluded: list[tuple[Property, list[str]]]  # (property, [reason, ...])


def _is_rooftop_addition(prop: Property) -> bool:
    for field in (prop.title, prop.floor, prop.address):
        if field and any(kw in field for kw in _ROOFTOP_KEYWORDS):
            return True
    return False


def _is_social_housing(prop: Property) -> bool:
    title = prop.title or ""
    return any(kw in title for kw in _SOCIAL_HOUSING_KEYWORDS)


def _is_top_floor(prop: Property) -> bool:
    if prop.current_floor is not None and prop.total_floors is not None:
        return prop.current_floor == prop.total_floors and prop.total_floors > 0
    return False


def apply_filters(properties: list[Property], config: dict) -> FilterResult:
    """Apply all config-driven pre-display filters.

    Returns a FilterResult with two lists:
      kept     — properties that passed every filter
      excluded — (property, [reason]) pairs that were dropped, for logging
    """
    kept: list[Property] = []
    excluded: list[tuple[Property, list[str]]] = []

    floor_min: int = config.get("floor_min", 1)
    area_min: float = float(config.get("area_min", 0) or 0)
    excl_rooftop: bool = config.get("exclude_rooftop_addition", False)
    excl_top: bool = config.get("exclude_top_floor", False)

    for prop in properties:
        reasons: list[str] = []

        if _is_social_housing(prop):
            reasons.append("社宅/社會住宅 (標題含關鍵字)")

        if floor_min > 1 and prop.current_floor is not None:
            if prop.current_floor < floor_min:
                reasons.append(f"樓層 {prop.current_floor}F < 最低要求 {floor_min}F")

        if area_min > 0 and prop.area is not None:
            if prop.area < area_min:
                reasons.append(f"坪數 {prop.area} < 最低要求 {area_min} 坪")

        if excl_rooftop and _is_rooftop_addition(prop):
            reasons.append("頂樓加蓋 (標題/樓層含關鍵字)")

        if excl_top and _is_top_floor(prop):
            reasons.append(
                f"頂樓 ({prop.current_floor}F/{prop.total_floors}F)"
            )

        if reasons:
            excluded.append((prop, reasons))
        else:
            kept.append(prop)

    return FilterResult(kept=kept, excluded=excluded)
