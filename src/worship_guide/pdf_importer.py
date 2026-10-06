
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import csv

from .pdf_tools import extract_pdf_pages
from .ocr_titles import ocr_title_directory, create_ocr_backend

@dataclass
class ImportResult:
    pdf_path: Path
    work_dir: Path
    pages_dir: Path
    title_crops_dir: Path
    ocr_csv: Path
    page_count: int

def import_pdf_to_ocr(
    pdf_path: str | Path,
    work_dir: str | Path,
    *,
    start_page: int = 1,
    end_page: int | None = None,
    engine: str = "easyocr",
) -> ImportResult:
    pdf_path = Path(pdf_path)
    work_dir = Path(work_dir)
    pdf_work = work_dir / "pdf_work"
    ocr_out = work_dir / "ocr_titles"

    manifest = extract_pdf_pages(
        pdf_path=pdf_path,
        output_dir=pdf_work,
        start_page=start_page,
        end_page=end_page,
        title_crop_ratio=0.13,
    )

    title_dir = pdf_work / "title_crops"
    backend = create_ocr_backend(engine)
    ocr_title_directory(
        title_dir=title_dir,
        output_dir=ocr_out,
        start_page=start_page,
        end_page=end_page,
        backend=backend,
    )

    csv_path = ocr_out / "titles_ocr.csv"
    count = 0
    if csv_path.exists():
        with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
            count = sum(1 for _ in csv.DictReader(f))
    return ImportResult(
        pdf_path=pdf_path,
        work_dir=work_dir,
        pages_dir=pdf_work / "pages",
        title_crops_dir=title_dir,
        ocr_csv=csv_path,
        page_count=count,
    )
