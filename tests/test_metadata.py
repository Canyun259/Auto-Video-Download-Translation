import sqlite3
import unittest
from video_metadata import migrate,save,publication,youtube_channel_publisher

class MetadataTests(unittest.TestCase):
    def test_dates(self):
        self.assertEqual(publication({'timestamp':0,'upload_date':'20261113'}),'2026-11-13（平台仅提供日期）')
        self.assertEqual(publication({'timestamp':1}),'1970-01-01 08:00:01 北京时间')
        self.assertIsNone(publication({'upload_date':'unknown'}))

    def test_refresh_preserves_job_and_invalidates_changed_title(self):
        c=sqlite3.connect(':memory:'); c.row_factory=sqlite3.Row
        c.execute('CREATE TABLE videos(id TEXT PRIMARY KEY,url TEXT,title TEXT,thumb TEXT,duration REAL,state TEXT DEFAULT "waiting")')
        migrate(c); migrate(c)
        save(c,'1','https://example.com',{'title':'Old','uploader':'Player','timestamp':1})
        c.execute('UPDATE videos SET state="done",title_zh="旧标题"')
        save(c,'1','https://example.com',{'title':'Old','upload_date':'19700101'},
             channel_publisher=('Channel owner','https://example.com/channel'))
        row=c.execute('SELECT title_zh,publisher,publisher_url,published_at FROM videos').fetchone()
        self.assertEqual(tuple(row), ('旧标题','Player',None,'1970-01-01 08:00:01 北京时间'))
        save(c,'1','https://example.com',{'title':'New'})
        row=c.execute('SELECT * FROM videos').fetchone()
        self.assertEqual(row['state'],'done')
        self.assertEqual(row['publisher'],'Player')
        self.assertIsNone(row['title_zh'])
        self.assertEqual(c.execute('SELECT count(*) FROM videos').fetchone()[0],1)
        c.close()

    def test_curated_playlists_do_not_borrow_channel_owner(self):
        channel='UC1234567890123456789012'
        results={'id':channel,'channel_id':channel,'channel':'Host','entries':[]}
        for url in ('https://www.youtube.com/@host/playlists',
                    'https://www.youtube.com/playlist?list=PL123',
                    'https://www.youtube.com/@host/videos?list=PL123'):
            with self.subTest(url=url):
                self.assertEqual(youtube_channel_publisher(url, results),(None,None))
        playlist={**results,'id':'PL123'}
        self.assertEqual(youtube_channel_publisher('https://www.youtube.com/@host',playlist),(None,None))
