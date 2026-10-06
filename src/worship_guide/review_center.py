
from __future__ import annotations
import csv, os
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk

from .ocr_titles import create_ocr_backend
from .key_ocr import EasyOCRKeyDetector

from .wgdb_v2 import (
    connect, get_or_create_song, get_or_create_arrangement,
    add_score_variant, add_review_event
)

KEYS = ["", "C", "Db", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B", "Cm", "Dm", "Em", "Fm", "Gm", "Am", "Bm"]

class ReviewCenter(tk.Toplevel):
    def __init__(self, master=None, *, ocr_csv=None, pages_dir=None, db_path=None, source_pdf=None):
        super().__init__(master)
        self.title("Worship Guide Review Center")
        self.geometry("1180x760")
        self.minsize(1000, 680)

        self.db_path = Path(db_path or "data/wgdb.sqlite3")
        self.conn = connect(self.db_path)
        self.ocr_csv = Path(ocr_csv) if ocr_csv else None
        self.pages_dir = Path(pages_dir) if pages_dir else None
        self.source_pdf = str(source_pdf or "")
        self.rows = []
        self.index = 0
        self.photo = None
        self._key_detector = None
        self.key_conf_var = tk.StringVar(value='')

        self.title_var = tk.StringVar()
        self.ocr_var = tk.StringVar()
        self.conf_var = tk.StringVar()
        self.key_var = tk.StringVar()
        self.arr_var = tk.StringVar(value="Original")
        self.page_var = tk.StringVar()
        self.counter_var = tk.StringVar()

        self._build()
        if self.ocr_csv:
            self.load_csv(self.ocr_csv, self.pages_dir)

    def _build(self):
        outer = ttk.Frame(self, padding=10)
        outer.pack(fill="both", expand=True)

        top = ttk.Frame(outer)
        top.pack(fill="x")
        ttk.Label(top, textvariable=self.counter_var, font=("Segoe UI", 12, "bold")).pack(side="left")
        ttk.Button(top, text="OCR 결과 열기", command=self._choose_csv).pack(side="right")

        body = ttk.Panedwindow(outer, orient="horizontal")
        body.pack(fill="both", expand=True, pady=8)

        left = ttk.Frame(body)
        right = ttk.Frame(body, padding=(12,0,0,0))
        body.add(left, weight=3)
        body.add(right, weight=2)

        self.canvas = tk.Canvas(left, bg="#202020", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda e: self._show_image())

        ttk.Label(right, text="OCR 제목").pack(anchor="w")
        ttk.Label(right, textvariable=self.ocr_var, font=("Segoe UI", 12)).pack(anchor="w", pady=(2,10))

        ttk.Label(right, text="OCR 신뢰도").pack(anchor="w")
        ttk.Label(right, textvariable=self.conf_var).pack(anchor="w", pady=(2,10))

        ttk.Label(right, text="확정 제목").pack(anchor="w")
        ttk.Entry(right, textvariable=self.title_var, font=("Segoe UI", 13)).pack(fill="x", pady=(2,10))

        g = ttk.Frame(right); g.pack(fill="x")
        ttk.Label(g, text="Key (자동 후보)").grid(row=0,column=0,sticky="w")
        ttk.Combobox(g, textvariable=self.key_var, values=KEYS, width=10, state="readonly").grid(row=1,column=0,sticky="w", pady=(2,2))
        ttk.Label(g, textvariable=self.key_conf_var).grid(row=2,column=0,sticky="w", pady=(0,10))
        ttk.Label(g, text="Arrangement").grid(row=0,column=1,sticky="w", padx=(14,0))
        ttk.Entry(g, textvariable=self.arr_var, width=18).grid(row=1,column=1,sticky="w", padx=(14,0), pady=(2,10))
        ttk.Label(g, text="Page").grid(row=0,column=2,sticky="w", padx=(14,0))
        ttk.Label(g, textvariable=self.page_var).grid(row=1,column=2,sticky="w", padx=(14,0), pady=(2,10))

        self.same_song_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            right,
            text="같은 제목이면 기존 Song에 연결 (Key별 Score Variant로 저장)",
            variable=self.same_song_var
        ).pack(anchor="w", pady=(2,12))

        buttons = ttk.Frame(right); buttons.pack(fill="x", pady=10)
        ttk.Button(buttons, text="◀ 이전", command=self.prev).pack(side="left")
        ttk.Button(buttons, text="승인 (Enter)", command=self.approve).pack(side="left", padx=8)
        ttk.Button(buttons, text="다음 ▶", command=self.next).pack(side="left")

        ttk.Separator(right).pack(fill="x", pady=10)
        ttk.Label(right, text="검수 원칙").pack(anchor="w")
        ttk.Label(
            right,
            text="• 같은 곡의 다른 Key 페이지는 같은 Song 아래 Score Variant로 저장\n"
                 "• OCR 제목은 원문으로 보존\n"
                 "• 확정 제목과 Key만 사람이 승인\n"
                 "• 이후 Theme/Mood/Scripture는 Song 단위로 추가",
            justify="left"
        ).pack(anchor="w", pady=5)

        self.bind("<Return>", lambda e: self.approve())
        self.bind("<Left>", lambda e: self.prev())
        self.bind("<Right>", lambda e: self.next())

    def _choose_csv(self):
        p = filedialog.askopenfilename(
            title="titles_ocr.csv 선택",
            filetypes=[("CSV", "*.csv")]
        )
        if not p:
            return
        # Standard folder structure is inferred automatically.
        self.load_csv(Path(p), None)

    def load_csv(self, csv_path: Path, pages_dir: Path | None):
        self.ocr_csv = Path(csv_path)

        # If the page-image folder was not supplied, infer it from the standard
        # work-folder structure:
        #   <work>/ocr_titles/titles_ocr.csv
        #   <work>/pdf_work/pages/
        if pages_dir is None:
            inferred = self.ocr_csv.parent.parent / "pdf_work" / "pages"
            if inferred.exists():
                pages_dir = inferred
        self.pages_dir = Path(pages_dir) if pages_dir else None

        if not self.ocr_csv.exists():
            messagebox.showerror("OCR 결과 없음", f"OCR CSV를 찾지 못했습니다:\n{self.ocr_csv}")
            self.rows = []
            self._load_current()
            return

        with self.ocr_csv.open("r", encoding="utf-8-sig", newline="") as f:
            self.rows = list(csv.DictReader(f))

        if not self.rows:
            messagebox.showwarning(
                "OCR 결과 비어 있음",
                f"CSV 파일은 있지만 데이터 행이 없습니다.\n\n{self.ocr_csv}\n\n"
                "메인 화면에서 '분석 시작'을 다시 실행한 뒤 '검수 시작'을 눌러 주세요."
            )

        self.index = 0
        self._load_current()

    def _page_number(self, row):
        try:
            return int(row.get("page") or row.get("page_number") or self.index + 1)
        except Exception:
            return self.index + 1

    def _image_path(self, row):
        if row.get("image"):
            p = Path(row["image"])
            if p.exists():
                return p
        if self.pages_dir:
            page = self._page_number(row)
            for name in [f"page_{page:04}.png", f"page_{page:03}.png", f"page_{page}.png"]:
                p = self.pages_dir / name
                if p.exists():
                    return p
        return None

    def _load_current(self):
        if not self.rows:
            self.counter_var.set("검수 데이터 없음 — 메인 화면에서 분석을 먼저 실행하세요")
            self.ocr_var.set("(없음)")
            self.conf_var.set("")
            self.title_var.set("")
            self.key_var.set("")
            self.page_var.set("")
            self.canvas.delete("all")
            self.canvas.create_text(
                30, 30, anchor="nw", fill="white",
                text="OCR 결과가 로드되지 않았습니다.\n\n"
                     "1) 메인 화면에서 '분석 시작'\n"
                     "2) 완료 후 '검수 시작'\n\n"
                     "또는 오른쪽 위 'OCR 결과 열기'에서\n"
                     "data\\wg_work\\ocr_titles\\titles_ocr.csv 를 선택하세요.",
                font=("Segoe UI", 12)
            )
            return
        row = self.rows[self.index]
        raw = (row.get("title") or "").strip()
        corrected = (row.get("corrected_title") or row.get("matched_title") or raw).strip()
        self.ocr_var.set(raw or "(없음)")
        self.title_var.set(corrected)
        conf = row.get("confidence") or ""
        self.conf_var.set(conf)
        self.page_var.set(str(self._page_number(row)))
        self.counter_var.set(f"{self.index+1} / {len(self.rows)}")
        self._show_image()
        self._detect_key_candidate()

    def _show_image(self):
        self.canvas.delete("all")
        if not self.rows:
            return
        p = self._image_path(self.rows[self.index])
        if not p or not p.exists():
            self.canvas.create_text(20,20,anchor="nw",fill="white",text="악보 이미지를 찾지 못했습니다.")
            return
        try:
            im = Image.open(p).convert("RGB")
            cw = max(self.canvas.winfo_width()-20, 200)
            ch = max(self.canvas.winfo_height()-20, 200)
            scale = min(cw/im.width, ch/im.height)
            size = (max(1,int(im.width*scale)), max(1,int(im.height*scale)))
            im = im.resize(size)
            self.photo = ImageTk.PhotoImage(im)
            self.canvas.create_image(cw//2+10, ch//2+10, image=self.photo, anchor="center")
        except Exception as e:
            self.canvas.create_text(20,20,anchor="nw",fill="white",text=str(e))


def _detect_key_candidate(self):
    if not self.rows:
        return
    p = self._image_path(self.rows[self.index])
    if not p or not p.exists():
        self.key_conf_var.set("자동 인식 불가")
        return
    try:
        if self._key_detector is None:
            backend = create_ocr_backend("easyocr")
            reader = getattr(backend, "_reader", None)
            if reader is None:
                self.key_conf_var.set("자동 인식 불가")
                return
            self._key_detector = EasyOCRKeyDetector(reader)
        key, conf, _texts = self._key_detector.detect(p)
        if key:
            if key in KEYS:
                self.key_var.set(key)
            self.key_conf_var.set(f"후보 신뢰도 {conf:.2f} · 승인 전 확인")
        else:
            self.key_conf_var.set("Key 후보 없음")
    except Exception as e:
        self.key_conf_var.set("Key 자동 인식 실패")

    def approve(self):
        if not self.rows:
            return
        title = self.title_var.get().strip()
        if not title:
            messagebox.showwarning("제목 필요", "확정 제목을 입력하세요.")
            return
        row = self.rows[self.index]
        page = self._page_number(row)
        raw = (row.get("title") or "").strip()
        try:
            conf = float(row.get("confidence") or 0)
        except Exception:
            conf = None
        song_id, wgid = get_or_create_song(self.conn, title)
        arr_id = get_or_create_arrangement(self.conn, song_id, self.arr_var.get().strip() or "Original")
        image_path = str(self._image_path(row) or "")
        score_id = add_score_variant(
            self.conn,
            arrangement_id=arr_id,
            key_signature=self.key_var.get().strip() or None,
            source_document=self.source_pdf,
            page=page,
            image_path=image_path,
            raw_ocr_title=raw,
            confidence=conf,
        )
        add_review_event(self.conn, "score_variant", score_id, "title", raw, title, conf)
        self.conn.commit()
        self.next()

    def prev(self):
        if self.rows and self.index > 0:
            self.index -= 1
            self._load_current()

    def next(self):
        if not self.rows:
            return
        if self.index < len(self.rows)-1:
            self.index += 1
            self._load_current()
        else:
            messagebox.showinfo("검수 완료", "마지막 페이지까지 검수했습니다.")

def open_review_center(master=None, **kwargs):
    return ReviewCenter(master, **kwargs)
