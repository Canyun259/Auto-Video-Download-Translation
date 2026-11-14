import json, tempfile, unittest, subprocess
from pathlib import Path
from unittest.mock import patch
from review_tools import fit_ass,subtitle_style,export_subtitles,preview_frame,encode
from media_tools import ffmpeg_path

class SubtitleOutputTests(unittest.TestCase):
    def test_style_validation(self):
        for style in [{'font':'bad,style'},{'x':float('nan')},{'size':0}]:
            with self.assertRaises(ValueError): subtitle_style(style,640,360)

    def test_export_and_real_preview(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as temp:
            folder=Path(temp).resolve()
            subprocess.run([ffmpeg_path(),'-y','-f','lavfi','-i','color=c=gray:s=640x360:d=2','-c:v','libx264',str(folder/'source.mp4')],check=True,capture_output=True)
            data={'original':[[0,2,'Hello world']],'chinese':[[0,2,'你好，世界']],'screen':[],
                  'subtitle_style':{'font':'Microsoft YaHei','size':28,'x':40,'y':80}}
            (folder/'transcript.json').write_text(json.dumps(data),encoding='utf-8')
            export_subtitles(folder,data)
            self.assertFalse((folder/'result.mp4').exists())
            self.assertIn('你好，世界\nHello world',(folder/'bilingual.srt').read_text(encoding='utf-8'))
            self.assertIn(r'\pos(256,288)',(folder/'bilingual.ass').read_text(encoding='utf-8'))
            image=preview_frame(folder,data,1)
            self.assertGreater(image.stat().st_size,1000)
            self.assertEqual((folder/'preview.ass').read_bytes(),(folder/'bilingual.ass').read_bytes())
            encode(folder,lambda _:None)
            self.assertGreater((folder/'result.mp4').stat().st_size,1000)

if __name__=='__main__': unittest.main()
