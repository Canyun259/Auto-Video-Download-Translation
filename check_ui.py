"""Render the real Streamlit entrypoint without starting background downloads."""
import threading
from pathlib import Path
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
original_start=threading.Thread.start

def isolated_start(thread):
    target=getattr(thread,'_target',None)
    if getattr(target,'__name__','') in {'poll','worker'}:
        return
    return original_start(thread)

with patch.object(threading.Thread,'start',isolated_start):
    app=AppTest.from_file(str(Path(__file__).resolve().parent/'local_ui.py')).run(timeout=60)
    if app.exception:
        for error in app.exception:
            print(error.message)
        raise SystemExit(1)
    labels=[s.label for s in app.selectbox]
    assert '语音识别设备' in labels, labels
    print('WebUI rendered successfully; GPU device selector present.')
