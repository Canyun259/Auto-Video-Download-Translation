import json, subprocess, time, unicodedata, math
from pathlib import Path
from media_tools import ffmpeg_path

def atomic_json(path,data):
    temp=path.with_suffix('.tmp.json');temp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8');temp.replace(path)

def video_info(video):
    probe=str(Path(ffmpeg_path()).with_name('ffprobe.exe'))
    data=json.loads(subprocess.check_output([probe,'-v','error','-select_streams','v:0','-show_entries','stream=width,height:stream_tags=rotate:stream_side_data=rotation','-show_entries','format=duration','-of','json',str(video)],text=True))
    stream=data['streams'][0]; w,h=stream['width'],stream['height']
    rotation=stream.get('tags',{}).get('rotate',0)
    for side in stream.get('side_data_list',[]): rotation=side.get('rotation',rotation)
    if abs(float(rotation))%180==90:w,h=h,w
    return w,h,float(data['format']['duration'])

def wrap(text,limit):
    text=text.replace('\\','／').replace('{','（').replace('}','）')
    lines=[];line='';units=0
    for char in text:
        size=2 if unicodedata.east_asian_width(char) in 'WF' else 1
        if char=='\n' or units+size>limit:
            lines.append(line);line='';units=0
        if char!='\n':line+=char;units+=size
    if line:lines.append(line)
    return r'\N'.join(lines)

def fit_ass(path,original,chinese,screen,w,h):
    font=max(12,round(w*0.038));margin=max(12,round(w*0.045))
    header=f'''[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
WrapStyle: 2
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Speech,Microsoft YaHei,{font},&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,2,0,2,{margin},{margin},{round(h*.07)},1
Style: Screen,Microsoft YaHei,{font},&H0000FFFF,&H00FFFFFF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,2,0,8,{margin},{margin},{round(h*.05)},1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
    def stamp(t):
        cs=round(float(t)*100);hours,cs=divmod(cs,360000);minutes,cs=divmod(cs,6000);seconds,cs=divmod(cs,100)
        return f'{hours}:{minutes:02}:{seconds:02}.{cs:02}'
    lines=[]
    for index,(a,b,text) in enumerate(original):
        size=font
        while True:
            width=max(8,int((w-2*margin)/(size*.65)))
            body=wrap(chinese[index][2],width)+r'\N'+wrap(text,width)
            if (body.count(r'\N')+1)*size*1.4<h*.5 or size<=10:break
            size-=1
        lines.append(f'Dialogue: 0,{stamp(a)},{stamp(b)},Speech,,0,0,0,,'+r'{\fs'+str(size)+'}'+body)
    for a,b,text in screen:lines.append(f'Dialogue: 1,{stamp(a)},{stamp(b)},Screen,,0,0,0,,'+wrap(text,max(8,int((w-2*margin)/(font*.65)))))
    path.write_text(header+'\n'.join(lines),encoding='utf-8')

def encode(folder,report):
    data=json.loads((folder/'transcript.json').read_text(encoding='utf-8'))
    video=next(p for p in folder.glob('source.*') if p.suffix in {'.mp4','.mkv','.mov','.webm'})
    w,h,duration=video_info(video)
    fit_ass(folder/'bilingual.ass',data['original'],data['chinese'],data.get('screen',[]),w,h)
    import subtitle_core as app
    app.write_srt(folder/'original.srt',data['original']);app.write_srt(folder/'chinese.srt',data['chinese'])
    progress=folder/'encode-progress.txt';progress.write_text('')
    command=[ffmpeg_path(),'-nostdin','-y','-i',video.name,'-vf','ass=bilingual.ass','-map','0:v:0','-map','0:a?','-c:v','libx264','-crf','20','-c:a','aac','-movflags','+faststart','-progress',progress.name,'-nostats','result.tmp.mp4']
    with (folder/'ffmpeg.log').open('w') as log:
        proc=subprocess.Popen(command,cwd=folder,stdout=log,stderr=log);started=time.monotonic()
        try:
            while proc.poll() is None:
                if time.monotonic()-started>14400:raise TimeoutError('烧录超时')
                for line in progress.read_text(errors='ignore').splitlines():
                    if line.startswith('out_time_us='):
                        try:report(min(.99,int(line.split('=')[1])/1000000/duration))
                        except ValueError:pass
                time.sleep(.5)
            if proc.returncode:raise RuntimeError('FFmpeg 烧录失败，请查看 ffmpeg.log')
        finally:
            if proc.poll() is None:proc.kill();proc.wait()
    (folder/'result.tmp.mp4').replace(folder/'result.mp4')

def validate_edit(rows,duration=None):
    original=[];chinese=[];previous=0
    for row in rows:
        a,b=float(row['开始']),float(row['结束'])
        if not math.isfinite(a+b) or a<previous or b<=a or (duration and b>duration+.1):raise ValueError('时间轴必须有效、按序且不重叠，不超出视频长度')
        if not isinstance(row['中文'],str) or not row['中文'].strip():raise ValueError('中文字幕不能为空')
        original.append([a,b,str(row['原文'])]);chinese.append([a,b,row['中文']]);previous=b
    return original,chinese
