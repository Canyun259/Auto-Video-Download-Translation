"""Video metadata storage and presentation."""
from datetime import datetime, timezone, timedelta
from urllib.parse import parse_qs, urlsplit
import threading
LOCK=threading.Lock()
COLUMNS={'output_dir':'TEXT','publisher':'TEXT','publisher_url':'TEXT','published_at':'TEXT','title_zh':'TEXT','title_error':'TEXT','progress':'REAL DEFAULT 0','hidden':'INTEGER NOT NULL DEFAULT 0','deleted_at':'REAL'}

def migrate(c):
    with LOCK:
        columns={r[1] for r in c.execute('PRAGMA table_info(videos)')}
        for name,kind in COLUMNS.items():
            if name not in columns: c.execute(f'ALTER TABLE videos ADD COLUMN {name} {kind}')
        c.execute('CREATE TABLE IF NOT EXISTS scan_checkpoints(url TEXT PRIMARY KEY,since REAL NOT NULL,completed_at REAL NOT NULL)')
        c.execute('CREATE TABLE IF NOT EXISTS manual_scan_checkpoints(url TEXT PRIMARY KEY,since REAL NOT NULL,completed_at REAL NOT NULL)')
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

def publisher_details(item):
    name = item.get('uploader') or item.get('channel') or item.get('uploader_id') or item.get('channel_id')
    url = item.get('uploader_url') or item.get('channel_url')
    return name, url


def youtube_channel_publisher(url, listing):
    """Use the channel header only for the channel's own uploads."""
    source = urlsplit(url)
    parts = source.path.strip('/').split('/')
    if 'list' in parse_qs(source.query, keep_blank_values=True):
        return None, None
    if parts[0].startswith('@'):
        tab = parts[1:]
    elif parts[0] in {'channel', 'c', 'user'} and len(parts) >= 2:
        tab = parts[2:]
    else:
        return None, None
    if tab and tab not in (['videos'], ['shorts'], ['streams']):
        return None, None
    channel_id = listing.get('channel_id')
    if not channel_id or listing.get('id') != channel_id or listing.get('entries') is None:
        return None, None
    return publisher_details(listing)


def thumbnail_url(item):
    return item.get('thumbnail') or next(
        (thumb['url'] for thumb in reversed(item.get('thumbnails') or []) if thumb.get('url')), None
    )


def update_publication(c, ident, item, channel_publisher=(None, None)):
    """Update an existing visible video without changing its title, files or task state."""
    publisher, publisher_url = publisher_details(item)
    # A video can credit a different uploader. Use the channel header only when
    # the entry has no author of its own.
    fallback, fallback_url = channel_publisher if not (publisher or publisher_url) else (None, None)
    return c.execute("""UPDATE videos SET
        thumb=COALESCE(:thumbnail,thumb),
        publisher=COALESCE(:publisher, NULLIF(publisher,''), CASE
            WHEN NULLIF(publisher_url,'') IS NULL OR publisher_url=:fallback_url THEN :fallback END),
        publisher_url=COALESCE(:publisher_url, NULLIF(publisher_url,''), CASE
            WHEN NULLIF(publisher,'') IS NULL OR publisher=:fallback THEN :fallback_url END),
        published_at=CASE
            WHEN published_at LIKE '% 北京时间' AND :published LIKE '%（平台仅提供日期）' THEN published_at
            ELSE COALESCE(:published,published_at) END
        WHERE id=:id AND hidden=0
        RETURNING publisher,publisher_url,published_at,thumb""",
        {'id': ident, 'publisher': publisher, 'publisher_url': publisher_url,
         'fallback': fallback, 'fallback_url': fallback_url, 'published': publication(item),
         'thumbnail': thumbnail_url(item)}).fetchone()


def save(c,ident,link,item,*,channel_publisher=(None,None)):
    from library_store import excluded
    if excluded(c,ident,link): return False
    title=item.get('title') or '视频'
    c.execute("""INSERT INTO videos(id,url,title,duration)
        VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET
        url=excluded.url, duration=COALESCE(excluded.duration,videos.duration),
        title_zh=CASE WHEN videos.title=excluded.title THEN videos.title_zh ELSE NULL END,
        title_error=CASE WHEN videos.title=excluded.title THEN videos.title_error ELSE NULL END,
        title=excluded.title""", (ident,link,title,item.get('duration')))
    update_publication(c, ident, item, channel_publisher)
    return True
