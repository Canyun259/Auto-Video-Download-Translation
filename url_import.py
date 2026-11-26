"""Import one online video without changing account monitoring or checkpoints."""
from contextlib import closing
import hashlib
from urllib.parse import urlparse
from yt_dlp import YoutubeDL
from youtube_guard import extract_video, rate_limited, YouTubeCooldown
from media_tools import safe_error
from video_metadata import save, update_publication


def fetch_video_info(url, options):
    url = url.strip()
    if not url:
        raise ValueError('请先填写视频地址')
    parsed = urlparse(url)
    hosts = {'youtube.com', 'www.youtube.com', 'youtu.be', 'x.com', 'www.x.com',
             'twitter.com', 'www.twitter.com', 'instagram.com', 'www.instagram.com'}
    if parsed.scheme != 'https' or parsed.hostname not in hosts or parsed.username or parsed.password:
        raise ValueError('请填写 YouTube、X 或 Instagram 的单条视频 HTTPS 地址')
    # Avoid extracting a whole channel or playlist for a one-video import.
    item = extract_video(url, {**options, 'noplaylist': True, 'playlistend': 1,
                         'skip_download': True, 'extract_flat': False,
                         'ignoreerrors': False}, download=False, factory=YoutubeDL)
    if not item:
        raise ValueError('未获取到视频信息，请确认链接有效且视频可以访问')
    if item.get('entries') is not None or item.get('_type') in {'playlist', 'multi_video'}:
        raise ValueError('该地址包含多个视频或属于账号/播放列表，请提供单条视频地址')
    if item.get('is_live') or item.get('live_status') in {'is_live', 'is_upcoming'}:
        raise ValueError('该视频正在直播或尚未开播，请在直播结束后再导入')
    if not item.get('id') or not (item.get('formats') or item.get('url')):
        raise ValueError('该地址没有可用的视频，可能是图文内容或视频已不可访问')
    return item


def import_url(connect, url, options):
    url = url.strip()
    item = fetch_video_info(url, options)
    link = item.get('webpage_url') or item.get('original_url') or url
    ident = hashlib.sha256((str(item.get('extractor_key'))+':'+str(item['id'])).encode()).hexdigest()[:24]
    with closing(connect()) as c, c:
        existing = c.execute('SELECT id,hidden FROM videos WHERE id=? OR url IN (?,?) LIMIT 1',
                             (ident, link, url)).fetchone()
        if existing:
            if existing[1]:
                raise ValueError('该视频之前已被手动删除，当前已设置为不再入库')
            update_publication(c, existing[0], item)
            return existing[0], False
        if not save(c, ident, link, item):
            raise ValueError('该视频已被设置为不再入库')
    return ident, True


def import_error(exc, action='导入'):
    detail = safe_error(exc)
    lower = str(exc).lower()
    if isinstance(exc, YouTubeCooldown) or rate_limited(exc):
        hint = 'YouTube 会话触发限流时应暂停约一小时，避免继续检测或重试；这不表示视频已被删除。'
    elif any(s in lower for s in ('login', 'sign in', 'cookies', 'private', 'authentication', 'feedback_required', 'confirm you', '403')):
        hint = '请在浏览器确认视频可访问并完成登录/验证，必要时更新本地 Cookies。'
    elif any(s in lower for s in ('timed out', 'timeout', 'proxy', 'ssl eof', 'connection', 'resolve', 'network')):
        hint = '请检查网络及左侧代理设置，确认代理可用后重试。'
    elif any(s in lower for s in ('404', 'not found', 'removed', 'unavailable')):
        hint = '请确认视频未被删除，且当前账号和地区有访问权限。'
    elif '429' in lower or 'too many requests' in lower:
        hint = '平台请求过于频繁，请稍后重试。'
    elif 'unsupported url' in lower:
        hint = '下载器无法解析此地址，请复制单条视频的完整页面链接。'
    else:
        hint = ''
    return action+'失败：'+detail+ ('\n\n'+hint if hint else '')
