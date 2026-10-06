"""Legacy API adapters into the canonical db.WGDB; no schema of its own."""

from pathlib import Path
from .db import WGDB


def connect(db_path=None):
    return WGDB(db_path).conn


def _db(conn):
    db = WGDB.__new__(WGDB)
    db.conn = conn
    db._transaction_depth = 0
    return db


def next_wgid(conn):
    return _db(conn).next_wgid()


def find_song_by_title(conn, title):
    from .normalize import canonical_title

    return conn.execute(
        "SELECT * FROM songs WHERE normalized_title=? ORDER BY id LIMIT 1",
        (canonical_title(title),),
    ).fetchone()


def get_or_create_song(conn, title):
    return _db(conn).get_or_create_song(title)


def get_or_create_arrangement(conn, song_id, name="Original"):
    return _db(conn).ensure_arrangement(song_id, name)


def add_score_variant(
    conn,
    *,
    arrangement_id,
    key_signature,
    source_document,
    page,
    image_path,
    raw_ocr_title,
    confidence,
):
    owner = conn.execute(
        "SELECT song_id,name FROM arrangements WHERE id=?", (arrangement_id,)
    ).fetchone()
    if not owner:
        raise ValueError("편곡을 찾을 수 없습니다.")
    if not source_document:
        raise ValueError("원본 PDF 식별자가 필요합니다. 검수센터에서 저장하세요.")
    old = conn.execute(
        "SELECT id FROM score_variants WHERE source_pdf=? AND page_start=?",
        (str(source_document), page),
    ).fetchone()
    return _db(conn).save_score(
        owner["song_id"],
        {
            "arrangement": owner["name"],
            "key_signature": key_signature,
            "source_pdf": str(source_document),
            "page_start": page,
            "image_path": str(image_path),
            "ocr_title_raw": raw_ocr_title,
            "ocr_confidence": confidence,
            "review_status": "reviewed",
        },
        old["id"] if old else None,
    )


def add_review_event(
    conn, entity_type, entity_id, field_name, previous_value, new_value, confidence=None
):
    conn.execute(
        "INSERT INTO review_events(entity_type,entity_id,field_name,previous_value,new_value,confidence) VALUES(?,?,?,?,?,?)",
        (entity_type, entity_id, field_name, previous_value, new_value, confidence),
    )
