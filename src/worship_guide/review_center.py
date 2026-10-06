from __future__ import annotations
import json
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageTk
from .db import WGDB
from .key_ocr import KEYS


class ReviewCenter(tk.Toplevel):
    """Review persisted pages, including after restart; never run OCR on UI thread."""

    def __init__(
        self, master=None, *, db_path=None, source_id=None, on_change=None, **legacy
    ):
        super().__init__(master)
        self.title("Worship Guide · 악보 검수")
        self.geometry("1200x780")
        self.minsize(1000, 650)
        self.db = WGDB(db_path)
        self.source_id = source_id
        self.on_change = on_change
        self.index = 0
        self.rows = []
        self.photo = None
        self._closed = False
        self.include_reviewed = tk.BooleanVar(value=False)
        self.title_var = tk.StringVar()
        self.key_var = tk.StringVar()
        self.arr_var = tk.StringVar(value="Original")
        self.counter_var = tk.StringVar()
        self.raw_var = tk.StringVar()
        self.key_hint = tk.StringVar()
        self.choice_var = tk.StringVar()
        self.suggestions = []
        self.explicit_song_id = None
        self.new_song_var = tk.BooleanVar(value=False)
        self._build()
        self.reload()
        self.protocol("WM_DELETE_WINDOW", self.close)

    def _build(self):
        wrap = ttk.Frame(self, padding=12)
        wrap.pack(fill="both", expand=True)
        top = ttk.Frame(wrap)
        top.pack(fill="x")
        ttk.Label(
            top, textvariable=self.counter_var, font=("TkDefaultFont", 12, "bold")
        ).pack(side="left")
        ttk.Checkbutton(
            top,
            text="검수 완료 페이지 포함",
            variable=self.include_reviewed,
            command=self.reload,
        ).pack(side="right")
        body = ttk.Panedwindow(wrap, orient="horizontal")
        body.pack(fill="both", expand=True, pady=10)
        left = ttk.Frame(body)
        right = ttk.Frame(body, padding=(12, 0, 0, 0))
        body.add(left, weight=3)
        body.add(right, weight=2)
        self.canvas = tk.Canvas(left, bg="#20252d", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda _e: self.show_image())
        ttk.Label(right, text="OCR 원문 (보존)").pack(anchor="w")
        ttk.Label(right, textvariable=self.raw_var, wraplength=390).pack(
            anchor="w", pady=(3, 12)
        )
        ttk.Label(right, text="확정 제목").pack(anchor="w")
        self.title_entry = ttk.Entry(
            right, textvariable=self.title_var, font=("TkDefaultFont", 13)
        )
        self.title_entry.pack(fill="x", pady=(3, 10))
        ttk.Label(right, text="추천 제목 · 기존 검수 수정 이력 포함").pack(anchor="w")
        self.choice = ttk.Combobox(
            right, textvariable=self.choice_var, state="readonly"
        )
        self.choice.pack(fill="x", pady=4)
        ttk.Button(right, text="추천 제목 적용", command=self.apply_suggestion).pack(
            anchor="w", pady=(0, 10)
        )
        ttk.Checkbutton(
            right, text="같은 이름의 다른 곡으로 새 등록", variable=self.new_song_var
        ).pack(anchor="w", pady=(0, 8))
        ttk.Label(right, text="확정 Key · 빈칸은 미확인").pack(anchor="w")
        self.key_box = ttk.Combobox(
            right, textvariable=self.key_var, values=KEYS, state="readonly", width=15
        )
        self.key_box.pack(anchor="w", pady=4)
        ttk.Label(right, textvariable=self.key_hint, wraplength=390).pack(
            anchor="w", pady=4
        )
        ttk.Button(right, text="Key 후보를 확인하고 적용", command=self.apply_key).pack(
            anchor="w", pady=(0, 10)
        )
        ttk.Label(right, text="편곡").pack(anchor="w")
        ttk.Entry(right, textvariable=self.arr_var).pack(fill="x", pady=4)
        ttk.Label(
            right,
            text="Key 후보는 자동 저장하지 않습니다. 제목과 조성을 확인한 뒤 승인하세요.",
            wraplength=390,
        ).pack(anchor="w", pady=10)
        buttons = ttk.Frame(right)
        buttons.pack(fill="x", pady=8)
        ttk.Button(buttons, text="이전", command=self.prev).pack(side="left")
        ttk.Button(buttons, text="승인 · Enter", command=self.approve).pack(
            side="left", padx=6
        )
        ttk.Button(buttons, text="다음", command=self.next).pack(side="left")
        ttk.Label(
            right,
            text="Ctrl+← / Ctrl+→: 페이지 이동\n입력 중 ←/→: 글자 커서 이동\n다시 분석해도 기존 검수 내용은 유지됩니다.",
            wraplength=390,
        ).pack(anchor="w", pady=8)
        self.bind("<Return>", lambda _e: self.approve())
        self.bind("<Control-Left>", lambda _e: self.prev())
        self.bind("<Control-Right>", lambda _e: self.next())
        self.bind("<Left>", lambda e: self.navigate(e, -1))
        self.bind("<Right>", lambda e: self.navigate(e, 1))

    def navigate(self, event, direction):
        if isinstance(event.widget, (tk.Entry, ttk.Entry, ttk.Combobox, tk.Text)):
            return None
        self.prev() if direction < 0 else self.next()
        return "break"

    def reload(self):
        self.rows = list(
            self.db.review_queue(self.source_id, self.include_reviewed.get())
        )
        self.index = min(self.index, max(0, len(self.rows) - 1))
        self.load_current()

    def load_current(self):
        self.explicit_song_id = None
        self.suggestions = []
        self.new_song_var.set(False)
        if not self.rows:
            self.counter_var.set("검수 대기 페이지가 없습니다.")
            self.raw_var.set("")
            self.title_var.set("")
            self.key_var.set("")
            self.key_hint.set("")
            self.choice["values"] = []
            self.choice_var.set("")
            self.canvas.delete("all")
            return
        row = self.rows[self.index]
        self.counter_var.set(
            f"{self.index + 1} / {len(self.rows)} · {row['original_name']} · p.{row['page']} · {row['state']}"
        )
        self.raw_var.set(
            f"{row['raw_title'] or '(제목 인식 없음)'} · 신뢰도 {row['confidence'] or 0:.2f}"
        )
        self.title_var.set(row["ocr_title_corrected"] or row["raw_title"] or "")
        self.key_var.set(row["key_signature"] or "")
        self.arr_var.set("Original")
        if row["reviewed_score_id"]:
            self.arr_var.set(self.db.get_score(row["reviewed_score_id"])["arrangement"])
        candidate = row["key_candidate"] or "미확인"
        self.key_hint.set(
            f"자동 후보: {candidate} · 신뢰도 {row['key_confidence'] or 0:.2f}\n승인값과 별도로 보존됩니다."
        )
        self.suggestions = self.db.suggest_titles(row["raw_title"] or "")
        options = [
            f"{r['title']} · {r['wgid']} ({r['confidence']:.2f}{' · 이전 수정' if r['remembered'] else ''})"
            for r in self.suggestions
        ]
        self.choice["values"] = options
        self.choice_var.set(options[0] if options else "")
        self.show_image()

    def apply_suggestion(self):
        index = self.choice.current()
        if 0 <= index < len(self.suggestions):
            self.title_var.set(self.suggestions[index]["title"])
            self.explicit_song_id = self.suggestions[index]["song_id"]

    def apply_key(self):
        if self.rows and self.rows[self.index]["key_candidate"] in KEYS:
            self.key_var.set(self.rows[self.index]["key_candidate"])

    def show_image(self):
        self.canvas.delete("all")
        if not self.rows:
            return
        path = Path(self.rows[self.index]["image_path"])
        if not path.is_file():
            self.canvas.create_text(
                20,
                20,
                anchor="nw",
                fill="white",
                text="미리보기 없음 · 원본을 다시 분석하면 복원됩니다.",
            )
            return
        with Image.open(path) as image:
            image = image.convert("RGB")
            image.thumbnail(
                (
                    max(200, self.canvas.winfo_width() - 20),
                    max(200, self.canvas.winfo_height() - 20),
                )
            )
            self.photo = ImageTk.PhotoImage(image)
        self.canvas.create_image(
            max(200, self.canvas.winfo_width()) // 2,
            max(200, self.canvas.winfo_height()) // 2,
            image=self.photo,
            anchor="center",
        )

    def approve(self):
        if not self.rows:
            return "break"
        try:
            selected = self.explicit_song_id
            if (
                selected
                and self.db.get_song(selected)["title"] != self.title_var.get().strip()
            ):
                selected = None
            self.db.approve_page(
                self.rows[self.index]["id"],
                self.title_var.get(),
                self.key_var.get(),
                self.arr_var.get(),
                selected,
                new_song=self.new_song_var.get(),
            )
            if self.on_change:
                self.on_change()
            if self.include_reviewed.get():
                self.rows = list(self.db.review_queue(self.source_id, True))
                self.next()
            else:
                self.reload()
        except Exception as exc:
            messagebox.showerror("검수 저장", str(exc), parent=self)
        return "break"

    def prev(self):
        if self.rows and self.index > 0:
            self.index -= 1
            self.load_current()
        return "break"

    def next(self):
        if self.rows and self.index < len(self.rows) - 1:
            self.index += 1
            self.load_current()
        return "break"

    def close(self):
        if not self._closed:
            self._closed = True
            self.db.close()
            self.destroy()


def open_review_center(master=None, **kwargs):
    return ReviewCenter(master, **kwargs)
