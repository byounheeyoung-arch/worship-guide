from pathlib import Path
import sqlite3
import pytest
from worship_guide.db import WGDB
from worship_guide.migrations import SCHEMA_VERSION

FIXTURES = Path(__file__).parent / "fixtures"


def legacy(path, kind):
    c = sqlite3.connect(path)
    c.executescript((FIXTURES / ("legacy_" + kind + ".sql")).read_text())
    return c


def test_editor_upgrade_preserves_score_ids_collections_and_metadata(tmp_path):
    path = tmp_path / "old.sqlite3"
    c = legacy(path, "editor")
    c.execute(
        "INSERT INTO songs(id,wgid,title,themes,notes) VALUES(7,'WG000088','예수 닮기를','헌신','내 메모')"
    )
    c.execute("INSERT INTO arrangements(id,song_id,name) VALUES(2,7,'Original')")
    c.execute(
        "INSERT INTO scores(id,arrangement_id,key_signature,page_start,page_end,ocr_title_raw) VALUES(5,2,'E',1,1,'예수 닭기틀')"
    )
    c.execute("INSERT INTO collections(id,name) VALUES(3,'헌신곡')")
    c.execute(
        "INSERT INTO collection_items(id,collection_id,song_id,score_id,position) VALUES(9,3,7,5,1)"
    )
    c.execute("INSERT INTO setlists(id,name) VALUES(8,'주일예배')")
    c.execute(
        "INSERT INTO setlist_items(id,setlist_id,song_id,score_id,position,selected_key) VALUES(11,8,7,5,1,'E')"
    )
    c.commit()
    c.close()
    with WGDB(path) as db:
        assert db.migration_backup.is_file()
        assert db.get_song(7)["wgid"] == "WG000088"
        assert db.get_song(7)["notes"] == "내 메모"
        assert db.get_score(5)["ocr_title_raw"] == "예수 닭기틀"
        assert db.get_collection_items(3)[0]["id"] == 9
        assert db.get_collection_items(3)[0]["score_id"] == 5
        assert db.get_setlist_items(8)[0]["score_id"] == 5
        assert not db.conn.execute("PRAGMA foreign_key_check").fetchall()
        assert db.conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        backup = db.migration_backup
    with sqlite3.connect(backup) as c:
        assert (
            c.execute("SELECT key_signature FROM scores WHERE id=5").fetchone()[0]
            == "E"
        )
        assert c.execute("PRAGMA user_version").fetchone()[0] == 0
    with WGDB(path) as db:
        assert db.migration_backup is None
        assert len(db.list_scores(7)) == 1


def test_review_upgrade_preserves_raw_corrections_tags_and_review_events(tmp_path):
    path = tmp_path / "v2.sqlite3"
    c = legacy(path, "review")
    c.execute(
        "INSERT INTO songs(id,wgid,title,memo,composer) VALUES(1,'WG000120','예수 닮기를','기존 메모','심형진')"
    )
    c.execute("INSERT INTO arrangements(id,song_id,name) VALUES(1,1,'Original')")
    c.execute(
        "INSERT INTO score_variants(id,arrangement_id,key_signature,start_page,end_page,source_document,raw_ocr_title,review_status) VALUES(1,1,'Eb',2,2,'scores.pdf','예수 닭기틀','reviewed')"
    )
    c.execute(
        "INSERT INTO review_events(entity_type,entity_id,field_name,previous_value,new_value) VALUES('score_variant',1,'title','예수 닭기틀','예수 닮기를')"
    )
    c.execute("INSERT INTO tags(id,category,name) VALUES(1,'theme','헌신')")
    c.execute("INSERT INTO song_tags VALUES(1,1)")
    c.execute(
        "INSERT INTO scripture_links(song_id,reference_text) VALUES(1,'갈라디아서 2:20')"
    )
    c.commit()
    c.close()
    with WGDB(path) as db:
        assert db.get_score(1)["page_start"] == 2
        assert db.get_score(1)["source_pdf"] == "scores.pdf"
        assert db.get_score(1)["ocr_title_raw"] == "예수 닭기틀"
        assert db.get_song(1)["composer"] == "심형진"
        assert db.get_song(1)["notes"] == "기존 메모"
        assert (
            db.collection_candidates(themes="헌신", bible="갈라디아서")[0]["score_id"]
            == 1
        )
        assert db.suggest_titles("예수 닭기틀")[0]["remembered"]
        assert db.conn.execute("SELECT COUNT(*) FROM review_events").fetchone()[0] == 1


def test_mixed_schemas_preserve_overlapping_ids_without_collapsing_variants(tmp_path):
    path = tmp_path / "mixed.sqlite3"
    c = legacy(path, "editor")
    c.executescript((FIXTURES / "legacy_review.sql").read_text())
    c.execute("INSERT INTO songs(id,wgid,title) VALUES(1,'WG000001','예수 닮기를')")
    c.execute("INSERT INTO arrangements(id,song_id,name) VALUES(1,1,'Original')")
    c.execute(
        "INSERT INTO scores(id,arrangement_id,key_signature,page_start) VALUES(1,1,'E',1)"
    )
    c.execute(
        "INSERT INTO score_variants(id,arrangement_id,key_signature,start_page) VALUES(1,1,'C',3)"
    )
    c.execute("INSERT INTO collections(id,name) VALUES(1,'원래 악보집')")
    c.execute(
        "INSERT INTO collection_items(collection_id,song_id,score_id,position) VALUES(1,1,1,1)"
    )
    c.commit()
    c.close()
    with WGDB(path) as db:
        assert len(db.list_scores(1)) == 2
        assert {r["key_signature"] for r in db.list_scores(1)} == {"E", "C"}
        assert db.get_collection_items(1)[0]["key_signature"] == "E"
        assert db.get_collection_items(1)[0]["score_id"] != 1
        assert (
            db.conn.execute(
                "SELECT type FROM sqlite_master WHERE name='scores'"
            ).fetchone()[0]
            == "view"
        )


def test_failed_migration_rolls_back_and_keeps_recoverable_backup(tmp_path):
    path = tmp_path / "broken.sqlite3"
    c = legacy(path, "editor")
    c.execute("PRAGMA foreign_keys=OFF")
    c.execute("INSERT INTO collections(id,name) VALUES(1,'원본')")
    c.execute(
        "INSERT INTO collection_items(collection_id,song_id,score_id,position) VALUES(1,99,999,1)"
    )
    c.commit()
    c.close()
    with pytest.raises(ValueError, match="Migration blocked"):
        WGDB(path)
    with sqlite3.connect(path) as c:
        assert c.execute("PRAGMA user_version").fetchone()[0] == 0
        assert c.execute("SELECT score_id FROM collection_items").fetchone()[0] == 999
        assert (
            c.execute("SELECT type FROM sqlite_master WHERE name='scores'").fetchone()[
                0
            ]
            == "table"
        )
    assert list(tmp_path.glob("*.bak"))


def test_future_schema_is_read_only_and_partial_edits_preserve_metadata(tmp_path):
    path = tmp_path / "future.sqlite3"
    with sqlite3.connect(path) as c:
        c.execute("PRAGMA user_version=999")
    with pytest.raises(RuntimeError):
        WGDB(path)
    with sqlite3.connect(path) as c:
        assert c.execute("PRAGMA user_version").fetchone()[0] == 999
    with WGDB(tmp_path / "current.sqlite3") as db:
        song = db.save_song(
            {"title": "곡", "composer": "작곡가", "themes": "감사", "wgid": "WG000020"}
        )
        db.save_song({"bpm": 100}, song)
        assert db.get_song(song)["title"] == "곡"
        assert db.get_song(song)["composer"] == "작곡가"
        assert db.get_song(song)["themes"] == "감사"
        assert db.get_song(song)["wgid"] == "WG000020"
        with pytest.raises(sqlite3.IntegrityError):
            db.save_song({"title": "중복", "wgid": "WG000020"})
        assert db.save_song({"title": "다음"}) > song
