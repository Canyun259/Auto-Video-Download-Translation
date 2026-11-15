"""Video metadata storage and presentation."""
from datetime import datetime, timezone, timedelta
import threading
LOCK=threading.Lock()
COLUMNS={'output_dir':'TEXT','publisher':'TEXT','publisher_url':'TEXT','published_at':'TEXT','title_zh':'TEXT','title_error':'TEXT','progress':'REAL DEFAULT 0','hidden':'INTEGER NOT NULL DEFAULT 0','deleted_at':'REAL'}

def migrate(c):
    with LOCK:
        columns={r[1] for r in c.execute('PRAGMA table_info(videos)')}
        for name,kind in COLUMNS.items():
            if name not in columns: c.execute(f'ALTER TABLE videos ADD COLUMN {name} {kind}')
        c.execute('CREATE TABLE IF NOT EXISTS scan_checkpoints(url TEXT PRIMARY KEY,since REAL NOT NULL,completed_at REAL NOT NULL)')
        c.execute('CREATE INDEX IF NOT EXISTS videos_visible_state ON videos(hidden,state)')
        c.execute('CREATE INDEX IF NOT EXISTS videos_url ON videos(url)')
        c.commit()

def publication(item):
    stamp=item.get('timestamp') or item.get('release_timestamp')
    if stamp is not None:
        try:
            return datetime.fromtimestamp(float(stamp),timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S 北京时间')
        except (ValueError,TypeError,OverflowError,OSError): pass
    date=item.get('upload_date') or item.get('release_date')
    if date:
        try: return datetime.strptime(str(date),'%Y%m%d').strftime('%Y-%m-%d（平台仅提供日期）')
        except ValueError: pass
    return None

def save(c,ident,link,item):
    from library_store import excluded
    if excluded(c,ident,link): return False
    title=item.get('title') or '视频'
    publisher=item.get('uploader') or item.get('channel') or item.get('uploader_id') or item.get('channel_id')
    publisher_url=item.get('uploader_url') or item.get('channel_url')
    c.execute('''INSERT INTO videos(id,url,title,thumb,duration,publisher,publisher_url,published_at)
        VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
        url=excluded.url, thumb=COALESCE(excluded.thumb,videos.thumb), duration=COALESCE(excluded.duration,videos.duration),
        publisher=COALESCE(excluded.publisher,videos.publisher),publisher_url=COALESCE(excluded.publisher_url,videos.publisher_url),
        published_at=COALESCE(excluded.published_at,videos.published_at),
        title_zh=CASE WHEN videos.title=excluded.title THEN videos.title_zh ELSE NULL END,
        title_error=CASE WHEN videos.title=excluded.title THEN videos.title_error ELSE NULL END,
        title=excluded.title''',(ident,link,title,item.get('thumbnail'),item.get('duration'),publisher,publisher_url,publication(item)))
    return True
