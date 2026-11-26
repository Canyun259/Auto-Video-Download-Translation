import tempfile, unittest, subprocess
from pathlib import Path
from unittest.mock import patch
from subtitle_source import parse_srt,existing_cues
from review_tools import fit_ass,export_subtitles,preview_frame,encode
from media_tools import ffmpeg_path

class ExistingSubtitleTests(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(parse_srt('1\n00:00:01,200 --> 00:00:02,300\n<i>Hello</i> &amp; world\n'),[(1.2,2.3,'Hello & world')])
        self.assertEqual(parse_srt('invalid'),[])

    def test_existing_and_chinese_output(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp)
            video=folder/'source.mp4'
            subprocess.run([ffmpeg_path(),'-y','-f','lavfi','-i','color=c=gray:s=640x360:d=2','-c:v','libx264',str(video)],check=True,capture_output=True)
            self.assertEqual(existing_cues(folder,video),[])
            (folder/'source.en.vtt').write_text('WEBVTT\n\n00:00:00.000 --> 00:00:01.500\nHello world\n',encoding='utf-8')
            cues=existing_cues(folder,video)
            self.assertEqual(cues,[(0.,1.5,'Hello world')])
            data={'original':cues,'chinese':[(0,1.5,'你好')],'screen':[],'subtitle_display':'chinese'}
            import json
            (folder/'transcript.json').write_text(json.dumps(data),encoding='utf-8')
            export_subtitles(folder,data,video)
            self.assertNotIn('Hello world',(folder/'chinese.ass').read_text(encoding='utf-8'))
            self.assertIn('Hello world',(folder/'bilingual.ass').read_text(encoding='utf-8'))
            preview_frame(folder,data,1)
            self.assertEqual((folder/'preview.ass').read_bytes(),(folder/'chinese.ass').read_bytes())
            encode(folder,lambda _:None)
            self.assertGreater((folder/'result.mp4').stat().st_size,1000)
            embedded=folder/'embedded.mp4'
            subprocess.run([ffmpeg_path(),'-y','-i',str(video),'-i',str(folder/'source.en.vtt'),'-c:v','copy','-c:s','mov_text',str(embedded)],check=True,capture_output=True)
            (folder/'source.en.vtt').unlink()
            self.assertEqual(existing_cues(folder,embedded),cues)

if __name__=='__main__': unittest.main()
