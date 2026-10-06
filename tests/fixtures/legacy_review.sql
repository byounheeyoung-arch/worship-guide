
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
