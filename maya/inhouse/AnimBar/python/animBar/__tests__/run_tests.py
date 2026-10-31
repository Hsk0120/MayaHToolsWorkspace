"""Anim Bar のテストを mayapy で実行する。

使い方::

    "C:\\Program Files\\Autodesk\\Maya2027\\bin\\mayapy.exe" maya\\inhouse\\AnimBar\\python\\animBar\\__tests__\\run_tests.py

作業中の Maya GUI へは送らない(新しいシーンへ切り替えるため)。
"""

import os
import sys
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
    import maya.standalone
    maya.standalone.initialize()
    suite = unittest.defaultTestLoader.discover(HERE, pattern="test_*.py", top_level_dir=PYTHON)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
