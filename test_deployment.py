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
    def test_semantic_version(self):
        self.assertRegex(__version__,r'^\d+\.\d+\.\d+$')
    def test_bundled_ffmpeg_preferred(self):
        import media_tools
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory);tools=base/'tools'/'bin';tools.mkdir(parents=True)
            (tools/'ffmpeg.exe').touch();(tools/'ffprobe.exe').touch()
            with patch.object(media_tools,'__file__',str(base/'media_tools.py')):
                self.assertEqual(media_tools.ffmpeg_path(),str(tools/'ffmpeg.exe'))

if __name__=='__main__': unittest.main()
