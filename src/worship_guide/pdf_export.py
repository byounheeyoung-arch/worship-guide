"""Atomic PDF output preserving selected variant order and original score pages."""

from __future__ import annotations
from pathlib import Path
from uuid import uuid4
import math
import fitz

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}


def _resolve(text, base=None):
    if not text:
        return None
    p = Path(text)
    if p.is_file():
        return p.resolve()
    if base and (base / p).is_file():
        return (base / p).resolve()
    return None


def _asset(item, base):
    path = _resolve(item.get("file_path"), base)
    if path:
        if path.suffix.lower() == ".pdf":
            return fitz.open(path), path
        if path.suffix.lower() in IMAGE_SUFFIXES:
            with fitz.open(path) as image:
                return fitz.open("pdf", image.convert_to_pdf()), path
        raise ValueError(f"지원하지 않는 파일: {path.name}")
    path = _resolve(item.get("source_pdf"), base)
    if path:
        with fitz.open(path) as source:
            start = item.get("page_start")
            end = item.get("page_end") or start
            if (
                not isinstance(start, int)
                or not isinstance(end, int)
                or not 1 <= start <= end <= len(source)
            ):
                raise ValueError("원본 PDF 페이지 범위 오류")
            result = fitz.open()
            result.insert_pdf(source, from_page=start - 1, to_page=end - 1)
            return result, path
    path = _resolve(item.get("image_path"), base)
    if path:
        with fitz.open(path) as image:
            return fitz.open("pdf", image.convert_to_pdf()), path
    raise ValueError("원본 PDF/악보 파일을 찾을 수 없습니다.")


_FONT = None


def _text(page, rect, text, size=13):
    global _FONT
    if _FONT is None:
        _FONT = fitz.Font("korea").buffer
    page.insert_font(fontname="WGKorean", fontbuffer=_FONT)
    for fontsize in (size, size - 1, size - 2, 9, 8, 7):
        shape = page.new_shape()
        left = shape.insert_textbox(
            rect,
            str(text),
            fontsize=fontsize,
            fontname="WGKorean",
            color=(0.13, 0.18, 0.24),
        )
        if left >= 0:
            shape.commit()
            return
    raise ValueError("PDF 텍스트가 너무 깁니다. 제목/메모 길이를 줄이세요.")


def _cover(out, title, description):
    page = out.new_page()
    page.draw_rect(
        fitz.Rect(0, 0, page.rect.width, 18), color=None, fill=(0.16, 0.30, 0.39)
    )
    _text(page, fitz.Rect(45, 150, 550, 360), title, 28)
    _text(
        page,
        fitz.Rect(45, 390, 550, 570),
        description or "Worship Guide · 선택한 조성의 악보집",
        14,
    )


def export_collection_pdf(
    items,
    output_path,
    *,
    db_dir=None,
    mode="simple",
    title="Worship Guide",
    description="",
    allow_partial=False,
):
    """simple / guide / setlist. Invalid items fail before replacing output.

    A guide has cover, TOC, section dividers, metadata pages, then unchanged
    score pages. PDF bookmarks and TOC point to each original score's start.
    """
    if mode not in {"simple", "guide", "setlist"}:
        raise ValueError("PDF 출력 형식 오류")
    items = [dict(i) for i in items]
    if not items:
        raise ValueError("악보집에 악보가 없습니다.")
    base = Path(db_dir) if db_dir else None
    target = Path(output_path).expanduser().resolve()
    assets = []
    warnings = []
    out = fitz.open()
    temporary = target.with_name(target.name + "." + uuid4().hex + ".tmp.pdf")
    try:
        for item in items:
            try:
                doc, path = _asset(item, base)
                if doc.needs_pass or not len(doc):
                    doc.close()
                    raise ValueError("암호가 있거나 빈 악보 파일입니다.")
                if path == target:
                    doc.close()
                    raise ValueError("출력 파일이 원본 악보와 같습니다.")
                assets.append((item, doc))
            except Exception as exc:
                warnings.append(
                    f"{item.get('title', '곡')} ({item.get('key_signature') or '?'}): {exc}"
                )
        if warnings and not allow_partial:
            raise ValueError("PDF 저장을 중단했습니다.\n" + "\n".join(warnings))
        if not assets:
            raise ValueError("내보낼 수 있는 악보가 없습니다.")
        toc_pages = math.ceil(len(assets) / 24) if mode != "simple" else 0
        if mode != "simple":
            _cover(out, title, description)
            for _ in range(toc_pages):
                out.new_page()
        bookmarks = []
        entries = []
        section = None
        for index, (item, score) in enumerate(assets, 1):
            if mode != "simple":
                current = item.get("section") or ""
                if current and current != section:
                    page = out.new_page()
                    _text(page, fitz.Rect(45, 220, 550, 430), current, 24)
                    section = current
                elif not current:
                    section = ""
                page = out.new_page()
                label = f"{index}. {item.get('title', '')}"
                _text(page, fitz.Rect(45, 60, 550, 170), label, 21)
                metadata = "\n".join(
                    [
                        "Key: " + (item.get("key_signature") or "미확인"),
                        "편곡: " + (item.get("arrangement") or "Original"),
                        "주제: " + (item.get("themes") or ""),
                        "성경: " + (item.get("bible") or ""),
                        "메모 / 전환: " + (item.get("item_notes") or ""),
                    ]
                )
                _text(page, fitz.Rect(45, 190, 550, 720), metadata, 14)
            first = out.page_count + 1
            out.insert_pdf(score)
            label = f"{item.get('title', '')} · {item.get('key_signature') or '미확인'}"
            entries.append((label, first))
            bookmarks.append([1, label, first])
        if mode != "simple":
            for offset in range(toc_pages):
                page = out[1 + offset]
                _text(page, fitz.Rect(45, 35, 550, 90), "목차", 22)
                for index, (label, number) in enumerate(
                    entries[offset * 24 : (offset + 1) * 24]
                ):
                    y = 100 + index * 28
                    _text(page, fitz.Rect(45, y, 505, y + 27), label, 11)
                    _text(page, fitz.Rect(510, y, 550, y + 27), str(number), 11)
                    page.insert_link(
                        {
                            "kind": fitz.LINK_GOTO,
                            "from": fitz.Rect(45, y, 550, y + 27),
                            "page": number - 1,
                        }
                    )
        out.set_toc(bookmarks)
        out.set_metadata(
            {"title": title, "author": "Worship Guide", "subject": description}
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        out.save(temporary, garbage=4, deflate=True)
        temporary.replace(target)
        return len(out), warnings
    finally:
        temporary.unlink(missing_ok=True)
        for _, doc in assets:
            doc.close()
        out.close()
