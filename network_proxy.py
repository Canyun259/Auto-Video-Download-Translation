"""Use one explicit media proxy across download and discovery clients."""
import os
from urllib.request import getproxies
from urllib.parse import urlparse


def validate_proxy(value):
    if not value: return
    parsed=urlparse(value)
    if parsed.scheme not in {'http','https'} or not parsed.hostname:
        raise ValueError('代理地址请使用 http://主机:端口 或 https://主机:端口')
    try: parsed.port
    except ValueError: raise ValueError('代理端口无效') from None


def media_proxy(configured=''):
    value=configured.strip() or os.getenv('VIDEO_PROXY','').strip()
    if not value:
        proxies=getproxies()
        value=proxies.get('https') or proxies.get('http') or proxies.get('all') or ''
    if value and '://' not in value: value='http://'+value
    validate_proxy(value)
    return value


def apply_instagram_proxy(loader,proxy):
    # Call after load_session_from_file, which replaces the requests session.
    if proxy:
        loader.context._session.trust_env=False
        loader.context._session.proxies.update({'http':proxy,'https':proxy})
