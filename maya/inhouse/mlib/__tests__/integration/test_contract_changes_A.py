"""2026-10-26 に変えた約束(担当A)を実Mayaで検証する。

対象は、disconnect の戻り値(src を渡した場合はそのPlug、省略時は取得した入力元Plugを返し、
名前から取り直さない)、削除の一括化(通常は1回の cmds.delete、fast は1つの MDagModifier の
doIt 1回。ロック・参照・削除できないノードを含む場合は何も削除せずに RuntimeError)、
fast で既定・共有ノードを削除しても異常終了せずに例外になること、
無効なノードの getHistory が RuntimeError になることとする。
"""

import os
import re
import sys
import tempfile
import unittest
import uuid

import maya.api.OpenMaya as om2
import maya.cmds as cmds

import mlib
mlib.reload()


def _unlock_and_remove(namespace):
    """名前空間内のロックを外して、名前空間ごと削除する。

    Args:
        namespace (str): 削除する名前空間。
    """
    if not cmds.namespace(exists=namespace):
        return
    for node in cmds.ls(namespace + ":*", long=True) or []:
        if cmds.objExists(node) and cmds.lockNode(node, query=True, lock=True)[0]:
            cmds.lockNode(node, lock=False)
    cmds.namespace(removeNamespace=namespace, deleteNamespaceContent=True)


class DisconnectReturnTest(unittest.TestCase):
    """disconnect が手元の入力元Plugを返し、名前から取り直さないことを確かめる。"""

    def setUp(self):
        self.ns = "mlibContractA_" + uuid.uuid4().hex
        cmds.namespace(add=self.ns)
        self.a = cmds.createNode("transform", name=self.ns + ":a")
        self.b = cmds.createNode("transform", name=self.ns + ":b")
        self.bs = cmds.createNode("blendShape", name=self.ns + ":bs")

    def tearDown(self):
        _unlock_and_remove(self.ns)

    def test_explicit_source_is_returned_as_is(self):
        """Plug を渡すとそのオブジェクト、MPlug・名前は解決したPlugを返す(fast・通常)。"""
        node_a, node_b = mlib.getNode(self.a), mlib.getNode(self.b)
        for fast in (False, True):
            for mode in ("plug", "mplug", "string"):
                with self.subTest(fast=fast, mode=mode):
                    cmds.connectAttr(self.a + ".tx", self.b + ".tx")
                    source = node_a.getPlug("tx")
                    value = {"plug": source, "mplug": source.mplug(), "string": self.a + ".tx"}[mode]
                    result = node_b.getPlug("tx").disconnect(value, fast=fast)
                    if mode == "plug":
                        self.assertIs(result, source)
                    self.assertIsInstance(result, mlib.plugs.Plug)
                    self.assertEqual(result, source)
                    self.assertFalse(cmds.isConnected(self.a + ".tx", self.b + ".tx"))

    def test_omitted_source_returns_acquired_plug(self):
        """省略時は切断前に取得した入力元Plugを返し、切断後も同じアトリビュートを指す。"""
        node_b, node_bs = mlib.getNode(self.b), mlib.getNode(self.bs)
        for fast in (False, True):
            with self.subTest(fast=fast):
                cmds.connectAttr(self.a + ".r", self.b + ".r")
                cmds.connectAttr(self.a + ".ty", self.bs + ".weight[2]")
                result = node_b.getPlug("r").disconnect(fast=fast)
                self.assertEqual(result.getFullName(), mlib.getNode(self.a).getPlug("r").getFullName())
                self.assertIsInstance(result, mlib.plugs.CompoundPlug)
                element = node_bs.getPlug("weight[2]").disconnect(fast=fast)
                self.assertEqual(element.getFullName(), mlib.getNode(self.a).getPlug("ty").getFullName())
                self.assertTrue(element.isValid())

    def test_alias_source_resolves_to_real_attribute(self):
        """エイリアス名で渡した入力元も、解決したPlug(実際のアトリビュート)を返す。"""
        cmds.addAttr(self.a, longName="driver", attributeType="double")
        cmds.aliasAttr("drv", self.a + ".driver")
        cmds.connectAttr(self.a + ".driver", self.b + ".sx")
        result = mlib.getNode(self.b).getPlug("sx").disconnect(self.a + ".drv")
        self.assertEqual(result, mlib.getNode(self.a).getPlug("driver"))
        self.assertFalse(cmds.isConnected(self.a + ".driver", self.b + ".sx"))


class BatchDeleteTest(unittest.TestCase):
    """削除を1回にまとめ、削除できない対象があれば何も削除しないことを確かめる。"""

    def setUp(self):
        self.ns = "mlibContractA_" + uuid.uuid4().hex
        cmds.namespace(add=self.ns)
        self.state = cmds.undoInfo(query=True, state=True)
        cmds.undoInfo(state=True)

    def tearDown(self):
        cmds.undoInfo(state=self.state)
        if cmds.objExists("|" + self.ns + ":g|persp"):
            cmds.parent("|" + self.ns + ":g|persp", world=True)
        _unlock_and_remove(self.ns)

    def _make(self, *names):
        return [cmds.createNode("transform", name=self.ns + ":" + name) for name in names]

    def test_single_cmds_delete_and_undo(self):
        """通常経路は cmds.delete を1回だけ呼び、Mayaの一括削除と同じ順で消え、1回のUndoで戻る。"""
        names = self._make("d0", "d1", "d2")
        child = cmds.createNode("transform", name=self.ns + ":dc", parent=names[0])
        md = cmds.createNode("multiplyDivide", name=self.ns + ":dmd")
        cmds.connectAttr(md + ".outputX", names[1] + ".tx")
        calls = []
        original = cmds.delete

        def counting(*args, **kwargs):
            calls.append(args)
            return original(*args, **kwargs)

        removed = []
        callback = om2.MDGMessage.addNodeRemovedCallback(
            lambda obj, _data: removed.append(om2.MFnDependencyNode(obj).name()), "dependNode")
        before = sorted(cmds.ls(long=True))
        cmds.delete = counting
        try:
            mlib.delete([child, md] + names)
        finally:
            cmds.delete = original
            om2.MMessage.removeCallback(callback)
        self.assertEqual(len(calls), 1)
        short = [name.rpartition(":")[2] for name in removed]
        # 渡した順(dc, dmd, d0...)ではなく、Mayaがまとめて削除するときの順になる。
        self.assertEqual(short, ["dc", "d0", "dmd", "d1", "d2"])
        self.assertRegex(cmds.undoInfo(query=True, undoName=True), r"^mlib delete( |$)")
        cmds.undo()
        self.assertEqual(sorted(cmds.ls(long=True)), before)

    def test_locked_node_deletes_nothing(self):
        """ロックされたノード・ロックされた子・参照のノードが含まれると、何も削除しない。"""
        for fast in (False, True):
            with self.subTest(fast=fast):
                names = self._make("l0", "l1", "l2")
                cmds.lockNode(names[2], lock=True)
                short = re.escape(names[2])
                pattern = "Node is locked or referenced: " + short if fast else "Cannot delete locked node '" + short
                with self.assertRaisesRegex(RuntimeError, pattern):
                    mlib.delete(names, fast=fast)
                self.assertEqual([cmds.objExists(name) for name in names], [True] * 3)
                cmds.lockNode(names[2], lock=False)
                parent = self._make("lp")[0]
                child = cmds.createNode("transform", name=self.ns + ":lc", parent=parent)
                cmds.lockNode(child, lock=True)
                pattern = ("Node is locked or referenced: " + re.escape(child) if fast
                           else "Cannot delete '" + re.escape(parent) + "' as it has locked or read-only children")
                with self.assertRaisesRegex(RuntimeError, pattern):
                    mlib.delete(names + [parent], fast=fast)
                with self.assertRaisesRegex(RuntimeError, pattern):
                    mlib.getNode(parent).delete(fast=fast)
                self.assertTrue(all(cmds.objExists(name) for name in names + [parent, child]))
                cmds.lockNode(child, lock=False)
                mlib.delete(names + [parent], fast=fast)
                self.assertFalse(any(cmds.objExists(name) for name in names + [parent, child]))

    def test_default_and_shared_nodes_fail_without_crash(self):
        """既定・共有ノード(time1・persp・defaultLayer・lambert1)は fast でも異常終了せず例外になる。"""
        others = self._make("n0", "n1")
        for fast in (False, True):
            for target in ("time1", "persp", "defaultLayer", "lambert1", "perspShape"):
                with self.subTest(fast=fast, target=target):
                    with self.assertRaisesRegex(RuntimeError, "Non-deletable node '" + target + "'"):
                        mlib.delete(others + [target], fast=fast)
                    with self.assertRaisesRegex(RuntimeError, "Non-deletable node"):
                        mlib.getNode(target).delete(fast=fast)
                    self.assertTrue(all(cmds.objExists(name) for name in others + [target]))
            with self.subTest(fast=fast, target="d*"):
                with self.assertRaisesRegex(RuntimeError, "Non-deletable node"):
                    mlib.delete("d*", fast=fast)
                self.assertTrue(cmds.objExists("defaultLayer"))
        # 削除できないノードを子に持つ親も、何も削除しない。
        group = self._make("g")[0]
        cmds.parent("persp", group)
        for fast in (False, True):
            with self.subTest(fast=fast, target="undeletable child"):
                with self.assertRaisesRegex(RuntimeError, "Non-deletable node 'persp'"):
                    mlib.delete(others + [group], fast=fast)
                self.assertTrue(all(cmds.objExists(name) for name in others + [group]))

    def test_user_shared_node_can_be_deleted(self):
        """利用者が shared で作ったノードは cmds.delete と同じく削除できる(isShared だけで拒否しない)。"""
        for fast in (False, True):
            with self.subTest(fast=fast):
                name = cmds.createNode("multiplyDivide", name=self.ns + ":shared", shared=True)
                mlib.delete(name, fast=fast)
                self.assertFalse(cmds.objExists(name))

    def test_referenced_node_deletes_nothing(self):
        """参照のノードを含むと、通常・fast とも何も削除しない。"""
        path = os.path.join(tempfile.gettempdir(), "mlibContractA_" + uuid.uuid4().hex + ".ma").replace("\\", "/")
        current = cmds.file(query=True, sceneName=True)
        modified = cmds.file(query=True, modified=True)
        source = cmds.createNode("transform", name="mlibContractA_refT_" + uuid.uuid4().hex)
        cmds.select(source)
        cmds.file(path, exportSelected=True, type="mayaAscii", force=True)
        cmds.delete(source)
        reference = cmds.file(path, reference=True, namespace=self.ns + "_ref")
        try:
            ref_node = cmds.ls(self.ns + "_ref:" + source, long=True)[0]
            local = self._make("r0")[0]
            for fast in (False, True):
                with self.subTest(fast=fast):
                    # 5.0.0から通常・fastとも参照ノードであることと参照元を示す。
                    pattern = "it is a referenced node from reference '" + self.ns + "_refRN'"
                    with self.assertRaisesRegex(RuntimeError, pattern):
                        mlib.delete([local, ref_node], fast=fast)
                    self.assertTrue(cmds.objExists(local) and cmds.objExists(ref_node))
        finally:
            cmds.file(reference, removeReference=True)
            if os.path.exists(path):
                os.remove(path)
            if current and not modified:
                cmds.file(modified=False)

    def test_duplicates_parent_child_and_cascade(self):
        """重複・親子の両方・連鎖して消えるノード・インスタンスを含めても、1回で全部消える。"""
        for fast in (False, True):
            with self.subTest(fast=fast):
                a, b, parent = self._make("a", "b", "p")
                child = cmds.createNode("transform", name=self.ns + ":c", parent=parent)
                cmds.connectAttr(a + ".rx", b + ".ty")
                conversion = cmds.listConnections(b + ".ty", source=True, destination=False)[0]
                cube, history = cmds.polyCube(name=self.ns + ":cube")
                md = cmds.createNode("multiplyDivide", name=self.ns + ":md")
                cmds.connectAttr(a + ".ry", md + ".input1X")
                md_conversion = cmds.listConnections(md + ".input1X", source=True, destination=False)[0]
                targets = [child, parent, parent, b, conversion, cube, history, md, md_conversion]
                mlib.delete(targets, fast=fast)
                self.assertFalse(any(cmds.objExists(name) for name in targets))
                self.assertTrue(cmds.objExists(a))
                # インスタンスされた子は、親の削除後も残る別のインスタンスから消える(従来と同じ)。
                first, second = self._make("ia", "ib")
                cmds.createNode("transform", name=self.ns + ":ix", parent=first)
                shared = cmds.ls(self.ns + ":ix", long=True)[0]
                cmds.parent(shared, second, addObject=True)
                mlib.delete([first, shared], fast=fast)
                self.assertFalse(cmds.objExists(first))
                self.assertEqual(cmds.ls(self.ns + ":ix", long=True, allPaths=True), [])
                self.assertTrue(cmds.objExists(second))
                mlib.delete([a, second], fast=fast)

    def test_missing_name_deletes_nothing(self):
        """存在しない名前を含むと、従来どおり RuntimeError で何も削除しない。"""
        names = self._make("m0")
        for fast in (False, True):
            with self.subTest(fast=fast):
                with self.assertRaises(RuntimeError):
                    mlib.delete(names + [self.ns + ":missing"], fast=fast)
                self.assertTrue(cmds.objExists(names[0]))


class HistoryInvalidNodeTest(unittest.TestCase):
    """無効なノードの getHistory が RuntimeError になることを確かめる。"""

    def test_deleted_node_raises_runtime_error(self):
        node = mlib.getNode(cmds.createNode("transform", name="mlibContractA_history_" + uuid.uuid4().hex))
        cmds.delete(node.getFullName())
        with self.assertRaisesRegex(RuntimeError, r"Cannot get the history of an invalid \w+"):
            node.getHistory()
        with self.assertRaisesRegex(RuntimeError, r"invalid \w+"):
            node.getHistory(future=True)

    def test_history_matches_cmds_order(self):
        """まとめて解決した getHistory は、listHistory の順(自身と重複を除く)と同じ。"""
        cube, maker = cmds.polyCube(name="mlibContractA_hist_" + uuid.uuid4().hex)
        try:
            shape = cmds.listRelatives(cube, shapes=True, fullPath=True)[0]
            expected = [name for name in cmds.listHistory(shape) if cmds.ls(name, long=True) != [shape]]
            result = mlib.getNode(shape).getHistory()
            self.assertEqual([node.getName() for node in result],
                             [cmds.ls(name)[0] for name in expected])
            self.assertIn(maker, [node.getName() for node in result])
        finally:
            cmds.delete(cube)


class DestroyedNodeTest(unittest.TestCase):
    """Undo の記録から消えて破棄されたノードの基本メソッドが、異常終了せず RuntimeError になる。"""

    def test_destroyed_node_basic_queries_raise(self):
        state = cmds.undoInfo(query=True, state=True)
        node = mlib.getNode(cmds.createNode("multiplyDivide", name="mlibContractA_dead_" + uuid.uuid4().hex))
        cmds.undoInfo(state=False)
        try:
            cmds.delete(node.getFullName())
            cmds.flushUndo()
        finally:
            cmds.undoInfo(state=state)
        if node.isAlive():
            self.skipTest("the deleted node is still alive in this Maya version")
        for method in ("getType", "getTypeId", "getPluginName", "isLocked", "isFromReferencedFile",
                       "getClassification"):
            with self.subTest(method=method):
                with self.assertRaisesRegex(RuntimeError, r"Cannot access an invalid \w+"):
                    getattr(node, method)()
        # 5.0.0から名前の取得は無効なノードでRuntimeError。str()だけは空文字列を返す。
        for method in ("getName", "getNodeName"):
            with self.subTest(method=method):
                with self.assertRaisesRegex(RuntimeError, r"was deleted or undone; check isValid\(\)"):
                    getattr(node, method)()
        self.assertEqual(str(node), "")
        self.assertFalse(node.isType("multiplyDivide"))


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
