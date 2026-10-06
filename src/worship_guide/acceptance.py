"""Check real reviewed pages in an isolated DB copy before unlocking bulk OCR."""

from __future__ import annotations
import hashlib
import json
import sqlite3
from collections import defaultdict
from pathlib import Path
from uuid import uuid4
import fitz

from .db import WGDB
from .normalize import canonical_title
from .pipeline import import_document, PIPELINE_REVISION
from .pdf_export import export_collection_pdf


def _check(condition, message):
    if not condition:
        raise ValueError("20페이지 E2E: " + message)


def _signature(page):
    pix = page.get_pixmap(matrix=fitz.Matrix(0.5, 0.5), alpha=False)
    return (pix.width, pix.height, hashlib.sha256(pix.samples).hexdigest())


def verify_twenty(db: WGDB, source_id: int):
    source = db.conn.execute(
        "SELECT * FROM source_documents WHERE id=?", (source_id,)
    ).fetchone()
    _check(source is not None, "원본을 찾을 수 없습니다.")
    pages = list(
        db.conn.execute(
            "SELECT * FROM imported_pages WHERE source_id=? AND state='reviewed' ORDER BY page LIMIT 20",
            (source_id,),
        )
    )
    _check(len(pages) == 20, "사람이 승인한 20페이지가 먼저 필요합니다.")
    _check(pages[-1]["page"] - pages[0]["page"] == 19, "연속된 20페이지를 검수하세요.")
    scores = [db.get_score(p["reviewed_score_id"]) for p in pages]
    _check(all(scores), "검수 악보 연결이 끊겼습니다.")
    _check(
        len({s["id"] for s in scores}) == 20, "페이지마다 독립 악보 버전이 필요합니다."
    )
    grouped = defaultdict(set)
    for score in scores:
        if score["key_signature"]:
            grouped[score["song_id"]].add(score["key_signature"])
    _check(
        any(len(keys) >= 2 for keys in grouped.values()),
        "같은 곡의 서로 다른 Key를 포함하세요.",
    )
    corrected = [
        s
        for s in scores
        if canonical_title(s["ocr_title_raw"])
        != canonical_title(s["ocr_title_corrected"])
        and s["ocr_title_raw"]
    ]
    _check(bool(corrected), "실제 OCR 제목 오류를 사람이 수정한 페이지를 포함하세요.")
    _check(
        any(not s["key_signature"] for s in scores),
        "Key를 미확인으로 남겨야 하는 페이지를 포함하세요.",
    )
    _check(
        all(s["key_origin"] == "user" for s in scores), "Key는 사람이 확정해야 합니다."
    )
    before = [dict(s) for s in scores]
    root = db.path.parent / "work" / "acceptance" / uuid4().hex
    root.mkdir(parents=True)
    clone_path = root / "acceptance.sqlite3"
    with sqlite3.connect(clone_path) as connection:
        db.conn.backup(connection)
    simple = root / "score-order.pdf"
    guide = root / "guidebook.pdf"
    with WGDB(clone_path) as clone:
        # Only this isolated QA copy receives a test collection and changed
        # candidate evidence. Original reviewed data never changes.
        cid = clone.create_collection(
            "E2E 검증 악보집",
            filters={
                "key_signature": ",".join(
                    sorted({s["key_signature"] for s in scores if s["key_signature"]})
                )
            },
        )
        selected = list(reversed(scores))
        for score in selected:
            clone.add_score_to_collection(cid, score["id"])
        items = clone.get_collection_items(cid)
        _check(
            [i["score_id"] for i in items] == [s["id"] for s in selected],
            "Collection이 선택한 악보 버전을 유지하지 않습니다.",
        )
        clone.update_collection_item(
            items[0]["id"], section="검증 섹션", notes="다음 곡으로 연결"
        )
        with clone.conn:
            clone.conn.execute(
                "UPDATE imported_pages SET key_candidate='B',key_confidence=.1 WHERE id=?",
                (pages[0]["id"],),
            )
        result = import_document(
            clone,
            source["stored_path"],
            start_page=pages[0]["page"],
            end_page=pages[-1]["page"],
            engine=pages[0]["ocr_engine"],
        )
        _check(result.reused_pages == 20, "검수 페이지를 재분석하여 덮어썼습니다.")
        _check(
            [dict(clone.get_score(s["id"])) for s in scores] == before,
            "낮은 신뢰도의 후보가 검수값을 변경했습니다.",
        )
        suggestion = clone.suggest_titles(corrected[0]["ocr_title_raw"])
        _check(
            any(
                r["song_id"] == corrected[0]["song_id"] and r["remembered"]
                for r in suggestion
            ),
            "이전 제목 수정을 다시 추천하지 못합니다.",
        )
    with WGDB(clone_path) as reopened:
        _check(
            [dict(reopened.get_score(s["id"])) for s in scores] == before,
            "재시작 후 악보 데이터가 달라졌습니다.",
        )
        items = reopened.get_collection_items(cid)
        export_collection_pdf(items, simple, db_dir=db.path.parent)
        export_collection_pdf(
            items,
            guide,
            db_dir=db.path.parent,
            mode="guide",
            title="Worship Guide · 검증 악보집",
        )
        with fitz.open(source["stored_path"]) as original, fitz.open(simple) as output:
            _check(len(output) == 20, "단순 PDF 페이지 수가 다릅니다.")
            for index, score in enumerate(selected):
                _check(
                    _signature(output[index])
                    == _signature(original[score["page_start"] - 1]),
                    f"PDF p.{index + 1}의 조성/원본 페이지가 다릅니다.",
                )
        with fitz.open(guide) as output, fitz.open(source["stored_path"]) as original:
            _check("검증 악보집" in output[0].get_text(), "한글 표지 글꼴/추출 오류")
            _check("목차" in output[1].get_text(), "목차 오류")
            toc = output.get_toc()
            _check(len(toc) == 20, "목차 항목 수가 다릅니다.")
            for entry, score in zip(toc, selected):
                _check(
                    _signature(output[entry[2] - 1])
                    == _signature(original[score["page_start"] - 1]),
                    "목차의 페이지 연결/순서 오류",
                )
    evidence = {
        "passed": True,
        "pages": 20,
        "source_sha256": source["sha256"],
        "pipeline_revision": PIPELINE_REVISION,
        "page_range": [pages[0]["page"], pages[-1]["page"]],
        "distinct_score_variants": 20,
        "multiple_keys_same_song": True,
        "correction_memory": True,
        "human_key_preserved": True,
        "restart_persistence": True,
        "collection_variant_identity": True,
        "simple_pdf_render_order_match": True,
        "guide_toc_render_order_match": True,
        "korean_text": True,
        "simple_pdf": str(simple),
        "guide_pdf": str(guide),
        "qa_database": str(clone_path),
    }
    # Insert the bulk gate only after all assertions and reopen checks pass.
    with db.transaction():
        db.conn.execute(
            "INSERT INTO acceptance_runs(source_sha256,pipeline_revision,pages,passed,evidence_json) VALUES(?,?,?,?,?)",
            (
                source["sha256"],
                PIPELINE_REVISION,
                20,
                1,
                json.dumps(evidence, ensure_ascii=False),
            ),
        )
    (root / "evidence.json").write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return evidence
