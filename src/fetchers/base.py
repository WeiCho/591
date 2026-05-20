"""Shared utilities for all platform fetchers."""
from __future__ import annotations
import re
import time
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Mimic a real browser to reduce bot-detection
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

JSON_HEADERS = {
    **HEADERS,
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "X-Requested-With": "XMLHttpRequest",
}


def clean_price(raw: str | int | None) -> Optional[int]:
    """Parse price strings like '20,000' or '20000' into int."""
    if raw is None:
        return None
    if isinstance(raw, int):
        return raw
    digits = re.sub(r"[^\d]", "", str(raw))
    return int(digits) if digits else None


def clean_area(raw: str | float | None) -> Optional[float]:
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    match = re.search(r"[\d.]+", str(raw))
    return float(match.group()) if match else None


def throttle(seconds: float = 1.5) -> None:
    time.sleep(seconds)
