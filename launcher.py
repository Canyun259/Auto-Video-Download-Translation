"""Local Windows service manager; only controls this project's Streamlit process."""
import os,sys,time,json,socket,subprocess,threading,queue,webbrowser,importlib.util,sqlite3
from pathlib import Path
BASE=Path(__file__).resolve().parent
PYTHON=BASE/'.venv'/'Scripts'/'python.exe'
APP=BASE/'local_ui.py'
DATA=BASE/'local-data'
LOGS=DATA/'logs'
URL='http://127.0.0.1:8501'

def own_process(p):
    try:
        args=p.cmdline()
        if not any('python' in Path(a).name.lower() for a in args[:1]): return False
        if 'streamlit' not in args or 'run' not in args: return False
        target=Path(args[args.index('run')+1])
        if not target.is_absolute(): target=Path(p.cwd())/target
        return target.resolve()==APP.resolve()
    except Exception:return False

def processes():
    import psutil
    return [p for p in psutil.process_iter() if own_process(p)]

def busy():
    path=DATA/'library.sqlite'
    if not path.exists():return False
    with sqlite3.connect(path,timeout=5) as c:
        return c.execute("SELECT count(*) FROM videos WHERE state NOT IN ('waiting','review','done','failed','queued','burn_queued')").fetchone()[0]>0

def port_open():
    with socket.socket() as s:
        s.settimeout(.5);return s.connect_ex(('127.0.0.1',8501))==0

def checks():
    missing=[m for m in ['streamlit','dotenv','yt_dlp','faster_whisper','cv2','rapidocr','psutil'] if not importlib.util.find_spec(m)]
    if missing:raise RuntimeError('缺少依赖：'+', '.join(missing)+'。请运行“安装或更新依赖”。')
    from dotenv import dotenv_values
    cfg=dotenv_values(BASE/'.env')
    if not cfg.get('TRANSLATE_API_KEY'):raise RuntimeError('请先在项目 .env 填写翻译密钥。')
    url=cfg.get('TRANSLATE_BASE_URL','')
    if not url.startswith('https://') or any(x in url for x in ('YOUR_','{','你的')):raise RuntimeError('翻译接口地址未填写完整，请检查 .env。')
    if not cfg.get('TRANSLATE_MODEL'):raise RuntimeError('请填写 TRANSLATE_MODEL。')
    from media_tools import ffmpeg_path
    ff=Path(ffmpeg_path())
    if not ff.is_file() or not ff.with_name('ffprobe.exe').is_file():raise RuntimeError('未找到 FFmpeg/ffprobe，请先安装 FFmpeg。')
    from gpu_support import cuda_status
    ready,reason=cuda_status()
    return '基础检查通过。'+('CUDA 可用。' if ready else 'CUDA 暂不可用，自动模式将用 CPU：'+reason)

class ManagerLock:
    def __enter__(self):
        import msvcrt
        DATA.mkdir(exist_ok=True)
        self.file=(DATA/'manager.lock').open('a+b');self.file.seek(0)
        if self.file.read(1)==b'':self.file.write(b'0');self.file.flush()
        self.file.seek(0)
        try:msvcrt.locking(self.file.fileno(),msvcrt.LK_NBLCK,1)
        except OSError:self.file.close();raise RuntimeError('另一项启动/停止操作正在执行，请稍后再试。')
        return self
    def __exit__(self,*args):
        import msvcrt
        self.file.seek(0);msvcrt.locking(self.file.fileno(),msvcrt.LK_UNLCK,1);self.file.close()

def start(open_browser=True):
    with ManagerLock():
        existing=processes()
        if existing:
            message='程序已运行，复用已有服务。'
        else:
            if port_open():raise RuntimeError('8501 端口被其他程序占用，未启动或关闭其他程序。')
            checks();LOGS.mkdir(parents=True,exist_ok=True)
            log=LOGS/(time.strftime('startup-%Y%m%d-%H%M%S')+'.log')
            env=os.environ.copy();env['PYTHONIOENCODING']='utf-8';env['PYTHONUNBUFFERED']='1'
            with log.open('w',encoding='utf-8') as out:
                p=subprocess.Popen([str(PYTHON),'-m','streamlit','run',str(APP),'--server.address','127.0.0.1','--server.port','8501','--server.headless','true','--browser.gatherUsageStats','false'],cwd=BASE,env=env,stdout=out,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
            deadline=time.monotonic()+40
            while not port_open():
                if p.poll() is not None:raise RuntimeError('启动失败，请查看日志：'+str(log))
                if time.monotonic()>deadline:raise RuntimeError('启动仍未就绪，请查看日志：'+str(log)+'；不要重复启动。')
                time.sleep(.5)
            message='启动成功。日志：'+str(log)
    if open_browser:webbrowser.open(URL)
    return message

def stop():
    import psutil
    with ManagerLock():
        roots=processes();targets={}
        for p in roots:
            if not own_process(p):continue
            try:
                for child in p.children(recursive=True):targets[(child.pid,child.create_time())]=child
                targets[(p.pid,p.create_time())]=p
            except psutil.NoSuchProcess:pass
        for p in targets.values():
            try:p.terminate()
            except psutil.NoSuchProcess:pass
        _,alive=psutil.wait_procs(list(targets.values()),timeout=8)
        for p in alive:
            try:p.kill()
            except psutil.NoSuchProcess:pass
    return '已停止本项目服务。' if roots else '程序当前未运行。'

def gui(action=None):
    import tkinter as tk
    from tkinter import ttk,messagebox
    root=tk.Tk();root.title('本地视频翻译台 · 启动管理');root.geometry('620x380')
    status=tk.StringVar(value='正在检查状态…');messages=queue.Queue();buttons=[]
    ttk.Label(root,text='本地视频翻译台',font=('Microsoft YaHei UI',20)).pack(pady=20)
    ttk.Label(root,textvariable=status,wraplength=570).pack(pady=10)
    def launch(name):
        if name in ('停止','重启'):
            try:active=busy()
            except Exception:active=True
            if active and not messagebox.askyesno('有任务正在处理','停止会中断当前任务，重启后需在失败页重试。仍要继续吗？'):return
        for b in buttons:b.config(state='disabled')
        status.set('正在'+name+'…')
        def run():
            try:
                if name=='启动':result=start()
                elif name=='重启':stop();result=start()
                elif name=='停止':result=stop()
                else:result=checks()
                messages.put((True,result))
            except Exception as exc:messages.put((False,str(exc)))
        threading.Thread(target=run,daemon=True).start()
    frame=ttk.Frame(root);frame.pack(pady=15)
    for i,label in enumerate(['启动','重启','停止','检查环境']):
        b=ttk.Button(frame,text=label,command=lambda name=label:launch(name));b.grid(row=0,column=i,padx=5);buttons.append(b)
    ttk.Button(root,text='打开网页',command=lambda:webbrowser.open(URL)).pack(pady=5)
    def logs():LOGS.mkdir(parents=True,exist_ok=True);os.startfile(LOGS)
    ttk.Button(root,text='打开日志文件夹',command=logs).pack(pady=5)
    ttk.Label(root,text='关闭这个管理窗口不会停止服务。\n安装或更新依赖请使用单独的安装入口。',justify='center').pack(pady=15)
    def poll():
        try:
            ok,text=messages.get_nowait();status.set(text)
            for b in buttons:b.config(state='normal')
            if not ok:messagebox.showerror('操作未完成',text)
        except queue.Empty:pass
        root.after(200,poll)
    status.set('程序正在运行。' if processes() else '程序未启动。')
    poll()
    if action:root.after(300,lambda:launch(action))
    def close():
        if buttons and str(buttons[0]['state'])=='disabled':
            messagebox.showinfo('操作进行中','请等待当前操作结束后再关闭管理窗口。')
            return
        root.destroy()
    root.protocol('WM_DELETE_WINDOW',close)
    root.mainloop()

if __name__=='__main__':
    if '--check' in sys.argv:print(checks())
    elif '--status' in sys.argv:print('running' if processes() else 'stopped')
    else:gui({'start':'启动','restart':'重启','stop':'停止'}.get(sys.argv[1] if len(sys.argv)>1 else ''))

