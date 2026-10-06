
from __future__ import annotations
from pathlib import Path
import sqlite3
from datetime import datetime

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS songs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    wgid TEXT UNIQUE,
    title TEXT NOT NULL,
    original_title TEXT,
    lyrics TEXT,
    composer TEXT,
    lyricist TEXT,
    bpm INTEGER,
    meter TEXT,
    memo TEXT,
    favorite INTEGER NOT NULL DEFAULT 0,
    review_status TEXT NOT NULL DEFAULT 'unreviewed',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS arrangements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    song_id INTEGER NOT NULL,
    name TEXT NOT NULL DEFAULT 'Original',
    arranger TEXT,
    memo TEXT,
    UNIQUE(song_id, name),
    FOREIGN KEY(song_id) REFERENCES songs(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS score_variants (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    arrangement_id INTEGER NOT NULL,
    key_signature TEXT,
    source_document TEXT,
    start_page INTEGER,
    end_page INTEGER,
    file_path TEXT,
    image_path TEXT,
    raw_ocr_title TEXT,
    raw_ocr_key TEXT,
    ocr_confidence REAL,
    review_status TEXT NOT NULL DEFAULT 'unreviewed',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(arrangement_id) REFERENCES arrangements(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL,
    name TEXT NOT NULL,
    UNIQUE(category, name)
);

CREATE TABLE IF NOT EXISTS song_tags (
    song_id INTEGER NOT NULL,
    tag_id INTEGER NOT NULL,
    PRIMARY KEY(song_id, tag_id),
    FOREIGN KEY(song_id) REFERENCES songs(id) ON DELETE CASCADE,
    FOREIGN KEY(tag_id) REFERENCES tags(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS scripture_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    song_id INTEGER NOT NULL,
    reference_text TEXT NOT NULL,
    memo TEXT,
    FOREIGN KEY(song_id) REFERENCES songs(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS review_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type TEXT NOT NULL,
    entity_id INTEGER NOT NULL,
    field_name TEXT,
    previous_value TEXT,
    new_value TEXT,
    source TEXT NOT NULL DEFAULT 'user',
    confidence REAL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""

def connect(db_path: str | Path):
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn

def next_wgid(conn):
    row = conn.execute("SELECT MAX(id) AS m FROM songs").fetchone()
    n = (row["m"] or 0) + 1
    return f"WG{n:06d}"

def find_song_by_title(conn, title: str):
    return conn.execute(
        "SELECT * FROM songs WHERE lower(trim(title)) = lower(trim(?))",
        (title,),
    ).fetchone()

def get_or_create_song(conn, title: str):
    row = find_song_by_title(conn, title)
    if row:
        return row["id"], row["wgid"]
    wgid = next_wgid(conn)
    cur = conn.execute(
        "INSERT INTO songs (wgid, title, review_status) VALUES (?, ?, 'reviewed')",
        (wgid, title.strip()),
    )
    return cur.lastrowid, wgid

def get_or_create_arrangement(conn, song_id: int, name: str = "Original"):
    row = conn.execute(
        "SELECT id FROM arrangements WHERE song_id=? AND name=?",
        (song_id, name),
    ).fetchone()
    if row:
        return row["id"]
    cur = conn.execute(
        "INSERT INTO arrangements(song_id, name) VALUES (?, ?)",
        (song_id, name),
    )
    return cur.lastrowid

def add_score_variant(
    conn,
    *,
    arrangement_id: int,
    key_signature: str | None,
    source_document: str,
    page: int,
    image_path: str,
    raw_ocr_title: str,
    confidence: float | None,
):
    # Avoid duplicate page insert for the same source.
    row = conn.execute(
        """SELECT id FROM score_variants
           WHERE source_document=? AND start_page=?""",
        (source_document, page),
    ).fetchone()
    if row:
        conn.execute(
            """UPDATE score_variants
               SET arrangement_id=?, key_signature=?, image_path=?,
                   raw_ocr_title=?, ocr_confidence=?, review_status='reviewed'
               WHERE id=?""",
            (arrangement_id, key_signature, image_path, raw_ocr_title, confidence, row["id"])
        )
        return row["id"]
    cur = conn.execute(
        """INSERT INTO score_variants
           (arrangement_id,key_signature,source_document,start_page,end_page,
            image_path,raw_ocr_title,ocr_confidence,review_status)
           VALUES (?,?,?,?,?,?,?,?, 'reviewed')""",
        (arrangement_id,key_signature,source_document,page,page,image_path,
         raw_ocr_title,confidence)
    )
    return cur.lastrowid

def add_review_event(conn, entity_type, entity_id, field_name, previous_value, new_value, confidence=None):
    conn.execute(
        """INSERT INTO review_events
           (entity_type,entity_id,field_name,previous_value,new_value,confidence)
           VALUES (?,?,?,?,?,?)""",
        (entity_type,entity_id,field_name,previous_value,new_value,confidence)
    )
