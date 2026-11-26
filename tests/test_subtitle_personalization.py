import ast,json,sqlite3,subprocess,tempfile,unittest
from pathlib import Path
from PIL import Image
from streamlit.testing.v1 import AppTest
from review_tools import subtitle_style,fit_ass,preview_frame,export_subtitles,atomic_json,encode
from media_tools import ffmpeg_path
from database_setup import ManagedConnection

class SubtitlePersonalizationTests(unittest.TestCase):
    def test_invalid_style_and_legacy_defaults(self):
        defaults=subtitle_style({'size':30,'x':40},640,360)
        self.assertEqual(defaults['chinese_color'],'#FFFFFF')
        self.assertEqual(defaults['outline'],2)
        self.assertFalse(defaults['box'])
        for value in [{'chinese_color':'red'},{'original_color':'#12,456'},{'outline':-1},
                      {'shadow':float('nan')},{'box_opacity':101},{'bold':'yes'},{'order':'bad'}]:
            with self.subTest(value=value),self.assertRaises(ValueError):subtitle_style(value,640,360)

    def test_real_colors_order_box_preview_export_and_burn(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            folder=Path(directory).resolve()
            subprocess.run([ffmpeg_path(),'-v','error','-y','-f','lavfi','-i','color=c=gray:s=640x360:d=2','-c:v','libx264',str(folder/'source.mp4')],check=True)
            data={'original':[[0,2,'Original text']],'chinese':[[0,2,'中文字幕']],'screen':[],
                  'subtitle_style':{'size':30,'chinese_color':'#FF0000','original_color':'#00FF00','outline_color':'#0000FF',
                                    'bold':True,'italic':True,'shadow':2,'box':True,'box_opacity':60,'outline':4,'order':'original_first'}}
            atomic_json(folder/'transcript.json',data)
            image=preview_frame(folder,data,1)
            with Image.open(image) as frame:
                rgb=frame.convert('RGB')
                pixels=list(rgb.get_flattened_data() if hasattr(rgb,'get_flattened_data') else rgb.getdata())
            self.assertGreater(sum(r>150 and r>g*2 and r>b*2 for r,g,b in pixels),30)
            self.assertGreater(sum(g>150 and g>r*2 and g>b*2 for r,g,b in pixels),30)
            ass=(folder/'preview.ass').read_text(encoding='utf-8')
            self.assertIn('&H66FF0000',ass)
            self.assertIn(r'{\1c&H00FF00&}Original text\N{\1c&H0000FF&}中文字幕',ass)
            export_subtitles(folder,data)
            self.assertEqual((folder/'preview.ass').read_bytes(),(folder/'bilingual.ass').read_bytes())
            data['subtitle_display']='chinese'
            atomic_json(folder/'transcript.json',data)
            encode(folder,lambda _:None)
            self.assertGreater((folder/'result.mp4').stat().st_size,1000)
            chinese=(folder/'chinese.ass').read_text(encoding='utf-8')
            self.assertNotIn('Original text',chinese)
            self.assertIn('&H000000FF',chinese)

    def test_review_controls_save_and_reopen(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            folder=Path(directory).resolve()
            (folder/'transcript.json').write_text(json.dumps({'original':[[0,1,'Hello']],'chinese':[[0,1,'你好']],'screen':[]}),encoding='utf-8')
            with sqlite3.connect(folder/'test.sqlite',factory=ManagedConnection) as c:
                c.execute('CREATE TABLE videos(id TEXT,title_zh TEXT)')
                c.execute("INSERT INTO videos VALUES('sample','标题')")
            tree=ast.parse((Path(__file__).resolve().parents[1] / 'local_ui.py').read_text(encoding='utf-8'))
            function=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='render_review')
            script='from database_setup import ManagedConnection\nimport json,hashlib,sqlite3\nfrom pathlib import Path\nimport streamlit as st\nfolder=Path('+repr(str(folder))+')\ndef db(): return sqlite3.connect(folder/"test.sqlite",factory=ManagedConnection)\ndef render_subtitle_import(*args): pass\n'+ast.unparse(function)+'\nrender_review({"id":"sample","title":"Title","title_zh":"标题"},folder)'
            page=AppTest.from_string(script).run(timeout=30)
            self.assertFalse(page.exception)
            self.assertEqual(len(page.color_picker),3)
            next(n for n in page.color_picker if n.label=='中文字幕颜色').set_value('#FF8800')
            next(n for n in page.checkbox if n.label=='粗体').check()
            next(n for n in page.checkbox if n.label=='使用半透明背景框').check()
            next(n for n in page.button if n.label=='保存修改').click().run()
            self.assertFalse(page.exception)
            saved=json.loads((folder/'transcript.json').read_text(encoding='utf-8'))['subtitle_style']
            self.assertEqual(saved['chinese_color'],'#FF8800')
            self.assertTrue(saved['bold']);self.assertTrue(saved['box'])
            reopened=AppTest.from_string(script).run(timeout=30)
            self.assertFalse(reopened.exception)
            self.assertEqual(next(n for n in reopened.color_picker if n.label=='中文字幕颜色').value.lower(),'#ff8800')
            self.assertTrue(next(n for n in reopened.checkbox if n.label=='使用半透明背景框').value)

if __name__=='__main__':unittest.main()
