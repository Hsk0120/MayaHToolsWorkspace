"""Plugの接続・切断・接続照会の約束(方向・force・lock・nextAvailable・fast・Undo・戻り値)を固定する。

期待値はmaya.cmdsの接続照会と比べる。食い違いは`.maya-output/mlib-spec-tests/FINDINGS_B.md`の
番号をコメントに書き、実際の今の振る舞いを固定する。
"""

import unittest
import uuid

import maya.cmds as cmds
import mlib
from mlib import plugs


class _ConnectionSpecCase(unittest.TestCase):
    """専用の名前空間とUndoを用意し、作成したノードを終了時に削除する。"""

    def setUp(self):
        self.namespace = ":specBConnect_" + uuid.uuid4().hex
        self.before = set(cmds.ls(long=True) or [])
        cmds.namespace(add=self.namespace)
        self.undo_state = cmds.undoInfo(query=True, state=True)
        self.units = (cmds.currentUnit(query=True, linear=True), cmds.currentUnit(query=True, angle=True))
        cmds.undoInfo(state=True)
        cmds.currentUnit(linear="cm", angle="deg")
        self.a = self.make("transform")
        self.b = self.make("transform")
        self.an = self.a.getName()
        self.bn = self.b.getName()

    def tearDown(self):
        cmds.currentUnit(linear=self.units[0], angle=self.units[1])
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


class ConnectSpecTest(_ConnectionSpecCase):
    """connect・connectToの入力・戻り値・置換・ロック。"""

    def test_connect_returns_destination_and_accepts_inputs(self):
        """connectは接続先(自身)を返し、Plug・名前・MPlugとsource別名を受け付ける。"""
        bx = self.b.getPlug("tx")
        self.assertIs(bx.connect(self.a.getPlug("tx")), bx)
        self.assertEqual(self.inputs(self.bn + ".tx"), [self.an + ".translateX"])
        self.b.getPlug("ty").connect(self.an + ".ty")
        self.assertTrue(cmds.isConnected(self.an + ".ty", self.bn + ".ty"))
        self.b.getPlug("tz").connect(self.a.getPlug("tz").mplug())
        self.assertTrue(cmds.isConnected(self.an + ".tz", self.bn + ".tz"))
        self.b.getPlug("sx").connect(source=self.a.getPlug("sx"))
        self.assertTrue(cmds.isConnected(self.an + ".sx", self.bn + ".sx"))

    def test_connect_argument_errors(self):
        """接続元の欠落・重複指定・未対応型はTypeError、存在しない名前はRuntimeError。"""
        sy = self.b.getPlug("sy")
        with self.assertRaises(TypeError):
            sy.connect()
        with self.assertRaises(TypeError):
            sy.connect(self.a.getPlug("tx"), source=self.a.getPlug("tx"))
        with self.assertRaises(TypeError):
            sy.connect(5)
        with self.assertRaises(TypeError):
            sy.connect(self.a.getPlug("tx"), fast=1)
        with self.assertRaises(ValueError):
            sy.connect("")
        with self.assertRaises(RuntimeError):
            sy.connect(self.namespace + ":missing.tx")
        self.assertEqual(self.inputs(self.bn + ".sy"), [])

    def test_same_and_existing_connection(self):
        """同じ接続はRuntimeError。別の入力の置換はforce/fが必要。"""
        bx = self.b.getPlug("tx")
        bx.connect(self.a.getPlug("tx"))
        with self.assertRaises(RuntimeError):
            bx.connect(self.a.getPlug("tx"))
        with self.assertRaises(RuntimeError):
            bx.connect(self.a.getPlug("ty"))
        with self.assertRaises(RuntimeError):
            bx.connect(self.a.getPlug("ty"), fast=True)
        self.assertEqual(self.inputs(self.bn + ".tx"), [self.an + ".translateX"])
        bx.connect(self.a.getPlug("ty"), force=True)
        self.assertEqual(self.inputs(self.bn + ".tx"), [self.an + ".translateY"])
        bx.connect(self.a.getPlug("tz"), f=True)
        self.assertEqual(self.inputs(self.bn + ".tx"), [self.an + ".translateZ"])
        bx.connect(self.a.getPlug("tx"), force=True, fast=True)
        self.assertEqual(self.inputs(self.bn + ".tx"), [self.an + ".translateX"])

    def test_undo_each_connect_and_restore_constant(self):
        """通常の接続・置換はそれぞれ1回のUndoで戻り、接続前の定数値も戻る。"""
        cmds.setAttr(self.bn + ".tx", 5.0)
        bx = self.b.getPlug("tx")
        cmds.flushUndo()
        bx.connect(self.a.getPlug("ty"))
        bx.connect(self.a.getPlug("tz"), force=True)
        cmds.undo()
        self.assertEqual(self.inputs(self.bn + ".tx"), [self.an + ".translateY"])
        cmds.undo()
        self.assertEqual(self.inputs(self.bn + ".tx"), [])
        self.assertEqual(cmds.getAttr(self.bn + ".tx"), 5.0)
        self.assertUndoEmpty()
        cmds.redo()
        self.assertEqual(self.inputs(self.bn + ".tx"), [self.an + ".translateY"])

    def test_fast_connect_is_not_recorded(self):
        """fastの接続はUndoへ記録せず、Undoの設定も変えない。"""
        cmds.flushUndo()
        self.b.getPlug("ty").connect(self.a.getPlug("tx"), fast=True)
        self.a.getPlug("tz").connectTo(self.b.getPlug("tz"), fast=True)
        self.assertTrue(cmds.isConnected(self.an + ".tx", self.bn + ".ty"))
        self.assertTrue(cmds.isConnected(self.an + ".tz", self.bn + ".tz"))
        self.assertUndoEmpty()
        self.assertTrue(cmds.undoInfo(query=True, state=True))

    def test_locked_destination(self):
        """ロックされた接続先はforce・unlockの両方が必要で、接続後も元のロックを戻す。"""
        cmds.setAttr(self.bn + ".ty", lock=True)
        ty = self.b.getPlug("ty")
        with self.assertRaises(RuntimeError):
            ty.connect(self.a.getPlug("tx"))
        with self.assertRaises(RuntimeError):
            ty.connect(self.a.getPlug("tx"), force=True, unlock=False)
        self.assertEqual(self.inputs(self.bn + ".ty"), [])
        ty.connect(self.a.getPlug("tx"), force=True)
        self.assertTrue(cmds.isConnected(self.an + ".tx", self.bn + ".ty"))
        self.assertTrue(cmds.getAttr(self.bn + ".ty", lock=True))

    def test_locked_parent_is_temporarily_unlocked_with_force(self):
        """forceは上位の複合のロックも一時解除し、接続後に再ロックする。"""
        cmds.setAttr(self.bn + ".t", lock=True)
        tz = self.b.getPlug("tz")
        tz.connect(self.a.getPlug("tx"), force=True)
        self.assertTrue(cmds.isConnected(self.an + ".tx", self.bn + ".tz"))
        self.assertTrue(cmds.getAttr(self.bn + ".t", lock=True))

    def test_lock_after_connect(self):
        """lock/lは接続後に接続先をロックする(通常・fast)。"""
        self.b.getPlug("tx").connect(self.a.getPlug("tx"), lock=True)
        self.b.getPlug("ty").connect(self.a.getPlug("tx"), l=True)
        self.b.getPlug("tz").connect(self.a.getPlug("tx"), lock=True, fast=True)
        for axis in "xyz":
            with self.subTest(axis=axis):
                self.assertTrue(cmds.getAttr(self.bn + ".t" + axis, lock=True))

    def test_next_available_on_array(self):
        """配列全体へのnextAvailable/naは入力・ロックの無い最初の要素を選んで返す。"""
        net = self.make("network")
        cmds.addAttr(net.getFullName(), longName="vals", attributeType="double", multi=True)
        values = net.getPlug("vals")
        cmds.setAttr(net.getFullName() + ".vals[0]", 1.0)
        cmds.setAttr(net.getFullName() + ".vals[0]", lock=True)
        cmds.connectAttr(self.an + ".tx", net.getFullName() + ".vals[1]")
        target = values.connect(self.a.getPlug("ty"), nextAvailable=True)
        self.assertEqual(target.getFullName(), net.getFullName() + ".vals[2]")
        self.assertIsNot(target, values)
        target = values.connect(self.a.getPlug("tz"), na=True)
        self.assertEqual(target.getFullName(), net.getFullName() + ".vals[3]")
        self.assertTrue(cmds.isConnected(self.an + ".tz", net.getFullName() + ".vals[3]"))

    def test_connect_to_delegates_and_returns_destination(self):
        """connectToは接続先Plugを返し、force等の指定をconnectへ渡す。dstの欠落・重複はTypeError。"""
        result = self.a.getPlug("rx").connectTo(self.bn + ".rx")
        self.assertEqual(result, self.b.getPlug("rx"))
        self.assertTrue(cmds.isConnected(self.an + ".rx", self.bn + ".rx"))
        self.a.getPlug("ry").connectTo(destination=self.b.getPlug("rx"), force=True)
        self.assertEqual(self.inputs(self.bn + ".rx"), [self.an + ".rotateY"])
        with self.assertRaises(RuntimeError):
            self.a.getPlug("rz").connectTo(self.b.getPlug("rx"))
        with self.assertRaises(TypeError):
            self.a.getPlug("rz").connectTo()
        with self.assertRaises(TypeError):
            self.a.getPlug("rz").connectTo(self.b.getPlug("rz"), destination=self.b.getPlug("rz"))
        with self.assertRaises(TypeError):
            self.a.getPlug("rz").connectTo(self.b.getPlug("rz"), fast=1)

    def test_connect_from_deleted_attribute_source(self):
        """削除済みアトリビュートの接続元は事前に拒否し、対象名入りのRuntimeError(FINDINGS B-8で修正)。"""
        cmds.addAttr(self.an, longName="gone", attributeType="double")
        gone = self.a.getPlug("gone")
        cmds.deleteAttr(self.an + ".gone")
        for fast in (False, True):
            with self.subTest(fast=fast):
                with self.assertRaises(RuntimeError) as context:
                    self.b.getPlug("tx").connect(gone, fast=fast)
                message = str(context.exception)
                self.assertIn(".gone", message)
                self.assertIn(self.a.getName(), message)
                self.assertIn(self.bn + ".translateX", message)
                self.assertEqual(self.inputs(self.bn + ".tx"), [])
        # connectTo(削除済みの接続元から)も同じ。
        with self.assertRaises(RuntimeError):
            gone.connectTo(self.b.getPlug("ty"))
        self.assertEqual(self.inputs(self.bn + ".ty"), [])


class DisconnectSpecTest(_ConnectionSpecCase):
    """disconnect・disconnectInput・disconnectAllの戻り値と例外。"""

    def test_disconnect_returns_source(self):
        """disconnectは切断した入力元Plugを返す。srcを渡せばそのオブジェクト自身。"""
        cmds.connectAttr(self.an + ".tx", self.bn + ".tx")
        source = self.a.getPlug("tx")
        self.assertIs(self.b.getPlug("tx").disconnect(source), source)
        self.assertEqual(self.inputs(self.bn + ".tx"), [])
        cmds.connectAttr(self.an + ".ty", self.bn + ".ty")
        result = self.b.getPlug("ty").disconnect()
        self.assertEqual(result.getFullName(), self.an + ".translateY")
        self.assertIsInstance(result, plugs.Plug)
        cmds.connectAttr(self.an + ".tz", self.bn + ".tz")
        result = self.b.getPlug("tz").disconnect(source=self.an + ".tz")
        self.assertEqual(result, self.a.getPlug("tz"))

    def test_disconnect_errors(self):
        """入力が無い・指定の接続が無いはRuntimeError、boolはTypeError、src重複はTypeError。"""
        bx = self.b.getPlug("tx")
        with self.assertRaises(RuntimeError):
            bx.disconnect()
        cmds.connectAttr(self.an + ".tx", self.bn + ".tx")
        with self.assertRaises(RuntimeError):
            bx.disconnect(self.a.getPlug("ty"))
        with self.assertRaises(TypeError):
            bx.disconnect(True)
        with self.assertRaises(TypeError):
            bx.disconnect(self.a.getPlug("tx"), source=self.a.getPlug("tx"))
        with self.assertRaises(TypeError):
            bx.disconnect(fast=1)
        self.assertTrue(cmds.isConnected(self.an + ".tx", self.bn + ".tx"))

    def test_disconnect_does_not_disconnect_outputs(self):
        """出力側から呼ぶと入力が無いためRuntimeErrorで、出力接続は残る。"""
        cmds.connectAttr(self.an + ".tx", self.bn + ".tx")
        with self.assertRaises(RuntimeError):
            self.a.getPlug("tx").disconnect()
        self.assertTrue(cmds.isConnected(self.an + ".tx", self.bn + ".tx"))

    def test_disconnect_undo_and_fast(self):
        """通常の切断は1回のUndoで戻り、fastは記録しない。"""
        cmds.connectAttr(self.an + ".tx", self.bn + ".tx")
        cmds.flushUndo()
        self.b.getPlug("tx").disconnect()
        cmds.undo()
        self.assertTrue(cmds.isConnected(self.an + ".tx", self.bn + ".tx"))
        cmds.flushUndo()
        self.b.getPlug("tx").disconnect(fast=True)
        self.assertFalse(cmds.isConnected(self.an + ".tx", self.bn + ".tx"))
        self.assertUndoEmpty()

    def test_disconnect_locked_requires_force(self):
        """ロックされた接続先はforce/fで一時解除して切断し、ロックを戻す。"""
        cmds.connectAttr(self.an + ".tx", self.bn + ".tx")
        cmds.setAttr(self.bn + ".tx", lock=True)
        with self.assertRaises(RuntimeError):
            self.b.getPlug("tx").disconnect()
        self.b.getPlug("tx").disconnect(f=True)
        self.assertFalse(cmds.isConnected(self.an + ".tx", self.bn + ".tx"))
        self.assertTrue(cmds.getAttr(self.bn + ".tx", lock=True))
        cmds.setAttr(self.bn + ".tx", lock=False)
        cmds.connectAttr(self.an + ".tx", self.bn + ".tx")
        cmds.setAttr(self.bn + ".tx", lock=True)
        self.b.getPlug("tx").disconnect(force=True, fast=True)
        self.assertFalse(cmds.isConnected(self.an + ".tx", self.bn + ".tx"))
        self.assertTrue(cmds.getAttr(self.bn + ".tx", lock=True))

    def test_disconnect_unit_conversion_keeps_node(self):
        """変換ノードを飛ばさずに直接の入力(unitConversion)を切断し、変換ノードは削除しない。"""
        cmds.connectAttr(self.an + ".tx", self.bn + ".rx")
        conversion = cmds.listConnections(self.bn + ".rx", source=True, destination=False,
                                          skipConversionNodes=False)[0]
        result = self.b.getPlug("rx").disconnect()
        self.assertEqual(result.getNode().getName(), conversion)
        self.assertTrue(cmds.objExists(conversion))
        self.assertEqual(self.inputs(self.bn + ".rx"), [])

    def test_disconnect_next_available_on_array(self):
        """配列でsrcとnaを指定すると、srcへ直結した全要素を切断して要素のlistを返す。"""
        net = self.make("network")
        name = net.getFullName()
        cmds.addAttr(name, longName="vals", attributeType="double", multi=True)
        cmds.connectAttr(self.an + ".tx", name + ".vals[1]")
        cmds.connectAttr(self.an + ".ty", name + ".vals[2]")
        cmds.connectAttr(self.an + ".tx", name + ".vals[4]")
        values = net.getPlug("vals")
        result = values.disconnect(self.a.getPlug("tx"), nextAvailable=True)
        self.assertEqual([p.getFullName() for p in result], [name + ".vals[1]", name + ".vals[4]"])
        self.assertEqual(values.getSourceNodes(), {2: self.a})
        with self.assertRaises(RuntimeError):
            values.disconnect(self.a.getPlug("tx"), na=True)

    def test_disconnect_input_is_noop_without_input(self):
        """disconnectInputは入力が無ければ何もせず自身を返し、あれば切断して自身を返す。"""
        ty = self.b.getPlug("ty")
        self.assertIs(ty.disconnectInput(), ty)
        cmds.connectAttr(self.an + ".ty", self.bn + ".ty")
        self.assertIs(ty.disconnectInput(), ty)
        self.assertEqual(self.inputs(self.bn + ".ty"), [])
        cmds.connectAttr(self.an + ".ty", self.bn + ".ty")
        cmds.flushUndo()
        ty.disconnectInput(fast=True)
        self.assertUndoEmpty()
        with self.assertRaises(TypeError):
            ty.disconnectInput(fast=1)

    def test_disconnect_all_directions_and_undo(self):
        """disconnectAllは入力と全出力を外し、方向指定・別名を受け付け、1回のUndoで戻る。"""
        middle = self.b.getPlug("tx")
        cmds.connectAttr(self.an + ".tx", self.bn + ".tx")
        cmds.connectAttr(self.bn + ".tx", self.bn + ".ty")
        cmds.connectAttr(self.bn + ".tx", self.bn + ".tz")
        self.assertIs(middle.disconnectAll(src=False, dst=False), middle)
        self.assertTrue(cmds.isConnected(self.an + ".tx", self.bn + ".tx"))
        middle.disconnectAll(source=False)
        self.assertTrue(cmds.isConnected(self.an + ".tx", self.bn + ".tx"))
        self.assertFalse(cmds.listConnections(self.bn + ".tx", source=False, destination=True))
        cmds.connectAttr(self.bn + ".tx", self.bn + ".ty")
        cmds.flushUndo()
        middle.disconnectAll()
        self.assertFalse(cmds.listConnections(self.bn + ".tx"))
        cmds.undo()
        self.assertTrue(cmds.isConnected(self.an + ".tx", self.bn + ".tx"))
        self.assertTrue(cmds.isConnected(self.bn + ".tx", self.bn + ".ty"))
        unconnected = self.a.getPlug("sx")
        self.assertIs(unconnected.disconnectAll(), unconnected)
        with self.assertRaises(TypeError):
            middle.disconnectAll(src=1)
        with self.assertRaises(TypeError):
            middle.disconnectAll(dst=True, destination=True)
        with self.assertRaises(TypeError):
            middle.disconnectAll(fast=1)

    def test_disconnect_all_does_not_unlock(self):
        """disconnectAllはロックを解除しないため、ロックされた出力先でRuntimeErrorになる。"""
        cmds.connectAttr(self.an + ".tx", self.bn + ".tx")
        cmds.setAttr(self.bn + ".tx", lock=True)
        with self.assertRaises(RuntimeError):
            self.a.getPlug("tx").disconnectAll()
        self.assertTrue(cmds.isConnected(self.an + ".tx", self.bn + ".tx"))

    def test_disconnect_all_fast(self):
        """fastのdisconnectAllはUndoへ記録しない。"""
        cmds.connectAttr(self.an + ".tx", self.bn + ".tx")
        cmds.flushUndo()
        self.a.getPlug("tx").disconnectAll(fast=True)
        self.assertFalse(cmds.isConnected(self.an + ".tx", self.bn + ".tx"))
        self.assertUndoEmpty()


class ConnectionQuerySpecTest(_ConnectionSpecCase):
    """getSource・getDestinations・getConnections・isConnected系の照会。"""

    def setUp(self):
        super().setUp()
        cmds.connectAttr(self.an + ".tx", self.bn + ".ty")
        cmds.connectAttr(self.an + ".tx", self.bn + ".tz")
        cmds.connectAttr(self.an + ".tx", self.bn + ".rx")  # unitConversionを経由する。
        self.conversion = cmds.listConnections(self.bn + ".rx", source=True, destination=False,
                                               skipConversionNodes=False)[0]

    def test_get_source(self):
        """getSourceは既定で変換ノードを飛ばし、未接続はNone。asNode・asPair・typeも使える。"""
        self.assertEqual(self.b.getPlug("ty").getSource(), self.a.getPlug("tx"))
        self.assertIsNone(self.b.getPlug("tx").getSource())
        self.assertEqual(self.b.getPlug("rx").getSource(), self.a.getPlug("tx"))
        direct = self.b.getPlug("rx").getSource(skipConversionNodes=False)
        self.assertEqual(direct.getNode().getName(), self.conversion)
        self.assertEqual(self.b.getPlug("rx").getSource(scn=False), direct)
        self.assertEqual(self.b.getPlug("ty").getSource(asNode=True), self.a)
        pair = self.b.getPlug("ty").getSource(asPair=True)
        self.assertEqual(pair, (self.b.getPlug("ty"), self.a.getPlug("tx")))
        self.assertEqual(self.b.getPlug("ty").getSource(type="transform"), self.a.getPlug("tx"))
        self.assertIsNone(self.b.getPlug("ty").getSource(type="joint"))
        with self.assertRaises(TypeError):
            self.b.getPlug("ty").getSource(scn=True, skipConversionNodes=True)
        with self.assertRaises(TypeError):
            self.b.getPlug("ty").getSource(idx=0)

    def test_get_source_does_not_expand_children(self):
        """getSourceは子の独立した接続を展開しない。"""
        self.assertIsNone(self.b.getPlug("translate").getSource())

    def test_get_destinations(self):
        """getDestinationsは出力先のlist。未接続は[]、asNodeはノード単位で統合、indexは範囲外None。"""
        destinations = self.a.getPlug("tx").getDestinations()
        self.assertEqual(sorted(p.getFullName() for p in destinations),
                         sorted([self.bn + ".rotateX", self.bn + ".translateY", self.bn + ".translateZ"]))
        direct = self.a.getPlug("tx").getDestinations(skipConversionNodes=False)
        self.assertIn(self.conversion + ".input", [p.getFullName() for p in direct])
        self.assertEqual(self.a.getPlug("tx").getDestinations(asNode=True), [self.b])
        self.assertEqual(self.a.getPlug("sx").getDestinations(), [])
        self.assertIsNone(self.a.getPlug("tx").getDestinations(index=99))
        self.assertIsInstance(self.a.getPlug("tx").getDestinations(index=-1), plugs.Plug)
        with self.assertRaises(TypeError):
            self.a.getPlug("tx").getDestinations(scn=True, skipConversionNodes=True)

    def test_get_connections_on_compound_and_flags(self):
        """getConnectionsは子を再帰し、変換ノードは既定で飛ばさない。方向・ペア・index・pclsの扱い。"""
        translate = self.b.getPlug("translate")
        self.assertEqual(translate.getConnections(), [self.a.getPlug("tx")])
        self.assertEqual(translate.getConnections(checkChildren=False), [])
        pairs = translate.getConnections(c=True)
        self.assertEqual(sorted(p[0].getFullName() for p in pairs), [self.bn + ".translateY", self.bn + ".translateZ"])
        self.assertTrue(all(p[1] == self.a.getPlug("tx") for p in pairs))
        self.assertEqual(translate.getConnections(d=False), translate.getConnections(destination=False))
        self.assertEqual(translate.getConnections(s=False), [])
        self.assertEqual(self.b.getPlug("rx").getConnections()[0].getNode().getName(), self.conversion)
        self.assertEqual(self.b.getPlug("rx").getConnections(scn=True), [self.a.getPlug("tx")])
        self.assertIsNone(translate.getConnections(index=5))
        self.assertEqual(translate.getConnections(idx=0), self.a.getPlug("tx"))
        # pclsは指定クラスで構築する。基底Plugを渡すと型登録に従って派生クラスを選ぶ。
        self.assertIs(type(translate.getConnections(pcls=plugs.DoublePlug)[0]), plugs.DoublePlug)
        self.assertIs(type(translate.getConnections(pcls=plugs.Plug)[0]), plugs.DoubleLinearPlug)
        self.assertEqual(self.a.getPlug("tx").getConnections(dst=False), [])
        for kwargs in (dict(index=0, idx=0), dict(source=True, src=True), dict(destination=True, dst=True)):
            with self.subTest(**kwargs):
                with self.assertRaises(TypeError):
                    translate.getConnections(**kwargs)

    def test_is_connected_and_directions(self):
        """isConnectedは方向別に直接の接続を判定する。両Falseは常にFalse、bool以外はTypeError。"""
        ax = self.a.getPlug("tx")
        self.assertTrue(ax.isConnected())
        self.assertFalse(ax.isConnected(dst=False))
        self.assertTrue(ax.isConnected(src=False))
        self.assertFalse(ax.isConnected(src=False, dst=False))
        self.assertTrue(self.b.getPlug("ty").isConnected(destination=False))
        self.assertFalse(self.b.getPlug("translate").isConnected())
        self.assertTrue(ax.isSource())
        self.assertFalse(ax.isDestination())
        self.assertTrue(self.b.getPlug("ty").isDestination())
        self.assertFalse(self.b.getPlug("ty").isSource())
        with self.assertRaises(TypeError):
            ax.isConnected(src=1)
        with self.assertRaises(TypeError):
            ax.isConnected(src=True, source=True)

    def test_is_connected_to(self):
        """isConnectedToは直結だけを方向別に判定し、変換ノードの先は展開しない。"""
        ax, by = self.a.getPlug("tx"), self.b.getPlug("ty")
        self.assertTrue(by.isConnectedTo(ax))
        self.assertTrue(by.isConnectedTo(self.an + ".tx"))
        self.assertTrue(by.isConnectedTo(ax.mplug()))
        self.assertTrue(ax.isConnectedTo(by))
        self.assertFalse(by.isConnectedTo(ax, src=False))
        self.assertTrue(ax.isConnectedTo(by, src=False))
        self.assertFalse(ax.isConnectedTo(by, dst=False))
        self.assertFalse(by.isConnectedTo(ax, src=False, dst=False))
        self.assertFalse(self.b.getPlug("rx").isConnectedTo(ax))
        self.assertFalse(by.isConnectedTo(self.a.getPlug("ty")))
        with self.assertRaises(TypeError):
            by.isConnectedTo(5)
        with self.assertRaises(TypeError):
            by.isConnectedTo(self.an)
        with self.assertRaises(ValueError):
            by.isConnectedTo("")
        with self.assertRaises(RuntimeError):
            by.isConnectedTo(self.an + ".missingAttr")
        with self.assertRaises(TypeError):
            by.isConnectedTo(ax, src=1)
        with self.assertRaises(TypeError):
            by.isConnectedTo(ax, dst=True, destination=True)

    def test_get_anim_curve_direct_only(self):
        """getAnimCurveは直接のanimCurve入力だけを返し、それ以外はNone。"""
        self.assertIsNone(self.b.getPlug("ty").getAnimCurve())
        self.assertIsNone(self.b.getPlug("sx").getAnimCurve())
        cmds.setKeyframe(self.bn + ".sx", time=1, value=2)
        curve = self.b.getPlug("sx").getAnimCurve()
        self.assertEqual(curve.getName(),
                         cmds.listConnections(self.bn + ".sx", source=True, destination=False)[0])
        self.assertTrue(curve.isType("animCurve"))


if __name__ == "__main__":
    unittest.main()
