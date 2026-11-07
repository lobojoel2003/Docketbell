"""How many SMS segments a text costs.

Carriers bill per segment. A text that only uses the GSM-7 alphabet fits 160
characters in one segment (153 per segment when split). Any other character,
such as a curly quote, an accented "á" or any Chinese, Russian or Arabic letter,
switches the whole text to UCS-2: 70 characters, or 67 per segment when split.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

GSM7_BASIC = frozenset(
    "@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?"
    "¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà"
)
GSM7_EXTENDED = frozenset("^{}\\[~]|€\f")


@dataclass(frozen=True)
class SegmentInfo:
    encoding: str  # "GSM-7" or "UCS-2"
    units: int  # characters as the network counts them
    segments: int
    per_segment: int
    non_gsm: tuple[str, ...]  # characters that forced UCS-2

    @property
    def is_unicode(self) -> bool:
        return self.encoding == "UCS-2"


def analyze(text: str) -> SegmentInfo:
    non_gsm = [ch for ch in text if ch not in GSM7_BASIC and ch not in GSM7_EXTENDED]
    if not non_gsm:
        units = sum(2 if ch in GSM7_EXTENDED else 1 for ch in text)
        single, multi, encoding = 160, 153, "GSM-7"
    else:
        units = len(text.encode("utf-16-le")) // 2
        single, multi, encoding = 70, 67, "UCS-2"
    if units <= single:
        segments, per = (1 if units else 0), single
    else:
        segments, per = math.ceil(units / multi), multi
    return SegmentInfo(encoding, units, segments, per, tuple(dict.fromkeys(non_gsm)))
