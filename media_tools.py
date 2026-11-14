"""Resolve local media tools and retain useful, redacted download errors."""
import os, shutil, re
from pathlib import Path

def ffmpeg_path():
    bundled=Path(__file__).resolve().parent/'tools'/'bin'/'ffmpeg.exe'
    if bundled.is_file() and bundled.with_name('ffprobe.exe').is_file(): return str(bundled)
    found=shutil.which('ffmpeg')
    if found: return found
    root=Path(os.environ.get('LOCALAPPDATA',Path.home()/'AppData'/'Local'))/'Microsoft'/'WinGet'/'Packages'
    candidates=sorted(root.glob('Gyan.FFmpeg_*/ffmpeg-*/bin/ffmpeg.exe'))
    return str(candidates[-1]) if candidates else 'ffmpeg'

def download_options():
    path=ffmpeg_path()
    options={}
    if Path(path).is_file(): options['ffmpeg_location']=str(Path(path).parent)
    node=shutil.which('node')
    if node: options['js_runtimes']={'node':{'path':node}}
    return options

def safe_error(exc):
    message=re.sub(r'\x1b\[[0-9;]*m','',str(exc))
    message=re.sub(r'https?://\S+','[链接已省略]',message)
    message=re.sub(r'(?i)(authorization|cookie|token|sessionid)\s*[:=]\s*\S+',r'\1=[已隐藏]',message)
    return type(exc).__name__+'：'+' '.join(message.split())[:1200]
