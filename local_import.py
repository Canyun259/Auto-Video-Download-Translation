from contextlib import closing
"""Import a validated local video into managed storage without changing its source."""
import hashlib, shutil, tempfile
from pathlib import Path
from review_tools import video_info
from output_paths import readable_path, checked

EXTENSIONS={'.mp4','.mkv','.mov','.webm','.avi','.m4v'}

def import_video(data,connect,source,name=None):
    if isinstance(source,(str,Path)):
        source=Path(str(source).strip().strip('"')).expanduser().resolve()
        if not source.is_file(): raise ValueError('本地视频文件不存在')
        name=source.name
    suffix=Path(name or '').suffix.lower()
    if suffix not in EXTENSIONS: raise ValueError('请选择 MP4、MKV、MOV、WEBM、AVI 或 M4V 视频')
    data.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='import-',dir=data) as tmp:
        staged=Path(tmp)/('source'+suffix)
        digest=hashlib.sha256()
        def copy(stream):
            with staged.open('wb') as out:
                while chunk:=stream.read(4*1024*1024): digest.update(chunk);out.write(chunk)
        if isinstance(source,Path):
            with source.open('rb') as stream: copy(stream)
        else:
            source.seek(0);copy(source)
        _,_,duration=video_info(staged)
        ident='local_'+digest.hexdigest()[:24]
        with closing(connect()) as c,c:
            if c.execute('SELECT id FROM videos WHERE id=?',(ident,)).fetchone(): return ident,False
            row={'id':ident,'url':'local://'+ident,'title':Path(name).stem,'publisher':'本地导入'}
            relative=readable_path(row)
            folder=checked(data/'output',relative);folder.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(staged,folder/('source'+suffix))
            c.execute('INSERT INTO videos(id,url,title,thumb,duration,publisher,output_dir) VALUES(?,?,?,?,?,?,?)',
                      (ident,row['url'],row['title'],'',duration,row['publisher'],relative.as_posix()))
        return ident,True
