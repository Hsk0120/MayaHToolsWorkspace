"""Plugの名前・状態フラグ・別名・ミュート・定義照会・有効性の約束を固定する。

期待値はmaya.cmdsとOpenMayaで独立に求めた値と比べる。
"""

import unittest
import uuid

import maya.api.OpenMaya as om2
import maya.cmds as cmds
import mlib
from mlib import plugs
from mlib.plugs.plug import MAX_LOGICAL_INDEX, DeletedAttributeError


class _StateSpecCase(unittest.TestCase):
    """専用の名前空間・Undo・単位・時刻を用意し、終了時に元へ戻す。"""

    def setUp(self):
        self.namespace = ":specBStates_" + uuid.uuid4().hex
        self.before = set(cmds.ls(long=True) or [])
        cmds.namespace(add=self.namespace)
        self.undo_state = cmds.undoInfo(query=True, state=True)
        self.units = (cmds.currentUnit(query=True, linear=True), cmds.currentUnit(query=True, angle=True),
                      cmds.currentUnit(query=True, time=True))
        self.time = cmds.currentTime(query=True)
        cmds.undoInfo(state=True)
        cmds.currentUnit(linear="cm", angle="deg", time="film")
        self.node = self.make("transform")
        self.name = self.node.getName()

    def tearDown(self):
        cmds.currentUnit(linear=self.units[0], angle=self.units[1], time=self.units[2])
        cmds.currentTime(self.time)
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

    def make(self, kind="network", **kwargs):
        """Mayaコマンドで作成したノードを取得する。"""
        return mlib.getNode(cmds.createNode(kind, name=self.namespace + ":n#", skipSelect=True, **kwargs))

    def assertUndoEmpty(self):
        """Undoの記録が追加されていないことを確かめる。"""
        self.assertTrue(cmds.undoInfo(query=True, undoQueueEmpty=True))


class PlugNameSpecTest(_StateSpecCase):
    """名前の取得と、名前変更・親変更・別名への追従。"""

    def test_name_forms(self):
        """短い名前・ロング名・ニース名・Plug名とstrの対応。"""
        tx = self.node.getPlug("tx")
        self.assertEqual(tx.getName(), self.name + ".tx")
        self.assertEqual(tx.getAttrName(), ".tx")
        self.assertEqual(tx.getShortName(), "tx")
        self.assertEqual(tx.getLongName(), "translateX")
        self.assertEqual(tx.getNiceName(), "Translate X")
        self.assertEqual(tx.getFullName(), self.name + ".translateX")
        self.assertEqual(str(tx), tx.getFullName())
        self.assertEqual(repr(tx), "Plug(%r)" % tx.getFullName())
        self.assertEqual(cmds.getAttr(tx), 0.0)

    def test_full_attribute_path_option(self):
        """複合の子でも getFullName は最短のパス(全階層のパスを返す入口は無い)。"""
        child = self.node.getPlug("boundingBoxMinX")
        self.assertFalse(hasattr(child, "getPlugName"))
        self.assertEqual(child.getFullName(), self.name + ".boundingBoxMinX")

    def test_element_and_child_names(self):
        """配列要素の子は必要な論理番号を含む名前になる。"""
        cmds.addAttr(self.name, longName="items", shortName="its", attributeType="compound",
                     numberOfChildren=1, multi=True)
        cmds.addAttr(self.name, longName="weight", shortName="wt", attributeType="double", parent="items")
        child = self.node.getPlug("items[3].weight")
        self.assertEqual(child.getFullName(), self.name + ".items[3].weight")
        self.assertEqual(child.getName(), self.name + ".its[3].wt")
        self.assertEqual(child.getAttrName(), ".its[3].wt")
        self.assertEqual(child.getShortName(), "wt")
        self.assertEqual(child.getParent().getFullName(), self.name + ".items[3]")

    def test_names_follow_rename_and_reparent(self):
        """名前変更・親変更・Undoに追従し、DAGパスは一意になる最短の形を使う。"""
        group = cmds.createNode("transform", name=self.namespace + ":grp", skipSelect=True)
        tx = self.node.getPlug("tx")
        cmds.parent(self.name, group)
        same = cmds.createNode("transform", name=self.name.split(":")[-1], skipSelect=True)
        cmds.namespace(set=self.namespace)
        try:
            same_in_namespace = cmds.createNode("transform", name=self.name.split(":")[-1], skipSelect=True)
        finally:
            cmds.namespace(set=":")
        self.assertTrue(cmds.objExists(same))
        self.assertTrue(tx.getFullName().endswith(self.name + ".translateX"))
        self.assertEqual(len(cmds.ls(tx.getFullName())), 1)
        cmds.delete(same_in_namespace)
        cmds.flushUndo()
        renamed = cmds.rename(self.node.getFullName(), self.namespace + ":renamed")
        self.assertEqual(tx.getFullName(), renamed + ".translateX")
        cmds.undo()
        self.assertTrue(tx.getFullName().endswith(self.name + ".translateX"))

    def test_alias_is_used_by_full_name_only(self):
        """別名があればgetFullNameは別名を使い、getName・getLongNameは元の名前。"""
        cmds.aliasAttr("myAlias", self.name + ".ty")
        ty = self.node.getPlug("ty")
        self.assertEqual(ty.getFullName(), self.name + ".myAlias")
        self.assertEqual(ty.getName(), self.name + ".ty")
        self.assertEqual(ty.getLongName(), "translateY")
        self.assertEqual(self.node.getPlug("myAlias"), ty)


class PlugFlagSpecTest(_StateSpecCase):
    """setKeyable・setChannelBox・setLocked・setFlags・unlock。"""

    def test_keyable_and_channel_box_are_exclusive(self):
        """setChannelBox(True)はkeyableを外し、setKeyable(True)はchannelBoxを外す。自身を返す。"""
        tx = self.node.getPlug("tx")
        self.assertTrue(tx.isKeyable())
        self.assertFalse(tx.isChannelBox())
        self.assertIs(tx.setChannelBox(True), tx)
        self.assertTrue(cmds.getAttr(self.name + ".tx", channelBox=True))
        self.assertFalse(cmds.getAttr(self.name + ".tx", keyable=True))
        self.assertIs(tx.setKeyable(True), tx)
        self.assertTrue(cmds.getAttr(self.name + ".tx", keyable=True))
        self.assertFalse(cmds.getAttr(self.name + ".tx", channelBox=True))
        self.assertIs(tx.setKeyable(False), tx)
        self.assertFalse(tx.isKeyable())
        self.assertFalse(tx.isChannelBox())

    def test_flag_undo_and_fast(self):
        """通常の変更は1回のUndoで両方のフラグが戻り、fastは記録しない。"""
        tx = self.node.getPlug("tx")
        cmds.flushUndo()
        tx.setChannelBox(True)
        cmds.undo()
        self.assertTrue(cmds.getAttr(self.name + ".tx", keyable=True))
        self.assertFalse(cmds.getAttr(self.name + ".tx", channelBox=True))
        self.assertUndoEmpty()
        tx.setChannelBox(True, fast=True)
        tx.setLocked(True, fast=True)
        self.assertTrue(cmds.getAttr(self.name + ".tx", channelBox=True))
        self.assertFalse(cmds.getAttr(self.name + ".tx", keyable=True))
        self.assertTrue(cmds.getAttr(self.name + ".tx", lock=True))
        tx.setKeyable(True, fast=True)
        self.assertTrue(cmds.getAttr(self.name + ".tx", keyable=True))
        self.assertFalse(cmds.getAttr(self.name + ".tx", channelBox=True))
        self.assertUndoEmpty()

    def test_leaf_applies_to_children(self):
        """leaf=Trueは複合の子へ設定し、親自身は変えない。leaf=Falseは親だけを変える。"""
        translate = self.node.getPlug("translate")
        translate.setLocked(True, leaf=True)
        self.assertEqual([cmds.getAttr(self.name + ".t" + a, lock=True) for a in "xyz"], [True] * 3)
        self.assertFalse(cmds.getAttr(self.name + ".t", lock=True))
        translate.setLocked(False)
        self.assertEqual([cmds.getAttr(self.name + ".t" + a, lock=True) for a in "xyz"], [True] * 3)
        translate.setLocked(False, leaf=True)
        translate.setKeyable(False, leaf=True)
        self.assertEqual([cmds.getAttr(self.name + ".t" + a, keyable=True) for a in "xyz"], [False] * 3)
        translate.setChannelBox(True, leaf=True)
        self.assertEqual([cmds.getAttr(self.name + ".t" + a, channelBox=True) for a in "xyz"], [True] * 3)

    def test_set_flags_validation(self):
        """setFlagsは省略した状態を変えず、bool・None以外は変更前にTypeError。"""
        tx = self.node.getPlug("tx")
        self.assertIs(tx.setFlags(), tx)
        tx.setFlags(locked=True, keyable=False)
        self.assertTrue(cmds.getAttr(self.name + ".tx", lock=True))
        self.assertFalse(cmds.getAttr(self.name + ".tx", keyable=True))
        tx.setFlags(locked=False, fast=True)
        self.assertFalse(cmds.getAttr(self.name + ".tx", lock=True))
        self.assertFalse(cmds.getAttr(self.name + ".tx", keyable=True))
        for kwargs in (dict(locked=1), dict(keyable="yes"), dict(channelBox=0), dict(fast=None)):
            with self.subTest(**kwargs):
                with self.assertRaises(TypeError):
                    tx.setFlags(**kwargs)
        for method in (tx.setLocked, tx.setKeyable, tx.setChannelBox):
            with self.subTest(method=method.__name__):
                with self.assertRaises(TypeError):
                    method(1)
                with self.assertRaises(TypeError):
                    method(True, fast=1)
        self.assertFalse(cmds.getAttr(self.name + ".tx", lock=True))

    def test_unlock_parents_and_children(self):
        """unlockは自身と上位のロックを外し、below=Trueで子も外す。外したPlugを上位から返す。"""
        cmds.setAttr(self.name + ".r", lock=True)
        cmds.setAttr(self.name + ".ry", lock=True)
        cmds.setAttr(self.name + ".rz", lock=True)
        result = self.node.getPlug("ry").unlock()
        self.assertEqual([p.getLongName() for p in result], ["rotate", "rotateY"])
        self.assertTrue(cmds.getAttr(self.name + ".rz", lock=True))
        cmds.setAttr(self.name + ".r", lock=True)
        cmds.setAttr(self.name + ".ry", lock=True)
        result = self.node.getPlug("rotate").unlock(below=True)
        self.assertEqual([p.getLongName() for p in result], ["rotate", "rotateY", "rotateZ"])
        self.assertEqual(self.node.getPlug("rotate").unlock(below=True), [])

    def test_unlock_undo_paths(self):
        """通常のunlockは1回のUndoで戻り、fast=Trueは記録しない。undoable引数は無い。"""
        cmds.setAttr(self.name + ".r", lock=True)
        cmds.flushUndo()
        self.node.getPlug("rotate").unlock()
        cmds.undo()
        self.assertTrue(cmds.getAttr(self.name + ".r", lock=True))
        with self.assertRaises(TypeError):
            self.node.getPlug("rotate").unlock(undoable=False)
        cmds.setAttr(self.name + ".r", lock=True)
        cmds.flushUndo()
        self.node.getPlug("rotate").unlock(fast=True)
        self.assertFalse(cmds.getAttr(self.name + ".r", lock=True))
        self.assertUndoEmpty()
        with self.assertRaises(TypeError):
            self.node.getPlug("rotate").unlock(fast=1)

    def test_locked_inherits_from_parent_in_query(self):
        """親がロックされていると子のisLockedもTrue(MPlugの判定)。"""
        cmds.setAttr(self.name + ".t", lock=True)
        self.assertTrue(self.node.getPlug("tx").isLocked())
        self.assertEqual(self.node.getPlug("tx").isLocked(), cmds.getAttr(self.name + ".tx", lock=True))


class PlugAliasSpecTest(_StateSpecCase):
    """setAliasの設定・解除・Undo・fast。"""

    def test_set_and_remove_alias(self):
        """別名を設定し、Noneまたは空文字列で解除する。別名が無い解除は何もしない。"""
        tz = self.node.getPlug("tz")
        self.assertIs(tz.setAlias("zAlias"), tz)
        self.assertEqual(cmds.aliasAttr(self.name, query=True), ["zAlias", "translateZ"])
        self.assertEqual(tz.getFullName(), self.name + ".zAlias")
        self.assertIs(tz.setAlias(), tz)
        self.assertIsNone(cmds.aliasAttr(self.name, query=True))
        tz.setAlias("zAlias")
        tz.setAlias("")
        self.assertIsNone(cmds.aliasAttr(self.name, query=True))
        self.assertIs(tz.setAlias(None), tz)
        self.assertEqual(tz.getFullName(), self.name + ".translateZ")

    def test_alias_undo_fast_and_errors(self):
        """通常の設定は1回のUndoで戻り、fastは記録しない。既存名と重なる別名はRuntimeError。"""
        sx = self.node.getPlug("sx")
        cmds.flushUndo()
        sx.setAlias("sxa")
        cmds.undo()
        self.assertIsNone(cmds.aliasAttr(self.name, query=True))
        cmds.flushUndo()
        sx.setAlias("sxb", fast=True)
        self.assertEqual(cmds.aliasAttr(self.name, query=True), ["sxb", "scaleX"])
        sx.setAlias(None, fast=True)
        self.assertIsNone(cmds.aliasAttr(self.name, query=True))
        self.assertUndoEmpty()
        with self.assertRaises(RuntimeError):
            sx.setAlias("tx")
        with self.assertRaises(TypeError):
            sx.setAlias("x", fast=1)


class PlugMuteSpecTest(_StateSpecCase):
    """mute・unmute・setMuted・isMuted。"""

    def setUp(self):
        super().setUp()
        self.sz = self.node.getPlug("sz")
        cmds.setKeyframe(self.name + ".sz", time=1, value=2)
        cmds.setKeyframe(self.name + ".sz", time=10, value=4)
        cmds.currentTime(5)

    def test_mute_holds_current_value_and_unmute_restores_animation(self):
        """muteは現在値で固定し、unmuteはアニメーションへ戻す。繰り返しても状態は同じ。"""
        held = cmds.getAttr(self.name + ".sz")
        self.assertIs(self.sz.mute(), self.sz)
        self.assertTrue(self.sz.isMuted())
        self.assertTrue(cmds.mute(self.name + ".sz", query=True))
        cmds.currentTime(10)
        self.assertAlmostEqual(self.sz.get(), held)
        self.sz.mute()
        self.assertTrue(self.sz.isMuted())
        self.assertIs(self.sz.unmute(), self.sz)
        self.assertFalse(self.sz.isMuted())
        self.assertAlmostEqual(self.sz.get(), 4.0)
        self.assertIs(self.sz.unmute(), self.sz)
        self.assertFalse(self.sz.isMuted())

    def test_mute_undo(self):
        """通常のmuteは1回のUndoで戻る。"""
        cmds.flushUndo()
        self.sz.setMuted(True)
        cmds.undo()
        self.assertFalse(self.sz.isMuted())
        self.assertFalse(cmds.mute(self.name + ".sz", query=True))

    def test_fast_and_argument_errors(self):
        """fast=TrueはNotImplementedError、bool以外の状態・fastはTypeErrorで、状態を変えない。"""
        for call in (lambda: self.sz.mute(fast=True), lambda: self.sz.unmute(fast=True),
                     lambda: self.sz.setMuted(True, fast=True)):
            with self.assertRaises(NotImplementedError):
                call()
        for call in (lambda: self.sz.mute(fast=1), lambda: self.sz.setMuted(1), lambda: self.sz.unmute(fast=None)):
            with self.assertRaises(TypeError):
                call()
        self.assertFalse(self.sz.isMuted())

    def test_mute_without_animation_is_silent_noop(self):
        """アニメーションの無いチャンネルのmuteはMayaが警告して何もせず、自身を返す。"""
        sy = self.node.getPlug("sy")
        self.assertIs(sy.mute(), sy)
        self.assertFalse(sy.isMuted())
        self.assertFalse(cmds.listConnections(self.name + ".sy", source=True, destination=False))

    def test_is_muted_only_for_mute_node(self):
        """isMutedは直接の入力がmuteノードの場合だけTrue。"""
        other = self.make("transform")
        cmds.connectAttr(other.getName() + ".sx", self.name + ".sx")
        self.assertFalse(self.node.getPlug("sx").isMuted())
        self.assertFalse(self.node.getPlug("sy").isMuted())


class PlugDefinitionQuerySpecTest(_StateSpecCase):
    """定義の照会(hidden・dynamic・readable・writable・storable・範囲)と構造の判定。"""

    def test_definition_flags_match_attribute_query(self):
        """定義フラグはcmds.attributeQueryと一致する。"""
        cmds.addAttr(self.name, longName="extraHidden", attributeType="double", hidden=True)
        for attr in ("translateX", "worldMatrix", "message", "extraHidden"):
            with self.subTest(attr=attr):
                plug = self.node.getPlug(attr)
                self.assertEqual(plug.isHidden(), cmds.attributeQuery(attr, node=self.name, hidden=True))
                self.assertEqual(plug.isReadable(), cmds.attributeQuery(attr, node=self.name, readable=True))
                self.assertEqual(plug.isWritable(), cmds.attributeQuery(attr, node=self.name, writable=True))
                self.assertEqual(plug.isStorable(), cmds.attributeQuery(attr, node=self.name, storable=True))
        self.assertTrue(self.node.getPlug("extraHidden").isDynamic())
        self.assertFalse(self.node.getPlug("tx").isDynamic())

    def test_structure_predicates(self):
        """isArray・isCompound・isElement・isChildはMPlugの構造を返す。"""
        world = self.node.getPlug("worldMatrix")
        self.assertEqual((world.isArray(), world.isCompound(), world.isElement(), world.isChild()),
                         (True, False, False, False))
        element = world[0]
        self.assertEqual((element.isArray(), element.isElement()), (False, True))
        tx = self.node.getPlug("tx")
        self.assertEqual((tx.isChild(), tx.isCompound()), (True, False))
        self.assertTrue(self.node.getPlug("translate").isCompound())
        self.assertIsNone(self.node.getPlug("translate").getParent())

    def test_numeric_ranges(self):
        """数値の範囲はfloat、無い場合はNone・False。"""
        cmds.addAttr(self.name, longName="rng", attributeType="double", minValue=-1, maxValue=2,
                     softMinValue=0, softMaxValue=1)
        cmds.addAttr(self.name, longName="soft", attributeType="double", softMinValue=-5, softMaxValue=5)
        rng, soft = self.node.getPlug("rng"), self.node.getPlug("soft")
        self.assertEqual((rng.hasMin(), rng.hasMax(), rng.getMin(), rng.getMax()), (True, True, -1.0, 2.0))
        self.assertEqual((rng.hasSoftMin(), rng.hasSoftMax(), rng.getSoftMin(), rng.getSoftMax()),
                         (True, True, 0.0, 1.0))
        self.assertEqual((soft.hasMin(), soft.getMin(), soft.hasMax(), soft.getMax()), (False, None, False, None))
        self.assertEqual((soft.getSoftMin(), soft.getSoftMax()), (-5.0, 5.0))
        tx = self.node.getPlug("tx")
        self.assertEqual((tx.hasMin(), tx.getMin(), tx.hasSoftMin(), tx.getSoftMin()), (False, None, False, None))
        self.assertEqual(self.node.getPlug("visibility").getMin(), 0.0)

    def test_unit_ranges_return_api_objects(self):
        """角度・距離の範囲はMAngle・MDistanceをそのまま返し、換算しない。"""
        cmds.addAttr(self.name, longName="angleLimit", attributeType="doubleAngle", minValue=-1, maxValue=1)
        cmds.addAttr(self.name, longName="lengthLimit", attributeType="doubleLinear", minValue=-2, maxValue=3)
        angle, length = self.node.getPlug("angleLimit"), self.node.getPlug("lengthLimit")
        self.assertIsInstance(angle.getMin(), om2.MAngle)
        self.assertAlmostEqual(angle.getMin().asRadians(), -1.0)
        self.assertAlmostEqual(angle.getMax().asRadians(), 1.0)
        self.assertIsInstance(length.getMax(), om2.MDistance)
        self.assertAlmostEqual(length.getMin().asCentimeters(), -2.0)
        self.assertAlmostEqual(length.getMax().asCentimeters(), 3.0)

    def test_ranges_of_non_numeric_types(self):
        """文字列・マトリクス・messageには範囲が無い。"""
        cmds.addAttr(self.name, longName="txt", dataType="string")
        for attr in ("txt", "message", "worldMatrix"):
            with self.subTest(attr=attr):
                plug = self.node.getPlug(attr)
                self.assertEqual((plug.hasMin(), plug.hasMax(), plug.hasSoftMin(), plug.hasSoftMax()),
                                 (False, False, False, False))
                self.assertEqual((plug.getMin(), plug.getMax(), plug.getSoftMin(), plug.getSoftMax()),
                                 (None, None, None, None))

    def test_identity_get_node_and_mplug(self):
        """getNodeは所有Nodeそのもの、mplugは保持中のMPlug。同じアトリビュートは等しくハッシュも同じ。"""
        tx = self.node.getPlug("tx")
        self.assertIs(tx.getNode(), self.node)
        self.assertIsInstance(tx.mplug(), om2.MPlug)
        self.assertIs(tx.mplug(), tx.mplug())
        other = self.node.getPlug("translateX")
        self.assertEqual(tx, other)
        self.assertEqual(hash(tx), hash(other))
        self.assertNotEqual(tx, self.node.getPlug("ty"))
        self.assertNotEqual(tx, "tx")
        self.assertEqual(len({tx, other}), 1)
        self.assertEqual(MAX_LOGICAL_INDEX, 2147483647)


class PlugValiditySpecTest(_StateSpecCase):
    """削除済みのノード・アトリビュート、Undo・Redoでの有効性と例外。"""

    def test_deleted_dynamic_attribute(self):
        """deleteAttr後はisValid=False・名前は空・値と照会はRuntimeError。構造の判定は例外にしない。"""
        cmds.addAttr(self.name, longName="dynValue", attributeType="double")
        plug = self.node.getPlug("dynValue")
        plug.set(3)
        cmds.flushUndo()
        cmds.deleteAttr(self.name + ".dynValue")
        self.assertFalse(plug.isValid())
        self.assertEqual((plug.getFullName(), plug.getName(), plug.getAttrName(), str(plug)), ("", "", "", ""))
        self.assertEqual(repr(plug), "<Plug invalid>")
        self.assertFalse(plug.isArray())
        self.assertIs(type(plug), plugs.DoublePlug)
        for method in ("get", "getLongName", "getShortName", "getNiceName", "getType",
                       "getParent", "isLocked", "isKeyable", "isChannelBox", "isConnected", "isSource",
                       "isDestination", "getSource", "getDestinations", "getConnections", "getDefault", "hasMin",
                       "getMin", "isSettable", "isDynamic", "isHidden", "getAnimCurve", "isMuted", "unlock",
                       "reset", "delete", "disconnectInput"):
            with self.subTest(method=method):
                with self.assertRaises(RuntimeError):
                    getattr(plug, method)()
        for call in (lambda: plug.set(1), lambda: plug.set(1, fast=True), lambda: plug.setLocked(True),
                     lambda: plug.setIfChanged(2.0), lambda: plug.getEnumName(0),
                     lambda: plug.connect(self.node.getPlug("tx"))):
            with self.assertRaises(RuntimeError):
                call()
        self.assertEqual(plug.set(1, safe=True), 1)
        with self.assertRaises(DeletedAttributeError):
            mlib.getNode(plug)
        cmds.undo()
        self.assertTrue(plug.isValid())
        self.assertEqual(plug.get(), 3.0)
        self.assertEqual(plug.getFullName(), self.name + ".dynValue")
        cmds.redo()
        self.assertFalse(plug.isValid())

    def test_readded_attribute_is_different(self):
        """同じ名前で追加し直したアトリビュートは別のアトリビュートで、古い参照は無効のまま。"""
        cmds.addAttr(self.name, longName="dynValue", attributeType="double")
        old = self.node.getPlug("dynValue")
        cmds.deleteAttr(self.name + ".dynValue")
        cmds.addAttr(self.name, longName="dynValue", attributeType="double")
        new = self.node.getPlug("dynValue")
        self.assertFalse(old.isValid())
        self.assertTrue(new.isValid())
        self.assertNotEqual(old, new)

    def test_deleted_attribute_error_types(self):
        """DeletedAttributeErrorはValueErrorとRuntimeErrorの両方として捕捉できる。"""
        self.assertTrue(issubclass(DeletedAttributeError, ValueError))
        self.assertTrue(issubclass(DeletedAttributeError, RuntimeError))

    def test_deleted_node(self):
        """所有ノードの削除後は無効、Undoで同じ参照が再び有効になる。"""
        node = self.make("transform")
        tx = node.getPlug("tx")
        tx.set(4)
        cmds.flushUndo()
        cmds.delete(node.getFullName())
        self.assertFalse(tx.isValid())
        self.assertEqual(tx.getFullName(), "")
        self.assertEqual(repr(tx), "<Plug invalid>")
        self.assertFalse(tx.isArray())
        with self.assertRaises(RuntimeError):
            tx.get()
        with self.assertRaises(RuntimeError):
            tx.getLongName()
        with self.assertRaises(RuntimeError):
            tx.set(1)
        cmds.undo()
        self.assertTrue(tx.isValid())
        self.assertEqual(tx.get(), 4.0)
        self.assertEqual(cmds.getAttr(tx), 4.0)

    def test_plug_constructor_rejects_foreign_mplug(self):
        """所有ノードではないNodeとMPlugの組はRuntimeError。"""
        other = self.make("transform")
        with self.assertRaises(RuntimeError):
            plugs.Plug(self.node, other.getPlug("tx").mplug())

    def test_missing_element_reference_is_valid(self):
        """未作成の配列要素の参照は有効で、名前を返す。"""
        net = self.make("network")
        cmds.addAttr(net.getName(), longName="vals", attributeType="double", multi=True)
        element = net.getPlug("vals")[20]
        self.assertTrue(element.isValid())
        self.assertEqual(element.getFullName(), net.getName() + ".vals[20]")
        self.assertEqual(cmds.getAttr(net.getName() + ".vals", multiIndices=True), None)


class PlugDeleteSpecTest(_StateSpecCase):
    """Plug.deleteによる動的アトリビュートの削除。"""

    def test_delete_undo_and_lock(self):
        """deleteはNoneを返して1回のUndoで戻る。ロック中はforce/fが必要。"""
        cmds.addAttr(self.name, longName="extra", attributeType="double")
        plug = self.node.getPlug("extra")
        cmds.flushUndo()
        self.assertIsNone(plug.delete())
        self.assertFalse(cmds.attributeQuery("extra", node=self.name, exists=True))
        cmds.undo()
        self.assertTrue(plug.isValid())
        cmds.setAttr(self.name + ".extra", lock=True)
        with self.assertRaises(RuntimeError):
            plug.delete()
        self.assertTrue(cmds.attributeQuery("extra", node=self.name, exists=True))
        plug.delete(f=True)
        self.assertFalse(plug.isValid())

    def test_delete_fast_and_errors(self):
        """fastはUndoへ記録しない。静的・子アトリビュートとロックは拒否、force/f重複はTypeError。"""
        cmds.addAttr(self.name, longName="extra", attributeType="double")
        cmds.addAttr(self.name, longName="locked", attributeType="double")
        cmds.setAttr(self.name + ".locked", lock=True)
        cmds.flushUndo()
        self.node.getPlug("extra").delete(fast=True)
        self.assertFalse(cmds.attributeQuery("extra", node=self.name, exists=True))
        self.assertUndoEmpty()
        with self.assertRaises(RuntimeError):
            self.node.getPlug("locked").delete(fast=True)
        self.node.getPlug("locked").delete(fast=True, force=True)
        self.assertFalse(cmds.attributeQuery("locked", node=self.name, exists=True))
        with self.assertRaises(RuntimeError):
            self.node.getPlug("message").delete()
        with self.assertRaises(RuntimeError):
            self.node.getPlug("message").delete(fast=True)
        with self.assertRaises(RuntimeError):
            self.node.getPlug("tx").delete(fast=True)
        with self.assertRaises(TypeError):
            self.node.getPlug("message").delete(force=True, f=True)
        with self.assertRaises(TypeError):
            self.node.getPlug("message").delete(fast=1)

    def test_delete_connected_attribute_disconnects(self):
        """接続があるアトリビュートもMayaが切断して削除する。"""
        cmds.addAttr(self.name, longName="extra", attributeType="double")
        other = self.make("transform")
        cmds.connectAttr(self.name + ".extra", other.getName() + ".tx")
        self.node.getPlug("extra").delete()
        self.assertFalse(cmds.listConnections(other.getName() + ".tx", source=True, destination=False))


class PlugSetKeySpecTest(_StateSpecCase):
    """setKeyの通常経路とfastの対応範囲。"""

    def test_set_key_and_fast(self):
        """setKeyは自身を返しキーを作る。fastはUndoへ記録せず、時間・値はUI単位。"""
        cmds.currentUnit(linear="mm")
        tz = self.node.getPlug("tz")
        self.assertIs(tz.setKey(t=5, v=20), tz)
        self.assertEqual(cmds.keyframe(self.name + ".tz", query=True, timeChange=True), [5.0])
        self.assertEqual(cmds.keyframe(self.name + ".tz", query=True, valueChange=True), [20.0])
        cmds.flushUndo()
        tz.setKey(time=10, value=30, fast=True)
        self.assertEqual(cmds.keyframe(self.name + ".tz", query=True, timeChange=True), [5.0, 10.0])
        self.assertAlmostEqual(cmds.getAttr(self.name + ".tz", time=10), 30.0)
        self.assertUndoEmpty()
        tx = self.node.getPlug("tx")
        tx.setKey(t=2, v=5, fast=True)
        self.assertAlmostEqual(cmds.getAttr(self.name + ".tx", time=2), 5.0)

    def test_set_key_undo(self):
        """通常のsetKeyは1回のUndoでカーブごと戻る。"""
        cmds.flushUndo()
        self.node.getPlug("ty").setKey(t=1, v=1)
        cmds.undo()
        self.assertIsNone(cmds.keyframe(self.name + ".ty", query=True, timeChange=True))

    def test_fast_set_key_rejections(self):
        """fastは未対応のフラグ・複合・直接animCurve以外の入力・stepnextを生成前に拒否する。"""
        tz = self.node.getPlug("tz")
        other = self.make("transform")
        cmds.connectAttr(other.getName() + ".tx", self.name + ".sz")
        cases = ((NotImplementedError, lambda: tz.setKey(t=3, v=1, breakdown=True, fast=True)),
                 (TypeError, lambda: tz.setKey(t=3, time=3, fast=True)),
                 (NotImplementedError, lambda: tz.setKey(t=3, v=1, itt="stepnext", fast=True)),
                 (ValueError, lambda: tz.setKey(t=3, v=1, itt="fixed", fast=True)),
                 (NotImplementedError, lambda: self.node.getPlug("translate").setKey(t=3, fast=True)),
                 (NotImplementedError, lambda: self.node.getPlug("sz").setKey(t=3, fast=True)),
                 (TypeError, lambda: tz.setKey(t=3, fast=1)))
        for error, call in cases:
            with self.assertRaises(error):
                call()
        self.assertIsNone(cmds.keyframe(self.name + ".tz", query=True, timeChange=True))
        cmds.setAttr(self.name + ".tz", lock=True)
        with self.assertRaises(RuntimeError):
            tz.setKey(t=3, v=1, fast=True)

    def test_anim_layers_without_layers(self):
        """アニメーションレイヤーが無ければgetAnimLayersは空のlist。"""
        self.node.getPlug("tz").setKey(t=1, v=1)
        self.assertEqual(self.node.getPlug("tz").getAnimLayers(), [])


if __name__ == "__main__":
    unittest.main()
