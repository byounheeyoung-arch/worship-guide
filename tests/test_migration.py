import importlib.util
import hashlib
import sqlite3
import tempfile
import unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location('migrate',Path(__file__).parents[1]/'scripts/migrate_legacy.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class MigrationTest(unittest.TestCase):
 def test_both_schemas_and_original_unchanged(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'legacy.db';c=sqlite3.connect(p)
   c.executescript("""CREATE TABLE songs(id INTEGER,title TEXT,lyrics TEXT,memo TEXT);INSERT INTO songs VALUES(1,'은혜','가사','메모');CREATE TABLE arrangements(id INTEGER,song_id INTEGER,name TEXT);INSERT INTO arrangements VALUES(1,1,'Original');CREATE TABLE scores(id INTEGER,arrangement_id INTEGER,page_start INTEGER,page_end INTEGER,key_signature TEXT);INSERT INTO scores VALUES(1,1,1,2,'C');CREATE TABLE score_variants(id INTEGER,arrangement_id INTEGER,start_page INTEGER,end_page INTEGER,key_signature TEXT,review_status TEXT);INSERT INTO score_variants VALUES(1,1,3,3,'D','reviewed');CREATE TABLE collections(id INTEGER,name TEXT);INSERT INTO collections VALUES(1,'주일');CREATE TABLE collection_items(collection_id INTEGER,score_id INTEGER,position INTEGER);INSERT INTO collection_items VALUES(1,1,1);""")
   c.close();before=hashlib.sha256(p.read_bytes()).hexdigest();result=m.convert(p)
   self.assertEqual(before,hashlib.sha256(p.read_bytes()).hexdigest())
   self.assertEqual(len(result['state']['scores']),2)
   self.assertNotEqual(result['state']['scores'][0]['id'],result['state']['scores'][1]['id'])
   self.assertEqual(result['state']['songs'][0]['lyrics'],'가사')
   self.assertEqual(result['state']['songs'][0]['notes'],'메모')
   self.assertEqual(result['state']['collections'][0]['scoreIds'],[result['state']['scores'][0]['id']])
   self.assertEqual(result['state']['scores'][1]['status'],'reviewed')
   self.assertEqual(m.convert(p),result)
 def test_missing_db_not_created(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'missing.db'
   with self.assertRaises(sqlite3.OperationalError):m.convert(p)
   self.assertFalse(p.exists())
if __name__=='__main__':unittest.main()
