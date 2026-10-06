from __future__ import annotations

import csv
import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

_CLEAN_RE = re.compile(r"[^0-9A-Za-z가-힣]+")


@dataclass(frozen=True, slots=True)
class LexiconEntry:
    canonical: str
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class LexiconMatch:
    canonical: str
    matched_text: str
    score: float


def _compact(text: str) -> str:
    return _CLEAN_RE.sub("", text).lower()


def _jamo(text: str) -> str:
    return unicodedata.normalize("NFD", _compact(text))


def title_similarity(a: str, b: str) -> float:
    """OCR-friendly title similarity.

    Korean syllables are decomposed to Jamo so small OCR mistakes such as
    닭/닮 or 틀/를 still score reasonably. Exact substring matches get a boost,
    which helps short OCR results such as '산 위에' -> '갈보리 산 위에'.
    """
    aa, bb = _compact(a), _compact(b)
    if not aa or not bb:
        return 0.0
    if aa == bb:
        return 1.0
    shorter, longer = (aa, bb) if len(aa) <= len(bb) else (bb, aa)
    substring = 0.92 if shorter in longer and len(shorter) >= 3 else 0.0
    syllable = SequenceMatcher(None, aa, bb).ratio()
    jamo = SequenceMatcher(None, _jamo(aa), _jamo(bb)).ratio()
    return min(1.0, max(substring, syllable * 0.35 + jamo * 0.65))


def load_lexicon(path: Path) -> list[LexiconEntry]:
    if not path.exists():
        return []
    entries: list[LexiconEntry] = []
    with path.open("r", encoding="utf-8-sig", newline="") as fp:
        for row in csv.DictReader(fp):
            canonical = (row.get("canonical") or "").strip()
            if not canonical:
                continue
            aliases = tuple(
                part.strip() for part in (row.get("aliases") or "").split("|") if part.strip()
            )
            entries.append(LexiconEntry(canonical=canonical, aliases=aliases))
    return entries


def best_lexicon_match(candidates: list[str], entries: list[LexiconEntry]) -> LexiconMatch | None:
    best: LexiconMatch | None = None
    for candidate in candidates:
        for entry in entries:
            for target in (entry.canonical, *entry.aliases):
                score = title_similarity(candidate, target)
                if best is None or score > best.score:
                    best = LexiconMatch(entry.canonical, target, score)
    return best
