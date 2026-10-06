
from __future__ import annotations
import threading, traceback, os, csv
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from .pdf_importer import import_pdf_to_ocr
from .review_center import ReviewCenter

class WorshipGuide2(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Worship Guide 2.0")
        self.geometry("980x660")
        self.minsize(860, 580)

        self.pdf = tk.StringVar()
        self.work = tk.StringVar(value=str(Path("data") / "wg_work"))
        self.db = tk.StringVar(value=str(Path("data") / "wgdb.sqlite3"))
        self.start = tk.StringVar(value="1")
        self.end = tk.StringVar(value="5")
        self.status = tk.StringVar(value="PDF를 선택하세요.")
        self.progress = tk.DoubleVar(value=0)
        self.last_result = None

        self._build()

    def _build(self):
        wrap = ttk.Frame(self, padding=18)
        wrap.pack(fill="both", expand=True)

        ttk.Label(wrap, text="Worship Guide", font=("Segoe UI", 24, "bold")).pack(anchor="w")
        ttk.Label(
            wrap,
            text="PDF 가져오기 → OCR → 악보 보면서 검수 → WGDB 저장",
            font=("Segoe UI", 11)
        ).pack(anchor="w", pady=(0,16))

        pdfbox = ttk.LabelFrame(wrap, text="악보 PDF", padding=10)
        pdfbox.pack(fill="x")
        ttk.Entry(pdfbox, textvariable=self.pdf).pack(side="left", fill="x", expand=True)
        ttk.Button(pdfbox, text="PDF 선택", command=self.choose_pdf).pack(side="left", padx=8)

        options = ttk.Frame(wrap)
        options.pack(fill="x", pady=10)
        ttk.Label(options, text="시작").pack(side="left")
        ttk.Entry(options, width=7, textvariable=self.start).pack(side="left", padx=5)
        ttk.Label(options, text="끝").pack(side="left")
        ttk.Entry(options, width=7, textvariable=self.end).pack(side="left", padx=5)
        ttk.Label(options, text="(처음에는 1~5 권장)").pack(side="left", padx=8)

        actions = ttk.Frame(wrap)
        actions.pack(fill="x", pady=6)
        self.run_btn = ttk.Button(actions, text="분석 시작", command=self.start_analysis)
        self.run_btn.pack(side="left")
        self.review_btn = ttk.Button(actions, text="검수 시작", command=self.open_review, state="disabled")
        self.review_btn.pack(side="left", padx=8)
        ttk.Button(actions, text="DB Editor", command=self.open_editor).pack(side="left", padx=8)
        ttk.Button(actions, text="결과 폴더", command=self.open_result).pack(side="left")

        ttk.Progressbar(wrap, maximum=100, variable=self.progress).pack(fill="x", pady=(12,4))
        ttk.Label(wrap, textvariable=self.status).pack(anchor="w")

        info = ttk.LabelFrame(wrap, text="이번 버전 핵심", padding=10)
        info.pack(fill="x", pady=10)
        ttk.Label(
            info,
            text="• 같은 곡의 여러 Key 페이지를 한 Song 아래 별도 Score Variant로 저장\n"
                 "• OCR 제목은 원문 그대로 보존하고, 검수 화면에서 사람이 확정\n"
                 "• Enter=승인, ←/→=이전/다음\n"
                 "• 승인 결과는 data\\wgdb.sqlite3 에 누적 저장",
            justify="left"
        ).pack(anchor="w")

        logbox = ttk.LabelFrame(wrap, text="로그", padding=8)
        logbox.pack(fill="both", expand=True)
        self.log = tk.Text(logbox, height=14, wrap="word")
        self.log.pack(fill="both", expand=True)

    def choose_pdf(self):
        p = filedialog.askopenfilename(filetypes=[("PDF", "*.pdf")])
        if p: self.pdf.set(p)

    def append(self, s):
        self.log.insert("end", s.rstrip()+"\n")
        self.log.see("end")

    def start_analysis(self):
        if not self.pdf.get():
            messagebox.showwarning("PDF 필요", "먼저 PDF를 선택하세요.")
            return
        self.run_btn.config(state="disabled")
        self.review_btn.config(state="disabled")
        threading.Thread(target=self.worker, daemon=True).start()

    def worker(self):
        try:
            self.after(0, self.progress.set, 10)
            self.after(0, self.status.set, "PDF 분석 중...")
            self.after(0, self.append, f"PDF: {self.pdf.get()}")
            result = import_pdf_to_ocr(
                self.pdf.get(),
                self.work.get(),
                start_page=int(self.start.get() or 1),
                end_page=int(self.end.get()) if self.end.get().strip() else None,
                engine="easyocr",
            )
            self.last_result = result
            self.after(0, self.progress.set, 100)
            self.after(0, self.status.set, f"완료: {result.page_count}페이지. 이제 검수를 시작하세요.")
            self.after(0, self.append, f"OCR 결과: {result.ocr_csv}")
            self.after(0, self.review_btn.config, {"state": "normal"})
        except Exception as e:
            self.after(0, self.append, traceback.format_exc())
            self.after(0, messagebox.showerror, "오류", str(e))
        finally:
            self.after(0, self.run_btn.config, {"state": "normal"})

    def open_review(self):
        work = Path(self.work.get())
        csv_path = work / "ocr_titles" / "titles_ocr.csv"
        pages = work / "pdf_work" / "pages"

        # Prefer the current on-disk result. This avoids a stale/empty
        # in-memory result after restarting or upgrading versions.
        if csv_path.exists():
            ReviewCenter(
                self,
                ocr_csv=csv_path,
                pages_dir=pages if pages.exists() else None,
                db_path=self.db.get(),
                source_pdf=self.pdf.get(),
            )
            return

        if self.last_result and Path(self.last_result.ocr_csv).exists():
            ReviewCenter(
                self,
                ocr_csv=self.last_result.ocr_csv,
                pages_dir=self.last_result.pages_dir,
                db_path=self.db.get(),
                source_pdf=self.pdf.get(),
            )
            return

        messagebox.showwarning(
            "분석 필요",
            "OCR 결과를 찾지 못했습니다.\n메인 화면에서 '분석 시작'을 먼저 실행하세요."
        )

    def open_editor(self):
        try:
            from .editor_v2 import open_editor
            open_editor(self, db_path=self.db.get())
        except Exception as e:
            messagebox.showerror("Editor 오류", str(e))

    def open_result(self):
        p = Path(self.work.get()).resolve()
        p.mkdir(parents=True, exist_ok=True)
        os.startfile(str(p))

def main():
    WorshipGuide2().mainloop()

if __name__ == "__main__":
    main()
