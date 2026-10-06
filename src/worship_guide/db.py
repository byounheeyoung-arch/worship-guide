from __future__ import annotations
import csv
import sqlite3
import json
from pathlib import Path

SCHEMA = """
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
"""

SONG_FIELDS = [
    "wgid","title","original_title","bpm","meter","category","themes","bible",
    "flow","mood","difficulty","favorite","review_status","notes"
]

class WGDB:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self): self.conn.close()

    def next_wgid(self) -> str:
        row = self.conn.execute("SELECT MAX(CAST(SUBSTR(wgid,3) AS INTEGER)) n FROM songs WHERE wgid LIKE 'WG%'").fetchone()
        return f"WG{((row['n'] or 0)+1):06d}"

    def list_songs(self, query: str = ""):
        q=query.strip()
        if not q:
            return self.conn.execute("""SELECT s.*, GROUP_CONCAT(DISTINCT sc.key_signature) available_keys
                FROM songs s LEFT JOIN arrangements a ON a.song_id=s.id LEFT JOIN scores sc ON sc.arrangement_id=a.id
                GROUP BY s.id ORDER BY s.title COLLATE NOCASE""").fetchall()
        like=f"%{q}%"
        return self.conn.execute("""SELECT s.*, GROUP_CONCAT(DISTINCT sc.key_signature) available_keys
            FROM songs s LEFT JOIN arrangements a ON a.song_id=s.id LEFT JOIN scores sc ON sc.arrangement_id=a.id
            WHERE s.title LIKE ? OR s.themes LIKE ? OR s.bible LIKE ? OR s.category LIKE ? OR sc.key_signature LIKE ?
            GROUP BY s.id ORDER BY s.title COLLATE NOCASE""",(like,like,like,like,like)).fetchall()

    def get_song(self, song_id:int):
        return self.conn.execute("SELECT * FROM songs WHERE id=?",(song_id,)).fetchone()

    def save_song(self, data:dict, song_id:int|None=None)->int:
        clean={k:data.get(k,"") for k in SONG_FIELDS}
        if not clean["wgid"]: clean["wgid"]=self.next_wgid()
        clean["favorite"]=1 if clean["favorite"] is True or str(clean["favorite"]).lower() in {"1","true","yes","y","on"} else 0
        for key in ("bpm","difficulty"):
            v=str(clean[key]).strip(); clean[key]=int(v) if v.isdigit() else None
        if song_id:
            assigns=",".join(f"{k}=?" for k in SONG_FIELDS)
            self.conn.execute(f"UPDATE songs SET {assigns}, updated_at=CURRENT_TIMESTAMP WHERE id=?",[clean[k] for k in SONG_FIELDS]+[song_id])
            self.conn.commit(); return song_id
        cols=",".join(SONG_FIELDS); ph=",".join("?" for _ in SONG_FIELDS)
        cur=self.conn.execute(f"INSERT INTO songs({cols}) VALUES({ph})",[clean[k] for k in SONG_FIELDS])
        self.conn.commit(); return int(cur.lastrowid)

    def delete_song(self,song_id:int):
        self.conn.execute("DELETE FROM songs WHERE id=?",(song_id,)); self.conn.commit()

    def ensure_arrangement(self,song_id:int,name:str="Original")->int:
        name=(name or "Original").strip()
        row=self.conn.execute("SELECT id FROM arrangements WHERE song_id=? AND name=?",(song_id,name)).fetchone()
        if row:return int(row["id"])
        cur=self.conn.execute("INSERT INTO arrangements(song_id,name) VALUES(?,?)",(song_id,name)); self.conn.commit(); return int(cur.lastrowid)

    def list_scores(self,song_id:int):
        return self.conn.execute("""SELECT sc.*,a.name arrangement FROM scores sc JOIN arrangements a ON a.id=sc.arrangement_id
            WHERE a.song_id=? ORDER BY a.name, COALESCE(sc.page_start,999999), sc.key_signature""",(song_id,)).fetchall()

    def get_score(self,score_id:int):
        return self.conn.execute("""SELECT sc.*,a.song_id,a.name arrangement FROM scores sc JOIN arrangements a ON a.id=sc.arrangement_id WHERE sc.id=?""",(score_id,)).fetchone()

    def save_score(self,song_id:int,data:dict,score_id:int|None=None)->int:
        arr_id=self.ensure_arrangement(song_id,data.get("arrangement") or "Original")
        def intval(v):
            s=str(v or "").strip(); return int(s) if s.isdigit() else None
        def floatval(v):
            try:return float(v) if str(v or "").strip() else None
            except ValueError:return None
        vals={
            "arrangement_id":arr_id,
            "key_signature":str(data.get("key_signature") or "").strip(),
            "page_start":intval(data.get("page_start")),
            "page_end":intval(data.get("page_end")) or intval(data.get("page_start")),
            "source_pdf":str(data.get("source_pdf") or ""),
            "file_path":str(data.get("file_path") or ""),
            "ocr_title_raw":str(data.get("ocr_title_raw") or ""),
            "ocr_title_corrected":str(data.get("ocr_title_corrected") or ""),
            "ocr_confidence":floatval(data.get("ocr_confidence")),
            "review_status":str(data.get("review_status") or "미검수"),
            "notes":str(data.get("notes") or ""),
        }
        fields=list(vals)
        if score_id:
            assigns=",".join(f"{k}=?" for k in fields)
            self.conn.execute(f"UPDATE scores SET {assigns} WHERE id=?",[vals[k] for k in fields]+[score_id]); self.conn.commit(); return score_id
        cur=self.conn.execute(f"INSERT INTO scores({','.join(fields)}) VALUES({','.join('?' for _ in fields)})",[vals[k] for k in fields]); self.conn.commit(); return int(cur.lastrowid)

    def delete_score(self,score_id:int):
        self.conn.execute("DELETE FROM scores WHERE id=?",(score_id,)); self.conn.commit()

    def import_ocr_csv(self,csv_path:str|Path)->tuple[int,int,int]:
        new_songs=new_scores=skipped=0
        with open(csv_path,"r",encoding="utf-8-sig",newline="") as f:
            for row in csv.DictReader(f):
                title=(row.get("title") or row.get("corrected_title") or "").strip()
                raw=(row.get("raw_title") or row.get("ocr_title_raw") or title).strip()
                if not title: skipped+=1; continue
                song=self.conn.execute("SELECT id FROM songs WHERE title=?",(title,)).fetchone()
                if song: song_id=int(song["id"])
                else:
                    song_id=self.save_song({"title":title,"review_status":"OCR초안"}); new_songs+=1
                page=(row.get("page") or "").strip()
                p=int(page) if page.isdigit() else None
                conf=(row.get("confidence") or "").strip()
                review=str(row.get("review_required") or "").lower() in {"true","1","yes"}
                # 같은 곡이어도 페이지가 다르면 별도 Score Variant로 보존한다.
                exists=self.conn.execute("""SELECT 1 FROM scores sc JOIN arrangements a ON a.id=sc.arrangement_id
                    WHERE a.song_id=? AND sc.page_start IS ? AND sc.ocr_title_raw=?""",(song_id,p,raw)).fetchone()
                if exists: skipped+=1; continue
                self.save_score(song_id,{"arrangement":"Original","page_start":p,"page_end":p,"ocr_title_raw":raw,
                    "ocr_title_corrected":title,"ocr_confidence":conf,"review_status":"검수필요" if review else "OCR완료",
                    "notes":"OCR 후보: "+(row.get("candidates") or "")})
                new_scores+=1
        return new_songs,new_scores,skipped

    def export_csv(self,csv_path:str|Path):
        rows=self.conn.execute("""SELECT s.wgid,s.title,s.original_title,s.bpm,s.meter,s.category,s.themes,s.bible,s.flow,s.mood,s.difficulty,
            s.review_status,a.name arrangement,sc.key_signature,sc.page_start,sc.page_end,sc.source_pdf,sc.file_path,sc.ocr_title_raw,
            sc.ocr_title_corrected,sc.ocr_confidence,sc.review_status score_status
            FROM songs s LEFT JOIN arrangements a ON a.song_id=s.id LEFT JOIN scores sc ON sc.arrangement_id=a.id ORDER BY s.wgid,sc.page_start""").fetchall()
        fields=list(rows[0].keys()) if rows else ["wgid","title","arrangement","key_signature","page_start"]
        with open(csv_path,"w",encoding="utf-8-sig",newline="") as f:
            w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); [w.writerow(dict(r)) for r in rows]

    # ----- Songbook collections -----
    def create_collection(self, name:str, description:str="", filters:dict|None=None)->int:
        cur=self.conn.execute("INSERT INTO collections(name,description,filter_json) VALUES(?,?,?)",
            (name.strip(), description, json.dumps(filters or {}, ensure_ascii=False)))
        self.conn.commit(); return int(cur.lastrowid)

    def update_collection(self, collection_id:int, name:str, description:str="", filters:dict|None=None):
        self.conn.execute("UPDATE collections SET name=?,description=?,filter_json=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (name.strip(), description, json.dumps(filters or {}, ensure_ascii=False), collection_id)); self.conn.commit()

    def list_collections(self):
        return self.conn.execute("SELECT * FROM collections ORDER BY updated_at DESC,id DESC").fetchall()

    def get_collection(self, collection_id:int):
        return self.conn.execute("SELECT * FROM collections WHERE id=?",(collection_id,)).fetchone()

    def delete_collection(self, collection_id:int):
        self.conn.execute("DELETE FROM collections WHERE id=?",(collection_id,)); self.conn.commit()

    @staticmethod
    def _terms(value:str):
        return [x.strip() for x in str(value or '').replace(';',',').split(',') if x.strip()]

    def collection_candidates(self, *, query:str="", category:str="", themes:str="", mood:str="", key_signature:str="", flow:str="", max_difficulty:str=""):
        clauses=[]; params=[]
        if query.strip():
            like=f"%{query.strip()}%"; clauses.append("(s.title LIKE ? OR s.original_title LIKE ? OR s.bible LIKE ?)"); params += [like,like,like]
        for column,value in (("s.category",category),("s.themes",themes),("s.mood",mood),("s.flow",flow)):
            terms=self._terms(value)
            if terms:
                sub=[]
                for term in terms:
                    sub.append(f"{column} LIKE ?"); params.append(f"%{term}%")
                clauses.append("("+" OR ".join(sub)+")")
        keys=self._terms(key_signature)
        if keys:
            clauses.append("("+" OR ".join("sc.key_signature = ?" for _ in keys)+")"); params += keys
        d=str(max_difficulty or '').strip()
        if d.isdigit():
            clauses.append("(s.difficulty IS NULL OR s.difficulty <= ?)"); params.append(int(d))
        where="WHERE "+" AND ".join(clauses) if clauses else ""
        sql=f"""SELECT sc.id score_id,s.id song_id,s.wgid,s.title,s.category,s.themes,s.mood,s.flow,s.difficulty,
            a.name arrangement,sc.key_signature,sc.page_start,sc.page_end,sc.source_pdf,sc.file_path,sc.review_status score_status
            FROM scores sc JOIN arrangements a ON a.id=sc.arrangement_id JOIN songs s ON s.id=a.song_id
            {where} ORDER BY s.title COLLATE NOCASE,a.name,sc.key_signature,sc.page_start"""
        return self.conn.execute(sql, params).fetchall()

    def add_score_to_collection(self, collection_id:int, score_id:int):
        row=self.conn.execute("SELECT a.song_id FROM scores sc JOIN arrangements a ON a.id=sc.arrangement_id WHERE sc.id=?",(score_id,)).fetchone()
        if not row: raise ValueError("악보 버전을 찾을 수 없습니다.")
        exists=self.conn.execute("SELECT 1 FROM collection_items WHERE collection_id=? AND score_id=?",(collection_id,score_id)).fetchone()
        if exists:return
        pos=self.conn.execute("SELECT COALESCE(MAX(position),0)+1 p FROM collection_items WHERE collection_id=?",(collection_id,)).fetchone()["p"]
        self.conn.execute("INSERT INTO collection_items(collection_id,song_id,score_id,position) VALUES(?,?,?,?)",(collection_id,row["song_id"],score_id,pos)); self.conn.commit()

    def get_collection_items(self, collection_id:int):
        sql="""SELECT ci.*,s.wgid,s.title,a.name arrangement,sc.key_signature,sc.page_start,sc.page_end,sc.source_pdf,sc.file_path
            FROM collection_items ci JOIN songs s ON s.id=ci.song_id JOIN scores sc ON sc.id=ci.score_id JOIN arrangements a ON a.id=sc.arrangement_id
            WHERE ci.collection_id=? ORDER BY ci.position,ci.id"""
        return self.conn.execute(sql,(collection_id,)).fetchall()

    def remove_collection_item(self, item_id:int):
        row=self.conn.execute("SELECT collection_id FROM collection_items WHERE id=?",(item_id,)).fetchone()
        if not row:return
        cid=row["collection_id"]
        self.conn.execute("DELETE FROM collection_items WHERE id=?",(item_id,)); self._renumber_collection(cid); self.conn.commit()

    def _renumber_collection(self, collection_id:int):
        rows=self.conn.execute("SELECT id FROM collection_items WHERE collection_id=? ORDER BY position,id",(collection_id,)).fetchall()
        for i,r in enumerate(rows,1):
            self.conn.execute("UPDATE collection_items SET position=? WHERE id=?",(i,r["id"]))

    def move_collection_item(self, item_id:int, delta:int):
        row=self.conn.execute("SELECT collection_id,position FROM collection_items WHERE id=?",(item_id,)).fetchone()
        if not row:return
        cid,pos=int(row["collection_id"]),int(row["position"]); target=pos+delta
        other=self.conn.execute("SELECT id FROM collection_items WHERE collection_id=? AND position=?",(cid,target)).fetchone()
        if not other:return
        self.conn.execute("UPDATE collection_items SET position=-1 WHERE id=?",(item_id,))
        self.conn.execute("UPDATE collection_items SET position=? WHERE id=?",(pos,other["id"]))
        self.conn.execute("UPDATE collection_items SET position=? WHERE id=?",(target,item_id)); self.conn.commit()

    def create_setlist(self,name:str,service_date:str="",scripture:str="",notes:str="")->int:
        cur=self.conn.execute("INSERT INTO setlists(name,service_date,scripture,notes) VALUES(?,?,?,?)",(name,service_date,scripture,notes)); self.conn.commit(); return int(cur.lastrowid)
    def list_setlists(self): return self.conn.execute("SELECT * FROM setlists ORDER BY service_date DESC,id DESC").fetchall()
    def add_song_to_setlist(self,setlist_id:int,song_id:int,score_id:int|None=None,selected_key:str=""):
        row=self.conn.execute("SELECT COALESCE(MAX(position),0)+1 p FROM setlist_items WHERE setlist_id=?",(setlist_id,)).fetchone()
        self.conn.execute("INSERT INTO setlist_items(setlist_id,song_id,score_id,position,selected_key) VALUES(?,?,?,?,?)",(setlist_id,song_id,score_id,row["p"],selected_key)); self.conn.commit()
    def get_setlist_items(self,setlist_id:int):
        return self.conn.execute("""SELECT si.*,s.title,s.wgid,sc.key_signature score_key FROM setlist_items si JOIN songs s ON s.id=si.song_id LEFT JOIN scores sc ON sc.id=si.score_id
            WHERE si.setlist_id=? ORDER BY si.position""",(setlist_id,)).fetchall()
