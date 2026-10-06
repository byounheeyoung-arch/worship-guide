import json
from worship_guide.db import WGDB
from worship_guide.master_import import import_master_snapshot


def test_reference_seed_is_idempotent_preserves_all_tabs_and_never_fabricates_keys(
    tmp_path,
):
    path = tmp_path / "master.json"
    payload = {
        "spreadsheet_id": "test-reference",
        "sheets": {
            "Songs": [
                [
                    "WGID",
                    "곡명",
                    "원제/부제",
                    "사용 가능 Key",
                    "핵심 주제",
                    "난이도(1-5)",
                    "검수 상태",
                ],
                [
                    "WG000021",
                    "예수 닮기를",
                    "예수닮기를",
                    "E,F,G",
                    "헌신",
                    "3",
                    "미검수",
                ],
            ],
            "Flow": [
                ["WGID", "곡명", "오프닝", "헌신"],
                ["WG000021", "예수 닮기를", 10, 100],
            ],
            "Bible": [
                ["WGID", "곡명", "연결 수준", "성경 본문"],
                ["WG000021", "예수 닮기를", "후보", "갈라디아서 2:20"],
            ],
            "Community": [["종류", "메모"], ["사용자", "나의 기록"]],
        },
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    with WGDB(tmp_path / "db") as db:
        assert import_master_snapshot(db, path)["created"] == 1
        song = db.list_songs()[0]
        sid = song["id"]
        assert song["bible"] == "갈라디아서 2:20" and song["flow"] == "헌신"
        assert song["review_status"] == "미검수" and len(db.list_scores(sid)) == 0
        assert json.loads(song["source_metadata"])["사용 가능 Key"] == "E,F,G"
        db.save_song({"themes": "사람이 수정", "notes": "내 메모"}, sid)
        assert import_master_snapshot(db, path)["reused"]
        payload["sheets"]["Songs"][1][4] = "다른 초안"
        path.write_text(json.dumps(payload), encoding="utf-8")
        assert import_master_snapshot(db, path)["existing"] == 1
        assert (
            db.get_song(sid)["themes"] == "사람이 수정"
            and db.get_song(sid)["notes"] == "내 메모"
        )
        assert (
            db.conn.execute(
                "SELECT count(*) FROM reference_rows WHERE sheet='Community'"
            ).fetchone()[0]
            == 1
        )
