import ast,threading,time,unittest
from pathlib import Path
from unittest.mock import Mock,patch
from urllib.parse import urlparse

class ManualScanTests(unittest.TestCase):
    def setUp(self):
        tree=ast.parse((Path(__file__).resolve().parents[1] / 'local_ui.py').read_text(encoding='utf-8'))
        cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Runtime')
        self.discover=Mock()
        self.ns={'threading':threading,'time':time,'urlparse':urlparse,'discover':self.discover,
                 'settings':lambda:{'sources':['https://www.youtube.com/@a/videos','https://www.youtube.com/@b/videos'],'limit':20}}
        exec(compile(ast.Module(body=[cls],type_ignores=[]),'local_ui.py','exec'),self.ns)
        self.rt=self.ns['Runtime'].__new__(self.ns['Runtime'])
        self.rt.errors=[];self.rt.scan=threading.Event();self.rt.scan_lock=threading.Lock()
        self.rt.scan_requested_at=None;self.rt.scan_status={'state':'idle'}

    def test_startup_waits_indefinitely_without_scanning(self):
        with patch.object(self.rt.scan,'wait',side_effect=StopIteration) as wait:
            with self.assertRaises(StopIteration): self.rt.poll()
            wait.assert_called_once_with()
        self.discover.assert_not_called()

    def test_one_click_one_scan_shared_timestamp_and_no_timer(self):
        with patch('time.time',return_value=1234): self.assertTrue(self.rt.request_scan())
        self.assertFalse(self.rt.request_scan())
        def during_scan(*args): self.assertFalse(self.rt.request_scan())
        self.discover.side_effect=during_scan
        with patch.object(self.rt.scan,'wait',side_effect=[True,StopIteration]) as wait:
            with self.assertRaises(StopIteration): self.rt.poll()
            self.assertEqual(wait.call_args_list, [unittest.mock.call(),unittest.mock.call()])
        self.assertEqual(self.discover.call_count,2)
        self.assertTrue(all(c.args[2]==1234 for c in self.discover.call_args_list))
        self.assertFalse(self.rt.scan.is_set())
        self.assertEqual(self.rt.scan_status['state'],'done')
        self.assertTrue(self.rt.request_scan())

    def test_source_failure_does_not_prevent_other_sources(self):
        self.discover.side_effect=[RuntimeError('network failed'),None]
        self.rt.run_scan(1234)
        self.assertEqual(self.discover.call_count,2)
        self.assertEqual(self.rt.scan_status['failures'],1)

    def test_settings_failure_allows_another_manual_attempt(self):
        self.ns['settings']=Mock(side_effect=RuntimeError('bad settings'))
        self.rt.request_scan()
        with patch.object(self.rt.scan,'wait',side_effect=[True,StopIteration]):
            with self.assertRaises(StopIteration): self.rt.poll()
        self.assertEqual(self.rt.scan_status['state'],'error')
        self.assertTrue(self.rt.request_scan())

if __name__=='__main__':unittest.main()
