"""仕様テスト(test_spec_*.py)で共有するテストケース基底。

各 test_spec_*.py が個別に持っていた ``_NamespaceCase`` を1つにまとめる。
runMaya.py・unitGui.py が ``__tests__`` を sys.path に入れるので、
``from support.specCase import NamespaceCase`` で mayapy・GUI の双方から使える。
"""

import unittest
import uuid

import maya.cmds as cmds


class NamespaceCase(unittest.TestCase):
    """専用の一時名前空間でノードを作り、終了時に名前空間ごと削除し、Undo の設定を元に戻す。

    Attributes:
        PREFIX (str): 名前空間の先頭。派生クラスで上書きしてテストファイルを区別できる。
        ns (str): このテストの名前空間(setUp で作る)。
    """

    PREFIX = "mlibSpec_"

    def setUp(self):
        self.ns = self.PREFIX + uuid.uuid4().hex[:12]
        cmds.namespace(add=self.ns)
        self.undo_state = cmds.undoInfo(query=True, state=True)
        cmds.undoInfo(state=True)

    def tearDown(self):
        if cmds.namespace(exists=self.ns):
            cmds.namespace(removeNamespace=self.ns, deleteNamespaceContent=True)
        cmds.undoInfo(state=self.undo_state)

    def name(self, text):
        """名前空間付きの名前を返す。

        Args:
            text (str): 名前空間を除いた名前。

        Returns:
            str: ``<名前空間>:<text>``。
        """
        return self.ns + ":" + text

    def make(self, kind="transform", text="node#", parent=None):
        """cmds.createNode でこの名前空間にノードを作り、できた名前を返す。

        Args:
            kind (str): Maya の nodeType 名。
            text (str): 名前(``#`` は連番)。
            parent (str | None): 親の名前。

        Returns:
            str: 作成されたノードの名前。
        """
        flags = {"name": self.name(text), "skipSelect": True}
        if parent is not None:
            flags["parent"] = parent
        return cmds.createNode(kind, **flags)

    def assertSequenceAlmostEqual(self, actual, expected, places=9):
        """同じ長さで、各要素がほぼ等しいことを確かめる。"""
        actual, expected = list(actual), list(expected)
        self.assertEqual(len(actual), len(expected))
        for a, e in zip(actual, expected):
            self.assertAlmostEqual(a, e, places=places)

    def assertSameRotation(self, actual, expected):
        """クォータニオンは q と -q が同じ回転なので、符号をそろえて比べる。"""
        actual, expected = list(actual), list(expected)
        if sum(a * e for a, e in zip(actual, expected)) < 0:
            expected = [-value for value in expected]
        self.assertSequenceAlmostEqual(actual, expected)

    def assertUndoEmpty(self):
        """Undo キューが空であることを確かめる(fast 経路の確認用)。"""
        self.assertTrue(cmds.undoInfo(query=True, undoQueueEmpty=True))
