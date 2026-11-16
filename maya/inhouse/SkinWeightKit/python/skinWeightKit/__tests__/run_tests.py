"""Skin Weight Kit のテストを mayapy で実行する。

使い方::

    "C:\\Program Files\\Autodesk\\Maya2027\\bin\\mayapy.exe" maya\\inhouse\\SkinWeightKit\\python\\skinWeightKit\\__tests__\\run_tests.py

作業中の Maya GUI へは送らない(新しいシーンへ切り替えるため)。
"""

import os
import shutil
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PYTHON = os.path.dirname(os.path.dirname(HERE))
INHOUSE = os.path.dirname(os.path.dirname(PYTHON))


def main():
    """mayapy を初期化し、このフォルダの test_*.py を実行する。

    Returns:
        int: 終了コード(全部成功で0)。
    """
    for path in (PYTHON, INHOUSE):
        if path not in sys.path:
            sys.path.insert(0, path)
    temporary = _use_local_temp()
    import maya.standalone
    maya.standalone.initialize()
    try:
        suite = unittest.defaultTestLoader.discover(HERE, pattern="test_*.py", top_level_dir=PYTHON)
        result = unittest.TextTestRunner(verbosity=2).run(suite)
    finally:
        if temporary:
            shutil.rmtree(temporary, ignore_errors=True)
    return 0 if result.wasSuccessful() else 1


def _use_local_temp():
    """テストとMayaが作る一時ファイルの置き場所を、このフォルダーの ``_output`` の中にする。

    システムの一時フォルダーは別のドライブのことがあるので、テストと同じ場所へ作る。
    書き込めないときは何も変えず、システムの一時フォルダーのまま続ける。

    Returns:
        str | None: 作った一時フォルダー(終わったら消す)。作れなかったときはNone。
    """
    try:
        output = os.path.join(HERE, "_output")
        if not os.path.isdir(output):
            os.makedirs(output)
        # Mayaが終わるまでフォルダーを掴んでいて消せなかった、1日より前の残りを先に消す。
        for name in os.listdir(output):
            path = os.path.join(output, name)
            if name.startswith("temp-") and os.path.isdir(path) and os.path.getmtime(path) < time.time() - 24 * 60 * 60:
                shutil.rmtree(path, ignore_errors=True)
        temporary = tempfile.mkdtemp(prefix="temp-", dir=output)
    except OSError:
        return None
    os.environ["TEMP"] = os.environ["TMP"] = temporary
    tempfile.tempdir = temporary
    return temporary


if __name__ == "__main__":
    sys.exit(main())
