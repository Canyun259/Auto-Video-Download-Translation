"""Readable, stable output paths; database IDs remain internal."""
import re
import sqlite3
from contextlib import closing
import threading
from pathlib import Path
from urllib.parse import urlparse

_LOCK = threading.RLock()

def clean_name(value, limit=48):
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', str(value or ''))
    text = re.sub(r'\s+', ' ', text).strip(' .')[:limit].rstrip(' .')
    if not text:
        text = '未命名'
    if re.fullmatch(r'(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?', text):
        text = '_' + text
    return text

def readable_path(row):
    row = dict(row)
    host = urlparse(row.get('url') or '').hostname or ''
    platform = 'Instagram' if host.endswith('instagram.com') else 'YouTube' if host.endswith('youtube.com') or host == 'youtu.be' else 'X'
    if (row.get('url') or '').startswith('local://'): platform = '本地视频'
    date = (row.get('published_at') or '')[:10]
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', date):
        date = '日期未知'
    title = clean_name(row.get('title_zh') or row.get('title'), 48)
    publisher = clean_name(row.get('publisher') or '未知账号', 28)
    return Path(platform) / publisher / (date + '_' + title + '_' + str(row['id'])[:10])

def checked(root, relative):
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()) or path == root.resolve():
        raise ValueError('输出路径必须位于 output 目录内')
    return path

def output_folder(data, row, create=False):
    """Persist on first download; title edits never orphan existing files."""
    with _LOCK, closing(sqlite3.connect(data/'library.sqlite', timeout=30)) as c, c:
        saved = c.execute('SELECT output_dir FROM videos WHERE id=?', (row['id'],)).fetchone()
        if not saved:
            raise ValueError('视频记录不存在')
        root = data/'output'
        legacy = checked(root, str(row['id']))
        if saved[0]:
            path = checked(root, saved[0])
        elif legacy.exists():
            path = legacy
        else:
            path = checked(root, readable_path(row))
        if create:
            path.mkdir(parents=True, exist_ok=True)
            c.execute('UPDATE videos SET output_dir=? WHERE id=?', (path.relative_to(root.resolve()).as_posix(), row['id']))
        return path

def migrate_existing(data):
    """Only call while the service is stopped."""
    from video_metadata import migrate
    with closing(sqlite3.connect(data/'library.sqlite', timeout=30)) as c, c:
        c.row_factory = sqlite3.Row
        migrate(c)
        rows = c.execute('SELECT * FROM videos').fetchall()
        active = [r for r in rows if r['state'] not in {'waiting','review','done','failed','queued','burn_queued'}]
        if active:
            raise RuntimeError('有未结束任务，暂不整理目录')
        count = 0
        root = data/'output'
        for row in rows:
            old = checked(root, str(row['id']))
            if not old.is_dir() or (row['output_dir'] and row['output_dir'] != row['id']):
                continue
            new = checked(root, readable_path(row))
            if new.exists():
                raise FileExistsError('目标目录已存在，未覆盖：' + str(new))
            new.parent.mkdir(parents=True, exist_ok=True)
            old.rename(new)
            try:
                c.execute('UPDATE videos SET output_dir=? WHERE id=?', (new.relative_to(root.resolve()).as_posix(), row['id']))
                c.commit()
            except Exception:
                new.rename(old)
                raise
            count += 1
        return count

if __name__ == '__main__':
    import launcher
    if launcher.processes():
        raise SystemExit('请先停止视频翻译台，再运行目录整理。')
    data = Path(__file__).resolve().parent/'local-data'
    if not (data/'library.sqlite').exists():
        raise SystemExit('没有需要整理的历史数据。')
    print('已整理视频目录：', migrate_existing(data))

