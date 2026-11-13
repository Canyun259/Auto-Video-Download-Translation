import unittest,tempfile
from pathlib import Path
from review_tools import validate_edit,fit_ass
class ReviewTests(unittest.TestCase):
    def test_edit_and_time_validation(self):
        rows=[{'开始':0,'结束':2,'原文':'hello','中文':'你好'}]
        a,b=validate_edit(rows,3);self.assertEqual(b,[[0.,2.,'你好']])
        rows[0]['结束']=5
        with self.assertRaises(ValueError):validate_edit(rows,3)
    def test_portrait_wrap(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            p=Path(directory)/'test.ass'
            fit_ass(p,[(0,2,'A long English sentence that must fit inside a portrait video without clipping.')],[(0,2,'这是一段用于检查竖屏视频自动换行的中文字幕，确保字幕不会被画面边缘裁掉。')],[],360,640)
            text=p.read_text(encoding='utf-8');self.assertIn('PlayResX: 360',text);self.assertIn('PlayResY: 640',text);self.assertGreater(text.count(r'\N'),2)
