"""Initialize each database once per process, outside frequent progress writes."""
import threading,sqlite3
from video_metadata import migrate
_LOCK=threading.Lock()
_READY=set()


def ensure_schema(c):
    path=c.execute('PRAGMA database_list').fetchone()[2]
    with _LOCK:
        if path and path in _READY: return
        c.execute('PRAGMA journal_mode=WAL')
        c.execute('CREATE TABLE IF NOT EXISTS videos(id TEXT PRIMARY KEY,url TEXT,title TEXT,thumb TEXT,duration REAL,state TEXT DEFAULT "waiting",error TEXT DEFAULT "",ocr INTEGER DEFAULT 0)')
        c.execute('CREATE TABLE IF NOT EXISTS settings(id INTEGER PRIMARY KEY,body TEXT)')
        migrate(c)
        columns={r[1] for r in c.execute('PRAGMA table_info(videos)')}
        for name,kind in {'output_mode':"TEXT DEFAULT 'burn'",'subtitle_display':"TEXT DEFAULT 'bilingual'",'prefer_subtitles':'INTEGER DEFAULT 1'}.items():
            if name not in columns: c.execute(f'ALTER TABLE videos ADD COLUMN {name} {kind}')
        c.commit()
        if path: _READY.add(path)


class ManagedConnection(sqlite3.Connection):
    def __exit__(self,*args):
        try: return super().__exit__(*args)
        finally: self.close()
