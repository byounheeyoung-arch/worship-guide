"""Conservative key candidates. Suggestions never set an authoritative key."""

from __future__ import annotations
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from PIL import Image
import numpy as np

ROOTS = (
    "C",
    "Db",
    "C#",
    "D",
    "Eb",
    "D#",
    "E",
    "Fb",
    "E#",
    "F",
    "Gb",
    "F#",
    "G",
    "Ab",
    "G#",
    "A",
    "Bb",
    "A#",
    "B",
    "Cb",
    "B#",
)
KEYS = ["", *ROOTS, *(r + "m" for r in ROOTS)]
_PC = {
    "C": 0,
    "B#": 0,
    "Db": 1,
    "C#": 1,
    "D": 2,
    "Eb": 3,
    "D#": 3,
    "E": 4,
    "Fb": 4,
    "F": 5,
    "E#": 5,
    "Gb": 6,
    "F#": 6,
    "G": 7,
    "Ab": 8,
    "G#": 8,
    "A": 9,
    "Bb": 10,
    "A#": 10,
    "B": 11,
    "Cb": 11,
}
CHORD_RE = re.compile(
    r"(?<![A-Za-z0-9])([A-G])([#b♭♯]?)(maj|min|sus|dim|aug|m|M)?(?:\d{0,2})(?:\([^)]{1,8}\))?(?:/[A-G][#b♭♯]?)?(?![A-Za-z0-9])"
)
_SIGNATURE = r"([A-G])\s*([#b♭♯]?)\s*(minor|major|min|maj|m|M)?"
EXPLICIT = [
    re.compile(
        r"(?:\b[Kk][Ee][Yy]|조성|조)\s*[:=]?\s*" + _SIGNATURE + r"(?![A-Za-z0-9])"
    ),
    re.compile(
        r"(?<![A-Za-z0-9])"
        + _SIGNATURE
        + r"\s*(?:[Kk][Ee][Yy]|장조|단조)(?![A-Za-z0-9])"
    ),
]


def normalize_signature(value) -> str:
    value = str(value or "").strip().replace("♭", "b").replace("♯", "#")
    if not value:
        return ""
    m = re.fullmatch(r"([A-Ga-g])([#b]?)(m|minor|major|maj|min|M)?", value)
    if not m:
        raise ValueError(f"지원하지 않는 Key: {value}")
    key = m[1].upper() + m[2] + ("m" if m[3] in {"m", "minor", "min"} else "")
    if key not in KEYS:
        raise ValueError(f"지원하지 않는 Key: {value}")
    return key


def extract_chord_roots(texts: list[str]) -> list[tuple[str, bool]]:
    return [
        (m[1] + m[2].replace("♭", "b").replace("♯", "#"), m[3] in {"m", "min"})
        for text in texts
        for m in CHORD_RE.finditer(text or "")
    ]


def infer_key_from_chords(chords):
    if len(chords) < 4 or len(set(r for r, _ in chords)) < 2:
        return None, 0.0
    candidates = []
    for tonic, minor in set(chords):
        if tonic not in _PC:
            continue
        scale = {0, 2, 3, 5, 7, 8, 10} if minor else {0, 2, 4, 5, 7, 9, 11}
        fit = sum(
            (_PC.get(r, -99) - _PC[tonic]) % 12 in scale for r, _ in chords
        ) / len(chords)
        count = sum(r == tonic and m == minor for r, m in chords) / len(chords)
        edge = int(chords[0] == (tonic, minor)) + int(chords[-1] == (tonic, minor))
        candidates.append(
            (0.55 * fit + 0.25 * count + 0.1 * edge, tonic + ("m" if minor else ""))
        )
    candidates.sort(reverse=True)
    if len(candidates) < 2 or candidates[0][0] - candidates[1][0] < 0.1:
        return None, 0.0
    confidence = min(0.74, candidates[0][0])
    if confidence < 0.65:
        return None, round(confidence, 4)
    return candidates[0][1], round(confidence, 4)


@dataclass(frozen=True)
class KeyCandidate:
    key: str | None
    confidence: float
    method: str
    texts: list[str]
    chords: list[tuple[str, bool]]
    reason: str = ""

    def evidence(self):
        return asdict(self)


def detect_key_candidate(texts):
    explicit = set()
    for text in texts:
        for pattern in EXPLICIT:
            for m in pattern.finditer(text):
                key = m[1] + m[2].replace("♭", "b").replace("♯", "#")
                minor = m[3] in {"m", "minor", "min"} or "단조" in m[0]
                explicit.add(key + ("m" if minor else ""))
    chords = extract_chord_roots(texts)
    if len(explicit) == 1:
        return KeyCandidate(explicit.pop(), 0.95, "printed", texts, chords)
    if len(explicit) > 1:
        return KeyCandidate(
            None, 0, "conflict", texts, chords, "Conflicting printed key labels"
        )
    key, confidence = infer_key_from_chords(chords)
    return KeyCandidate(
        key,
        confidence,
        "chords" if key else "unknown",
        texts,
        chords,
        "Manual confirmation required; staff signature is not automatically read",
    )


class EasyOCRKeyDetector:
    def __init__(self, reader):
        self.reader = reader

    def detect(self, image_path):
        with Image.open(image_path) as im:
            crop = im.convert("RGB").crop(
                (0, 0, im.width, max(1, int(im.height * 0.32)))
            )
            outputs = self.reader.readtext(np.array(crop), detail=1, paragraph=False)
        result = detect_key_candidate(
            [str(o[1]).strip() for o in outputs if len(o) >= 3]
        )
        return result.key, result.confidence, result.texts
