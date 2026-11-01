"""Maya不要のC++部品を、同じQt版のmayapy/PySideで統合検証する。"""
import ctypes
import faulthandler
import json
from pathlib import Path
import re
import runpy
import sys
import time


def main():
    """テスト専用DLLと製品Pythonを結び、既存スイートを実行する。"""
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / 'maya/inhouse/QuickPathExplorer/python'))
    dll = ctypes.CDLL(sys.argv[1])
    if '--embedded' in sys.argv[4:]:
        header = Path(sys.argv[1]).resolve().parents[1] / 'generated/sources.h'
        payload = header.read_text(encoding='utf-8')
        arrays = {number: bytes(int(value, 16) for value in re.findall(r'0x([a-f0-9]{2})', body)).decode('utf-8')
                  for number, body in re.findall(r'source(\d+)\[\] = \{(.*?)\};', payload, re.S)}
        sources = {name: arrays[number] for name, number in re.findall(
            r'\{"([^"]+)", reinterpret_cast<const char\*>\(source(\d+)\)\}', payload)}
        bootstrap = (root / 'maya/inhouse/QuickPathExplorer/src/plugin.cpp').read_text(encoding='utf-8')
        bootstrap = bootstrap.split('R"PY(', 1)[1].split(')PY"', 1)[0]
        exec(bootstrap, dict(_qpe_sources=sources))
        sys.path[:] = [p for p in sys.path if not p.replace('\\', '/').endswith('QuickPathExplorer/python')]
    import qpeNative
    from qpeQt import QtCore, QtWidgets, shiboken
    faulthandler.enable()
    if '--dump-abort' in sys.argv[4:]:
        dll.qpeTestAbortLog.argtypes = (ctypes.c_wchar_p,)
        dll.qpeTestAbortLog(str(Path(sys.argv[3]).with_suffix('.dmp').resolve()))

    def qtMessage(kind, context, message):
        """隔離テストでのみ、Qtの終了理由も標準エラーへ記録する。"""
        print('Qt: ' + message, file=sys.stderr, flush=True)

    QtCore.qInstallMessageHandler(qtMessage)
    dll.qpeTestCreate.argtypes = (ctypes.c_char_p, ctypes.c_size_t)
    dll.qpeTestCreate.restype = ctypes.c_size_t

    def create(kind, parent, base):
        """製品と同じQt所有権でラップする。"""
        if kind == 'icons' and '--no-icons' in sys.argv[4:]:
            return QtCore.QObject(parent)
        pointer = dll.qpeTestCreate(kind.encode('ascii'), shiboken.getCppPointer(parent)[0])
        if not pointer:
            raise RuntimeError('Native test factory rejected parent')
        return shiboken.wrapInstance(pointer, base)

    def available():
        """このテストプロセス内だけでC++部品を有効にする。"""
        return True

    qpeNative.create = create
    qpeNative.available = available
    qpeNative.prepareImageReader(dll)
    app = QtWidgets.QApplication([])
    try:
        result = runpy.run_path(sys.argv[2])['main'](sys.argv[3])
    finally:
        QtCore.QThreadPool.globalInstance().waitForDone(10000)
        # テストが保持した非表示Explorerも、QtとDLLの有効な間に破棄する。
        for widget in app.topLevelWidgets():
            if widget.objectName() == 'qpeExplorer':
                widget.close()
                widget.deleteLater()
        QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
        dll.qpeTestReleased.restype = ctypes.c_bool
        deadline = time.monotonic() + 30
        while not dll.qpeTestReleased():
            if time.monotonic() > deadline:
                raise RuntimeError('Native objects/workers did not finish')
            app.processEvents()
            time.sleep(.01)
    print(json.dumps(result, ensure_ascii=True))
    return 0 if result['status'] == 'passed' else 1


if __name__ == '__main__':
    sys.exit(main())
