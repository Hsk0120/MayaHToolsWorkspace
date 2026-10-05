"""公開メソッドを独立シーンで参照実装と比較する。"""
import sys
import unittest
from pathlib import Path
import maya.cmds as cmds
import maya.api.OpenMaya as om2
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "external" / "cymel" / "python"))
from cymel import core as cy
from hlib.nodes import Node
from hlib.maths import Vector


class ApiMethodsTest(unittest.TestCase):
    """名前だけでなく返す対象・階層・Undoを確認する。"""

    def setUp(self):
        """専用プロセスのシーンを初期化する。"""
        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)

    def test_names_and_enum(self):
        """Plug名・所有ノード・enumの現在値と指定値を比較する。"""
        node = Node(cmds.createNode("transform", name="control"))
        cp = cy.Node(node.name()).plug("tx")
        hp = node.plug("tx")
        for name in ("name", "shortName", "longName", "attrName", "plugName"):
            self.assertEqual(getattr(hp, name)(), getattr(cp, name)())
        self.assertEqual(hp.node(), node)
        enum = node.addAttr("mode", at="enum", en="off:on", dv=1)
        ce = cy.Node(node.name()).plug("mode")
        self.assertEqual(enum.getEnumName(), ce.getEnumName())
        self.assertEqual(enum.enumName(0), ce.enumName(0))
        self.assertTrue(node.hasAttr("mode"))
        enum.delete()
        self.assertFalse(node.hasAttr("mode"))
        cmds.undo()
        self.assertTrue(node.hasAttr("mode"))

    def test_conversion_and_connection_filters(self):
        """変換ノード省略とペア・型・方向・単一結果を比較する。"""
        a = Node(cmds.createNode("transform", name="a"))
        b = Node(cmds.createNode("transform", name="b"))
        conversion = Node(cmds.createNode("unitConversion"))
        a.tx.connectTo(conversion.input)
        conversion.output.connectTo(b.tx)
        cb = cy.Node(b.name())
        self.assertEqual(b.tx.source().name(), cb.tx.source().name())
        self.assertEqual(b.tx.sourceWithConversion().node(), conversion)
        self.assertEqual([p.name() for p in a.tx.destinations()], [p.name() for p in cy.Node(a.name()).tx.destinations()])
        for kwargs in ({}, {"asNode": True}, {"scn": True}, {"asPair": True},
                       {"t": "unitConversion", "et": True}, {"s": False}):
            def names(items):
                """比較対象のラッパー差を除く。"""
                return [(a.name(), b.name()) if isinstance(item, tuple) else item.name()
                        for item in items for a, b in ([item] if isinstance(item, tuple) else [(None, None)])]
            self.assertEqual(names(b.connections(**kwargs)), names(cb.connections(**kwargs)))
        self.assertEqual(b.inputs(index=0).node(), conversion)
        self.assertIsNone(b.inputs(index=100))
        from hlib.plugs import Plug
        class CustomPlug(Plug):
            """接続照会の明示ラッパー型。"""
            pass
        self.assertIsInstance(b.inputs(pcls=CustomPlug)[0], CustomPlug)
        b.tx.disconnectInput()
        self.assertIsNone(b.tx.source())
        cmds.undo()
        self.assertEqual(b.tx.source().node(), a)

    def test_dag(self):
        """親・子・表示・Shape欠落を比較する。"""
        parent = cmds.createNode("transform", name="parent")
        name = cmds.createNode("transform", name="child", parent=parent)
        shape = cmds.createNode("mesh", parent=name)
        hidden = cmds.createNode("mesh", parent=name)
        cmds.setAttr(hidden + ".intermediateObject", True)
        h, c = Node(name), cy.Transform(name)
        original = h.fullPath()
        self.assertEqual(h.parent().name(), c.parent().name())
        self.assertEqual(h.fullPath(), original)
        self.assertEqual(h.partialPath(), c.partialPath())
        for shapes in (False, True):
            for intermediates in (False, True):
                self.assertEqual([p.name() for p in h.children(shapes, intermediates)],
                                 [p.name() for p in c.children(shapes, intermediates)])
        self.assertIsNone(h.shape(20))
        mesh = h.shape()
        self.assertIs(mesh.shape(), mesh)
        self.assertEqual(mesh.children(), [])
        self.assertEqual(mesh.parent(2), Node(parent))
        Node(parent).hide()
        self.assertTrue(h.getVisibility())
        self.assertEqual(h.isVisible(), c.isVisible())
        Node(parent).show()
        self.assertTrue(h.isVisible())
        self.assertIsInstance(h.mnode(), om2.MObject)
        self.assertIsInstance(h.mpath(), om2.MDagPath)

    def test_flags(self):
        """末端フラグ設定とchannelBox操作のUndoを確認する。"""
        node = Node(cmds.createNode("transform"))
        self.assertIs(node.translate.setLocked(True, leaf=True).node(), node)
        self.assertTrue(node.tx.isLocked())
        cmds.undo()
        self.assertFalse(node.tx.isLocked())
        node.tx.setChannelBox(True)
        self.assertFalse(node.tx.isKeyable())
        self.assertTrue(node.tx.isChannelBox())
        cmds.undo()
        self.assertTrue(node.tx.isKeyable())

    def test_arrays(self):
        """疎配列・値だけの要素・接続・ロックを区別する。"""
        node = Node(cmds.createNode("network"))
        array = node.addAttr("values", at="double", multi=True)
        created = array.addElement(3)
        self.assertEqual([p.fullName() for p in created], [node.name() + ".values[3]"])
        self.assertEqual(array.addElement(3), [])
        ca = cy.Node(node.name()).plug("values")
        self.assertEqual(array.nextAvailable(), ca.nextAvailable())
        src = Node(cmds.createNode("network")).addAttr("value")
        src.connectTo(array[3])
        array.element(1, create=True).setLocked(True)
        for start in (-1, 0, 1, 4):
            self.assertEqual(array.nextAvailable(start), ca.nextAvailable(start))
        # 開始番号より小さい既存要素があっても、接続済み番号を避ける仕様を検証する。
        self.assertEqual(array.nextAvailable(3), 4)
        self.assertEqual(array.nextAvailable(0, asPlug=True).name(), ca.nextAvailable(0, asPlug=True).name())
        messages = node.addAttr("links", at="message", multi=True)
        with self.assertRaises(NotImplementedError):
            messages.addElement(0)

    def test_transform_short_names(self):
        """短縮名の取得・更新と既定戻り値を確認する。"""
        node = Node(cmds.createNode("transform"))
        self.assertIs(node.setT((1, 2, 3)), node)
        self.assertEqual(tuple(node.getT()), tuple(node.getTranslation()))
        self.assertEqual(node.getM(), node.getMatrix())
        self.assertEqual(node.getQ(), node.getQuaternion())
        self.assertEqual(node.getJOQ(), node.getQuaternion(r=False))
        self.assertEqual(Vector(1, 2, 3).lengthSq(), 14)
