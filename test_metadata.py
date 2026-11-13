import sqlite3
import unittest
from video_metadata import migrate,save,publication

class MetadataTests(unittest.TestCase):
    def test_dates(self):
        self.assertEqual(publication({'timestamp':0,'upload_date':'20261113'}),'2026-11-13（平台仅提供日期）')
        self.assertEqual(publication({'timestamp':1}),'1970-01-01 08:00:01 北京时间')
        self.assertIsNone(publication({'upload_date':'unknown'}))

    def test_refresh_preserves_job_and_invalidates_changed_title(self):
        c=sqlite3.connect(':memory:'); c.row_factory=sqlite3.Row
        c.execute('CREATE TABLE videos(id TEXT PRIMARY KEY,url TEXT,title TEXT,thumb TEXT,duration REAL,state TEXT DEFAULT "waiting")')
        migrate(c); migrate(c)
        save(c,'1','https://example.com',{'title':'Old','uploader':'Player','upload_date':'20261113'})
        c.execute('UPDATE videos SET state="done",title_zh="旧标题"')
        save(c,'1','https://example.com',{'title':'Old'})
        self.assertEqual(c.execute('SELECT title_zh FROM videos').fetchone()[0],'旧标题')
        save(c,'1','https://example.com',{'title':'New'})
        row=c.execute('SELECT * FROM videos').fetchone()
        self.assertEqual(row['state'],'done')
        self.assertEqual(row['publisher'],'Player')
        self.assertIsNone(row['title_zh'])
        self.assertEqual(c.execute('SELECT count(*) FROM videos').fetchone()[0],1)
        c.close()
