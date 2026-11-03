"""10.2.0 で common に足した照会・コールバックの契約を固定する。

- Environment: バッチ判定・Maya の版・API 版を cmds.about と突き合わせる。インスタンスは作れない。
- Callbacks: シーン新規・アトリビュート変更・時間変更で呼ばれ、remove/with の後は呼ばれない。例外は握りつぶす。
- Plugin.listUnknown/removeUnknown/listUnknownNodes: 見つからないプラグインを requires するファイルの読み込みで確かめる。
- Time.getSelectedRange: バッチでは None。
"""

import os
import shutil
import tempfile
import unittest

import maya.api.OpenMaya as om2
import maya.cmds as cmds

import mlib
mlib.reload()
from mlib.common import Plugin, Time, Version
from mlib.common.callbacks import Callbacks
from mlib.common.environment import Environment
from mlib.nodes import Node
from support.specCase import NamespaceCase

_FAKE_PLUGIN = "mlibSpecFakePlugin"


class EnvironmentTest(NamespaceCase):

    def test_matches_about(self):
        """各照会は cmds.about と一致し、版の年は API 版と一致する。"""
        self.assertIs(Environment.isBatch(), bool(cmds.about(batch=True)))
        self.assertIs(Environment.isInteractive(), not cmds.about(batch=True))
        version = Environment.getMayaVersion()
        self.assertIsInstance(version, Version)
        self.assertEqual(version, Version(cmds.about(version=True)))
        api = Environment.getApiVersion()
        self.assertIsInstance(api, int)
        self.assertEqual(api, cmds.about(apiVersion=True))
        self.assertEqual(version.major, api // 10000)

    def test_no_instance(self):
        """インスタンスは作れない。"""
        self.assertRaises(TypeError, Environment)


class CallbacksTest(NamespaceCase):

    def test_attribute_changed(self):
        """setAttr で (message, Plug) が渡り、remove 後は呼ばれない。"""
        node = self.make("transform", "cb")
        calls = []
        callbacks = Callbacks()
        callback_id = callbacks.addAttributeChangedCallback(node, lambda message, plug: calls.append((message, plug)))
        self.assertIsInstance(callback_id, int)
        cmds.setAttr(node + ".translateX", 3)
        self.assertTrue(calls)
        message, plug = calls[-1]
        self.assertTrue(message & om2.MNodeMessage.kAttributeSet)
        self.assertEqual(str(plug), node + ".translateX")
        callbacks.remove()
        count = len(calls)
        cmds.setAttr(node + ".translateX", 4)
        self.assertEqual(len(calls), count)

    def test_attribute_changed_accepts_node(self):
        """Node も受け付ける。"""
        node = mlib.getNode(self.make("transform", "cbNode"))
        calls = []
        with Callbacks() as callbacks:
            callbacks.addAttributeChangedCallback(node, lambda message, plug: calls.append(plug))
            node.tx = 2
        self.assertTrue(calls)
        count = len(calls)
        node.tx = 5
        self.assertEqual(len(calls), count)

    def test_time_changed(self):
        """timeChanged のイベントで呼ばれ、with を抜けると呼ばれない。"""
        calls = []
        with Time.preserved():
            with Callbacks() as callbacks:
                callbacks.addEventCallback("timeChanged", lambda: calls.append("time"))
                cmds.currentTime(cmds.currentTime(query=True) + 1)
            self.assertEqual(calls, ["time"])
            cmds.currentTime(cmds.currentTime(query=True) + 1)
        self.assertEqual(calls, ["time"])

    def test_scene_new(self):
        """afterNew はシーン新規で呼ばれ、remove 後は呼ばれない(この試験だけ新規シーンにする)。"""
        calls = []
        callbacks = Callbacks()
        callbacks.addSceneCallback("beforeNew", lambda: calls.append("before"))
        callbacks.addSceneCallback("afterNew", lambda: calls.append("after"))
        cmds.file(new=True, force=True)
        self.assertEqual(calls, ["before", "after"])
        callbacks.remove()
        cmds.file(new=True, force=True)
        self.assertEqual(calls, ["before", "after"])
        # 名前空間は新規シーンで消えたので、tearDown のために作り直す。
        cmds.namespace(add=self.ns)

    def test_exception_is_swallowed(self):
        """コールバックの例外は警告になり、後続の処理と他のコールバックを止めない。"""
        calls = []

        def fail():
            raise ValueError("boom")

        with Time.preserved():
            with Callbacks() as callbacks:
                callbacks.addEventCallback("timeChanged", fail)
                callbacks.addEventCallback("timeChanged", lambda: calls.append("ok"))
                cmds.currentTime(cmds.currentTime(query=True) + 1)
        self.assertEqual(calls, ["ok"])

    def test_remove_is_repeatable(self):
        """remove は何度呼んでもよい。with を入れ子にすると RuntimeError。"""
        callbacks = Callbacks()
        callbacks.addEventCallback("SelectionChanged", lambda: None)
        callbacks.remove()
        callbacks.remove()
        with callbacks:
            with self.assertRaises(RuntimeError):
                with callbacks:
                    pass

    def test_errors(self):
        """不正な入力は例外で、登録は残さない。"""
        callbacks = Callbacks()
        cases = [
            (ValueError, callbacks.addSceneCallback, "afterOpenTypo", lambda: None),
            (ValueError, callbacks.addSceneCallback, "beforeSaveCheck", lambda: None),
            (ValueError, callbacks.addSceneCallback, "AfterOpen", lambda: None),
            (TypeError, callbacks.addSceneCallback, 1, lambda: None),
            (TypeError, callbacks.addSceneCallback, "afterOpen", None),
            (ValueError, callbacks.addEventCallback, "noSuchEvent", lambda: None),
            (TypeError, callbacks.addEventCallback, None, lambda: None),
            (TypeError, callbacks.addEventCallback, "timeChanged", 3),
            (RuntimeError, callbacks.addAttributeChangedCallback, self.name("missing"), lambda m, p: None),
            (TypeError, callbacks.addAttributeChangedCallback, 1.5, lambda m, p: None),
            (TypeError, callbacks.addAttributeChangedCallback, self.make("transform", "err"), "x"),
        ]
        for error, method, first, second in cases:
            with self.subTest(method=method.__name__, first=first):
                self.assertRaises(error, method, first, second)
        self.assertEqual(callbacks._ids, [])


class UnknownPluginTest(NamespaceCase):

    def setUp(self):
        super().setUp()
        self.folder = tempfile.mkdtemp(prefix="mlibSpecUnknown")
        path = os.path.join(self.folder, "unknown.ma")
        with open(path, "w", encoding="utf-8") as stream:
            stream.write(
                "//Maya ASCII 2022 scene\n"
                f'requires "{_FAKE_PLUGIN}" "1.0";\n'
                'createNode mlibSpecFakeType -n "fakeNode";\n'
                'createNode transform -n "fakeParent";\n'
                'createNode mlibSpecFakeShape -n "fakeShape" -p "fakeParent";\n')
        try:
            cmds.file(path, i=True, namespace=self.ns, mergeNamespacesOnClash=True)
        except RuntimeError:
            # 見つからないプラグインの requires は読み込みの最後にエラーになるが、ノードは読み込まれる。
            pass

    def tearDown(self):
        if _FAKE_PLUGIN in (cmds.unknownPlugin(query=True, list=True) or []):
            cmds.unknownPlugin(_FAKE_PLUGIN, remove=True)
        shutil.rmtree(self.folder, ignore_errors=True)
        super().tearDown()

    def test_list_and_remove(self):
        """listUnknown・listUnknownNodes は cmds と一致し、removeUnknown は外した名前を返す。"""
        self.assertIn(_FAKE_PLUGIN, Plugin.listUnknown())
        self.assertEqual(Plugin.listUnknown(), cmds.unknownPlugin(query=True, list=True))
        nodes = [node for node in Plugin.listUnknownNodes() if node.getNodeName().startswith(self.ns + ":")]
        for node in nodes:
            self.assertIsInstance(node, Node)
        self.assertEqual(sorted(node.getType() for node in nodes), ["unknown", "unknownDag"])
        expected = cmds.ls(type=["unknown", "unknownDag", "unknownTransform"], long=True)
        self.assertEqual([node.getFullName() for node in Plugin.listUnknownNodes()], expected)
        self.assertEqual(Plugin.removeUnknown(_FAKE_PLUGIN), [_FAKE_PLUGIN])
        self.assertNotIn(_FAKE_PLUGIN, Plugin.listUnknown())

    def test_remove_all(self):
        """names=None は未知のプラグインをすべて外す。"""
        before = Plugin.listUnknown()
        self.assertEqual(Plugin.removeUnknown(), before)
        self.assertEqual(Plugin.listUnknown(), [])

    def test_errors(self):
        """未知でない名前は ValueError で何も外さず、型の違いは TypeError。"""
        self.assertRaises(ValueError, Plugin.removeUnknown, [_FAKE_PLUGIN, "mlibSpecNotUnknown"])
        self.assertIn(_FAKE_PLUGIN, Plugin.listUnknown())
        self.assertRaises(TypeError, Plugin.removeUnknown, 1)
        self.assertRaises(TypeError, Plugin.removeUnknown, [_FAKE_PLUGIN, 2])


class SelectedRangeTest(NamespaceCase):

    def test_batch_returns_none(self):
        """バッチでは範囲を選べないので None。不正な単位は ValueError。"""
        if not cmds.about(batch=True):
            self.skipTest("batch only")
        self.assertIsNone(Time.getSelectedRange())
        self.assertIsNone(Time.getSelectedRange(timeUnit="sec"))
        self.assertRaises(ValueError, Time.getSelectedRange, timeUnit="minute")


if __name__ == "__main__":
    unittest.main()
