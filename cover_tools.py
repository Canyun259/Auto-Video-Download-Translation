"""Download the platform thumbnail as a validated JPEG, without blocking encoding."""
from io import BytesIO
from urllib.parse import urlparse
import warnings
import requests
from PIL import Image
from media_tools import safe_error

def save_cover(folder, url):
    destination = folder/'cover.jpg'
    warning = folder/'cover-warning.txt'
    temporary = folder/'cover.tmp.jpg'
    try:
        if destination.exists():
            with Image.open(destination) as image:
                image.verify()
            warning.unlink(missing_ok=True)
            return True
        if urlparse(url or '').scheme not in {'https','http'}:
            raise ValueError('平台未提供可下载的封面链接')
        content = bytearray()
        with requests.get(url, stream=True, timeout=(10,30)) as response:
            response.raise_for_status()
            for chunk in response.iter_content(65536):
                content.extend(chunk)
                if len(content)>20*1024*1024:
                    raise ValueError('封面超过 20 MB')
        with warnings.catch_warnings():
            warnings.simplefilter('error',Image.DecompressionBombWarning)
            with Image.open(BytesIO(content)) as image:
                image.convert('RGB').save(temporary,format='JPEG',quality=95)
        temporary.replace(destination)
        warning.unlink(missing_ok=True)
        return True
    except Exception as exc:
        temporary.unlink(missing_ok=True)
        warning.write_text('封面保存失败：'+safe_error(exc),encoding='utf-8')
        return False
