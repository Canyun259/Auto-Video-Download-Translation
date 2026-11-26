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


class EmptyReviewRowsTests(unittest.TestCase):
    def test_merged_rows_with_blank_or_retained_timestamps(self):
        rows=[{'开始':0,'结束':4,'原文':'merged sentence','中文':'合并后的字幕'},
              {'开始':None,'结束':None,'原文':None,'中文':None},
              {'开始':float('nan'),'结束':float('nan'),'原文':' ','中文':''},
              {'开始':2,'结束':4,'原文':'','中文':''},
              {'开始':4,'结束':6,'原文':'next','中文':'下一句'}]
        original,chinese=validate_edit(rows,6)
        self.assertEqual([r[:2] for r in original],[[0.,4.],[4.,6.]])
        self.assertEqual([r[2] for r in chinese],['合并后的字幕','下一句'])
    def test_partial_rows_report_original_row_number(self):
        rows=[{'开始':None,'结束':None,'原文':None,'中文':None},
              {'开始':None,'结束':2,'原文':'keep','中文':'保留'}]
        with self.assertRaisesRegex(ValueError,'第 2 行.*时间不能为空'):validate_edit(rows,3)
        rows[1]['开始']=0;rows[1]['中文']=None
        with self.assertRaisesRegex(ValueError,'第 2 行.*中文字幕不能为空'):validate_edit(rows,3)
    def test_missing_original_is_not_stringified_as_none(self):
        original,_=validate_edit([{'开始':0,'结束':1,'原文':None,'中文':'译文'}],1)
        self.assertEqual(original[0][2],'')
    def test_clearing_all_rows_and_rejecting_overlap(self):
        self.assertEqual(validate_edit([{'开始':0,'结束':1,'原文':'','中文':''}],1),([],[]))
        with self.assertRaisesRegex(ValueError,'第 2 行'):
            validate_edit([{'开始':0,'结束':3,'原文':'a','中文':'甲'},{'开始':2,'结束':4,'原文':'b','中文':'乙'}],4)
