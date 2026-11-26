import ast,hashlib,sqlite3,tempfile,time,unittest
from pathlib import Path
from urllib.parse import urlparse
from unittest.mock import patch,MagicMock
from video_metadata import migrate,save
from library_store import dismiss,excluded,checkpoint,complete_scan,is_new
from database_setup import ensure_schema,ManagedConnection

class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.path=Path(self.tmp.name)/'library.sqlite'
        with self.connect() as c: ensure_schema(c)
    def tearDown(self): self.tmp.cleanup()
    def connect(self):
        c=sqlite3.connect(self.path,factory=ManagedConnection);c.row_factory=sqlite3.Row
        return c
    def add(self,ident,state):
        with self.connect() as c:
            save(c,ident,'https://example.com/'+ident,{'title':ident})
            c.execute('UPDATE videos SET state=? WHERE id=?',(state,ident))
    def test_dismiss_persists_and_prevents_both_id_and_url_reimport(self):
        for state in ['waiting','review','done']:
            self.add(state,state)
            with self.connect() as c: self.assertTrue(dismiss(c,state))
            with self.connect() as c:
                self.assertTrue(excluded(c,state))
                self.assertFalse(save(c,state,'https://example.com/'+state,{'title':'Again'}))
                self.assertFalse(save(c,state+'-alias','https://example.com/'+state,{'title':'Again'}))
                self.assertEqual(c.execute('SELECT state FROM videos WHERE id=?',(state,)).fetchone()[0],state)
        with self.connect() as c: self.assertEqual(c.execute('SELECT COUNT(*) FROM videos WHERE hidden=0').fetchone()[0],0)
    def test_active_job_not_deleted_and_files_preserved(self):
        self.add('active','queued');self.add('done','done')
        artifact=Path(self.tmp.name)/'result.mp4';artifact.write_bytes(b'keep')
        with self.connect() as c:
            self.assertFalse(dismiss(c,'active'))
            self.assertTrue(dismiss(c,'done'))
        self.assertEqual(artifact.read_bytes(),b'keep')
    def test_dates_and_checkpoints(self):
        with self.connect() as c:
            self.assertIsNone(checkpoint(c,'a'));complete_scan(c,'a',100);complete_scan(c,'b',200);complete_scan(c,'a',90)
            self.assertEqual(checkpoint(c,'a'),100);self.assertEqual(checkpoint(c,'b'),200)
        self.assertFalse(is_new({'timestamp':100},100))
        self.assertTrue(is_new({'timestamp':101},100))
        self.assertTrue(is_new({},100))
        self.assertTrue(is_new({'upload_date':'19700101'},100))
        self.assertFalse(is_new({'upload_date':'19700101'},90000))
    def test_legacy_automatic_checkpoint_not_used_for_manual_scan(self):
        with self.connect() as c:
            c.execute('INSERT INTO scan_checkpoints VALUES(?,?,?)',('a',9999,9999))
            self.assertIsNone(checkpoint(c,'a'))
            complete_scan(c,'a',100)
            self.assertEqual(checkpoint(c,'a'),100)
            self.assertEqual(c.execute('SELECT since FROM scan_checkpoints WHERE url=?',('a',)).fetchone()[0],9999)
    def test_discovery_success_failure_and_cutoff(self):
        tree=ast.parse((Path(__file__).resolve().parents[1] / 'local_ui.py').read_text(encoding='utf-8'))
        funcs=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in {'discover','entries','valid_url'}]
        ns={'db':self.connect,'urlparse':urlparse,'hashlib':hashlib,'time':time,'opts':lambda:{},'translate_title':lambda ident:None}
        exec(compile(ast.Module(body=funcs,type_ignores=[]),'local_ui.py','exec'),ns)
        url='https://www.youtube.com/@test/shorts'
        def item(ident,stamp): return {'id':ident,'extractor_key':'Youtube','webpage_url':'https://www.youtube.com/watch?v='+ident,'title':ident,'timestamp':stamp}
        with self.connect() as c: complete_scan(c,url,100)
        loader=MagicMock();loader.__enter__.return_value=loader
        loader.extract_info.return_value={'entries':[item('old',50),item('new',time.time()+10)]}
        with patch('yt_dlp.YoutubeDL',return_value=loader) as factory:
            ns['discover'](url,20,started=200)
            self.assertEqual(factory.call_args.args[0]['extract_flat'],'in_playlist')
        with self.connect() as c:
            self.assertEqual(c.execute('SELECT title FROM videos').fetchone()[0],'new')
            before=checkpoint(c,url);self.assertEqual(before,200)
        # Flat uploads reuse the channel header without fetching each video.
        channel_id = 'UC1234567890123456789012'
        loader.extract_info.return_value = {
            'id':channel_id, 'channel_id':channel_id, 'channel':'Test channel',
            'uploader_url':'https://www.youtube.com/@test',
            'entries': [
                {'id':'new','ie_key':'Youtube','url':'https://www.youtube.com/watch?v=new','title':'new',
                 'thumbnails':[{'url':'https://example.com/thumb.jpg'}]},
                {'id':'older','ie_key':'Youtube','url':'https://www.youtube.com/watch?v=older',
                 'title':'Test title','timestamp':50},
            ],
        }
        older_id = hashlib.sha256(b'Youtube:older').hexdigest()[:24]
        with self.connect() as c:
            save(c, older_id, 'https://www.youtube.com/watch?v=older', {'title':'Original title'})
            c.execute("UPDATE videos SET title_zh='已有译名' WHERE id=?", (older_id,))
        loader.extract_info.reset_mock()
        with patch('yt_dlp.YoutubeDL',return_value=loader): ns['discover'](url,20)
        loader.extract_info.assert_called_once_with(url,download=False)
        with self.connect() as c:
            self.assertEqual(c.execute('SELECT count(*) FROM videos').fetchone()[0],2)
            known=c.execute("SELECT thumb,publisher,published_at FROM videos WHERE title='new'").fetchone()
            self.assertEqual(known['thumb'],'https://example.com/thumb.jpg')
            self.assertEqual(known['publisher'],'Test channel')
            self.assertIsNotNone(known['published_at'])
            older=c.execute('SELECT title_zh,publisher,published_at FROM videos WHERE id=?',(older_id,)).fetchone()
            self.assertEqual(tuple(older), ('已有译名','Test channel','1970-01-01 08:00:50 北京时间'))
            before=checkpoint(c,url)
        loader.extract_info.side_effect=RuntimeError('network down')
        with patch('yt_dlp.YoutubeDL',return_value=loader),self.assertRaises(RuntimeError): ns['discover'](url,20)
        with self.connect() as c: self.assertEqual(checkpoint(c,url),before)

if __name__=='__main__': unittest.main()
