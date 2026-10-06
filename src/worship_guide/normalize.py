from __future__ import annotations

import re
import unicodedata
from pathlib import Path

KEY_PATTERN = re.compile(
    r"(?<![A-Za-z])(?P<key>[A-Ga-g])\s*(?P<accidental>[#♯b♭]?)(?:\s*(?:key|키|코드))?(?![A-Za-z])",
    re.IGNORECASE,
)

TRAILING_NOISE = re.compile(
    r"(?:[_\-\s]*(?:원키|기타|화음|멜로디|악보|score|sheet|ver\.?\s*\d+|\d+페이지|\(.*?\)|\[.*?\]))+$",
    re.IGNORECASE,
)


def normalize_key(letter: str, accidental: str = "") -> str:
    letter = letter.upper()
    accidental = accidental.replace("♯", "#").replace("♭", "b")
    return f"{letter}{accidental}"


def parse_title_and_key(file_name: str) -> tuple[str, str | None, int]:
    stem = unicodedata.normalize("NFKC", Path(file_name).stem)
    stem = stem.replace("+", " ").replace("_", " ")

    matches = list(KEY_PATTERN.finditer(stem))
    detected_key: str | None = None
    confidence = 70

    # 파일 끝부분의 Key 표기를 우선합니다.
    for match in reversed(matches):
        tail = stem[match.end():].strip(" -_()[]")
        if len(tail) <= 8:
            detected_key = normalize_key(match.group("key"), match.group("accidental"))
            stem = (stem[: match.start()] + " " + stem[match.end():]).strip()
            confidence += 15
            break

    stem = re.sub(r"(?i)\b(?:key|키|코드)\b", " ", stem)
    stem = re.sub(r"[#♯]\s*\d+|[b♭]\s*\d+", " ", stem)
    stem = re.sub(r"\b\d+\b$", " ", stem)
    stem = TRAILING_NOISE.sub("", stem)
    stem = re.sub(r"\s+", " ", stem).strip(" -_.,")

    if not stem:
        stem = Path(file_name).stem
        confidence = 30

    return stem, detected_key, min(confidence, 100)


def canonical_title(title: str) -> str:
    value = unicodedata.normalize("NFKC", title)
    value = re.sub(r"[\s_\-+]+", "", value)
    value = re.sub(r"[^0-9A-Za-z가-힣]", "", value)
    return value.casefold()
