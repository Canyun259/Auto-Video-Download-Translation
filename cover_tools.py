"""Save a platform thumbnail or a frame from a local video as cover.jpg."""
from io import BytesIO
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
from urllib.parse import urlparse
import warnings

import requests
from PIL import Image

from media_tools import ffmpeg_path, safe_error

LOCAL_VIDEO_EXTENSIONS = {'.mp4', '.mkv', '.mov', '.webm', '.avi', '.m4v'}


def download_thumbnail(url, destination, proxy):
    parsed = urlparse(url or '')
    if parsed.scheme not in {'https','http'} or not parsed.hostname:
        raise ValueError('平台未提供可下载的封面链接')
    options = {'proxies': {'http': proxy, 'https': proxy}} if proxy else {}
    content = bytearray()
    with requests.get(url, stream=True, timeout=(10,30), **options) as response:
        response.raise_for_status()
        for chunk in response.iter_content(65536):
            content.extend(chunk)
            if len(content) > 20 * 1024 * 1024:
                raise ValueError('封面超过 20 MB')
    with warnings.catch_warnings():
        warnings.simplefilter('error', Image.DecompressionBombWarning)
        with Image.open(BytesIO(content)) as image:
            image.convert('RGB').save(destination, format='JPEG', quality=95)


def extract_cover_frame(folder, destination):
    source = next((p for p in folder.glob('source.*')
                   if p.is_file() and p.suffix.lower() in LOCAL_VIDEO_EXTENSIONS), None)
    if source is None:
        raise ValueError('找不到原视频，无法提取封面')
    result = subprocess.run(
        [ffmpeg_path(), '-nostdin', '-v', 'error', '-i', str(source), '-map', '0:V:0',
         '-vf', "scale='min(1280,iw)':-2,thumbnail=12", '-frames:v', '1',
         '-q:v', '2', '-update', '1', '-y', str(destination)],
        capture_output=True, timeout=30,
    )
    if result.returncode or not destination.is_file():
        raise ValueError('无法从原视频提取画面')


def verify_jpeg(path):
    with Image.open(path) as image:
        if image.format != 'JPEG':
            raise ValueError('封面文件不是 JPEG')
        image.verify()


def save_cover(folder, url, *, from_local_video=False, proxy=None):
    destination = folder/'cover.jpg'
    warning = folder/'cover-warning.txt'
    try:
        if destination.exists():
            try:
                verify_jpeg(destination)
            except (OSError, ValueError, SyntaxError):
                pass
            else:
                warning.unlink(missing_ok=True)
                return True
        with TemporaryDirectory(dir=folder, prefix='cover-') as stage_dir:
            staging = Path(stage_dir)/'cover.jpg'
            if from_local_video:
                extract_cover_frame(folder, staging)
            else:
                download_thumbnail(url, staging, proxy)
            verify_jpeg(staging)
            staging.replace(destination)
        warning.unlink(missing_ok=True)
        return True
    except Exception as exc:
        try:
            warning.write_text('封面保存失败：'+safe_error(exc),encoding='utf-8')
        except OSError:
            pass
        return False
