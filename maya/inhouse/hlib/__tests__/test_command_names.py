"""動詞を用いたコマンド公開と生成専用の契約を検証する。"""

from pathlib import Path
import unittest
import uuid
import maya.cmds as cmds
import hlib


class CommandNamesTest(unittest.TestCase):
    """旧名の除去とオブジェクト側の編集を確認する。"""

    def test_exports_and_files(self):
        names = dict(constraint="addConstraint", curve="createCurve", ikHandle="createIkHandle",
                     sets="createSet", group="createGroup", node="getNode", plug="getPlug",
                     scene="getScene", channelBox="getChannelBox", outliner="getOutliner",
                     timeSlider="getTimeSlider", viewport="getViewport", drivenKey="getDrivenKey")
        hlib.reload()
        for old, new in names.items():
            if old == "scene":
                # 旧sceneコマンドは廃止しても、正式なsceneパッケージは公開する。
                self.assertFalse(callable(hlib.scene))
                self.assertEqual(hlib.scene.__name__, "hlib.scene")
            else:
                self.assertFalse(hasattr(hlib, old), old)
            self.assertFalse(hasattr(hlib.cmds, old), old)
            self.assertFalse((Path(hlib.__file__).parent / 'cmds' / (old + '.py')).exists())
            self.assertIs(getattr(hlib, new), getattr(hlib.cmds, new))
        self.assertIs(hlib.ls, hlib.cmds.ls)
        self.assertFalse(hasattr(hlib, 'listNodes'))

    def test_creation_guards_and_enum_edit(self):
        node = hlib.createNode('transform', name='commandNames_' + uuid.uuid4().hex, skipSelect=True)
        try:
            enum = hlib.addAttr(node, longName='mode', attributeType='enum', enumName='one:two')
            before = set(cmds.ls(long=True))
            operations = (
                lambda: hlib.addAttr(enum, edit=True, enumName='changed'),
                lambda: hlib.createCurve(replace=True),
                lambda: hlib.createCurve(append=True),
                lambda: hlib.createIkHandle(query=True),
                lambda: hlib.createSet(query=True),
                lambda: hlib.createSet(remove=node),
                lambda: hlib.addConstraint(node, node, query=True),
                lambda: hlib.addConstraint(node, node, edit=True),
            )
            for operation in operations:
                with self.assertRaises(ValueError):
                    operation()
            self.assertEqual(set(cmds.ls(long=True)), before)
            enum.setEnumNames(['local', 'world', 'foot'])
            self.assertEqual(enum.getEnumValue('foot'), 2)
            cmds.undo()
            self.assertEqual(enum.getEnumValue('two'), 1)
            cmds.redo()
            self.assertEqual(enum.getEnumValue('world'), 1)
        finally:
            node.delete()
