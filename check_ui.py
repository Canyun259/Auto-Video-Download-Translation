"""Render the WebUI against a disposable library without starting workers."""
import shutil
import threading
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from streamlit.testing.v1 import AppTest


def check_web_ui():
    source = Path(__file__).resolve().with_name('local_ui.py')
    original_start = threading.Thread.start

    def isolated_start(thread):
        target = getattr(thread, '_target', None)
        if getattr(target, '__name__', '') not in {'poll', 'worker'}:
            original_start(thread)

    with TemporaryDirectory(prefix='video-subtitle-smoke-') as scratch:
        entrypoint = Path(scratch) / source.name
        shutil.copyfile(source, entrypoint)
        with patch.object(threading.Thread, 'start', isolated_start):
            app = AppTest.from_file(str(entrypoint)).run(timeout=60)
        if app.exception:
            raise RuntimeError('\n'.join(error.message for error in app.exception))
        assert any(s.label == '语音识别设备' for s in app.selectbox)
        assert not any(n.label == '检测间隔（秒）' for n in app.number_input)
        assert any(b.label == '手动检测' for b in app.button)
        assert any(b.label == '保存设置' for b in app.button)
    print('WebUI smoke test passed with a temporary video library.')


if __name__ == '__main__':
    check_web_ui()
