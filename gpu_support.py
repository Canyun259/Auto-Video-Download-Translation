"""Select the speech device without claiming GPU use when DLLs are missing."""
import os
import sysconfig
from pathlib import Path
import threading
_DLL_HANDLES = []
_DLL_LOCK = threading.Lock()
_DLL_READY = False

def prepare_cuda():
    global _DLL_READY
    if os.name != 'nt':
        return
    with _DLL_LOCK:
        if _DLL_READY:
            return
        root = Path(sysconfig.get_paths()['purelib']) / 'nvidia'
        directories = sorted({p.parent for p in root.rglob('*.dll')}) if root.exists() else []
        for directory in directories:
            _DLL_HANDLES.append(os.add_dll_directory(str(directory)))
        os.environ['PATH'] = os.pathsep.join(map(str, directories)) + os.pathsep + os.environ.get('PATH', '')
        _DLL_READY = True

def cuda_status():
    try:
        prepare_cuda()
        import ctranslate2
        if ctranslate2.get_cuda_device_count() < 1:
            return False, '未检测到 CUDA 显卡'
        if os.name == 'nt':
            import ctypes
            for library in ('cublas64_12.dll', 'cudnn64_9.dll'):
                try:
                    ctypes.WinDLL(library)
                except OSError:
                    return False, '缺少或无法加载 ' + library
        return True, 'CUDA 基础检查通过；实际推理仍需测试'
    except Exception as exc:
        return False, 'CUDA 检查失败：' + type(exc).__name__

def speech_device(mode):
    if mode == 'cpu':
        return 'cpu', 'int8'
    ready, reason = cuda_status()
    if ready:
        return 'cuda', 'int8_float16'
    if mode == 'cuda':
        raise RuntimeError(reason)
    return 'cpu', 'int8'

