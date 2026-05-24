"""591.com.tw fetcher — v3/web/rent/list API.

Strategy
--------
1. Launch headless Chromium, load rent.591.com.tw once to let JS generate
   a `deviceid` (stored in localStorage / cookie by the SPA).
2. Extract `deviceid` from the page context.
3. Use context.request to paginate bff-house.591.com.tw/v3/web/rent/list,
   passing deviceid + device=pc headers.  No CSRF needed.
"""
from __future__ import annotations
import asyncio
import logging
import time
from datetime import datetime, timezone

from playwright.async_api import async_playwright

from ..models import Property, parse_floor_string
from .base import clean_area, clean_price, throttle

logger = logging.getLogger(__name__)

CITY_IDS: dict[str, int] = {
    "台北市": 1,
    "新北市": 3,
    "基隆市": 5,
    "桃園市": 8,
    "新竹市": 10,
    "新竹縣": 11,
    "苗栗縣": 12,
    "台中市": 15,
    "彰化縣": 17,
    "南投縣": 19,
    "雲林縣": 20,
    "嘉義市": 21,
    "台南市": 28,
    "高雄市": 22,
    "屏東縣": 33,
    "花蓮縣": 38,
    "台東縣": 35,
    "宜蘭縣": 7,
    "澎湖縣": 41,
}

# 591 section IDs — 實測對照（API param: section）
SECTION_IDS: dict[str, int] = {
    # 新北市（regionid=3）
    "板橋": 26,
    "三重": 43,
    "中和": 38,
    "永和": 37,
    "新莊": 44,
    "新店": 34,
    "樹林": 41,
    "鶯歌": 42,
    "三峽": 40,
    "淡水": 50,
    "汐止": 27,
    "瑞芳": 30,
    "土城": 39,
    "蘆洲": 47,
    "五股": 48,
    "泰山": 45,
    "林口": 46,
    "深坑": 28,
    "烏來": 36,
    "三芝": 51,
    "八里": 49,
    "萬里": 20,
    "金山": 21,
}

ROOM_TYPE_CODES: dict[str, int] = {
    "整層住家": 1,
    "獨立套房": 2,
    "分租套房": 3,
    "雅房":     4,
}

API_URL   = "https://bff-house.591.com.tw/v3/web/rent/list"
PAGE_SIZE = 30

_raw_keys_logged = False  # print API field names once for debugging


def _api_headers(deviceid: str) -> dict:
    return {
        "deviceid":        deviceid,
        "device":          "pc",
        "Accept":          "application/json, text/plain, */*",
        "Accept-Language": "zh-TW,zh;q=0.9",
        "Referer":         "https://rent.591.com.tw/",
        "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    }


def _build_params(
    city_id:    int,
    kind:       int,
    price_min:  int,
    price_max:  int,
    floor_min:  int,
    first_row:  int,
    timestamp:  int,
    section_id: int | None = None,
) -> dict:
    p: dict = {
        "timestamp": timestamp,
        "regionid":  city_id,
        "kind":      kind,
        "firstRow":  first_row,
    }
    if price_min > 0 or price_max < 999_999:
        p["price"] = f"{price_min}_{price_max}"
    if floor_min > 1:
        p["floor"] = f"{floor_min}_"
    if section_id is not None:
        p["section"] = section_id
    return p


def _parse_item(raw: dict) -> Property | None:
    global _raw_keys_logged
    if not _raw_keys_logged:
        logger.info("591 raw item keys: %s", list(raw.keys()))
        _raw_keys_logged = True
    try:
        post_id = str(raw.get("id", ""))
        if not post_id:
            return None

        floor_name = raw.get("floor_name") or ""
        current_floor, total_floors = parse_floor_string(floor_name)

        price_str = str(raw.get("price") or "").replace(",", "").strip()
        price = clean_price(price_str)
        if price is None:
            return None

        area_str = str(raw.get("area_name") or raw.get("area") or "")
        area = clean_area(area_str)

        photos = raw.get("photoList") or []
        image_url = photos[0] if photos else raw.get("cover") or None

        link = raw.get("url") or f"https://rent.591.com.tw/{post_id}"

        tags = raw.get("tags") or []
        has_elevator = "有電梯" in tags

        # post_time is a Unix timestamp (seconds) returned by the 591 API
        listed_date: str | None = None
        post_ts = raw.get("post_time") or raw.get("posttime") or raw.get("insert_time")
        if post_ts:
            try:
                listed_date = datetime.fromtimestamp(int(post_ts), tz=timezone.utc).strftime("%Y-%m-%d")
            except (ValueError, OSError):
                pass

        return Property(
            id=post_id,
            platform="591",
            title=(raw.get("title") or "").strip(),
            price=price,
            area=area,
            layout=raw.get("layoutStr") or raw.get("layout"),
            address=(raw.get("address") or "").strip(),
            floor=floor_name or None,
            image_url=image_url,
            link=link,
            current_floor=current_floor,
            total_floors=total_floors,
            has_elevator=has_elevator,
            listed_date=listed_date,
        )
    except Exception as exc:
        logger.warning("591: failed to parse item id=%s — %s", raw.get("id"), exc)
        return None


async def _get_deviceid(ctx) -> str:
    """Load the SPA once to let JS generate deviceid, then extract it."""
    page = await ctx.new_page()
    try:
        await page.goto(
            "https://rent.591.com.tw/",
            wait_until="domcontentloaded",
            timeout=30_000,
        )
        await page.wait_for_timeout(2500)

        # deviceid is stored in localStorage by the SPA
        deviceid = await page.evaluate("() => localStorage.getItem('deviceid') || ''")
        if not deviceid:
            # fallback: check cookies
            cookies = {c["name"]: c["value"] for c in await ctx.cookies()}
            deviceid = cookies.get("deviceid", "")
        if not deviceid:
            logger.warning("591: deviceid not found, requests may fail")
        else:
            logger.debug("591: deviceid=%s", deviceid)
        return deviceid
    finally:
        await page.close()


async def _fetch_city_async(
    city_id:    int,
    kind:       int,
    price_min:  int,
    price_max:  int,
    floor_min:  int,
    section_id: int | None = None,
) -> list[Property]:
    results: list[Property] = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx     = await browser.new_context(locale="zh-TW")

        deviceid  = await _get_deviceid(ctx)
        headers   = _api_headers(deviceid)
        timestamp = int(time.time() * 1000)
        first_row = 0
        total     = None

        while True:
            params = _build_params(
                city_id, kind, price_min, price_max,
                floor_min, first_row, timestamp, section_id,
            )
            resp = await ctx.request.get(API_URL, params=params, headers=headers)

            if resp.status != 200:
                logger.error("591: HTTP %d at firstRow=%d", resp.status, first_row)
                break

            body = await resp.json()
            if str(body.get("status")) != "1":
                # API returns status=0 with empty items when past the last page — handled below
                pass

            data  = body.get("data", {})
            items = data.get("items") or []

            if total is None:
                total = int(data.get("total") or 0)
                logger.info("591 [city=%d kind=%d]: total=%d", city_id, kind, total)

            for raw in items:
                prop = _parse_item(raw)
                if prop:
                    results.append(prop)

            logger.info(
                "591 [city=%d section=%s]: rows %d-%d / %d",
                city_id, section_id, first_row, first_row + len(items), total,
            )

            first_row += PAGE_SIZE
            if not items or first_row >= (total or 0):
                break

            await asyncio.sleep(1.2)

        await browser.close()

    return results


def _resolve_section_ids(regions: list[str]) -> list[int | None]:
    """Map region names to 591 section IDs. Empty/全區 → [None] (no filter)."""
    if not regions or regions == ["全區"]:
        return [None]
    ids: list[int | None] = []
    for region in regions:
        sid = SECTION_IDS.get(region)
        if sid is None:
            logger.warning("591: unknown region '%s', skipping", region)
        else:
            ids.append(sid)
    return ids if ids else [None]


async def fetch_591_async(config: dict) -> list[Property]:
    room_types = config.get("room_types", [])
    price_min  = config.get("price_min", 0)
    price_max  = config.get("price_max", 999_999)
    floor_min  = config.get("floor_min", 1)

    # Support nested cities structure: [{"name": "新北市", "regions": [...]}]
    # Fall back to legacy flat target_cities + target_regions
    cities_cfg: list[dict] = config.get("cities") or []
    if not cities_cfg:
        cities_cfg = [
            {"name": c, "regions": config.get("target_regions", [])}
            for c in config.get("target_cities", [])
        ]

    all_props: list[Property] = []
    seen_ids:  set[str] = set()

    for city_entry in cities_cfg:
        city_name = city_entry.get("name", "")
        city_id   = CITY_IDS.get(city_name)
        if city_id is None:
            logger.warning("591: unknown city '%s', skipping", city_name)
            continue

        section_ids = _resolve_section_ids(city_entry.get("regions", []))

        for rt in room_types:
            kind = ROOM_TYPE_CODES.get(rt)
            if kind is None:
                logger.warning("591: unknown room_type '%s', skipping", rt)
                continue

            for section_id in section_ids:
                region_label = (
                    next((r for r, sid in SECTION_IDS.items() if sid == section_id), "全區")
                    if section_id is not None else "全區"
                )
                logger.info("591: fetching %s / %s / %s …", city_name, rt, region_label)
                props = await _fetch_city_async(
                    city_id, kind, price_min, price_max, floor_min, section_id
                )
                logger.info("591: got %d listings for %s/%s/%s",
                            len(props), city_name, rt, region_label)
                for p in props:
                    if p.id not in seen_ids:
                        seen_ids.add(p.id)
                        all_props.append(p)

    return all_props


def fetch_591(config: dict) -> list[Property]:
    return asyncio.run(fetch_591_async(config))
