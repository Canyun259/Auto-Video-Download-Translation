import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import deploy
from version import __version__

class DeploymentTests(unittest.TestCase):
    def test_config_created_once_and_never_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory)
            (base/'.env.example').write_text('KEY=example',encoding='utf-8')
            self.assertTrue(deploy.initialize_config(base))
            (base/'.env').write_text('KEY=private',encoding='utf-8')
            self.assertFalse(deploy.initialize_config(base))
            self.assertEqual((base/'.env').read_text(encoding='utf-8'),'KEY=private')
    def test_busy_service_blocks_install(self):
        with patch.object(deploy,'PYTHON') as python,patch.object(deploy.subprocess,'run') as run:
            python.exists.return_value=True;run.return_value.returncode=2
            with self.assertRaisesRegex(RuntimeError,'Stop this project'):deploy.require_stopped()
    def test_import_only_startup_needs_no_translation_config_or_ocr(self):
        import launcher
        with tempfile.TemporaryDirectory() as directory:
            ff=Path(directory)/'ffmpeg.exe';ff.touch();ff.with_name('ffprobe.exe').touch()
            def available(name):
                return None if name in {'cv2','rapidocr','onnxruntime'} else object()
            with patch('launcher.importlib.util.find_spec',side_effect=available), \
                 patch('dotenv.dotenv_values',return_value={}), \
                 patch('media_tools.ffmpeg_path',return_value=str(ff)), \
                 patch('gpu_support.cuda_status',return_value=(False,'CPU')):
                self.assertIn('基础检查通过',launcher.checks())
    def test_semantic_version(self):
        self.assertRegex(__version__,r'^\d+\.\d+\.\d+$')
    def test_bundled_ffmpeg_preferred(self):
        import media_tools
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory);tools=base/'tools'/'bin';tools.mkdir(parents=True)
            (tools/'ffmpeg.exe').touch();(tools/'ffprobe.exe').touch()
            with patch.object(media_tools,'__file__',str(base/'media_tools.py')):
                self.assertTrue(Path(media_tools.ffmpeg_path()).samefile(tools/'ffmpeg.exe'))

if __name__=='__main__': unittest.main()
