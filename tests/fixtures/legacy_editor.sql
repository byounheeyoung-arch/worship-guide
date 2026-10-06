
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS songs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    wgid TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    original_title TEXT DEFAULT '',
    bpm INTEGER,
    meter TEXT DEFAULT '',
    category TEXT DEFAULT '',
    themes TEXT DEFAULT '',
    bible TEXT DEFAULT '',
    flow TEXT DEFAULT '',
    mood TEXT DEFAULT '',
    difficulty INTEGER,
    favorite INTEGER NOT NULL DEFAULT 0,
    review_status TEXT DEFAULT '미검수',
    notes TEXT DEFAULT '',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS arrangements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    song_id INTEGER NOT NULL REFERENCES songs(id) ON DELETE CASCADE,
    name TEXT NOT NULL DEFAULT 'Original',
    source TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    UNIQUE(song_id, name)
);
CREATE TABLE IF NOT EXISTS scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    arrangement_id INTEGER NOT NULL REFERENCES arrangements(id) ON DELETE CASCADE,
    key_signature TEXT DEFAULT '',
    page_start INTEGER,
    page_end INTEGER,
    source_pdf TEXT DEFAULT '',
    file_path TEXT DEFAULT '',
    ocr_title_raw TEXT DEFAULT '',
    ocr_title_corrected TEXT DEFAULT '',
    ocr_confidence REAL,
    review_status TEXT DEFAULT '미검수',
    notes TEXT DEFAULT '',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS collections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    filter_json TEXT DEFAULT '{}',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS collection_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    collection_id INTEGER NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
    song_id INTEGER NOT NULL REFERENCES songs(id) ON DELETE CASCADE,
    score_id INTEGER NOT NULL REFERENCES scores(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    item_notes TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS setlists (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    service_date TEXT DEFAULT '',
    scripture TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS setlist_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    setlist_id INTEGER NOT NULL REFERENCES setlists(id) ON DELETE CASCADE,
    song_id INTEGER NOT NULL REFERENCES songs(id) ON DELETE CASCADE,
    score_id INTEGER REFERENCES scores(id) ON DELETE SET NULL,
    position INTEGER NOT NULL,
    selected_key TEXT DEFAULT '',
    item_notes TEXT DEFAULT ''
);
