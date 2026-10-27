"""統合したNode APIと、生成・削除・スキン更新のUndo/fastを検証する。"""

from contextlib import ExitStack
import sys
import unittest
from unittest.mock import patch

import maya.api.OpenMaya as om2
import maya.cmds as cmds
import mlib


class ConsolidatedNodesTest(unittest.TestCase):
    """公開呼出しの戻り値・同値性・Undoキューを確認する。"""

    def setUp(self):
        """他の検証に影響しない新規シーンを用意する。"""
        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)

    def api_only(self):
        """fast実行中にMayaコマンドによるシーン更新を禁止する。"""
        stack = ExitStack()
        for name in ("setAttr", "delete", "deleteAttr", "addAttr", "createNode", "group", "parent",
                     "rename", "connectAttr", "disconnectAttr", "skinCluster", "skinPercent", "undoInfo"):
            stack.enter_context(patch.object(cmds, name, side_effect=AssertionError(name)))
        return stack

    def assertMatrixEqual(self, actual, expected):
        """Mayaの分解に伴う丸め差だけを許容する。"""
        for a, b in zip(actual, expected):
            self.assertAlmostEqual(a, b, delta=1e-6)

    def test_create_delete_undo(self):
        """通常作成はUndo、fast作成削除はキューを変更しない。"""
        ordinary = mlib.createNode("transform", name="ordinary")
        cmds.undo()
        self.assertFalse(ordinary.isValid())
        sentinel = cmds.createNode("network", name="sentinel")
        previous = cmds.undoInfo(query=True, undoName=True)
        with self.api_only():
            node = mlib.createNode("network", n="direct", skipSelect=True, fast=True)
            transform = mlib.createNode("transform", name="directTransform", fast=True)
            shape = mlib.createNode("mesh", parent=transform, name="directShape", fast=True)
            self.assertEqual(shape.getType(), "mesh")
            self.assertEqual(shape.getParent(), transform)
            node.delete(fast=True)
        self.assertFalse(node.isValid())
        self.assertTrue(transform.isValid())
        self.assertEqual(cmds.undoInfo(query=True, undoName=True), previous)
        cmds.undo()
        self.assertFalse(cmds.objExists(sentinel))
        self.assertTrue(transform.isValid())

    def test_alias_getters_and_fast_attributes(self):
        """追加アトリビュートの型・既定値・公開統合を確認する。"""
        node = mlib.createNode("network")
        with self.api_only():
            plug = node.addAttr("amount", "double", defaultValue=.25, minValue=0, maxValue=1,
                                keyable=True, fast=True)
            self.assertEqual(plug.get(), .25)
            self.assertIsNone(node.addAttr("ignored", "bool", getPlug=False, fast=True))
            vector = node.addAttr("offset", "double3", defaultValue=(1, 2, 3),
                                  childNames=("first", "second", "third"), fast=True)
            self.assertEqual(tuple(vector.get()), (1, 2, 3))
            text = node.addAttr("label", "string", defaultValue="sample", fast=True)
            self.assertEqual(text.get(), "sample")
            enum = node.addAttr("mode", "enum", enumName="zero:three=3:four", defaultValue=3, fast=True)
            self.assertEqual(enum.getEnumName(), "three")
            node.resetAttrs(["amount"], fast=True)
        self.assertEqual([p.getLongName() for p in node.getPlugs(userDefined=True, includeChildren=False)], ["amount", "ignored", "offset", "label", "mode"])
        self.assertEqual(len(node.getPlugs(userDefined=True, includeChildren=False)), 5)
        for obsolete in ("getInputs", "getOutputs", "getExtraAttrNames"):
            self.assertFalse(hasattr(type(node), obsolete))

    def test_fast_units_and_unsupported_definition(self):
        """UI単位に依存せず既定値を作り、未対応定義は追加前に拒否する。"""
        node = mlib.createNode("network")
        cmds.currentUnit(linear="m", angle="deg", time="film")
        try:
            with self.api_only():
                angle = node.addAttr("angle", "doubleAngle", defaultValue=.4, fast=True)
                length = node.addAttr("length", "doubleLinear", defaultValue=2.5, fast=True)
                time = node.addAttr("time", "time", defaultValue=.5, fast=True)
                self.assertAlmostEqual(angle.get(), .4)
                self.assertAlmostEqual(length.get(), 2.5)
                self.assertAlmostEqual(time.get(), .5)
                plain = mlib.getNode(node).addAttr(longName="plain", attributeType="double", defaultValue=3, fast=True)
                self.assertEqual(plain.get(), 3)
                with self.assertRaises(NotImplementedError):
                    node.addAttr("proxy", proxy=plain, fast=True)
            self.assertFalse(node.hasAttr("proxy"))
        finally:
            cmds.currentUnit(linear="cm", angle="deg", time="film")

    def test_fast_typed_defaults_validate_before_definition(self):
        """未対応factory・不正値・配列親の既定値で定義を部分追加しない。"""
        node = mlib.createNode("network")
        attempts = [
            ("floats", "floatArray", [1, 2], {}, NotImplementedError),
            ("geometry", "mesh", [1, 2], {}, NotImplementedError),
            ("numbers", "doubleArray", ["invalid"], {}, (TypeError, RuntimeError, ValueError)),
            ("matrix", "matrix", [1, 2], {}, (TypeError, RuntimeError, ValueError)),
            ("multiText", "string", "value", {"multi": True}, TypeError),
            ("readOnly", "string", "value", {"writable": False}, RuntimeError),
        ]
        for name, kind, value, flags, error in attempts:
            with self.subTest(name=name), self.api_only(), self.assertRaises(error):
                node.addAttr(name, kind, defaultValue=value, fast=True, **flags)
            self.assertFalse(node.hasAttr(name))
        with self.api_only():
            numbers = node.addAttr("validNumbers", "doubleArray", defaultValue=[1, 2, 3], fast=True)
            text = node.addAttr("validText", "string", defaultValue="value", fast=True)
            matrix = node.addAttr("validMatrix", "matrix", defaultValue=mlib.maths.Matrix(), fast=True)
        self.assertEqual(list(numbers.get()), [1, 2, 3])
        self.assertEqual(text.get(), "value")
        self.assertMatrixEqual(matrix.get(), mlib.maths.Matrix())

    def test_fast_delete_keeps_parent_and_component_rejects_before_edit(self):
        """modifier既定の親削除を抑え、cmds.deleteの対象範囲を保つ。"""
        parent = mlib.createNode("transform", name="parent")
        child = mlib.createNode("transform", parent=parent, name="child")
        with self.api_only():
            child.delete(fast=True)
        self.assertTrue(parent.isValid())
        self.assertFalse(child.isValid())
        mesh = mlib.getNode(cmds.polyCube(ch=False)[0]).getShapes()[0]
        with self.assertRaises(NotImplementedError):
            mlib.delete([parent, mesh.getVertices([0])], fast=True)
        self.assertTrue(parent.isValid())

    def test_rename_namespace_keeps_shape_and_world_matrix(self):
        """fastの名前・namespace変更は子Shapeを追従させ、行列を維持する。"""
        transform = mlib.createNode("transform", name="old")
        shape = mlib.createNode("mesh", name="oldShape", parent=transform)
        transform.setTranslate((2, 3, 4))
        matrix = list(transform.getMatrix(worldSpace=True))
        with self.api_only():
            self.assertEqual(transform.rename("new", fast=True), "new")
            self.assertEqual(shape.getNodeName(), "newShape")
            transform.setNamespace(":direct:children", fast=True)
            self.assertEqual(transform.getNodeName(), "direct:children:new")
        self.assertMatrixEqual(transform.getMatrix(worldSpace=True), matrix)

    def test_fast_rename_keeps_foreign_namespace_shape(self):
        """別namespaceのShapeは、ローカル名の接頭辞が一致しても改名しない。"""
        cmds.namespace(add="foreign")
        transform = mlib.createNode("transform", name="old")
        foreign = mlib.createNode("mesh", name="foreign:oldShape", parent=transform)
        normal = mlib.createNode("mesh", name="oldShape", parent=transform)
        with self.api_only():
            transform.rename("new", fast=True)
        self.assertEqual(foreign.getNodeName(), "foreign:oldShape")
        self.assertEqual(normal.getNodeName(), "newShape")

    def skin_fixture(self):
        """単一meshと3influenceの最小スキンを作る。"""
        mesh = cmds.polyPlane(ch=False, sx=1, sy=1)[0]
        root = mlib.createNode("joint", name="root")
        middle = mlib.createNode("joint", parent=root, name="middle")
        other = mlib.createNode("joint", name="other")
        skin = mlib.getNode(cmds.skinCluster([root.getFullName(), middle.getFullName(), other.getFullName()],
                                           mesh, toSelectedBones=True)[0])
        skin.setWeights([root.getFullName(), middle.getFullName(), other.getFullName()], [.2, .3, .5])
        return skin, root, middle, other

    def test_fast_native_skin_callback_and_last_influence(self):
        """移送先のない削除ではネイティブ削除と同じスキン構造を維持する。"""
        for single in (False, True):
            cmds.file(new=True, force=True)
            mesh = cmds.polyPlane(ch=False, sx=1, sy=1)[0]
            targets = [mlib.createNode("joint") for _ in range(1 if single else 2)]
            skin = mlib.getNode(cmds.skinCluster([n.getFullName() for n in targets], mesh,
                                               toSelectedBones=True)[0])
            name = targets[0].getFullName()
            cmds.delete(name)
            expected_exists = skin.isValid()
            expected_weights = list(skin.getWeights([targets[-1].getFullName()])) if expected_exists else None
            cmds.undo()
            with self.api_only():
                mlib.getNode(name).delete(fast=True)
            self.assertEqual(skin.isValid(), expected_exists)
            if expected_exists:
                self.assertEqual(list(skin.getWeights([targets[-1].getFullName()])), expected_weights)

    def test_fast_remove_influence_matches_normal(self):
        """正規化設定別のinfluence解除と残存ウェイトを比較する。"""
        for normalize in (0, 1, 2):
            cmds.file(new=True, force=True)
            skin, root, middle, other = self.skin_fixture()
            skin.getPlug("normalizeWeights").set(normalize)
            skin.removeInfluence(middle, transfer_to_parent=False)
            expected = list(skin.getWeights([root.getFullName(), other.getFullName()]))
            cmds.undo()
            with self.api_only():
                skin.removeInfluence(middle, transfer_to_parent=False, fast=True)
            self.assertEqual([n.getUuid() for n in skin.getInfluences()], [root.getUuid(), other.getUuid()])
            self.assertEqual(list(skin.getWeights([root.getFullName(), other.getFullName()])), expected)

    def test_fast_mixed_delete_preflights_before_first_node(self):
        """後続Jointのノードロックで先行Nodeを部分削除しない。"""
        skin, root, middle, other = self.skin_fixture()
        untouched = mlib.createNode("network", name="untouched")
        names = [n.getFullName() for n in (root, middle, other)]
        weights = list(skin.getWeights(names))
        cmds.lockNode(middle.getFullName(), lock=True)
        with self.api_only(), self.assertRaises(RuntimeError):
            mlib.delete([untouched, middle], fast=True)
        self.assertTrue(untouched.isValid())
        self.assertTrue(middle.isValid())
        self.assertEqual(list(skin.getWeights(names)), weights)

    def test_fast_influence_structure_failure_precedes_transfer(self):
        """influenceの構造ロックを祖先への加算より前に拒否する。"""
        skin, root, middle, other = self.skin_fixture()
        names = [n.getFullName() for n in (root, middle, other)]
        weights = list(skin.getWeights(names))
        skin.getPlug("matrix")[1].setFlags(locked=True)
        with self.api_only(), self.assertRaises(RuntimeError):
            skin.removeInfluence(middle, fast=True)
        self.assertEqual(list(skin.getWeights(names)), weights)
        self.assertEqual(len(skin.getInfluences()), 3)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
