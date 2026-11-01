"""Windows Shellのごみ箱へ直接移動し、同じ項目を安全に復元する。

大容量の削除に内容のコピーやハッシュを要求しない。COMは呼出元の
ワーカースレッドで初期化・解放し、Qt/MayaのUIには依存しない。
"""
import ctypes
import os
import uuid
from contextlib import contextmanager
from pathlib import Path


_P = ctypes.c_void_p
_U = ctypes.c_uint32
_H = ctypes.c_int32
_W = ctypes.c_wchar_p
_ABORT = -2147023673  # HRESULT_FROM_WIN32(ERROR_CANCELLED)
_FAIL = -2147467259
_UNKNOWN = '00000000-0000-0000-C000-000000000046'
_SINK = '04B0F1A7-9490-44BC-96E1-4296A31252E2'
_ITEM = '43826D1E-E718-42EE-BC55-A1E261C37BFE'
_OPERATION = '947AAB5F-0A5C-4C13-B4D6-4BF7836FC9F8'
_CLASS = '3AD05575-8857-4850-9277-11B85BDB8E09'


def _guid(value):
    """Windowsのバイト順でGUIDを作り、呼出中の所有権を保持する。"""
    return (ctypes.c_ubyte * 16).from_buffer_copy(uuid.UUID(value).bytes_le)


def _method(pointer, index, result, *arguments):
    """固定したCOMインターフェースのvtableをABI通りに呼ぶ。"""
    table = ctypes.cast(pointer, ctypes.POINTER(ctypes.POINTER(_P))).contents
    return ctypes.WINFUNCTYPE(result, _P, *arguments)(table[index])


def _call(pointer, index, types=(), values=()):
    """HRESULTを検証し、Shellの失敗を通常のOSErrorとして返す。"""
    code = _method(pointer, index, _H, *types)(pointer, *values)
    if code < 0:
        raise OSError('Windows file operation failed (0x{:08X})'.format(code & 0xffffffff))
    return code


def _release(pointer):
    """この呼出が取得したCOM参照だけを解放する。"""
    if pointer:
        _method(pointer, 2, _U)(pointer)


@contextmanager
def _apartment():
    """ワーカーのCOM初期化を対にし、既存ホストの初期化は解除しない。"""
    if os.name != 'nt':
        raise OSError('Recycle Bin is supported on Windows only.')
    ole = ctypes.WinDLL('ole32')
    ole.CoInitializeEx.argtypes = [_P, _U]
    ole.CoInitializeEx.restype = _H
    code = ole.CoInitializeEx(None, 2)
    if code < 0:
        # 別apartmentからの直接利用を拒否し、ホストのCOM設定は変更しない。
        raise OSError('Recycle Bin requires a COM STA worker (0x{:08X})'.format(code & 0xffffffff))
    try:
        yield
    finally:
        ole.CoUninitialize()


def _item(name):
    """通常パスまたは保存済みのShell解析名をIShellItemへ変換する。"""
    function = ctypes.WinDLL('shell32').SHCreateItemFromParsingName
    function.argtypes = [_W, _P, _P, ctypes.POINTER(_P)]
    function.restype = _H
    pointer = _P()
    code = function(str(name), None, _guid(_ITEM), ctypes.byref(pointer))
    if code < 0:
        raise FileNotFoundError('Shell item is unavailable (0x{:08X}): {}'.format(code & 0xffffffff, name))
    return pointer


def _name(pointer, kind):
    """Shellが確保した文字列をコピーし、同じallocatorで解放する。"""
    value = _P()
    _call(pointer, 5, (_U, ctypes.POINTER(_P)), (kind, ctypes.byref(value)))
    try:
        return ctypes.wstring_at(value)
    finally:
        free = ctypes.WinDLL('ole32').CoTaskMemFree
        free.argtypes = [_P]
        free(value)


def _identity(path):
    """内容を読まず、ごみ箱項目の入替えをファイルIDで検出する。"""
    info = Path(path).lstat()
    # Python 3.7のst_devは32bit、3.12以降は64bitのvolume serial。
    # NTFSの同じFile IDを、異なるMaya/Pythonからも検証できる表現にする。
    return [info.st_dev & 0xffffffff, info.st_ino]


class _ProgressSink:
    """Shellの完了通知から復元対象を取得し、完全削除への切替を拒否する。"""

    def __init__(self, cancel=None, progress=None, source=''):
        """callbackとvtableはPerformOperations終了までPython側が所有する。"""
        self.cancel, self.progress, self.source = cancel, progress, source
        self.receipt = None
        self.completed = False
        self.error = None
        self.refcount = 1
        signatures = [
            (_H, (_P, ctypes.POINTER(_P)), self._query),
            (_U, (), self._addref), (_U, (), self._release),
            (_H, (), self._check), (_H, (_H,), self._finish),
            (_H, (_U, _P, _W), self._check),
            (_H, (_U, _P, _W, _H, _P), self._check),
            (_H, (_U, _P, _P, _W), self._pre_move),
            (_H, (_U, _P, _P, _W, _H, _P), self._post_move),
            (_H, (_U, _P, _P, _W), self._check),
            (_H, (_U, _P, _P, _W, _H, _P), self._check),
            (_H, (_U, _P), self._pre_delete),
            (_H, (_U, _P, _H, _P), self._post_delete),
            (_H, (_U, _P, _W), self._check),
            (_H, (_U, _P, _W, _W, _U, _H, _P), self._check),
            (_H, (_U, _U), self._check),
            (_H, (), self._check), (_H, (), self._check), (_H, (), self._check),
        ]
        self.callbacks = [ctypes.WINFUNCTYPE(result, _P, *args)(function)
                          for result, args, function in signatures]
        self.table = (_P * len(self.callbacks))(*[ctypes.cast(c, _P) for c in self.callbacks])
        self.instance = ctypes.pointer(ctypes.cast(self.table, _P))

    def _query(self, this, iid, output):
        """IUnknownとこのsink以外のインターフェースは提供しない。"""
        output[0] = None
        if ctypes.string_at(iid, 16) not in (uuid.UUID(_UNKNOWN).bytes_le, uuid.UUID(_SINK).bytes_le):
            return -2147467262
        output[0] = ctypes.cast(self.instance, _P).value
        self.refcount += 1
        return 0

    def _addref(self, this):
        """COMの参照数を保持する。メモリの寿命は外側のPythonが管理する。"""
        self.refcount += 1
        return self.refcount

    def _release(self, this):
        """Shellの参照を減らし、callback実行中にはvtableを破棄しない。"""
        self.refcount -= 1
        return self.refcount

    def _check(self, *args):
        """例外をC ABIへ漏らさず、キャンセルをShellへ伝える。"""
        if self.cancel is not None and self.cancel.is_set():
            return _ABORT
        return 0

    def _finish(self, this, result):
        """実操作の失敗をPerformOperationsの戻り値とは別に記録する。"""
        if result < 0:
            self.error = self.error or OSError('Recycle Bin operation failed (0x{:08X})'.format(result & 0xffffffff))
        return 0

    def _pre_delete(self, this, flags, item):
        """ごみ箱不可の媒体・容量・設定では、完全削除前に中止する。"""
        if not flags & 0x80:  # TSF_DELETE_RECYCLE_IF_POSSIBLE
            self.error = OSError('This item cannot be recycled. Permanent deletion was refused.')
            return _FAIL
        try:
            if self.progress:
                self.progress('Moving to Recycle Bin: ' + self.source, 0)
        except Exception as error:
            self.error = error
            return _FAIL
        return self._check()

    def _post_delete(self, this, flags, item, result, created):
        """名前でごみ箱を検索せず、Shellが返した正確な項目を保存する。"""
        if result < 0:
            return self._finish(this, result)
        if not created:
            self.error = OSError('Windows did not return a Recycle Bin item. Check Recycle Bin before retrying.')
            return _FAIL
        try:
            physical = _name(created, 0x80058000)  # SIGDN_FILESYSPATH
            self.receipt = dict(parsingName=_name(created, 0x80028000),
                                physicalPath=physical, identity=_identity(physical))
            # ShellのMoveItemでは$Iが残ることがある。今回の削除が作った
            # 小さな管理項目だけを記録し、復元後にID照合して片付ける。
            recycled = Path(physical)
            if recycled.name.startswith('$R') and '$Recycle.Bin' in recycled.parts:
                metadata = recycled.with_name('$I' + recycled.name[2:])
                try:
                    if metadata.is_file():
                        self.receipt['metadataPath'] = str(metadata)
                        self.receipt['metadataIdentity'] = _identity(metadata)
                except OSError:
                    pass
            self.completed = True
        except Exception as error:
            self.error = error
            return _FAIL
        return 0

    def _pre_move(self, this, flags, item, destination, name):
        """復元時の衝突・上書きを直前にも拒否する。"""
        if flags & 2 or os.path.lexists(self.source):
            self.error = FileExistsError('Restore destination already exists: ' + self.source)
            return _FAIL
        return self._check()

    def _post_move(self, this, flags, item, destination, name, result, created):
        """復元成功を記録し、終了通知での中止と区別する。"""
        if result < 0:
            return self._finish(this, result)
        self.completed = bool(created)
        return 0


def _perform(source, sink, destination=None, name=None):
    """一項目だけをShellへ渡す。UI非表示・失敗即停止・完全削除禁止。"""
    pointer = _P()
    create = ctypes.WinDLL('ole32').CoCreateInstance
    create.argtypes = [_P, _P, _U, _P, ctypes.POINTER(_P)]
    create.restype = _H
    code = create(_guid(_CLASS), None, 1, _guid(_OPERATION), ctypes.byref(pointer))
    if code < 0:
        raise OSError('Windows file operation is unavailable')
    try:
        # FOFX_RECYCLEONDELETE | EARLYFAILURE | NOERRORUI | SILENT |
        # WANTNUKEWARNING。PreDeleteItemも完全削除を拒否する。
        flags = 0x80000 | 0x100000 | 0x400 | 0x4 | 0x4000 | 0x10
        if destination is not None:
            # 復元ではYes-to-allを使わず、競合時の自動上書きを許可しない。
            flags = 0x100000 | 0x400 | 0x4
        _call(pointer, 5, (_U,), (flags,))
        if destination is None:
            _call(pointer, 18, (_P, _P), (source, sink.instance))
        else:
            _call(pointer, 14, (_P, _P, _W, _P), (source, destination, name, sink.instance))
        # 完了通知がある場合は、直後のCancelで完了済み項目を失敗へ戻さない。
        result = _method(pointer, 21, _H)(pointer)
        if sink.completed:
            return
        if sink.cancel is not None and sink.cancel.is_set():
            from qpeTransactions import Cancelled
            raise Cancelled('Cancelled')
        if sink.error:
            raise sink.error
        raise OSError('Recycle Bin operation did not complete (0x{:08X})'.format(result & 0xffffffff))
    finally:
        _release(pointer)


def recycle(path, cancel=None, progress=None):
    """内容をコピーせずごみ箱へ送り、永続Undo用のShell識別情報を返す。"""
    if cancel is not None and cancel.is_set():
        from qpeTransactions import Cancelled
        raise Cancelled('Cancelled')
    with _apartment():
        source = _item(os.path.abspath(path))
        try:
            sink = _ProgressSink(cancel, progress, str(path))
            _perform(source, sink)
            return sink.receipt
        finally:
            _release(source)


def validateReceipt(receipt):
    """ごみ箱を空にした場合や項目の入替え時は復元を拒否する。"""
    if _identity(receipt['physicalPath']) != receipt['identity']:
        raise ValueError('Recycle Bin item changed; restore was refused.')


def _recycled_item(receipt):
    """ごみ箱の仮想項目を解決し、復元時にShellの削除情報も消費する。"""
    folder = _item('shell:RecycleBinFolder')
    enumerator = _P()
    try:
        _call(folder, 3, (_P, _P, _P, ctypes.POINTER(_P)),
              (None, _guid('94F60519-2850-4924-AA5A-D15E84868039'),
               _guid('70629033-E363-4A28-A567-0DB78006E6D7'), ctypes.byref(enumerator)))
        while True:
            child, fetched = _P(), _U()
            _call(enumerator, 3, (_U, ctypes.POINTER(_P), ctypes.POINTER(_U)),
                  (1, ctypes.byref(child), ctypes.byref(fetched)))
            if not fetched.value:
                break
            matched = False
            try:
                physical = _name(child, 0x80058000)
                matched = os.path.normcase(physical) == os.path.normcase(receipt['physicalPath'])
                if matched:
                    validateReceipt(receipt)
                    return child
            finally:
                if not matched:
                    _release(child)
        raise FileNotFoundError('Item is no longer in Recycle Bin.')
    finally:
        _release(enumerator)
        _release(folder)


def restore(receipt, path):
    """Shell経由で元の名前へ戻す。別媒体コピー・既存ファイル上書きをしない。"""
    validateReceipt(receipt)
    path = Path(path).absolute()
    if os.path.lexists(str(path)):
        raise FileExistsError('Restore destination already exists: ' + str(path))
    if not path.parent.is_dir():
        raise FileNotFoundError('Restore parent folder is missing: ' + str(path.parent))
    if _identity(path.parent)[0] != receipt['identity'][0]:
        raise ValueError('Restore destination volume changed; restore was refused.')
    with _apartment():
        source, destination = _recycled_item(receipt), None
        try:
            # 解析名の再解決先が記録したごみ箱項目と同じことを確認する。
            if _identity(_name(source, 0x80058000)) != receipt['identity']:
                raise ValueError('Recycle Bin identity changed')
            destination = _item(path.parent)
            _perform(source, _ProgressSink(source=str(path)), destination, path.name)
            metadata = receipt.get('metadataPath')
            physical = Path(receipt['physicalPath'])
            expected_metadata = physical.with_name('$I' + physical.name[2:])
            # 復元済みの原本には触れず、この操作のごみ箱管理項目だけを対象にする。
            if (metadata and Path(metadata) == expected_metadata and physical.name.startswith('$R')
                    and '$Recycle.Bin' in physical.parts and not physical.exists() and path.exists()):
                try:
                    if _identity(metadata) == receipt.get('metadataIdentity'):
                        Path(metadata).unlink()
                except OSError:
                    # 管理項目の掃除失敗を、成功した復元の失敗として再試行させない。
                    pass
        finally:
            _release(destination)
            _release(source)
