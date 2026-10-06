
from __future__ import annotations
from pathlib import Path
import re
from collections import Counter
from PIL import Image
import numpy as np

# Common chord roots including flats/sharps and minor suffix.
CHORD_RE = re.compile(
    r"(?<![A-Za-z])([A-G])([#b♭♯]?)(m|maj|min|sus|dim|aug)?(?:\d{0,2})?(?:/[A-G][#b♭♯]?)?(?![A-Za-z])",
    re.IGNORECASE,
)

def _normalize_root(letter: str, accidental: str) -> str:
    accidental = accidental.replace("♭", "b").replace("♯", "#")
    return letter.upper() + accidental

def extract_chord_roots(texts: list[str]) -> list[tuple[str, bool]]:
    out = []
    for text in texts:
        for m in CHORD_RE.finditer(text or ""):
            root = _normalize_root(m.group(1), m.group(2))
            qual = (m.group(3) or "").lower()
            minor = qual in {"m", "min"}
            out.append((root, minor))
    return out

def infer_key_from_chords(chords: list[tuple[str, bool]]) -> tuple[str | None, float]:
    """
    Conservative candidate inference.
    This is NOT treated as final truth; Review Center still requires user approval.
    """
    if not chords:
        return None, 0.0

    # Score tonic candidates using occurrence, first chord, and last chord.
    roots = [r for r, _ in chords]
    counts = Counter(roots)
    first_root, first_minor = chords[0]
    last_root, last_minor = chords[-1]

    candidates = {}
    for root, cnt in counts.items():
        score = cnt * 1.0
        if root == first_root:
            score += 1.5
        if root == last_root:
            score += 2.0
        candidates[root] = score

    tonic = max(candidates, key=candidates.get)
    # Minor only when tonic occurs as minor and especially if first/last tonic is minor.
    tonic_minor_votes = sum(1 for r, m in chords if r == tonic and m)
    tonic_total = sum(1 for r, _ in chords if r == tonic)
    is_minor = tonic_total > 0 and tonic_minor_votes / tonic_total >= 0.6
    if tonic == first_root and first_minor:
        is_minor = True
    if tonic == last_root and last_minor:
        is_minor = True

    total_score = sum(candidates.values()) or 1.0
    conf = min(0.95, candidates[tonic] / total_score + 0.15)
    return tonic + ("m" if is_minor else ""), round(conf, 4)

class EasyOCRKeyDetector:
    def __init__(self, reader):
        self.reader = reader

    def detect(self, image_path: str | Path) -> tuple[str | None, float, list[str]]:
        p = Path(image_path)
        im = Image.open(p).convert("RGB")
        # Chords/key clues are concentrated near the top of the score.
        crop = im.crop((0, 0, im.width, max(1, int(im.height * 0.32))))
        arr = np.array(crop)
        outputs = self.reader.readtext(arr, detail=1, paragraph=False)
        texts = []
        for item in outputs:
            try:
                text = str(item[1]).strip()
            except Exception:
                continue
            if text:
                texts.append(text)
        chords = extract_chord_roots(texts)
        key, conf = infer_key_from_chords(chords)
        return key, conf, texts
