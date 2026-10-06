
from __future__ import annotations
import os, threading, traceback
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from .pdf_importer import import_pdf_to_ocr

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Worship Guide 1.0.2")
        self.geometry("900x600")

        self.pdf = tk.StringVar()
        self.work = tk.StringVar(value=str(Path("data") / "wg_work"))
        self.start = tk.StringVar(value="1")
        self.end = tk.StringVar(value="5")
        self.status = tk.StringVar(value="PDF를 선택하세요.")
        self.progress = tk.DoubleVar(value=0)
        self._build()

    def _build(self):
        f = ttk.Frame(self, padding=18)
        f.pack(fill="both", expand=True)
        ttk.Label(f, text="Worship Guide", font=("Segoe UI", 22, "bold")).pack(anchor="w")
        ttk.Label(f, text="PDF 선택 → 페이지 추출 → OCR까지 자동 실행합니다.").pack(anchor="w", pady=(0, 14))

        r = ttk.Frame(f); r.pack(fill="x")
        ttk.Entry(r, textvariable=self.pdf).pack(side="left", fill="x", expand=True)
        ttk.Button(r, text="PDF 선택", command=self.choose_pdf).pack(side="left", padx=8)

        r2 = ttk.Frame(f); r2.pack(fill="x", pady=10)
        ttk.Label(r2, text="시작").pack(side="left")
        ttk.Entry(r2, width=7, textvariable=self.start).pack(side="left", padx=5)
        ttk.Label(r2, text="끝").pack(side="left")
        ttk.Entry(r2, width=7, textvariable=self.end).pack(side="left", padx=5)

        r3 = ttk.Frame(f); r3.pack(fill="x")
        ttk.Entry(r3, textvariable=self.work).pack(side="left", fill="x", expand=True)
        ttk.Button(r3, text="작업 폴더", command=self.choose_work).pack(side="left", padx=8)

        r4 = ttk.Frame(f); r4.pack(fill="x", pady=14)
        self.go = ttk.Button(r4, text="분석 시작", command=self.start_run)
        self.go.pack(side="left")
        ttk.Button(r4, text="결과 폴더 열기", command=self.open_result).pack(side="left", padx=8)

        ttk.Progressbar(f, maximum=100, variable=self.progress).pack(fill="x")
        ttk.Label(f, textvariable=self.status).pack(anchor="w", pady=6)

        self.log = tk.Text(f, height=18, wrap="word")
        self.log.pack(fill="both", expand=True)

    def choose_pdf(self):
        p = filedialog.askopenfilename(filetypes=[("PDF", "*.pdf")])
        if p: self.pdf.set(p)

    def choose_work(self):
        p = filedialog.askdirectory()
        if p: self.work.set(p)

    def open_result(self):
        p = Path(self.work.get()).resolve()
        p.mkdir(parents=True, exist_ok=True)
        os.startfile(str(p))

    def start_run(self):
        if not self.pdf.get():
            messagebox.showwarning("PDF 필요", "먼저 PDF를 선택하세요.")
            return
        self.go.config(state="disabled")
        threading.Thread(target=self.worker, daemon=True).start()

    def worker(self):
        try:
            self.after(0, self.progress.set, 10)
            self.after(0, self.status.set, "분석 중...")
            self.after(0, self.log.insert, "end", f"PDF: {self.pdf.get()}\n")
            result = import_pdf_to_ocr(
                self.pdf.get(),
                self.work.get(),
                start_page=int(self.start.get() or 1),
                end_page=int(self.end.get()) if self.end.get().strip() else None,
                engine="easyocr",
            )
            self.after(0, self.progress.set, 100)
            self.after(0, self.status.set, f"완료: {result.page_count}페이지")
            self.after(0, self.log.insert, "end", f"OCR 결과: {result.ocr_csv}\n")
            self.after(0, messagebox.showinfo, "완료", "분석이 완료되었습니다.")
        except Exception as e:
            self.after(0, self.log.insert, "end", traceback.format_exc() + "\n")
            self.after(0, messagebox.showerror, "오류", str(e))
        finally:
            self.after(0, self.go.config, {"state": "normal"})

def main():
    App().mainloop()

if __name__ == "__main__":
    main()
