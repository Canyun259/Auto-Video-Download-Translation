"""Persistent library dismissal and conservative incremental discovery."""
from datetime import datetime,timezone,timedelta
import time


def dismiss(c,ident):
    # A tombstone stays in the database, preserving both ID and URL deduplication.
    cursor=c.execute("UPDATE videos SET hidden=1,deleted_at=? WHERE id=? AND hidden=0 AND state IN ('waiting','review','done')",(time.time(),ident))
    return cursor.rowcount==1


def checkpoint(c,url):
    row=c.execute('SELECT since FROM manual_scan_checkpoints WHERE url=?',(url,)).fetchone()
    return row[0] if row else None


def complete_scan(c,url,started):
    c.execute('INSERT INTO manual_scan_checkpoints(url,since,completed_at) VALUES(?,?,?) ON CONFLICT(url) DO UPDATE SET since=MAX(manual_scan_checkpoints.since,excluded.since),completed_at=excluded.completed_at',(url,started,time.time()))


def manual_history(c):
    return c.execute('SELECT url,since FROM manual_scan_checkpoints ORDER BY since DESC').fetchall()


def is_new(item,since):
    if since is None: return True
    stamp=item.get('timestamp')
    if stamp is None: stamp=item.get('release_timestamp')
    if stamp is not None:
        try: return float(stamp)>since
        except (ValueError,TypeError): pass
    date=item.get('upload_date') or item.get('release_date')
    if date:
        try:
            # Date-only metadata must retain the entire boundary day.
            end=datetime.strptime(str(date),'%Y%m%d').replace(tzinfo=timezone.utc)+timedelta(days=1)
            return end.timestamp()>since
        except (ValueError,TypeError): pass
    return True  # Missing dates must not silently lose videos.


def excluded(c,ident=None,url=None):
    return c.execute('SELECT 1 FROM videos WHERE hidden=1 AND (id=? OR url=?) LIMIT 1',(ident,url)).fetchone() is not None
