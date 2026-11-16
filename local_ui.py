"""Local review-first video translation UI. Run with streamlit."""
import os, sys, importlib, json, sqlite3, threading, time, hashlib, subprocess
from pathlib import Path
from urllib.parse import urlparse
from datetime import timezone
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
           ('subtitle_style', 'preview_frame', 'export_subtitles', 'is_blank_cell')):
    importlib.reload(review_tools)
load_dotenv(BASE / '.env')
DATA = BASE / 'local-data'
DATA.mkdir(exist_ok=True)
os.environ.setdefault('HF_HOME', str(DATA/'models'/'huggingface'))
import subtitle_core as app

def db():
    from database_setup import ManagedConnection
    c = sqlite3.connect(DATA / 'library.sqlite', timeout=30,factory=ManagedConnection)
    c.row_factory = sqlite3.Row
    from database_setup import ensure_schema
    ensure_schema(c)
    return c

def settings():
    with db() as c:
        row = c.execute('SELECT body FROM settings WHERE id=1').fetchone()
    return json.loads(row[0]) if row else {'sources': [], 'interval':900,'limit':20,'model':'small'}

def update(ident, state, error=''):
    with db() as c:
        c.execute('UPDATE videos SET state=?,error=?,progress=0 WHERE id=? AND hidden=0',(state,error,ident))

def set_progress(ident,value):
    with db() as c: c.execute('UPDATE videos SET progress=? WHERE id=?',(max(0.,min(1.,value)),ident))

def opts():
    from media_tools import download_options
    o = {'quiet':True,'socket_timeout':30,'retries':2,'ignoreerrors':False}
    o.update(download_options())
    from network_proxy import media_proxy
    proxy=media_proxy(settings().get('proxy',''))
    if proxy: o['proxy']=proxy
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
    from library_store import checkpoint,is_new,excluded,complete_scan
    started=time.time()
    with db() as c: since=checkpoint(c,url)
    parsed=urlparse(url); parts=parsed.path.strip('/').split('/')
    urls=[url]
    if parsed.hostname in {'x.com','www.x.com','twitter.com','www.twitter.com'} and len(parts)==1:
        urls=[u for _,u in app.x_posts(parts[0],limit)]
    elif 'instagram.com' in parsed.hostname and len(parts)==1:
        import instaloader, itertools
        loader=instaloader.Instaloader(max_connection_attempts=2,request_timeout=30)
        login=os.getenv('IG_USERNAME')
        if login: loader.load_session_from_file(login,str(DATA/'secrets'/'instagram.session'))
        from network_proxy import media_proxy,apply_instagram_proxy
        apply_instagram_proxy(loader,media_proxy(settings().get('proxy','')))
        profile=instaloader.Profile.from_username(loader.context,parts[0])
        urls=[]; section_errors=[]
        for method in (profile.get_reels, profile.get_posts):
            try:
                for post in itertools.islice(method(),limit):
                    if not is_new({'timestamp':post.date_utc.replace(tzinfo=timezone.utc).timestamp()},since): continue
                    link='https://www.instagram.com/p/'+post.shortcode+'/'
                    with db() as c:
                        if excluded(c,url=link): continue
                    if post.is_video or post.typename=='GraphSidecar': urls.append(link)
            except Exception as exc:
                from media_tools import safe_error
                message=safe_error(exc)
                if 'feedback_required' in str(exc):
                    raise RuntimeError('Instagram 返回 feedback_required：请先在浏览器登录并处理验证，暂停反复检测；通过后如仍失败需重新导入登录会话') from exc
                section_errors.append(message)
                print('Instagram 分栏扫描失败：'+message, flush=True)
        urls=list(dict.fromkeys(urls))
        if section_errors:
            raise RuntimeError('Instagram 未能读取帖子或 Reels：'+'；'.join(section_errors))
    for source in urls:
        def match_new(item,*,incomplete=False):
            if not is_new(item,since): return '早于上次成功检测时间'
            link=item.get('webpage_url') or item.get('original_url')
            with db() as c:
                if link and excluded(c,url=link): return '已手动删除，跳过'
            return None
        with YoutubeDL({**opts(),'playlistend':limit,'lazy_playlist':True,'extract_flat':False,'skip_download':True,'match_filter':match_new}) as y:
            info=y.extract_info(source,download=False)
            if not info: continue
            for item in entries(info):
                if item.get('is_live') or not is_new(item,since): continue
                link=item.get('webpage_url') or item.get('original_url')
                if not link: continue
                ident=hashlib.sha256((str(item.get('extractor_key'))+':'+str(item.get('id'))).encode()).hexdigest()[:24]
                with db() as c:
                    from video_metadata import save
                    stored=save(c,ident,link,item)
                if stored: translate_title(ident)
    with db() as c: complete_scan(c,url,started)

def translate_title(ident, retry=False):
    with db() as c:
        row=c.execute('SELECT title,title_zh,title_error FROM videos WHERE id=? AND hidden=0',(ident,)).fetchone()
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

def process(row, model_name, device_mode='auto'):
    from yt_dlp import YoutubeDL
    folder=output_folder(DATA,row,create=True)
    imported=json.loads(row['imported_subtitles']) if row['imported_subtitles'] else None
    if not row['url'].startswith('local://'):
        update(row['id'],'下载中')
        with YoutubeDL({**opts(),'outtmpl':str(folder/'source.%(ext)s'),'format':'bv*+ba/b','merge_output_format':'mp4','noplaylist':True,'writesubtitles':False,'writeautomaticsub':False,'progress_hooks':[lambda d:set_progress(row['id'],d.get('downloaded_bytes',0)/(d.get('total_bytes') or d.get('total_bytes_estimate') or 1))]}) as y:
            downloaded_info=y.extract_info(row['url'],download=True)
        # Preserve at most one manual platform subtitle, without blocking the video.
        available=downloaded_info.get('subtitles') or {}
        languages=[k for k in available if k != 'live_chat']
        automatic=False
        if not languages and str(row['prefer_subtitles'])=='1':
            available=downloaded_info.get('automatic_captions') or {}
            languages=[k for k in available if k != 'live_chat']
            automatic=True
        if languages and imported is None:
            language=downloaded_info.get('language')
            selected=language if language in languages else languages[0]
            try:
                with YoutubeDL({**opts(),'outtmpl':str(folder/'source.%(ext)s'),'skip_download':True,'writesubtitles':not automatic,'writeautomaticsub':automatic,'subtitleslangs':[selected],'subtitlesformat':'srt/best','retries':0}) as y:
                    y.process_ie_result(downloaded_info,download=True)
            except Exception as exc:
                from media_tools import safe_error
                (folder/'subtitle-warning.txt').write_text(safe_error(exc),encoding='utf-8')
    videos=[p for p in folder.glob('source.*') if p.suffix in {'.mp4','.webm','.mkv','.mov','.avi','.m4v'}]
    if not videos: raise RuntimeError('未下载到视频')
    video=videos[0]
    if imported is not None:
        from review_tools import validate_edit,video_info
        original,chinese=validate_edit([{'开始':a[0],'结束':a[1],'原文':a[2],'中文':b[2]}
                                        for a,b in zip(imported['original'],imported['chinese'])],video_info(video)[2])
        if not chinese: raise ValueError('导入字幕没有有效内容，请重新选择字幕文件')
        transcript={**imported,'original':original,'chinese':chinese,'screen':[]}
    else:
        from subtitle_source import existing_cues
        cues=existing_cues(folder,video) if str(row['prefer_subtitles'])=='1' else []
        language=None
        subtitle_source='existing' if cues else 'speech'
        if not cues:
            update(row['id'],'语音识别中')
            from gpu_support import speech_device
            device, precision = speech_device(device_mode)
            update(row['id'], '语音识别中')
            local_model = DATA/'models'/('whisper-'+model_name)
            model_source = str(local_model) if (local_model/'model.bin').exists() else model_name
            from faster_whisper import WhisperModel
            model=WhisperModel(model_source,device=device,compute_type=precision,download_root=str(DATA/'models'))
            segments,info=model.transcribe(str(video),word_timestamps=True,vad_filter=True)
            def tracked():
                for seg in segments:
                    set_progress(row['id'],seg.end/max(info.duration,1));yield seg
            cues=app.cues_from_words(tracked())
            language=info.language
        update(row['id'],'翻译中')
        zh=app.translate(cues,progress=lambda n,total:set_progress(row['id'],n/total)) if cues else []
        app.write_srt(folder/'original.srt',cues); app.write_srt(folder/'chinese.srt',zh)
        screen=[]
        transcript={'language':language,'subtitle_source':subtitle_source,'subtitle_display':row['subtitle_display'],'original':cues,'chinese':zh,'screen':screen}
    from review_tools import atomic_json
    atomic_json(folder/'transcript.json',transcript)
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
        self.scan_status={'state':'idle'}
        with db() as c:
            c.execute("UPDATE videos SET state='failed',error='程序中断，请手动重试' WHERE state NOT IN ('waiting','queued','done','failed','review','burn_queued')")
        threading.Thread(target=self.poll,daemon=True).start()
        threading.Thread(target=self.worker,daemon=True).start()
    def request_scan(self):
        if self.scan_status['state'] != 'running':
            self.scan.set()

    def poll(self):
        while True:
            cfg=settings()
            ig_blocked=False
            sources=cfg['sources']
            failures=0
            for index,url in enumerate(sources,1):
                self.scan_status={'state':'running','url':url,'index':index,'total':len(sources)}
                prefix=url+'：'
                self.errors=[error for error in self.errors if not error.startswith(prefix)]
                if ig_blocked and 'instagram.com' in (urlparse(url).hostname or ''):
                    failures+=1
                    self.errors.append(prefix+'本轮暂停：Instagram 登录会话触发风控，请先在浏览器处理验证')
                    continue
                try: discover(url,cfg['limit'])
                except Exception as exc:
                    from media_tools import safe_error
                    failures+=1
                    self.errors.append(prefix+safe_error(exc))
                    if 'instagram.com' in (urlparse(url).hostname or '') and 'feedback_required' in str(exc): ig_blocked=True
            self.errors=[error for error in self.errors if any(error.startswith(url+'：') for url in cfg['sources'])][-30:]
            self.scan_status={'state':'done','total':len(sources),'failures':failures,'finished':time.strftime('%H:%M:%S')}
            self.scan.wait(cfg['interval']); self.scan.clear()
    def worker(self):
        while True:
            with db() as c:
                row=c.execute("SELECT * FROM videos WHERE hidden=0 AND state IN ('queued','burn_queued') ORDER BY rowid LIMIT 1").fetchone()
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

@st.fragment(run_every=1)
def render_scan_status(rt):
    status=rt.scan_status
    if status['state']=='running':
        parsed=urlparse(status['url'])
        account=parsed.path.strip('/') or parsed.hostname
        st.info(f"正在检测：{account}（{status['index']}/{status['total']}）")
        st.caption(status['url'])
    elif rt.scan.is_set():
        st.info('正在准备检测…')
    elif status['state']=='done':
        if not status['total']:
            st.caption('尚未配置检测账号，请填写链接并保存。')
        elif status['failures']:
            st.warning(f"检测结束：共 {status['total']} 个来源，{status['failures']} 个失败或暂停。请查看下方错误详情。")
        else:
            st.success(f"检测完成：共 {status['total']} 个来源（{status['finished']}），视频列表已更新。")
    else:
        st.caption('等待检测')


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
            st.caption('按每个来源上次成功检测的时间增量入库；失败不会推进时间。日期不精确时保留当天视频，以免遗漏。')
            model=st.selectbox('识别模型',['small','medium','large-v3'],index=['small','medium','large-v3'].index(cfg['model']))
            device=st.selectbox('语音识别设备', ['auto','cuda','cpu'], index=['auto','cuda','cpu'].index(cfg.get('device','auto')), format_func=lambda x: {'auto':'自动（优先 CUDA）','cuda':'CUDA（缺少依赖时报错）','cpu':'CPU'}[x])
            from gpu_support import cuda_status
            ready, reason = cuda_status()
            st.caption(('CUDA 可用：' if ready else '当前自动模式使用 CPU：') + reason)
            proxy=st.text_input('视频检测与下载代理',cfg.get('proxy',''),placeholder='留空自动使用系统代理，例如 http://127.0.0.1:7897')
            st.caption('留空跟随系统代理；修改后点击保存并检测。请保持代理软件运行。')
            save=st.form_submit_button('保存并检测')
        if save:
            urls=[s.strip() for s in sources.splitlines() if s.strip()]
            from network_proxy import validate_proxy
            proxy_error=''
            try: validate_proxy(proxy.strip())
            except ValueError as exc: proxy_error=str(exc)
            if proxy_error: st.error(proxy_error)
            elif not all(valid_url(u) for u in urls): st.error('请使用支持平台的 HTTPS 链接')
            else:
                with db() as c: c.execute('INSERT OR REPLACE INTO settings VALUES(1,?)',(json.dumps({'sources':urls,'interval':interval,'limit':limit,'model':model,'device':device,'proxy':proxy.strip()}),))
                rt.request_scan(); st.success('已保存')
        if st.button('立即检测'): rt.request_scan()
        render_scan_status(rt)
        st.caption('输出目录：'+str(DATA/'output'))
        st.caption('扫描后自动翻译标题并缓存；仅翻译标题不会下载或翻译视频。标题翻译会使用少量 API 额度。')
        if rt.errors:
            st.caption('来源恢复成功后会自动清除对应错误；Instagram 风控需要先在浏览器处理。')
            st.warning('\n'.join(rt.errors[-5:]))
            if st.button('清空旧错误记录'):
                rt.errors.clear();st.rerun()
    render_url_import()
    render_local_import()
    show_library()

def render_url_import():
    with st.expander('通过视频地址导入', expanded=True):
        st.caption('粘贴 YouTube、X 或 Instagram 的单条视频地址，无需添加监控账号。导入信息后进入「待选择」，选择处理时才下载视频。')
        with st.form('url-import-form'):
            source = st.text_input('视频地址', placeholder='https://www.youtube.com/watch?v=…', key='import-url-input')
            submitted = st.form_submit_button('导入视频地址')
        if submitted:
            try:
                from url_import import import_url
                with st.spinner('正在解析视频地址…'):
                    ident, created = import_url(db, source, opts())
                st.session_state['url-import-result'] = ('success' if created else 'info',
                    '视频已导入「待选择」。选择处理后将下载视频并生成字幕。' if created else '该视频已在视频库中，无需重复导入；请在对应分区查看。')
                if created:
                    st.session_state['library-section'] = '待选择'
                    st.session_state['library-page-待选择'] = 1
            except Exception as exc:
                from url_import import import_error
                st.session_state['url-import-result'] = ('error', import_error(exc))
        if st.session_state.get('url-import-result'):
            level, message = st.session_state['url-import-result']
            getattr(st, level)(message)


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


def render_processing_options(row):
    ident=row['id']
    mode=st.radio('输出方式',['burn','files'],format_func=lambda v: '预览审核后烧录字幕' if v=='burn' else '保存视频＋字幕文件（不烧录）',key='mode-'+ident)
    saved=row['imported_subtitles']
    input_mode=st.radio('字幕获取方式',['auto','import'],index=1 if saved else 0,
                        format_func=lambda v: '自动识别 / 翻译' if v=='auto' else '导入现成字幕（跳过语音识别和翻译）',key='input-mode-'+ident)
    upload=None
    if input_mode=='import':
        st.caption('上传 SRT / VTT，最大 5 MB。中文字幕直接使用；双语字幕要求每条首行中文、后续原文。此模式不调用翻译服务。在线视频仍需下载。')
        upload=st.file_uploader('处理前导入字幕文件',type=['srt','vtt'],key='prepare-subtitle-'+ident)
        import_mode=st.radio('导入字幕内容',['chinese','bilingual'],format_func=lambda v: '中文字幕' if v=='chinese' else '双语字幕（首行中文，后续原文）',key='prepare-subtitle-mode-'+ident)
        if saved:
            st.caption('已保存上次提交的字幕，未选择新文件时重试会继续使用。')
        label='使用导入字幕并送审' if mode=='burn' else '保存视频和导入字幕'
    else:
        display=st.radio('字幕显示',['bilingual','chinese'],index=1 if row['subtitle_display']=='chinese' else 0,format_func=lambda v: '只显示中文字幕' if v=='chinese' else '中文＋原文双语字幕',key='display-'+ident)
        prefer=st.checkbox('优先使用已有字幕翻译（无字幕时识别语音）',str(row['prefer_subtitles'])=='1',key='prefer-'+ident)
        st.caption('支持平台字幕和视频内嵌文字字幕；只显示中文不会移除原视频画面上的文字。')
        label='翻译并送审' if mode=='burn' else '下载并生成字幕'
    if st.button(('重试：' if row['state']=='failed' else '')+label,key=ident):
        try:
            payload=None
            if input_mode=='import':
                from review_subtitle_import import prepare_subtitles
                if upload is not None:
                    prepared=prepare_subtitles(upload.getvalue(),upload.name,import_mode,row['duration'] or None)
                    payload=json.dumps(prepared,ensure_ascii=False)
                elif saved:
                    payload=saved
                    prepared=json.loads(saved)
                else:
                    raise ValueError('请先选择字幕文件')
                display=prepared['subtitle_display'];prefer=False
            elif not os.getenv('TRANSLATE_API_KEY'):
                raise ValueError('请先填写 .env 中的翻译服务配置并重启')
            with db() as c:
                c.execute("UPDATE videos SET state='queued',ocr=0,output_mode=?,subtitle_display=?,prefer_subtitles=?,imported_subtitles=?,error='' WHERE id=? AND hidden=0 AND state IN ('waiting','failed')",
                          (mode,display,int(prefer),payload,ident))
            st.rerun()
        except Exception as exc:
            from media_tools import safe_error
            st.error('无法开始处理：'+safe_error(exc))


def render_subtitle_import(row, folder, duration):
    with st.expander('导入字幕文件'):
        st.caption('支持 SRT / VTT（UTF-8、GB18030 或带 BOM 的 UTF-16），最大 5 MB。按文件时间轴替换当前语音字幕；中文字幕模式会清空原文并切换为只显示中文。双语模式要求每条首行中文、后续行原文。')
        st.caption('导入前请先保存下方尚未保存的修改。已保存的审核稿会自动备份，字幕样式和画面文字保留；导入不会自动翻译或开始烧录。')
        upload = st.file_uploader('选择字幕文件', type=['srt', 'vtt'], key='subtitle-upload-'+row['id'])
        mode = st.radio('文件中的字幕内容', ['chinese', 'bilingual'],
                        format_func=lambda v: '中文字幕' if v == 'chinese' else '双语字幕（首行中文，后续原文）',
                        key='subtitle-import-mode-'+row['id'])
        if st.button('导入并替换审核字幕', key='subtitle-import-'+row['id']):
            try:
                if upload is None:
                    raise ValueError('请先选择字幕文件')
                from review_subtitle_import import import_review_subtitles
                imported = import_review_subtitles(folder, upload.getvalue(), upload.name, mode, duration)
                st.session_state['subtitle-import-result-'+row['id']] = ('success', f'已导入 {len(imported["chinese"])} 条字幕，原审核稿已备份。请检查下方内容并更新字幕预览。')
                st.rerun()
            except Exception as exc:
                from media_tools import safe_error
                st.session_state['subtitle-import-result-'+row['id']] = ('error', '字幕导入失败：'+safe_error(exc))
        result = st.session_state.get('subtitle-import-result-'+row['id'])
        if result:
            getattr(st, result[0])(result[1])


def render_review(row,folder):
    from review_tools import atomic_json,validate_edit,video_info,subtitle_style,preview_frame,export_subtitles
    data=json.loads((folder/'transcript.json').read_text(encoding='utf-8'))
    source=next((p for p in folder.glob('source.*') if p.suffix in {'.mp4','.webm','.mkv','.mov','.avi','.m4v'}),None)
    if source: st.video(str(source))
    w,h,duration=video_info(source) if source else (1280,720,None)
    render_subtitle_import(row,folder,duration)
    revision=hashlib.sha256(json.dumps([data['original'],data['chinese'],data.get('subtitle_source')],ensure_ascii=False).encode()).hexdigest()[:12]
    style=subtitle_style(data.get('subtitle_style'),w,h)
    if data.get('subtitle_source'):
        st.caption('字幕来源：'+({'existing':'已有文字字幕（已跳过语音识别）','imported':'手动导入字幕文件'}.get(data['subtitle_source'],'语音识别')))
    st.caption('字幕位置以画面百分比表示：水平为居中锚点，垂直为字幕底边。')
    with st.form('edit-'+row['id']):
        title=st.text_input('中文标题',row['title_zh'] or row['title'])
        st.caption('合并字幕后，请同时清空多余行的原文和中文，该行会被忽略；保留行的结束时间请覆盖合并后的整段。')
        table=st.data_editor([{'开始':a[0],'结束':a[1],'原文':a[2],'中文':b[2]} for a,b in zip(data['original'],data['chinese'])],key='editor-'+row['id']+'-'+revision,num_rows='fixed')
        screen=st.data_editor([{'开始':a,'结束':b,'原文':'','中文':t} for a,b,t in data.get('screen',[])],key='screen-'+row['id'],num_rows='fixed') if data.get('screen') else []
        display=st.radio('字幕显示',['bilingual','chinese'],index=1 if data.get('subtitle_display')=='chinese' else 0,format_func=lambda v: '只显示中文字幕' if v=='chinese' else '中文＋原文双语字幕',key='review-display-'+row['id']+'-'+revision)
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
            if data.get('screen'): _,data['screen']=validate_edit(screen,duration)
            data['subtitle_display']=display
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

def filter_publishers(rows,platform_name):
    def identity(row):
        return (platform_name(row['url']), (row['publisher_url'] or '').rstrip('/') or row['publisher'] or '未知发布者')
    options={}
    for row in rows:
        ident=identity(row)
        options.setdefault(ident,{'name':row['publisher'] or '未知发布者','url':row['publisher_url'] or '', 'count':0})['count']+=1
    def widget_key(ident):
        return 'publisher-filter-'+hashlib.sha256(repr(ident).encode()).hexdigest()
    selected=[ident for ident in options if st.session_state.get(widget_key(ident),False)]
    with st.popover('选择发布者'+(f'（已选 {len(selected)} 个）' if selected else '（全部）'),use_container_width=True):
        query=st.text_input('搜索待选发布者',key='publisher-candidate-search',placeholder='输入名称或主页，缩小待选范围').strip().casefold()
        st.caption('搜索仅筛选候选项；勾选后筛选视频，可选择多个发布者。不勾选时显示全部。')
        if st.button('清空勾选',key='clear-publisher-filter'):
            for key in list(st.session_state):
                if key.startswith('publisher-filter-'): st.session_state[key]=False
        matches=[ident for ident,item in options.items() if not query or query in (item['name']+' '+item['url']).casefold()]
        if not matches: st.info('没有匹配的发布者，试试其他名称或主页。')
        with st.container(height=260):
            for ident in sorted(matches,key=lambda i:(options[i]['name'].casefold(),i)):
                item=options[ident]
                st.checkbox(f"{item['name']} · {ident[0]}（{item['count']} 个视频）",key=widget_key(ident),help=item['url'] or None)
        # Keep selections when their checkbox is temporarily hidden by a search.
        for ident in options:
            key=widget_key(ident)
            if ident not in matches and key in st.session_state: st.session_state[key]=st.session_state[key]
    selected={ident for ident in options if st.session_state.get(widget_key(ident),False)}
    if selected: st.caption('已选发布者：'+'、'.join(options[ident]['name']+' · '+ident[0] for ident in sorted(selected)))
    return [row for row in rows if not selected or identity(row) in selected]


@st.fragment(run_every=5)
def show_library():
    with db() as c: rows=c.execute('SELECT * FROM videos WHERE hidden=0 ORDER BY rowid DESC').fetchall()
    platform=st.selectbox('发布平台',['全部','Instagram','YouTube','X','本地视频'])
    order=st.selectbox('排序',['发布时间：最新优先','发布时间：最早优先'])
    def platform_name(url):
        if url.startswith('local://'): return '本地视频'
        host=urlparse(url).hostname or ''
        return 'Instagram' if 'instagram.com' in host else 'YouTube' if 'youtube.com' in host or host=='youtu.be' else 'X'
    rows=[r for r in rows if platform=='全部' or platform_name(r['url'])==platform]
    rows=filter_publishers(rows,platform_name)
    known=[r for r in rows if r['published_at']];unknown=[r for r in rows if not r['published_at']]
    rows=sorted(known,key=lambda r:r['published_at'][:19],reverse='最新' in order)+unknown
    sections={'待选择':{'waiting'},'处理中':{'queued','burn_queued','下载中','语音识别中','翻译中','画面文字识别中','字幕烧录中'},'审核区':{'review'},'已完成':{'done'},'失败':{'failed'}}
    section=st.radio('视频分区',list(sections),horizontal=True,key='library-section')
    states=sections[section]
    subset=[r for r in rows if r['state'] in states]
    st.caption(f'共 {len(subset)} 个视频；每页最多显示 12 个，详情按需加载。')
    if not subset:
        st.info('暂无视频')
        return
    pages=max(1,(len(subset)+11)//12)
    page_key='library-page-'+section
    if st.session_state.get(page_key,1)>pages: st.session_state[page_key]=pages
    page=st.number_input('页码',min_value=1,max_value=pages,step=1,key=page_key)
    if section in {'待选择','审核区','已完成'}:
        with st.popover('批量删除本页视频'):
            st.caption('删除后不再检测入库。只移除列表记录，本地视频、字幕和成品文件均保留。')
            chosen=[]
            for row in subset[(page-1)*12:page*12]:
                if st.checkbox(row['title_zh'] or row['title'],key='delete-select-'+row['id']): chosen.append(row['id'])
            if st.button('删除勾选视频',disabled=not chosen,key='delete-page'):
                from library_store import dismiss
                with db() as c:
                    for ident in chosen: dismiss(c,ident)
                st.rerun()
    for r in subset[(page-1)*12:page*12]:
        with st.container(border=True):
            image,body=st.columns([1,3])
            with image:
                if r['thumb']:
                    if r['state'] in {'waiting','review','done'}: st.image(r['thumb'],width=100)
                    else: st.image(r['thumb'],use_container_width=True)
            with body:
                st.subheader(r['title_zh'] or r['title'])
                st.caption('发布时间：'+(r['published_at'] or '平台未提供或尚未获取'))
                if r['state'] in {'waiting','review','done'}:
                    if st.button('从列表删除' if r['state']=='done' else '删除视频',key='delete-'+r['id'],help='移出界面并阻止重新入库，本地文件保留'):
                        from library_store import dismiss
                        with db() as c: dismiss(c,r['id'])
                        st.rerun()
                if st.checkbox('展开审核与字幕设置' if r['state']=='review' else '展开成品与字幕下载' if r['state']=='done' else '展开视频详情与处理选项',key='details-'+r['id']):
                    st.text('原标题：'+r['title'])
                    st.text('发布账号：'+(r['publisher'] or '暂未获取，重新检测后补齐'))
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
                        render_processing_options(r)
                    if r['error']: st.error(r['error'])
                    if r['state']=='done':
                        folder=output_folder(DATA,r)
                        video=(folder/'result.mp4') if r['output_mode']!='files' else next((p for p in folder.glob('source.*') if p.suffix in {'.mp4','.mkv','.webm','.mov'}),None)
                        if video and video.exists():
                            st.video(str(video))
                            st.caption('已保存：'+str(video))
                        st.caption('字幕及原视频目录：'+str(folder))
                        for name in ['original.srt','chinese.srt','bilingual.srt','bilingual.ass','chinese.ass','screen-chinese.srt']:
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
                        if (folder/'subtitle-warning.txt').exists(): st.warning('平台附带字幕未获取成功，将尝试读取内嵌字幕，无可用字幕时使用语音识别。')
                        with st.expander('原文 / 中文字幕'):
                            data=json.loads((folder/'transcript.json').read_text(encoding='utf-8'))
                            st.dataframe([{'开始':a[0],'结束':a[1],'原文':a[2],'中文':b[2]} for a,b in zip(data['original'],data['chinese'])],use_container_width=True)
                            if data.get('screen'):
                                st.caption('历史画面字幕')
                                st.dataframe([{'开始':a,'结束':b,'画面中文':t} for a,b,t in data['screen']],use_container_width=True)

if __name__=='__main__': main()
