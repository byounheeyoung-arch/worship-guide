from pathlib import Path
import fitz
from worship_guide.db import WGDB
from worship_guide.pdf_export import export_collection_pdf


def _make_pdf(path:Path, labels):
    doc=fitz.open()
    for label in labels:
        page=doc.new_page(width=300,height=200)
        page.insert_text((40,80),label,fontsize=18)
    doc.save(path); doc.close()


def test_collection_filters_and_order(tmp_path:Path):
    db=WGDB(tmp_path/'t.db')
    s1=db.save_song({'title':'감사해','category':'감사','themes':'감사,찬양','mood':'밝음','difficulty':'2'})
    sc1=db.save_score(s1,{'arrangement':'Original','key_signature':'G','page_start':1})
    s2=db.save_song({'title':'예수 닮기를','category':'헌신','themes':'헌신,제자도','mood':'잔잔함','difficulty':'3'})
    sc2=db.save_score(s2,{'arrangement':'Original','key_signature':'E','page_start':2})
    rows=db.collection_candidates(themes='헌신',mood='잔잔함',key_signature='E')
    assert [r['title'] for r in rows]==['예수 닮기를']
    cid=db.create_collection('헌신곡',filters={'themes':'헌신'})
    db.add_score_to_collection(cid,sc2); db.add_score_to_collection(cid,sc1)
    items=db.get_collection_items(cid)
    assert [r['title'] for r in items]==['예수 닮기를','감사해']
    db.move_collection_item(items[1]['id'],-1)
    assert [r['title'] for r in db.get_collection_items(cid)]==['감사해','예수 닮기를']
    db.close()


def test_export_collection_pdf_from_source_pages(tmp_path:Path):
    source=tmp_path/'source.pdf'; _make_pdf(source,['ONE','TWO','THREE'])
    db=WGDB(tmp_path/'t.db')
    s1=db.save_song({'title':'곡1'}); sc1=db.save_score(s1,{'key_signature':'G','page_start':2,'source_pdf':str(source)})
    s2=db.save_song({'title':'곡2'}); sc2=db.save_score(s2,{'key_signature':'A','page_start':3,'source_pdf':str(source)})
    cid=db.create_collection('테스트'); db.add_score_to_collection(cid,sc1); db.add_score_to_collection(cid,sc2)
    out=tmp_path/'book.pdf'
    pages,warnings=export_collection_pdf(db.get_collection_items(cid),out,db_dir=tmp_path)
    assert pages==2 and not warnings and out.exists()
    doc=fitz.open(out); assert doc.page_count==2; doc.close(); db.close()
