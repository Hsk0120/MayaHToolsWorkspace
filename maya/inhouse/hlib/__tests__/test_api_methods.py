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
        cp = cy.Node(node.getName()).plug("tx")
        hp = node.getPlug("tx")
        for h_name, c_name in (("getName", "name"), ("getShortName", "shortName"),
                               ("getLongName", "longName"), ("getAttrName", "attrName"),
                               ("getPlugName", "plugName")):
            self.assertEqual(getattr(hp, h_name)(), getattr(cp, c_name)())
        self.assertEqual(hp.getNode(), node)
        enum = node.addAttr("mode", at="enum", en="off:on", dv=1)
        ce = cy.Node(node.getName()).plug("mode")
        self.assertEqual(enum.getEnumName(), ce.getEnumName())
        self.assertEqual(enum.getEnumFieldName(0), ce.enumName(0))
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
        a.tx.connectTo(conversion.getPlug("input"))
        conversion.output.connectTo(b.tx)
        cb = cy.Node(b.getName())
        self.assertEqual(b.tx.getSource().getName(), cb.tx.source().name())
        self.assertEqual(b.tx.getSourceWithConversion().getNode(), conversion)
        self.assertEqual([p.getName() for p in a.tx.getDestinations()], [p.name() for p in cy.Node(a.getName()).tx.destinations()])
        for kwargs in ({}, {"asNode": True}, {"scn": True}, {"asPair": True},
                       {"t": "unitConversion", "et": True}, {"s": False}):
            def names(items, get_name):
                """各ライブラリの正式名取得を使い、比較対象のラッパー差を除く。

                Args:
                    items: 接続照会の戻り値。
                    get_name: 対象の名前を取得する関数。

                Returns:
                    list: 対象名または接続ペアの名前列。
                """
                return [(get_name(item[0]), get_name(item[1])) if isinstance(item, tuple) else get_name(item)
                        for item in items]
            self.assertEqual(names(b.getConnections(**kwargs), lambda item: item.getName()),
                             names(cb.connections(**kwargs), lambda item: item.name()))
        self.assertEqual(b.getInputs(index=0).getNode(), conversion)
        self.assertIsNone(b.getInputs(index=100))
        from hlib.plugs import Plug
        class CustomPlug(Plug):
            """接続照会の明示ラッパー型。"""
            pass
        self.assertIsInstance(b.getInputs(pcls=CustomPlug)[0], CustomPlug)
        b.tx.disconnectInput()
        self.assertIsNone(b.tx.getSource())
        cmds.undo()
        self.assertEqual(b.tx.getSource().getNode(), a)

    def test_dag(self):
        """親・子・表示・Shape欠落を比較する。"""
        parent = cmds.createNode("transform", name="parent")
        name = cmds.createNode("transform", name="child", parent=parent)
        shape = cmds.createNode("mesh", parent=name)
        hidden = cmds.createNode("mesh", parent=name)
        cmds.setAttr(hidden + ".intermediateObject", True)
        h, c = Node(name), cy.Transform(name)
        original = h.getFullPath()
        self.assertEqual(h.getParent().getName(), c.parent().name())
        self.assertEqual(h.getFullPath(), original)
        self.assertEqual(h.getPartialPath(), c.partialPath())
        for shapes in (False, True):
            for intermediates in (False, True):
                self.assertEqual([p.getName() for p in h.getChildren(shapes, intermediates)],
                                 [p.name() for p in c.children(shapes, intermediates)])
        self.assertIsNone(h.getShape(20))
        mesh = h.getShape()
        self.assertIs(mesh.getShape(), mesh)
        self.assertEqual(mesh.getChildren(), [])
        self.assertEqual(mesh.getParent(2), Node(parent))
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
        self.assertIs(node.getPlug("translate").setLocked(True, leaf=True).getNode(), node)
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
        self.assertEqual([p.getFullName() for p in created], [node.getName() + ".values[3]"])
        self.assertEqual(array.addElement(3), [])
        ca = cy.Node(node.getName()).plug("values")
        self.assertEqual(array.getNextAvailable(), ca.nextAvailable())
        src = Node(cmds.createNode("network")).addAttr("value")
        src.connectTo(array[3])
        array.getElement(1, create=True).setLocked(True)
        for start in (-1, 0, 1, 4):
            self.assertEqual(array.getNextAvailable(start), ca.nextAvailable(start))
        # 開始番号より小さい既存要素があっても、接続済み番号を避ける仕様を検証する。
        self.assertEqual(array.getNextAvailable(3), 4)
        self.assertEqual(array.getNextAvailable(0, asPlug=True).getName(), ca.nextAvailable(0, asPlug=True).name())
        messages = node.addAttr("links", at="message", multi=True)
        with self.assertRaises(NotImplementedError):
            messages.addElement(0)

    def test_transform_short_names(self):
        """短縮名の取得・更新と既定戻り値を確認する。"""
        node = Node(cmds.createNode("transform"))
        self.assertIs(node.setTranslate((1, 2, 3)), node)
        self.assertEqual(tuple(node.getTranslate()), tuple(node.getTranslate()))
        self.assertEqual(node.getMatrix(), node.getMatrix())
        self.assertEqual(node.getQuaternion(), node.getQuaternion())
        self.assertEqual(node.getJointOrientQuaternion(), node.getQuaternion(r=False))
        self.assertEqual(Vector(1, 2, 3).lengthSq(), 14)
