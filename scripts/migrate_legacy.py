"""Read-only v1/v2 SQLite -> unified portable backup. Never mutates source DB.
Usage: python scripts/migrate_legacy.py database.db backup.json [--asset-root DIR]
"""
import argparse
import base64
import hashlib
import json
import sqlite3
from pathlib import Path


def convert(db_path, asset_root=None):
    db_path = Path(db_path).resolve()
    conn = sqlite3.connect(db_path.as_uri() + '?mode=ro', uri=True)
    conn.row_factory = sqlite3.Row
    prefix = hashlib.sha256(str(db_path).encode()).hexdigest()[:16]
    uid = lambda kind, value: f'legacy-{prefix}-{kind}-{value}'
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    def rows(table):
        return [dict(r) for r in conn.execute(f'SELECT * FROM "{table}"')] if table in tables else []
    state = dict(schemaVersion=1, songs=[], arrangements=[], scores=[], documents=[], collections=[], reviews=[])
    assets, warnings, docs = {}, [], {}
    for r in rows('songs'):
        s = {'id': uid('song', r['id']), 'title': r.get('title') or '제목 미상', 'favorite': bool(r.get('favorite')), 'legacy': r}
        mapping = {'original_title':'originalTitle', 'lyrics':'lyrics', 'composer':'composer', 'lyricist':'lyricist', 'bpm':'bpm', 'meter':'meter', 'category':'category', 'themes':'themes', 'bible':'bible', 'flow':'flow', 'mood':'mood', 'difficulty':'difficulty', 'notes':'notes'}
        for old,new in mapping.items():
            if r.get(old) is not None:s[new]=r[old]
        s['notes'] = s.get('notes') or r.get('memo') or ''
        for key in ('bpm', 'difficulty'):
            if key in s:
                try:s[key]=int(s[key])
                except (ValueError,TypeError):s[key]=None
        state['songs'].append(s)
    for r in rows('arrangements'):
        state['arrangements'].append({'id':uid('arrangement',r['id']),'songId':uid('song',r['song_id']),'name':r.get('name') or 'Original','legacy':r})
    tags = {r['id']:r for r in rows('tags')}
    for r in rows('song_tags'):
        song=next((s for s in state['songs'] if s['id']==uid('song',r['song_id'])),None)
        tag=tags.get(r['tag_id'])
        if song and tag:song['themes']=', '.join(filter(None,[song.get('themes'),tag['name']]))
    for r in rows('scripture_links'):
        song=next((s for s in state['songs'] if s['id']==uid('song',r['song_id'])),None)
        if song:song['bible']='; '.join(filter(None,[song.get('bible'),r.get('reference_text')]))
    def document(r):
        candidates = [r.get(k) for k in ('source_pdf','source_document','file_path') if r.get(k)]
        for raw in candidates:
            p=Path(raw)
            choices=[p,db_path.parent/p]
            if asset_root: choices += [Path(asset_root)/p.name,Path(asset_root)/str(raw).replace('\\','/').split('/')[-1]]
            for path in choices:
                if path.is_file() and path.suffix.lower()=='.pdf':
                    data=path.read_bytes();digest=hashlib.sha256(data).hexdigest()
                    if digest not in docs:
                        did='pdf-'+digest;docs[digest]=did
                        state['documents'].append({'id':did,'name':path.name,'sha256':digest})
                        assets[did]='data:application/pdf;base64,'+base64.b64encode(data).decode()
                    return docs[digest]
        warnings.append(f"원본 PDF 연결 필요: {candidates or r.get('id')}")
        return None
    for table in ('scores','score_variants'):
        for r in rows(table):
            start=r.get('page_start') or r.get('start_page') or 1
            end=r.get('page_end') or r.get('end_page') or start
            score={'id':uid(table,r['id']),'arrangementId':uid('arrangement',r['arrangement_id']), 'key':r.get('key_signature') or '', 'startPage':max(1,int(start)), 'endPage':max(1,int(start),int(end)), 'documentId':document(r), 'status':'reviewed' if r.get('review_status') in ('reviewed','검수완료','검수 완료','승인') else 'unreviewed', 'rawOcr':r.get('ocr_title_raw') or r.get('raw_ocr_title') or '', 'ocrConfidence':r.get('ocr_confidence'), 'legacy':r}
            state['scores'].append(score)
    items=rows('collection_items')
    for r in rows('collections'):
        score_ids=[uid('scores',x['score_id']) for x in sorted(items,key=lambda x:x.get('position',0)) if x['collection_id']==r['id']]
        state['collections'].append({'id':uid('collection',r['id']),'name':r.get('name') or '가져온 악보집','scoreIds':score_ids,'legacy':r})
    for r in rows('review_events'):
        state['reviews'].append({'id':uid('review',r['id']),'legacy':r})
    # Retain every legacy table for lossless archival, including setlists and image paths.
    legacy_tables={t:rows(t) for t in tables if not t.startswith('sqlite_')}
    conn.close()
    return {'format':'worship-guide-backup','state':state,'assets':assets,'legacyTables':legacy_tables,'warnings':warnings}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('database');parser.add_argument('output');parser.add_argument('--asset-root')
    a=parser.parse_args()
    if Path(a.database).resolve()==Path(a.output).resolve():parser.error('출력 파일은 원본 DB와 달라야 합니다.')
    result=convert(a.database,a.asset_root)
    # Exclusive creation avoids accidental overwrite of an earlier backup.
    with open(a.output,'x',encoding='utf-8') as f:json.dump(result,f,ensure_ascii=False)
    print(f"{len(result['state']['songs'])}곡 / {len(result['state']['scores'])}악보 변환. 원본 DB 변경 없음.")
    for warning in result['warnings']:print(warning)

if __name__=='__main__':main()
