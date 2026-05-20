"""永慶房屋 (yungching.com.tw) rental fetcher.

Uses httpx + BeautifulSoup4 to scrape the rendered HTML listing pages.

NOTE: Yungching may serve listings via a JavaScript-rendered SPA in which case
httpx will only see an empty shell.  If `_parse_card` consistently yields 0
results, switch to Playwright (same pattern as fetcher_591.py).

Selector reference — verified against buy.yungching.com.tw/lease/ 2024-Q1.
"""
from __future__ import annotations
import logging
import re
from typing import Optional
from urllib.parse import urlencode

import httpx
from bs4 import BeautifulSoup, Tag

from ..models import Property, parse_floor_string
from .base import HEADERS, clean_area, clean_price, throttle

logger = logging.getLogger(__name__)

BASE_URL = "https://buy.yungching.com.tw"

CITY_SLUGS: dict[str, str] = {
    "台北市": "台北市",
    "新北市": "新北市",
    "基隆市": "基隆市",
    "桃園市": "桃園市",
    "新竹市": "新竹市",
    "新竹縣": "新竹縣",
    "台中市": "台中市",
    "台南市": "台南市",
    "高雄市": "高雄市",
}

ROOM_TYPE_SLUGS: dict[str, str] = {
    "整層住家": "1",
    "獨立套房": "2",
    "分租套房": "3",
    "雅房":     "4",
}


def _build_search_url(city: str, config: dict, page: int = 1) -> str:
    room_types = config.get("room_types", [])
    type_code  = ROOM_TYPE_SLUGS.get(room_types[0], "") if room_types else ""
    floor_min  = config.get("floor_min", 1)

    qs: dict = {
        "city":        city,
        "price_lower": config.get("price_min", 0),
        "price_upper": config.get("price_max", 999_999),
        "pg":          page,
    }
    if type_code:
        qs["houseType"] = type_code
    if floor_min > 1:
        qs["floorMin"] = floor_min
    if config.get("has_elevator"):
        qs["elevator"] = "Y"
    if config.get("pet_friendly"):
        qs["pet"] = "Y"

    # FIXME: confirm exact URL path and param names against yungching.com.tw
    return f"{BASE_URL}/lease/?{urlencode(qs, encoding='utf-8')}"


def _parse_card(card: Tag, city_name: str) -> Optional[Property]:
    """Parse one listing element into a Property.

    FIXME: class selectors below are best-guess — verify in DevTools.
    """
    try:
        title_el = card.select_one(".m-subjectTitle, .item-title, h3")
        title = title_el.get_text(strip=True) if title_el else ""

        link_el = card.select_one("a[href*='/lease/'], a[href*='/rent/']")
        if not link_el:
            return None
        href = str(link_el.get("href", ""))
        if not href.startswith("http"):
            href = BASE_URL + href
        id_match = re.search(r"/(\d{6,})", href)
        listing_id = id_match.group(1) if id_match else href

        price_el = card.select_one(".price, .m-price, [class*='price']")
        price = clean_price(price_el.get_text(strip=True) if price_el else None)
        if price is None:
            return None

        area_el = card.select_one(".area, .m-area, [class*='area']")
        area = clean_area(area_el.get_text(strip=True) if area_el else None)

        layout_el = card.select_one(".layout, .room, [class*='room']")
        layout = layout_el.get_text(strip=True) if layout_el else None

        floor_el = card.select_one(".floor, .m-floor, [class*='floor']")
        floor_raw = floor_el.get_text(strip=True) if floor_el else ""
        cur_floor, tot_floors = parse_floor_string(floor_raw)

        addr_el = card.select_one(".address, .m-address, [class*='address']")
        address = addr_el.get_text(strip=True) if addr_el else city_name

        img_el = card.select_one("img[src], img[data-src], img[data-lazy]")
        image_url = None
        if img_el:
            raw_src = str(img_el.get("data-lazy") or img_el.get("data-src") or img_el.get("src") or "")
            if raw_src.startswith("//"):
                raw_src = "https:" + raw_src
            image_url = raw_src or None

        return Property(
            id=listing_id,
            platform="Yungching",
            title=title,
            price=price,
            area=area,
            layout=layout,
            address=address,
            floor=floor_raw or None,
            image_url=image_url,
            link=href,
            current_floor=cur_floor,
            total_floors=tot_floors,
        )
    except Exception as exc:
        logger.warning("Yungching: failed to parse card — %s", exc)
        return None


def _fetch_city(city_name: str, config: dict) -> list[Property]:
    results: list[Property] = []
    page = 1

    with httpx.Client(headers=HEADERS, timeout=20, follow_redirects=True) as client:
        while True:
            url  = _build_search_url(city_name, config, page)
            logger.debug("Yungching: GET %s", url)
            resp = client.get(url)
            if resp.status_code != 200:
                logger.warning("Yungching: HTTP %d for %s", resp.status_code, url)
                break

            soup  = BeautifulSoup(resp.text, "lxml")
            cards = soup.select(
                ".m-listItem, .item-wrap, [class*='list-item'], [class*='houseItem']"
            )

            if not cards:
                logger.info("Yungching: no cards found on page %d — stopping", page)
                break

            for card in cards:
                prop = _parse_card(card, city_name)
                if prop:
                    results.append(prop)

            next_pg = soup.select_one("a.next-page, [class*='pagination'] .next")
            if not next_pg:
                break

            page += 1
            throttle(1.5)

    return results


def fetch_yungching(config: dict) -> list[Property]:
    cities = config.get("target_cities", [])
    all_props: list[Property] = []

    for city_name in cities:
        if city_name not in CITY_SLUGS:
            logger.warning("Yungching: unknown city '%s', skipping", city_name)
            continue
        logger.info("Yungching: fetching %s …", city_name)
        props = _fetch_city(city_name, config)
        logger.info("Yungching: got %d listings for %s", len(props), city_name)
        all_props.extend(props)

    return all_props
