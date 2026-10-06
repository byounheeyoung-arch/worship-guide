
from __future__ import annotations
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox

from .wgdb_v2 import connect

class DBEditorV2(tk.Toplevel):
    def __init__(self, master=None, db_path="data/wgdb.sqlite3"):
        super().__init__(master)
        self.title("Worship Guide DB Editor v2")
        self.geometry("1180x720")
        self.db_path = Path(db_path)
        self.conn = connect(self.db_path)

        self.search_var = tk.StringVar()
        self.title_var = tk.StringVar()
        self.original_var = tk.StringVar()
        self.bpm_var = tk.StringVar()
        self.meter_var = tk.StringVar()
        self.memo_var = tk.StringVar()

        self._build()
        self.refresh()

    def _build(self):
        outer = ttk.Frame(self, padding=10)
        outer.pack(fill="both", expand=True)

        top = ttk.Frame(outer); top.pack(fill="x")
        ttk.Label(top, text="검색").pack(side="left")
        e = ttk.Entry(top, textvariable=self.search_var)
        e.pack(side="left", fill="x", expand=True, padx=6)
        e.bind("<KeyRelease>", lambda _e: self.refresh())
        ttk.Button(top, text="새로고침", command=self.refresh).pack(side="left")

        body = ttk.Panedwindow(outer, orient="horizontal")
        body.pack(fill="both", expand=True, pady=8)

        left = ttk.Frame(body)
        right = ttk.Frame(body, padding=(12,0,0,0))
        body.add(left, weight=3); body.add(right, weight=4)

        self.tree = ttk.Treeview(left, columns=("wgid","title","keys","status"), show="headings")
        for col, title, width in [
            ("wgid","WGID",100),("title","곡명",250),("keys","악보 Key",180),("status","상태",100)
        ]:
            self.tree.heading(col, text=title)
            self.tree.column(col, width=width, anchor="w")
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", self._select_song)

        form = ttk.LabelFrame(right, text="곡 정보", padding=10)
        form.pack(fill="x")
        fields = [
            ("곡명", self.title_var),
            ("원제", self.original_var),
            ("BPM", self.bpm_var),
            ("박자", self.meter_var),
            ("메모", self.memo_var),
        ]
        for i,(label,var) in enumerate(fields):
            ttk.Label(form, text=label).grid(row=i,column=0,sticky="w",pady=4)
            ttk.Entry(form, textvariable=var).grid(row=i,column=1,sticky="ew",pady=4)
        form.columnconfigure(1, weight=1)
        ttk.Button(form, text="곡 저장", command=self.save_song).grid(row=len(fields),column=1,sticky="e",pady=8)

        scores = ttk.LabelFrame(right, text="악보 버전", padding=8)
        scores.pack(fill="both", expand=True, pady=(10,0))
        self.scores = ttk.Treeview(
            scores,
            columns=("arrangement","key","page","ocr","confidence","status"),
            show="headings"
        )
        for col, title, width in [
            ("arrangement","Arrangement",120),("key","Key",70),("page","Page",80),
            ("ocr","OCR 제목",230),("confidence","OCR 신뢰도",90),("status","상태",90)
        ]:
            self.scores.heading(col, text=title)
            self.scores.column(col, width=width, anchor="w")
        self.scores.pack(fill="both", expand=True)

        ttk.Label(
            right,
            text="이 Editor는 v2 DB 스키마(Song → Arrangement → Score Variant)를 사용합니다.",
        ).pack(anchor="w", pady=6)

    def refresh(self):
        q = self.search_var.get().strip()
        for x in self.tree.get_children():
            self.tree.delete(x)
        sql = """
        SELECT s.id, s.wgid, s.title, s.review_status,
               GROUP_CONCAT(DISTINCT sv.key_signature) AS keys
        FROM songs s
        LEFT JOIN arrangements a ON a.song_id=s.id
        LEFT JOIN score_variants sv ON sv.arrangement_id=a.id
        """
        params = []
        if q:
            sql += " WHERE s.title LIKE ? OR s.wgid LIKE ?"
            params = [f"%{q}%", f"%{q}%"]
        sql += " GROUP BY s.id ORDER BY s.title"
        for r in self.conn.execute(sql, params):
            self.tree.insert("", "end", iid=str(r["id"]), values=(
                r["wgid"], r["title"], r["keys"] or "", r["review_status"]
            ))

    def _select_song(self, _event=None):
        sel = self.tree.selection()
        if not sel:
            return
        song_id = int(sel[0])
        r = self.conn.execute("SELECT * FROM songs WHERE id=?", (song_id,)).fetchone()
        if not r:
            return
        self.title_var.set(r["title"] or "")
        self.original_var.set(r["original_title"] or "")
        self.bpm_var.set("" if r["bpm"] is None else str(r["bpm"]))
        self.meter_var.set(r["meter"] or "")
        self.memo_var.set(r["memo"] or "")

        for x in self.scores.get_children():
            self.scores.delete(x)
        rows = self.conn.execute("""
            SELECT sv.*, a.name AS arrangement
            FROM score_variants sv
            JOIN arrangements a ON a.id=sv.arrangement_id
            WHERE a.song_id=?
            ORDER BY sv.start_page
        """, (song_id,))
        for sv in rows:
            page = str(sv["start_page"] or "")
            if sv["end_page"] and sv["end_page"] != sv["start_page"]:
                page += f"-{sv['end_page']}"
            conf = "" if sv["ocr_confidence"] is None else f"{sv['ocr_confidence']:.3f}"
            self.scores.insert("", "end", values=(
                sv["arrangement"], sv["key_signature"] or "", page,
                sv["raw_ocr_title"] or "", conf, sv["review_status"]
            ))

    def save_song(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("곡 선택", "곡을 먼저 선택하세요.")
            return
        song_id = int(sel[0])
        bpm = None
        if self.bpm_var.get().strip():
            try:
                bpm = int(self.bpm_var.get())
            except ValueError:
                messagebox.showwarning("BPM", "BPM은 숫자로 입력하세요.")
                return
        self.conn.execute("""
            UPDATE songs SET title=?, original_title=?, bpm=?, meter=?, memo=?,
                             updated_at=CURRENT_TIMESTAMP
            WHERE id=?
        """, (
            self.title_var.get().strip(),
            self.original_var.get().strip() or None,
            bpm,
            self.meter_var.get().strip() or None,
            self.memo_var.get().strip() or None,
            song_id
        ))
        self.conn.commit()
        self.refresh()
        messagebox.showinfo("저장", "곡 정보를 저장했습니다.")

def open_editor(master=None, db_path="data/wgdb.sqlite3"):
    return DBEditorV2(master, db_path=db_path)

def main():
    root = tk.Tk()
    root.withdraw()
    ed = DBEditorV2(root)
    ed.protocol("WM_DELETE_WINDOW", root.destroy)
    root.mainloop()

if __name__ == "__main__":
    main()
