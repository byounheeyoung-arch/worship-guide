from __future__ import annotations

import csv
import json
import re
import io
import os
import subprocess
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Protocol

from .title_lexicon import best_lexicon_match, load_lexicon

from PIL import Image, ImageEnhance, ImageFilter, ImageOps
import numpy as np


_HANGUL_RE = re.compile(r"[가-힣]")
_SPACE_RE = re.compile(r"\s+")
_NOISE_PATTERNS = (
    "kang score",
    "king score",
    "words & music",
    "words and music",
    "copyright",
    "arranged",
    "composed",
    "lyrics",
)


@dataclass(slots=True)
class OCRLine:
    text: str
    confidence: float
    box: list[list[float]] | None = None


@dataclass(slots=True)
class TitleOCRResult:
    page: int
    image: str
    title: str
    raw_title: str
    confidence: float
    review_required: bool
    candidates: list[str]
    lexicon_match: str = ""
    lexicon_score: float = 0.0
    raw_lines: list[dict[str, Any]] | None = None


class OCRBackend(Protocol):
    def read(self, image_path: Path) -> list[OCRLine]: ...


class EasyOCRBackend:
    """EasyOCR adapter for Windows-friendly Korean title recognition."""

    def __init__(self, *, gpu: bool = False) -> None:
        try:
            import easyocr  # type: ignore
        except ImportError as exc:  # pragma: no cover - environment-specific
            raise RuntimeError(
                'EasyOCR가 설치되어 있지 않습니다. python -m pip install -e ".[easyocr]" 를 실행하세요.'
            ) from exc

        self._reader = easyocr.Reader(["ko", "en"], gpu=gpu, verbose=False)

    def read(self, image_path: Path) -> list[OCRLine]:
        # EasyOCR/OpenCV can fail to read Windows paths containing Korean
        # characters. Load through Pillow and pass a NumPy array instead.
        with Image.open(image_path) as image:
            image_array = np.array(image.convert("RGB"))
        if image_array.size == 0:
            raise RuntimeError(f"OCR 이미지를 읽을 수 없습니다: {image_path}")
        outputs = self._reader.readtext(image_array, detail=1, paragraph=False)
        lines: list[OCRLine] = []
        for item in outputs:
            if not isinstance(item, (list, tuple)) or len(item) < 3:
                continue
            box, text, confidence = item[0], item[1], item[2]
            lines.append(
                OCRLine(
                    text=str(text),
                    confidence=float(confidence),
                    box=_to_plain_box(box),
                )
            )
        return lines


def create_ocr_backend(engine: str = "easyocr", *, gpu: bool = False) -> OCRBackend:
    normalized = engine.strip().lower()
    if normalized in {"easy", "easyocr"}:
        return EasyOCRBackend(gpu=gpu)
    if normalized in {"paddle", "paddleocr"}:
        return PaddleOCRBackend()
    if normalized == "tesseract":
        return TesseractBackend()
    raise ValueError(f"지원하지 않는 OCR 엔진입니다: {engine}")


class TesseractBackend:
    """CPU/offline Korean OCR using the installed Tesseract executable."""

    def __init__(self, *, tessdata_dir=None, language="kor+eng", executable=None):
        self.executable = (
            executable or os.environ.get("WG_TESSERACT") or shutil.which("tesseract")
        )
        if not self.executable:
            raise RuntimeError(
                "Tesseract 실행 파일이 없습니다. EasyOCR를 선택하거나 Tesseract를 설치하세요."
            )
        self.tessdata_dir = str(tessdata_dir or os.environ.get("WG_TESSDATA_DIR") or "")
        self.language = language
        command = [self.executable, "--list-langs"]
        if self.tessdata_dir:
            command += ["--tessdata-dir", self.tessdata_dir]
        available = subprocess.run(
            command, capture_output=True, text=True, timeout=20, check=True
        ).stdout.splitlines()
        missing = set(language.split("+")) - set(available)
        if missing:
            raise RuntimeError(
                "Tesseract 언어 데이터가 없습니다: " + ", ".join(sorted(missing))
            )

    def read(self, image_path: Path) -> list[OCRLine]:
        command = [
            self.executable,
            str(image_path),
            "stdout",
            "-l",
            self.language,
            "--psm",
            "11",
        ]
        if self.tessdata_dir:
            command += ["--tessdata-dir", self.tessdata_dir]
        # Do not rely on <custom tessdata>/configs/tsv being installed.
        command += ["-c", "tessedit_create_tsv=1", "-c", "tessedit_create_txt=0"]
        result = subprocess.run(
            command, capture_output=True, encoding="utf-8", timeout=120
        )
        if result.returncode:
            raise RuntimeError(result.stderr.strip() or "Tesseract OCR failed")
        if not result.stdout.startswith("level\tpage_num\t"):
            raise RuntimeError(
                "Tesseract가 TSV 결과를 반환하지 않았습니다: " + result.stderr.strip()
            )
        groups = {}
        for word in csv.DictReader(io.StringIO(result.stdout), delimiter="\t"):
            text = word.get("text", "").strip()
            if not text or word.get("level") != "5":
                continue
            key = tuple(word[k] for k in ("block_num", "par_num", "line_num"))
            groups.setdefault(key, []).append(word)
        lines = []
        for words in groups.values():
            left = min(int(w["left"]) for w in words)
            top = min(int(w["top"]) for w in words)
            right = max(int(w["left"]) + int(w["width"]) for w in words)
            bottom = max(int(w["top"]) + int(w["height"]) for w in words)
            lines.append(
                OCRLine(
                    " ".join(w["text"] for w in words),
                    sum(max(0.0, float(w["conf"])) for w in words) / (100 * len(words)),
                    [[left, top], [right, top], [right, bottom], [left, bottom]],
                )
            )
        return lines


class PaddleOCRBackend:
    """PaddleOCR 3.x adapter.

    PaddleOCR is imported lazily so the rest of the project keeps working
    without the optional OCR dependencies.
    """

    def __init__(self) -> None:
        try:
            from paddleocr import PaddleOCR  # type: ignore
        except ImportError as exc:  # pragma: no cover - environment-specific
            raise RuntimeError(
                "PaddleOCR가 설치되어 있지 않습니다. README의 OCR 설치 명령을 실행하세요."
            ) from exc

        self._ocr = PaddleOCR(
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
            engine="paddle",
        )

    def read(self, image_path: Path) -> list[OCRLine]:
        outputs = self._ocr.predict(str(image_path))
        lines: list[OCRLine] = []
        for output in outputs:
            payload = _result_to_dict(output)
            result = payload.get("res", payload)
            texts = list(result.get("rec_texts") or [])
            scores = list(result.get("rec_scores") or [])
            boxes = list(result.get("rec_polys") or result.get("rec_boxes") or [])
            for index, text in enumerate(texts):
                confidence = float(scores[index]) if index < len(scores) else 0.0
                box = _to_plain_box(boxes[index]) if index < len(boxes) else None
                lines.append(OCRLine(text=str(text), confidence=confidence, box=box))
        return lines


def _result_to_dict(result: Any) -> dict[str, Any]:
    if isinstance(result, dict):
        return result

    for attr in ("json", "to_dict", "dict"):
        value = getattr(result, attr, None)
        if value is None:
            continue
        try:
            converted = value() if callable(value) else value
        except TypeError:
            continue
        if isinstance(converted, str):
            try:
                converted = json.loads(converted)
            except json.JSONDecodeError:
                continue
        if isinstance(converted, dict):
            return converted

    try:
        return dict(result)
    except Exception as exc:  # pragma: no cover - library-specific
        raise RuntimeError("PaddleOCR 결과 형식을 해석할 수 없습니다.") from exc


def _to_plain_box(value: Any) -> list[list[float]] | None:
    if value is None:
        return None
    try:
        raw = value.tolist() if hasattr(value, "tolist") else value
        if raw and isinstance(raw[0], (int, float)):
            # rec_boxes can be [x1, y1, x2, y2]
            x1, y1, x2, y2 = map(float, raw[:4])
            return [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]
        return [[float(x), float(y)] for x, y in raw]
    except Exception:
        return None


def preprocess_title_crop(source: Path, destination: Path, *, scale: int = 2) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source) as image:
        gray = ImageOps.grayscale(image)
        gray = ImageOps.autocontrast(gray, cutoff=1)
        gray = ImageEnhance.Contrast(gray).enhance(1.8)
        gray = gray.filter(ImageFilter.SHARPEN)
        if scale > 1:
            gray = gray.resize(
                (gray.width * scale, gray.height * scale), Image.Resampling.LANCZOS
            )
        gray.save(destination)
    return destination


def normalize_title(text: str) -> str:
    text = text.replace("_", " ").replace("|", " ")
    text = re.sub(r"[^0-9A-Za-z가-힣()\[\]·'’\- ]+", " ", text)
    return _SPACE_RE.sub(" ", text).strip(" -")


def choose_title(
    lines: Iterable[OCRLine], image_width: int, image_height: int | None = None
) -> tuple[str, float, list[str]]:
    lines = list(lines)
    heights = [
        max(p[1] for p in line.box) - min(p[1] for p in line.box)
        for line in lines
        if line.box
    ]
    largest_height = max(heights, default=1)
    scored: list[tuple[float, OCRLine, str]] = []
    for line in lines:
        text = normalize_title(line.text)
        if not text or len(text) < 2:
            continue
        lowered = text.lower()
        if any(noise in lowered for noise in _NOISE_PATTERNS):
            continue

        hangul_count = len(_HANGUL_RE.findall(text))
        if hangul_count == 0 and len(text) <= 3:
            continue
        if hangul_count == 0:
            from .key_ocr import CHORD_RE

            rest = CHORD_RE.sub("", text)
            # Reject score/chord clutter, retaining normal English titles.
            words = re.findall(r"[A-Za-z]{2,}", rest)
            if len(words) < 2 or sum(len(w) for w in words) < len(text) * 0.5:
                continue

        center_bonus = 0.0
        size_bonus = 0.0
        if line.box:
            xs = [point[0] for point in line.box]
            ys = [point[1] for point in line.box]
            center_x = (min(xs) + max(xs)) / 2
            width = max(xs) - min(xs)
            center_distance = abs(center_x - image_width / 2) / max(1, image_width / 2)
            center_bonus = max(0.0, 1.0 - center_distance) * 0.25
            size_bonus = min(0.2, width / max(1, image_width) * 0.3)
            height_bonus = (
                min(1.0, (max(ys) - min(ys)) / max(1.0, largest_height)) * 0.4
            )
            crop_height = image_height or max(max(ys), 1)
            top_bonus = max(0.0, 1.0 - min(ys) / max(1.0, crop_height)) * 0.4
        else:
            top_bonus = 0.0
            height_bonus = 0.0

        length_score = min(len(text), 20) / 20 * 0.15
        hangul_score = min(hangul_count, 12) / 12 * 0.25
        score = (
            line.confidence * 0.2
            + center_bonus
            + size_bonus * 0.3
            + top_bonus
            + height_bonus
            + length_score * 0.5
            + hangul_score * 0.5
        )
        scored.append((score, line, text))

    scored.sort(key=lambda item: item[0], reverse=True)
    if not scored:
        return "", 0.0, []

    best_score, best_line, best_text = scored[0]
    candidates = [text for _, _, text in scored[:5]]
    confidence = min(
        1.0, max(0.0, best_line.confidence * 0.75 + min(best_score, 1.0) * 0.25)
    )
    return best_text, confidence, candidates


def ocr_title_directory(
    title_dir: Path,
    output_dir: Path,
    *,
    backend: OCRBackend | None = None,
    start_page: int | None = None,
    end_page: int | None = None,
    review_threshold: float = 0.82,
    lexicon_path: Path | None = None,
    lexicon_threshold: float = 0.72,
) -> list[TitleOCRResult]:
    if not title_dir.exists() or not title_dir.is_dir():
        raise FileNotFoundError(f"제목 이미지 폴더가 없습니다: {title_dir}")
    if not 0.0 <= review_threshold <= 1.0:
        raise ValueError("review_threshold는 0~1 사이여야 합니다.")

    backend = backend or EasyOCRBackend()
    lexicon_entries = load_lexicon(lexicon_path) if lexicon_path else []
    output_dir.mkdir(parents=True, exist_ok=True)
    preprocessed_dir = output_dir / "preprocessed"
    preprocessed_dir.mkdir(parents=True, exist_ok=True)

    results: list[TitleOCRResult] = []
    for image_path in sorted(title_dir.glob("title_*.png")):
        page = _page_number_from_name(image_path.name)
        if start_page is not None and page < start_page:
            continue
        if end_page is not None and page > end_page:
            continue

        prepared = preprocess_title_crop(image_path, preprocessed_dir / image_path.name)
        lines = backend.read(prepared)
        with Image.open(prepared) as image:
            raw_title, confidence, candidates = choose_title(
                lines, image.width, image.height
            )

        corrected_title = raw_title
        lexicon_match = ""
        lexicon_score = 0.0
        if lexicon_entries and candidates:
            match = best_lexicon_match(candidates, lexicon_entries)
            if match is not None:
                lexicon_match = match.matched_text
                lexicon_score = round(match.score, 4)
                # Keep the raw candidate; approval is the only title boundary.

        review_required = True
        result = TitleOCRResult(
            page=page,
            image=str(image_path),
            title=corrected_title,
            raw_title=raw_title,
            confidence=round(confidence, 4),
            review_required=review_required,
            candidates=candidates,
            lexicon_match=lexicon_match,
            lexicon_score=lexicon_score,
            raw_lines=[asdict(line) for line in lines],
        )
        results.append(result)

    _write_title_results(results, output_dir)
    return results


def _page_number_from_name(name: str) -> int:
    match = re.search(r"(\d+)", name)
    if not match:
        raise ValueError(f"페이지 번호를 찾을 수 없습니다: {name}")
    return int(match.group(1))


def _write_title_results(results: list[TitleOCRResult], output_dir: Path) -> None:
    json_path = output_dir / "titles_ocr.json"
    csv_path = output_dir / "titles_ocr.csv"
    review_path = output_dir / "titles_review_queue.csv"

    json_path.write_text(
        json.dumps(
            [asdict(result) for result in results], ensure_ascii=False, indent=2
        ),
        encoding="utf-8",
    )

    fieldnames = [
        "page",
        "title",
        "raw_title",
        "confidence",
        "review_required",
        "lexicon_match",
        "lexicon_score",
        "image",
        "candidates",
    ]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=fieldnames)
        writer.writeheader()
        for result in results:
            writer.writerow(
                {
                    "page": result.page,
                    "title": result.title,
                    "raw_title": result.raw_title,
                    "confidence": result.confidence,
                    "review_required": result.review_required,
                    "lexicon_match": result.lexicon_match,
                    "lexicon_score": result.lexicon_score,
                    "image": result.image,
                    "candidates": " | ".join(result.candidates),
                }
            )

    with review_path.open("w", encoding="utf-8-sig", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=fieldnames)
        writer.writeheader()
        for result in results:
            if result.review_required:
                writer.writerow(
                    {
                        "page": result.page,
                        "title": result.title,
                        "confidence": result.confidence,
                        "review_required": result.review_required,
                        "image": result.image,
                        "candidates": " | ".join(result.candidates),
                    }
                )
