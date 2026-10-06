"""Resumable PDF/image -> OCR -> review queue, one canonical WGDB."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from threading import Event
from uuid import uuid4

import fitz
from PIL import Image

from .db import WGDB
from .key_ocr import detect_key_candidate
from .ocr_titles import create_ocr_backend, preprocess_title_crop, choose_title

PIPELINE_REVISION = "2026-10-core1"


def file_sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def register_source(db: WGDB, path) -> int:
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    checksum = file_sha256(source)
    old = db.conn.execute(
        "SELECT * FROM source_documents WHERE sha256=?", (checksum,)
    ).fetchone()
    if old and Path(old["stored_path"]).is_file():
        return old["id"]
    if source.suffix.lower() not in {
        ".pdf",
        ".jpg",
        ".jpeg",
        ".png",
        ".webp",
        ".tif",
        ".tiff",
    }:
        raise ValueError("PDF 또는 악보 이미지를 선택하세요.")
    target = db.path.parent / "source" / (checksum + ".pdf")
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.stem + "." + uuid4().hex + ".tmp.pdf")
    try:
        if source.suffix.lower() == ".pdf":
            with fitz.open(source) as document:
                if document.needs_pass or document.page_count == 0:
                    raise ValueError("암호가 있거나 페이지가 없는 PDF입니다.")
                page_count = document.page_count
            shutil.copyfile(source, temporary)
        else:
            with (
                fitz.open(source) as image,
                fitz.open("pdf", image.convert_to_pdf()) as document,
            ):
                page_count = len(document)
                document.save(temporary)
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    with db.transaction():
        if old:
            db.conn.execute(
                "UPDATE source_documents SET stored_path=? WHERE id=?",
                (str(target), old["id"]),
            )
            return old["id"]
        cur = db.conn.execute(
            "INSERT INTO source_documents(sha256,original_name,stored_path,page_count) VALUES(?,?,?,?)",
            (checksum, source.name, str(target), page_count),
        )
        return cur.lastrowid


@dataclass(frozen=True)
class PipelineResult:
    source_id: int
    job_id: int
    requested_pages: int
    completed_pages: int
    reused_pages: int
    failed_pages: int
    state: str


def import_document(
    db: WGDB,
    path,
    *,
    start_page=1,
    end_page=None,
    engine="easyocr",
    backend=None,
    dpi=180,
    progress=None,
    cancel: Event | None = None,
):
    source_id = register_source(db, path)
    source = db.conn.execute(
        "SELECT * FROM source_documents WHERE id=?", (source_id,)
    ).fetchone()
    end_page = source["page_count"] if end_page is None else end_page
    if (
        not isinstance(start_page, int)
        or not isinstance(end_page, int)
        or not 1 <= start_page <= end_page <= source["page_count"]
    ):
        raise ValueError(f"페이지 범위는 1~{source['page_count']}입니다.")
    if not 72 <= dpi <= 300:
        raise ValueError("OCR DPI는 72~300입니다.")
    requested = end_page - start_page + 1
    if requested > 20:
        gate = db.conn.execute(
            """SELECT 1 FROM acceptance_runs WHERE source_sha256=? AND pipeline_revision=?
            AND pages>=20 AND passed=1""",
            (source["sha256"], PIPELINE_REVISION),
        ).fetchone()
        if not gate:
            raise ValueError(
                "이 원본의 20페이지 E2E 통과 기록이 먼저 필요합니다. 아직 전체 분석을 시작하지 않습니다."
            )
    with db.transaction():
        db.conn.execute(
            """INSERT INTO import_jobs(source_id,start_page,end_page,engine) VALUES(?,?,?,?)
            ON CONFLICT(source_id,start_page,end_page,engine) DO NOTHING""",
            (source_id, start_page, end_page, engine),
        )
        job_id = db.conn.execute(
            "SELECT id FROM import_jobs WHERE source_id=? AND start_page=? AND end_page=? AND engine=?",
            (source_id, start_page, end_page, engine),
        ).fetchone()[0]
        db.conn.execute(
            "UPDATE import_jobs SET state='running',error='',updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (job_id,),
        )
    root = db.path.parent / "work" / source["sha256"]
    for folder in ("pages", "title_crops", "prepared", "key_crops"):
        (root / folder).mkdir(parents=True, exist_ok=True)
    done = reused = failed = 0
    state = "complete"
    try:
        with fitz.open(source["stored_path"]) as document:
            for number in range(start_page, end_page + 1):
                if cancel and cancel.is_set():
                    state = "cancelled"
                    break
                old = db.conn.execute(
                    "SELECT * FROM imported_pages WHERE source_id=? AND page=?",
                    (source_id, number),
                ).fetchone()
                reusable = old and (
                    old["state"] == "reviewed"
                    or (
                        old["state"] == "ocr_done"
                        and old["ocr_engine"] == engine
                        and old["ocr_revision"] == PIPELINE_REVISION
                    )
                )
                if reusable and Path(old["image_path"]).is_file():
                    done += 1
                    reused += 1
                else:
                    if backend is None:
                        # Initialize once; missing packages/models are a job
                        # failure, rather than twenty separate page failures.
                        backend = create_ocr_backend(engine)
                    page_path = root / "pages" / f"page_{number:04d}.png"
                    title_path = root / "title_crops" / f"title_{number:04d}.png"
                    with db.transaction():
                        db.conn.execute(
                            """INSERT INTO imported_pages(source_id,page,image_path,title_crop) VALUES(?,?,?,?)
                            ON CONFLICT(source_id,page) DO UPDATE SET image_path=excluded.image_path,title_crop=excluded.title_crop""",
                            (source_id, number, str(page_path), str(title_path)),
                        )
                    try:
                        page = document[number - 1]
                        pix = page.get_pixmap(
                            matrix=fitz.Matrix(dpi / 72, dpi / 72), alpha=False
                        )
                        temp_image = page_path.with_suffix(".tmp.png")
                        pix.save(temp_image)
                        os.replace(temp_image, page_path)
                        key_path = root / "key_crops" / page_path.name
                        with Image.open(page_path) as image:
                            image.crop(
                                (0, 0, image.width, max(1, int(image.height * 0.18)))
                            ).save(title_path)
                            image.crop(
                                (0, 0, image.width, max(1, int(image.height * 0.32)))
                            ).save(key_path)
                        prepared = preprocess_title_crop(
                            title_path, root / "prepared" / title_path.name
                        )
                        lines = backend.read(prepared)
                        with Image.open(prepared) as image:
                            raw_title, confidence, candidates = choose_title(
                                lines, image.width, image.height
                            )
                        key_lines = backend.read(key_path)
                        key = detect_key_candidate([line.text for line in key_lines])
                        with db.transaction():
                            page_id = db.conn.execute(
                                "SELECT id FROM imported_pages WHERE source_id=? AND page=?",
                                (source_id, number),
                            ).fetchone()[0]
                            db.conn.execute(
                                """INSERT INTO ocr_observations(imported_page_id,engine,revision,raw_title,confidence,raw_lines_json,key_evidence)
                                VALUES(?,?,?,?,?,?,?)""",
                                (
                                    page_id,
                                    engine,
                                    PIPELINE_REVISION,
                                    raw_title,
                                    confidence,
                                    json.dumps(
                                        [asdict(line) for line in lines],
                                        ensure_ascii=False,
                                    ),
                                    json.dumps(key.evidence(), ensure_ascii=False),
                                ),
                            )
                            # A reviewed page can lose a cached image; rebuilding
                            # it must not replace its raw evidence or decision.
                            if not old or old["state"] != "reviewed":
                                db.conn.execute(
                                    """UPDATE imported_pages SET raw_title=?,confidence=?,candidates_json=?,raw_lines_json=?,
                                    key_candidate=?,key_confidence=?,key_evidence=?,state='ocr_done',error='',ocr_engine=?,ocr_revision=?
                                    WHERE source_id=? AND page=?""",
                                    (
                                        raw_title,
                                        confidence,
                                        json.dumps(candidates, ensure_ascii=False),
                                        json.dumps(
                                            [asdict(line) for line in lines],
                                            ensure_ascii=False,
                                        ),
                                        key.key or "",
                                        key.confidence,
                                        json.dumps(key.evidence(), ensure_ascii=False),
                                        engine,
                                        PIPELINE_REVISION,
                                        source_id,
                                        number,
                                    ),
                                )
                        done += 1
                    except Exception as exc:
                        failed += 1
                        with db.transaction():
                            if not old or old["state"] != "reviewed":
                                db.conn.execute(
                                    "UPDATE imported_pages SET state='failed',error=? WHERE source_id=? AND page=?",
                                    (str(exc), source_id, number),
                                )
                with db.transaction():
                    db.conn.execute(
                        "UPDATE import_jobs SET completed_pages=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                        (done, job_id),
                    )
                if progress:
                    progress(
                        {
                            "page": number,
                            "completed": done,
                            "total": requested,
                            "failed": failed,
                            "reused": reused,
                        }
                    )
        if failed:
            state = "failed"
    except Exception as exc:
        state = "failed"
        with db.transaction():
            db.conn.execute(
                "UPDATE import_jobs SET error=? WHERE id=?", (str(exc), job_id)
            )
        raise
    finally:
        with db.transaction():
            db.conn.execute(
                "UPDATE import_jobs SET state=?,completed_pages=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (state, done, job_id),
            )
    return PipelineResult(source_id, job_id, requested, done, reused, failed, state)


def import_legacy_csv(db, path, *, source_pdf=None):
    path = Path(path).resolve()
    manifest = path.parent.parent / "import_manifest.json"
    if source_pdf is None and manifest.exists():
        source_pdf = json.loads(manifest.read_text(encoding="utf-8"))["source_pdf"]
    if not source_pdf:
        raise ValueError(
            "이전 OCR CSV에는 원본 PDF 정보가 없습니다. 원본 PDF를 함께 선택하세요."
        )
    source_id = register_source(db, source_pdf)
    count = 0
    with open(path, encoding="utf-8-sig", newline="") as file, db.transaction():
        for row in csv.DictReader(file):
            page = int(row.get("page") or row.get("page_number") or 0)
            total = db.conn.execute(
                "SELECT page_count FROM source_documents WHERE id=?", (source_id,)
            ).fetchone()[0]
            if not 1 <= page <= total:
                raise ValueError("OCR CSV의 페이지 범위가 원본과 맞지 않습니다.")
            image = path.parent.parent / "pdf_work/pages" / f"page_{page:04d}.png"
            raw = row.get("raw_title") or row.get("title") or ""
            cur = db.conn.execute(
                """INSERT INTO imported_pages(source_id,page,image_path,title_crop,raw_title,confidence,candidates_json,state)
                VALUES(?,?,?,?,?,?,?,'ocr_done') ON CONFLICT(source_id,page) DO NOTHING""",
                (
                    source_id,
                    page,
                    str(image),
                    row.get("image") or "",
                    raw,
                    float(row.get("confidence") or 0),
                    json.dumps([row.get("title") or ""], ensure_ascii=False),
                ),
            )
            count += cur.rowcount
    return count
