"""信義房屋 (sinyi.com.tw) rental fetcher.

Uses httpx + BeautifulSoup4 to scrape the rendered HTML listing pages.

NOTE: Sinyi uses a React SPA; the initial HTML is server-side rendered (SSR)
for SEO, so most listing data IS present in the raw HTML.  If a future site
update removes SSR, switch this module to Playwright.

Selector reference — verified against sinyi.com.tw/rent/ 2024-Q1.
If selectors stop matching, open the page in DevTools and re-check.
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

BASE_URL = "https://www.sinyi.com.tw"

# Map config city names → Sinyi URL city slugs
# FIXME: verify these against sinyi.com.tw/rent/ dropdown values
CITY_SLUGS: dict[str, str] = {
    "台北市": "taipei-city",
    "新北市": "new-taipei-city",
    "基隆市": "keelung-city",
    "桃園市": "taoyuan-city",
    "新竹市": "hsinchu-city",
    "新竹縣": "hsinchu-county",
    "台中市": "taichung-city",
    "台南市": "tainan-city",
    "高雄市": "kaohsiung-city",
}

ROOM_TYPE_SLUGS: dict[str, str] = {
    "整層住家": "whole",
    "獨立套房": "suite",
    "分租套房": "shared-suite",
    "雅房":     "room",
}


def _build_search_url(city_slug: str, config: dict, page: int = 1) -> str:
    room_types = config.get("room_types", [])
    type_slug  = ROOM_TYPE_SLUGS.get(room_types[0], "") if room_types else ""
    floor_min  = config.get("floor_min", 1)

    qs = {
        "price_lower": config.get("price_min", 0),
        "price_upper": config.get("price_max", 999_999),
        "page":        page,
    }
    if type_slug:
        qs["property_type"] = type_slug
    if floor_min > 1:
        qs["floor_lower"] = floor_min
    if config.get("has_elevator"):
        qs["elevator"] = 1
    if config.get("pet_friendly"):
        qs["pet"] = 1

    # FIXME: confirm the exact URL path and param names against sinyi.com.tw
    return f"{BASE_URL}/rent/{city_slug}/?{urlencode(qs)}"


def _parse_floor_sinyi(text: str) -> tuple[Optional[int], Optional[int], str]:
    """Extract current/total floors from Sinyi's floor text.

    Sinyi typically shows '5樓/12樓' or '5F/12F'.
    Returns (current, total, raw_str).
    """
    cur, tot = parse_floor_string(text)
    return cur, tot, text.strip()


def _parse_card(card: Tag, city_name: str) -> Optional[Property]:
    """Parse one listing <div> into a Property.

    FIXME: selectors below are best-guess based on sinyi.com.tw HTML structure.
    Open DevTools on the listing page and adjust class names as needed.
    """
    try:
        # Title
        title_el = card.select_one(".item-title, h3.name, .house-name")
        title = title_el.get_text(strip=True) if title_el else ""

        # Link + ID
        link_el = card.select_one("a[href*='/rent/']")
        if not link_el:
            return None
        href = str(link_el.get("href", ""))
        if not href.startswith("http"):
            href = BASE_URL + href
        # Extract numeric ID from URL e.g. /rent/detail/12345678/
        id_match = re.search(r"/(\d{6,})", href)
        listing_id = id_match.group(1) if id_match else href

        # Price
        price_el = card.select_one(".price, .rent-price, [class*='price']")
        price = clean_price(price_el.get_text(strip=True) if price_el else None)
        if price is None:
            return None

        # Area
        area_el = card.select_one(".area, [class*='area']")
        area = clean_area(area_el.get_text(strip=True) if area_el else None)

        # Layout
        layout_el = card.select_one(".layout, .room-type, [class*='layout']")
        layout = layout_el.get_text(strip=True) if layout_el else None

        # Floor
        floor_el = card.select_one(".floor, [class*='floor']")
        floor_raw = floor_el.get_text(strip=True) if floor_el else ""
        cur_floor, tot_floors, floor_str = _parse_floor_sinyi(floor_raw)

        # Address
        addr_el = card.select_one(".address, [class*='address']")
        address = addr_el.get_text(strip=True) if addr_el else city_name

        # Image
        img_el = card.select_one("img[src], img[data-src]")
        image_url = None
        if img_el:
            image_url = str(img_el.get("data-src") or img_el.get("src") or "")
            if image_url.startswith("//"):
                image_url = "https:" + image_url

        return Property(
            id=listing_id,
            platform="Sinyi",
            title=title,
            price=price,
            area=area,
            layout=layout,
            address=address,
            floor=floor_str or None,
            image_url=image_url or None,
            link=href,
            current_floor=cur_floor,
            total_floors=tot_floors,
        )
    except Exception as exc:
        logger.warning("Sinyi: failed to parse card — %s", exc)
        return None


def _fetch_city(city_name: str, city_slug: str, config: dict) -> list[Property]:
    results: list[Property] = []
    page = 1

    with httpx.Client(headers=HEADERS, timeout=20, follow_redirects=True) as client:
        while True:
            url  = _build_search_url(city_slug, config, page)
            logger.debug("Sinyi: GET %s", url)
            resp = client.get(url)
            if resp.status_code != 200:
                logger.warning("Sinyi: HTTP %d for %s", resp.status_code, url)
                break

            soup  = BeautifulSoup(resp.text, "lxml")
            cards = soup.select(".item-list .item, .house-list .house-item, [class*='list-item']")

            if not cards:
                logger.info("Sinyi: no cards found on page %d — stopping", page)
                break

            for card in cards:
                prop = _parse_card(card, city_name)
                if prop:
                    results.append(prop)

            # Pagination: stop if no "next page" link
            next_pg = soup.select_one("a.next, [class*='pagination'] a[rel='next']")
            if not next_pg:
                break

            page += 1
            throttle(1.5)

    return results


def fetch_sinyi(config: dict) -> list[Property]:
    cities = config.get("target_cities", [])
    all_props: list[Property] = []

    for city_name in cities:
        city_slug = CITY_SLUGS.get(city_name)
        if city_slug is None:
            logger.warning("Sinyi: unknown city '%s', skipping", city_name)
            continue
        logger.info("Sinyi: fetching %s …", city_name)
        props = _fetch_city(city_name, city_slug, config)
        logger.info("Sinyi: got %d listings for %s", len(props), city_name)
        all_props.extend(props)

    return all_props
