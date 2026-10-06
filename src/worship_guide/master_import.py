"""Lossless reference snapshot import; never overwrite user-owned metadata."""

from __future__ import annotations
import hashlib
import json
from pathlib import Path


def import_master_snapshot(db, path):
    payload = Path(path).read_bytes()
    snapshot = json.loads(payload)
    source = snapshot.get("spreadsheet_id") or "WGDB Master"
    checksum = hashlib.sha256(payload).hexdigest()
    if db.conn.execute(
        "SELECT 1 FROM reference_imports WHERE source=? AND content_sha256=?",
        (source, checksum),
    ).fetchone():
        return {"created": 0, "existing": 0, "reused": True}
    sheets = snapshot["sheets"]
    created = existing = 0
    with db.transaction():
        for sheet, values in sheets.items():
            if not values:
                continue
            header = values[0]
            for index, cells in enumerate(values[1:], 2):
                record = dict(zip(header, cells))
                # Exact source rows, scores, URLs and provenance remain local.
                db.conn.execute(
                    """INSERT INTO reference_rows(source,sheet,row_number,payload) VALUES(?,?,?,?)
                    ON CONFLICT(source,sheet,row_number) DO UPDATE SET payload=excluded.payload""",
                    (source, sheet, index, json.dumps(record, ensure_ascii=False)),
                )
        bible = {}
        for row in sheets.get("Bible", [])[1:]:
            if len(row) >= 4:
                bible.setdefault(row[0], []).append(row[3])
        flows = {}
        flow_values = sheets.get("Flow", [])
        if flow_values:
            for row in flow_values[1:]:
                flows[row[0]] = [
                    name
                    for name, score in zip(flow_values[0][2:14], row[2:14])
                    if str(score).isdigit() and int(score) >= 80
                ]
        values = sheets.get("Songs", [])
        if values:
            for cells in values[1:]:
                row = dict(zip(values[0], cells))
                if not row.get("WGID") or not row.get("곡명"):
                    continue
                if db.conn.execute(
                    "SELECT 1 FROM songs WHERE wgid=?", (row["WGID"],)
                ).fetchone():
                    existing += 1
                    continue
                db.save_song(
                    {
                        "wgid": row["WGID"],
                        "title": row["곡명"],
                        "original_title": row.get("원제/부제", ""),
                        "aliases": row.get("원제/부제", ""),
                        "bpm": row.get("BPM", ""),
                        "meter": row.get("박자", ""),
                        "category": row.get("대분류", ""),
                        "themes": ",".join(
                            filter(None, [row.get("핵심 주제"), row.get("보조 주제")])
                        ),
                        "mood": row.get("분위기", ""),
                        "difficulty": row.get("난이도(1-5)", ""),
                        "review_status": row.get("검수 상태", "미검수"),
                        "notes": row.get("메모", ""),
                        "bible": ",".join(bible.get(row["WGID"], [])),
                        "flow": ",".join(flows.get(row["WGID"], [])),
                        "source_metadata": json.dumps(row, ensure_ascii=False),
                    }
                )
                created += 1
        db.conn.execute(
            "INSERT INTO reference_imports(source,content_sha256) VALUES(?,?)",
            (source, checksum),
        )
    # Available keys in a spreadsheet are claims, not fabricated score files.
    return {"created": created, "existing": existing, "reused": False}
