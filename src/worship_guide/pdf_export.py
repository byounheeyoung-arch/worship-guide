from __future__ import annotations
from pathlib import Path
import fitz

IMAGE_SUFFIXES={'.png','.jpg','.jpeg','.webp','.bmp','.tif','.tiff'}

def _resolve(path_text:str, base_dir:Path|None=None)->Path|None:
    if not path_text:return None
    p=Path(path_text)
    if p.exists():return p
    if base_dir:
        q=(base_dir/p).resolve()
        if q.exists():return q
    return None

def _append_image(out:fitz.Document, image_path:Path):
    img=fitz.open(image_path)
    pdf=fitz.open('pdf',img.convert_to_pdf())
    out.insert_pdf(pdf)
    pdf.close(); img.close()

def export_collection_pdf(items, output_path:str|Path, *, db_dir:str|Path|None=None):
    """Merge selected Score Variants in collection order.

    Priority: file_path (PDF/image) -> source_pdf + page range.
    Returns (pages_added, warnings).
    """
    out=fitz.open(); warnings=[]; base=Path(db_dir) if db_dir else None
    try:
        for item in items:
            title=item['title']; key=item['key_signature'] or '?'
            file_path=_resolve(item['file_path'] or '',base)
            source_pdf=_resolve(item['source_pdf'] or '',base)
            try:
                if file_path:
                    if file_path.suffix.lower()=='.pdf':
                        doc=fitz.open(file_path); out.insert_pdf(doc); doc.close()
                    elif file_path.suffix.lower() in IMAGE_SUFFIXES:
                        _append_image(out,file_path)
                    else:
                        warnings.append(f"{title} ({key}): 지원하지 않는 파일 형식 - {file_path.name}")
                    continue
                if source_pdf:
                    doc=fitz.open(source_pdf)
                    start=(item['page_start'] or 1)-1
                    end=(item['page_end'] or item['page_start'] or 1)-1
                    if start<0 or end>=doc.page_count or start>end:
                        warnings.append(f"{title} ({key}): PDF 페이지 범위 오류")
                    else:
                        out.insert_pdf(doc,from_page=start,to_page=end)
                    doc.close(); continue
                warnings.append(f"{title} ({key}): 원본 PDF/파일 경로 없음")
            except Exception as e:
                warnings.append(f"{title} ({key}): {e}")
        if out.page_count==0:
            raise ValueError("내보낼 수 있는 악보 페이지가 없습니다. 각 악보의 원본 PDF 또는 파일 경로를 확인하세요.")
        target=Path(output_path); target.parent.mkdir(parents=True,exist_ok=True)
        out.save(target,garbage=4,deflate=True)
        return out.page_count,warnings
    finally:
        out.close()
