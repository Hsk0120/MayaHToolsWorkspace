"""統合したconstraintコマンドのフラグ・戻り値・Undoを検証する。"""

import unittest
import uuid
from pathlib import Path
import maya.cmds as cmds
import hlib


class UnifiedConstraintTest(unittest.TestCase):
    """削除した個別コマンドの機能を統合入口から確認する。"""

    def setUp(self):
        self.selection = cmds.ls(selection=True, long=True) or []
        self.namespace = ":constraintTest_" + uuid.uuid4().hex
        self.previous = cmds.namespaceInfo(currentNamespace=True, absoluteName=True)
        cmds.namespace(add=self.namespace)
        cmds.namespace(set=self.namespace)
        self.source = hlib.createNode("transform", name="source", skipSelect=True)
        self.target = hlib.createNode("transform", name="target", skipSelect=True)
        self.up = hlib.createNode("transform", name="up", skipSelect=True)
        self.source.getPlug("translateZ").set(5)
        self.up.getPlug("translateY").set(5)

    def tearDown(self):
        cmds.namespace(set=self.previous)
        cmds.namespace(removeNamespace=self.namespace, deleteNamespaceContent=True)
        cmds.select(self.selection, replace=True) if self.selection else cmds.select(clear=True)

    def test_aim_flags_queries_edit_and_undo(self):
        result = hlib.addConstraint(
            self.source,
            self.target,
            typ="aim",
            aim=(0, 0, 1),
            u=(0, 1, 0),
            wut="object",
            wuo=self.up,
        )
        self.assertEqual(result.getType(), "aimConstraint")
        self.assertEqual(
            result.getPlug("worldUpMatrix").getSourceWithConversion().getNode().getUuid(), self.up.getUuid()
        )
        self.assertEqual(
            result.getTargets()[0].getUuid(), self.source.getUuid()
        )
        weight = result.getWeightPlugs()[0]
        result.setWeight(0.25)
        self.assertAlmostEqual(weight.get(), 0.25)
        cmds.undo()
        self.assertAlmostEqual(weight.get(), 1.0)
        name = result.getFullName()
        cmds.undo()
        self.assertFalse(cmds.objExists(name))
        cmds.redo()
        self.assertTrue(cmds.objExists(name))

    def test_parent_orient_and_transform_creation(self):
        for kind in ("parent", "orient"):
            with self.subTest(kind=kind):
                result = self.target.addConstraint(self.source, type=kind, weight=0.3)
                self.assertEqual(result.getType(), kind + "Constraint")
                self.assertAlmostEqual(result.getWeights()[0], 0.3)
                cmds.delete(result.getFullName())

    def test_conflicting_flags_and_modes_do_not_create_nodes(self):
        before = set(cmds.ls())
        with self.assertRaises(TypeError):
            hlib.addConstraint(
                self.source, self.target, type="aim", wuo=self.up, worldUpObject=self.up
            )
        with self.assertRaises(ValueError):
            self.target.addConstraint(self.source, type="aim", q=True)
        with self.assertRaises(ValueError):
            hlib.addConstraint(self.source, self.target, type="aim", query=True, edit=True)
        self.assertEqual(set(cmds.ls()), before)

    def test_individual_command_exports_and_files_are_removed(self):
        for name in (
            "aimConstraint",
            "parentConstraint",
            "orientConstraint",
            "poleVectorConstraint",
        ):
            self.assertFalse(hasattr(hlib, name))
            self.assertFalse(hasattr(hlib.cmds, name))
            self.assertFalse((Path(hlib.__file__).parent / "cmds" / (name + ".py")).exists())
