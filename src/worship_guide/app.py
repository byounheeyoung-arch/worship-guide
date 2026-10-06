"""One desktop entrypoint, shared storage, thread-safe background import."""

from __future__ import annotations
import argparse
import os
import subprocess
import sys
import threading
from queue import Queue, Empty
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from .db import WGDB
from .paths import adopt_legacy_database
from .pipeline import import_document, file_sha256
from .review_center import ReviewCenter
from .master_import import import_master_snapshot


class WorshipGuide(tk.Tk):
    def __init__(self, db_path=None):
        super().__init__()
        self.title("Worship Guide")
        self.geometry("1000x720")
        self.minsize(850, 620)
        self.db_path = Path(db_path) if db_path else adopt_legacy_database()
        self.db = WGDB(self.db_path)
        self.events = Queue()
        self.cancel = threading.Event()
        self.worker_thread = None
        self.closing = False
        self.pdf = tk.StringVar()
        self.start = tk.StringVar(value="1")
        self.end = tk.StringVar(value="20")
        self.engine = tk.StringVar(value="easyocr")
        self.status = tk.StringVar()
        self.progress = tk.DoubleVar()
        self.counts = tk.StringVar()
        self._poll_id = None
        self._build()
        self.refresh()
        self._poll_id = self.after(100, self.poll)
        self.protocol("WM_DELETE_WINDOW", self.close)

    def _build(self):
        root = ttk.Frame(self, padding=20)
        root.pack(fill="both", expand=True)
        ttk.Label(root, text="Worship Guide", font=("TkDefaultFont", 24, "bold")).pack(
            anchor="w"
        )
        ttk.Label(
            root, text="악보 가져오기 → OCR → 검수 → 곡·조성별 DB → 악보집·PDF"
        ).pack(anchor="w", pady=(4, 12))
        ttk.Label(root, textvariable=self.counts).pack(anchor="w", pady=5)
        box = ttk.LabelFrame(root, text="PDF / 악보 이미지", padding=12)
        box.pack(fill="x", pady=8)
        row = ttk.Frame(box)
        row.pack(fill="x")
        ttk.Entry(row, textvariable=self.pdf).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="파일 선택", command=self.choose).pack(side="left", padx=6)
        row = ttk.Frame(box)
        row.pack(fill="x", pady=10)
        for label, var in [("시작 페이지", self.start), ("끝 페이지", self.end)]:
            ttk.Label(row, text=label).pack(side="left")
            ttk.Entry(row, textvariable=var, width=8).pack(side="left", padx=(5, 15))
        ttk.Label(row, text="OCR 엔진").pack(side="left")
        ttk.Combobox(
            row,
            textvariable=self.engine,
            values=["easyocr", "tesseract"],
            state="readonly",
            width=12,
        ).pack(side="left", padx=5)
        ttk.Label(
            box,
            text="첫 검증은 최대 20페이지입니다. 전체 분석은 해당 원본의 E2E 통과 기록 후 열립니다.",
        ).pack(anchor="w")
        row = ttk.Frame(root)
        row.pack(fill="x", pady=10)
        self.run_btn = ttk.Button(
            row, text="분석 / 이어서 분석", command=self.start_analysis
        )
        self.run_btn.pack(side="left")
        ttk.Button(row, text="분석 중단", command=self.cancel.set).pack(
            side="left", padx=5
        )
        ttk.Button(row, text="검수센터", command=self.open_review).pack(
            side="left", padx=5
        )
        ttk.Button(row, text="곡 · 검색 · 악보집", command=self.open_editor).pack(
            side="left", padx=5
        )
        ttk.Button(row, text="마스터 자료 가져오기", command=self.import_master).pack(
            side="left", padx=5
        )
        ttk.Button(
            root, text="검수한 20페이지 E2E 검증", command=self.verify_twenty
        ).pack(anchor="w", pady=(0, 8))
        ttk.Progressbar(root, variable=self.progress, maximum=100).pack(fill="x")
        ttk.Label(root, textvariable=self.status, wraplength=900).pack(
            anchor="w", pady=6
        )
        self.log = tk.Text(root, height=13, wrap="word", state="disabled")
        self.log.pack(fill="both", expand=True, pady=8)
        bottom = ttk.Frame(root)
        bottom.pack(fill="x")
        ttk.Label(bottom, text=f"데이터: {self.db.path.parent}", wraplength=680).pack(
            side="left"
        )
        ttk.Button(bottom, text="데이터 폴더", command=self.open_data).pack(
            side="right"
        )

    def choose(self):
        path = filedialog.askopenfilename(
            parent=self,
            filetypes=[("악보", "*.pdf *.png *.jpg *.jpeg *.webp *.tif *.tiff")],
        )
        if path:
            self.pdf.set(path)

    def append(self, message):
        self.log.configure(state="normal")
        self.log.insert("end", message + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def refresh(self):
        songs = self.db.conn.execute("SELECT COUNT(*) FROM songs").fetchone()[0]
        scores = self.db.conn.execute("SELECT COUNT(*) FROM score_variants").fetchone()[
            0
        ]
        pending = self.db.conn.execute(
            "SELECT COUNT(*) FROM imported_pages WHERE state!='reviewed'"
        ).fetchone()[0]
        self.counts.set(f"등록 곡 {songs} · 악보 버전 {scores} · 검수 대기 {pending}")
        self.status.set(
            "파일을 선택하고 분석하세요. 재시작 후에도 검수센터에서 이어갈 수 있습니다."
        )

    def start_analysis(self):
        if self.worker_thread and self.worker_thread.is_alive():
            return
        try:
            path = Path(self.pdf.get())
            first = int(self.start.get())
            last = int(self.end.get()) if self.end.get().strip() else None
            if not path.is_file():
                raise ValueError("악보 PDF 또는 이미지를 선택하세요.")
        except Exception as exc:
            messagebox.showerror("분석 시작", str(exc), parent=self)
            return
        # All Tk variables are read on the main thread, then immutable values
        # and a thread-local database connection are handed to the worker.
        engine = self.engine.get()
        self.cancel.clear()
        self.run_btn.configure(state="disabled")
        self.progress.set(0)
        self.status.set("분석 중… 페이지별로 저장합니다.")
        self.append(f"분석: {path.name} · {first}~{last or '끝'}")

        def work():
            try:
                with WGDB(self.db.path) as db:
                    result = import_document(
                        db,
                        path,
                        start_page=first,
                        end_page=last,
                        engine=engine,
                        cancel=self.cancel,
                        progress=lambda item: self.events.put(("progress", item)),
                    )
                self.events.put(("complete", result))
            except Exception as exc:
                self.events.put(("error", str(exc)))

        self.worker_thread = threading.Thread(target=work, daemon=True)
        self.worker_thread.start()

    def poll(self):
        if self._poll_id:
            self.after_cancel(self._poll_id)
            self._poll_id = None
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == "progress":
                    self.progress.set(
                        100 * (value["completed"] + value["failed"]) / value["total"]
                    )
                    self.status.set(
                        f"p.{value['page']} · {value['completed']}/{value['total']} · 실패 {value['failed']}"
                    )
                else:
                    self.refresh()
                    self.run_btn.configure(state="normal")
                    if kind == "complete":
                        text = f"분석 {value.state} · {value.completed_pages}페이지 · 기존 결과 재사용 {value.reused_pages} · 실패 {value.failed_pages}"
                    elif kind == "validation":
                        text = "20페이지 E2E 통과 · 이 원본의 전체 분석을 시작할 수 있습니다."
                    else:
                        text = "분석 실패: " + value
                    self.status.set(text)
                    self.append(text)
        except Empty:
            pass
        if self.closing and (
            not self.worker_thread or not self.worker_thread.is_alive()
        ):
            for window in list(self.winfo_children()):
                if hasattr(window, "close") and isinstance(window, tk.Toplevel):
                    window.close()
            self.db.close()
            self.destroy()
            return
        self._poll_id = self.after(100, self.poll)

    def verify_twenty(self):
        if self.worker_thread and self.worker_thread.is_alive():
            return
        path = Path(self.pdf.get())
        if path.is_file():
            source = self.db.conn.execute(
                "SELECT id FROM source_documents WHERE sha256=?", (file_sha256(path),)
            ).fetchone()
        else:
            sources = self.db.conn.execute("SELECT id FROM source_documents").fetchall()
            source = sources[0] if len(sources) == 1 else None
        if not source:
            messagebox.showinfo(
                "20페이지 검증", "검수한 원본 PDF를 선택하세요.", parent=self
            )
            return
        source_id = source[0]
        self.run_btn.configure(state="disabled")
        self.status.set("재시작·수정 이력·조성·PDF 순서를 검증합니다…")

        def work():
            try:
                from .acceptance import verify_twenty

                with WGDB(self.db.path) as db:
                    result = verify_twenty(db, source_id)
                self.events.put(("validation", result))
            except Exception as exc:
                self.events.put(("error", str(exc)))

        self.worker_thread = threading.Thread(target=work, daemon=True)
        self.worker_thread.start()

    def open_review(self):
        return ReviewCenter(self, db_path=self.db.path, on_change=self.refresh)

    def open_editor(self):
        from .editor import Editor

        return Editor(self, db_path=self.db.path, on_change=self.refresh)

    def import_master(self):
        path = filedialog.askopenfilename(
            parent=self, filetypes=[("마스터 스냅샷", "*.json")]
        )
        if not path:
            return
        try:
            result = import_master_snapshot(self.db, path)
            self.refresh()
            self.append(f"마스터 가져오기: {result}")
        except Exception as exc:
            messagebox.showerror("마스터 가져오기", str(exc), parent=self)

    def open_data(self):
        path = str(self.db.path.parent)
        if sys.platform == "win32":
            os.startfile(path)
        else:
            subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", path])

    def close(self):
        self.closing = True
        self.cancel.set()
        self.status.set("현재 페이지를 저장한 후 종료합니다…")


def main():
    parser = argparse.ArgumentParser(description="Worship Guide Desktop")
    parser.add_argument("--db", type=Path, help="기존 또는 사용자 지정 DB")
    args = parser.parse_args()
    WorshipGuide(args.db).mainloop()


if __name__ == "__main__":
    main()
