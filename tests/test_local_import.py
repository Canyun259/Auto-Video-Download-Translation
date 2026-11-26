from contextlib import closing
import io,sqlite3,subprocess,tempfile,unittest
from pathlib import Path
from local_import import import_video
from media_tools import ffmpeg_path
class ImportTests(unittest.TestCase):
    def test_import_and_duplicate(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);data=root/'data';data.mkdir();source=root/'sample.mp4'
            subprocess.run([ffmpeg_path(),'-y','-f','lavfi','-i','color=c=gray:s=320x240:d=1',str(source)],check=True,capture_output=True)
            def connect(): return sqlite3.connect(data/'library.sqlite')
            with closing(connect()) as c,c:c.execute('CREATE TABLE videos(id TEXT PRIMARY KEY,url TEXT,title TEXT,thumb TEXT,duration REAL,publisher TEXT,output_dir TEXT)')
            ident,created=import_video(data,connect,source)
            self.assertTrue(created);self.assertTrue(source.exists())
            with closing(connect()) as c,c: row=c.execute('SELECT url,output_dir FROM videos').fetchone()
            self.assertTrue(row[0].startswith('local://'));self.assertTrue((data/'output'/row[1]/'source.mp4').exists())
            self.assertEqual(import_video(data,connect,io.BytesIO(source.read_bytes()),'other.mp4'),(ident,False))
            with self.assertRaises(Exception):import_video(data,connect,io.BytesIO(b'bad'),'broken.mp4')
            with closing(connect()) as c,c:self.assertEqual(c.execute('SELECT count(*) FROM videos').fetchone()[0],1)
if __name__=='__main__':unittest.main()
