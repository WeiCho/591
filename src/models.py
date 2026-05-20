from __future__ import annotations
import hashlib
import re
from dataclasses import dataclass, field
from typing import Optional


def parse_floor_string(raw: str | None) -> tuple[Optional[int], Optional[int]]:
    """Parse a raw floor string into (current_floor, total_floors).

    Handles common Taiwan rental formats:
      "5F/12F"     -> (5, 12)
      "5樓/共12樓"  -> (5, 12)
      "B1/8F"      -> (-1, 8)   (basement = negative)
      "頂樓/5F"    -> (5, 5)    (treated as top floor)
      "5F"         -> (5, None)
      None / ""    -> (None, None)
    """
    if not raw:
        return None, None

    s = raw.strip()

    # "頂樓" alone: we don't know total, signal both as None
    if re.fullmatch(r"頂[樓層]", s):
        return None, None

    # Regex: optional B prefix means basement (negative floor)
    _num = r"(?:B(\d+)|(\d+))"
    _sep = r"[FfLl樓層]?\s*/\s*(?:共)?"

    match = re.search(_num + _sep + _num + r"[FfLl樓層]?", s, re.IGNORECASE)
    if match:
        b1, n1, b2, n2 = match.groups()
        current = -int(b1) if b1 else int(n1)
        total   = -int(b2) if b2 else int(n2)
        # "頂樓/5F" style: first token is a text word, not a number → already
        # handled above; here both tokens are numbers.
        return current, total

    # Single floor number
    single = re.search(r"B(\d+)|(\d+)\s*[FfLl樓層]", s, re.IGNORECASE)
    if single:
        b, n = single.groups()
        return (-int(b) if b else int(n)), None

    return None, None


@dataclass
class Property:
    id: str
    platform: str           # "591" | "Sinyi" | "Yungching"
    title: str
    price: int              # monthly rent in NTD
    area: Optional[float]   # ping (坪)
    layout: Optional[str]   # e.g. "2房1廳"
    address: Optional[str]
    floor: Optional[str]    # raw string e.g. "5F/12F"
    image_url: Optional[str]
    link: str
    # Parsed floor fields; auto-filled from `floor` if left as None
    current_floor: Optional[int] = field(default=None)
    total_floors: Optional[int] = field(default=None)
    has_elevator: bool = field(default=False)
    hash_key: str = field(init=False)

    def __post_init__(self) -> None:
        self.hash_key = hashlib.md5(f"{self.platform}{self.id}".encode()).hexdigest()
        if self.current_floor is None and self.total_floors is None and self.floor:
            self.current_floor, self.total_floors = parse_floor_string(self.floor)
