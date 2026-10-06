import json
import threading
from pathlib import Path
import fitz
import pytest
from PIL import Image
from worship_guide.db import WGDB
from worship_guide.pipeline import import_document, PIPELINE_REVISION, file_sha256
from worship_guide.ocr_titles import OCRLine
from worship_guide.pdf_export import export_collection_pdf


class FixtureOCR:
    """Deliberately deterministic OCR adapter; real scan test is separate."""

    def read(self, path):
        number = int(path.stem.split("_")[-1])
        if path.stem.startswith("page_"):
            if number == 4:
                return [OCRLine("words & music", 0.9)]
            return [OCRLine("Key: " + (["E", "F", "G"][(number - 1) % 3]), 0.9)]
        with Image.open(path) as im:
            width = im.width
        title = "예수 닭기틀" if number <= 3 else f"테스트 곡 {number}"
        return [
            OCRLine(
                title,
                0.8,
                [
                    [width * 0.2, 0],
                    [width * 0.8, 0],
                    [width * 0.8, 30],
                    [width * 0.2, 30],
                ],
            )
        ]


def make_pdf(path, count=20):
    with fitz.open() as doc:
        for i in range(1, count + 1):
            page = doc.new_page(width=300, height=200)
            page.insert_text((30, 70), f"PAGE {i:02d}", fontsize=18)
        doc.save(path)
    return path


def reviewed(db, source, count=20):
    result = import_document(
        db, source, end_page=count, backend=FixtureOCR(), engine="fixture", dpi=72
    )
    assert result.completed_pages == count and result.failed_pages == 0
    for row in db.review_queue(result.source_id):
        n = row["page"]
        db.approve_page(
            row["id"],
            "예수 닮기를" if n <= 3 else f"테스트 곡 {n}",
            row["key_candidate"],
        )
    return result


def test_twenty_page_end_to_end_persistence_corrections_variants_collection_pdf(
    tmp_path,
):
    source = make_pdf(tmp_path / "twenty.pdf")
    path = tmp_path / "data/wgdb.sqlite3"
    with WGDB(path) as db:
        result = reviewed(db, source)
        song = db.list_songs("예수")[0]
        assert len(db.list_songs()) == 18
        assert len(db.list_scores(song["id"])) == 3
        assert [r["key_signature"] for r in db.list_scores(song["id"])] == [
            "E",
            "F",
            "G",
        ]
        assert db.suggest_titles("예수 닭기틀")[0]["title"] == "예수 닮기를"
        assert db.suggest_titles("예수 닭기틀")[0]["remembered"]
        assert db.conn.execute("SELECT COUNT(*) FROM review_events").fetchone()[0] == 40
        unknown = db.conn.execute(
            "SELECT reviewed_score_id FROM imported_pages WHERE page=4"
        ).fetchone()[0]
        assert db.get_score(unknown)["key_signature"] == ""
        scores = db.list_scores(song["id"])
        cid = db.create_collection("조성별", filters={"key_signature": "G,E"})
        db.add_score_to_collection(cid, scores[2]["id"])
        db.add_score_to_collection(cid, scores[0]["id"])
        item = db.get_collection_items(cid)[1]
        db.update_collection_item(item["id"], section="헌신", notes="기도로 연결")
    # Move the original PDF away: managed source copy must still export.
    source.rename(tmp_path / "moved.pdf")
    with WGDB(path) as db:
        assert not db.review_queue()
        assert [r["key_signature"] for r in db.get_collection_items(cid)] == ["G", "E"]
        simple = tmp_path / "simple.pdf"
        guide = tmp_path / "guide.pdf"
        assert export_collection_pdf(db.get_collection_items(cid), simple)[0] == 2
        export_collection_pdf(
            db.get_collection_items(cid), guide, mode="guide", title="헌신 악보집"
        )
        with fitz.open(simple) as pdf:
            assert "PAGE 03" in pdf[0].get_text() and "PAGE 01" in pdf[1].get_text()
        with fitz.open(guide) as pdf:
            assert "헌신 악보집" in pdf[0].get_text()
            assert "목차" in pdf[1].get_text()
            for (_, label, start), expected in zip(
                pdf.get_toc(), ["PAGE 03", "PAGE 01"]
            ):
                assert expected in pdf[start - 1].get_text()
        original = [
            dict(r) for r in db.conn.execute("SELECT * FROM score_variants ORDER BY id")
        ]
        resumed = import_document(
            db,
            tmp_path / "moved.pdf",
            end_page=20,
            backend=FixtureOCR(),
            engine="fixture",
            dpi=72,
        )
        assert resumed.reused_pages == 20
        assert [
            dict(r) for r in db.conn.execute("SELECT * FROM score_variants ORDER BY id")
        ] == original
        assert len(db.review_queue(include_reviewed=True)) == 20
        sid = db.setlist_from_collection(cid, "주일", "2026-10-11", "시편 103편")
        assert [r["score_id"] for r in db.get_setlist_items(sid)] == [
            r["score_id"] for r in db.get_collection_items(cid)
        ]


def test_cancel_retry_and_two_source_identity(tmp_path):
    source = make_pdf(tmp_path / "one.pdf", 5)
    other = make_pdf(tmp_path / "two.pdf", 6)
    cancel = threading.Event()
    with WGDB(tmp_path / "data/db") as db:
        first = import_document(
            db,
            source,
            end_page=5,
            backend=FixtureOCR(),
            engine="fixture",
            dpi=72,
            cancel=cancel,
            progress=lambda p: cancel.set() if p["page"] == 2 else None,
        )
        assert first.state == "cancelled" and first.completed_pages == 2
        again = import_document(
            db, source, end_page=5, backend=FixtureOCR(), engine="fixture", dpi=72
        )
        assert again.reused_pages == 2 and again.completed_pages == 5
        second = import_document(
            db, other, end_page=5, backend=FixtureOCR(), engine="fixture", dpi=72
        )
        assert second.source_id != first.source_id
        assert len(db.review_queue()) == 10


def test_large_gate_requires_twenty_pages_of_same_source(tmp_path):
    source = make_pdf(tmp_path / "full.pdf", 21)
    with WGDB(tmp_path / "data/db") as db:
        with pytest.raises(ValueError, match="20페이지"):
            import_document(
                db, source, end_page=21, backend=FixtureOCR(), engine="fixture", dpi=72
            )
        # Wrong source or pipeline version does not unlock a large import.
        with db.conn:
            db.conn.execute(
                "INSERT INTO acceptance_runs(source_sha256,pipeline_revision,pages,passed,evidence_json) VALUES(?,?,?,?,?)",
                ("wrong", PIPELINE_REVISION, 20, 1, "{}"),
            )
        with pytest.raises(ValueError, match="20페이지"):
            import_document(
                db, source, end_page=21, backend=FixtureOCR(), engine="fixture", dpi=72
            )
        with db.conn:
            db.conn.execute(
                "INSERT INTO acceptance_runs(source_sha256,pipeline_revision,pages,passed,evidence_json) VALUES(?,?,?,?,?)",
                (file_sha256(source), PIPELINE_REVISION, 20, 1, "{}"),
            )
        assert (
            import_document(
                db, source, end_page=21, backend=FixtureOCR(), engine="fixture", dpi=72
            ).completed_pages
            == 21
        )


def test_review_is_atomic_and_manual_key_wins(tmp_path, monkeypatch):
    source = make_pdf(tmp_path / "one.pdf", 1)
    with WGDB(tmp_path / "data/db") as db:
        import_document(
            db, source, end_page=1, backend=FixtureOCR(), engine="fixture", dpi=72
        )
        row = db.review_queue()[0]
        monkeypatch.setattr(
            db,
            "review_event",
            lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("disk simulation")),
        )
        with pytest.raises(RuntimeError):
            db.approve_page(row["id"], "예수 닮기를", "Bb")
        assert len(db.list_songs()) == 0 and db.review_queue()[0]["state"] == "ocr_done"
        monkeypatch.undo()
        score = db.approve_page(row["id"], "예수 닮기를", "Bb")
        assert db.get_score(score)["key_signature"] == "Bb"
        assert db.get_score(score)["key_candidate"] == "E"
        import_document(
            db, source, end_page=1, backend=FixtureOCR(), engine="fixture", dpi=72
        )
        assert db.get_score(score)["key_signature"] == "Bb"
        db.approve_page(row["id"], "예수 닮기를", "C")
        assert db.conn.execute("SELECT COUNT(*) FROM score_variants").fetchone()[0] == 1
        assert db.get_score(score)["ocr_title_raw"] == "예수 닭기틀"


def test_pdf_failure_does_not_replace_previous_output_and_filters_are_and_or(tmp_path):
    source = make_pdf(tmp_path / "one.pdf", 3)
    out = tmp_path / "previous.pdf"
    out.write_bytes(b"previous-output")
    with WGDB(tmp_path / "data/db") as db:
        result = reviewed(db, source, count=3)
        song = db.list_songs()[0]
        db.save_song(
            {
                "themes": "감사,헌신",
                "mood": "묵상",
                "bible": "시편 103편",
                "tags": "가족",
                "composer": "심형진",
            },
            song["id"],
        )
        matches = db.collection_candidates(
            themes="감사,부활",
            mood="묵상",
            key_signature="E,G",
            bible="시편",
            tags="가족",
            composer="심형진",
        )
        assert {r["key_signature"] for r in matches} == {"E", "G"}
        assert not db.collection_candidates(themes="부활", mood="묵상")
        with pytest.raises(ValueError):
            export_collection_pdf(
                [{"title": "없음", "key_signature": "G", "source_pdf": "missing.pdf"}],
                out,
            )
        assert out.read_bytes() == b"previous-output"
        cid = db.create_collection(
            "새 추천", filters={"themes": "감사", "key_signature": "G"}
        )
        assert len(db.collection_suggestions(cid)) == 1
        db.add_score_to_collection(cid, matches[-1]["score_id"])
        assert db.collection_suggestions(cid) == []
        with pytest.raises(ValueError):
            db.delete_song(song["id"])
        assert len(db.list_scores(song["id"])) == 3
