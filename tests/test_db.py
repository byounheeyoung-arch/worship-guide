from pathlib import Path
from worship_guide.db import WGDB

def test_song_score_variants(tmp_path: Path):
    db=WGDB(tmp_path/'t.db')
    sid=db.save_song({'title':'예수 닮기를'})
    db.save_score(sid,{'arrangement':'Original','key_signature':'E','page_start':1})
    db.save_score(sid,{'arrangement':'Original','key_signature':'F','page_start':2})
    db.save_score(sid,{'arrangement':'Original','key_signature':'G','page_start':3})
    rows=db.list_scores(sid)
    assert len(rows)==3
    assert [r['key_signature'] for r in rows]==['E','F','G']
    songs=db.list_songs('예수')
    assert len(songs)==1
    assert set((songs[0]['available_keys'] or '').split(','))=={'E','F','G'}
    db.close()
