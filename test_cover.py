import tempfile,unittest
from pathlib import Path
from io import BytesIO
from unittest.mock import patch,MagicMock
from PIL import Image
from cover_tools import save_cover

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
