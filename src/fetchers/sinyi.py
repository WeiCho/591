"""信義房屋 (sinyi.com.tw) rental fetcher.

URL format (confirmed 2025-06):
  /rent/list/{city}/{zips}-zip/{price_min}-{price_max}-price[/{area_min}-9999-area][/{type}]/index.html
  Pagination page N: .../{type}/N/index.html  (page 1 = /index.html)

Server-side filtering handles price / area / type / district — no Python-level
re-filtering needed.  Uses httpx + BeautifulSoup (SSR HTML, no JS required).
"""
from __future__ import annotations
import logging
import re
from typing import Optional

import httpx
from bs4 import BeautifulSoup, Tag

from ..models import Property, parse_floor_string
from .base import HEADERS, clean_area, clean_price, throttle

logger = logging.getLogger(__name__)

BASE_URL = "https://www.sinyi.com.tw"

CITY_SLUGS: dict[str, str] = {
    "台北市": "Taipei-city",
    "新北市": "NewTaipei-city",
    "基隆市": "Keelung-city",
    "桃園市": "Taoyuan-city",
    "新竹市": "Hsinchu-city",
    "新竹縣": "Hsinchu-county",
    "台中市": "Taichung-city",
    "台南市": "Tainan-city",
    "高雄市": "Kaohsiung-city",
}

# District name (with or without 區) → Taiwan postal code
DISTRICT_ZIPS: dict[str, int] = {
    # ── 台北市 ──────────────────────────────────
    "中正": 100, "中正區": 100,
    "大同": 103, "大同區": 103,
    "中山": 104, "中山區": 104,
    "松山": 105, "松山區": 105,
    "大安": 106, "大安區": 106,
    "萬華": 108, "萬華區": 108,
    "信義": 110, "信義區": 110,
    "士林": 111, "士林區": 111,
    "北投": 112, "北投區": 112,
    "內湖": 114, "內湖區": 114,
    "南港": 115, "南港區": 115,
    "文山": 116, "文山區": 116,
    # ── 新北市 ──────────────────────────────────
    "板橋": 220, "板橋區": 220,
    "汐止": 221, "汐止區": 221,
    "新店": 231, "新店區": 231,
    "永和": 234, "永和區": 234,
    "中和": 235, "中和區": 235,
    "土城": 236, "土城區": 236,
    "樹林": 238, "樹林區": 238,
    "三重": 241, "三重區": 241,
    "新莊": 242, "新莊區": 242,
    "泰山": 243, "泰山區": 243,
    "林口": 244, "林口區": 244,
    "蘆洲": 247, "蘆洲區": 247,
    "五股": 248, "五股區": 248,
    "淡水": 251, "淡水區": 251,
    "三峽": 237, "三峽區": 237,
    "鶯歌": 239, "鶯歌區": 239,
    # ── 其他縣市 ─────────────────────────────────
    "東區": 600,  # 台中
}

# Confirmed slug for 整層住家; others TBD
ROOM_TYPE_SLUGS: dict[str, str] = {
    "整層住家": "house-use",
}


def _build_url(
    city_slug:      str,
    zip_codes:      list[int],
    price_min:      int,
    price_max:      int,
    area_min:       float,
    room_type_slug: str,
    page:           int = 1,
) -> str:
    parts: list[str] = [BASE_URL, "rent", "list", city_slug]

    if zip_codes:
        parts.append("-".join(str(z) for z in zip_codes) + "-zip")

    parts.append(f"{price_min}-{price_max}-price")

    if area_min > 0:
        parts.append(f"{int(area_min)}-9999-area")

    if room_type_slug:
        parts.append(room_type_slug)

    if page >= 2:
        parts.append(str(page))

    parts.append("index.html")
    return "/".join(parts)


def _id_from_href(href: str) -> Optional[str]:
    m = re.search(r"/rent/houseno/([A-Z0-9]+)", href)
    return m.group(1) if m else None


def _parse_card(a_tag: Tag, city_name: str) -> Optional[Property]:
    href = str(a_tag.get("href", ""))
    if not href.startswith("http"):
        href = BASE_URL + href

    listing_id = _id_from_href(href)
    if not listing_id:
        return None

    text = a_tag.get_text(separator=" ", strip=True)
    if not text:
        return None

    # Price — "XX,XXX元/月"
    price_m = re.search(r"([\d,]+)\s*元/月", text)
    price = clean_price(price_m.group(1)) if price_m else None
    if price is None:
        return None

    # Floor — "12/15樓"
    floor_m = re.search(r"(\d+)/(\d+)樓", text)
    floor_str = floor_m.group(0) if floor_m else None
    cur_floor, tot_floors = parse_floor_string(floor_str or "")

    # Area — "51.93坪"
    area_m = re.search(r"([\d.]+)\s*坪", text)
    area = clean_area(area_m.group(1)) if area_m else None

    # Layout — "3房2廳2衛"
    layout_m = re.search(r"\d+房[\d廳衛]+", text)
    layout = layout_m.group(0) if layout_m else None

    # Title — first non-empty line
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    title = lines[0] if lines else listing_id

    # Address — "台北市文山區..."
    addr_m = re.search(r"[一-鿿]{2,3}[市縣][一-鿿]{2,3}[區鄉鎮][一-鿿\d]+", text)
    address = addr_m.group(0) if addr_m else city_name

    # Elevator heuristic
    has_elev = "電梯" in text or (tot_floors or 0) >= 7 or (cur_floor or 0) >= 7

    # Image — CDN pattern
    img_tag = a_tag.find("img")
    img: str | None = None
    if img_tag:
        img = str(img_tag.get("data-src") or img_tag.get("src") or "")
        if img.startswith("//"):
            img = "https:" + img
        if not img or img.startswith("data:"):
            img = None
    if not img:
        img = f"https://res.sinyi.com.tw/rent/{listing_id}/smallimg/A.JPG"

    return Property(
        id=listing_id,
        platform="Sinyi",
        title=title,
        price=price,
        area=area,
        layout=layout,
        address=address,
        floor=floor_str,
        image_url=img,
        link=href,
        current_floor=cur_floor,
        total_floors=tot_floors,
        has_elevator=has_elev,
        tags=[],
    )


def _fetch_url(client: httpx.Client, url: str, city_name: str) -> list[Property]:
    logger.debug("Sinyi: GET %s", url)
    resp = client.get(url)
    if resp.status_code != 200:
        logger.warning("Sinyi: HTTP %d for %s", resp.status_code, url)
        return []

    soup  = BeautifulSoup(resp.text, "lxml")
    cards = soup.select('a[href*="/rent/houseno/"]')

    results: list[Property] = []
    for tag in cards:
        prop = _parse_card(tag, city_name)
        if prop:
            results.append(prop)
    return results


def _fetch_city(
    city_name:      str,
    city_slug:      str,
    city_regions:   list[str],
    price_min:      int,
    price_max:      int,
    area_min:       float,
    room_type_slug: str,
) -> list[Property]:
    zip_codes = [DISTRICT_ZIPS[r] for r in city_regions if r in DISTRICT_ZIPS]
    if city_regions and not zip_codes:
        unknown = [r for r in city_regions if r not in DISTRICT_ZIPS]
        logger.warning("Sinyi: no zip code found for regions %s — fetching whole city", unknown)

    results:  list[Property] = []
    seen_ids: set[str]       = set()

    with httpx.Client(headers=HEADERS, timeout=20, follow_redirects=True) as client:
        page = 1
        while True:
            url   = _build_url(city_slug, zip_codes, price_min, price_max, area_min, room_type_slug, page)
            props = _fetch_url(client, url, city_name)

            if not props:
                break

            new_ids = {p.id for p in props} - seen_ids
            if page > 1 and not new_ids:
                break  # pagination looped back or exhausted

            for p in props:
                if p.id not in seen_ids:
                    seen_ids.add(p.id)
                    results.append(p)

            logger.info("Sinyi %s page %d: %d new (total %d)", city_name, page, len(new_ids), len(results))

            if len(new_ids) < len(props):
                break  # partial new batch → last page

            page += 1
            throttle(1.5)

    return results


def fetch_sinyi(config: dict) -> list[Property]:
    cities_cfg: list[dict] = config.get("cities") or [
        {"name": c, "regions": config.get("target_regions", [])}
        for c in config.get("target_cities", [])
    ]
    price_min = config.get("price_min", 0)
    price_max = config.get("price_max", 999_999)
    area_min  = float(config.get("area_min", 0))
    all_regions_flag: bool = config.get("all_regions", True)

    room_types   = config.get("room_types", [])
    type_slugs   = [ROOM_TYPE_SLUGS[rt] for rt in room_types if rt in ROOM_TYPE_SLUGS]
    # If no known slug, fetch without type filter (server returns all types)
    type_slug    = type_slugs[0] if type_slugs else ""

    if not type_slugs and room_types:
        unknown_types = [rt for rt in room_types if rt not in ROOM_TYPE_SLUGS]
        logger.warning("Sinyi: unknown room_type slug for %s — fetching without type filter", unknown_types)

    all_props: list[Property] = []
    for city_entry in cities_cfg:
        city_name   = city_entry.get("name", "")
        city_slug   = CITY_SLUGS.get(city_name)
        city_regions = [] if all_regions_flag else city_entry.get("regions", [])

        if not city_slug:
            logger.warning("Sinyi: unknown city '%s', skipping", city_name)
            continue

        logger.info("Sinyi: fetching %s / regions=%s", city_name, city_regions or "全區")
        props = _fetch_city(city_name, city_slug, city_regions, price_min, price_max, area_min, type_slug)
        logger.info("Sinyi: %d listings for %s", len(props), city_name)
        all_props.extend(props)

    return all_props
