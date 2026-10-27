"""仕様テスト(test_spec_*.py)で共有するテストケース基底。

各 test_spec_*.py が個別に持っていた ``_NamespaceCase`` を1つにまとめたもの。
runMaya.py・unitGui.py が ``__tests__`` を sys.path に入れるので、
``from support.specCase import NamespaceCase`` で mayapy・GUI の双方から使える。
"""

import unittest
import uuid

import maya.cmds as cmds


class NamespaceCase(unittest.TestCase):
    """専用の一時名前空間でノードを作り、終了時に名前空間ごと削除し、Undo の設定・UI 単位・選択を元に戻す。

    差分は派生クラスのクラス属性で選ぶ。ファイル固有のノード作成の補助(joint の連鎖・polyCube 等)は
    各ファイルの薄い派生クラスに置く。

    Attributes:
        PREFIX (str): 名前空間の先頭。派生クラスで上書きしてテストファイルを区別できる。
        ENABLE_UNDO (bool): True なら setUp で Undo を有効にする(終了時は元の設定へ戻す)。
        CLEAR_SELECTION (bool): True なら setUp で選択を外す(終了時は元の選択へ戻す)。
        UNLOCK_NODES (bool): True なら tearDown で名前空間内のロックされたノードを解除してから削除する。
        ns (str): このテストの名前空間(setUp で作る)。
        extra_namespaces (list[str]): テスト中に作った別の名前空間。tearDown で中身ごと削除する。
    """

    PREFIX = "mlibSpec_"
    ENABLE_UNDO = True
    CLEAR_SELECTION = False
    UNLOCK_NODES = False

    def setUp(self):
        self.ns = self.PREFIX + uuid.uuid4().hex[:12]
        cmds.namespace(add=self.ns)
        self.extra_namespaces = []
        self.undo_state = cmds.undoInfo(query=True, state=True)
        if self.ENABLE_UNDO:
            cmds.undoInfo(state=True)
        self.linear_unit = cmds.currentUnit(query=True, linear=True)
        self.angle_unit = cmds.currentUnit(query=True, angle=True)
        self.selection = cmds.ls(selection=True, long=True)
        if self.CLEAR_SELECTION:
            cmds.select(clear=True)

    def tearDown(self):
        if cmds.currentUnit(query=True, linear=True) != self.linear_unit:
            cmds.currentUnit(linear=self.linear_unit)
        if cmds.currentUnit(query=True, angle=True) != self.angle_unit:
            cmds.currentUnit(angle=self.angle_unit)
        if self.UNLOCK_NODES:
            for name in cmds.ls(self.ns + ":*", long=True) or []:
                if cmds.objExists(name) and cmds.lockNode(name, query=True, lock=True)[0]:
                    cmds.lockNode(name, lock=False)
        for namespace in [self.ns] + self.extra_namespaces:
            if cmds.namespace(exists=namespace):
                cmds.namespace(removeNamespace=namespace, deleteNamespaceContent=True)
        cmds.undoInfo(state=self.undo_state)
        selection = [name for name in self.selection if cmds.objExists(name)]
        if selection:
            cmds.select(selection, replace=True)
        else:
            cmds.select(clear=True)

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

    def flushUndo(self):
        """Undo キューを空にして、以後の操作が記録する項目数を数えられるようにする。"""
        cmds.flushUndo()
        self.assertTrue(cmds.undoInfo(query=True, undoQueueEmpty=True))

    def assertUndoesInOneStep(self, check_before, check_after):
        """直前の操作が Undo 1 回で戻り、キューに他の項目を残さないことを確かめる。

        Args:
            check_before (callable): 操作前の状態を確かめる関数(Undo の後に呼ぶ)。
            check_after (callable): 操作後の状態を確かめる関数(Undo の前に呼ぶ)。
        """
        check_after()
        self.assertFalse(cmds.undoInfo(query=True, undoQueueEmpty=True))
        cmds.undo()
        check_before()
        self.assertTrue(cmds.undoInfo(query=True, undoQueueEmpty=True))

    def assertUndoEmpty(self):
        """Undo キューが空であることを確かめる(fast 経路の確認用)。"""
        self.assertTrue(cmds.undoInfo(query=True, undoQueueEmpty=True))
