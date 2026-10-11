"""正式コマンド・取得の省略入口と生成専用の契約を検証する。"""

from pathlib import Path
import unittest
import uuid
import maya.cmds as cmds
import mlib


class CommandNamesTest(unittest.TestCase):
    """生成の旧名は除去し、取得の省略入口とオブジェクト側の編集を確認する。"""

    def test_exports_and_files(self):
        names = dict(constraint="addConstraint", curve="createCurve", ikHandle="createIkHandle",
                     sets="createSet", group="createGroup")
        mlib.reload()
        for old, new in names.items():
            self.assertFalse(hasattr(mlib, old), old)
            self.assertFalse(hasattr(mlib.cmds, old), old)
            self.assertFalse((Path(mlib.__file__).parent / 'cmds' / (old + '.py')).exists())
            self.assertIs(getattr(mlib, new), getattr(mlib.cmds, new))
        for getter in ("getNode", "getPlug", "getScene", "getChannelBox", "getOutliner",
                       "getTimeSlider", "getViewport", "getDrivenKey"):
            name = getter[3].lower() + getter[4:]
            self.assertTrue(callable(getattr(mlib, name)))
            self.assertIn(name, mlib.__all__)
            self.assertIn(name, mlib.cmds.__all__)
            self.assertIs(getattr(mlib, name), getattr(mlib.cmds, name))
            self.assertIs(getattr(mlib, getter), getattr(mlib.cmds, getter))
        self.assertIs(mlib.ls, mlib.cmds.ls)
        self.assertFalse(hasattr(mlib, 'listNodes'))

    def test_creation_guards_and_enum_edit(self):
        node = mlib.createNode('transform', name='commandNames_' + uuid.uuid4().hex, skipSelect=True)
        try:
            enum = mlib.addAttr(node, longName='mode', attributeType='enum', enumName='one:two')
            before = set(cmds.ls(long=True))
            operations = (
                lambda: mlib.addAttr(enum, edit=True, enumName='changed'),
                lambda: mlib.createCurve(replace=True),
                lambda: mlib.createCurve(append=True),
                lambda: mlib.createIkHandle(query=True),
                lambda: mlib.createSet(query=True),
                lambda: mlib.createSet(remove=node),
                lambda: mlib.addConstraint(node, node, query=True),
                lambda: mlib.addConstraint(node, node, edit=True),
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
