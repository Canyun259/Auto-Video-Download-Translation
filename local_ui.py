"""Local review-first video translation UI. Run with streamlit."""
import os, sys, importlib, json, sqlite3, threading, time, hashlib, subprocess
from pathlib import Path
from urllib.parse import urlparse
from output_paths import output_folder
import streamlit as st
from dotenv import load_dotenv
BASE = Path(__file__).resolve().parent
# Streamlit may execute outside this folder or retain a stale import cache.
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))
importlib.invalidate_caches()
# Streamlit reruns this file but can retain helpers imported before an update.
import review_tools
if not all(hasattr(review_tools, name) for name in
           ('subtitle_style', 'preview_frame', 'export_subtitles')):
    importlib.reload(review_tools)
load_dotenv(BASE / '.env')
DATA = BASE / 'local-data'
DATA.mkdir(exist_ok=True)
os.environ.setdefault('HF_HOME', str(DATA/'models'/'huggingface'))
import subtitle_core as app

def db():
    c = sqlite3.connect(DATA / 'library.sqlite', timeout=30)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA journal_mode=WAL')
    c.execute('CREATE TABLE IF NOT EXISTS videos(id TEXT PRIMARY KEY,url TEXT,title TEXT,thumb TEXT,duration REAL,state TEXT DEFAULT "waiting",error TEXT DEFAULT "",ocr INTEGER DEFAULT 0)')
    c.execute('CREATE TABLE IF NOT EXISTS settings(id INTEGER PRIMARY KEY,body TEXT)')
    from video_metadata import migrate
    migrate(c)
    columns={r[1] for r in c.execute('PRAGMA table_info(videos)')}
    if 'output_mode' not in columns:
        try: c.execute("ALTER TABLE videos ADD COLUMN output_mode TEXT DEFAULT 'burn'")
        except sqlite3.OperationalError:
            if 'output_mode' not in {r[1] for r in c.execute('PRAGMA table_info(videos)')}: raise
    return c

def settings():
    with db() as c:
        row = c.execute('SELECT body FROM settings WHERE id=1').fetchone()
    return json.loads(row[0]) if row else {'sources': [], 'interval':900,'limit':20,'model':'small'}

def update(ident, state, error=''):
    with db() as c:
        c.execute('UPDATE videos SET state=?,error=?,progress=0 WHERE id=?',(state,error,ident))

def set_progress(ident,value):
    with db() as c: c.execute('UPDATE videos SET progress=? WHERE id=?',(max(0.,min(1.,value)),ident))

def opts():
    from media_tools import download_options
    o = {'quiet':True,'socket_timeout':30,'retries':2,'ignoreerrors':False}
    o.update(download_options())
    cookie = DATA / 'secrets' / 'cookies.txt'
    if cookie.exists(): o['cookiefile'] = str(cookie)
    return o

def valid_url(url):
    p=urlparse(url)
    return p.scheme=='https' and p.hostname in {'youtube.com','www.youtube.com','youtu.be','x.com','www.x.com','twitter.com','www.twitter.com','instagram.com','www.instagram.com'}

def entries(info):
    if info.get('entries') is not None:
        for item in info['entries']:
            if item: yield from entries(item)
    else: yield info

def discover(url, limit):
    from yt_dlp import YoutubeDL
    if not valid_url(url): raise ValueError('仅支持 X、Instagram 和 YouTube 的 HTTPS 链接')
    parsed=urlparse(url); parts=parsed.path.strip('/').split('/')
    urls=[url]
    if parsed.hostname in {'x.com','www.x.com','twitter.com','www.twitter.com'} and len(parts)==1:
        urls=[u for _,u in app.x_posts(parts[0],limit)]
    elif 'instagram.com' in parsed.hostname and len(parts)==1:
        import instaloader, itertools
        loader=instaloader.Instaloader(max_connection_attempts=2,request_timeout=30)
        login=os.getenv('IG_USERNAME')
        if login: loader.load_session_from_file(login,str(DATA/'secrets'/'instagram.session'))
        profile=instaloader.Profile.from_username(loader.context,parts[0])
        urls=[]
        for method in (profile.get_reels, profile.get_posts):
            try:
                for post in itertools.islice(method(),limit):
                    if post.is_video or post.typename=='GraphSidecar': urls.append('https://www.instagram.com/p/'+post.shortcode+'/')
            except Exception as exc:
                print('Instagram 分栏扫描失败：'+type(exc).__name__, flush=True)
        urls=list(dict.fromkeys(urls))
    for source in urls:
        with YoutubeDL({**opts(),'playlistend':limit,'extract_flat':False,'skip_download':True}) as y:
            info=y.extract_info(source,download=False)
        for item in entries(info):
            if item.get('is_live'): continue
            link=item.get('webpage_url') or item.get('original_url')
            if not link: continue
            ident=hashlib.sha256((str(item.get('extractor_key'))+':'+str(item.get('id'))).encode()).hexdigest()[:24]
            with db() as c:
                from video_metadata import save
                save(c,ident,link,item)
            translate_title(ident)

def translate_title(ident, retry=False):
    with db() as c:
        row=c.execute('SELECT title,title_zh,title_error FROM videos WHERE id=?',(ident,)).fetchone()
    if not row or row['title_zh'] or (row['title_error'] and not retry): return
    if not os.getenv('TRANSLATE_API_KEY'): return
    try:
        translated=app.translate([(0,1,row['title'])])[0][2]
        with db() as c:
            c.execute('UPDATE videos SET title_zh=?,title_error=NULL WHERE id=? AND title=?',(translated,ident,row['title']))
    except Exception as exc:
        with db() as c:
            c.execute('UPDATE videos SET title_error=? WHERE id=? AND title=?',(type(exc).__name__,ident,row['title']))

def ass_time(t):
    h,r=divmod(round(t*100),360000); m,r=divmod(r,6000); s,cs=divmod(r,100)
    return f'{h}:{m:02}:{s:02}.{cs:02}'

def clean(t):
    return t.replace('\\','／').replace('{','（').replace('}','）').replace('\n',' ')

def make_ass(path,cues,zh,screen):
    header='''[Script Info]
ScriptType: v4.00+
PlayResX: 1280
PlayResY: 720
WrapStyle: 0
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Speech,Microsoft YaHei,28,&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,2,0,2,30,30,22,1
Style: Screen,Microsoft YaHei,24,&H0000FFFF,&H00FFFFFF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,2,0,8,30,30,20,1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
    lines=[]
    for original,chinese in zip(cues,zh):
        a,b,text=original
        lines.append(f'Dialogue: 0,{ass_time(a)},{ass_time(b)},Speech,,0,0,0,,{clean(chinese[2])}\\N{clean(text)}')
    for a,b,text in screen:
        lines.append(f'Dialogue: 1,{ass_time(a)},{ass_time(b)},Screen,,0,0,0,,画面文字：{clean(text)}')
    path.write_text(header+'\n'.join(lines),encoding='utf-8')

def screen_cues(video, progress=None):
    import cv2
    from rapidocr import RapidOCR
    engine=RapidOCR(); cap=cv2.VideoCapture(str(video)); result=[]
    try:
        fps=cap.get(cv2.CAP_PROP_FPS)
        if not fps: return []
        duration=cap.get(cv2.CAP_PROP_FRAME_COUNT)/fps
        tick=0.0
        while tick<duration:
            cap.set(cv2.CAP_PROP_POS_MSEC,tick*1000)
            ok,frame=cap.read()
            if not ok: break
            out=engine(frame)
            text=' / '.join(t for t,score in zip(out.txts if out.txts is not None else [],out.scores if out.scores is not None else []) if score>=0.75)
            end=min(duration,tick+0.5)
            if text:
                if result and result[-1][2]==text and abs(result[-1][1]-tick)<0.01: result[-1]=(result[-1][0],end,text)
                else: result.append((tick,end,text))
            tick=end
            if progress: progress(tick/duration)
    finally: cap.release()
    return result

def process(row, model_name, device_mode='auto'):
    from yt_dlp import YoutubeDL
    from faster_whisper import WhisperModel
    folder=output_folder(DATA,row,create=True)
    if not row['url'].startswith('local://'):
        update(row['id'],'下载中')
        with YoutubeDL({**opts(),'outtmpl':str(folder/'source.%(ext)s'),'format':'bv*+ba/b','merge_output_format':'mp4','noplaylist':True,'writesubtitles':False,'writeautomaticsub':False,'progress_hooks':[lambda d:set_progress(row['id'],d.get('downloaded_bytes',0)/(d.get('total_bytes') or d.get('total_bytes_estimate') or 1))]}) as y:
            downloaded_info=y.extract_info(row['url'],download=True)
        # Preserve at most one manual platform subtitle, without blocking the video.
        available=downloaded_info.get('subtitles') or {}
        languages=[k for k in available if k != 'live_chat']
        if languages:
            language=downloaded_info.get('language')
            selected=language if language in languages else languages[0]
            try:
                with YoutubeDL({**opts(),'outtmpl':str(folder/'source.%(ext)s'),'skip_download':True,'writesubtitles':True,'writeautomaticsub':False,'subtitleslangs':[selected],'subtitlesformat':'srt/best','retries':0}) as y:
                    y.process_ie_result(downloaded_info,download=True)
            except Exception as exc:
                from media_tools import safe_error
                (folder/'subtitle-warning.txt').write_text(safe_error(exc),encoding='utf-8')
    videos=[p for p in folder.glob('source.*') if p.suffix in {'.mp4','.webm','.mkv','.mov','.avi','.m4v'}]
    if not videos: raise RuntimeError('未下载到视频')
    video=videos[0]
    update(row['id'],'语音识别中')
    from gpu_support import speech_device
    device, precision = speech_device(device_mode)
    update(row['id'], '语音识别中')
    local_model = DATA/'models'/('whisper-'+model_name)
    model_source = str(local_model) if (local_model/'model.bin').exists() else model_name
    model=WhisperModel(model_source,device=device,compute_type=precision,download_root=str(DATA/'models'))
    segments,info=model.transcribe(str(video),word_timestamps=True,vad_filter=True)
    def tracked():
        for seg in segments:
            set_progress(row['id'],seg.end/max(info.duration,1));yield seg
    cues=app.cues_from_words(tracked())
    update(row['id'],'翻译中')
    zh=app.translate(cues,progress=lambda n,total:set_progress(row['id'],n/total)) if cues else []
    app.write_srt(folder/'original.srt',cues); app.write_srt(folder/'chinese.srt',zh)
    screen=[]
    if row['ocr']:
        update(row['id'],'画面文字识别中')
        raw=screen_cues(video,progress=lambda value:set_progress(row['id'],value))
        app.write_srt(folder/'screen-original.srt',raw)
        set_progress(row['id'],0)
        screen=app.translate(raw,progress=lambda n,total:set_progress(row['id'],n/total)) if raw else []
        app.write_srt(folder/'screen-chinese.srt',screen)
    (folder/'transcript.json').write_text(json.dumps({'language':info.language,'original':cues,'chinese':zh,'screen':screen},ensure_ascii=False),encoding='utf-8')
    if row['output_mode']=='files':
        from review_tools import export_subtitles
        export_subtitles(folder,json.loads((folder/'transcript.json').read_text(encoding='utf-8')),video)
        from cover_tools import save_cover
        save_cover(folder,row['thumb'])
        update(row['id'],'done')
    else:
        update(row['id'],'review')

class Runtime:
    def __init__(self):
        self.errors=[]; self.scan=threading.Event()
        with db() as c:
            c.execute("UPDATE videos SET state='failed',error='程序中断，请手动重试' WHERE state NOT IN ('waiting','queued','done','failed','review','burn_queued')")
        threading.Thread(target=self.poll,daemon=True).start()
        threading.Thread(target=self.worker,daemon=True).start()
    def poll(self):
        while True:
            cfg=settings()
            for url in cfg['sources']:
                try: discover(url,cfg['limit'])
                except Exception as exc: self.errors.append(url+'：'+type(exc).__name__)
            self.errors=self.errors[-30:]
            self.scan.wait(cfg['interval']); self.scan.clear()
    def worker(self):
        while True:
            with db() as c:
                row=c.execute("SELECT * FROM videos WHERE state IN ('queued','burn_queued') ORDER BY rowid LIMIT 1").fetchone()
            if row:
                try:
                    if row['state']=='burn_queued':
                        from review_tools import encode
                        update(row['id'],'字幕烧录中')
                        from cover_tools import save_cover
                        folder=output_folder(DATA,row)
                        save_cover(folder,row['thumb'])
                        encode(folder,lambda value: set_progress(row['id'],value))
                        update(row['id'],'done')
                    else: process(row,settings()['model'],settings().get('device','auto'))
                except Exception as exc:
                    from media_tools import safe_error
                    update(row['id'],'failed',safe_error(exc))
            else: time.sleep(2)

@st.cache_resource
def runtime(): return Runtime()

def main():
    st.set_page_config(page_title='本地视频翻译台',layout='wide')
    from version import __version__
    st.title('本地视频翻译台')
    st.caption('版本 v'+__version__)
    st.caption('发现视频 → 自动翻译 → 保存独立字幕，或审核预览后烧录')
    rt=runtime(); cfg=settings()
    with st.sidebar:
        st.header('监控设置')
        with st.form('settings'):
            sources=st.text_area('账号、频道或单条视频链接（每行一个）','\n'.join(cfg['sources']))
            interval=st.number_input('检测间隔（秒）',60,86400,cfg['interval'])
            limit=st.number_input('每个入口扫描数量',1,500,cfg['limit'])
            model=st.selectbox('识别模型',['small','medium','large-v3'],index=['small','medium','large-v3'].index(cfg['model']))
            device=st.selectbox('语音识别设备', ['auto','cuda','cpu'], index=['auto','cuda','cpu'].index(cfg.get('device','auto')), format_func=lambda x: {'auto':'自动（优先 CUDA）','cuda':'CUDA（缺少依赖时报错）','cpu':'CPU'}[x])
            from gpu_support import cuda_status
            ready, reason = cuda_status()
            st.caption(('CUDA 可用：' if ready else '当前自动模式使用 CPU：') + reason)
            save=st.form_submit_button('保存并检测')
        if save:
            urls=[s.strip() for s in sources.splitlines() if s.strip()]
            if not all(valid_url(u) for u in urls): st.error('请使用支持平台的 HTTPS 链接')
            else:
                with db() as c: c.execute('INSERT OR REPLACE INTO settings VALUES(1,?)',(json.dumps({'sources':urls,'interval':interval,'limit':limit,'model':model,'device':device}),))
                rt.scan.set(); st.success('已保存')
        if st.button('立即检测'): rt.scan.set()
        st.caption('输出目录：'+str(DATA/'output'))
        st.caption('扫描后自动翻译标题并缓存；仅翻译标题不会下载或翻译视频。标题翻译会使用少量 API 额度。')
        st.caption('画面文字识别默认关闭；仅在单个视频勾选后启用。')
        if rt.errors: st.warning('\n'.join(rt.errors[-5:]))
    render_local_import()
    show_library()

def render_local_import():
    with st.expander('导入已下载的本地视频'):
        st.caption('导入后出现在「待选择」，可生成独立字幕或预览后烧录。原文件保持不变；导入的视频会复制到输出目录。')
        method=st.radio('导入方式',['本机文件路径（适合大视频）','上传视频文件'],horizontal=True)
        source=st.text_input('视频完整路径',placeholder=r'D:\Videos\video.mp4') if method.startswith('本机') else st.file_uploader('选择已下载的视频',type=['mp4','mkv','mov','webm','avi','m4v'])
        if st.button('导入到待选择',key='import-local'):
            if not source: st.error('请先填写路径或选择视频')
            else:
                try:
                    from local_import import import_video
                    with st.spinner('正在检查并复制视频…'):
                        ident,created=import_video(DATA,db,source,getattr(source,'name',None))
                    st.session_state['local-import-message']='视频已导入「待选择」。' if created else '该视频已经导入，请在视频库中查找。'
                    st.rerun()
                except Exception as exc:
                    from media_tools import safe_error
                    st.error(safe_error(exc))
        if st.session_state.get('local-import-message'):
            st.success(st.session_state.pop('local-import-message'))


def render_review(row,folder):
    from review_tools import atomic_json,validate_edit,video_info,subtitle_style,preview_frame,export_subtitles
    data=json.loads((folder/'transcript.json').read_text(encoding='utf-8'))
    source=next((p for p in folder.glob('source.*') if p.suffix in {'.mp4','.webm','.mkv','.mov','.avi','.m4v'}),None)
    if source: st.video(str(source))
    w,h,duration=video_info(source) if source else (1280,720,None)
    style=subtitle_style(data.get('subtitle_style'),w,h)
    st.caption('字幕位置以画面百分比表示：水平为居中锚点，垂直为字幕底边。画面文字保持顶部显示。')
    with st.form('edit-'+row['id']):
        title=st.text_input('中文标题',row['title_zh'] or row['title'])
        table=st.data_editor([{'开始':a[0],'结束':a[1],'原文':a[2],'中文':b[2]} for a,b in zip(data['original'],data['chinese'])],key='editor-'+row['id'],num_rows='fixed')
        screen=st.data_editor([{'开始':a,'结束':b,'原文':'','中文':t} for a,b,t in data.get('screen',[])],key='screen-'+row['id'],num_rows='fixed') if data.get('screen') else []
        font=st.selectbox('字幕字体',['Microsoft YaHei','SimHei','SimSun','KaiTi','Arial'],index=(['Microsoft YaHei','SimHei','SimSun','KaiTi','Arial'].index(style['font']) if style['font'] in ['Microsoft YaHei','SimHei','SimSun','KaiTi','Arial'] else 0))
        size=st.number_input('字幕字号（原视频像素）',10,200,style['size'])
        x=st.slider('水平位置（%）',5,95,int(style['x']))
        y=st.slider('垂直位置（%）',5,95,int(style['y']))
        second=st.number_input('预览时间（秒）',min_value=0.,max_value=max(0.,(duration or 1)-.05),value=min(float(data['original'][0][0])+.1,max(0.,(duration or 1)-.05)) if data['original'] else 0.,step=.1)
        preview=st.form_submit_button('更新字幕预览')
        save=st.form_submit_button('保存修改')
        files=st.form_submit_button('保存视频和字幕文件（不烧录）')
        approve=st.form_submit_button('确认审核并烧录')
    if save or approve or preview or files:
        try:
            duration=video_info(source)[2] if source else None
            data['original'],data['chinese']=validate_edit(table,duration)
            if screen: _,data['screen']=validate_edit(screen,duration)
            data['subtitle_style']=subtitle_style({'font':font,'size':size,'x':x,'y':y},w,h)
            atomic_json(folder/'transcript.json',data)
            with db() as c: c.execute('UPDATE videos SET title_zh=? WHERE id=?',(title,row['id']))
            if preview:
                with st.spinner('正在生成实际烧录效果…'):
                    image=preview_frame(folder,data,second)
                st.success('预览已更新，使用当前保存的字幕和样式。')
            elif files:
                export_subtitles(folder,data,source)
                with db() as c: c.execute("UPDATE videos SET output_mode='files' WHERE id=?",(row['id'],))
                update(row['id'],'done');st.rerun()
            elif approve:
                with db() as c: c.execute("UPDATE videos SET output_mode='burn' WHERE id=?",(row['id'],))
                update(row['id'],'burn_queued');st.rerun()
            else: st.success('修改已保存')
        except Exception as exc: st.error(str(exc))
    if (folder/'preview.png').exists():
        st.image(str(folder/'preview.png'),caption='上次生成的烧录预览；修改字幕或样式后请点击更新字幕预览。')

@st.fragment(run_every=5)
def show_library():
    with db() as c: rows=c.execute('SELECT * FROM videos ORDER BY rowid DESC').fetchall()
    platform=st.selectbox('发布平台',['全部','Instagram','YouTube','X','本地视频'])
    publisher=st.text_input('搜索发布者（名称或主页）').strip().casefold()
    order=st.selectbox('排序',['发布时间：最新优先','发布时间：最早优先'])
    def platform_name(url):
        if url.startswith('local://'): return '本地视频'
        host=urlparse(url).hostname or ''
        return 'Instagram' if 'instagram.com' in host else 'YouTube' if 'youtube.com' in host or host=='youtu.be' else 'X'
    rows=[r for r in rows if (platform=='全部' or platform_name(r['url'])==platform) and (not publisher or publisher in ((r['publisher'] or '')+' '+(r['publisher_url'] or '')).casefold())]
    known=[r for r in rows if r['published_at']];unknown=[r for r in rows if not r['published_at']]
    rows=sorted(known,key=lambda r:r['published_at'][:19],reverse='最新' in order)+unknown
    tabs=st.tabs(['待选择','处理中','审核区','已完成','失败'])
    for tab,states in zip(tabs,[{'waiting'},{'queued','burn_queued','下载中','语音识别中','翻译中','画面文字识别中','字幕烧录中'},{'review'},{'done'},{'failed'}]):
        with tab:
            subset=[r for r in rows if r['state'] in states]
            if not subset: st.info('暂无视频')
            for r in subset:
                with st.container(border=True):
                    image,body=st.columns([1,3])
                    with image:
                        if r['thumb']: st.image(r['thumb'],use_container_width=True)
                    with body:
                        st.subheader(r['title_zh'] or r['title'])
                        st.text('原标题：'+r['title'])
                        st.text('发布账号：'+(r['publisher'] or '暂未获取，重新检测后补齐'))
                        st.caption('发布时间：'+(r['published_at'] or '平台未提供或尚未获取'))
                        if r['publisher_url'] and urlparse(r['publisher_url']).scheme in {'http','https'}:
                            st.link_button('发布账号主页',r['publisher_url'])
                        if not r['title_zh']:
                            st.caption('中文标题：'+('翻译失败（'+r['title_error']+'）' if r['title_error'] else '待翻译'))
                            if st.button('翻译标题',key='title-'+r['id']):
                                if not os.getenv('TRANSLATE_API_KEY'):
                                    st.error('请先配置翻译服务')
                                else:
                                    with st.spinner('正在翻译标题…'): translate_title(r['id'],retry=True)
                                    st.rerun()
                        duration=r['duration']
                        st.caption(('时长：'+str(int(duration)//60)+':'+str(int(duration)%60).zfill(2) if duration else '时长未知')+' · '+r['state'])
                        if r['state'] not in {'waiting','review','failed'}:
                            value=1.0 if r['state']=='done' else float(r['progress'] or 0)
                            st.progress(value,text=f"{r['state']} · 当前阶段 {value:.0%}")
                            st.caption('按阶段计量；准备模型或请求返回前进度可能暂时不变。')
                        if not r['url'].startswith('local://'): st.link_button('打开原视频',r['url'])
                        folder=output_folder(DATA,r)
                        if r['state'] in {'done','failed'} and (folder/'transcript.json').exists():
                            if st.button('返回审核（不重新翻译）',key='review-'+r['id']):
                                update(r['id'],'review');st.rerun()
                        if r['state']=='review':
                            render_review(r,folder)
                        if r['state'] in {'waiting','failed'}:
                            mode=st.radio('输出方式',['burn','files'],format_func=lambda v: '预览审核后烧录字幕' if v=='burn' else '下载视频＋生成独立字幕文件（不烧录）',key='mode-'+r['id'])
                            ocr=st.checkbox('识别并翻译画面中的字幕/文字',False,key='ocr'+r['id'])
                            if st.button(('翻译并送审' if mode=='burn' else '下载并生成字幕') if r['state']=='waiting' else '重试',key=r['id']):
                                if not os.getenv('TRANSLATE_API_KEY'): st.error('请先填写 .env 中的翻译服务配置并重启')
                                else:
                                    with db() as c: c.execute("UPDATE videos SET state='queued',ocr=?,output_mode=?,error='' WHERE id=? AND state IN ('waiting','failed')",(int(ocr),mode,r['id']))
                                    st.rerun()
                        if r['error']: st.error(r['error'])
                        if r['state']=='done':
                            folder=output_folder(DATA,r)
                            video=(folder/'result.mp4') if r['output_mode']!='files' else next((p for p in folder.glob('source.*') if p.suffix in {'.mp4','.mkv','.webm','.mov'}),None)
                            if video and video.exists():
                                st.video(str(video))
                                st.caption('已保存：'+str(video))
                            st.caption('字幕及原视频目录：'+str(folder))
                            for name in ['original.srt','chinese.srt','bilingual.srt','bilingual.ass','screen-chinese.srt']:
                                path=folder/name
                                if path.exists(): st.download_button('下载 '+name,path.read_bytes(),file_name=name,key='download-'+r['id']+name)
                            if (folder/'cover.jpg').exists():
                                st.caption('封面已保存：'+str(folder/'cover.jpg'))
                            else:
                                if (folder/'cover-warning.txt').exists():
                                    st.warning((folder/'cover-warning.txt').read_text(encoding='utf-8'))
                                if st.button('保存/重试封面',key='cover-'+r['id']):
                                    from cover_tools import save_cover
                                    with st.spinner('正在保存封面…'): save_cover(folder,r['thumb'])
                                    st.rerun()
                            if (folder/'subtitle-warning.txt').exists(): st.warning('平台附带字幕未获取成功，成品使用音轨识别生成的双语字幕。')
                            with st.expander('原文 / 中文 / 画面翻译'):
                                data=json.loads((folder/'transcript.json').read_text(encoding='utf-8'))
                                st.dataframe([{'开始':a[0],'结束':a[1],'原文':a[2],'中文':b[2]} for a,b in zip(data['original'],data['chinese'])],use_container_width=True)
                                st.dataframe([{'开始':a,'结束':b,'画面中文':t} for a,b,t in data['screen']],use_container_width=True)

if __name__=='__main__': main()









