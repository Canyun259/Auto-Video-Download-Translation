import subprocess,tempfile,unittest
from pathlib import Path
from io import BytesIO
from unittest.mock import patch,MagicMock
from PIL import Image
from cover_tools import save_cover
from media_tools import ffmpeg_path

class CoverTests(unittest.TestCase):
    def test_image_and_reuse(self):
        data=BytesIO();Image.new('RGBA',(16,24)).save(data,format='PNG')
        response=MagicMock();response.__enter__.return_value=response
        response.iter_content.return_value=[data.getvalue()]
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as tmp:
            folder=Path(tmp)
            with patch('cover_tools.requests.get',return_value=response) as get:
                self.assertTrue(save_cover(folder,'https://example.com/image'))
                with Image.open(folder/'cover.jpg') as result:
                    self.assertEqual(result.format,'JPEG')
                    self.assertEqual(result.size,(16,24))
                self.assertTrue(save_cover(folder,'https://example.com/image'))
                self.assertEqual(get.call_count,1)
    def test_invalid_response_nonfatal(self):
        response=MagicMock();response.__enter__.return_value=response
        response.iter_content.return_value=[b'<html>expired</html>']
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as tmp:
            folder=Path(tmp)
            with patch('cover_tools.requests.get',return_value=response):
                self.assertFalse(save_cover(folder,'https://example.com/image'))
            self.assertFalse((folder/'cover.jpg').exists())
            self.assertTrue((folder/'cover-warning.txt').exists())

    def test_local_cover_is_created_from_video_without_network(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as tmp:
            folder=Path(tmp)
            source=folder/'source.mp4'
            subprocess.run(
                [ffmpeg_path(),'-v','error','-y','-f','lavfi','-i','color=c=blue:s=160x90:d=0.2',
                 '-c:v','libx264',str(source)],check=True,capture_output=True,timeout=20,
            )
            previous=source.read_bytes()
            warning=folder/'cover-warning.txt'
            warning.write_text('No original thumbnail URL',encoding='utf-8')
            (folder/'cover.jpg').write_bytes(b'invalid previous cover')
            with patch('cover_tools.requests.get') as get:
                self.assertTrue(save_cover(folder,None,from_local_video=True))
                get.assert_not_called()
            with Image.open(folder/'cover.jpg') as result:
                self.assertEqual((result.format,result.size),('JPEG',(160,90)))
                r,g,b=result.getpixel((80,45))
                self.assertGreater(b,max(r,g)+100)
            self.assertEqual(source.read_bytes(),previous)
            self.assertFalse(warning.exists())
