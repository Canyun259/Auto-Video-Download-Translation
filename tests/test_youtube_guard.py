import json,tempfile,unittest
from pathlib import Path
from unittest.mock import MagicMock,patch
from youtube_guard import download_session,extract_video,remaining,YouTubeCooldown

class GuardTests(unittest.TestCase):
    def test_shared_cooldown_blocks_without_network_and_expires(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'cooldown.json'
            options={'_youtube_guard_path':str(path)}
            factory=MagicMock()
            with patch('youtube_guard.time.time',return_value=1000):
                with self.assertRaises(YouTubeCooldown):
                    with download_session('https://youtu.be/a',options,factory):
                        raise RuntimeError('Video unavailable. The current session has been rate-limited by YouTube')
                self.assertEqual(remaining(path),3600)
                before=path.read_bytes();factory.reset_mock()
                with self.assertRaises(YouTubeCooldown):
                    with download_session('https://www.youtube.com/@other/videos',options,factory):pass
                factory.assert_not_called();self.assertEqual(path.read_bytes(),before)
                with download_session('https://www.instagram.com/p/a/',options,factory):pass
                self.assertNotIn('_youtube_guard_path',factory.call_args.args[0])
            with patch('youtube_guard.time.time',return_value=4601):
                factory.reset_mock()
                with download_session('https://youtu.be/a',options,factory):pass
                self.assertEqual(factory.call_args.args[0]['sleep_interval_requests'],.75)
                self.assertEqual(factory.call_args.args[0]['sleep_interval'],10)

    def test_unavailable_without_rate_limit_is_not_cooldown(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'cooldown.json'
            with self.assertRaisesRegex(RuntimeError,'removed'):
                with download_session('https://youtu.be/a',{'_youtube_guard_path':str(path)},MagicMock()):
                    raise RuntimeError('Video removed')
            self.assertFalse(path.exists())


    def test_tls_eof_retries_once_with_the_same_download_options(self):
        factory=MagicMock()
        extract=factory.return_value.__enter__.return_value.extract_info
        interrupted=RuntimeError('SSL: UNEXPECTED_EOF_WHILE_READING')
        extract.side_effect=[interrupted, {'id':'test'}]
        url='https://youtu.be/test'
        with patch('youtube_guard.time.sleep') as delay:
            self.assertEqual(extract_video(url, {'continuedl':True}, download=True, factory=factory),
                             {'id':'test'})
        self.assertEqual(extract.call_count,2)
        self.assertTrue(all(call.args[0]['continuedl'] for call in factory.call_args_list))
        delay.assert_called_once_with(2)
        extract.reset_mock()
        extract.side_effect=[interrupted,interrupted]
        with patch('youtube_guard.time.sleep'), self.assertRaisesRegex(ConnectionError,'SSL EOF'):
            extract_video(url, {}, download=True, factory=factory)
        self.assertEqual(extract.call_count,2)

    def test_rate_limit_is_not_retried(self):
        factory=MagicMock()
        factory.return_value.__enter__.return_value.extract_info.side_effect=RuntimeError('HTTP Error 429')
        with tempfile.TemporaryDirectory() as directory, patch('youtube_guard.time.sleep') as delay:
            cooldown=Path(directory)/'cooldown.json'
            with self.assertRaises(YouTubeCooldown):
                extract_video('https://youtu.be/test', {'_youtube_guard_path':cooldown},
                              download=True, factory=factory)
            self.assertGreater(remaining(cooldown),0)
        factory.assert_called_once()
        delay.assert_not_called()

if __name__=='__main__':unittest.main()
