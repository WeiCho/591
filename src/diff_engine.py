from __future__ import annotations
import json
from datetime import date
from pathlib import Path
from typing import Literal, NamedTuple, Optional

from .models import Property

HISTORY_PATH     = Path("history.jsonl")
ALL_LISTINGS_PATH = Path("all_listings.jsonl")

Status = Literal["new", "price_drop", "unchanged", "delisted"]


class DiffEntry(NamedTuple):
    property: Property
    status: Status
    old_price: Optional[int]  # populated only when status == "price_drop"


# ── Low-level I/O ────────────────────────────────────────────────────────────

def _load_jsonl(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    records: dict[str, dict] = {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                record = json.loads(line)
                records[record["hash_key"]] = record
    return records


def _save_jsonl(records: dict[str, dict], path: Path) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        for record in records.values():
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def load_history(path: Path = HISTORY_PATH) -> dict[str, dict]:
    return _load_jsonl(path)


def save_history(history: dict[str, dict], path: Path = HISTORY_PATH) -> None:
    _save_jsonl(history, path)


# ── Property serialisation ───────────────────────────────────────────────────

def _to_history_record(prop: Property) -> dict:
    return {
        "hash_key": prop.hash_key,
        "platform": prop.platform,
        "id":       prop.id,
        "title":    prop.title,
        "price":    prop.price,
        "link":     prop.link,
        "last_seen": date.today().isoformat(),
    }


def _to_listing_record(prop: Property) -> dict:
    """Full display record for all_listings.jsonl."""
    return {
        "hash_key":     prop.hash_key,
        "platform":     prop.platform,
        "id":           prop.id,
        "title":        prop.title,
        "price":        prop.price,
        "area":         prop.area,
        "layout":       prop.layout,
        "address":      prop.address,
        "floor":        prop.floor,
        "image_url":    prop.image_url,
        "link":         prop.link,
        "current_floor": prop.current_floor,
        "total_floors": prop.total_floors,
        "has_elevator": prop.has_elevator,
        "last_seen":    date.today().isoformat(),
        "delisted":     False,
    }


def _record_to_property(r: dict) -> Property:
    from .models import Property  # avoid circular at module level
    return Property(
        id=r["id"],
        platform=r["platform"],
        title=r.get("title", ""),
        price=r["price"],
        area=r.get("area"),
        layout=r.get("layout"),
        address=r.get("address", ""),
        floor=r.get("floor"),
        image_url=r.get("image_url"),
        link=r.get("link", ""),
        current_floor=r.get("current_floor"),
        total_floors=r.get("total_floors"),
        has_elevator=r.get("has_elevator", False),
    )


# ── Diff logic ───────────────────────────────────────────────────────────────

def _classify(prop: Property, history: dict[str, dict]) -> tuple[Status, Optional[int]]:
    if prop.hash_key not in history:
        return "new", None
    existing = history[prop.hash_key]
    if prop.price < existing["price"]:
        return "price_drop", existing["price"]
    return "unchanged", None


def run_diff(
    properties: list[Property],
    history_path:      Path = HISTORY_PATH,
    all_listings_path: Path = ALL_LISTINGS_PATH,
) -> list[DiffEntry]:
    """Classify each property; upsert history + all_listings; detect delisted.

    Returns DiffEntry list:
    - new / price_drop / unchanged  → from current crawl
    - delisted                      → in all_listings but absent this crawl
    """
    history  = load_history(history_path)
    listings = _load_jsonl(all_listings_path)

    current_keys: set[str] = set()
    entries: list[DiffEntry] = []

    for prop in properties:
        status, old_price = _classify(prop, history)
        entries.append(DiffEntry(property=prop, status=status, old_price=old_price))
        history[prop.hash_key]  = _to_history_record(prop)
        listings[prop.hash_key] = _to_listing_record(prop)  # upsert with fresh data
        current_keys.add(prop.hash_key)

    # detect delisted: previously known, not seen this run
    for key, record in listings.items():
        if key not in current_keys and not record.get("delisted"):
            record["delisted"] = True
            prop = _record_to_property(record)
            entries.append(DiffEntry(property=prop, status="delisted", old_price=None))

    save_history(history, history_path)
    _save_jsonl(listings, all_listings_path)
    return entries
