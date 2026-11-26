import json, subprocess, time, unicodedata, math, re
from pathlib import Path
from subtitle_rules import clean_chinese, normalize_transcript
from media_tools import ffmpeg_path

def atomic_json(path,data):
    if path.name == 'transcript.json': normalize_transcript(data)
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

def ass_color(color, opacity=100):
    """Convert validated RGB and opacity to ASS alpha/BGR notation."""
    if not isinstance(color,str) or not re.fullmatch(r'#[0-9a-fA-F]{6}',color):
        raise ValueError('颜色需使用 #RRGGBB 格式')
    alpha=round(255*(100-opacity)/100)
    return f'&H{alpha:02X}{color[5:7]}{color[3:5]}{color[1:3]}'.upper()


def subtitle_style(style,w,h):
    style=style or {}
    font=str(style.get('font','Microsoft YaHei'))
    if not font or any(c in font for c in ',\n\r{}\\'): raise ValueError('字体名称无效')
    size=int(style.get('size',max(12,min(200,round(w*.038)))))
    x=float(style.get('x',50)); y=float(style.get('y',93))
    if not 10<=size<=200 or not math.isfinite(x+y) or not 5<=x<=95 or not 5<=y<=95:
        raise ValueError('字号需在 10–200，位置需在 5–95% 之间')
    result={'font':font,'size':size,'x':x,'y':y}
    for key,default in [('chinese_color','#FFFFFF'),('original_color','#FFFFFF'),
                        ('screen_color','#FFFF00'),('outline_color','#000000')]:
        color=style.get(key,default)
        ass_color(color)
        result[key]=color.upper()
    for key,default,low,high in [('outline',2,0,10),('shadow',0,0,10),('box_opacity',60,0,100)]:
        value=float(style.get(key,default))
        if not math.isfinite(value) or not low<=value<=high:
            raise ValueError(f'{key} 需在 {low}–{high} 之间')
        result[key]=value
    for key in ('bold','italic','box'):
        value=style.get(key,False)
        if not isinstance(value,bool): raise ValueError('粗体、斜体和背景框设置需为开关值')
        result[key]=value
    order=style.get('order','chinese_first')
    if order not in {'chinese_first','original_first'}: raise ValueError('双语顺序无效')
    result['order']=order
    return result



def fit_ass(path,original,chinese,screen,w,h,style=None,display="bilingual"):
    style=subtitle_style(style,w,h)
    font=style['size'];margin=max(12,round(w*0.045))
    chinese_color=ass_color(style['chinese_color'])
    original_color=ass_color(style['original_color'])
    outline_color=ass_color(style['outline_color'],style['box_opacity'] if style['box'] else 100)
    border=3 if style['box'] else 1
    bold=-1 if style['bold'] else 0
    italic=-1 if style['italic'] else 0
    header=f'''[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
WrapStyle: 2
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Speech,{style["font"]},{font},{chinese_color},&H00FFFFFF,{outline_color},&H80000000,{bold},{italic},0,0,100,100,0,0,{border},{style["outline"]},{style["shadow"]},2,{margin},{margin},{round(h*.07)},1
Style: Screen,{style["font"]},{font},{ass_color(style["screen_color"])},&H00FFFFFF,{outline_color},&H80000000,{bold},{italic},0,0,100,100,0,0,{border},{style["outline"]},{style["shadow"]},8,{margin},{margin},{round(h*.05)},1
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
            width=max(8,int(min(w-2*margin,2*w*min(style['x'],100-style['x'])/100)/(size*.65)))
            body=r'\N'.join(clean_chinese(line) for line in wrap(clean_chinese(chinese[index][2]),width).split(r'\N'))
            if display!='chinese' and text.strip():
                translated=body
                source=wrap(text,width)
                # ASS inline colours omit the alpha bytes and use BGR.
                zh_tag=r'{\1c&H'+chinese_color[4:]+'&}'
                source_tag=r'{\1c&H'+original_color[4:]+'&}'
                body=(source_tag+source+r'\N'+zh_tag+translated if style['order']=='original_first'
                      else zh_tag+translated+r'\N'+source_tag+source)
            if (body.count(r'\N')+1)*size*1.4<h*.5 or size<=10:break
            size-=1
        lines.append(f'Dialogue: 0,{stamp(a)},{stamp(b)},Speech,,0,0,0,,'+r'{\an2\pos('+str(round(w*style['x']/100))+','+str(round(h*style['y']/100))+r')\fs'+str(size)+'}'+body)
    for a,b,text in screen:lines.append(f'Dialogue: 1,{stamp(a)},{stamp(b)},Screen,,0,0,0,,'+wrap(text,max(8,int((w-2*margin)/(font*.65)))))
    path.write_text(header+'\n'.join(lines),encoding='utf-8')

def export_subtitles(folder,data,video=None):
    normalize_transcript(data)
    import subtitle_core as app
    if video is None:
        video=next(p for p in folder.glob('source.*') if p.suffix in {'.mp4','.mkv','.mov','.webm','.avi','.m4v'})
    w,h,_=video_info(video)
    fit_ass(folder/'bilingual.ass',data['original'],data['chinese'],data.get('screen',[]),w,h,data.get('subtitle_style'))
    fit_ass(folder/'chinese.ass',data['original'],data['chinese'],data.get('screen',[]),w,h,data.get('subtitle_style'),'chinese')
    app.write_srt(folder/'original.srt',data['original'])
    app.write_srt(folder/'chinese.srt',data['chinese'])
    app.write_srt(folder/'bilingual.srt',[(a,b,data['chinese'][i][2]+'\n'+text) for i,(a,b,text) in enumerate(data['original'])])
    if data.get('screen'):
        app.write_srt(folder/'screen-chinese.srt',data['screen'])


def preview_frame(folder,data,second):
    video=next(p for p in folder.glob('source.*') if p.suffix in {'.mp4','.mkv','.mov','.webm','.avi','.m4v'})
    w,h,duration=video_info(video)
    second=max(0,min(float(second),max(0,duration-.05)))
    fit_ass(folder/'preview.ass',data['original'],data['chinese'],data.get('screen',[]),w,h,data.get('subtitle_style'),data.get('subtitle_display','bilingual'))
    # Seek after the input so libass sees the original timeline.
    command=[ffmpeg_path(),'-nostdin','-y','-i',video.name,'-vf','ass=preview.ass',
             '-ss',str(second),'-frames:v','1','-update','1','preview.png']
    with (folder/'preview.log').open('w') as log:
        subprocess.run(command,cwd=folder,stdout=log,stderr=log,check=True,timeout=120)
    return folder/'preview.png'


def encode(folder,report):
    data=json.loads((folder/'transcript.json').read_text(encoding='utf-8'))
    video=next(p for p in folder.glob('source.*') if p.suffix in {'.mp4','.mkv','.mov','.webm','.avi','.m4v'})
    w,h,duration=video_info(video)
    export_subtitles(folder,data,video)
    progress=folder/'encode-progress.txt';progress.write_text('')
    ass='chinese.ass' if data.get('subtitle_display')=='chinese' else 'bilingual.ass'
    command=[ffmpeg_path(),'-nostdin','-y','-i',video.name,'-vf','ass='+ass,'-map','0:v:0','-map','0:a?','-c:v','libx264','-crf','20','-c:a','aac','-movflags','+faststart','-progress',progress.name,'-nostats','result.tmp.mp4']
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

def is_blank_cell(value):
    return value is None or (isinstance(value,str) and not value.strip()) or (isinstance(value,float) and math.isnan(value))


def validate_edit(rows,duration=None):
    original=[];chinese=[];previous=0
    for number,row in enumerate(rows,1):
        # Merged-away captions can retain timestamps: no text means no cue.
        if is_blank_cell(row.get('原文')) and is_blank_cell(row.get('中文')):
            continue
        if is_blank_cell(row.get('开始')) or is_blank_cell(row.get('结束')):
            raise ValueError(f'第 {number} 行：开始和结束时间不能为空；删除字幕请同时清空原文和中文')
        try:
            a,b=float(row['开始']),float(row['结束'])
        except (TypeError,ValueError):
            raise ValueError(f'第 {number} 行：开始和结束时间必须是秒数') from None
        if not math.isfinite(a+b) or a<previous or b<=a or (duration is not None and b>duration+.1):
            raise ValueError(f'第 {number} 行：时间轴必须有效、按序且不重叠，不超出视频长度；合并字幕后请检查相邻行')
        if not isinstance(row.get('中文'),str) or not row['中文'].strip():
            raise ValueError(f'第 {number} 行：中文字幕不能为空；删除字幕请同时清空原文和中文')
        text='' if is_blank_cell(row.get('原文')) else str(row['原文'])
        original.append([a,b,text]);chinese.append([a,b,clean_chinese(row['中文'])]);previous=b
    return original,chinese
