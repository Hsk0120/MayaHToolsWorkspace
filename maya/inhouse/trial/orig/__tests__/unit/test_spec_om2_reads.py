"""2.1.0 で om2 へ置き換えた読取りと、Plug.setMuted の fast の約束(仕様)を固定する(担当C)。

対象: Plug.isSettable(isFreeToChange の比較)、Node.resetAttrs の省略時の絞込み(通常/fastで同じ選択)、
Node.getHistory(Transform は直下のShapeの履歴)、Node.getPlugs(om2 で扱うフラグと cmds へ渡すフラグ)、
IkHandle.getJoints、Plug.setMuted(fast=True)(cmds を呼ばない・Undoに記録しない・通常経路と同じ結果・
再現できない条件は変更前に NotImplementedError)と通常経路の Undo 1 回。

cmds の生の値との突き合わせは ``integration/test_cmds_parity.py`` が担当し、ここでは重ねない。
"""

import sys
import unittest
import uuid
from unittest.mock import patch

import maya.cmds as cmds

import mlib
mlib.reload()
from mlib.nodes import Joint
from support.specCase import NamespaceCase


class PlugIsSettableSpecTest(NamespaceCase):
    """isSettable はロック・入力接続を親子とも反映し、定義の writable は見ない。"""

    def test_locks_connections_and_outputs(self):
        node = self.make()
        driver = self.make()
        cmds.setAttr(node + ".tx", lock=True)
        cmds.connectAttr(driver + ".ry", node + ".ry")
        plug = mlib.getPlug
        cases = (("tx", False), ("ty", True), ("translate", False), ("ry", False), ("rotate", False),
                 ("worldMatrix", True), ("message", True))
        for attribute, expected in cases:
            with self.subTest(attribute=attribute):
                result = plug(node + "." + attribute).isSettable()
                self.assertIs(result, expected)
        cmds.setAttr(node + ".scale", lock=True)
        self.assertFalse(plug(node + ".sx").isSettable())

    def test_invalid_plug_raises(self):
        node = self.make()
        target = mlib.getPlug(node + ".tx")
        cmds.delete(node)
        with self.assertRaises(RuntimeError):
            target.isSettable()


class NodeResetAttrsSpecTest(NamespaceCase):
    """省略時の絞込みは通常/fastで同じで、配列・ロック・入力接続を除く。"""

    def setUp(self):
        super().setUp()
        self.node = self.make("multiplyDivide", "reset#")
        driver = self.make()
        cmds.setAttr(self.node + ".input1X", 3)
        cmds.setAttr(self.node + ".input1Z", 4)
        cmds.setAttr(self.node + ".input2X", 5)
        cmds.setAttr(self.node + ".input2X", lock=True)
        cmds.connectAttr(driver + ".ty", self.node + ".input1Y")

    def test_normal_and_fast_select_the_same_attributes(self):
        normal = [plug.getLongName() for plug in mlib.getNode(self.node).resetAttrs()]
        cmds.setAttr(self.node + ".input1X", 3)
        cmds.setAttr(self.node + ".input1Z", 4)
        fast = [plug.getLongName() for plug in mlib.getNode(self.node).resetAttrs(fast=True)]
        self.assertEqual(normal, fast)
        self.assertIn("input1X", normal)
        self.assertNotIn("input1Y", normal)
        self.assertNotIn("input2X", normal)
        self.assertEqual(cmds.getAttr(self.node + ".input1Z"), 0)
        self.assertEqual(cmds.getAttr(self.node + ".input2X"), 5)

    def test_normal_undo_once_and_fast_without_undo(self):
        cmds.flushUndo()
        mlib.getNode(self.node).resetAttrs()
        self.assertEqual(cmds.getAttr(self.node + ".input1X"), 0)
        cmds.undo()
        self.assertEqual(cmds.getAttr(self.node + ".input1X"), 3)
        cmds.flushUndo()
        mlib.getNode(self.node).resetAttrs(fast=True)
        self.assertEqual(cmds.getAttr(self.node + ".input1X"), 0)
        self.assertUndoEmpty()

    def test_array_plugs_are_skipped(self):
        average = self.make("plusMinusAverage", "average#")
        cmds.setAttr(average + ".input1D[0]", 2)
        for fast in (False, True):
            with self.subTest(fast=fast):
                names = [plug.getLongName() for plug in mlib.getNode(average).resetAttrs(fast=fast)]
                self.assertNotIn("input1D", names)
        self.assertEqual(cmds.getAttr(average + ".input1D[0]"), 2)


class NodeHistoryAndPlugsSpecTest(NamespaceCase):
    """getHistory の探索の起点と、getPlugs のフラグの振り分け。"""

    def test_transform_history_is_the_shape_history(self):
        cube = cmds.polyCube(name=self.name("cube"))[0]
        transform = mlib.getNode(cube)
        shape = transform.getShape()
        history = transform.getHistory()
        self.assertEqual(history[0], shape)
        self.assertEqual(history[1:], shape.getHistory())
        self.assertEqual([node.getType() for node in transform.getHistory(type="polyCube")], ["polyCube"])
        with patch.object(cmds, "listHistory", side_effect=AssertionError("listHistory")):
            self.assertTrue(transform.getHistory(future=True))

    def test_get_history_of_invalid_node_raises(self):
        node = mlib.getNode(self.make())
        cmds.delete(node.getFullName())
        with self.assertRaises(RuntimeError):
            node.getHistory()

    def test_get_plugs_uses_om2_only_for_known_true_flags(self):
        node = mlib.getNode(self.make())
        cmds.addAttr(node.getFullName(), longName="values", attributeType="double", multi=True, keyable=True)
        with patch.object(cmds, "listAttr", side_effect=AssertionError("listAttr")):
            plugs = node.getPlugs()
            keyable = node.getPlugs(keyable=True)
            scalar = node.getPlugs(scalar=True, includeChildren=False)
        self.assertIn("translateX", [plug.getLongName() for plug in plugs])
        self.assertEqual([plug.getLongName() for plug in keyable][:3], ["visibility", "translateX", "translateY"])
        self.assertNotIn("translateX", [plug.getLongName() for plug in scalar])
        self.assertIn("values", [plug.getLongName() for plug in scalar])
        # om2 で扱わないフラグ・False の値は cmds.listAttr へそのまま渡す。
        for flags in ({"multi": True}, {"keyable": False}, {"k": True}):
            with self.subTest(flags=flags):
                with patch.object(cmds, "listAttr", wraps=cmds.listAttr) as spy:
                    node.getPlugs(**flags)
                spy.assert_called_once_with(node.getFullName(), **flags)


class IkHandleJointsSpecTest(NamespaceCase):
    """getJoints は start から末端の1つ前までの Joint を返し、includeTip で末端を足す。"""

    def test_joints_from_start_and_tip(self):
        cmds.select(clear=True)
        joints = [cmds.joint(position=(index, 0, 0), name=self.name("joint{}".format(index))) for index in range(4)]
        cmds.select(clear=True)
        handle = mlib.getNode(cmds.ikHandle(startJoint=joints[1], endEffector=joints[3],
                                            name=self.name("handle"))[0])
        with patch.object(cmds, "ikHandle", side_effect=AssertionError("ikHandle")):
            result = handle.getJoints()
            tipped = handle.getJoints(includeTip=True)
        self.assertTrue(all(isinstance(joint, Joint) for joint in tipped))
        self.assertEqual([joint.getName() for joint in result], [joints[1], joints[2]])
        self.assertEqual([joint.getName() for joint in tipped], [joints[1], joints[2], joints[3]])


class PlugSetMutedFastSpecTest(unittest.TestCase):
    """setMuted(fast=True) の約束。fast は名前空間の無いノードだけ扱うため、ルートに一意な名前で作る。"""

    def setUp(self):
        self.prefix = "mlibSpecMute" + uuid.uuid4().hex[:8]
        self.created = []
        self.undo_state = cmds.undoInfo(query=True, state=True)
        cmds.undoInfo(state=True)
        cmds.currentTime(4)

    def tearDown(self):
        for name in cmds.ls(self.prefix + "*", "mute_" + self.prefix + "*") or []:
            if cmds.objExists(name):
                cmds.delete(name)
        cmds.undoInfo(state=self.undo_state)

    def keyed(self, attribute="tx"):
        node = cmds.createNode("transform", name=self.prefix + "#", skipSelect=True)
        cmds.setKeyframe(node + "." + attribute, time=1, value=2)
        cmds.setKeyframe(node + "." + attribute, time=10, value=5)
        return node

    def test_fast_matches_normal_without_cmds_or_undo(self):
        fast_node, normal_node = self.keyed(), self.keyed()
        cmds.flushUndo()
        with patch.object(cmds, "mute", side_effect=AssertionError("mute")):
            mlib.getPlug(fast_node + ".tx").setMuted(True, fast=True)
        self.assertUndoEmpty()
        mlib.getPlug(normal_node + ".tx").setMuted(True)
        for node in (fast_node, normal_node):
            mute = cmds.listConnections(node + ".tx", source=True, destination=False)[0]
            self.assertEqual(cmds.nodeType(mute), "mute")
            self.assertEqual(mute, "mute_{}_translateX".format(node))
            self.assertEqual(cmds.getAttr(mute + ".holdTime"), 4.0)
        self.assertEqual(cmds.getAttr(fast_node + ".tx"), cmds.getAttr(normal_node + ".tx"))
        cmds.flushUndo()
        mlib.getPlug(fast_node + ".tx").setMuted(False, fast=True)
        self.assertUndoEmpty()
        self.assertFalse(mlib.getPlug(fast_node + ".tx").isMuted())
        self.assertEqual(cmds.nodeType(cmds.listConnections(fast_node + ".tx", source=True,
                                                            destination=False)[0]), "animCurveTL")

    def test_normal_undo_once(self):
        node = self.keyed()
        cmds.flushUndo()
        mlib.getPlug(node + ".tx").setMuted(True)
        cmds.undo()
        self.assertFalse(mlib.getPlug(node + ".tx").isMuted())
        self.assertFalse(cmds.ls("mute_" + node + "*"))

    def test_compound_mutes_animated_children_and_static_is_noop(self):
        node = self.keyed("sx")
        mlib.getPlug(node + ".scale").setMuted(True, fast=True)
        self.assertTrue(mlib.getPlug(node + ".sx").isMuted())
        self.assertEqual(cmds.ls("mute_" + node + "*"), ["mute_{}_scaleX".format(node)])
        mlib.getPlug(node + ".ty").setMuted(True, fast=True)
        self.assertFalse(mlib.getPlug(node + ".ty").isMuted())

    def test_unsupported_cases_raise_before_changes(self):
        cmds.namespace(add=self.prefix + "Ns")
        try:
            spaced = cmds.createNode("transform", name=self.prefix + "Ns:node")
            cmds.setKeyframe(spaced + ".tx", value=1)
            locked = self.keyed()
            cmds.setAttr(locked + ".tx", lock=True)
            converted = cmds.createNode("transform", name=self.prefix + "#")
            cmds.connectAttr(cmds.createNode("multiplyDivide", name=self.prefix + "#") + ".outputX",
                             converted + ".rx")
            array = self.keyed()
            cmds.addAttr(array, longName="values", attributeType="double", multi=True)
            cases = (spaced + ".tx", locked + ".tx", converted + ".rx", array + ".values")
            before = cmds.ls(type="mute")
            for name in cases:
                with self.subTest(plug=name):
                    with self.assertRaises(NotImplementedError):
                        mlib.getPlug(name).setMuted(True, fast=True)
                    self.assertEqual(cmds.ls(type="mute"), before)
        finally:
            cmds.namespace(removeNamespace=self.prefix + "Ns", deleteNamespaceContent=True)

    def test_argument_errors(self):
        node = self.keyed()
        for call in (lambda: mlib.getPlug(node + ".tx").setMuted(1, fast=True),
                     lambda: mlib.getPlug(node + ".tx").setMuted(True, fast=1)):
            with self.assertRaises(TypeError):
                call()
        self.assertFalse(mlib.getPlug(node + ".tx").isMuted())

    def assertUndoEmpty(self):
        """Undo キューが空であることを確かめる(fast 経路の確認用)。"""
        self.assertTrue(cmds.undoInfo(query=True, undoQueueEmpty=True))


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
