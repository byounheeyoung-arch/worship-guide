from __future__ import annotations
import csv
import sqlite3
import json
from contextlib import contextmanager
from .migrations import migrate
from .normalize import canonical_title
from .paths import default_db_path
from pathlib import Path
from functools import wraps


def atomic(method):
    @wraps(method)
    def wrapped(self, *args, **kwargs):
        with self.transaction():
            return method(self, *args, **kwargs)

    return wrapped


SONG_FIELDS = [
    "wgid",
    "title",
    "original_title",
    "bpm",
    "meter",
    "category",
    "themes",
    "bible",
    "flow",
    "mood",
    "difficulty",
    "favorite",
    "review_status",
    "notes",
    "composer",
    "lyricist",
    "lyrics",
    "aliases",
    "tags",
    "source_metadata",
]


class WGDB:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else default_db_path()
        self.path = self.path.expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path, timeout=10)
        self.conn.row_factory = sqlite3.Row
        self._transaction_depth = 0
        try:
            self.migration_backup = migrate(self.conn, self.path)
            self.conn.execute("PRAGMA foreign_keys=ON")
            self.conn.execute("PRAGMA journal_mode=WAL")
            self.conn.execute("PRAGMA busy_timeout=10000")
            self._resolve_legacy_paths()
        except Exception:
            self.conn.close()
            raise

    def _resolve_legacy_paths(self):
        origin = self.path.parent / "legacy_origin.txt"
        base = (
            Path(origin.read_text(encoding="utf-8")).parent
            if origin.exists()
            else self.path.parent
        )
        with self.conn:
            for row in self.conn.execute(
                "SELECT id,source_pdf,file_path,image_path FROM score_variants"
            ).fetchall():
                for field in ("source_pdf", "file_path", "image_path"):
                    text = row[field]
                    if text and not Path(text).is_absolute():
                        for folder in (base, base.parent):
                            candidate = folder / text
                            if candidate.is_file():
                                self.conn.execute(
                                    f"UPDATE score_variants SET {field}=? WHERE id=?",
                                    (str(candidate.resolve()), row["id"]),
                                )
                                break

    def close(self):
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def _commit(self):
        if not self._transaction_depth:
            self.conn.commit()

    @contextmanager
    def transaction(self):
        outer = self._transaction_depth == 0
        if outer:
            self.conn.execute("BEGIN IMMEDIATE")
        else:
            self.conn.execute(f"SAVEPOINT wg_{self._transaction_depth}")
        level = self._transaction_depth
        self._transaction_depth += 1
        try:
            yield
            if outer:
                self.conn.commit()
            else:
                self.conn.execute(f"RELEASE wg_{level}")
        except Exception:
            if outer:
                self.conn.rollback()
            else:
                self.conn.execute(f"ROLLBACK TO wg_{level}")
                self.conn.execute(f"RELEASE wg_{level}")
            raise
        finally:
            self._transaction_depth -= 1

    def next_wgid(self) -> str:
        row = self.conn.execute(
            "SELECT MAX(CAST(SUBSTR(wgid,3) AS INTEGER)) n FROM songs WHERE wgid LIKE 'WG%'"
        ).fetchone()
        return f"WG{((row['n'] or 0) + 1):06d}"

    def list_songs(self, query: str = ""):
        q = query.strip()
        if not q:
            return self.conn.execute("""SELECT s.*, GROUP_CONCAT(DISTINCT sc.key_signature) available_keys
                FROM songs s LEFT JOIN arrangements a ON a.song_id=s.id LEFT JOIN score_variants sc ON sc.arrangement_id=a.id
                GROUP BY s.id ORDER BY s.title COLLATE NOCASE""").fetchall()
        like = f"%{q}%"
        return self.conn.execute(
            """SELECT s.*, GROUP_CONCAT(DISTINCT sc.key_signature) available_keys
            FROM songs s LEFT JOIN arrangements a ON a.song_id=s.id LEFT JOIN score_variants sc ON sc.arrangement_id=a.id
            WHERE s.title LIKE ? OR s.themes LIKE ? OR s.bible LIKE ? OR s.category LIKE ? OR sc.key_signature LIKE ? OR s.aliases LIKE ? OR s.composer LIKE ? OR s.lyricist LIKE ? OR s.lyrics LIKE ? OR s.tags LIKE ?
            GROUP BY s.id ORDER BY s.title COLLATE NOCASE""",
            (like,) * 10,
        ).fetchall()

    def get_song(self, song_id: int):
        return self.conn.execute(
            "SELECT * FROM songs WHERE id=?", (song_id,)
        ).fetchone()

    @atomic
    def save_song(self, data: dict, song_id: int | None = None) -> int:
        existing = self.get_song(song_id) if song_id else None
        if song_id and existing is None:
            raise ValueError("곡을 찾을 수 없습니다.")
        clean = {k: data.get(k, existing[k] if existing else "") for k in SONG_FIELDS}
        if not str(clean["title"] or "").strip():
            raise ValueError("곡명을 입력하세요.")
        clean["title"] = clean["title"].strip()
        if not clean["wgid"]:
            clean["wgid"] = existing["wgid"] if existing else self.next_wgid()
        clean["favorite"] = int(
            str(clean["favorite"]).lower() in {"1", "true", "yes", "y", "on"}
        )
        for key in ("bpm", "difficulty"):
            v = str(clean[key] if clean[key] is not None else "").strip()
            if v and not v.isdigit():
                raise ValueError(f"{key}: 숫자를 입력하세요.")
            clean[key] = int(v) if v else None
        if clean["difficulty"] is not None and not 1 <= clean["difficulty"] <= 5:
            raise ValueError("난이도는 1~5입니다.")
        clean["normalized_title"] = canonical_title(clean["title"])
        fields = list(clean)
        if song_id:
            self.conn.execute(
                f"UPDATE songs SET {','.join(k + '=?' for k in fields)}, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                [clean[k] for k in fields] + [song_id],
            )
            self._commit()
            return song_id
        cur = self.conn.execute(
            f"INSERT INTO songs({','.join(fields)},created_at,updated_at) VALUES({','.join('?' for _ in fields)},CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)",
            [clean[k] for k in fields],
        )
        self._commit()
        return int(cur.lastrowid)

    @atomic
    def get_or_create_song(self, title: str):
        title = title.strip()
        if not title:
            raise ValueError("확정 제목이 필요합니다.")
        rows = self.conn.execute(
            "SELECT id,wgid FROM songs WHERE normalized_title=? ORDER BY id",
            (canonical_title(title),),
        ).fetchall()
        if len(rows) > 1:
            raise ValueError(
                "동명곡이 여러 개입니다. 추천 목록에서 기존 곡을 선택하거나 동명곡 새 등록을 선택하세요."
            )
        if rows:
            return rows[0]["id"], rows[0]["wgid"]
        sid = self.save_song({"title": title, "review_status": "reviewed"})
        return sid, self.get_song(sid)["wgid"]

    @atomic
    def delete_song(self, song_id: int):
        if any(
            self.conn.execute(
                f"SELECT 1 FROM {table} WHERE song_id=?", (song_id,)
            ).fetchone()
            for table in ("collection_items", "setlist_items")
        ):
            raise ValueError(
                "악보집/세트리스트에서 사용하는 곡입니다. 항목을 먼저 제거하세요."
            )
        self.conn.execute(
            "DELETE FROM score_variants WHERE arrangement_id IN (SELECT id FROM arrangements WHERE song_id=?)",
            (song_id,),
        )
        self.conn.execute("DELETE FROM arrangements WHERE song_id=?", (song_id,))
        self.conn.execute("DELETE FROM songs WHERE id=?", (song_id,))
        self._commit()

    @atomic
    def ensure_arrangement(self, song_id: int, name: str = "Original") -> int:
        name = (name or "Original").strip()
        row = self.conn.execute(
            "SELECT id FROM arrangements WHERE song_id=? AND name=?", (song_id, name)
        ).fetchone()
        if row:
            return int(row["id"])
        cur = self.conn.execute(
            "INSERT INTO arrangements(song_id,name) VALUES(?,?)", (song_id, name)
        )
        self._commit()
        return int(cur.lastrowid)

    def list_scores(self, song_id: int):
        return self.conn.execute(
            """SELECT sc.*,a.name arrangement FROM score_variants sc JOIN arrangements a ON a.id=sc.arrangement_id
            WHERE a.song_id=? ORDER BY a.name, COALESCE(sc.page_start,999999), sc.key_signature""",
            (song_id,),
        ).fetchall()

    def get_score(self, score_id: int):
        return self.conn.execute(
            """SELECT sc.*,a.song_id,a.name arrangement FROM score_variants sc JOIN arrangements a ON a.id=sc.arrangement_id WHERE sc.id=?""",
            (score_id,),
        ).fetchone()

    @atomic
    def save_score(self, song_id: int, data: dict, score_id: int | None = None) -> int:
        existing = self.get_score(score_id) if score_id else None
        if score_id and existing is None:
            raise ValueError("악보를 찾을 수 없습니다.")

        def value(k, default=""):
            return data.get(
                k, existing[k] if existing and k in existing.keys() else default
            )

        arr_id = self.ensure_arrangement(song_id, value("arrangement") or "Original")

        def number(v, cast=int):
            if v is None or str(v).strip() == "":
                return None
            return cast(v)

        from .key_ocr import normalize_signature

        key = normalize_signature(value("key_signature"))
        start = number(value("page_start"))
        end = number(value("page_end")) or start
        if start is not None and (start < 1 or end < start):
            raise ValueError("악보 페이지 범위가 잘못되었습니다.")
        vals = {
            "arrangement_id": arr_id,
            "key_signature": key,
            "page_start": start,
            "page_end": end,
            "ocr_confidence": number(value("ocr_confidence"), float),
            "key_confidence": number(value("key_confidence"), float),
            "source_id": number(value("source_id")),
        }
        for k in (
            "source_pdf",
            "file_path",
            "image_path",
            "ocr_title_raw",
            "ocr_title_corrected",
            "raw_ocr_key",
            "key_candidate",
            "key_evidence",
            "key_origin",
            "review_status",
            "notes",
        ):
            vals[k] = str(value(k) or "")
        # Original OCR is evidence and never overwritten by a user edit or retry.
        if existing and existing["ocr_title_raw"]:
            vals["ocr_title_raw"] = existing["ocr_title_raw"]
        if not vals["ocr_title_corrected"]:
            vals["ocr_title_corrected"] = self.get_song(song_id)["title"]
        vals["review_status"] = vals["review_status"] or "unreviewed"
        fields = list(vals)
        if score_id:
            self.conn.execute(
                f"UPDATE score_variants SET {','.join(k + '=?' for k in fields)} WHERE id=?",
                [vals[k] for k in fields] + [score_id],
            )
            for table in ("collection_items", "setlist_items"):
                self.conn.execute(
                    f"UPDATE {table} SET song_id=? WHERE score_id=?",
                    (song_id, score_id),
                )
            self._commit()
            return score_id
        cur = self.conn.execute(
            f"INSERT INTO score_variants({','.join(fields)},created_at) VALUES({','.join('?' for _ in fields)},CURRENT_TIMESTAMP)",
            [vals[k] for k in fields],
        )
        self._commit()
        return int(cur.lastrowid)

    @atomic
    def delete_score(self, score_id: int):
        self.conn.execute("DELETE FROM score_variants WHERE id=?", (score_id,))
        self._commit()

    def import_ocr_csv(
        self, csv_path: str | Path, source_pdf: str | Path | None = None
    ):
        from .pipeline import import_legacy_csv

        count = import_legacy_csv(self, csv_path, source_pdf=source_pdf)
        return 0, 0, count

    def export_csv(self, csv_path: str | Path):
        rows = self.conn.execute("""SELECT s.wgid,s.title,s.original_title,s.bpm,s.meter,s.category,s.themes,s.bible,s.flow,s.mood,s.difficulty,
            s.review_status,a.name arrangement,sc.key_signature,sc.page_start,sc.page_end,sc.source_pdf,sc.file_path,sc.ocr_title_raw,
            sc.ocr_title_corrected,sc.ocr_confidence,sc.review_status score_status
            FROM songs s LEFT JOIN arrangements a ON a.song_id=s.id LEFT JOIN score_variants sc ON sc.arrangement_id=a.id ORDER BY s.wgid,sc.page_start""").fetchall()
        fields = (
            list(rows[0].keys())
            if rows
            else ["wgid", "title", "arrangement", "key_signature", "page_start"]
        )
        with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            [w.writerow(dict(r)) for r in rows]

    # ----- Songbook collections -----
    @atomic
    def create_collection(
        self, name: str, description: str = "", filters: dict | None = None
    ) -> int:
        cur = self.conn.execute(
            "INSERT INTO collections(name,description,filter_json) VALUES(?,?,?)",
            (name.strip(), description, json.dumps(filters or {}, ensure_ascii=False)),
        )
        self._commit()
        return int(cur.lastrowid)

    @atomic
    def update_collection(
        self,
        collection_id: int,
        name: str,
        description: str = "",
        filters: dict | None = None,
    ):
        self.conn.execute(
            "UPDATE collections SET name=?,description=?,filter_json=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (
                name.strip(),
                description,
                json.dumps(filters or {}, ensure_ascii=False),
                collection_id,
            ),
        )
        self._commit()

    def list_collections(self):
        return self.conn.execute(
            "SELECT * FROM collections ORDER BY updated_at DESC,id DESC"
        ).fetchall()

    def get_collection(self, collection_id: int):
        return self.conn.execute(
            "SELECT * FROM collections WHERE id=?", (collection_id,)
        ).fetchone()

    @atomic
    def delete_collection(self, collection_id: int):
        self.conn.execute("DELETE FROM collections WHERE id=?", (collection_id,))
        self._commit()

    @staticmethod
    def _terms(value: str):
        return [
            x.strip()
            for x in (
                ",".join(value)
                if isinstance(value, (list, tuple, set))
                else str(value or "")
            )
            .replace(";", ",")
            .split(",")
            if x.strip()
        ]

    def collection_candidates(
        self,
        *,
        query: str = "",
        category: str = "",
        themes: str = "",
        mood: str = "",
        key_signature: str = "",
        flow: str = "",
        max_difficulty: str = "",
        bible: str = "",
        tags: str = "",
        composer: str = "",
        lyricist: str = "",
        reviewed_only: bool = False,
    ):
        clauses = []
        params = []
        if query.strip():
            like = f"%{query.strip()}%"
            clauses.append(
                "(s.title LIKE ? OR s.original_title LIKE ? OR s.bible LIKE ? OR s.aliases LIKE ? OR s.lyrics LIKE ?)"
            )
            params += [like] * 5
        for column, value in (
            ("s.category", category),
            ("s.themes", themes),
            ("s.mood", mood),
            ("s.flow", flow),
            ("s.bible", bible),
            ("s.tags", tags),
            ("s.composer", composer),
            ("s.lyricist", lyricist),
        ):
            terms = self._terms(value)
            if terms:
                sub = []
                for term in terms:
                    sub.append(f"{column} LIKE ?")
                    params.append(f"%{term}%")
                clauses.append("(" + " OR ".join(sub) + ")")
        keys = self._terms(key_signature)
        if keys:
            clauses.append(
                "(" + " OR ".join("sc.key_signature = ?" for _ in keys) + ")"
            )
            params += keys
        d = str(max_difficulty or "").strip()
        if d:
            if not d.isdigit() or not 1 <= int(d) <= 5:
                raise ValueError("최대 난이도는 1~5입니다.")
            clauses.append("s.difficulty <= ?")
            params.append(int(d))
        if reviewed_only:
            clauses.append("sc.review_status IN ('reviewed','검수완료')")
        where = "WHERE " + " AND ".join(clauses) if clauses else ""
        sql = f"""SELECT sc.id score_id,s.id song_id,s.wgid,s.title,s.category,s.themes,s.mood,s.flow,s.difficulty,s.bible,s.tags,
            a.name arrangement,sc.key_signature,sc.page_start,sc.page_end,sc.source_pdf,sc.file_path,sc.image_path,sc.review_status score_status
            FROM score_variants sc JOIN arrangements a ON a.id=sc.arrangement_id JOIN songs s ON s.id=a.song_id
            {where} ORDER BY s.title COLLATE NOCASE,a.name,sc.key_signature,sc.page_start"""
        return self.conn.execute(sql, params).fetchall()

    @atomic
    def add_score_to_collection(self, collection_id: int, score_id: int):
        row = self.conn.execute(
            "SELECT a.song_id FROM score_variants sc JOIN arrangements a ON a.id=sc.arrangement_id WHERE sc.id=?",
            (score_id,),
        ).fetchone()
        if not row:
            raise ValueError("악보 버전을 찾을 수 없습니다.")
        exists = self.conn.execute(
            "SELECT 1 FROM collection_items WHERE collection_id=? AND score_id=?",
            (collection_id, score_id),
        ).fetchone()
        if exists:
            return
        pos = self.conn.execute(
            "SELECT COALESCE(MAX(position),0)+1 p FROM collection_items WHERE collection_id=?",
            (collection_id,),
        ).fetchone()["p"]
        self.conn.execute(
            "INSERT INTO collection_items(collection_id,song_id,score_id,position) VALUES(?,?,?,?)",
            (collection_id, row["song_id"], score_id, pos),
        )
        self._commit()

    def get_collection_items(self, collection_id: int):
        sql = """SELECT ci.*,s.wgid,s.title,s.themes,s.bible,a.name arrangement,sc.image_path,sc.key_signature,sc.page_start,sc.page_end,sc.source_pdf,sc.file_path
            FROM collection_items ci JOIN songs s ON s.id=ci.song_id JOIN score_variants sc ON sc.id=ci.score_id JOIN arrangements a ON a.id=sc.arrangement_id
            WHERE ci.collection_id=? ORDER BY ci.position,ci.id"""
        return self.conn.execute(sql, (collection_id,)).fetchall()

    @atomic
    def remove_collection_item(self, item_id: int):
        row = self.conn.execute(
            "SELECT collection_id FROM collection_items WHERE id=?", (item_id,)
        ).fetchone()
        if not row:
            return
        cid = row["collection_id"]
        self.conn.execute("DELETE FROM collection_items WHERE id=?", (item_id,))
        self._renumber_collection(cid)
        self._commit()

    def _renumber_collection(self, collection_id: int):
        rows = self.conn.execute(
            "SELECT id FROM collection_items WHERE collection_id=? ORDER BY position,id",
            (collection_id,),
        ).fetchall()
        for i, r in enumerate(rows, 1):
            self.conn.execute(
                "UPDATE collection_items SET position=? WHERE id=?", (i, r["id"])
            )

    @atomic
    def move_collection_item(self, item_id: int, delta: int):
        row = self.conn.execute(
            "SELECT collection_id,position FROM collection_items WHERE id=?", (item_id,)
        ).fetchone()
        if not row:
            return
        cid, pos = int(row["collection_id"]), int(row["position"])
        target = pos + delta
        other = self.conn.execute(
            "SELECT id FROM collection_items WHERE collection_id=? AND position=?",
            (cid, target),
        ).fetchone()
        if not other:
            return
        self.conn.execute(
            "UPDATE collection_items SET position=-1 WHERE id=?", (item_id,)
        )
        self.conn.execute(
            "UPDATE collection_items SET position=? WHERE id=?", (pos, other["id"])
        )
        self.conn.execute(
            "UPDATE collection_items SET position=? WHERE id=?", (target, item_id)
        )
        self._commit()

    @atomic
    def create_setlist(
        self, name: str, service_date: str = "", scripture: str = "", notes: str = ""
    ) -> int:
        cur = self.conn.execute(
            "INSERT INTO setlists(name,service_date,scripture,notes) VALUES(?,?,?,?)",
            (name, service_date, scripture, notes),
        )
        self._commit()
        return int(cur.lastrowid)

    def list_setlists(self):
        return self.conn.execute(
            "SELECT * FROM setlists ORDER BY service_date DESC,id DESC"
        ).fetchall()

    @atomic
    def add_song_to_setlist(
        self,
        setlist_id: int,
        song_id: int,
        score_id: int | None = None,
        selected_key: str = "",
    ):
        if score_id is not None:
            score = self.get_score(score_id)
            if not score or score["song_id"] != song_id:
                raise ValueError("선택한 악보와 곡이 일치하지 않습니다.")
            if selected_key and selected_key != score["key_signature"]:
                raise ValueError("선택한 악보의 Key와 요청 Key가 다릅니다.")
        row = self.conn.execute(
            "SELECT COALESCE(MAX(position),0)+1 p FROM setlist_items WHERE setlist_id=?",
            (setlist_id,),
        ).fetchone()
        self.conn.execute(
            "INSERT INTO setlist_items(setlist_id,song_id,score_id,position,selected_key) VALUES(?,?,?,?,?)",
            (setlist_id, song_id, score_id, row["p"], selected_key),
        )
        self._commit()

    def get_setlist_items(self, setlist_id: int):
        return self.conn.execute(
            """SELECT si.*,s.title,s.wgid,sc.key_signature score_key FROM setlist_items si JOIN songs s ON s.id=si.song_id LEFT JOIN score_variants sc ON sc.id=si.score_id
            WHERE si.setlist_id=? ORDER BY si.position""",
            (setlist_id,),
        ).fetchall()

    def review_event(self, score_id, field, before, after, confidence=None):
        self.conn.execute(
            """INSERT INTO review_events(entity_type,entity_id,field_name,previous_value,new_value,confidence)
            VALUES('score_variant',?,?,?,?,?)""",
            (score_id, field, before, after, confidence),
        )

    def suggest_titles(self, raw: str, limit: int = 4):
        from .title_lexicon import title_similarity

        if not raw.strip():
            return []
        normalized = canonical_title(raw)
        remembered = {
            r[0]
            for r in self.conn.execute(
                "SELECT song_id FROM title_corrections WHERE raw_normalized=?",
                (normalized,),
            )
        }
        matches = []
        for song in self.conn.execute(
            "SELECT id,wgid,title,aliases,original_title,composer FROM songs"
        ):
            targets = [
                song["title"],
                song["original_title"],
                *self._terms(song["aliases"]),
            ]
            score = max(title_similarity(raw, t or "") for t in targets)
            if song["id"] in remembered:
                score = 1.0
            if score >= 0.55:
                matches.append(
                    {
                        "song_id": song["id"],
                        "title": song["title"],
                        "confidence": round(score, 4),
                        "wgid": song["wgid"],
                        "composer": song["composer"] or "",
                        "remembered": song["id"] in remembered,
                    }
                )
        return sorted(matches, key=lambda r: (-r["confidence"], r["song_id"]))[:limit]

    def review_queue(self, source_id=None, include_reviewed=False):
        clauses, params = [], []
        if source_id is not None:
            clauses.append("p.source_id=?")
            params.append(source_id)
        if not include_reviewed:
            clauses.append("p.state!='reviewed'")
        where = "WHERE " + " AND ".join(clauses) if clauses else ""
        return self.conn.execute(
            f"""SELECT p.*,d.original_name,d.stored_path source_pdf,
            sc.ocr_title_corrected,sc.key_signature,sc.review_status
            FROM imported_pages p JOIN source_documents d ON d.id=p.source_id
            LEFT JOIN score_variants sc ON sc.id=p.reviewed_score_id
            {where} ORDER BY p.source_id,p.page""",
            params,
        ).fetchall()

    def approve_page(
        self,
        page_id: int,
        title: str,
        key_signature: str = "",
        arrangement="Original",
        song_id=None,
        new_song=False,
    ):
        """The only OCR -> authoritative score boundary, requiring explicit review."""
        title = title.strip()
        if not title:
            raise ValueError("확정 제목을 입력하세요.")
        with self.transaction():
            page = self.conn.execute(
                """SELECT p.*,d.stored_path FROM imported_pages p
                JOIN source_documents d ON d.id=p.source_id WHERE p.id=?""",
                (page_id,),
            ).fetchone()
            if not page or page["state"] in {"pending", "failed"}:
                raise ValueError("OCR 처리가 완료된 페이지를 선택하세요.")
            if new_song:
                song_id = self.save_song({"title": title, "review_status": "reviewed"})
            elif song_id is None:
                song_id, _ = self.get_or_create_song(title)
            else:
                song = self.get_song(song_id)
                if not song or song["title"] != title:
                    raise ValueError("선택한 곡과 확정 제목이 다릅니다.")
            previous = (
                self.get_score(page["reviewed_score_id"])
                if page["reviewed_score_id"]
                else None
            )
            score_id = self.save_score(
                song_id,
                {
                    "arrangement": arrangement,
                    "key_signature": key_signature,
                    "key_origin": "user",
                    "key_candidate": page["key_candidate"],
                    "key_confidence": page["key_confidence"],
                    "key_evidence": page["key_evidence"],
                    "raw_ocr_key": page["key_evidence"],
                    "source_id": page["source_id"],
                    "page_start": page["page"],
                    "page_end": page["page"],
                    "source_pdf": page["stored_path"],
                    "image_path": page["image_path"],
                    "ocr_title_raw": page["raw_title"],
                    "ocr_title_corrected": title,
                    "ocr_confidence": page["confidence"],
                    "review_status": "reviewed",
                },
                page["reviewed_score_id"],
            )
            self.review_event(
                score_id,
                "title",
                previous["ocr_title_corrected"] if previous else page["raw_title"],
                title,
                page["confidence"],
            )
            self.review_event(
                score_id,
                "key",
                previous["key_signature"] if previous else "",
                key_signature,
                page["key_confidence"],
            )
            self.conn.execute(
                "UPDATE imported_pages SET state='reviewed',reviewed_score_id=? WHERE id=?",
                (score_id, page_id),
            )
            if page["raw_title"]:
                self.conn.execute(
                    """INSERT INTO title_corrections(raw_title,raw_normalized,song_id) VALUES(?,?,?)
                    ON CONFLICT(raw_normalized,song_id) DO UPDATE SET uses=uses+1,updated_at=CURRENT_TIMESTAMP""",
                    (page["raw_title"], canonical_title(page["raw_title"]), song_id),
                )
            return score_id

    def collection_suggestions(self, collection_id):
        collection = self.get_collection(collection_id)
        if not collection:
            raise ValueError("악보집을 찾을 수 없습니다.")
        selected = {r["score_id"] for r in self.get_collection_items(collection_id)}
        allowed = {
            "query",
            "category",
            "themes",
            "mood",
            "key_signature",
            "flow",
            "max_difficulty",
            "bible",
            "tags",
            "composer",
            "lyricist",
            "reviewed_only",
        }
        filters = {
            k: v
            for k, v in json.loads(collection["filter_json"] or "{}").items()
            if k in allowed
        }
        return [
            r
            for r in self.collection_candidates(**filters)
            if r["score_id"] not in selected
        ]

    @atomic
    def update_collection_item(self, item_id, *, section="", notes=""):
        self.conn.execute(
            "UPDATE collection_items SET section=?,item_notes=? WHERE id=?",
            (section, notes, item_id),
        )
        self._commit()

    def setlist_from_collection(
        self, collection_id, name, service_date="", scripture="", service_type=""
    ):
        with self.transaction():
            sid = self.create_setlist(name, service_date, scripture)
            self.conn.execute(
                "UPDATE setlists SET service_type=? WHERE id=?", (service_type, sid)
            )
            for item in self.get_collection_items(collection_id):
                self.add_song_to_setlist(
                    sid, item["song_id"], item["score_id"], item["key_signature"]
                )
                self.conn.execute(
                    "UPDATE setlist_items SET item_notes=? WHERE setlist_id=? AND score_id=?",
                    (item["item_notes"], sid, item["score_id"]),
                )
            return sid

    def setlist_export_items(self, setlist_id):
        return self.conn.execute(
            """SELECT si.*,s.title,s.themes,s.bible,sc.key_signature,
            sc.page_start,sc.page_end,sc.source_pdf,sc.file_path,sc.image_path,a.name arrangement
            FROM setlist_items si JOIN score_variants sc ON sc.id=si.score_id
            JOIN arrangements a ON a.id=sc.arrangement_id JOIN songs s ON s.id=a.song_id
            WHERE si.setlist_id=? ORDER BY si.position,si.id""",
            (setlist_id,),
        ).fetchall()

    @atomic
    def update_setlist_item(self, item_id, notes):
        self.conn.execute(
            "UPDATE setlist_items SET item_notes=? WHERE id=?", (notes, item_id)
        )
        self._commit()

    def move_setlist_item(self, item_id, delta):
        with self.transaction():
            row = self.conn.execute(
                "SELECT * FROM setlist_items WHERE id=?", (item_id,)
            ).fetchone()
            if not row:
                return
            other = self.conn.execute(
                "SELECT id FROM setlist_items WHERE setlist_id=? AND position=?",
                (row["setlist_id"], row["position"] + delta),
            ).fetchone()
            if other:
                self.conn.execute(
                    "UPDATE setlist_items SET position=? WHERE id=?",
                    (row["position"], other["id"]),
                )
                self.conn.execute(
                    "UPDATE setlist_items SET position=? WHERE id=?",
                    (row["position"] + delta, item_id),
                )

    def remove_setlist_item(self, item_id):
        with self.transaction():
            row = self.conn.execute(
                "SELECT setlist_id FROM setlist_items WHERE id=?", (item_id,)
            ).fetchone()
            if not row:
                return
            self.conn.execute("DELETE FROM setlist_items WHERE id=?", (item_id,))
            for position, item in enumerate(
                self.conn.execute(
                    "SELECT id FROM setlist_items WHERE setlist_id=? ORDER BY position,id",
                    (row[0],),
                ).fetchall(),
                1,
            ):
                self.conn.execute(
                    "UPDATE setlist_items SET position=? WHERE id=?",
                    (position, item[0]),
                )
