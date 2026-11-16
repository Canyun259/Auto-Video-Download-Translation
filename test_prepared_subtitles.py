import ast
import io
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from streamlit.testing.v1 import AppTest
from database_setup import ensure_schema, ManagedConnection
from review_subtitle_import import prepare_subtitles

SRT='1\n00:00:00,000 --> 00:00:02,000\n现成字幕\n'

class PreparedSubtitleTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder=Path(self.temp.name)
        self.payload=json.dumps(prepare_subtitles(SRT.encode(),'ready.srt'),ensure_ascii=False)
        self.row={'id':'test','url':'local://test','imported_subtitles':self.payload,'prefer_subtitles':1,
                  'ocr':1,'output_mode':'burn','thumb':None,'subtitle_display':'bilingual'}
        (self.folder/'source.mp4').write_bytes(b'placeholder')
        tree=ast.parse(Path('local_ui.py').read_text(encoding='utf-8'))
        self.functions={n.name:ast.unparse(n) for n in tree.body if isinstance(n,ast.FunctionDef)}
        self.env={'json':json,'DATA':self.folder,'output_folder':Mock(return_value=self.folder),
                  'update':Mock(),'set_progress':Mock(),'opts':lambda:{},'app':Mock(),'screen_cues':Mock()}
        exec(self.functions['process'],self.env)

    def test_local_and_remote_skip_translation_and_speech(self):
        for url,mode in [('local://test','burn'),('https://youtu.be/test','files')]:
            with self.subTest(url=url), patch('review_tools.video_info',return_value=(640,360,3)), \
                 patch('subtitle_source.existing_cues',side_effect=AssertionError('must not inspect platform subtitles')), \
                 patch('gpu_support.speech_device',side_effect=AssertionError('must not load speech model')), \
                 patch('yt_dlp.YoutubeDL') as downloader, patch('review_tools.export_subtitles') as export, \
                 patch('cover_tools.save_cover'):
                self.row.update(url=url,output_mode=mode)
                downloader.return_value.__enter__.return_value.extract_info.return_value={'subtitles':{'en':[{}]}}
                self.env['process'](self.row,'small')
                data=json.loads((self.folder/'transcript.json').read_text(encoding='utf-8'))
                self.assertEqual(data['chinese'][0][2],'现成字幕')
                self.assertEqual(data['subtitle_display'],'chinese')
                self.assertEqual(data['screen'],[])
                self.env['app'].translate.assert_not_called()
                self.env['screen_cues'].assert_not_called()
                self.env['update'].assert_called_with('test','review' if mode=='burn' else 'done')
                if mode=='files': export.assert_called_once()
                if url.startswith('https'):
                    downloader.return_value.__enter__.return_value.extract_info.assert_called_once_with(url,download=True)
                    downloader.return_value.__enter__.return_value.process_ie_result.assert_not_called()

    def test_actual_duration_failure_does_not_fallback_or_overwrite(self):
        draft=self.folder/'transcript.json';draft.write_text('previous',encoding='utf-8')
        with patch('review_tools.video_info',return_value=(640,360,1)), self.assertRaisesRegex(ValueError,'视频长度'):
            self.env['process'](self.row,'small')
        self.assertEqual(draft.read_text(encoding='utf-8'),'previous')
        self.env['app'].translate.assert_not_called()

    def test_auto_mode_still_translates(self):
        self.row.update(imported_subtitles=None,ocr=1)
        self.env['app'].translate.return_value=[[0,2,'自动译文']]
        with patch('subtitle_source.existing_cues',return_value=[[0,2,'source']]):
            self.env['process'](self.row,'small')
        self.env['app'].translate.assert_called_once()
        self.env['screen_cues'].assert_not_called()
        self.assertEqual(json.loads((self.folder/'transcript.json').read_text(encoding='utf-8'))['subtitle_source'],'existing')

    def test_ui_without_api_key_queue_and_retry(self):
        path=self.folder/'library.sqlite'
        with sqlite3.connect(path,factory=ManagedConnection) as c:
            ensure_schema(c)
            c.execute("INSERT INTO videos(id,url,title,duration) VALUES('test','local://test','test',3)")
        script=('import streamlit as st\nimport os,json,sqlite3\nfrom database_setup import ManagedConnection\n'
                +'def db():\n c=sqlite3.connect('+repr(str(path))+',factory=ManagedConnection)\n c.row_factory=sqlite3.Row\n return c\n'
                +self.functions['render_processing_options']
                +'\nwith db() as c: row=c.execute("SELECT * FROM videos").fetchone()\nrender_processing_options(row)\n')
        with patch.dict(os.environ,{'TRANSLATE_API_KEY':''}):
            page=AppTest.from_string(script).run(timeout=30)
            self.assertFalse(any('画面' in c.label for c in page.checkbox))
            page.radio(key='input-mode-test').set_value('import').run(timeout=30)
            page.button(key='test').click().run(timeout=30)
            self.assertIn('请先选择字幕文件',page.error[0].value)
            upload=io.BytesIO(SRT.encode());upload.name='ready.srt'
            with patch('streamlit.file_uploader',return_value=upload):
                page.button(key='test').click().run(timeout=30)
            self.assertFalse(page.exception)
            with sqlite3.connect(path,factory=ManagedConnection) as c:
                row=c.execute('SELECT state,imported_subtitles,ocr,prefer_subtitles FROM videos').fetchone()
                self.assertEqual(row[0],'queued');self.assertEqual(row[2:],(0,0))
                self.assertEqual(json.loads(row[1])['chinese'][0][2],'现成字幕')
                c.execute("UPDATE videos SET state='failed'")
            page=AppTest.from_string(script).run(timeout=30)
            self.assertEqual(page.radio(key='input-mode-test').value,'import')
            page.button(key='test').click().run(timeout=30)
            self.assertFalse(page.exception)
            with sqlite3.connect(path,factory=ManagedConnection) as c:
                self.assertEqual(c.execute('SELECT state FROM videos').fetchone()[0],'queued')
                c.execute("UPDATE videos SET state='failed'")
            with patch.dict(os.environ,{'TRANSLATE_API_KEY':'test'}):
                page.radio(key='input-mode-test').set_value('auto').run(timeout=30)
                page.button(key='test').click().run(timeout=30)
            with sqlite3.connect(path,factory=ManagedConnection) as c:
                self.assertIsNone(c.execute('SELECT imported_subtitles FROM videos').fetchone()[0])

if __name__=='__main__':unittest.main()
