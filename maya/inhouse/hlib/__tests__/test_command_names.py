"""正式コマンド・取得の省略入口と生成専用の契約を検証する。"""

from pathlib import Path
import unittest
import uuid
import maya.cmds as cmds
import hlib


class CommandNamesTest(unittest.TestCase):
    """生成の旧名は除去し、取得の省略入口とオブジェクト側の編集を確認する。"""

    def test_exports_and_files(self):
        names = dict(constraint="addConstraint", curve="createCurve", ikHandle="createIkHandle",
                     sets="createSet", group="createGroup")
        hlib.reload()
        for old, new in names.items():
            self.assertFalse(hasattr(hlib, old), old)
            self.assertFalse(hasattr(hlib.cmds, old), old)
            self.assertFalse((Path(hlib.__file__).parent / 'cmds' / (old + '.py')).exists())
            self.assertIs(getattr(hlib, new), getattr(hlib.cmds, new))
        for getter in ("getNode", "getPlug", "getScene", "getChannelBox", "getOutliner",
                       "getTimeSlider", "getViewport", "getDrivenKey"):
            name = getter[3].lower() + getter[4:]
            self.assertTrue(callable(getattr(hlib, name)))
            self.assertIn(name, hlib.__all__)
            self.assertIn(name, hlib.cmds.__all__)
            self.assertIs(getattr(hlib, name), getattr(hlib.cmds, name))
            self.assertIs(getattr(hlib, getter), getattr(hlib.cmds, getter))
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
