"""Read text subtitle tracks without loading a speech recognition model."""
import html
import re
import subprocess
from media_tools import ffmpeg_path


def parse_srt(text):
    cues=[]
    def seconds(stamp):
        h,m,s=stamp.replace(',', '.').split(':')
        return int(h)*3600+int(m)*60+float(s)
    for block in re.split(r'\n\s*\n',text.replace('\r','').strip()):
        lines=block.splitlines()
        for index,line in enumerate(lines):
            match=re.fullmatch(r'(\d+:\d{2}:\d{2}[,.]\d+)\s*-->\s*(\d+:\d{2}:\d{2}[,.]\d+).*',line)
            if not match: continue
            a,b=map(seconds,match.groups())
            body=html.unescape(re.sub(r'<[^>]+>|\{\\[^}]*\}', '', '\n'.join(lines[index+1:]))).strip()
            if body and b>a: cues.append((a,b,body))
            break
    return cues


def existing_cues(folder,video):
    # Only source subtitles, never translations left by an earlier run.
    candidates=sorted(p for p in folder.glob('source.*') if p.suffix.lower() in {'.srt','.vtt','.ass','.ssa','.ttml'})
    for source in [*candidates,video]:
        try:
            result=subprocess.run([ffmpeg_path(),'-nostdin','-v','error','-i',str(source),'-map','0:s:0','-f','srt','-'],capture_output=True,timeout=120)
            if result.returncode: continue
            cues=parse_srt(result.stdout.decode('utf-8-sig',errors='replace'))
            if cues: return cues
        except (OSError,subprocess.TimeoutExpired):
            continue
    return []
