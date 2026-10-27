"""高速化した読取・列挙・一括呼出しが、従来の経路と同じ結果になることを実Mayaで検証する。

対象は、複合Plugの子ラッパーを作らない値読取、Transformの静的チャンネルの直接読取、
子の列挙で入力解決を省いたラッパー作成、一括呼出し内のsignature・束縛の共有、
double2・double3の親への1回のsetAttr、Undo無効時のチャンク開閉と接続前の定数記録の省略、
名前付きundoTransactionの内側のundoChunkで入れ子のチャンクを開かないことも対象とする。
ls・getNode・getPlug・親/Shape/インスタンスの取得で入力解決を省いたラッパー作成も対象とする。
Nodesの重複判定の省略と、influence・displayLayer・shadingEngineの列挙結果から直接作るラッパーも対象とする。
ArrayPlug.getの要素ラッパーの省略、BlendShapeのtargetWeightsの範囲setAttr、Vectorの演算結果の複製も対象とする。
fast=Trueの経路で重ねていた書込み可否の検査・名前の取得・ラッパー生成の入口の省略も対象とする。
ノード・Plugのラッパー作成での関数セットの使い回し・ハンドルの共有・__init__の直接展開も対象とする。
Node.getConnectionsの自身側Plugの省略、getHistoryのUUIDの1回取得、getPlugs(userDefined=True)の選別、
Container.removeMembersの集合での所属判定、Container/Namespaceの列挙結果から直接作るラッパーも対象とする。
拡張の探索で名前の一致しない探索パスのパッケージ判定を省くことと、import時に読まない標準モジュールも対象とする。
Matrixの生成で循環importを省く入力の型と、TransformのsetMatrixでrotateAxisを1回だけ読むことも対象とする。
"""

import sys
import unittest
import uuid

import maya.api.OpenMaya as om2
import maya.cmds as cmds

import mlib
mlib.reload()
from mlib.decorator import undoChunk, undoTransaction
from mlib.nodes import Transforms
from mlib.plugs import CompoundPlug


class CompoundDirectReadTest(unittest.TestCase):
    """複合Plugのget()が、子Plugのget()を並べた値・cmds.getAttrと一致することを確かめる。"""

    def setUp(self):
        self.ns = "mlibSpeedup_" + uuid.uuid4().hex
        cmds.namespace(add=self.ns)
        self.units = (cmds.currentUnit(query=True, linear=True), cmds.currentUnit(query=True, angle=True),
                      cmds.currentUnit(query=True, time=True))
        self.node = cmds.createNode("transform", name=self.ns + ":node")
        cmds.setAttr(self.node + ".t", 1.5, -2.25, 3.0)
        cmds.setAttr(self.node + ".r", 10, 20, 30)
        cmds.setAttr(self.node + ".s", 1, 2, 3)
        cmds.setAttr(self.node + ".sh", 0.1, 0.2, 0.3)
        cmds.setAttr(self.node + ".rp", 0.5, 0.25, -1)
        add = cmds.addAttr
        add(self.node, longName="vecD", attributeType="double3")
        for axis in "XYZ":
            add(self.node, longName="vecD" + axis, attributeType="double", parent="vecD")
        add(self.node, longName="colF", attributeType="float3", usedAsColor=True)
        for axis in "RGB":
            add(self.node, longName="colF" + axis, attributeType="float", parent="colF")
        add(self.node, longName="pairL", attributeType="long2")
        for axis in "AB":
            add(self.node, longName="pairL" + axis, attributeType="long", parent="pairL")
        add(self.node, longName="mixed", attributeType="compound", numberOfChildren=8)
        add(self.node, longName="mDist", attributeType="doubleLinear", parent="mixed")
        add(self.node, longName="mAngle", attributeType="doubleAngle", parent="mixed")
        add(self.node, longName="mTime", attributeType="time", parent="mixed")
        add(self.node, longName="mEnum", attributeType="enum", enumName="a:b:c", parent="mixed")
        add(self.node, longName="mText", dataType="string", parent="mixed")
        add(self.node, longName="mFlag", attributeType="bool", parent="mixed")
        add(self.node, longName="mInner", attributeType="double2", parent="mixed")
        add(self.node, longName="mInnerA", attributeType="double", parent="mInner")
        add(self.node, longName="mInnerB", attributeType="double", parent="mInner")
        add(self.node, longName="mList", attributeType="double", multi=True, parent="mixed")
        cmds.setAttr(self.node + ".vecD", 0.125, 7, -3)
        cmds.setAttr(self.node + ".colF", 0.25, 0.5, 0.75)
        cmds.setAttr(self.node + ".pairL", 4, -9)
        cmds.setAttr(self.node + ".mDist", 2.5)
        cmds.setAttr(self.node + ".mAngle", 45)
        cmds.setAttr(self.node + ".mTime", 12)
        cmds.setAttr(self.node + ".mEnum", 2)
        cmds.setAttr(self.node + ".mText", "text", type="string")
        cmds.setAttr(self.node + ".mFlag", True)
        cmds.setAttr(self.node + ".mInner", 1.25, 2.5)
        cmds.setAttr(self.node + ".mList[3]", 0.5)
        self.wrapper = mlib.getNode(self.node)
        self.names = ("translate", "rotate", "scale", "shear", "rotatePivot", "boundingBox",
                      "vecD", "colF", "pairL", "mixed", "mInner")

    def tearDown(self):
        cmds.currentUnit(linear=self.units[0], angle=self.units[1], time=self.units[2])
        cmds.namespace(removeNamespace=self.ns, deleteNamespaceContent=True)

    def child_values(self, plug):
        """従来の実装と同じく、子Plugを作ってget()した値を並べる。"""
        return tuple(child.get() for child in plug.getChildren())

    def assert_values_equal(self, actual, expected):
        self.assertEqual(len(actual), len(expected))
        for a, b in zip(actual, expected):
            if isinstance(b, (tuple, list, dict)) or not isinstance(b, float):
                self.assertEqual(type(a), type(b))
                self.assertEqual(a if not hasattr(a, "__iter__") or isinstance(a, str) else tuple(a),
                                 b if not hasattr(b, "__iter__") or isinstance(b, str) else tuple(b))
            else:
                self.assertIs(type(a), float)
                self.assertEqual(a, b)

    def test_get_matches_child_plugs_in_any_ui_units(self):
        for linear, angle, time in (("cm", "rad", "film"), ("m", "deg", "ntsc")):
            cmds.currentUnit(linear=linear, angle=angle, time=time)
            for name in self.names:
                plug = self.wrapper.getPlug(name)
                with self.subTest(name=name, linear=linear):
                    self.assert_values_equal(tuple(plug.get()), self.child_values(plug))
                    # 同じPlugで2回目(読取関数を保持した後)も現在値を読み直す。
                    self.assert_values_equal(tuple(plug.get()), self.child_values(plug))
                    ui = plug.get(uiUnits=True)
                    self.assertEqual(tuple(ui), tuple(child.get(uiUnits=True) for child in plug.getChildren()))

    def test_get_returns_math_types_and_current_values(self):
        translate = self.wrapper.getPlug("translate")
        self.assertIsInstance(translate.get(), mlib.maths.Translate)
        self.assertIsInstance(self.wrapper.getPlug("shear").get(), mlib.maths.Shear)
        self.assertIsInstance(self.wrapper.getPlug("vecD").get(), mlib.maths.Vector)
        self.assertIsInstance(self.wrapper.getPlug("rotate").get(), mlib.maths.EulerRotate)
        self.assertEqual(tuple(translate.get()), tuple(cmds.getAttr(self.node + ".t")[0]))
        cmds.setAttr(self.node + ".t", 4, 5, 6)
        self.assertEqual(tuple(translate.get()), (4.0, 5.0, 6.0))
        mixed = self.wrapper.getPlug("mixed").get()
        self.assertEqual(mixed[3], 2)
        self.assertEqual(mixed[4], "text")
        self.assertIs(mixed[5], True)
        self.assertEqual(mixed[7], {3: 0.5})

    def test_deleted_attribute_and_node_still_raise(self):
        plug = self.wrapper.getPlug("vecD")
        plug.get()
        cmds.deleteAttr(self.node + ".vecD")
        with self.assertRaises(RuntimeError):
            plug.get()
        cmds.undo()
        self.assertEqual(tuple(plug.get()), (0.125, 7.0, -3.0))
        translate = self.wrapper.getPlug("translate")
        cmds.delete(self.node)
        with self.assertRaises(RuntimeError):
            translate.get()


class TransformStaticReadTest(unittest.TestCase):
    """Transformの静的チャンネルの直接読取が、xform・getAttrの値と一致することを確かめる。"""

    def setUp(self):
        self.ns = "mlibSpeedupXf_" + uuid.uuid4().hex
        cmds.namespace(add=self.ns)
        self.unit = cmds.currentUnit(query=True, linear=True)
        self.parent = cmds.createNode("transform", name=self.ns + ":parent")
        cmds.setAttr(self.parent + ".t", 1, 2, 3)
        cmds.setAttr(self.parent + ".r", 15, 30, 45)
        cmds.setAttr(self.parent + ".s", 2, 3, 0.5)
        self.node = cmds.createNode("transform", name=self.ns + ":node", parent=self.parent)
        cmds.setAttr(self.node + ".t", -1, 0.5, 2)
        cmds.setAttr(self.node + ".r", 5, 10, 20)
        cmds.setAttr(self.node + ".rp", 0.3, -0.2, 0.1)
        cmds.setAttr(self.node + ".rpt", 0.05, 0.1, -0.05)
        cmds.setAttr(self.node + ".sp", -0.4, 0.6, 0.2)
        self.joint = cmds.createNode("joint", name=self.ns + ":joint", parent=self.parent)
        self.child_joint = cmds.createNode("joint", name=self.ns + ":childJoint", parent=self.joint)
        cmds.setAttr(self.joint + ".s", 2, 0.5, 4)
        cmds.setAttr(self.child_joint + ".t", 1, 2, 3)

    def tearDown(self):
        cmds.currentUnit(linear=self.unit)
        cmds.namespace(removeNamespace=self.ns, deleteNamespaceContent=True)

    def assert_close(self, actual, expected):
        self.assertEqual(len(tuple(actual)), len(expected))
        for a, b in zip(actual, expected):
            self.assertAlmostEqual(a, b, places=9)

    def test_get_translate_matches_xform(self):
        for unit, scale in (("cm", 1.0), ("m", 0.01)):
            cmds.currentUnit(linear=unit)
            for target in (self.node, self.child_joint):
                node = mlib.getNode(target)
                with self.subTest(target=target, unit=unit):
                    self.assert_close(node.getTranslate(ws=True),
                                      [v / scale for v in cmds.xform(target, q=True, ws=True, rotatePivot=True)])
                    self.assert_close(node.getTranslate(ws=True, at=3),
                                      [v / scale for v in cmds.xform(target, q=True, ws=True, scalePivot=True)])
                    self.assert_close(node.getTranslate(at=1), [v / scale for v in cmds.getAttr(target + ".t")[0]])

    def test_set_translate_round_trip_and_undo(self):
        node = mlib.getNode(self.node)
        before = cmds.getAttr(self.node + ".t")[0]
        node.setTranslate((3, -2, 1), ws=True)
        self.assert_close(cmds.xform(self.node, q=True, ws=True, rotatePivot=True), (3, -2, 1))
        cmds.undo()
        self.assert_close(cmds.getAttr(self.node + ".t")[0], before)
        joint = mlib.getNode(self.child_joint)
        joint.setTranslate((0.5, 0.25, -0.5), ws=True, fast=True)
        self.assert_close(cmds.xform(self.child_joint, q=True, ws=True, rotatePivot=True), (0.5, 0.25, -0.5))

    def test_invalid_node_raises_like_get_plug(self):
        node = mlib.getNode(self.node)
        cmds.delete(self.node)
        with self.assertRaises(RuntimeError) as expected:
            node.getPlug("translate")
        with self.assertRaises(RuntimeError) as actual:
            node.getTranslate(at=1)
        self.assertEqual(str(actual.exception), str(expected.exception))


class ChildWrapperAndBulkTest(unittest.TestCase):
    """子の列挙と一括呼出しが、従来の型選択・引数検証を保つことを確かめる。"""

    def setUp(self):
        self.ns = "mlibSpeedupDag_" + uuid.uuid4().hex
        cmds.namespace(add=self.ns)
        self.root = cmds.createNode("transform", name=self.ns + ":root")
        self.joint = cmds.createNode("joint", name=self.ns + ":joint", parent=self.root)
        self.mesh = cmds.polyCube(name=self.ns + ":mesh", constructionHistory=False)[0]
        cmds.parent(self.mesh, self.joint)
        self.locator = cmds.spaceLocator(name=self.ns + ":loc")[0]
        cmds.parent(self.locator, self.root)
        self.instance = cmds.instance(self.locator, name=self.ns + ":locInst")[0]

    def tearDown(self):
        cmds.namespace(removeNamespace=self.ns, deleteNamespaceContent=True)

    def test_children_types_and_paths_match_node_constructor(self):
        root = mlib.getNode(self.root)
        children = root.getChildren(shapes=True, allDescendents=True)
        # listRelativesは同じノードの別インスタンスのパスを1つにまとめるが、getChildrenは残す。
        expected = set(cmds.listRelatives(self.root, allDescendents=True, fullPath=True))
        expected.add(cmds.ls(self.instance, long=True)[0] + "|" + self.locator.split(":")[0] + ":locShape")
        self.assertEqual(sorted(c.getFullName() for c in children), sorted(expected))
        for child in children:
            # 入力解決を省いても、Node(MDagPath)と同じ型・同じインスタンスのパスになる。
            self.assertIs(type(child), type(mlib.getNode(child.mpath())))
            self.assertEqual(child, mlib.getNode(child.mpath()))
            self.assertTrue(child.isValid())
        self.assertIsInstance(root.getChildren()[0], mlib.nodes.Joint)

    def test_bulk_calls_share_validation_but_keep_contracts(self):
        nodes = Transforms([self.root, self.joint, self.mesh, self.locator])
        matrices = nodes.getMatrix(ws=True)
        self.assertEqual([list(m) for m in matrices], [list(mlib.getNode(n).getMatrix(ws=True)) for n in nodes])
        with self.assertRaises(TypeError):
            nodes.setTranslate((1, 2, 3), fast="yes")
        with self.assertRaises(TypeError):
            nodes.getMatrix(unknown=True)
        self.assertIs(nodes.setTranslate((1, 2, 3), fast=True), nodes)
        self.assertEqual(nodes.setTranslate((4, 5, 6), get=True),
                         [mlib.getNode(n).setTranslate((4, 5, 6), get=True) for n in nodes])
        mixed = nodes.callEach("setTranslate", [((0, 0, 0),)] * 4,
                               [{"fast": True}, {}, {"fast": True}, {"get": True}])
        self.assertIsInstance(mixed, list)
        self.assertEqual(len(mixed), 4)
        with self.assertRaises(TypeError):
            nodes.callEach("setTranslate", [((0, 0, 0),)] * 4, [{}, {"fast": 1}, {}, {}])


class CompoundBulkSetTest(unittest.TestCase):
    """double3の親への1回のsetAttrが、子ごとの書込みと同じ結果・例外・Undoになることを確かめる。"""

    def setUp(self):
        self.ns = "mlibSpeedupSet_" + uuid.uuid4().hex
        cmds.namespace(add=self.ns)
        self.units = (cmds.currentUnit(query=True, linear=True), cmds.currentUnit(query=True, angle=True))
        self.state = cmds.undoInfo(query=True, state=True)
        cmds.undoInfo(state=True)
        self.node = cmds.createNode("transform", name=self.ns + ":node")
        cmds.addAttr(self.node, longName="vecD", attributeType="double3")
        for axis in "XYZ":
            cmds.addAttr(self.node, longName="vecD" + axis, attributeType="double", parent="vecD")
        self.source = cmds.createNode("transform", name=self.ns + ":source")

    def tearDown(self):
        cmds.currentUnit(linear=self.units[0], angle=self.units[1])
        cmds.undoInfo(state=self.state)
        cmds.namespace(removeNamespace=self.ns, deleteNamespaceContent=True)

    def values(self, attribute):
        return [cmds.getAttr(self.node + "." + attribute + axis) for axis in "XYZ"]

    def test_values_units_and_single_undo(self):
        node = mlib.getNode(self.node)
        cmds.currentUnit(linear="mm", angle="deg")
        node.translate.set((1.0, 2, -3.5))
        self.assertEqual(self.values("translate"), [10.0, 20.0, -35.0])
        node.rotate.set((0.5, 0.25, 0.125))
        for actual, expected in zip(self.values("rotate"), (0.5, 0.25, 0.125)):
            self.assertAlmostEqual(om2.MAngle(actual, om2.MAngle.kDegrees).asRadians(), expected)
        node.getPlug("vecD").set((1.5, 2.5, 3.5))
        self.assertEqual(cmds.getAttr(self.node + ".vecD")[0], (1.5, 2.5, 3.5))
        self.assertEqual(cmds.undoInfo(query=True, undoName=True), "mlibDouble3PlugSet")
        cmds.undo()
        self.assertEqual(cmds.getAttr(self.node + ".vecD")[0], (0.0, 0.0, 0.0))
        # 1回のUndoで戻るのは直前のset()だけで、それ以前の設定は残る。
        self.assertEqual(self.values("translate"), [10.0, 20.0, -35.0])
        self.assertNotEqual(self.values("rotate"), [0.0, 0.0, 0.0])

    def test_locked_and_connected_children_keep_partial_update_rules(self):
        node = mlib.getNode(self.node)
        cmds.setAttr(self.node + ".translateY", lock=True)
        with self.assertRaisesRegex(RuntimeError, "Attribute is locked or connected: .*translateY"):
            node.translate.set((1.0, 2.0, 3.0))
        self.assertEqual(self.values("translate"), [0.0, 0.0, 0.0])
        self.assertEqual(node.translate.set((1.0, 2.0, 3.0), safe=True), 1)
        self.assertEqual(self.values("translate"), [1.0, 0.0, 3.0])
        cmds.connectAttr(self.source + ".tx", self.node + ".vecDZ")
        plug = node.getPlug("vecD")
        # CompoundPlug.setも全子の書込み可否を事前に確かめ、何も書かずに止まる。
        cmds.setAttr(self.node + ".vecDY", lock=True)
        with self.assertRaisesRegex(RuntimeError, "locked or connected"):
            CompoundPlug.set(plug, (4.0, 5.0, 6.0))
        self.assertEqual(self.values("vecD"), [0.0, 0.0, 0.0])
        self.assertEqual(CompoundPlug.set(plug, (7.0, 8.0, 9.0), safe=True), 2)
        self.assertEqual(self.values("vecD"), [7.0, 0.0, 0.0])

    def test_attribute_changed_callbacks_stay_per_child(self):
        node = mlib.getNode(self.node)
        changed = []

        def record(message, plug, other, data):
            if message & om2.MNodeMessage.kAttributeSet:
                changed.append(plug.partialName())

        callback = om2.MNodeMessage.addAttributeChangedCallback(node.mnode(), record)
        try:
            node.translate.set((1.0, 2.0, 3.0))
        finally:
            om2.MMessage.removeCallback(callback)
        self.assertEqual(changed, ["tx", "ty", "tz"])


class UndoChunkStateTest(unittest.TestCase):
    """undoChunkがUndo有効時の名前・範囲を保ち、無効時は開閉を省くことを確かめる。"""

    def setUp(self):
        self.state = cmds.undoInfo(query=True, state=True)
        self.node = cmds.createNode("transform", name="mlibSpeedupChunk_" + uuid.uuid4().hex)

    def tearDown(self):
        cmds.undoInfo(state=self.state)
        if cmds.objExists(self.node):
            cmds.delete(self.node)

    def test_enabled_chunk_keeps_name_nesting_and_single_undo(self):
        cmds.undoInfo(state=True)

        @undoChunk("mlibSpeedupOuter")
        def work(depth):
            cmds.setAttr(self.node + ".tx", depth)
            with undoChunk("inner"):
                cmds.setAttr(self.node + ".ty", depth)
            if depth < 3:
                work(depth + 1)

        work(1)
        self.assertEqual(cmds.undoInfo(query=True, undoName=True), "mlibSpeedupOuter")
        cmds.undo()
        self.assertEqual((cmds.getAttr(self.node + ".tx"), cmds.getAttr(self.node + ".ty")), (0.0, 0.0))
        with self.assertRaises(ValueError):
            with undoChunk("mlibSpeedupError"):
                cmds.setAttr(self.node + ".tz", 5)
                raise ValueError("primary")
        # 例外時も閉じているため、次の操作は別のUndo単位になる。
        cmds.setAttr(self.node + ".sx", 2)
        cmds.undo()
        self.assertEqual(cmds.getAttr(self.node + ".tz"), 5.0)
        self.assertEqual(cmds.undoInfo(query=True, undoName=True), "mlibSpeedupError")

    def test_disabled_undo_skips_open_and_close(self):
        cmds.undoInfo(state=False)
        calls = []
        original = cmds.undoInfo

        def spy(*args, **kwargs):
            calls.append(sorted(kwargs))
            return original(*args, **kwargs)

        from unittest import mock
        with mock.patch.object(mlib.decorator.cmds, "undoInfo", side_effect=spy):
            with undoChunk("mlibSpeedupOff"):
                with undoChunk("inner"):
                    cmds.setAttr(self.node + ".tx", 3)
        self.assertEqual(calls, [["query", "state"]])
        self.assertEqual(cmds.getAttr(self.node + ".tx"), 3.0)
        # undoTransactionは状態によらず従来どおり独立したチャンクを開閉する。名前付きの
        # 最も外側のundoTransactionは、内側のundoChunkの扱いを決めるため状態を1回問い合わせる。
        calls.clear()
        with mock.patch.object(mlib.decorator.cmds, "undoInfo", side_effect=spy):
            with undoTransaction("mlibSpeedupTx"):
                with undoChunk("inner"):
                    cmds.setAttr(self.node + ".ty", 4)
        self.assertEqual(calls, [["query", "state"], ["chunkName", "openChunk"], ["closeChunk"]])
        self.assertEqual(cmds.getAttr(self.node + ".ty"), 4.0)

    def test_connect_records_constant_only_when_undo_is_enabled(self):
        source = cmds.createNode("transform", name=self.node + "Src")
        try:
            cmds.undoInfo(state=True)
            cmds.setAttr(self.node + ".tx", 5)
            mlib.getNode(self.node).getPlug("tx").connect(mlib.getNode(source).getPlug("ty"))
            cmds.setAttr(source + ".ty", 2)
            self.assertEqual(cmds.getAttr(self.node + ".tx"), 2.0)
            cmds.undo()  # 接続元の値の変更を戻す。
            cmds.undo()  # 接続を戻すと、接続前の定数5へ戻る。
            self.assertFalse(cmds.isConnected(source + ".ty", self.node + ".tx"))
            self.assertEqual(cmds.getAttr(self.node + ".tx"), 5.0)
            cmds.undoInfo(state=False)
            target = mlib.getNode(self.node).getPlug("tx")
            self.assertIs(target.connect(mlib.getNode(source).getPlug("ty")), target)
            cmds.setAttr(source + ".ty", 3)
            self.assertEqual(cmds.getAttr(self.node + ".tx"), 3.0)
        finally:
            cmds.undoInfo(state=True)
            cmds.delete(source)


class DisconnectCreateDeleteTest(unittest.TestCase):
    """disconnect・作成・fast削除の高速化で、結果・例外・選択・Undoが変わらないことを確かめる。"""

    def setUp(self):
        self.ns = "mlibSpeedupR2_" + uuid.uuid4().hex
        cmds.namespace(add=self.ns)
        self.state = cmds.undoInfo(query=True, state=True)
        cmds.undoInfo(state=True)
        self.a = cmds.createNode("transform", name=self.ns + ":a")
        self.b = cmds.createNode("transform", name=self.ns + ":b")
        self.bs = cmds.createNode("blendShape", name=self.ns + ":bs")

    def tearDown(self):
        cmds.undoInfo(state=self.state)
        if cmds.namespace(exists=self.ns):
            for node in cmds.ls(self.ns + ":*", long=True) or []:
                if cmds.objExists(node) and cmds.lockNode(node, query=True, lock=True)[0]:
                    cmds.lockNode(node, lock=False)
            cmds.namespace(removeNamespace=self.ns, deleteNamespaceContent=True)

    def test_disconnect_child_element_compound(self):
        """子・配列要素・compoundの接続で、省略時と明示時の戻り値と切断結果が同じ。"""
        cmds.connectAttr(self.a + ".tx", self.b + ".tx")
        cmds.connectAttr(self.a + ".r", self.b + ".r")
        cmds.connectAttr(self.a + ".ty", self.bs + ".weight[3]")
        node_a, node_b, node_bs = mlib.getNode(self.a), mlib.getNode(self.b), mlib.getNode(self.bs)
        for fast in (False, True):
            for explicit in (False, True):
                cases = ((node_b.getPlug("tx"), "tx", self.b + ".tx"),
                         (node_b.getPlug("r"), "r", self.b + ".r"),
                         (node_bs.getPlug("weight[3]"), "ty", self.bs + ".weight[3]"))
                for plug, source_attr, destination in cases:
                    source = node_a.getPlug(source_attr)
                    result = plug.disconnect(source if explicit else None, fast=fast)
                    # 2026-10-26 の約束の変更で、src を渡した場合は渡した Plug そのものを返す
                    # (名前から取り直さない)。省略時は getSource で得た別の Plug になる。
                    if explicit:
                        self.assertIs(result, source)
                    else:
                        self.assertIsNot(result, source)
                    self.assertEqual(result.getFullName(), source.getFullName())
                    self.assertEqual(type(result), type(source))
                    self.assertFalse(cmds.isConnected(source.getFullName(), destination))
                    with self.assertRaisesRegex(RuntimeError, "Input connection not found"):
                        plug.disconnect(source if explicit else None, fast=fast)
                    cmds.connectAttr(source.getFullName(), destination)
        # compoundの子を入力元に指定しても、親同士の接続とは一致しない。
        with self.assertRaisesRegex(RuntimeError, "Input connection not found"):
            node_b.getPlug("r").disconnect(node_a.getPlug("rx"))
        self.assertTrue(cmds.isConnected(self.a + ".r", self.b + ".r"))

    def test_disconnect_lock_and_undo(self):
        """ロック中はforceの時だけ切断して再ロックし、1回のUndoで接続へ戻る。"""
        cmds.connectAttr(self.a + ".sy", self.b + ".sy")
        cmds.setAttr(self.b + ".sy", lock=True)
        plug = mlib.getNode(self.b).getPlug("sy")
        with self.assertRaisesRegex(RuntimeError, "locked"):
            plug.disconnect()
        self.assertTrue(cmds.isConnected(self.a + ".sy", self.b + ".sy"))
        plug.disconnect(f=True)
        self.assertFalse(cmds.isConnected(self.a + ".sy", self.b + ".sy"))
        self.assertTrue(cmds.getAttr(self.b + ".sy", lock=True))
        cmds.undo()
        self.assertTrue(cmds.isConnected(self.a + ".sy", self.b + ".sy"))
        self.assertTrue(cmds.getAttr(self.b + ".sy", lock=True))

    def test_create_fast_matches_named_resolution(self):
        """fast作成のラッパーは、名前から取り直した場合と同じノード・パス・型・選択になる。"""
        group = cmds.createNode("transform", name=self.ns + ":grp")
        cmds.select(clear=True)
        cases = (("transform", {}), ("mesh", {}), ("locator", {"parent": group}),
                 ("multiplyDivide", {"name": self.ns + ":md"}), ("joint", {}))
        for node_type, flags in cases:
            node = mlib.createNode(node_type, fast=True, **flags)
            resolved = mlib.getNode(node.getName())
            self.assertEqual(type(node), type(resolved))
            self.assertEqual(node.getFullName(), resolved.getFullName())
            self.assertEqual(cmds.ls(selection=True, long=True), [node.getFullName()])
            cmds.delete(node.getFullName() if node_type not in ("mesh",) else cmds.listRelatives(
                node.getFullName(), parent=True, fullPath=True))
        shared = mlib.createNode("multiplyDivide", name=self.ns + ":sh", fast=True)
        again = mlib.createNode("multiplyDivide", name=self.ns + ":sh", shared=True, skipSelect=True, fast=True)
        self.assertTrue(again.sameNode(shared))

    def test_fast_delete_parent_and_child(self):
        """fast削除で親子を両方渡しても、先行する親の下の子は重ねて検証しない。"""
        parent = cmds.createNode("transform", name=self.ns + ":p")
        child = cmds.createNode("transform", name=self.ns + ":pc", parent=parent)
        other = cmds.createNode("transform", name=self.ns + ":pcx")
        nodes = [mlib.getNode(name) for name in (parent, child, other)]
        mlib.delete(nodes, fast=True)
        self.assertFalse(any(node.isValid() for node in nodes))
        # 名前の接頭辞が同じだけの別ノード(pc と pcx)は子として扱わず、ロックを検出して何も消さない。
        parent = cmds.createNode("transform", name=self.ns + ":q")
        lookalike = cmds.createNode("transform", name=self.ns + ":qx")
        cmds.lockNode(lookalike, lock=True)
        nodes = [mlib.getNode(parent), mlib.getNode(lookalike)]
        with self.assertRaisesRegex(RuntimeError, "Node is locked or referenced"):
            mlib.delete(nodes, fast=True)
        self.assertTrue(all(node.isValid() for node in nodes))
        # 子がロックされていれば、子を後に渡しても親の検証で拒否する。
        child = cmds.createNode("transform", name=self.ns + ":qc", parent=parent)
        cmds.lockNode(child, lock=True)
        with self.assertRaisesRegex(RuntimeError, "Node is locked or referenced"):
            mlib.delete([mlib.getNode(parent), mlib.getNode(child)], fast=True)
        self.assertTrue(cmds.objExists(child))

    def test_delete_order_undo_and_lock(self):
        """通常削除は1回のcmds.deleteにまとめ、1回のUndoで戻り、ロックがあれば何も消さずに例外になる。

        2026-10-26 の約束の変更(削除の一括化)に合わせて直した。従来は渡した順に1個ずつ削除し、
        ロックで先行分だけ消えて止まることを確かめていた。削除の順はMayaがまとめて削除するときの
        順(この構成では dc→d0→dmd→d1→d2)になる。
        """
        names = [cmds.createNode("transform", name=self.ns + ":d" + str(i)) for i in range(3)]
        child = cmds.createNode("transform", name=self.ns + ":dc", parent=names[0])
        md = cmds.createNode("multiplyDivide", name=self.ns + ":dmd")
        cmds.connectAttr(md + ".outputX", names[1] + ".tx")
        cmds.connectAttr(names[2] + ".rx", names[1] + ".ty")  # unitConversionが連鎖して消える。
        removed = []
        callback = om2.MDGMessage.addNodeRemovedCallback(
            lambda obj, _data: removed.append(om2.MFnDependencyNode(obj).name()), "dependNode")
        try:
            before = sorted(cmds.ls(long=True))
            mlib.delete([mlib.getNode(child), mlib.getNode(md)] + [mlib.getNode(name) for name in names])
        finally:
            om2.MMessage.removeCallback(callback)
        short = [name.rpartition(":")[2] for name in removed]
        self.assertEqual([name for name in short if name.startswith("d")], ["dc", "d0", "dmd", "d1", "d2"])
        self.assertTrue(any(name.startswith("unitConversion") for name in short))
        self.assertEqual(cmds.undoInfo(query=True, undoName=True), "mlibDelete")
        cmds.undo()
        self.assertEqual(sorted(cmds.ls(long=True)), before)
        cmds.lockNode(names[1], lock=True)
        with self.assertRaisesRegex(RuntimeError, "Cannot delete locked node"):
            mlib.delete(names)
        self.assertEqual([cmds.objExists(name) for name in names], [True, True, True])


class LookupWrapperTest(unittest.TestCase):
    """ls・名前からの取得・階層の取得が、Node(...)・Plug._resolve_input と同じ参照を返すことを確かめる。"""

    def setUp(self):
        self.ns = "mlibSpeedLookup_" + uuid.uuid4().hex
        cmds.namespace(add=self.ns)
        cmds.namespace(set=self.ns)
        try:
            self.grp = cmds.createNode("transform", name="grp")
            self.a = cmds.createNode("transform", name="a", parent=self.grp)
            cmds.createNode("locator", name="aShape", parent=self.a)
            cmds.createNode("transform", name="aChild", parent=self.a)
            orig = cmds.createNode("locator", name="aShapeOrig", parent=self.a)
            cmds.setAttr(orig + ".intermediateObject", True)
            self.box = cmds.polyCube(name="box", constructionHistory=False)[0]
            self.g2 = cmds.createNode("transform", name="g2")
            cmds.parent(cmds.instance(self.box)[0], self.g2)
            cmds.createNode("transform", name="dupl", parent=self.grp)
            cmds.createNode("transform", name="dupl", parent=self.g2)
            self.md = cmds.createNode("multiplyDivide", name="md")
            cmds.aliasAttr("myAlias", self.md + ".input1X")
            plane = cmds.nurbsPlane(name="plane", constructionHistory=False)[0]
            self.cos = cmds.curveOnSurface(plane, uv=[(0.1, 0.1), (0.5, 0.5), (0.9, 0.2)], name="cos")
        finally:
            cmds.namespace(set=":")

    def tearDown(self):
        cmds.namespace(removeNamespace=self.ns, deleteNamespaceContent=True)

    def _describe(self, item):
        path = item.mpath().fullPathName() if hasattr(item, "mpath") else None
        if isinstance(item, mlib.plugs.Plug):
            node = item.getNode()
            path = node.mpath().fullPathName() if hasattr(node, "mpath") else None
        return type(item), item.getFullName(), path

    def test_ls_matches_individual_resolution(self):
        from mlib.common.selection import Selection
        from mlib.nodes.node import Node
        from mlib.plugs.plug import Plug
        ns = self.ns + ":"
        names = [ns + "box", ns + "md", ns + "box", "|" + ns + "g2|" + ns + "box1",
                 ns + "md.myAlias", ns + "md.input1", ns + "box.tx", ns + "boxShape.worldMatrix[1]",
                 "|" + ns + "g2|" + ns + "box1|" + ns + "boxShape.castsShadows", "|" + ns + "g2|" + ns + "box1.castsShadows",
                 ns + "boxShape.pnts[0]", ns + "box.vtx[0:2]", ns + "aShapeOrig", ns + "cos"]
        expected = []
        for name in cmds.ls(names):
            if "." not in name:
                expected.append(Node(name))
                continue
            items = Selection(name).items
            expected.extend(items if isinstance(items[0], mlib.components.Component) else [Plug._resolve_input(name)])
        result = mlib.ls(names)
        self.assertEqual([self._describe(item) for item in result], [self._describe(item) for item in expected])
        self.assertEqual(result, expected)

    def test_get_node_and_plug_match_constructors(self):
        from mlib.nodes.node import Node
        from mlib.plugs.plug import Plug
        ns = self.ns + ":"
        for name in [ns + "box", "|" + ns + "g2|" + ns + "box1", ns + "boxShape", ns + "md", ns + "md.input1X", ns + "box.vtx[0]", ns + "cos"]:
            self.assertEqual(self._describe(mlib.getNode(name)), self._describe(Node(name)), name)
        for name in [ns + "nothing", ns + "dupl", ""]:
            with self.assertRaises(RuntimeError) as expected:
                Node(name)
            with self.assertRaises(RuntimeError) as actual:
                mlib.getNode(name)
            self.assertEqual(str(actual.exception), str(expected.exception))
            with self.assertRaises(RuntimeError) as bulk:
                mlib.nodes.Nodes([ns + "box", name])
            self.assertEqual(str(bulk.exception), str(expected.exception))
        names = [ns + "box", ns + "md", ns + "box", "|" + ns + "g2|" + ns + "box1", ns + "boxShape"]
        self.assertEqual([self._describe(item) for item in mlib.nodes.Nodes(names)],
                         [self._describe(Node(name)) for name in names[:2] + names[3:]])  # 同じノードは最初だけ
        for name, owner in [(ns + "box.tx", "|" + ns + "box"), (ns + "md.myAlias", None),
                            ("|" + ns + "g2|" + ns + "box1|" + ns + "boxShape.castsShadows",
                             "|" + ns + "g2|" + ns + "box1|" + ns + "boxShape"),
                            ("|" + ns + "g2|" + ns + "box1.castsShadows", "|" + ns + "g2|" + ns + "box1|" + ns + "boxShape"),
                            (ns + "aShape.visibility", "|" + ns + "grp|" + ns + "a|" + ns + "aShape")]:
            plug = mlib.getPlug(name)
            self.assertEqual(self._describe(plug)[2], owner, name)
            selection = om2.MSelectionList()
            selection.add(name)
            self.assertEqual(Node._selection_owner(selection, 0, name, plug=True), Node._selection_owner(selection, 0, name))
            self.assertEqual(plug.getFullName(), Plug._resolve_input(name).getFullName())

    def test_hierarchy_wrappers(self):
        from mlib.nodes.node import Node
        ns = self.ns + ":"
        a = mlib.getNode(self.a)
        shapes = a.getShapes()
        self.assertEqual([shape.getFullName() for shape in shapes], ["|" + ns + "grp|" + ns + "a|" + ns + "aShape"])
        self.assertEqual([shape.getFullName() for shape in a.getShapes(intermediates=True)],
                         cmds.listRelatives(self.a, shapes=True, fullPath=True))
        self.assertEqual(type(shapes[0]), type(Node(shapes[0].getFullName())))
        self.assertIsNone(mlib.getNode(self.grp).getShape())
        parent = a.getParent()
        self.assertEqual((type(parent), parent.getFullName()), (type(Node(self.grp)), "|" + ns + "grp"))
        shape = mlib.getNode("|" + ns + "g2|" + ns + "box1|" + ns + "boxShape")
        self.assertEqual(shape.getParent().mpath().fullPathName(), "|" + ns + "g2|" + ns + "box1")
        self.assertEqual(sorted(item.mpath().fullPathName() for item in shape.getInstances()),
                         sorted(cmds.ls(ns + "boxShape", allPaths=True, long=True)))
        # アンダーワールドの根まで遡るパスは、従来どおり Node(無効なパス) と同じ例外にする。
        curve = mlib.getNode(self.cos)
        with self.assertRaisesRegex(RuntimeError, "MDagPath"):
            curve.getParent()


class CollectionWrapperTest(unittest.TestCase):
    """Nodesの重複判定と、API列挙の結果から直接作るラッパーが従来と同じ結果になることを確認する。"""

    def setUp(self):
        self.ns = "mlibSpeedupColl_" + uuid.uuid4().hex[:8]
        cmds.namespace(add=self.ns)
        cmds.namespace(set=self.ns)
        try:
            self.box = cmds.polyCube(name="box")[0]
            self.g2 = cmds.createNode("transform", name="g2")
            cmds.parent(cmds.instance(self.box)[0], self.g2)
            self.md = cmds.createNode("multiplyDivide", name="md")
            cmds.select(clear=True)
            self.joints = [cmds.joint(name="j{}".format(i)) for i in range(3)]
            self.ball = cmds.polySphere(name="ball")[0]
            self.skin = cmds.skinCluster(self.joints, self.ball, toSelectedBones=True)[0]
            self.layer = cmds.createDisplayLayer(name="layer", empty=True)
            cmds.editDisplayLayerMembers(self.layer, self.box, self.g2, noRecurse=True)
            self.sg = cmds.sets(renderable=True, noSurfaceShader=True, empty=True, name="sg")
            self.instance_shape = cmds.ls(self.ns + ":boxShape", allPaths=True, long=True)[-1]
            cmds.sets(self.instance_shape, edit=True, forceElement=self.sg)
            cmds.sets(self.ball + ".f[0:1]", edit=True, forceElement=self.sg)
        finally:
            cmds.namespace(set=":")

    def tearDown(self):
        cmds.namespace(removeNamespace=self.ns, deleteNamespaceContent=True)

    def test_nodes_duplicates_match_uuid_and_path_keys(self):
        from mlib.nodes import Joints, Nodes
        from mlib.nodes.node import Node
        paths = cmds.ls(self.ns + ":boxShape", allPaths=True, long=True)
        names = [self.md, self.box, self.md] + paths + paths[::-1] + self.joints + [self.joints[0]]
        wrappers = [Node(name) for name in names]
        self.assertEqual([node.getFullName() for node in Nodes(names)], self._expected_unique(wrappers))
        self.assertEqual([node.getFullName() for node in Nodes(wrappers)], self._expected_unique(wrappers))
        # 同じノードの別ラッパーは同じ要素として1つにまとめ、最初の参照を保持する。
        first = Node(self.md)
        collected = Nodes([first, Node(self.md)])
        self.assertEqual(len(collected), 1)
        self.assertIs(collected[0], first)
        # 同じノードの別インスタンスは別要素として残す。
        self.assertEqual(len(Nodes(paths + paths)), len(paths))
        full = cmds.ls(self.joints, long=True)
        self.assertEqual([node.getFullName() for node in Joints(full + full)], full)
        with self.assertRaisesRegex(TypeError, "Joints requires Joint, got MultiplyDivide"):
            Joints(self.joints + [self.md])

    def test_nodes_reject_removed_instance_without_duplicates(self):
        from mlib.nodes import Nodes
        holder = cmds.createNode("transform", name=self.ns + ":holder")
        cmds.parent(cmds.instance(self.box)[0], holder)
        wrappers = [mlib.getNode(path) for path in cmds.ls(self.ns + ":boxShape", allPaths=True, long=True)]
        cmds.delete(holder)
        # 重複が無くても、保持インスタンスの消えた参照は従来どおり例外にする。
        with self.assertRaisesRegex(RuntimeError, "The referenced DAG instance no longer exists"):
            Nodes(wrappers)

    def test_api_listing_wrappers_match_node_construction(self):
        from mlib.nodes.node import Node
        skin = mlib.getNode(self.skin)
        influences = skin.getInfluences()
        self.assertEqual([(type(node), node.getFullName()) for node in influences],
                         [(type(Node(name)), name) for name in cmds.ls(self.joints, long=True)])
        unused = skin.getUnusedInfluences()
        self.assertTrue(all(type(node) is type(Node(node.getFullName())) for node in unused))
        skin.addInfluences(self.joints[:1])
        self.assertEqual(len(skin.getInfluences()), len(self.joints))
        members = mlib.getNode(self.layer).getMembers()
        expected = cmds.editDisplayLayerMembers(self.layer, query=True, fullNames=True)
        self.assertEqual(sorted((type(node).__name__, node.getFullName()) for node in members),
                         sorted((type(Node(name)).__name__, name) for name in expected))
        sg_members = mlib.getNode(self.sg).getMembers()
        shapes = [item for item in sg_members if isinstance(item, Node)]
        self.assertEqual([(type(node), node.mpath().fullPathName()) for node in shapes],
                         [(type(Node(self.instance_shape)), self.instance_shape)])
        faces = [item for item in sg_members if not isinstance(item, Node)]
        self.assertEqual(sorted(face.index for face in faces), [0, 1])

    def _expected_unique(self, nodes):
        """従来の (UUID, 完全パス) の集合による重複除去の結果を返す。"""
        result, seen = [], set()
        for node in nodes:
            key = (node.getUuid(), node.getFullName())
            if key not in seen:
                seen.add(key)
                result.append(node.getFullName())
        return result


class UndoTransactionNestingTest(unittest.TestCase):
    """名前付きundoTransactionの内側のundoChunkを開かなくても、Undoの単位・名前・巻戻しが同じことを確かめる。"""

    def setUp(self):
        self.state = cmds.undoInfo(query=True, state=True)
        cmds.undoInfo(state=True)
        self.node = cmds.createNode("transform", name="mlibSpeedupTx_" + uuid.uuid4().hex)
        self.created = []

    def tearDown(self):
        cmds.undoInfo(state=self.state)
        for name in [self.node] + self.created:
            if cmds.objExists(name):
                cmds.delete(name)

    def test_named_transaction_opens_only_its_own_chunks(self):
        from unittest import mock
        from mlib.decorator import _chunk_active
        names = []
        original = cmds.undoInfo

        def spy(*args, **kwargs):
            if kwargs.get("openChunk"):
                names.append(kwargs.get("chunkName"))
            return original(*args, **kwargs)

        node = mlib.getNode(self.node)
        cmds.setAttr(self.node + ".tx", 5)
        with mock.patch.object(mlib.decorator.cmds, "undoInfo", side_effect=spy):
            with undoTransaction("mlibSpeedupOuterTx"):
                node.getPlug("scale").set((1, 2, 3))
                with undoChunk("inner"):
                    md = mlib.createNode("multiplyDivide")
                    self.created.append(md.getFullName())
                    node.getPlug("tx").connect(md.getPlug("input1X"))
                with undoTransaction("mlibSpeedupInnerTx"):
                    node.getPlug("rx").set(0.5)
        # 入れ子のundoTransactionは独立したチャンクを維持し、undoChunkだけ開かない。
        self.assertEqual(names, ["mlibSpeedupOuterTx", "mlibSpeedupInnerTx"])
        self.assertIs(_chunk_active.get(), False)
        self.assertEqual(cmds.undoInfo(query=True, undoName=True), "mlibSpeedupOuterTx")
        cmds.undo()
        # 1回のUndoで全体が戻り、接続前の定数5の記録も外側のチャンク内で従来どおり働く。
        self.assertFalse(cmds.objExists(self.created[0]))
        self.assertEqual(cmds.getAttr(self.node + ".scale")[0], (1.0, 1.0, 1.0))
        self.assertEqual(cmds.getAttr(self.node + ".rx"), 0.0)
        self.assertEqual(cmds.getAttr(self.node + ".tx"), 5.0)
        cmds.redo()
        self.assertTrue(cmds.isConnected(self.created[0] + ".input1X", self.node + ".tx"))
        self.assertEqual(cmds.getAttr(self.node + ".scale")[0], (1.0, 2.0, 3.0))
        self.assertAlmostEqual(cmds.getAttr(self.node + ".rx"), 28.64788975654116)  # 0.5 rad を度で読む

    def test_unnamed_transaction_keeps_inner_chunk_name(self):
        # 名前を省略したundoTransactionは、最初の内側のチャンク名がUndoの表示名になる(従来どおり)。
        with undoTransaction():
            mlib.getNode(self.node).getPlug("tx").set(2)
            cmds.setAttr(self.node + ".ty", 3)
        self.assertEqual(cmds.undoInfo(query=True, undoName=True), "mlibDoubleLinearPlugSet")
        cmds.undo()
        self.assertEqual((cmds.getAttr(self.node + ".tx"), cmds.getAttr(self.node + ".ty")), (0.0, 0.0))

    def test_rollback_and_disabled_state(self):
        from mlib.decorator import _chunk_active, _undo_recording
        node = mlib.getNode(self.node)
        node.getPlug("sx").set(4)
        with self.assertRaisesRegex(ValueError, "primary"):
            with undoTransaction("mlibSpeedupFailTx"):
                node.getPlug("tx").set(7)
                with undoChunk("inner"):
                    node.getPlug("ty").set(8)
                raise ValueError("primary")
        # ブロック内だけ戻り、直前の別操作は残る。
        self.assertEqual((cmds.getAttr(self.node + ".tx"), cmds.getAttr(self.node + ".ty")), (0.0, 0.0))
        self.assertEqual(cmds.getAttr(self.node + ".sx"), 4.0)
        self.assertIs(_chunk_active.get(), False)
        cmds.undoInfo(state=False)
        with undoTransaction("mlibSpeedupOffTx"):
            self.assertFalse(_undo_recording())
            with undoChunk("inner"):
                node.getPlug("tz").set(6)
        self.assertEqual(cmds.getAttr(self.node + ".tz"), 6.0)
        self.assertIs(_chunk_active.get(), False)


class ArrayAndWeightRunTest(unittest.TestCase):
    """ArrayPlug.getの要素ラッパー省略、targetWeightsの範囲setAttr、Vectorの複製省略が従来と同じ結果になることを確かめる。"""

    def setUp(self):
        self.ns = "mlibSpeedupArr_" + uuid.uuid4().hex
        cmds.namespace(add=self.ns)
        self.state = cmds.undoInfo(query=True, state=True)
        cmds.undoInfo(state=True)
        self.units = (cmds.currentUnit(query=True, linear=True), cmds.currentUnit(query=True, angle=True))

    def tearDown(self):
        cmds.currentUnit(linear=self.units[0], angle=self.units[1])
        cmds.undoInfo(state=self.state)
        if cmds.namespace(exists=self.ns):
            cmds.namespace(removeNamespace=self.ns, deleteNamespaceContent=True)

    def test_array_get_matches_element_get(self):
        node = cmds.createNode("transform", name=self.ns + ":arr")
        specs = {"dbl": dict(attributeType="double"), "lng": dict(attributeType="long"),
                 "enm": dict(attributeType="enum", enumName="a:b:c"), "dst": dict(attributeType="doubleLinear"),
                 "ang": dict(attributeType="doubleAngle"), "mtx": dict(attributeType="matrix"),
                 "mss": dict(attributeType="message"), "str": dict(dataType="string"), "empty": dict(attributeType="double")}
        for name, flags in specs.items():
            cmds.addAttr(node, longName=name, multi=True, **flags)
        for i in (0, 3, 9):
            cmds.setAttr(f"{node}.dbl[{i}]", i * 1.5)
            cmds.setAttr(f"{node}.lng[{i}]", i)
            cmds.setAttr(f"{node}.enm[{i}]", i % 3)
            cmds.setAttr(f"{node}.dst[{i}]", i * 2.0)
            cmds.setAttr(f"{node}.ang[{i}]", i * 0.1)
            cmds.setAttr(f"{node}.mtx[{i}]", [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, i, 0, 0, 1], type="matrix")
            cmds.setAttr(f"{node}.str[{i}]", f"s{i}", type="string")
        src = cmds.createNode("transform", name=self.ns + ":src")
        cmds.setAttr(src + ".tx", 4.5)
        cmds.connectAttr(src + ".tx", node + ".dbl[5]")
        cmds.connectAttr(src + ".message", node + ".mss[1]")
        cmds.currentUnit(linear="mm", angle="deg")
        wrapped = mlib.getNode(node)
        for name in specs:
            array = wrapped.getPlug(name)
            for ui in (False, True):
                expected = {}
                error = None
                try:
                    for element in [array[i] for i in array.getIndices()]:
                        expected[element.mplug().logicalIndex()] = element.get(uiUnits=ui)
                except RuntimeError as exc:
                    error = str(exc)
                if error is not None:
                    with self.assertRaises(RuntimeError) as caught:
                        array.get(uiUnits=ui)
                    self.assertEqual(str(caught.exception), error)
                    continue
                actual = array.get(uiUnits=ui)
                self.assertEqual(list(actual), list(expected), name)
                self.assertEqual([type(v) for v in actual.values()], [type(v) for v in expected.values()], name)
                self.assertEqual(actual, expected, name)
        self.assertEqual(wrapped.getPlug("dbl").get()[5], 4.5)
        self.assertAlmostEqual(wrapped.getPlug("dst").get(uiUnits=True)[3], 60.0)
        self.assertEqual(wrapped.getPlug("empty").get(), {})
        with self.assertRaises(TypeError):
            wrapped.getPlug("dbl").get(uiUnits=1)
        # 削除済みアトリビュート・ノードは従来どおりRuntimeError。
        array = wrapped.getPlug("lng")
        cmds.deleteAttr(node + ".lng")
        with self.assertRaisesRegex(RuntimeError, "attribute was deleted"):
            array.get()

    def test_array_get_world_space_instances(self):
        loc = cmds.spaceLocator(name=self.ns + ":loc")[0]
        grp = cmds.group(loc, name=self.ns + ":grp")
        cmds.instance(grp, name=self.ns + ":grp2")
        shape = mlib.getNode(cmds.listRelatives(loc, shapes=True, fullPath=True)[0])
        for name in ("worldMatrix", "worldPosition", "worldInverseMatrix"):
            array = shape.getPlug(name)
            actual = array.get()
            expected = {plug.mplug().logicalIndex(): plug.get() for plug in array.getElements()}
            self.assertEqual(list(actual), [0, 1])
            self.assertEqual(actual, expected)

    def test_target_weights_runs_keep_order_undo_and_errors(self):
        node, path = self._blend_shape()
        sets = []

        def callback(message, plug, other, data):
            if message & om2.MNodeMessage.kAttributeSet:
                sets.append(plug.logicalIndex())
        cid = om2.MNodeMessage.addAttributeChangedCallback(node.mnode(), callback)
        try:
            node.setTargetWeights(0, {7: 0.1, 5: 0.2, 6: 0.3, 2: 0.4, 3: 0.5, 24: 0.6})
        finally:
            om2.MMessage.removeCallback(cid)
        # 指定順の書込み(連続区間でも要素ごとの属性変更通知が同じ順に出る)。
        self.assertEqual(sets, [7, 5, 6, 2, 3, 24])
        weights = dict(self._weights(path))
        for index, value in ((7, 0.1), (5, 0.2), (6, 0.3), (2, 0.4), (3, 0.5), (24, 0.6), (4, 0.9)):
            self.assertAlmostEqual(weights[index], value, places=6)
        self.assertEqual(cmds.undoInfo(query=True, undoName=True), "mlibBlendShapeSetTargetWeights")
        cmds.undo()
        self.assertTrue(all(abs(v - 0.9) < 1e-6 for _, v in self._weights(path)))
        cmds.redo()
        self.assertAlmostEqual(cmds.getAttr(path + "[24]"), 0.6, places=6)
        # 全頂点列。範囲内のロックは手前まで書いて、その要素のMayaのエラー。
        cmds.setAttr(path + "[6]", lock=True)
        with self.assertRaisesRegex(RuntimeError, r"targetWeights\[6\]"):
            node.setTargetWeights(0, [i / 25.0 for i in range(25)])
        self.assertAlmostEqual(cmds.getAttr(path + "[5]"), 5 / 25.0, places=6)
        self.assertAlmostEqual(cmds.getAttr(path + "[7]"), 0.1, places=6)
        self.assertAlmostEqual(cmds.getAttr(path + "[8]"), 0.9, places=6)
        cmds.setAttr(path + "[6]", lock=False)
        # 入力接続も同じ扱い。
        driver = cmds.createNode("transform", name=self.ns + ":drv")
        cmds.connectAttr(driver + ".tx", path + "[4]")
        with self.assertRaisesRegex(RuntimeError, r"targetWeights\[4\]"):
            node.setTargetWeights(0, {2: 0.11, 3: 0.12, 4: 0.13, 5: 0.14})
        self.assertAlmostEqual(cmds.getAttr(path + "[3]"), 0.12, places=6)
        self.assertAlmostEqual(cmds.getAttr(path + "[5]"), 5 / 25.0, places=6)
        # 空辞書は配列を解決せず何もしない。検証の失敗は書込み前。
        before = self._weights(path)
        node.setTargetWeights(0, {})
        with self.assertRaises(ValueError):
            node.setTargetWeights(0, [0.5] * 24)
        self.assertEqual(self._weights(path), before)

    def test_vector_copies_are_base_vectors(self):
        from mlib.maths import EulerRotate, Matrix, Quaternion, Vector

        class Sub(Vector):
            pass

        matrix = Matrix.compose(translate=(1, 2, 3), rotate=(0.1, 0.2, 0.3), scale=(1, 2, 3))
        quat = Quaternion(0.1, 0.2, 0.3, 0.9)
        for vector in (Sub(1, 2, 3), Vector(-0.0, 0.0, -0.0), Vector(0, 0, 0)):
            raw = om2.MVector(vector)
            for result, expected in ((vector.normal(), raw.normal()), (vector.rotateBy(quat), raw.rotateBy(quat)),
                                     (vector.rotateBy(EulerRotate(0.1, 0.2, 0.3)), raw.rotateBy(om2.MEulerRotation(0.1, 0.2, 0.3))),
                                     (vector.transformAsNormal(matrix), raw.transformAsNormal(om2.MMatrix(matrix)))):
                self.assertIs(type(result), Vector)
                self.assertEqual([repr(v) for v in result], [repr(v) for v in expected])
        with self.assertRaises((TypeError, ValueError)):
            Vector(1, 2, 3).rotateBy("x")

    def test_vertex_normals_match_vector_construction(self):
        from mlib.maths import Vector
        plane = cmds.polyPlane(subdivisionsX=3, subdivisionsY=3, name=self.ns + ":nrm")[0]
        cmds.move(0, 0.5, 0, plane + ".vtx[5]", relative=True)
        cmds.rotate(0, 0, 30, plane)
        shape = mlib.getNode(cmds.listRelatives(plane, shapes=True, fullPath=True)[0])
        for world in (False, True):
            for weighted in (False, True):
                space = om2.MSpace.kWorld if world else om2.MSpace.kObject
                raw = shape.mfn().getVertexNormals(weighted, space)
                actual = shape.getVertexNormals(worldSpace=world, angleWeighted=weighted)
                self.assertEqual([type(v) for v in actual], [Vector] * len(raw))
                self.assertEqual([tuple(map(repr, v)) for v in actual],
                                 [tuple(map(repr, Vector(v))) for v in raw])

    def test_component_quaternion_static_read(self):
        cmds.select(clear=True)
        joint = cmds.joint(name=self.ns + ":jnt")
        cmds.setAttr(joint + ".jo", 10, 20, 30)
        cmds.setAttr(joint + ".ra", 5, -5, 15)
        cmds.setAttr(joint + ".r", 40, 50, 60)
        cmds.setAttr(joint + ".ro", 4)
        plain = cmds.createNode("transform", name=self.ns + ":plain")
        cmds.setAttr(plain + ".ra", 1, 2, 3)
        cmds.setAttr(plain + ".spt", 0.1, -0.2, 0.3)
        for name in (joint, plain):
            node = mlib.getNode(name)
            for attr in ("rotate", "rotateAxis", "jointOrient"):
                order = node._rotate_order() if attr == "rotate" else om2.MEulerRotation.kXYZ
                try:
                    expected = om2.MEulerRotation(*tuple(node.getPlug(attr).get()), order).asQuaternion()
                except Exception as exc:  # noqa: BLE001
                    with self.assertRaises(type(exc)) as caught:
                        node._component_quaternion(attr)
                    self.assertEqual(str(caught.exception), str(exc))
                    continue
                actual = node._component_quaternion(attr)
                self.assertEqual([repr(v) for v in actual], [repr(v) for v in expected], (name, attr))
            values = node.setMatrix(node.getMatrix(), get=True)
            self.assertEqual(list(values), ["translate", "rotate", "scale", "shear"])
            for channel in ("translate", "scale", "shear"):
                for got, current in zip(values[channel], node.getPlug(channel).get()):
                    self.assertAlmostEqual(got, current, places=9)

    def _blend_shape(self):
        base = cmds.polyPlane(subdivisionsX=4, subdivisionsY=4, name=self.ns + ":base")[0]
        target = cmds.duplicate(base, name=self.ns + ":tg")[0]
        bs = cmds.blendShape(target, base, name=self.ns + ":bs")[0]
        path = bs + ".inputTarget[0].inputTargetGroup[0].targetWeights"
        cmds.setAttr(path + "[0:24]", *([0.9] * 25))
        return mlib.getNode(bs), path

    def _weights(self, path):
        return [(i, cmds.getAttr(f"{path}[{i}]")) for i in cmds.getAttr(path, multiIndices=True)]


class TransformationAndAnimKeyTest(unittest.TestCase):
    """Transformationの合成・コピーと、AnimCurveの単位変換の内部経路が従来の公開APIの計算と同じ値になることを確かめる。"""

    def setUp(self):
        self.ns = "speedupR7_" + uuid.uuid4().hex[:8]
        cmds.namespace(add=self.ns)
        self.units = (cmds.currentUnit(query=True, linear=True), cmds.currentUnit(query=True, angle=True),
                      cmds.currentUnit(query=True, time=True))

    def tearDown(self):
        cmds.currentUnit(linear=self.units[0], angle=self.units[1], time=self.units[2])
        if cmds.namespace(exists=self.ns):
            cmds.namespace(removeNamespace=self.ns, deleteNamespaceContent=True)

    def test_compose_matches_public_operations(self):
        """matrixの合成が、従来の式(公開のMatrix/Quaternion演算)とビット単位で一致する。"""
        for t in self._random_transformations():
            self.assertEqual(self._hex(t.matrix), self._hex(self._reference_matrix(t)), repr(t))

    def test_copy_and_defaults(self):
        """コピーは同じ並び・型・値で成分を共有せず、既定値はコンストラクタの既定値と同じ。"""
        from mlib.maths import EulerRotate, Quaternion, Scale, Shear, Transformation, Translate
        for t in self._random_transformations(50):
            c = t.copy()
            self.assertEqual(list(c._values), list(t._values))
            for name, value in t._values.items():
                copied = c._values[name]
                if isinstance(value, bool):
                    self.assertIs(copied, value)
                    continue
                self.assertIsNot(copied, value, name)
                self.assertIs(type(copied), type(value), name)
                self.assertEqual(self._hex(copied), self._hex(value), name)
                if isinstance(value, om2.MEulerRotation):
                    self.assertEqual(copied.order, value.order)
            self.assertEqual(repr(c), repr(t))
            self.assertTrue(c == t)
        default = Transformation()
        expected = {"translate": Translate(), "rotate": EulerRotate(), "scale": Scale((1, 1, 1)), "shear": Shear(),
                    "rotateAxis": Quaternion(), "jointOrient": Quaternion(), "rotatePivot": Translate(),
                    "rotatePivotTranslate": Translate(), "scalePivot": Translate(), "scalePivotTranslate": Translate(),
                    "inverseScale": Scale((1, 1, 1))}
        self.assertEqual(list(default._values), list(expected) + ["segmentScaleCompensate"])
        for name, value in expected.items():
            self.assertIs(type(default._values[name]), type(value))
            self.assertEqual(self._hex(default._values[name]), self._hex(value), name)
        self.assertEqual(default.rotate.order, 0)

    def test_compose_errors(self):
        """非有限の成分とSSC有効時のゼロのinverseScaleは従来と同じ例外になる。"""
        from mlib.maths import Transformation
        t = Transformation(translate=(1, 2, 3))
        t.translate.x = float("nan")
        with self.assertRaises(ValueError) as caught:
            t.matrix  # noqa: B018
        self.assertEqual(str(caught.exception), "Transformation components must be finite")
        t = Transformation()
        t.rotateAxis.w = float("inf")
        with self.assertRaises(ValueError) as caught:
            t.matrix  # noqa: B018
        self.assertEqual(str(caught.exception), "Transformation components must be finite")
        t = Transformation(inverseScale=(1, 0, 1))
        with self.assertRaises(ValueError) as caught:
            t.matrix  # noqa: B018
        self.assertEqual(str(caught.exception), "inverseScale must be nonzero while SSC is enabled")
        t.segmentScaleCompensate = False
        self.assertEqual(self._hex(t.matrix), self._hex(self._reference_matrix(t)))

    def test_anim_unit_value_matches_get_plug(self):
        """AnimCurveの単位変換がgetPlug(...).mplug()を使った変換と同じ値で、削除済みでは同じ例外になる。"""
        from mlib.core.attributeType import _convert_units
        for linear, angle in (("cm", "rad"), ("mm", "deg")):
            cmds.currentUnit(linear=linear, angle=angle)
            for kind in ("animCurveTL", "animCurveTA", "animCurveTU", "animCurveTT", "animCurveUL", "animCurveUA"):
                node = mlib.getNode(cmds.createNode(kind, name=self.ns + ":" + kind))
                for output in (False, True):
                    for to_ui in (True, False):
                        name = "output" if output else "input"
                        expected = _convert_units(node.getPlug(name).mplug(), 1.25, to_ui)
                        self.assertEqual(node._unit_value(1.25, output, to_ui), expected, (kind, name, to_ui))
                node.setKey(2.0, 0.5)
                self.assertEqual(node.getKeyCount(), 1)
        node = mlib.getNode(cmds.createNode("animCurveTL", name=self.ns + ":deleted"))
        cmds.delete(str(node))
        with self.assertRaises(RuntimeError) as expected:
            node.getPlug("input")
        with self.assertRaises(RuntimeError) as caught:
            node.setKey(1.0, 1.0)
        self.assertEqual(str(caught.exception), str(expected.exception))

    @staticmethod
    def _hex(values):
        return [float(v).hex() for v in values]

    @staticmethod
    def _reference_matrix(t):
        """従来の_composeと同じ式を、公開のMatrix・Quaternionの演算で計算する。"""
        from mlib.maths import Matrix
        sp, rp = t.scalePivot, t.rotatePivot
        rotation = t.rotateAxis * t.quaternion * t.jointOrient
        compensation = Matrix(scale=tuple(1.0 / v for v in t.inverseScale)) if t.ssc else Matrix()
        return (Matrix(translate=-sp) * Matrix(scale=t.scale, shear=t.shear)
                * Matrix(translate=sp + t.scalePivotTranslate - rp)
                * Matrix(rotate=rotation) * Matrix(translate=rp + t.rotatePivotTranslate)
                * compensation * Matrix(translate=t.translate))

    def _random_transformations(self, count=200):
        import random
        from mlib.maths import Quaternion, Transformation
        rng = random.Random(7)

        def vec(scale):
            return tuple(rng.uniform(-scale, scale) for _ in range(3))

        def scale():
            return tuple(rng.choice([rng.uniform(0.1, 3), -rng.uniform(0.1, 3), -1.0, 1.0]) for _ in range(3))
        result = [Transformation(), Transformation(translate=(-0.0, 0.0, -0.0), scale=(-1, -1, 1))]
        for _ in range(count):
            kwargs = dict(rotateOrder=rng.randrange(6), rotate=vec(7), translate=vec(10), scale=scale(), shear=vec(1),
                          rotatePivot=vec(3), rotatePivotTranslate=vec(3), scalePivot=vec(3), scalePivotTranslate=vec(3),
                          rotateAxis=Quaternion(*(rng.uniform(-1, 1) for _ in range(4))),
                          jointOrient=Quaternion(*(rng.uniform(-1, 1) for _ in range(4))))
            if rng.random() < 0.5:
                kwargs["inverseScale"] = scale()
            else:
                kwargs["segmentScaleCompensate"] = rng.random() < 0.5
            result.append(Transformation(**kwargs))
        return result


class FastPathOverheadTest(unittest.TestCase):
    """fast=Trueの経路で検査の重複を省いても、検査の順序・例外・戻り値・Undoの扱いが変わらないことを確かめる。"""

    def setUp(self):
        self.ns = "speedupR8_" + uuid.uuid4().hex[:8]
        cmds.namespace(add=self.ns)
        self.undo_state = cmds.undoInfo(query=True, state=True)

    def tearDown(self):
        cmds.undoInfo(state=self.undo_state)
        if cmds.namespace(exists=self.ns):
            cmds.namespace(removeNamespace=self.ns, deleteNamespaceContent=True)

    def test_double3_fast_checks_writable_once_in_order(self):
        from unittest import mock
        from mlib.core import fastWrite
        node = self._double3_node("d3")
        plug = mlib.getNode(node).getPlug("dv")
        cmds.flushUndo()
        with mock.patch.object(fastWrite, "require_writable", wraps=fastWrite.require_writable) as spy:
            plug.set((0.25, 1.5, -2.0), fast=True)
        # 親と3つの子を1回ずつ。検査の後に型・範囲を確かめて書き込む。
        self.assertEqual(spy.call_count, 4)
        self.assertEqual(cmds.getAttr(node + ".dv")[0], (0.25, 1.5, -2.0))
        self.assertEqual(cmds.undoInfo(query=True, undoName=True), "")
        # 書込み可否は全子を範囲より先に調べる(X の範囲外より Y のロックが先)。
        cmds.addAttr(node + ".dvX", edit=True, maxValue=0.5)
        cmds.setAttr(node + ".dvY", lock=True)
        with self.assertRaises(RuntimeError) as caught:
            plug.set((1.0, 0.0, 0.0), fast=True)
        self.assertRegex(str(caught.exception), r"^Attribute is locked or connected: \S+\.dvY$")
        cmds.setAttr(node + ".dvY", lock=False)
        with self.assertRaises(RuntimeError) as caught:
            plug.set((1.0, 0.0, 0.0), fast=True)
        self.assertRegex(str(caught.exception), r"^Value outside attribute limits: \S+\.dvX$")
        self.assertEqual(cmds.getAttr(node + ".dv")[0], (0.25, 1.5, -2.0))
        self.assertEqual(plug.set((0.5, 2.0, 3.0), safe=True, fast=True), 0)
        self.assertIs(plug.set((0.5, 2.0, 3.0), fast=True), plug)
        with self.assertRaises(ValueError):
            plug.set((1.0, 2.0), fast=True)

    def test_connect_fast_message_and_return(self):
        a = cmds.createNode("transform", name=self.ns + ":a")
        b = cmds.createNode("transform", name=self.ns + ":b")
        c = cmds.createNode("transform", name=self.ns + ":c")
        dst = mlib.getNode(b).getPlug("tx")
        cmds.flushUndo()
        self.assertIs(dst.connect(mlib.getNode(a).getPlug("tx"), lock=True, fast=True), dst)
        self.assertTrue(cmds.getAttr(b + ".tx", lock=True))
        self.assertEqual(cmds.undoInfo(query=True, undoName=True), "")
        with self.assertRaises(RuntimeError) as caught:
            dst.connect(mlib.getNode(c).getPlug("tx"), fast=True)
        self.assertEqual(str(caught.exception), "Attribute is locked: " + dst.getFullName())
        cmds.setAttr(b + ".tx", lock=False)
        with self.assertRaises(RuntimeError) as caught:
            dst.connect(mlib.getNode(c).getPlug("tx"), fast=True)
        self.assertEqual(str(caught.exception), "Destination already has an input: " + dst.getFullName())
        self.assertIs(dst.connect(mlib.getNode(c).getPlug("tx"), force=True, fast=True), dst)
        self.assertTrue(cmds.isConnected(c + ".tx", b + ".tx"))
        self.assertFalse(cmds.isConnected(a + ".tx", b + ".tx"))

    def test_create_and_delete_fast_wrappers(self):
        cmds.namespace(setNamespace=self.ns)
        try:
            created = [mlib.createNode("joint", fast=True), mlib.createNode("locator", name="loc", fast=True),
                       mlib.createNode("multiplyDivide", fast=True)]
        finally:
            cmds.namespace(setNamespace=":")
        for node in created:
            expected = mlib.getNode(node.getFullName())
            self.assertIs(type(node), type(expected))
            self.assertEqual(node.getFullName(), expected.getFullName())
        names = [node.getFullName() for node in created[:2]]
        self.assertIsNone(mlib.delete(names, fast=True))
        self.assertEqual(cmds.ls(names), [])
        missing = self.ns + ":missing"
        with self.assertRaises(RuntimeError) as expected:
            mlib.getNode(missing)
        with self.assertRaises(RuntimeError) as caught:
            mlib.delete([created[2].getFullName(), missing], fast=True)
        self.assertEqual(str(caught.exception), str(expected.exception))
        self.assertTrue(created[2].isValid())

    def _double3_node(self, name):
        node = cmds.createNode("transform", name=self.ns + ":" + name)
        cmds.addAttr(node, longName="dv", attributeType="double3")
        for axis in "XYZ":
            cmds.addAttr(node, longName="dv" + axis, attributeType="double", parent="dv")
        return node


class WrapperCreationCostTest(unittest.TestCase):
    """ラッパー作成の省略(型名の関数セットの使い回し・ハンドルの共有・__init__の展開)で状態が変わらないことを確かめる。"""

    def setUp(self):
        self.ns = "speedupR10_" + uuid.uuid4().hex[:8]
        cmds.namespace(add=self.ns)
        self.undo_state = cmds.undoInfo(query=True, state=True)

    def tearDown(self):
        cmds.undoInfo(state=self.undo_state)
        if cmds.namespace(exists=self.ns):
            cmds.namespace(removeNamespace=self.ns, deleteNamespaceContent=True)

    def test_fast_wrappers_match_constructor(self):
        from mlib.nodes.node import Node
        ns = self.ns
        grp = cmds.createNode("transform", name=ns + ":grp")
        cmds.createNode("transform", name=ns + ":t", parent=grp)
        cmds.createNode("pointEmitter", name=ns + ":em", parent=grp)  # 未登録のDAG型(祖先の型)
        dg = [cmds.createNode(t, name=ns + ":" + t) for t in ("addDoubleLinear", "animBlendNodeAdditive", "plusMinusAverage")]
        children = mlib.getNode(grp).getChildren()
        self.assertEqual([self._state(c) for c in children],
                         [self._state(Node(c.getFullName())) for c in children])
        # 型の異なるノードを交互に包んでも、使い回しの関数セットが前の型名を返さない。
        for _ in range(3):
            for name in dg + [grp]:
                node = mlib.getNode(name)
                wrapped = Node._wrap_resolved(node._mobject, node._dag_path)
                self.assertEqual(self._state(wrapped), self._state(Node(name)))
                self.assertEqual(wrapped.getType(), cmds.nodeType(name))
        self.assertEqual([self._state(n) for n in mlib.ls(ns + ":*")],
                         [self._state(Node(n)) for n in cmds.ls(ns + ":*", long=True)])

    def test_overridden_init_is_still_called(self):
        from mlib.nodes.node import Node
        from mlib.nodes import SkinCluster
        joint = cmds.createNode("joint", name=self.ns + ":j")
        mesh = cmds.polyCube(name=self.ns + ":box", constructionHistory=False)[0]
        skin = cmds.skinCluster(joint, mesh, toSelectedBones=True)[0]
        wrapped = Node._wrap_resolved(mlib.getNode(skin)._mobject, None)
        self.assertIs(type(wrapped), SkinCluster)
        self.assertEqual(sorted(wrapped.__dict__), sorted(Node(skin).__dict__))
        # SkinCluster.__init__ が呼ばれ、function set のキャッシュを保持していること(公開属性 fn は 2.1.0 で廃止)。
        self.assertTrue(hasattr(wrapped, "_skin_fn"))
        self.assertFalse(hasattr(wrapped, "fn"))

    def test_registry_changes_apply_to_next_wrapper(self):
        from mlib.nodes.node import Node
        registry = Node._registry
        name = cmds.createNode("animBlendNodeAdditive", name=self.ns + ":abn")
        # 未登録型は動的クラス(型名の先頭を大文字にした名前)になる。登録表の変更で生成キャッシュは無効化される。
        generated = mlib.getNode(name)
        self.assertEqual(type(generated).__name__, "AnimBlendNodeAdditive")
        self.assertIsInstance(generated, Node)
        snapshot = registry._snapshot()

        class Probe(Node):
            pass

        try:
            registry.register("animBlendNodeAdditive", Probe)
            self.assertIs(type(mlib.getNode(name)), Probe)
            self.assertIs(type(mlib.ls(name)[0]), Probe)
        finally:
            registry._restore(snapshot)
        restored = mlib.getNode(name)
        self.assertEqual(type(restored).__name__, "AnimBlendNodeAdditive")
        self.assertIsInstance(restored, Node)
        self.assertNotIsInstance(restored, Probe)

    def test_plug_handle_shared_with_validity(self):
        node = cmds.createNode("transform", name=self.ns + ":p")
        cmds.addAttr(node, longName="dynA", attributeType="double")
        cmds.undoInfo(state=True)
        plug = mlib.getPlug(node + ".dynA")
        static = mlib.getPlug(node + ".tx")
        self.assertFalse(plug._static_attribute)
        self.assertTrue(static._static_attribute)
        self.assertEqual(plug._attribute, plug._mplug.attribute())
        cmds.deleteAttr(node + ".dynA")
        self.assertFalse(plug.isValid())
        cmds.undo()
        self.assertTrue(plug.isValid())
        self.assertEqual(plug.getFullName(), mlib.getPlug(node + ".dynA").getFullName())

    def _state(self, node):
        return (type(node), sorted(node.__dict__), node.getFullName(), hash(node))


class ConnectionHistoryAttrListTest(unittest.TestCase):
    """接続・ヒストリー・動的アトリビュートの列挙と、container・名前空間の列挙が従来の手順と同じ結果になることを確かめる。"""

    def setUp(self):
        self.ns = "speedupR11_" + uuid.uuid4().hex[:8]
        cmds.namespace(add=self.ns)
        self.undo_state = cmds.undoInfo(query=True, state=True)
        self.extension = None

    def tearDown(self):
        cmds.undoInfo(state=self.undo_state)
        if cmds.namespace(exists=self.ns):
            cmds.namespace(removeNamespace=self.ns, deleteNamespaceContent=True)
        if self.extension:
            cmds.deleteExtension(nodeType="transform", attribute=self.extension, forceDelete=True)

    def test_node_connections_match_per_plug_lookup(self):
        flag_sets = [{}, {"asPair": True}, {"asNode": True}, {"source": False}, {"destination": False},
                     {"skipConversionNodes": True}, {"skipConversionNodes": True, "asPair": True},
                     {"type": "transform"}, {"type": "joint", "exactType": True}, {"index": -1}]
        for name in self._scene():
            node = mlib.getNode(name)
            for flags in flag_sets:
                with self.subTest(node=name, flags=flags):
                    self.assertEqual(self._key(node.getConnections(**flags)),
                                     self._key(self._reference_connections(node, **dict(flags))))
        node = mlib.getNode(self.ns + ":loc")
        # 短縮名とペア指定の別名も同じ結果になる。
        self.assertEqual(self._key(node.getConnections(c=True)), self._key(node.getConnections(asPair=True)))
        self.assertEqual(self._key(node.getConnections(t="joint", et=True)),
                         self._key(node.getConnections(type="joint", exactType=True)))

    def test_overriding_plug_subclass_is_still_called(self):
        import gc
        from mlib.nodes.node import _subclass_overrides
        from mlib.plugs.plug import Plug
        names = self._scene()
        self.assertFalse(_subclass_overrides(Plug, "getConnections"))

        class Probe(Plug):
            def getConnections(self, *args, **kwargs):
                return super().getConnections(*args, **kwargs)

        try:
            self.assertTrue(_subclass_overrides(Plug, "getConnections"))
            node = mlib.getNode(names[0])
            # 上書きする派生クラスがあれば自身側のPlugを作る経路を通り、結果は同じ。
            self.assertEqual(self._key(node.getConnections()), self._key(self._reference_connections(node)))
        finally:
            del Probe
            gc.collect()
        self.assertFalse(_subclass_overrides(Plug, "getConnections"))

    def test_history_matches_node_wrappers(self):
        from mlib.nodes.node import Node
        cube = cmds.polyCube(name=self.ns + ":cube")[0]
        cmds.polySmooth(cube)
        cmds.nonLinear(cube, type="bend")
        shape = cmds.listRelatives(cube, shapes=True, fullPath=True)[0]
        for name, flags in ((cube, {}), (shape, {}), (shape, {"type": "geometryFilter"}),
                            (cube, {"future": True})):
            node = mlib.getNode(name)
            expected, seen = [], {node.getUuid()}
            for item in cmds.listHistory(node.getFullName(), future=flags.get("future", False)) or []:
                wrapped = Node(item)
                if wrapped.getUuid() in seen:
                    continue
                seen.add(wrapped.getUuid())
                if flags.get("type") is None or wrapped.isType(flags["type"]):
                    expected.append(wrapped)
            with self.subTest(node=name, flags=flags):
                self.assertEqual(self._key(node.getHistory(**flags)), self._key(expected))
        dead = mlib.getNode(cmds.createNode("transform", name=self.ns + ":dead"))
        cmds.delete(dead.getFullName())
        # 削除済みノードは docstring どおり RuntimeError(2026-10-26 に実装を docstring へ揃えた。
        # 従来は cmds.listHistory("") の ValueError だった)。
        with self.assertRaisesRegex(RuntimeError, r"invalid \w+"):
            dead.getHistory()

    def test_extra_attrs_skip_static_and_extension(self):
        loc = self._scene()[0]
        self.extension = "speedupR11Ext"
        cmds.addAttr(loc, longName="dynV", attributeType="double3")
        for axis in "XYZ":
            cmds.addAttr(loc, longName="dynV" + axis, attributeType="double", parent="dynV")
        cmds.addExtension(nodeType="transform", longName=self.extension, attributeType="double")
        cmds.addAttr(loc, longName="late", attributeType="double")
        cmds.addAttr(loc, longName="gone", attributeType="double")
        cmds.deleteAttr(loc + ".gone")
        node = mlib.getNode(loc)
        fn = om2.MFnDependencyNode(node.mnode())
        for include_children in (False, True):
            expected = []
            for index in range(fn.attributeCount()):
                definition = om2.MFnAttribute(fn.attribute(index))
                if definition.dynamic and (include_children or definition.parent.isNull()):
                    expected.append(definition.name)
            with self.subTest(include_children=include_children):
                self.assertEqual([p.getLongName() for p in node.getPlugs(userDefined=True, includeChildren=include_children)], expected)
                self.assertEqual([p.getLongName() for p in node.getPlugs(userDefined=True, includeChildren=include_children)], expected)
                self.assertNotIn(self.extension, expected)
        self.assertEqual([p.getLongName() for p in node.getPlugs(userDefined=True, includeChildren=False)], ["dynM", "dynV", "late"])

    def test_container_membership_and_namespace_nodes(self):
        from mlib.common.namespace import Namespace
        from mlib.nodes.node import Node
        ns = self.ns
        names = [cmds.createNode(t, name=f"{ns}:{t}") for t in ("plusMinusAverage", "multiplyDivide")]
        names.append(cmds.createNode("transform", name=ns + ":ct"))
        outsider = cmds.createNode("transform", name=ns + ":out")
        cont = mlib.getNode(cmds.container(name=ns + ":cont"))
        cont.addMembers(*names)
        self.assertEqual([(type(m), m.getFullName()) for m in cont.getMembers()],
                         [(type(Node(o)), Node(o).getFullName())
                          for o in om2.MFnContainerNode(cont.mnode()).getMembers()])
        with self.assertRaisesRegex(ValueError, "nodes must all be members of this container"):
            cont.removeMembers(names[0], outsider)
        self.assertEqual(len(cont.getMembers()), 3)
        cmds.undoInfo(state=True)
        cont.removeMembers(names[0], names[0], names[2])
        self.assertEqual([m.getFullName() for m in cont.getMembers()], [mlib.getNode(names[1]).getFullName()])
        cmds.undo()
        self.assertEqual(len(cont.getMembers()), 3)
        for recurse in (False, True):
            nodes = Namespace(":" + ns).getNodes(recurse=recurse)
            objects = om2.MNamespace.getNamespaceObjects(":" + ns, recurse)
            with self.subTest(recurse=recurse):
                self.assertEqual([(type(n), n.getFullName()) for n in nodes],
                                 [(type(Node(o)), Node(o).getFullName()) for o in objects])

    def _scene(self):
        ns = self.ns
        loc = cmds.spaceLocator(name=ns + ":loc")[0]
        j1 = cmds.createNode("joint", name=ns + ":j1")
        j2 = cmds.createNode("joint", name=ns + ":j2", parent=j1)
        md = cmds.createNode("multiplyDivide", name=ns + ":md")
        cmds.connectAttr(loc + ".tx", j1 + ".rx")  # unitConversionを挟む
        cmds.connectAttr(loc + ".translate", j2 + ".translate")
        cmds.addAttr(loc, longName="dynM", attributeType="double", multi=True)
        cmds.connectAttr(md + ".outputX", loc + ".dynM[2]")
        cmds.connectAttr(md + ".outputX", j1 + ".sx")
        grp = cmds.createNode("transform", name=ns + ":grp")
        cmds.parent(cmds.instance(loc, name=ns + ":locI")[0], grp)
        return [loc, j1, j2, md, grp]

    @staticmethod
    def _key(value):
        from mlib.nodes.node import Node
        from mlib.plugs.plug import Plug
        if isinstance(value, (list, tuple)):
            return (type(value).__name__, [ConnectionHistoryAttrListTest._key(v) for v in value])
        if isinstance(value, (Node, Plug)):
            return (type(value).__name__, value.getFullName())
        return value

    @staticmethod
    def _reference_connections(node, **flags):
        """変更前の手順(自身側Plugごとに Plug.getConnections を呼ぶ)で求める。"""
        from mlib.plugs.plug import Plug
        as_pair = flags.pop("asPair", False)
        node_type = flags.pop("type", None)
        exact = flags.pop("exactType", False)
        as_node = flags.pop("asNode", False)
        index = flags.pop("index", None)
        pairs = []
        for mp in node._dependency_fn().getConnections():
            pairs.extend(Plug(node, mp).getConnections(asPair=True, checkChildren=False,
                                                       checkElements=False, **flags))
        return Plug._connection_results(pairs, node_type, exact, as_pair, as_node, index)


class ImportCostTest(unittest.TestCase):
    """import mlibの短縮が、拡張の探索結果と遅延したimportの動作を変えないことを確かめる。"""

    def setUp(self):
        import tempfile
        self.temp = tempfile.TemporaryDirectory()
        self.root = self.temp.name
        self.path = list(sys.path)

    def tearDown(self):
        sys.path[:] = self.path
        for path in list(sys.path_importer_cache):
            if path.startswith(self.root):
                del sys.path_importer_cache[path]
        self.temp.cleanup()

    def test_find_candidates_matches_iter_modules(self):
        """パッケージ・非パッケージ・ファイル・zip・存在しないパス・重複を含めて変更前と同じ候補を返す。"""
        import os
        import zipfile
        from mlib.core import extensions
        self._write("a", "mlib_zzpkg", "__init__.py")
        self._write("a", "mlib_zznopkg", "mod.py")
        self._write("a", "mlib_zzfile.py")
        self._write("a", "mlib_Upper", "__init__.py")
        self._write("a", "mlib_zzpyc", "__init__.pyc")
        self._write("a", "other", "__init__.py")
        self._write("b", "mlib_zzpkg", "__init__.py")
        self._write("c", "mlib_zzonly.py")
        os.makedirs(os.path.join(self.root, "c", "mlib_zzonly"))
        archive = os.path.join(self.root, "ext.zip")
        with zipfile.ZipFile(archive, "w") as stream:
            stream.writestr("mlib_zzzip/__init__.py", "")
        a, b, c = (os.path.join(self.root, name) for name in "abc")
        sys.path[:0] = [a, b, a, c, archive, os.path.join(self.root, "missing"),
                        self._write("plain.txt"), os.path.join(self.root, "a", "mlib_zzpkg")]
        expected = self._reference_candidates()
        self.assertEqual(extensions._find_candidates(), expected)
        found = extensions._find_candidates()
        self.assertEqual(found["mlib_zzpkg"], {os.path.normcase(os.path.realpath(a)),
                                               os.path.normcase(os.path.realpath(b))})
        self.assertIn("mlib_zzpyc", found)
        self.assertIn("mlib_zzzip", found)
        for name in ("mlib_zznopkg", "mlib_zzfile", "mlib_Upper", "mlib_zzonly"):
            self.assertNotIn(name, found)

    def test_find_candidates_current_path(self):
        """現在の探索パスでも変更前と同じ候補を返し、mlib自身の配置にある拡張を含む。"""
        import os
        from mlib.core import extensions
        found = extensions._find_candidates()
        self.assertEqual(found, self._reference_candidates())
        parent = os.path.dirname(os.path.dirname(mlib.__file__))
        local = {name for name in os.listdir(parent) if extensions._extension_pattern.fullmatch(name)
                 and os.path.isfile(os.path.join(parent, name, "__init__.py"))}
        self.assertTrue(local <= set(found))

    def test_lazy_standard_modules(self):
        """util.measure・Mayaへの通知・DagPoseの読取りが関数内のimportで動く。"""
        import logging
        from mlib import logger, util
        result = util.measure(lambda: None, samples=3, warmup=1)
        self.assertEqual(result["samples"], 3)
        self.assertLessEqual(result["min_seconds"], result["median_seconds"])
        for module in (util, logger):
            self.assertNotIn("statistics", vars(module))
            self.assertNotIn("html", vars(module))
        handler = logger.MayaHandler()
        record = logging.LogRecord("mlib", logging.WARNING, __file__, 1, "<a & b>", None, None)
        handler.emit(record)
        joint = cmds.createNode("joint", name="mlibSpeedupImport_" + uuid.uuid4().hex)
        try:
            pose = cmds.dagPose(joint, save=True, bindPose=True)
            from mlib.nodes import DagPose
            node = mlib.getNode(pose)
            self.assertIsInstance(node, DagPose)
            selection = om2.MSelectionList()
            selection.add(pose + ".xformMatrix[0]")
            self.assertTrue(DagPose._merge_matrix_payload(selection.getPlug(0)))
        finally:
            for name in cmds.ls(type="dagPose") or []:
                if joint in (cmds.dagPose(name, query=True, members=True) or []):
                    cmds.delete(name)
            cmds.delete(joint)

    @staticmethod
    def _reference_candidates():
        """変更前の手順(全探索パスでpkgutil.iter_modules)で候補を集める。"""
        import os
        import pkgutil
        from mlib.core import extensions
        candidates = {}
        for path in dict.fromkeys(sys.path):
            for info in pkgutil.iter_modules([path]):
                if info.ispkg and extensions._extension_pattern.fullmatch(info.name):
                    location = os.path.normcase(os.path.realpath(path))
                    candidates.setdefault(info.name, set()).add(location)
        return candidates

    def _write(self, *parts, text=""):
        """一時フォルダーの下へファイルを作る。"""
        import os
        path = os.path.join(self.root, *parts)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as stream:
            stream.write(text)
        return path


class MatrixTransformCostTest(unittest.TestCase):
    """Matrix生成のimport省略とsetMatrixのrotateAxisの1回読取が結果を変えないことを確かめる。"""

    def setUp(self):
        self.ns = "mlibSpeedupXform_" + uuid.uuid4().hex
        cmds.namespace(add=self.ns)

    def tearDown(self):
        cmds.namespace(removeNamespace=self.ns, deleteNamespaceContent=True)

    def test_matrix_inputs_keep_type_and_values(self):
        """MMatrix・Matrix・列・派生型・Transformation・不正入力の扱いが型ごとに変わらない。"""
        from mlib.maths.matrix import Matrix
        from mlib.maths.transformation import Transformation

        class SubMatrix(Matrix):
            pass

        class SubTransformation(Transformation):
            pass

        values = [float(index) for index in range(16)]
        transformation = SubTransformation(translate=(1, 2, 3), rotate=(0.1, 0.2, 0.3), scale=(2, 3, 4))
        for source, expected in ((om2.MMatrix(values), values), (Matrix(values), values),
                                 (SubMatrix(values), values), (tuple(values), values),
                                 (om2.MFloatMatrix(values), values), ((value for value in values), values),
                                 ([values[0:4], values[4:8], values[8:12], values[12:16]], values),
                                 (transformation, list(transformation.matrix)),
                                 (Transformation(scale=(1, 2, 3)), list(Transformation(scale=(1, 2, 3)).matrix))):
            result = Matrix(source)
            self.assertIs(type(result), Matrix)
            self.assertEqual(list(result), expected)
        for source in (values[:15], "abc", 5, ["a"] * 16, {}):
            with self.assertRaises(ValueError):
                Matrix(source)

    def test_set_matrix_reads_rotate_axis_once(self):
        """Transformは従来の_channel_rotateの経路と同じ値になり、JointはrotateAxisを従来どおり読む。"""
        from mlib.maths.matrix import Matrix
        from mlib.nodes import Transform
        node = mlib.getNode(cmds.createNode("transform", name=self.ns + ":t"))
        cmds.setAttr(str(node) + ".ra", 15, 25, 35)
        cmds.setAttr(str(node) + ".rp", 0.5, 0.2, -0.3)
        joint = mlib.getNode(cmds.createNode("joint", name=self.ns + ":j"))
        cmds.setAttr(str(joint) + ".ra", 5, 0, -5)
        cmds.setAttr(str(joint) + ".jo", 10, 20, 30)
        target = Matrix(translate=(1, 2, 3), rotate=(0.3, -0.2, 0.1), scale=(1, -2, 1.5))

        class Legacy(Transform):
            def _channel_rotate(self, quaternion, reference):
                return Transform._channel_rotate(self, quaternion, reference)

        legacy = mlib.getNode(str(node))
        legacy.__class__ = Legacy
        for space in (False, True):
            fast = node.setMatrix(target, ws=space, get=True)
            slow = legacy.setMatrix(target, ws=space, get=True)
            self.assertEqual(sorted(fast), sorted(slow))
            for key in fast:
                self.assertIs(type(fast[key]), type(slow[key]))
                self.assertEqual([value.hex() for value in fast[key]], [value.hex() for value in slow[key]])
        for wrapper, expected in ((node, 1), (legacy, 2), (joint, 1)):
            names = []
            original = type(wrapper)._component_quaternion

            def counting(self, name, original=original):
                names.append(name)
                return original(self, name)

            wrapper.__class__ = type("Counting", (type(wrapper),), {"_component_quaternion": counting})
            wrapper.setMatrix(target, get=True)
            self.assertEqual(names.count("rotateAxis"), expected)
        node.setMatrix(target)
        self.assertTrue(Matrix(cmds.xform(str(node), query=True, matrix=True)).isEquivalent(target, 1e-9))


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
