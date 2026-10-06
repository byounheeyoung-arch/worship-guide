"""Transactional, backed-up upgrades from both recovered desktop schemas.

No application initialization deletes or recreates a user database. Old score
IDs, collection order, metadata, OCR evidence and review events are retained.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

SCHEMA_VERSION = 3

SONG_COLUMNS = {
    "wgid": "TEXT",
    "title": "TEXT NOT NULL DEFAULT ''",
    "original_title": "TEXT DEFAULT ''",
    "bpm": "INTEGER",
    "meter": "TEXT DEFAULT ''",
    "category": "TEXT DEFAULT ''",
    "themes": "TEXT DEFAULT ''",
    "bible": "TEXT DEFAULT ''",
    "flow": "TEXT DEFAULT ''",
    "mood": "TEXT DEFAULT ''",
    "difficulty": "INTEGER",
    "favorite": "INTEGER NOT NULL DEFAULT 0",
    "review_status": "TEXT DEFAULT 'unreviewed'",
    "notes": "TEXT DEFAULT ''",
    "composer": "TEXT DEFAULT ''",
    "lyricist": "TEXT DEFAULT ''",
    "lyrics": "TEXT DEFAULT ''",
    "aliases": "TEXT DEFAULT ''",
    "tags": "TEXT DEFAULT ''",
    "source_metadata": "TEXT DEFAULT '{}'",
    "normalized_title": "TEXT DEFAULT ''",
    "created_at": "TEXT",
    "updated_at": "TEXT",
}
SCORE_COLUMNS = {
    "arrangement_id": "INTEGER REFERENCES arrangements(id)",
    "key_signature": "TEXT DEFAULT ''",
    "page_start": "INTEGER",
    "page_end": "INTEGER",
    "source_pdf": "TEXT DEFAULT ''",
    "file_path": "TEXT DEFAULT ''",
    "image_path": "TEXT DEFAULT ''",
    "ocr_title_raw": "TEXT DEFAULT ''",
    "ocr_title_corrected": "TEXT DEFAULT ''",
    "ocr_confidence": "REAL",
    "raw_ocr_key": "TEXT DEFAULT ''",
    "key_candidate": "TEXT DEFAULT ''",
    "key_confidence": "REAL",
    "key_evidence": "TEXT DEFAULT '{}'",
    "key_origin": "TEXT DEFAULT 'user'",
    "review_status": "TEXT DEFAULT 'unreviewed'",
    "notes": "TEXT DEFAULT ''",
    "created_at": "TEXT",
    "source_id": "INTEGER REFERENCES source_documents(id)",
}


def _columns(c, table):
    return {r[1] for r in c.execute(f'PRAGMA table_info("{table}")')}


def _exists(c, table):
    return (
        c.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone()
        is not None
    )


def _ensure_columns(c, table, columns):
    current = _columns(c, table)
    for name, definition in columns.items():
        if name not in current:
            c.execute(f'ALTER TABLE "{table}" ADD COLUMN "{name}" {definition}')


def _create(c, sql):
    c.execute(sql)


def _core(c):
    _create(c, "CREATE TABLE IF NOT EXISTS songs(id INTEGER PRIMARY KEY AUTOINCREMENT)")
    _ensure_columns(c, "songs", SONG_COLUMNS)
    if "memo" in _columns(c, "songs"):
        c.execute(
            "UPDATE songs SET notes=memo WHERE COALESCE(notes,'')='' AND memo IS NOT NULL"
        )
    _create(
        c,
        """CREATE TABLE IF NOT EXISTS arrangements(
        id INTEGER PRIMARY KEY AUTOINCREMENT, song_id INTEGER NOT NULL REFERENCES songs(id),
        name TEXT NOT NULL DEFAULT 'Original', UNIQUE(song_id,name))""",
    )
    _ensure_columns(
        c, "arrangements", {"source": "TEXT DEFAULT ''", "notes": "TEXT DEFAULT ''"}
    )
    if "memo" in _columns(c, "arrangements"):
        c.execute(
            "UPDATE arrangements SET notes=memo WHERE COALESCE(notes,'')='' AND memo IS NOT NULL"
        )
    _create(
        c,
        """CREATE TABLE IF NOT EXISTS source_documents(
        id INTEGER PRIMARY KEY AUTOINCREMENT, sha256 TEXT NOT NULL UNIQUE,
        original_name TEXT NOT NULL, stored_path TEXT NOT NULL, page_count INTEGER NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""",
    )
    _create(
        c,
        "CREATE TABLE IF NOT EXISTS score_variants(id INTEGER PRIMARY KEY AUTOINCREMENT)",
    )
    before = _columns(c, "score_variants")
    _ensure_columns(c, "score_variants", SCORE_COLUMNS)
    aliases = {
        "start_page": "page_start",
        "end_page": "page_end",
        "source_document": "source_pdf",
        "raw_ocr_title": "ocr_title_raw",
    }
    for old, new in aliases.items():
        if old in before:
            c.execute(
                f'UPDATE score_variants SET "{new}"="{old}" WHERE "{new}" IS NULL OR "{new}"=\'\''
            )
    _create(
        c,
        """CREATE TABLE IF NOT EXISTS review_events(
        id INTEGER PRIMARY KEY AUTOINCREMENT, entity_type TEXT NOT NULL, entity_id INTEGER NOT NULL,
        field_name TEXT, previous_value TEXT, new_value TEXT, source TEXT NOT NULL DEFAULT 'user',
        confidence REAL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""",
    )
    _ensure_columns(
        c,
        "review_events",
        {"source": "TEXT NOT NULL DEFAULT 'user'", "confidence": "REAL"},
    )
    _create(
        c,
        """CREATE TABLE IF NOT EXISTS collections(
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, description TEXT DEFAULT '',
        filter_json TEXT DEFAULT '{}', created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP)""",
    )
    _create(
        c,
        """CREATE TABLE IF NOT EXISTS setlists(
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, service_date TEXT DEFAULT '',
        scripture TEXT DEFAULT '', notes TEXT DEFAULT '', created_at TEXT DEFAULT CURRENT_TIMESTAMP)""",
    )
    _ensure_columns(c, "setlists", {"service_type": "TEXT DEFAULT ''"})

    # Old scores and v2 variants may have overlapping integer IDs. Preserve
    # both rows and record the mapping before updating collection references.
    _create(
        c,
        """CREATE TABLE IF NOT EXISTS migration_score_map(
        legacy_table TEXT NOT NULL, old_id INTEGER NOT NULL, score_id INTEGER NOT NULL,
        PRIMARY KEY(legacy_table,old_id))""",
    )
    mapping = {}
    if _exists(c, "scores"):
        for row in c.execute("SELECT * FROM scores ORDER BY id").fetchall():
            row = dict(row)
            old_id = row.pop("id")
            values = {k: v for k, v in row.items() if k in SCORE_COLUMNS}
            if not c.execute(
                "SELECT 1 FROM score_variants WHERE id=?", (old_id,)
            ).fetchone():
                values["id"] = old_id
            names = list(values)
            cur = c.execute(
                f"INSERT INTO score_variants({','.join(names)}) VALUES({','.join('?' for _ in names)})",
                [values[k] for k in names],
            )
            mapping[old_id] = cur.lastrowid
            c.execute(
                "INSERT INTO migration_score_map VALUES('scores',?,?)",
                (old_id, cur.lastrowid),
            )
        for old_id, new_id in mapping.items():
            c.execute(
                "UPDATE review_events SET entity_id=? WHERE entity_type='score' AND entity_id=?",
                (new_id, old_id),
            )

    for table, parent, extra in (
        ("collection_items", "collection_id", "section TEXT DEFAULT ''"),
        ("setlist_items", "setlist_id", "selected_key TEXT DEFAULT ''"),
    ):
        rows = (
            [dict(r) for r in c.execute(f"SELECT * FROM {table}")]
            if _exists(c, table)
            else []
        )
        if _exists(c, table):
            c.execute(f"DROP TABLE {table}")
        parent_table = "collections" if table == "collection_items" else "setlists"
        c.execute(f"""CREATE TABLE {table}(
            id INTEGER PRIMARY KEY AUTOINCREMENT, {parent} INTEGER NOT NULL REFERENCES {parent_table}(id) ON DELETE CASCADE,
            song_id INTEGER NOT NULL REFERENCES songs(id) ON DELETE RESTRICT,
            score_id INTEGER REFERENCES score_variants(id) ON DELETE RESTRICT,
            position INTEGER NOT NULL, item_notes TEXT DEFAULT '', {extra})""")
        cols = _columns(c, table)
        for row in rows:
            row["score_id"] = mapping.get(row.get("score_id"), row.get("score_id"))
            if row["score_id"] is not None:
                owner = c.execute(
                    "SELECT a.song_id FROM score_variants sc JOIN arrangements a ON a.id=sc.arrangement_id WHERE sc.id=?",
                    (row["score_id"],),
                ).fetchone()
                if not owner:
                    raise ValueError(
                        f"Migration blocked: {table} refers to missing score {row['score_id']}"
                    )
                row["song_id"] = owner[0]
            values = {k: v for k, v in row.items() if k in cols}
            c.execute(
                f"INSERT INTO {table}({','.join(values)}) VALUES({','.join('?' for _ in values)})",
                list(values.values()),
            )
    if _exists(c, "scores"):
        c.execute("DROP TABLE scores")
    # Read-only compatibility: all application writes use score_variants.
    c.execute("CREATE VIEW IF NOT EXISTS scores AS SELECT * FROM score_variants")
    from .normalize import canonical_title

    used = {r[0] for r in c.execute("SELECT wgid FROM songs WHERE wgid IS NOT NULL")}
    n = 1
    for row in c.execute("SELECT id,wgid,title FROM songs ORDER BY id").fetchall():
        wgid = row[1]
        if not wgid:
            while f"WG{n:06d}" in used:
                n += 1
            wgid = f"WG{n:06d}"
            used.add(wgid)
        c.execute(
            "UPDATE songs SET wgid=?,normalized_title=?,created_at=COALESCE(created_at,CURRENT_TIMESTAMP),updated_at=COALESCE(updated_at,CURRENT_TIMESTAMP) WHERE id=?",
            (wgid, canonical_title(row[2]), row[0]),
        )
    c.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_wgid ON songs(wgid)")
    c.execute("CREATE INDEX IF NOT EXISTS ix_song_title ON songs(normalized_title)")
    if _exists(c, "song_tags") and _exists(c, "tags"):
        for sid, category, name in c.execute(
            "SELECT st.song_id,t.category,t.name FROM song_tags st JOIN tags t ON t.id=st.tag_id"
        ).fetchall():
            field = {
                "theme": "themes",
                "themes": "themes",
                "mood": "mood",
                "flow": "flow",
            }.get(category, "tags")
            old = c.execute(f"SELECT {field} FROM songs WHERE id=?", (sid,)).fetchone()
            if old:
                terms = [s.strip() for s in (old[0] or "").split(",") if s.strip()]
                if name not in terms:
                    c.execute(
                        f"UPDATE songs SET {field}=? WHERE id=?",
                        (",".join([*terms, name]), sid),
                    )
    if _exists(c, "scripture_links"):
        for sid, reference in c.execute(
            "SELECT song_id,reference_text FROM scripture_links"
        ).fetchall():
            old = c.execute("SELECT bible FROM songs WHERE id=?", (sid,)).fetchone()
            if old and reference not in (old[0] or ""):
                c.execute(
                    "UPDATE songs SET bible=? WHERE id=?",
                    (",".join(filter(None, [old[0], reference])), sid),
                )
    c.execute("""UPDATE score_variants SET ocr_title_corrected=(SELECT s.title FROM songs s JOIN arrangements a ON a.song_id=s.id WHERE a.id=arrangement_id)
                 WHERE COALESCE(ocr_title_corrected,'')=''""")


def _pipeline(c):
    c.execute("""CREATE TABLE import_jobs(
        id INTEGER PRIMARY KEY AUTOINCREMENT, source_id INTEGER NOT NULL REFERENCES source_documents(id),
        start_page INTEGER NOT NULL, end_page INTEGER NOT NULL, engine TEXT NOT NULL,
        state TEXT NOT NULL DEFAULT 'pending', completed_pages INTEGER NOT NULL DEFAULT 0,
        error TEXT DEFAULT '', created_at TEXT DEFAULT CURRENT_TIMESTAMP, updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(source_id,start_page,end_page,engine))""")
    c.execute("""CREATE TABLE imported_pages(
        id INTEGER PRIMARY KEY AUTOINCREMENT, source_id INTEGER NOT NULL REFERENCES source_documents(id),
        page INTEGER NOT NULL, image_path TEXT NOT NULL, title_crop TEXT NOT NULL,
        raw_title TEXT DEFAULT '', confidence REAL, candidates_json TEXT DEFAULT '[]', raw_lines_json TEXT DEFAULT '[]',
        key_candidate TEXT DEFAULT '', key_confidence REAL, key_evidence TEXT DEFAULT '{}',
        state TEXT DEFAULT 'pending', error TEXT DEFAULT '',
        reviewed_score_id INTEGER REFERENCES score_variants(id) ON DELETE SET NULL,
        UNIQUE(source_id,page))""")
    c.execute("""CREATE TABLE title_corrections(
        id INTEGER PRIMARY KEY AUTOINCREMENT, raw_title TEXT NOT NULL, raw_normalized TEXT NOT NULL,
        song_id INTEGER NOT NULL REFERENCES songs(id) ON DELETE CASCADE, uses INTEGER NOT NULL DEFAULT 1,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP, UNIQUE(raw_normalized,song_id))""")
    c.execute("""CREATE TABLE reference_imports(
        id INTEGER PRIMARY KEY AUTOINCREMENT, source TEXT NOT NULL, content_sha256 TEXT NOT NULL,
        imported_at TEXT DEFAULT CURRENT_TIMESTAMP, UNIQUE(source,content_sha256))""")
    c.execute("""CREATE TABLE reference_rows(
        source TEXT NOT NULL, sheet TEXT NOT NULL, row_number INTEGER NOT NULL, payload TEXT NOT NULL,
        PRIMARY KEY(source,sheet,row_number))""")
    c.execute("CREATE INDEX ix_score_owner ON score_variants(arrangement_id)")
    c.execute(
        "CREATE INDEX ix_score_source ON score_variants(source_id,page_start,page_end)"
    )
    c.execute("CREATE INDEX ix_pending_pages ON imported_pages(state,source_id,page)")
    c.execute("""CREATE TABLE acceptance_runs(
        id INTEGER PRIMARY KEY AUTOINCREMENT, source_sha256 TEXT NOT NULL, pipeline_revision TEXT NOT NULL,
        pages INTEGER NOT NULL, passed INTEGER NOT NULL, evidence_json TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
    # Recover a correction lexicon from already-approved v2 review events.
    from .normalize import canonical_title

    rows = c.execute("""SELECT e.previous_value,a.song_id FROM review_events e
        JOIN score_variants sc ON sc.id=e.entity_id JOIN arrangements a ON a.id=sc.arrangement_id
        WHERE e.entity_type='score_variant' AND e.field_name='title'""").fetchall()
    for raw, song in rows:
        if raw:
            c.execute(
                "INSERT OR IGNORE INTO title_corrections(raw_title,raw_normalized,song_id) VALUES(?,?,?)",
                (raw, canonical_title(raw), song),
            )


def _observations(c):
    _ensure_columns(
        c,
        "imported_pages",
        {"ocr_engine": "TEXT DEFAULT 'legacy'", "ocr_revision": "TEXT DEFAULT ''"},
    )
    c.execute("""CREATE TABLE ocr_observations(
        id INTEGER PRIMARY KEY AUTOINCREMENT, imported_page_id INTEGER NOT NULL REFERENCES imported_pages(id) ON DELETE CASCADE,
        engine TEXT NOT NULL, revision TEXT NOT NULL, raw_title TEXT, confidence REAL,
        raw_lines_json TEXT NOT NULL, key_evidence TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
    c.execute("""INSERT INTO ocr_observations(imported_page_id,engine,revision,raw_title,confidence,raw_lines_json,key_evidence)
        SELECT id,'legacy','',raw_title,confidence,raw_lines_json,key_evidence FROM imported_pages
        WHERE state IN ('ocr_done','reviewed')""")


def migrate(conn: sqlite3.Connection, path: Path) -> Path | None:
    current = conn.execute("PRAGMA user_version").fetchone()[0]
    if current > SCHEMA_VERSION:
        raise RuntimeError(
            "더 새로운 앱에서 생성한 DB입니다. 이 버전으로 변경하지 않습니다."
        )
    if current == SCHEMA_VERSION:
        return None
    backup = None
    if conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchone():
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup = path.with_name(
            f"{path.name}.before-v{SCHEMA_VERSION}.{stamp}.{uuid4().hex[:8]}.bak"
        )
        with sqlite3.connect(backup) as destination:
            conn.backup(destination)
    conn.execute("PRAGMA foreign_keys=OFF")
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("""CREATE TABLE IF NOT EXISTS schema_migrations(
            version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
        for version, upgrade in ((1, _core), (2, _pipeline), (3, _observations)):
            if current < version:
                upgrade(conn)
                conn.execute(
                    "INSERT INTO schema_migrations(version) VALUES(?)", (version,)
                )
                conn.execute(f"PRAGMA user_version={version}")
        violations = conn.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise ValueError(
                f"Migration blocked by existing orphaned data: {violations[:5]}"
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.execute("PRAGMA foreign_keys=ON")
    return backup
