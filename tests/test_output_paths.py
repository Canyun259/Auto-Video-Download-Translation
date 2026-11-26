import sqlite3
from contextlib import closing
import tempfile
import unittest
from pathlib import Path
from output_paths import clean_name, output_folder, migrate_existing, checked
from video_metadata import migrate

class OutputTests(unittest.TestCase):
    def test_invalid_names(self):
        self.assertEqual(clean_name('CON'), '_CON')
        self.assertNotIn('/', clean_name('a/b'))
        self.assertNotIn('\\', clean_name('a\\b'))
        with self.assertRaises(ValueError):
            checked(Path.cwd(), '../escape')

    def test_persist_and_migrate(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as tmp:
            data=Path(tmp)
            with closing(sqlite3.connect(data/'library.sqlite')) as c, c:
                c.execute('CREATE TABLE videos(id TEXT PRIMARY KEY,url TEXT,title TEXT,state TEXT)')
                migrate(c)
                c.execute("INSERT INTO videos(id,url,title,state,publisher,published_at,title_zh) VALUES(?,?,?,?,?,?,?)",
                          ('1234567890abcdef','https://youtube.com/watch?v=sample','Original','done','Team','2026-11-13','中文标题'))
                c.commit()
                c.row_factory=sqlite3.Row
                row=c.execute('SELECT * FROM videos').fetchone()
            old=data/'output'/row['id']
            old.mkdir(parents=True)
            (old/'result.mp4').write_bytes(b'test')
            self.assertEqual(output_folder(data,row),old)
            self.assertEqual(migrate_existing(data),1)
            path=output_folder(data,row,create=True)
            self.assertIn('中文标题',path.name)
            self.assertEqual((path/'result.mp4').read_bytes(),b'test')
            changed=dict(row);changed['title_zh']='新标题'
            self.assertEqual(output_folder(data,changed),path)
            self.assertEqual(migrate_existing(data),0)

if __name__=='__main__': unittest.main()

