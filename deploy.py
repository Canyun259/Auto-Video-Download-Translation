"""Standard-library installer and diagnostics for the Windows source distribution."""
import argparse
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys
import venv

BASE=Path(__file__).resolve().parent
PYTHON=BASE/'.venv'/'Scripts'/'python.exe'


def initialize_config(base=BASE):
    target=base/'.env'
    try:
        with target.open('x',encoding='utf-8') as out:
            out.write((base/'.env.example').read_text(encoding='utf-8'))
        return True
    except FileExistsError:
        return False


def require_stopped():
    # Execute against the managed interpreter so process detection has psutil.
    if PYTHON.exists():
        result=subprocess.run([str(PYTHON),'-c',
            "import importlib.util,sys; sys.exit(2 if importlib.util.find_spec('psutil') and __import__('launcher').processes() else 0)"],cwd=BASE)
        if result.returncode:
            raise RuntimeError('Stop this project before installing or updating dependencies.')


def install(gpu=False):
    if os.name!='nt': raise RuntimeError('The one-click installer supports Windows only.')
    if sys.version_info[:2]!=(3,12): raise RuntimeError('Use Python 3.12 (64-bit) for this release.')
    if sys.maxsize<=2**32: raise RuntimeError('Use 64-bit Python.')
    require_stopped()
    if not PYTHON.exists(): venv.EnvBuilder(with_pip=True).create(BASE/'.venv')
    subprocess.run([str(PYTHON),'-c',"import sys; assert sys.version_info[:2]==(3,12), 'Existing .venv must use Python 3.12'"],check=True)
    subprocess.run([str(PYTHON),'-m','pip','install','--upgrade','pip'],check=True)
    subprocess.run([str(PYTHON),'-m','pip','install','-r',str(BASE/'requirements-local.txt')],check=True)
    if gpu:
        subprocess.run([str(PYTHON),'-m','pip','install','-r',str(BASE/'requirements-gpu.txt')],check=True)
    subprocess.run([str(PYTHON),'-m','pip','check'],check=True)
    created=initialize_config()
    print('Created .env from template.' if created else 'Preserved existing .env.')
    print('Install complete. Fill in .env, then run start-local.bat.')
    return subprocess.run([str(PYTHON),str(BASE/'deploy.py'),'doctor'],cwd=BASE).returncode


def doctor():
    from version import __version__
    from media_tools import ffmpeg_path
    print('Video Translation Console v'+__version__)
    print('Python:',sys.version.split()[0],sys.executable)
    missing=[m for m in ['streamlit','dotenv','yt_dlp','faster_whisper','cv2','rapidocr','psutil','PIL','tkinter'] if importlib.util.find_spec(m) is None]
    if missing: print('Missing modules:',', '.join(missing))
    ff=Path(ffmpeg_path())
    tools=ff.is_file() and ff.with_name('ffprobe.exe').is_file()
    print('FFmpeg + ffprobe:',str(ff) if tools else 'MISSING')
    print('Node.js:',shutil.which('node') or 'optional; recommended for YouTube')
    config=False
    if importlib.util.find_spec('dotenv'):
        from dotenv import dotenv_values
        cfg=dotenv_values(BASE/'.env')
        config=bool(cfg.get('TRANSLATE_API_KEY') and str(cfg.get('TRANSLATE_BASE_URL','')).startswith('https://') and cfg.get('TRANSLATE_MODEL'))
    print('Translation configuration:', 'ready' if config else 'fill in .env (values are never printed)')
    if not tools: print('Install FFmpeg: winget install --id Gyan.FFmpeg --exact\nOr place ffmpeg.exe and ffprobe.exe in tools/bin/.')
    return 1 if missing or not tools or not config else 0


def update():
    require_stopped()
    git=shutil.which('git')
    if not git: raise RuntimeError('Git is required for update-local.bat; ZIP users should follow docs/DEPLOYMENT.md.')
    def run(*args): return subprocess.check_output([git,*args],cwd=BASE,text=True).strip()
    if run('rev-parse','--show-toplevel').replace('\\','/').casefold()!=BASE.as_posix().casefold():
        raise RuntimeError('Run updates only inside a clone of this repository.')
    if run('status','--porcelain'): raise RuntimeError('Local code changes found. Commit or back them up before updating.')
    if run('branch','--show-current')!='main': raise RuntimeError('Automatic updates require main. For release tags, use the documented ZIP upgrade.')
    expected='github.com/canyun259/auto-video-download-translation'
    remote=run('remote','get-url','origin').lower().removesuffix('.git').rstrip('/')
    if not (remote=='https://'+expected or remote=='git@github.com:canyun259/auto-video-download-translation'):
        raise RuntimeError('Unexpected origin; update manually after reviewing your remote.')
    subprocess.run([git,'pull','--ff-only','origin','main'],cwd=BASE,check=True)
    # Read the installer from the new revision rather than retaining this module.
    subprocess.run([str(PYTHON if PYTHON.exists() else Path(sys.executable)),str(BASE/'deploy.py'),'install'],cwd=BASE,check=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['install','doctor','update'])
    parser.add_argument('--gpu',action='store_true',help='install optional NVIDIA runtime during install')
    args=parser.parse_args()
    try:
        if args.action=='install': return install(args.gpu)
        if args.action=='doctor': return doctor()
        update();return 0
    except Exception as exc:
        print('Deployment failed:',exc,file=sys.stderr);return 1

if __name__=='__main__': raise SystemExit(main())
