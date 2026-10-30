"""Plugの接続演算子と接続照会の mlib 2.0 の約束を固定する。

対象: ``a >> b``(connectTo、接続先を返す)・``a << b``(connect、自身を返す)・``a // b``(disconnect、接続先を返す)、
通常のUndo経路のみ(1回のUndoで戻る)、不正入力の例外型、``getConnections`` の ``pcls`` 廃止と戻り値のクラス、
``Plug`` から ``getNextAvailable`` が無くなったこと(マルチアトリビュートは :class:`mlib.plugs.MultiPlug`)。
期待値は maya.cmds の接続照会で独立に求める。
"""

import unittest
import uuid

import maya.api.OpenMaya as om2
import maya.cmds as cmds
import mlib
from mlib import plugs


class _ConnectionSpecCase(unittest.TestCase):
    """専用の名前空間とUndoを用意し、作成したノードを終了時に削除する。"""

    def setUp(self):
        self.namespace = ":specPlugConn_" + uuid.uuid4().hex
        self.before = set(cmds.ls(long=True) or [])
        cmds.namespace(add=self.namespace)
        self.undo_state = cmds.undoInfo(query=True, state=True)
        cmds.undoInfo(state=True)
        self.a = self.make("transform")
        self.b = self.make("transform")
        # Plug.getFullName() とcmdsの接続照会はノードの一意名(ルートの "|" 無し)なので同じ形で比べる。
        self.an = self.a.getName()
        self.bn = self.b.getName()
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

    def inputs(self, plug_name):
        """cmdsで直接の入力元プラグ名を取得する(変換ノードを飛ばさない)。"""
        return cmds.listConnections(plug_name, source=True, destination=False, plugs=True,
                                    skipConversionNodes=False) or []

    def assertUndoEmpty(self):
        """Undoの記録が追加されていないことを確かめる。"""
        self.assertTrue(cmds.undoInfo(query=True, undoQueueEmpty=True))


class RightShiftSpecTest(_ConnectionSpecCase):
    """``src >> dst`` はconnectToの通常経路で、接続先Plugを返す。"""

    def test_connects_and_returns_destination(self):
        """戻り値は実際の接続先(dstと同じプラグ)。cmdsで接続を確認する。"""
        result = self.a.getPlug("tx") >> self.b.getPlug("ty")
        self.assertIsInstance(result, plugs.Plug)
        self.assertEqual(result.getFullName(), self.bn + ".translateY")
        self.assertEqual(self.inputs(self.bn + ".ty"), [self.an + ".translateX"])
        self.assertTrue(cmds.isConnected(self.an + ".tx", self.bn + ".ty"))

    def test_accepts_mplug_and_string(self):
        """dstはPlug・MPlug・"node.attr"文字列を受け付ける。"""
        for label, dst in (("str", self.bn + ".tx"), ("MPlug", self.b.getPlug("ty").mplug()),
                           ("Plug", self.b.getPlug("tz"))):
            with self.subTest(dst=label):
                result = self.a.getPlug("tx") >> dst
                self.assertEqual(result.getNode(), self.b)
                self.assertEqual(self.inputs(result.getFullName()), [self.an + ".translateX"])

    def test_evaluation_order_with_attribute_access(self):
        """``a >> b.x`` は ``a >> (b.x)`` と評価される(属性参照が演算子より優先)。"""
        net = self.make("network")
        cmds.addAttr(net.getFullName(), longName="val", attributeType="double")
        result = self.a.getPlug("tx") >> net.val
        self.assertEqual(result.getFullName(), net.getName() + ".val")
        self.assertEqual(self.inputs(net.getName() + ".val"), [self.an + ".translateX"])

    def test_chaining_through_returned_destination(self):
        """戻り値を次の ``>>`` の接続元にできる(a >> b >> c)。"""
        c = self.make("transform")
        result = self.a.getPlug("tx") >> self.b.getPlug("tx") >> c.getPlug("tx")
        self.assertEqual(result.getFullName(), c.getName() + ".translateX")
        self.assertEqual(self.inputs(self.bn + ".tx"), [self.an + ".translateX"])
        self.assertEqual(self.inputs(c.getName() + ".tx"), [self.bn + ".translateX"])

    def test_multi_destination_is_not_expanded(self):
        """マルチアトリビュート全体へはconnectTo(マルチアトリビュート)と同じくRuntimeError。空き要素を選ぶのはconnectTo(nextAvailable=True)。"""
        net = self.make("network")
        cmds.addAttr(net.getName(), longName="vals", attributeType="double", multi=True)
        values = net.getPlug("vals")
        with self.assertRaises(RuntimeError):
            self.a.getPlug("ty") >> values
        with self.assertRaises(RuntimeError):
            values << self.a.getPlug("ty")
        self.assertIsNone(cmds.getAttr(net.getName() + ".vals", multiIndices=True))
        result = self.a.getPlug("ty") >> values[2]
        self.assertEqual(result.getFullName(), net.getName() + ".vals[2]")
        # 5.0.0: cmds.connectAttr(nextAvailable=True)と同じく、接続のある最後の要素の次を選ぶ。
        chosen = self.a.getPlug("tz").connectTo(values, nextAvailable=True)
        self.assertEqual(chosen.getIndex(), 3)
        self.assertEqual(self.inputs(net.getName() + ".vals[3]"), [self.an + ".translateZ"])

    def test_undo_once(self):
        """1回のUndoで接続が外れ、Redoで戻る。"""
        self.a.getPlug("tx") >> self.b.getPlug("tx")
        cmds.undo()
        self.assertEqual(self.inputs(self.bn + ".tx"), [])
        self.assertUndoEmpty()
        cmds.redo()
        self.assertEqual(self.inputs(self.bn + ".tx"), [self.an + ".translateX"])

    def test_errors(self):
        """未対応の型はTypeError、入力済み・ロック・同一接続はRuntimeError(connectと同じ)。"""
        tx = self.a.getPlug("tx")
        for value in (5, None, [self.b.getPlug("tx")], self.b):
            with self.subTest(dst=type(value).__name__):
                with self.assertRaises(TypeError):
                    tx >> value
        with self.assertRaises(RuntimeError):
            tx >> self.bn + ".noSuchAttr"
        tx >> self.b.getPlug("tx")
        with self.assertRaises(RuntimeError):
            tx >> self.b.getPlug("tx")
        with self.assertRaises(RuntimeError):
            self.a.getPlug("ty") >> self.b.getPlug("tx")
        cmds.setAttr(self.bn + ".ty", lock=True)
        with self.assertRaises(RuntimeError):
            tx >> self.b.getPlug("ty")
        self.assertEqual(self.inputs(self.bn + ".tx"), [self.an + ".translateX"])
        self.assertEqual(self.inputs(self.bn + ".ty"), [])

    def test_no_fast_path(self):
        """演算子はfastを持たず、常にUndoへ記録する。"""
        self.a.getPlug("tx") >> self.b.getPlug("tx")
        self.assertFalse(cmds.undoInfo(query=True, undoQueueEmpty=True))


class LeftShiftSpecTest(_ConnectionSpecCase):
    """``dst << src`` はconnectの通常経路で、自身(dst)を返す。"""

    def test_connects_and_returns_self(self):
        """戻り値は自身そのもの(同一オブジェクト)。"""
        ty = self.b.getPlug("ty")
        result = ty << self.a.getPlug("tx")
        self.assertIs(result, ty)
        self.assertEqual(self.inputs(self.bn + ".ty"), [self.an + ".translateX"])

    def test_accepts_mplug_and_string(self):
        """srcはPlug・MPlug・文字列を受け付ける。"""
        cases = (("str", self.an + ".tx", "tx"), ("MPlug", self.a.getPlug("ty").mplug(), "ty"),
                 ("Plug", self.a.getPlug("tz"), "tz"))
        for label, src, attr in cases:
            with self.subTest(src=label):
                dst = self.b.getPlug(attr)
                self.assertIs(dst << src, dst)
                self.assertEqual(self.inputs(dst.getFullName()), [self.an + ".translate" + attr[-1].upper()])

    def test_undo_once_and_errors(self):
        """1回のUndoで戻る。未対応の型はTypeError、入力済みはRuntimeError。"""
        tx = self.b.getPlug("tx")
        tx << self.a.getPlug("tx")
        cmds.undo()
        self.assertEqual(self.inputs(self.bn + ".tx"), [])
        self.assertUndoEmpty()
        for value in (5, None, self.a):
            with self.subTest(src=type(value).__name__):
                with self.assertRaises(TypeError):
                    tx << value
        tx << self.a.getPlug("tx")
        with self.assertRaises(RuntimeError):
            tx << self.a.getPlug("ty")
        self.assertEqual(self.inputs(self.bn + ".tx"), [self.an + ".translateX"])


class FloorDivSpecTest(_ConnectionSpecCase):
    """``src // dst`` は src→dst の直接接続を解除し、解決した接続先Plugを返す。"""

    def test_disconnects_and_returns_destination(self):
        """戻り値はdstのPlug。接続が消えたことをcmdsで確認。"""
        cmds.connectAttr(self.an + ".tx", self.bn + ".tx")
        cmds.connectAttr(self.an + ".tx", self.bn + ".ty")
        cmds.flushUndo()
        result = self.a.getPlug("tx") // self.b.getPlug("tx")
        self.assertIsInstance(result, plugs.Plug)
        self.assertEqual(result.getFullName(), self.bn + ".translateX")
        self.assertEqual(self.inputs(self.bn + ".tx"), [])
        self.assertEqual(self.inputs(self.bn + ".ty"), [self.an + ".translateX"])
        result = self.a.getPlug("tx") // (self.bn + ".ty")
        self.assertEqual(result.getFullName(), self.bn + ".translateY")
        self.assertEqual(self.inputs(self.bn + ".ty"), [])

    def test_undo_once(self):
        """1回のUndoで接続が戻る。"""
        cmds.connectAttr(self.an + ".tx", self.bn + ".tx")
        cmds.flushUndo()
        self.a.getPlug("tx") // self.b.getPlug("tx")
        cmds.undo()
        self.assertEqual(self.inputs(self.bn + ".tx"), [self.an + ".translateX"])
        self.assertUndoEmpty()

    def test_errors(self):
        """接続が無ければRuntimeError、未対応の型はTypeError。他の接続は変わらない。"""
        cmds.connectAttr(self.an + ".ty", self.bn + ".tx")
        with self.assertRaises(RuntimeError):
            self.a.getPlug("tx") // self.b.getPlug("tx")
        for value in (5, None, self.b):
            with self.subTest(dst=type(value).__name__):
                with self.assertRaises(TypeError):
                    self.a.getPlug("ty") // value
        self.assertEqual(self.inputs(self.bn + ".tx"), [self.an + ".translateY"])

    def test_round_trip_with_rshift(self):
        """``>>`` で作った接続を ``//`` で解除でき、戻り値は同じ接続先を指す。"""
        connected = self.a.getPlug("tx") >> self.b.getPlug("tz")
        released = self.a.getPlug("tx") // self.b.getPlug("tz")
        self.assertEqual(connected.getFullName(), released.getFullName())
        self.assertEqual(self.inputs(self.bn + ".tz"), [])


class GetConnectionsSpecTest(_ConnectionSpecCase):
    """getConnectionsはpclsを持たず、登録型のPlugラッパーで返す。"""

    def test_returns_registered_plug_classes(self):
        """接続相手は型に応じたクラス(DoubleLinearPlug等)。asPairは(自身側, 相手側)のtuple。"""
        cmds.connectAttr(self.an + ".tx", self.bn + ".tx")
        cmds.connectAttr(self.an + ".ry", self.bn + ".rx")
        tx = self.b.getPlug("tx")
        result = tx.getConnections(s=True, d=False)
        self.assertEqual(len(result), 1)
        self.assertIsInstance(result[0], plugs.DoubleLinearPlug)
        self.assertEqual(result[0].getFullName(), self.an + ".translateX")
        pairs = self.b.getPlug("rx").getConnections(s=True, d=False, asPair=True)
        self.assertEqual([(p[0].getFullName(), p[1].getFullName()) for p in pairs],
                         [(self.bn + ".rotateX", self.an + ".rotateY")])
        self.assertIsInstance(pairs[0][1], plugs.DoubleAnglePlug)
        nodes = tx.getConnections(s=True, d=False, asNode=True)
        self.assertEqual(nodes, [self.a])
        self.assertEqual([str(p) for p in tx.getConnections(s=True, d=False)],
                         cmds.listConnections(self.bn + ".tx", source=True, destination=False, plugs=True))

    def test_pcls_is_removed(self):
        """pclsは位置・キーワードのどちらでも受け付けない。"""
        tx = self.b.getPlug("tx")
        with self.assertRaises(TypeError):
            tx.getConnections(pcls=plugs.Plug)
        with self.assertRaises(TypeError):
            tx.getConnections(True, True, False, None, False, False, True, True, False, None, False, False,
                              False, False, True, True, None, plugs.Plug)


class NextAvailableLocationSpecTest(_ConnectionSpecCase):
    """getNextAvailableはMultiPlugだけが持つ。"""

    def test_plug_has_no_get_next_available(self):
        """非マルチアトリビュートのPlugにはgetNextAvailableが無い(AttributeError)。マルチアトリビュート全体のMultiPlugにはある。"""
        tx = self.a.getPlug("tx")
        self.assertFalse(hasattr(tx, "getNextAvailable"))
        with self.assertRaises(AttributeError):
            tx.getNextAvailable()
        self.assertFalse(hasattr(self.a.getPlug("t"), "getNextAvailable"))
        self.assertNotIn("getNextAvailable", plugs.Plug.__dict__)
        self.assertIn("getNextAvailable", plugs.MultiPlug.__dict__)
        net = self.make("network")
        cmds.addAttr(net.getFullName(), longName="vals", attributeType="double", multi=True)
        values = net.getPlug("vals")
        self.assertIsInstance(values, plugs.MultiPlug)
        self.assertEqual(values.getNextAvailable(), 0)
        element = values[0]
        self.assertFalse(hasattr(element, "getNextAvailable"))
        # Plug(node, mplug) でマルチアトリビュートを包んだ場合も MultiPlug になり、同じ入口を持つ。
        wrapped = plugs.Plug(net, values.mplug())
        self.assertIsInstance(wrapped, plugs.MultiPlug)
        self.assertEqual(wrapped.getNextAvailable(vacant=True), 0)
        self.assertIsInstance(values.mplug(), om2.MPlug)


if __name__ == "__main__":
    unittest.main()
