"""Shared, persistent YouTube cooldown for scanning, importing and downloading."""
from contextlib import contextmanager, nullcontext
import json
import math
from pathlib import Path
import threading
import time
from urllib.parse import urlparse

LOCK = threading.RLock()


def is_youtube(url):
    host = (urlparse(url).hostname or '').lower()
    return host == 'youtu.be' or host == 'youtube.com' or host.endswith('.youtube.com')


def rate_limited(error):
    message = str(error).lower()
    return any(value in message for value in ('rate-limited', 'rate limited', 'too many requests', 'http error 429', 'http status 429'))


class YouTubeCooldown(RuntimeError):
    pass


def remaining(path):
    if not path: return 0
    try:
        until = float(json.loads(Path(path).read_text(encoding='utf-8'))['until'])
        return max(0, math.ceil(until-time.time())) if math.isfinite(until) else 0
    except (OSError, ValueError, KeyError, TypeError):
        return 0


def cooldown_message(seconds):
    return f'YouTube 当前会话请求过于频繁，已暂停 YouTube 请求；约 {math.ceil(seconds/60)} 分钟后可重试。请勿反复点击检测或重试，其他平台不受影响。'


def pause(path):
    from review_tools import atomic_json
    if path:
        path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
        atomic_json(path, {'until': time.time()+3600})


@contextmanager
def download_session(url, options, factory=None):
    if factory is None:
        from yt_dlp import YoutubeDL
        factory = YoutubeDL
    options = dict(options)
    path = options.pop('_youtube_guard_path', None)
    youtube = is_youtube(url)
    with LOCK if youtube else nullcontext():
        if youtube:
            seconds = remaining(path)
            if seconds:
                raise YouTubeCooldown(cooldown_message(seconds))
            # yt-dlp's recommended sleep preset, also used for metadata requests.
            options.update(sleep_interval_requests=0.75, sleep_interval=10,
                           max_sleep_interval=20, sleep_interval_subtitles=5)
        try:
            with factory(options) as downloader:
                yield downloader
        except Exception as exc:
            if youtube and rate_limited(exc):
                pause(path)
                raise YouTubeCooldown(cooldown_message(3600)) from exc
            raise


def extract_video(url, options, *, download, factory=None):
    """Allow one top-level reconnect if a YouTube TLS stream closes early."""
    for attempt in range(2):
        try:
            with download_session(url, options, factory) as downloader:
                return downloader.extract_info(url, download=download)
        except YouTubeCooldown:
            raise
        except Exception as exc:
            if not is_youtube(url) or 'unexpected_eof_while_reading' not in str(exc).lower():
                raise
            if attempt:
                raise ConnectionError(
                    'YouTube 安全连接提前断开（SSL EOF），自动重试后仍未恢复。'
                    '请检查当前代理连接，恢复后可重试，程序会保留已有下载片段。'
                ) from exc
            time.sleep(2)
