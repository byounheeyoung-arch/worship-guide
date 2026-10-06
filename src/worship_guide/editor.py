from __future__ import annotations
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from pathlib import Path
import json
from .db import WGDB
from .pdf_export import export_collection_pdf

APP_TITLE="Worship Guide DB Editor v0.8"

class Editor(tk.Tk):
    def __init__(self):
        super().__init__(); self.title(APP_TITLE); self.geometry("1400x900"); self.minsize(1150,720)
        db_path=Path(__file__).resolve().parents[2]/"data"/"wgdb.sqlite3"; self.db=WGDB(db_path)
        self.current_id=None; self.current_score_id=None; self.current_collection_id=None
        self.protocol("WM_DELETE_WINDOW",self.on_close); self._build_ui(); self.refresh_songs(); self.refresh_setlists()

    def _build_ui(self):
        self.columnconfigure(0,weight=1); self.rowconfigure(1,weight=1)
        top=ttk.Frame(self,padding=8); top.grid(row=0,column=0,sticky="ew"); top.columnconfigure(1,weight=1)
        ttk.Label(top,text="검색").grid(row=0,column=0,padx=(0,6)); self.search_var=tk.StringVar(); e=ttk.Entry(top,textvariable=self.search_var); e.grid(row=0,column=1,sticky="ew"); e.bind("<KeyRelease>",lambda _e:self.refresh_songs())
        ttk.Button(top,text="OCR CSV 가져오기",command=self.import_ocr).grid(row=0,column=2,padx=4); ttk.Button(top,text="CSV 내보내기",command=self.export_csv).grid(row=0,column=3,padx=4)
        nb=ttk.Notebook(self); nb.grid(row=1,column=0,sticky="nsew"); self.song_tab=ttk.Frame(nb,padding=8); self.collection_tab=ttk.Frame(nb,padding=8); self.set_tab=ttk.Frame(nb,padding=8); nb.add(self.song_tab,text="곡 / 악보 DB"); nb.add(self.collection_tab,text="악보집"); nb.add(self.set_tab,text="세트리스트")
        self._build_song_tab(); self._build_collection_tab(); self._build_set_tab()

    def _build_song_tab(self):
        self.song_tab.columnconfigure(0,weight=2); self.song_tab.columnconfigure(1,weight=3); self.song_tab.rowconfigure(0,weight=1)
        left=ttk.Frame(self.song_tab); left.grid(row=0,column=0,sticky="nsew",padx=(0,8)); left.rowconfigure(0,weight=1); left.columnconfigure(0,weight=1)
        self.tree=ttk.Treeview(left,columns=("wgid","title","keys","status"),show="headings",selectmode="browse")
        for c,t,w in [("wgid","WGID",90),("title","곡명",230),("keys","악보 Key",140),("status","상태",90)]: self.tree.heading(c,text=t); self.tree.column(c,width=w,anchor="w")
        self.tree.grid(row=0,column=0,sticky="nsew"); self.tree.bind("<<TreeviewSelect>>",self.on_select); sb=ttk.Scrollbar(left,orient="vertical",command=self.tree.yview); sb.grid(row=0,column=1,sticky="ns"); self.tree.configure(yscrollcommand=sb.set)
        b=ttk.Frame(left); b.grid(row=1,column=0,columnspan=2,sticky="ew",pady=(6,0)); ttk.Button(b,text="새 곡",command=self.new_song).pack(side="left"); ttk.Button(b,text="곡 삭제",command=self.delete_song).pack(side="left",padx=4)

        right=ttk.Frame(self.song_tab); right.grid(row=0,column=1,sticky="nsew"); right.columnconfigure(1,weight=1); right.rowconfigure(11,weight=1)
        self.vars={k:tk.StringVar() for k in ["wgid","title","original_title","bpm","meter","category","themes","bible","flow","mood","difficulty","review_status"]}
        labels=[("WGID","wgid"),("곡명","title"),("원제","original_title"),("BPM","bpm"),("박자","meter"),("대분류","category"),("주제 태그","themes"),("성경","bible"),("예배 흐름","flow"),("분위기","mood"),("난이도(1~5)","difficulty"),("검수 상태","review_status")]
        for i,(lab,key) in enumerate(labels): ttk.Label(right,text=lab).grid(row=i,column=0,sticky="w",padx=(0,6),pady=2); ttk.Entry(right,textvariable=self.vars[key]).grid(row=i,column=1,sticky="ew",pady=2)
        self.favorite_var=tk.BooleanVar(); ttk.Checkbutton(right,text="즐겨찾기",variable=self.favorite_var).grid(row=12,column=1,sticky="w",pady=3)
        ttk.Label(right,text="곡 메모").grid(row=13,column=0,sticky="nw"); self.notes=tk.Text(right,height=4,wrap="word"); self.notes.grid(row=13,column=1,sticky="ew")
        ttk.Button(right,text="곡 저장",command=self.save_song).grid(row=14,column=1,sticky="e",pady=(6,10))

        box=ttk.LabelFrame(right,text="악보 버전 (같은 곡 · 다른 Key/페이지)",padding=6); box.grid(row=15,column=0,columnspan=2,sticky="nsew"); box.columnconfigure(0,weight=1); box.rowconfigure(0,weight=1); right.rowconfigure(15,weight=1)
        self.score_tree=ttk.Treeview(box,columns=("arr","key","page","ocr","status"),show="headings",height=9)
        for c,t,w in [("arr","Arrangement",110),("key","Key",70),("page","Page",70),("ocr","OCR 제목",220),("status","상태",90)]: self.score_tree.heading(c,text=t); self.score_tree.column(c,width=w,anchor="w")
        self.score_tree.grid(row=0,column=0,columnspan=5,sticky="nsew"); self.score_tree.bind("<<TreeviewSelect>>",self.on_score_select)
        self.score_vars={k:tk.StringVar() for k in ["arrangement","key_signature","page_start","page_end","source_pdf","file_path","ocr_title_raw","ocr_confidence","review_status"]}
        defaults={"arrangement":"Original","review_status":"미검수"}; [self.score_vars[k].set(v) for k,v in defaults.items()]
        row=1
        for j,(lab,key) in enumerate([("편곡","arrangement"),("Key","key_signature"),("시작 Page","page_start"),("끝 Page","page_end")]):
            ttk.Label(box,text=lab).grid(row=row,column=j*2 if j<2 else (j-2)*2,sticky="w",padx=3,pady=2)
            ttk.Entry(box,textvariable=self.score_vars[key],width=16).grid(row=row,column=(j*2+1) if j<2 else ((j-2)*2+1),sticky="ew",padx=3,pady=2)
            if j==1: row+=1
        row=3
        for lab,key in [("원본 PDF","source_pdf"),("파일 경로","file_path"),("OCR 원문","ocr_title_raw"),("OCR 신뢰도","ocr_confidence"),("악보 상태","review_status")]: ttk.Label(box,text=lab).grid(row=row,column=0,sticky="w",padx=3,pady=2); ttk.Entry(box,textvariable=self.score_vars[key]).grid(row=row,column=1,columnspan=3,sticky="ew",padx=3,pady=2); row+=1
        ab=ttk.Frame(box); ab.grid(row=row,column=0,columnspan=4,sticky="e",pady=(5,0)); ttk.Button(ab,text="새 악보",command=self.new_score).pack(side="left"); ttk.Button(ab,text="악보 저장",command=self.save_score).pack(side="left",padx=4); ttk.Button(ab,text="악보 삭제",command=self.delete_score).pack(side="left")

    def _build_collection_tab(self):
        tab=self.collection_tab
        tab.columnconfigure(0,weight=1); tab.columnconfigure(1,weight=3); tab.rowconfigure(0,weight=1)
        left=ttk.Frame(tab); left.grid(row=0,column=0,sticky="nsew",padx=(0,8)); left.rowconfigure(1,weight=1); left.columnconfigure(0,weight=1)
        ttk.Label(left,text="내 악보집",font=("TkDefaultFont",11,"bold")).grid(row=0,column=0,sticky="w",pady=(0,6))
        self.collection_tree=ttk.Treeview(left,columns=("name","count"),show="headings",selectmode="browse")
        self.collection_tree.heading("name",text="악보집"); self.collection_tree.heading("count",text="곡수")
        self.collection_tree.column("name",width=220); self.collection_tree.column("count",width=55,anchor="center")
        self.collection_tree.grid(row=1,column=0,sticky="nsew"); self.collection_tree.bind("<<TreeviewSelect>>",self.on_collection_select)
        cb=ttk.Frame(left); cb.grid(row=2,column=0,sticky="ew",pady=(6,0))
        ttk.Button(cb,text="새 악보집",command=self.new_collection).pack(side="left")
        ttk.Button(cb,text="삭제",command=self.delete_collection).pack(side="left",padx=4)

        right=ttk.Frame(tab); right.grid(row=0,column=1,sticky="nsew"); right.columnconfigure(0,weight=1); right.rowconfigure(2,weight=2); right.rowconfigure(4,weight=2)
        meta=ttk.LabelFrame(right,text="악보집 정보 / 필터",padding=8); meta.grid(row=0,column=0,sticky="ew");
        for c in range(6): meta.columnconfigure(c,weight=1 if c%2 else 0)
        self.collection_name=tk.StringVar(); self.collection_desc=tk.StringVar()
        ttk.Label(meta,text="이름").grid(row=0,column=0,sticky="w"); ttk.Entry(meta,textvariable=self.collection_name).grid(row=0,column=1,columnspan=2,sticky="ew",padx=(4,10))
        ttk.Label(meta,text="설명").grid(row=0,column=3,sticky="w"); ttk.Entry(meta,textvariable=self.collection_desc).grid(row=0,column=4,columnspan=2,sticky="ew",padx=(4,0))
        self.filter_vars={k:tk.StringVar() for k in ["query","category","themes","mood","key_signature","flow","max_difficulty"]}
        specs=[("검색","query"),("대분류","category"),("주제","themes"),("분위기","mood"),("Key","key_signature"),("예배 흐름","flow"),("최대 난이도","max_difficulty")]
        for i,(lab,key) in enumerate(specs):
            r=1+i//4; c=(i%4)*2
            ttk.Label(meta,text=lab).grid(row=r,column=c,sticky="w",pady=3)
            ttk.Entry(meta,textvariable=self.filter_vars[key],width=15).grid(row=r,column=c+1,sticky="ew",padx=(3,8),pady=3)
        footer=ttk.Frame(meta); footer.grid(row=3,column=0,columnspan=8,sticky="ew",pady=(5,0)); footer.columnconfigure(0,weight=1)
        ttk.Label(footer,text="쉼표로 여러 값 입력: 같은 항목은 OR, 서로 다른 항목은 AND").grid(row=0,column=0,sticky="w")
        ttk.Button(footer,text="조건 검색",command=self.refresh_collection_candidates).grid(row=0,column=1,padx=3)
        ttk.Button(footer,text="악보집 저장",command=self.save_collection).grid(row=0,column=2,padx=3)

        ttk.Label(right,text="조건에 맞는 악보 버전",font=("TkDefaultFont",10,"bold")).grid(row=1,column=0,sticky="w",pady=(8,3))
        self.candidate_tree=ttk.Treeview(right,columns=("title","key","arr","category","themes","mood"),show="headings",selectmode="extended")
        for c,t,w in [("title","곡명",220),("key","Key",55),("arr","편곡",90),("category","대분류",90),("themes","주제",180),("mood","분위기",120)]:
            self.candidate_tree.heading(c,text=t); self.candidate_tree.column(c,width=w,anchor="w")
        self.candidate_tree.grid(row=2,column=0,sticky="nsew")
        mid=ttk.Frame(right); mid.grid(row=3,column=0,sticky="ew",pady=6)
        ttk.Button(mid,text="선택 악보 추가 ↓",command=self.add_candidates_to_collection).pack(side="left")
        ttk.Button(mid,text="전체 검색 결과 추가",command=self.add_all_candidates).pack(side="left",padx=4)
        ttk.Label(mid,text="곡이 같아도 선택한 Key/편곡은 별도 악보로 보존됩니다.").pack(side="left",padx=12)

        itembox=ttk.LabelFrame(right,text="이 악보집에 들어갈 실제 악보 순서",padding=6); itembox.grid(row=4,column=0,sticky="nsew"); itembox.rowconfigure(0,weight=1); itembox.columnconfigure(0,weight=1)
        self.collection_item_tree=ttk.Treeview(itembox,columns=("pos","title","key","arr","pages"),show="headings",selectmode="browse")
        for c,t,w in [("pos","#",40),("title","곡명",260),("key","Key",60),("arr","편곡",100),("pages","Page",80)]:
            self.collection_item_tree.heading(c,text=t); self.collection_item_tree.column(c,width=w,anchor="w")
        self.collection_item_tree.grid(row=0,column=0,sticky="nsew")
        ib=ttk.Frame(itembox); ib.grid(row=1,column=0,sticky="ew",pady=(6,0))
        ttk.Button(ib,text="▲ 위로",command=lambda:self.move_collection_item(-1)).pack(side="left")
        ttk.Button(ib,text="▼ 아래로",command=lambda:self.move_collection_item(1)).pack(side="left",padx=4)
        ttk.Button(ib,text="빼기",command=self.remove_collection_item).pack(side="left")
        ttk.Button(ib,text="악보집 PDF 만들기",command=self.export_collection_pdf_ui).pack(side="right")
        self.refresh_collections(); self.refresh_collection_candidates()

    def _build_set_tab(self):
        self.set_tab.columnconfigure(0,weight=1); self.set_tab.columnconfigure(1,weight=2); self.set_tab.rowconfigure(1,weight=1)
        bar=ttk.Frame(self.set_tab); bar.grid(row=0,column=0,columnspan=2,sticky="ew",pady=(0,6)); bar.columnconfigure(1,weight=1); ttk.Label(bar,text="새 세트 이름").grid(row=0,column=0); self.new_set_var=tk.StringVar(); ttk.Entry(bar,textvariable=self.new_set_var).grid(row=0,column=1,sticky="ew",padx=6); ttk.Button(bar,text="세트 만들기",command=self.create_set).grid(row=0,column=2)
        self.set_tree=ttk.Treeview(self.set_tab,columns=("name","date"),show="headings"); self.set_tree.heading("name",text="세트명"); self.set_tree.heading("date",text="날짜"); self.set_tree.grid(row=1,column=0,sticky="nsew",padx=(0,8)); self.set_tree.bind("<<TreeviewSelect>>",lambda _e:self.refresh_set_items())
        self.item_tree=ttk.Treeview(self.set_tab,columns=("pos","title","key"),show="headings");
        for c,t,w in [("pos","#",45),("title","곡명",260),("key","선택 Key",90)]: self.item_tree.heading(c,text=t); self.item_tree.column(c,width=w)
        self.item_tree.grid(row=1,column=1,sticky="nsew")

    def refresh_songs(self):
        for x in self.tree.get_children(): self.tree.delete(x)
        for r in self.db.list_songs(self.search_var.get()): self.tree.insert("","end",iid=str(r["id"]),values=(r["wgid"],r["title"],r["available_keys"] or "",r["review_status"]))

    def on_select(self,_e=None):
        sel=self.tree.selection();
        if not sel:return
        self.current_id=int(sel[0]); r=self.db.get_song(self.current_id)
        for k,v in self.vars.items(): v.set("" if r[k] is None else str(r[k]))
        self.favorite_var.set(bool(r["favorite"])); self.notes.delete("1.0","end"); self.notes.insert("1.0",r["notes"] or ""); self.refresh_scores(); self.new_score()

    def new_song(self):
        self.current_id=None; [v.set("") for v in self.vars.values()]; self.vars["review_status"].set("미검수"); self.favorite_var.set(False); self.notes.delete("1.0","end"); self.refresh_scores(); self.new_score()

    def save_song(self):
        if not self.vars["title"].get().strip(): messagebox.showwarning(APP_TITLE,"곡명을 입력하세요."); return
        data={k:v.get() for k,v in self.vars.items()}; data["favorite"]=self.favorite_var.get(); data["notes"]=self.notes.get("1.0","end").strip()
        try:self.current_id=self.db.save_song(data,self.current_id); self.refresh_songs(); messagebox.showinfo(APP_TITLE,"곡을 저장했습니다.")
        except Exception as e: messagebox.showerror(APP_TITLE,str(e))

    def delete_song(self):
        if self.current_id and messagebox.askyesno(APP_TITLE,"곡과 연결된 모든 악보 버전을 삭제할까요?"): self.db.delete_song(self.current_id); self.current_id=None; self.new_song(); self.refresh_songs()

    def refresh_scores(self):
        for x in self.score_tree.get_children(): self.score_tree.delete(x)
        if not self.current_id:return
        for r in self.db.list_scores(self.current_id):
            p=str(r["page_start"] or ""); p=p if r["page_end"] in (None,r["page_start"]) else f"{p}-{r['page_end']}"
            self.score_tree.insert("","end",iid=str(r["id"]),values=(r["arrangement"],r["key_signature"],p,r["ocr_title_raw"],r["review_status"]))

    def on_score_select(self,_e=None):
        sel=self.score_tree.selection();
        if not sel:return
        self.current_score_id=int(sel[0]); r=self.db.get_score(self.current_score_id)
        for k,v in self.score_vars.items(): v.set("" if r[k] is None else str(r[k]))

    def new_score(self):
        self.current_score_id=None; [v.set("") for v in self.score_vars.values()]; self.score_vars["arrangement"].set("Original"); self.score_vars["review_status"].set("미검수")

    def save_score(self):
        if not self.current_id: messagebox.showwarning(APP_TITLE,"먼저 곡을 저장하세요."); return
        try:self.current_score_id=self.db.save_score(self.current_id,{k:v.get() for k,v in self.score_vars.items()},self.current_score_id); self.refresh_scores(); self.refresh_songs(); messagebox.showinfo(APP_TITLE,"악보 버전을 저장했습니다.")
        except Exception as e: messagebox.showerror(APP_TITLE,str(e))

    def delete_score(self):
        if self.current_score_id and messagebox.askyesno(APP_TITLE,"이 악보 버전만 삭제할까요?"): self.db.delete_score(self.current_score_id); self.current_score_id=None; self.new_score(); self.refresh_scores(); self.refresh_songs()

    def import_ocr(self):
        p=filedialog.askopenfilename(title="titles_ocr.csv 선택",filetypes=[("CSV","*.csv")]);
        if not p:return
        try:
            a,b,s=self.db.import_ocr_csv(p); self.refresh_songs(); messagebox.showinfo(APP_TITLE,f"가져오기 완료\n새 곡 {a} / 악보 버전 {b} / 건너뜀 {s}")
        except Exception as e: messagebox.showerror(APP_TITLE,str(e))

    def export_csv(self):
        p=filedialog.asksaveasfilename(defaultextension=".csv",filetypes=[("CSV","*.csv")],initialfile="wgdb_song_scores.csv")
        if p:self.db.export_csv(p); messagebox.showinfo(APP_TITLE,"CSV를 저장했습니다.")

    def collection_filters(self):
        return {k:v.get().strip() for k,v in self.filter_vars.items()}

    def refresh_collections(self):
        if not hasattr(self,"collection_tree"): return
        for x in self.collection_tree.get_children(): self.collection_tree.delete(x)
        for r in self.db.list_collections():
            count=self.db.conn.execute("SELECT COUNT(*) n FROM collection_items WHERE collection_id=?",(r["id"],)).fetchone()["n"]
            self.collection_tree.insert("","end",iid=str(r["id"]),values=(r["name"],count))

    def new_collection(self):
        self.current_collection_id=None; self.collection_name.set(""); self.collection_desc.set("")
        for v in self.filter_vars.values(): v.set("")
        self.refresh_collection_items(); self.refresh_collection_candidates()

    def save_collection(self):
        name=self.collection_name.get().strip()
        if not name: messagebox.showwarning(APP_TITLE,"악보집 이름을 입력하세요."); return
        if self.current_collection_id:
            self.db.update_collection(self.current_collection_id,name,self.collection_desc.get(),self.collection_filters())
        else:
            self.current_collection_id=self.db.create_collection(name,self.collection_desc.get(),self.collection_filters())
        self.refresh_collections(); messagebox.showinfo(APP_TITLE,"악보집을 저장했습니다.")

    def on_collection_select(self,_e=None):
        sel=self.collection_tree.selection()
        if not sel:return
        self.current_collection_id=int(sel[0]); r=self.db.get_collection(self.current_collection_id)
        self.collection_name.set(r["name"] or ""); self.collection_desc.set(r["description"] or "")
        try: filters=json.loads(r["filter_json"] or "{}")
        except Exception: filters={}
        for k,v in self.filter_vars.items(): v.set(filters.get(k,"") or "")
        self.refresh_collection_candidates(); self.refresh_collection_items()

    def delete_collection(self):
        if self.current_collection_id and messagebox.askyesno(APP_TITLE,"이 악보집을 삭제할까요? 원본 곡/악보는 삭제되지 않습니다."):
            self.db.delete_collection(self.current_collection_id); self.new_collection(); self.refresh_collections()

    def refresh_collection_candidates(self):
        if not hasattr(self,"candidate_tree"):return
        for x in self.candidate_tree.get_children():self.candidate_tree.delete(x)
        rows=self.db.collection_candidates(**self.collection_filters())
        for r in rows:
            self.candidate_tree.insert("","end",iid=str(r["score_id"]),values=(r["title"],r["key_signature"],r["arrangement"],r["category"],r["themes"],r["mood"]))

    def _ensure_collection(self):
        if self.current_collection_id:return True
        name=self.collection_name.get().strip()
        if not name: messagebox.showwarning(APP_TITLE,"먼저 악보집 이름을 입력하고 저장하세요."); return False
        self.save_collection(); return bool(self.current_collection_id)

    def add_candidates_to_collection(self):
        if not self._ensure_collection():return
        for iid in self.candidate_tree.selection(): self.db.add_score_to_collection(self.current_collection_id,int(iid))
        self.refresh_collection_items(); self.refresh_collections()

    def add_all_candidates(self):
        if not self._ensure_collection():return
        for iid in self.candidate_tree.get_children(): self.db.add_score_to_collection(self.current_collection_id,int(iid))
        self.refresh_collection_items(); self.refresh_collections()

    def refresh_collection_items(self):
        if not hasattr(self,"collection_item_tree"):return
        for x in self.collection_item_tree.get_children():self.collection_item_tree.delete(x)
        if not self.current_collection_id:return
        for r in self.db.get_collection_items(self.current_collection_id):
            ps=r["page_start"] or ""; pe=r["page_end"] or ""; pages=str(ps) if not pe or pe==ps else f"{ps}-{pe}"
            self.collection_item_tree.insert("","end",iid=str(r["id"]),values=(r["position"],r["title"],r["key_signature"],r["arrangement"],pages))

    def remove_collection_item(self):
        sel=self.collection_item_tree.selection()
        if not sel:return
        self.db.remove_collection_item(int(sel[0])); self.refresh_collection_items(); self.refresh_collections()

    def move_collection_item(self,delta:int):
        sel=self.collection_item_tree.selection()
        if not sel:return
        iid=int(sel[0]); self.db.move_collection_item(iid,delta); self.refresh_collection_items()
        if str(iid) in self.collection_item_tree.get_children(): self.collection_item_tree.selection_set(str(iid)); self.collection_item_tree.see(str(iid))

    def export_collection_pdf_ui(self):
        if not self.current_collection_id: messagebox.showwarning(APP_TITLE,"악보집을 선택하세요."); return
        items=self.db.get_collection_items(self.current_collection_id)
        if not items: messagebox.showwarning(APP_TITLE,"악보집에 악보가 없습니다."); return
        name=(self.collection_name.get().strip() or "worship-guide-songbook").replace("/","_").replace("\\","_")
        p=filedialog.asksaveasfilename(title="악보집 PDF 저장",defaultextension=".pdf",filetypes=[("PDF","*.pdf")],initialfile=f"{name}.pdf")
        if not p:return
        try:
            pages,warnings=export_collection_pdf(items,p,db_dir=self.db.path.parent)
            msg=f"PDF 저장 완료\n{pages}페이지\n{p}"
            if warnings: msg += "\n\n제외/경고:\n"+"\n".join(warnings[:12])+("\n..." if len(warnings)>12 else "")
            messagebox.showinfo(APP_TITLE,msg)
        except Exception as e: messagebox.showerror(APP_TITLE,str(e))

    def create_set(self):
        name=self.new_set_var.get().strip();
        if name:self.db.create_setlist(name); self.new_set_var.set(""); self.refresh_setlists()
    def refresh_setlists(self):
        for x in self.set_tree.get_children():self.set_tree.delete(x)
        for r in self.db.list_setlists():self.set_tree.insert("","end",iid=str(r["id"]),values=(r["name"],r["service_date"]))
    def refresh_set_items(self):
        for x in self.item_tree.get_children():self.item_tree.delete(x)
        sel=self.set_tree.selection();
        if not sel:return
        for r in self.db.get_setlist_items(int(sel[0])):self.item_tree.insert("","end",values=(r["position"],r["title"],r["selected_key"] or r["score_key"] or ""))
    def on_close(self): self.db.close(); self.destroy()

def main(): Editor().mainloop()
if __name__=="__main__":main()
