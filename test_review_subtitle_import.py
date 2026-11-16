import ast
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
from review_subtitle_import import read_captions, import_review_subtitles
from review_tools import fit_ass

SRT = '1\n00:00:00,000 --> 00:00:01,500\n你好\n\n2\n00:00:01,500 --> 00:00:02,000\n再见\n'

class SubtitleImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.path = self.folder/'transcript.json'
        self.data = {'original': [[0, 2, 'old']], 'chinese': [[0, 2, '旧字幕']],
                     'screen': [[0, 1, '画面文字']], 'subtitle_style': {'font': 'Arial', 'size': 20, 'x': 50, 'y': 90}}
        self.path.write_text(json.dumps(self.data), encoding='utf-8')

    def test_chinese_backup_and_output(self):
        before = self.path.read_bytes()
        result = import_review_subtitles(self.folder, SRT.encode(), 'test.srt', duration=2)
        self.assertEqual([r[2] for r in result['chinese']], ['你好', '再见'])
        self.assertEqual(result['original'], [[0, 1.5, ''], [1.5, 2, '']])
        self.assertEqual(result['screen'], self.data['screen'])
        self.assertEqual(result['subtitle_style'], self.data['subtitle_style'])
        self.assertEqual(result['subtitle_display'], 'chinese')
        self.assertEqual(next(self.folder.glob('transcript-before-import-*.json')).read_bytes(), before)
        fit_ass(self.folder/'preview.ass', result['original'], result['chinese'], result['screen'], 640, 360, display=result['subtitle_display'])
        text = (self.folder/'preview.ass').read_text(encoding='utf-8')
        self.assertIn('你好', text)
        self.assertNotIn('旧字幕', text)

    def test_vtt_bilingual_and_encodings(self):
        vtt = 'WEBVTT\n\nNOTE ignored\ncomment\n\ncue-1\n00:00.000 --> 00:01.500 align:start\n<b>你好</b>\nHello &amp; welcome\n'
        result = import_review_subtitles(self.folder, vtt.encode('utf-8-sig'), 'test.vtt', 'bilingual', 2)
        self.assertEqual(result['original'][0][2], 'Hello & welcome')
        self.assertEqual(result['chinese'][0][2], '你好')
        for encoding in ('utf-8-sig', 'utf-16', 'gb18030'):
            self.assertEqual(read_captions(SRT.encode(encoding), 'test.SRT')[0][2], '你好')

    def test_failures_preserve_draft(self):
        before = self.path.read_bytes()
        cases = [(b'', 'test.srt', 'chinese', 2), (b'bad', 'test.srt', 'chinese', 2),
                 (SRT.encode(), 'test.ass', 'chinese', 2), (SRT.encode(), 'test.srt', 'chinese', 1),
                 (SRT.encode(), 'test.srt', 'bilingual', 2),
                 (SRT.replace('00:00:01,500 -->', '00:00:01,000 -->').encode(), 'test.srt', 'chinese', 2),
                 (SRT.replace('00:00:02,000', '00:00:60,000').encode(), 'test.srt', 'chinese', 100),
                 ((SRT+'\nmalformed block').encode(), 'test.srt', 'chinese', 2)]
        for content, name, mode, duration in cases:
            with self.subTest(content=content), self.assertRaises(ValueError):
                import_review_subtitles(self.folder, content, name, mode, duration)
            self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(list(self.folder.glob('transcript-before-import-*')), [])

    def test_review_ui_import_refresh_and_error(self):
        tree = ast.parse(Path('local_ui.py').read_text(encoding='utf-8'))
        functions = [ast.unparse(n) for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in {'render_subtitle_import', 'render_review'}]
        script = ('import streamlit as st\nimport json,hashlib\nfrom pathlib import Path\n'+ '\n'.join(functions)
                  + '\nrender_review({"id":"test", "title":"Video", "title_zh":""}, Path('+repr(str(self.folder))+'))')
        page = AppTest.from_string(script).run(timeout=30)
        self.assertFalse(page.exception)
        self.assertEqual(len(page.dataframe[0].value), 1)
        upload = io.BytesIO(SRT.encode()); upload.name = 'new.srt'
        with patch('streamlit.file_uploader', return_value=upload):
            page.button(key='subtitle-import-test').click().run(timeout=30)
        self.assertFalse(page.exception)
        self.assertIn('已导入 2 条', page.success[0].value)
        self.assertEqual(len(page.dataframe[0].value), 2)
        self.assertEqual(page.dataframe[0].value.iloc[0]['中文'], '你好')
        self.assertEqual(next(r for r in page.radio if r.label == '字幕显示').value, 'chinese')
        self.assertEqual(json.loads(self.path.read_text(encoding='utf-8'))['chinese'][0][2], '你好')
        with patch('streamlit.file_uploader', return_value=None):
            page.button(key='subtitle-import-test').click().run(timeout=30)
        self.assertIn('请先选择', page.error[0].value)
        self.assertFalse(page.exception)

if __name__ == '__main__': unittest.main()
