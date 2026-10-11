"""追加依存なしでWindowsプロセスのワーキングセットを読む。"""
import ctypes
from ctypes import wintypes


class Counters(ctypes.Structure):
    """WindowsのPROCESS_MEMORY_COUNTERS_EXと同じメモリ配置。"""
    _fields_ = [('cb', wintypes.DWORD), ('PageFaultCount', wintypes.DWORD)] + [
        (name, ctypes.c_size_t) for name in ('PeakWorkingSetSize', 'WorkingSetSize',
        'QuotaPeakPagedPoolUsage', 'QuotaPagedPoolUsage', 'QuotaPeakNonPagedPoolUsage',
        'QuotaNonPagedPoolUsage', 'PagefileUsage', 'PeakPagefileUsage', 'PrivateUsage')]


def memory(handle):
    """有効なWindowsプロセスハンドルからメモリを取得する。

    Args:
        handle (int): 呼出元が所有するプロセスハンドル。

    Returns:
        dict: MiB単位の現在・ピークワーキングセット、プライベート使用量。
    """
    counters = Counters()
    counters.cb = ctypes.sizeof(counters)
    function = ctypes.windll.psapi.GetProcessMemoryInfo
    function.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
    function.restype = wintypes.BOOL
    if not function(handle, ctypes.byref(counters), counters.cb):
        raise ctypes.WinError()
    return dict(working_set_mib=counters.WorkingSetSize / 1048576,
                peak_working_set_mib=counters.PeakWorkingSetSize / 1048576,
                private_mib=counters.PrivateUsage / 1048576)
