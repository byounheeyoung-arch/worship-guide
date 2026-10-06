"""Legacy result-file adapter around the canonical resumable pipeline."""

from dataclasses import dataclass
from pathlib import Path
import csv, json
from .db import WGDB
from .pipeline import import_document


@dataclass
class ImportResult:
    pdf_path: Path
    work_dir: Path
    pages_dir: Path
    title_crops_dir: Path
    ocr_csv: Path
    page_count: int


def import_pdf_to_ocr(
    pdf_path, work_dir, *, start_page=1, end_page=None, engine="easyocr", db_path=None
):
    output = Path(work_dir).resolve()
    (output / "ocr_titles").mkdir(parents=True, exist_ok=True)
    with WGDB(db_path) as db:
        result = import_document(
            db, pdf_path, start_page=start_page, end_page=end_page, engine=engine
        )
        rows = [
            r
            for r in db.review_queue(result.source_id, True)
            if start_page <= r["page"] <= (end_page or 10**9)
        ]
        csv_path = output / "ocr_titles/titles_ocr.csv"
        with csv_path.open("w", encoding="utf-8-sig", newline="") as file:
            writer = csv.DictWriter(
                file,
                fieldnames=[
                    "page",
                    "title",
                    "raw_title",
                    "confidence",
                    "review_required",
                    "image",
                    "source_pdf",
                    "key_candidate",
                ],
            )
            writer.writeheader()
            for row in rows:
                writer.writerow(
                    {
                        "page": row["page"],
                        "title": row["raw_title"],
                        "raw_title": row["raw_title"],
                        "confidence": row["confidence"],
                        "review_required": True,
                        "image": row["image_path"],
                        "source_pdf": row["source_pdf"],
                        "key_candidate": row["key_candidate"],
                    }
                )
        source = db.conn.execute(
            "SELECT * FROM source_documents WHERE id=?", (result.source_id,)
        ).fetchone()
        (output / "import_manifest.json").write_text(
            json.dumps(
                {
                    "source_pdf": source["stored_path"],
                    "source_sha256": source["sha256"],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        root = db.path.parent / "work" / source["sha256"]
        return ImportResult(
            Path(source["stored_path"]),
            output,
            root / "pages",
            root / "title_crops",
            csv_path,
            len(rows),
        )
