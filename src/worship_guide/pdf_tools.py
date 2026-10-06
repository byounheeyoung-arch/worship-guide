from __future__ import annotations

import csv
from pathlib import Path

import fitz
from PIL import Image


def extract_pdf_pages(
    pdf_path: Path,
    output_dir: Path,
    *,
    dpi: int = 180,
    start_page: int = 1,
    end_page: int | None = None,
    title_crop_ratio: float = 0.18,
) -> list[dict[str, str | int]]:
    """PDF 페이지를 PNG와 제목 영역 이미지로 추출하고 manifest를 반환합니다.

    페이지 번호는 사용자 관점의 1-based 인덱스를 사용합니다.
    """
    if not pdf_path.exists() or not pdf_path.is_file():
        raise FileNotFoundError(f"PDF 파일이 없습니다: {pdf_path}")
    if pdf_path.suffix.lower() != ".pdf":
        raise ValueError(f"PDF 파일만 처리할 수 있습니다: {pdf_path}")
    if dpi < 72 or dpi > 600:
        raise ValueError("dpi는 72~600 사이여야 합니다.")
    if not 0.05 <= title_crop_ratio <= 0.5:
        raise ValueError("title_crop_ratio는 0.05~0.5 사이여야 합니다.")

    pages_dir = output_dir / "pages"
    titles_dir = output_dir / "title_crops"
    pages_dir.mkdir(parents=True, exist_ok=True)
    titles_dir.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(pdf_path)
    try:
        page_count = doc.page_count
        if page_count == 0:
            return []

        first = max(1, start_page)
        last = page_count if end_page is None else min(page_count, end_page)
        if first > last:
            raise ValueError(f"페이지 범위가 잘못되었습니다: {first}~{last}")

        scale = dpi / 72
        matrix = fitz.Matrix(scale, scale)
        manifest: list[dict[str, str | int]] = []

        for page_number in range(first, last + 1):
            page = doc[page_number - 1]
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            page_name = f"page_{page_number:04d}.png"
            page_path = pages_dir / page_name
            pix.save(page_path)

            with Image.open(page_path) as image:
                crop_height = max(1, round(image.height * title_crop_ratio))
                title_crop = image.crop((0, 0, image.width, crop_height))
                title_name = f"title_{page_number:04d}.png"
                title_path = titles_dir / title_name
                title_crop.save(title_path)

                manifest.append(
                    {
                        "page": page_number,
                        "page_image": str(page_path),
                        "title_crop": str(title_path),
                        "width": image.width,
                        "height": image.height,
                    }
                )

        _write_manifest(manifest, output_dir / "pages_manifest.csv")
        return manifest
    finally:
        doc.close()


def _write_manifest(rows: list[dict[str, str | int]], path: Path) -> None:
    fieldnames = ["page", "page_image", "title_crop", "width", "height"]
    with path.open("w", encoding="utf-8-sig", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
