"""Transformの分解を使う設定が、変わるチャンネルだけを書くことを実Mayaで検証する。

対象の約束(2026-10-26 変更):
    * ``setRotate`` はrotateチャンネルだけを書く。translate・scale・shearはロック・接続
      されていても例外にならず、通知・Undoの記録もrotateだけになる。
    * ``setMatrix``・``setTransformation`` は、分解した書込み値が現在値(内部単位)と完全に
      一致するチャンネルを書かない。書き込むチャンネルがロックされていれば従来どおり失敗する。
    * 通常・fast・safeのいずれも同じ考え方で、Jointでも同じ。
"""

import sys
import unittest
import uuid

import maya.api.OpenMaya as om2
import maya.cmds as cmds

import mlib
mlib.reload()
from mlib.maths.matrix import Matrix


class _ChangeRecorder(object):
    """attributeChangedコールバックで、値が設定されたアトリビュートの短い名前を記録する。"""

    def __init__(self, name):
        sel = om2.MSelectionList()
        sel.add(name)
        self.names = []
        self._id = om2.MNodeMessage.addAttributeChangedCallback(sel.getDependNode(0), self._callback)

    def _callback(self, message, plug, other, client):
        if message & om2.MNodeMessage.kAttributeSet:
            self.names.append(plug.partialName(useLongNames=False))

    def remove(self):
        om2.MMessage.removeCallback(self._id)

    def channels(self):
        """記録した名前を、親チャンネル(t・r・s・sh等)の集合へまとめて返す。"""
        result = set()
        for name in self.names:
            for parent in ("sh", "t", "r", "s"):
                if name.startswith(parent) and name[len(parent):] in ("", "x", "y", "z", "xy", "xz", "yz"):
                    result.add(parent)
                    break
            else:
                result.add(name)
        return result


def _unchanged(node, planned):
    """setMatrix(get=True)の予定値のうち、現在の内部値と完全に一致するチャンネル名の集合を返す。"""
    fn = om2.MFnDependencyNode(node.mnode())
    result = set()
    for key, attr in (("rotate", "rotate"), ("scale", "scale"), ("shear", "shear")):
        plug = fn.findPlug(attr, False)
        if tuple(planned[key]) == tuple(plug.child(i).asDouble() for i in range(3)):
            result.add(key)
    return result


def _close(a, b, tolerance=1e-9):
    return all(abs(x - y) <= tolerance for x, y in zip(a, b))


class _Base(unittest.TestCase):
    """専用の名前空間にノードを作り、tearDownで削除する。"""

    def setUp(self):
        self.ns = "mlibContractB_" + uuid.uuid4().hex
        cmds.namespace(add=self.ns)
        self.undo_state = cmds.undoInfo(query=True, state=True)
        cmds.undoInfo(state=True)
        self.recorders = []

    def tearDown(self):
        for recorder in self.recorders:
            recorder.remove()
        cmds.undoInfo(state=self.undo_state)
        if cmds.namespace(exists=self.ns):
            cmds.namespace(removeNamespace=self.ns, deleteNamespaceContent=True)

    def make(self, node_type="transform", name="node"):
        return cmds.createNode(node_type, name="%s:%s" % (self.ns, name))

    def record(self, name):
        recorder = _ChangeRecorder(name)
        self.recorders.append(recorder)
        return recorder

    @staticmethod
    def lock(name, *channels):
        for channel in channels:
            cmds.setAttr("%s.%s" % (name, channel), lock=True)


class SetRotateOnlyRotateTest(_Base):
    """setRotateがrotateだけを書くことを確かめる。"""

    def test_other_channels_locked(self):
        for kwargs in ({}, {"fast": True}, {"safe": True}):
            with self.subTest(**kwargs):
                name = self.make(name="locked%d" % len(self.recorders))
                cmds.setAttr(name + ".t", 1, 2, 3)
                self.lock(name, "t", "s", "sh")
                node = mlib.getNode(name)
                expected = node.setRotate((0.1, 0.2, 0.3), get=True)
                recorder = self.record(name)
                node.setRotate((0.1, 0.2, 0.3), **kwargs)
                self.assertTrue(_close(cmds.getAttr(name + ".r")[0], [om2.MAngle(v).asDegrees() for v in expected]))
                self.assertEqual(recorder.channels(), {"r"})
                self.assertEqual(cmds.getAttr(name + ".t")[0], (1.0, 2.0, 3.0))

    def test_undo_restores_rotate_only(self):
        name = self.make()
        cmds.setAttr(name + ".r", 5, 6, 7)
        node = mlib.getNode(name)
        node.setRotate((0.4, 0.5, 0.6))
        cmds.undo()
        self.assertTrue(_close(cmds.getAttr(name + ".r")[0], (5, 6, 7)))

    def test_pivot_kept_like_setattr(self):
        # ピボットが0でない場合も、translateは変えずrotateを設定したときと同じ結果になる。
        name = self.make(name="pivot")
        reference = self.make(name="pivotRef")
        for target in (name, reference):
            cmds.setAttr(target + ".rp", 0.5, 0.2, -0.3)
            cmds.setAttr(target + ".sp", 0.1, 0.2, 0.3)
            cmds.setAttr(target + ".t", 1, 2, 3)
        node = mlib.getNode(name)
        node.setRotate((10, 20, 30), unit="deg")
        cmds.setAttr(reference + ".r", 10, 20, 30)
        self.assertEqual(cmds.getAttr(name + ".t")[0], (1.0, 2.0, 3.0))
        self.assertTrue(_close(cmds.getAttr(name + ".wm"), cmds.getAttr(reference + ".wm")))

    def test_locked_rotate_still_fails(self):
        name = self.make()
        self.lock(name, "r")
        node = mlib.getNode(name)
        with self.assertRaises(RuntimeError):
            node.setRotate((0.1, 0.2, 0.3))
        node.setRotate((0.1, 0.2, 0.3), safe=True)
        self.assertEqual(cmds.getAttr(name + ".r")[0], (0.0, 0.0, 0.0))

    def test_joint(self):
        name = self.make("joint", "joint")
        cmds.setAttr(name + ".jo", 10, 5, 0)
        cmds.setAttr(name + ".t", 1, 0, 0)
        self.lock(name, "t", "s", "sh")
        node = mlib.getNode(name)
        recorder = self.record(name)
        node.setRotate((0.1, 0.2, 0.3), ws=True)
        self.assertEqual(recorder.channels(), {"r"})


class SetMatrixChangedOnlyTest(_Base):
    """setMatrix・setTransformationが変わるチャンネルだけを書くことを確かめる。"""

    def _translate_only_matrix(self, name):
        # 分解の往復で値が完全に再現される回転・スケールにする(90度回転と整数のスケール)。
        cmds.setAttr(name + ".r", 0, 0, 90)
        cmds.setAttr(name + ".s", 1, 2, 3)
        node = mlib.getNode(name)
        matrix = Matrix(node.getMatrix())
        matrix.translate = (4.0, 5.0, 6.0)
        return node, matrix

    def test_unchanged_channels_locked(self):
        for kwargs in ({}, {"fast": True}, {"safe": True}, {"ws": True}):
            with self.subTest(**kwargs):
                name = self.make(name="m%d" % len(self.recorders))
                node, matrix = self._translate_only_matrix(name)
                planned = node.setMatrix(matrix, get=True)
                self.lock(name, "r", "s", "sh")
                rotate, scale = cmds.getAttr(name + ".r")[0], cmds.getAttr(name + ".s")[0]
                # 書込み予定値が現在値と一致するチャンネルだけを、ロックしても通る対象として扱う。
                self.assertEqual(_unchanged(node, planned), {"rotate", "scale", "shear"})
                recorder = self.record(name)
                node.setMatrix(matrix, **kwargs)
                self.assertEqual(recorder.channels(), {"t"})
                self.assertTrue(_close(cmds.getAttr(name + ".t")[0], (4, 5, 6)))
                self.assertEqual(cmds.getAttr(name + ".r")[0], rotate)
                self.assertEqual(cmds.getAttr(name + ".s")[0], scale)

    def test_same_matrix_writes_nothing(self):
        name = self.make()
        cmds.setAttr(name + ".t", 1, 2, 3)
        node = mlib.getNode(name)
        self.lock(name, "t", "r", "s", "sh")
        recorder = self.record(name)
        node.setMatrix(node.getMatrix())
        node.setMatrix(node.getMatrix(), fast=True)
        self.assertEqual(recorder.names, [])

    def test_connected_unchanged_channel(self):
        name = self.make(name="driven")
        driver = self.make(name="driver")
        cmds.connectAttr(driver + ".s", name + ".s")
        node = mlib.getNode(name)
        node.setMatrix(Matrix(translate=(1, 2, 3)))
        self.assertTrue(_close(cmds.getAttr(name + ".t")[0], (1, 2, 3)))

    def test_changed_locked_channel_still_fails(self):
        name = self.make()
        node, matrix = self._translate_only_matrix(name)
        self.lock(name, "t")
        with self.assertRaises(RuntimeError):
            node.setMatrix(matrix)
        node.setMatrix(matrix, safe=True)
        self.assertEqual(cmds.getAttr(name + ".t")[0], (0.0, 0.0, 0.0))

    def test_undo_once(self):
        name = self.make()
        node, matrix = self._translate_only_matrix(name)
        node.setMatrix(matrix)
        cmds.undo()
        self.assertEqual(cmds.getAttr(name + ".t")[0], (0.0, 0.0, 0.0))

    def test_set_transformation_same_value(self):
        for node_type in ("transform", "joint"):
            with self.subTest(node_type=node_type):
                name = self.make(node_type, "tr_" + node_type)
                cmds.setAttr(name + ".t", 1, 2, 3)
                cmds.setAttr(name + ".ra", 10, 0, 0)
                node = mlib.getNode(name)
                value = node.getTransformation()
                value.translate = (4.0, 5.0, 6.0)
                pivots = ("ra",) + (("jo",) if node_type == "joint" else ("rp", "sp", "rpt", "spt"))
                self.lock(name, *pivots)
                recorder = self.record(name)
                node.setTransformation(value)
                self.assertNotIn("ra", recorder.channels())
                self.assertIn("t", recorder.channels())
                self.assertTrue(_close(cmds.getAttr(name + ".t")[0], (4, 5, 6)))

    def test_joint_translate_only(self):
        name = self.make("joint", "jointM")
        cmds.setAttr(name + ".jo", 0, 0, 90)
        cmds.setAttr(name + ".s", 2, 2, 2)
        node = mlib.getNode(name)
        matrix = Matrix(node.getMatrix())
        matrix.translate = (1.0, 2.0, 3.0)
        self.assertEqual(_unchanged(node, node.setMatrix(matrix, get=True)), {"rotate", "scale", "shear"})
        self.lock(name, "r", "s", "sh")
        recorder = self.record(name)
        node.setMatrix(matrix)
        self.assertEqual(recorder.channels(), {"t"})

    def test_inexact_roundtrip_is_written(self):
        # 比較は完全一致なので、分解の往復で丸め誤差が出るチャンネルは同じ値でも書き込まれる。
        name = self.make(name="inexact")
        cmds.setAttr(name + ".r", 10, 20, 30)
        cmds.setAttr(name + ".s", 1, 2, 3)
        node = mlib.getNode(name)
        planned = node.setMatrix(node.getMatrix(), get=True)
        written = {"rotate", "scale", "shear"} - _unchanged(node, planned)
        recorder = self.record(name)
        node.setMatrix(node.getMatrix())
        expected = {{"rotate": "r", "scale": "s", "shear": "sh"}[key] for key in written}
        self.assertEqual(recorder.channels(), expected)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
