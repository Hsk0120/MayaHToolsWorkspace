"""MultiPlug.getNextAvailable(start, asPlug, checkLocked, checkChildren, *, vacant=False) の約束を固定する。

3 つの探索規則(``getNextAvailable()`` = 最後の接続要素の次から入力・ロック・子の入力を避ける、
``getNextAvailable(vacant=True)`` = 既存番号に無い最初の番号、``appendMessage`` = 最大番号+1)の違いと、
``connect(nextAvailable=True)``(0 から探す)との差、フラグの組合せ、不正入力の例外型、
旧 ``getNextAvailableIndex`` が無いことを確かめる。期待値は maya.cmds(``getAttr multiIndices``・
``listConnections``)で独立に求める。
"""

import unittest
import uuid

import maya.cmds as cmds
import mlib
from mlib import plugs


class _MultiSpecCase(unittest.TestCase):
    """専用の名前空間とマルチアトリビュート付きのnetworkノードを用意し、終了時に削除する。"""

    def setUp(self):
        self.namespace = ":specPlugMulti_" + uuid.uuid4().hex
        self.before = set(cmds.ls(long=True) or [])
        cmds.namespace(add=self.namespace)
        self.undo_state = cmds.undoInfo(query=True, state=True)
        cmds.undoInfo(state=True)
        self.net = self.make("network")
        # Plug.getFullName() とcmdsの照会はノードの一意名なので同じ形で比べる。
        self.name = self.net.getName()
        cmds.addAttr(self.name, longName="vals", attributeType="double", multi=True)
        cmds.addAttr(self.name, longName="msgs", attributeType="message", multi=True)
        cmds.addAttr(self.name, longName="pairs", attributeType="compound", numberOfChildren=2, multi=True)
        cmds.addAttr(self.name, longName="px", attributeType="double", parent="pairs")
        cmds.addAttr(self.name, longName="py", attributeType="double", parent="pairs")
        self.values = self.net.getPlug("vals")
        self.src = self.make("transform")
        self.sn = self.src.getName()
        cmds.flushUndo()

    def tearDown(self):
        for name in sorted(set(cmds.ls(long=True) or []) - self.before, key=len, reverse=True):
            if cmds.objExists(name):
                try:
                    cmds.lockNode(name, lock=False)
                    cmds.delete(name)
                except RuntimeError:
                    pass  # Mayaが自動で作る削除できないノードは残す。
        if cmds.namespace(exists=self.namespace):
            cmds.namespace(removeNamespace=self.namespace, deleteNamespaceContent=True)
        cmds.undoInfo(state=self.undo_state)

    def make(self, kind="network"):
        """Mayaコマンドで作成したノードを取得する。"""
        return mlib.getNode(cmds.createNode(kind, name=self.namespace + ":n#", skipSelect=True))

    def existing(self, attr="vals"):
        """cmdsで既存要素の論理番号を取得する。"""
        return sorted(cmds.getAttr(self.name + "." + attr, multiIndices=True) or [])

    def connect(self, src_attr, index, attr="vals"):
        """cmdsで要素へ入力接続する。"""
        cmds.connectAttr(self.sn + "." + src_attr, "{}.{}[{}]".format(self.name, attr, index))

    def assertVacant(self, index, attr="vals"):
        """vacantの結果が「既存番号に無く、それより小さい番号はすべて既存」であることを確かめる。"""
        existing = self.existing(attr)
        self.assertNotIn(index, existing)
        self.assertTrue(all(i in existing for i in range(index)))


class DefaultSearchSpecTest(_MultiSpecCase):
    """既定(vacant=False): 最後の接続要素の次から、入力接続・ロック・子の入力を避ける。"""

    def test_empty_multi(self):
        """空のマルチアトリビュートは0。vacantも0。appendMessageは0。"""
        self.assertEqual(self.values.getNextAvailable(), 0)
        self.assertEqual(self.values.getNextAvailable(vacant=True), 0)
        self.assertEqual(self.values.getNextAvailable(start=5), 5)
        self.assertEqual(self.values.getNextAvailable(5, vacant=True), 5)
        self.assertEqual(self.existing(), [])

    def test_values_do_not_block_default_search(self):
        """値を持つだけの要素は既定では候補になり、vacantでは避ける。"""
        cmds.setAttr(self.name + ".vals[0]", 1.0)
        cmds.setAttr(self.name + ".vals[2]", 2.0)
        self.assertEqual(self.existing(), [0, 2])
        self.assertEqual(self.values.getNextAvailable(), 0)
        self.assertEqual(self.values.getNextAvailable(start=2), 2)
        self.assertEqual(self.values.getNextAvailable(vacant=True), 1)
        self.assertVacant(self.values.getNextAvailable(vacant=True))
        self.assertEqual(self.values.getNextAvailable(start=2, vacant=True), 3)
        self.assertEqual(self.values.getNextAvailable(start=1, vacant=True), 1)

    def test_starts_after_last_connected_and_skips_gaps(self):
        """start<0は最後の接続要素の次から。途中の空き(2〜4)は飛ばす。start指定は途中の空きも返す。"""
        self.connect("tx", 1)
        self.connect("ty", 5)
        self.assertEqual(self.values.getNextAvailable(), 6)
        self.assertEqual(self.values.getNextAvailable(-1), 6)
        self.assertEqual(self.values.getNextAvailable(start=-7), 6)
        self.assertEqual(self.values.getNextAvailable(start=0), 0)
        self.assertEqual(self.values.getNextAvailable(start=1), 2)
        self.assertEqual(self.values.getNextAvailable(start=5), 6)
        self.assertEqual(self.values.getNextAvailable(vacant=True), 0)
        self.assertEqual(self.values.getNextAvailable(start=1, vacant=True), 2)
        self.assertEqual(self.existing(), [1, 5])
        # 接続先として実際に使える番号であることをcmdsで確かめる。
        index = self.values.getNextAvailable()
        cmds.connectAttr(self.sn + ".tz", "{}.vals[{}]".format(self.name, index))
        self.assertEqual(self.values.getNextAvailable(), 7)

    def test_output_connections_do_not_block(self):
        """出力接続だけの要素は入力できるので候補になる。既定の開始位置はnumConnectedElementsに基づく。"""
        cmds.setAttr(self.name + ".vals[3]", 1.0)
        cmds.connectAttr(self.name + ".vals[3]", self.sn + ".tx")
        self.assertEqual(self.values.getNextAvailable(start=3), 3)
        self.assertEqual(self.values.getNextAvailable(), 4)
        self.assertEqual(self.values.getNextAvailable(start=3, vacant=True), 4)

    def test_check_locked(self):
        """checkLocked=Trueはロックされた要素を避け、Falseは避けない。vacantは既存番号で判断する。"""
        self.connect("tx", 0)
        cmds.setAttr(self.name + ".vals[1]", lock=True)
        self.assertEqual(self.values.getNextAvailable(), 2)
        self.assertEqual(self.values.getNextAvailable(checkLocked=False), 1)
        self.assertEqual(self.values.getNextAvailable(start=1), 2)
        self.assertEqual(self.values.getNextAvailable(start=1, checkLocked=False), 1)
        self.assertEqual(self.values.getNextAvailable(vacant=True), len(self.existing()))
        self.assertVacant(self.values.getNextAvailable(vacant=True))
        self.assertEqual(self.values.getNextAvailable(vacant=True, checkLocked=False),
                         self.values.getNextAvailable(vacant=True))

    def test_locked_multi(self):
        """マルチアトリビュート全体のロックは既定でRuntimeError。checkLocked=Falseとvacant=Trueは例外にしない。"""
        cmds.setAttr(self.name + ".vals", lock=True)
        with self.assertRaises(RuntimeError):
            self.values.getNextAvailable()
        with self.assertRaises(RuntimeError):
            self.values.getNextAvailable(start=3)
        self.assertEqual(self.values.getNextAvailable(checkLocked=False), 0)
        self.assertEqual(self.values.getNextAvailable(vacant=True), 0)
        self.assertEqual(self.values.getNextAvailable(vacant=True, checkLocked=True), 0)

    def test_check_children(self):
        """checkChildren=Trueはコンパウンドアトリビュートである要素の子の入力・ロックも避け、Falseは要素自身だけを見る。"""
        pairs = self.net.getPlug("pairs")
        cmds.connectAttr(self.sn + ".tx", self.name + ".pairs[0].px")
        cmds.setAttr(self.name + ".pairs[1].py", lock=True)
        self.assertEqual(pairs.getNextAvailable(start=0), 2)
        self.assertEqual(pairs.getNextAvailable(start=0, checkChildren=False), 0)
        self.assertEqual(pairs.getNextAvailable(start=0, checkLocked=False), 1)
        self.assertEqual(pairs.getNextAvailable(start=0, checkLocked=False, checkChildren=False), 0)
        self.assertEqual(pairs.getNextAvailable(vacant=True), len(self.existing("pairs")))
        self.assertVacant(pairs.getNextAvailable(vacant=True), "pairs")

    def test_as_plug(self):
        """asPlug=Trueは番号ではなく要素Plugを返す。要素は作成されない。"""
        self.connect("tx", 0)
        for vacant in (False, True):
            with self.subTest(vacant=vacant):
                index = self.values.getNextAvailable(vacant=vacant)
                plug = self.values.getNextAvailable(asPlug=True, vacant=vacant)
                self.assertIsInstance(plug, plugs.Plug)
                self.assertNotIsInstance(plug, plugs.MultiPlug)
                self.assertEqual(plug.getIndex(), index)
                self.assertEqual(plug.getMulti().getFullName(), self.values.getFullName())
                self.assertEqual(plug.getFullName(), "{}.vals[{}]".format(self.name, index))
        self.assertEqual(self.existing(), [0])


class ComparisonSpecTest(_MultiSpecCase):
    """appendMessage・connect(nextAvailable=True)との探索規則の対比。"""

    def test_append_message_uses_max_plus_one(self):
        """appendMessageは最大番号+1(穴を再利用しない)。getNextAvailable()は最後の接続の次、vacantは0から。"""
        msgs = self.net.getPlug("msgs")
        other = self.make("transform")
        cmds.connectAttr(self.sn + ".message", self.name + ".msgs[4]")
        self.assertEqual(msgs.getNextAvailable(), 5)
        self.assertEqual(msgs.getNextAvailable(vacant=True), 0)
        self.assertEqual(msgs.getNextAvailable(start=0), 0)
        index = msgs.appendMessage(other)
        self.assertEqual(index, 5)
        self.assertEqual(cmds.listConnections(self.name + ".msgs[5]", plugs=True), [other.getName() + ".message"])
        cmds.disconnectAttr(self.sn + ".message", self.name + ".msgs[4]")
        cmds.removeMultiInstance(self.name + ".msgs[4]", b=True)
        self.assertEqual(self.existing("msgs"), [5])
        self.assertEqual(msgs.appendMessage(self.src), 6)
        self.assertEqual(msgs.getNextAvailable(start=0), 0)
        self.assertEqual(msgs.getNextAvailable(vacant=True), 0)
        self.assertEqual(msgs.getNextAvailable(), 7)

    def test_connect_next_available_starts_at_zero(self):
        """connect(nextAvailable=True)は0から探すので、getNextAvailable()(最後の接続の次)と選ぶ要素が違う。"""
        self.connect("tx", 3)
        self.assertEqual(self.values.getNextAvailable(), 4)
        expected = self.values.getNextAvailable(start=0)
        target = self.values.connect(self.src.getPlug("ty"), nextAvailable=True)
        self.assertEqual(target.getIndex(), 0)
        self.assertEqual(target.getIndex(), expected)
        self.assertEqual(self.values.getNextAvailable(start=0), 1)
        self.assertEqual(self.values.getNextAvailable(), 4)
        self.assertEqual(self.values.getNextAvailable(vacant=True), 1)

    def test_vacant_matches_cmds_multi_indices(self):
        """vacantの結果はcmds.getAttr(multiIndices)に無く、それより小さい番号は全て既存。"""
        for index in (0, 1, 2, 5, 8):
            cmds.setAttr("{}.vals[{}]".format(self.name, index), float(index))
        self.connect("tx", 3)
        self.assertEqual(self.existing(), [0, 1, 2, 3, 5, 8])
        self.assertEqual(self.values.getNextAvailable(vacant=True), 4)
        self.assertVacant(self.values.getNextAvailable(vacant=True))
        for start, expected in ((0, 4), (4, 4), (5, 6), (8, 9), (20, 20)):
            with self.subTest(start=start):
                self.assertEqual(self.values.getNextAvailable(start=start, vacant=True), expected)
                self.assertNotIn(expected, self.existing())


class ArgumentSpecTest(_MultiSpecCase):
    """不正入力・上限・旧名。"""

    def test_type_errors(self):
        """startはbool以外の整数、asPlug/checkLocked/checkChildren/vacantはbool限定。"""
        for start in (True, "0", 1.5, None):
            with self.subTest(start=repr(start)):
                with self.assertRaises(TypeError):
                    self.values.getNextAvailable(start)
        for flag in ("asPlug", "checkLocked", "checkChildren", "vacant"):
            with self.subTest(flag=flag):
                with self.assertRaises(TypeError):
                    self.values.getNextAvailable(**{flag: 1})
        with self.assertRaises(TypeError):
            self.values.getNextAvailable(0, False, True, True, True)

    def test_index_limit(self):
        """上限(2147483647)を超えるstartはIndexError。上限そのものは返せる。"""
        limit = 2147483647
        self.assertEqual(self.values.getNextAvailable(start=limit), limit)
        self.assertEqual(self.values.getNextAvailable(start=limit, vacant=True), limit)
        for vacant in (False, True):
            with self.subTest(vacant=vacant):
                with self.assertRaises(IndexError):
                    self.values.getNextAvailable(start=limit + 1, vacant=vacant)
        self.assertEqual(self.existing(), [])

    def test_invalid_plug(self):
        """削除済みのアトリビュートはRuntimeError。"""
        cmds.deleteAttr(self.name, attribute="vals")
        with self.assertRaises(RuntimeError):
            self.values.getNextAvailable()
        with self.assertRaises(RuntimeError):
            self.values.getNextAvailable(vacant=True)

    def test_old_name_is_removed(self):
        """getNextAvailableIndexは無い。非マルチアトリビュートのPlugにgetNextAvailableは無い。"""
        self.assertFalse(hasattr(self.values, "getNextAvailableIndex"))
        self.assertFalse(hasattr(plugs.MultiPlug, "getNextAvailableIndex"))
        with self.assertRaises(AttributeError):
            self.values.getNextAvailableIndex()
        with self.assertRaises(AttributeError):
            self.values[0].getNextAvailable()
        with self.assertRaises(AttributeError):
            self.src.getPlug("tx").getNextAvailable()

    def test_does_not_record_undo_or_create_elements(self):
        """探索は読み取りで、Undoに記録せず要素も作らない。"""
        self.connect("tx", 2)
        cmds.flushUndo()
        self.values.getNextAvailable()
        self.values.getNextAvailable(start=10, asPlug=True)
        self.values.getNextAvailable(vacant=True)
        self.assertTrue(cmds.undoInfo(query=True, undoQueueEmpty=True))
        self.assertEqual(self.existing(), [2])


if __name__ == "__main__":
    unittest.main()
