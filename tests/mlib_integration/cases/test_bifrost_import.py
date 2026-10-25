"""Bifrost拡張の先行importとmlibの再読み込みを検証する。"""
import os
from pathlib import Path
import sys
import subprocess
import unittest

def mayapy_executable():
    """子プロセス用の mayapy を返す。

    Maya GUI 内では ``sys.executable`` が maya.exe になり、``-c`` を渡すと新しい GUI が起動してしまうため、
    同じフォルダーの mayapy を使う。見つからなければテストを skip する。

    Returns:
        str: mayapy のパス。
    """
    executable = Path(sys.executable)
    if executable.stem.lower() == "mayapy":
        return str(executable)
    candidate = executable.with_name("mayapy.exe" if os.name == "nt" else "mayapy")
    if not candidate.is_file():
        raise unittest.SkipTest("mayapy が見つからない: {}".format(candidate))
    return str(candidate)

class BifrostImportTest(unittest.TestCase):
    def test_bifrost_first_import_in_fresh_process(self):
        """先行importを軽い宣言だけで完了し、後から正常に検出する。"""
        script = '''
import sys
import mlib_bifrost
assert "mlib" not in sys.modules
import maya.standalone
maya.standalone.initialize(name="python")
import mlib
state = mlib.core.extensions.status()["mlib_bifrost"]["state"]
assert state in ("loaded", "unavailable"), state
assert mlib_bifrost.nodes.Graph is not None
old = mlib_bifrost
mlib.reload()
import mlib_bifrost
assert mlib_bifrost is not old
maya.standalone.uninitialize()
'''
        result = subprocess.run([mayapy_executable(), '-c', script],
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                timeout=120)
        self.assertEqual(result.returncode, 0, result.stdout.decode(errors='replace'))

if __name__ == "__main__":
    unittest.main()
