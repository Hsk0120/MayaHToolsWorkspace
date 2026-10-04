"""接続のforceと一時アンロックを別々に指定できることを検証する。"""

import unittest

import maya.cmds as cmds

from hlib.nodes import Node


class ConnectionLockTest(unittest.TestCase):
    """既定の挙動とMaya標準互換のロック保持を確認する。"""

    def test_force_without_unlock(self):
        """unlock=Falseは既存入力とロックを保持して失敗する。"""
        nodes = [Node.create("multiplyDivide") for _ in range(3)]
        original, replacement, target = nodes
        output = original.plug("outputX")
        destination = target.plug("input1X")
        try:
            output.connect(destination)
            destination.setFlags(locked=True)
            with self.assertRaises(RuntimeError):
                replacement.plug("outputX").connect(destination, force=True, unlock=False)
            self.assertEqual(destination.source(), output)
            self.assertTrue(destination.isLocked())
            # 既定値は従来どおり一時解除して接続し、ロックを戻す。
            replacement.plug("outputX").connect(destination, force=True)
            self.assertEqual(destination.source(), replacement.plug("outputX"))
            self.assertTrue(destination.isLocked())
            cmds.undo()
            self.assertEqual(destination.source(), output)
            self.assertTrue(destination.isLocked())
        finally:
            cmds.delete([node.fullName() for node in nodes if node.isValid()])


if __name__ == "__main__":
    unittest.main()
