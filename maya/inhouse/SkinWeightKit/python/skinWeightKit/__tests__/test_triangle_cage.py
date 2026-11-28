"""Triangle cage deformation, selective repair and portable binding regression tests."""

import json
from pathlib import Path
import tempfile
import unittest

from maya import cmds
from skinWeightKit.core import cage


class CageTests(unittest.TestCase):
    def test_edit_save_restore(self):
        cmds.file(new=True, force=True)
        driver = cmds.polyPlane(sx=2, sy=1)[0]
        driven = cmds.polyPlane(sx=3, sy=2)[0]
        cmds.move(2, 0, 0, driver, driven, relative=True)
        cmds.move(0, 2, 0, driven, relative=True)

        def point():
            return cmds.pointPosition(driven + ".vtx[0]", world=True)

        rest = point()
        node = cage.bind(driver, driven)
        self.assertEqual(point(), rest)
        old = json.loads(cmds.getAttr(node + ".binding"))
        cmds.move(0, 3, 0, driver, relative=True)
        moved = point()
        self.assertAlmostEqual(moved[1] - rest[1], 3)
        cage.bind(driver, driven, [1, 2], 0)
        new = json.loads(cmds.getAttr(node + ".binding"))
        self.assertNotEqual(old["rows"][1], new["rows"][1])
        for i, row in enumerate(old["rows"]):
            if i not in (1, 2):
                self.assertEqual(row, new["rows"][i])
        cmds.undo()
        self.assertEqual(json.loads(cmds.getAttr(node + ".binding")), old)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "binding.json"
            cage.save(driven, path)
            cmds.delete(node)
            self.assertEqual(point(), rest)
            cage.restore(driver, driven, path)
            self.assertEqual(point(), moved)
            other = cmds.polyCube()[0]
            with self.assertRaises(ValueError):
                cage.restore(driver, other, path)

    def test_fresh_scene_and_shared_cage(self):
        """同じケージの2対象が別シーンで同じ軌道へ復帰し、親移動を二重に適用しない。"""
        def setup():
            cmds.file(new=True, force=True)
            driver = cmds.polyPlane(sx=1, sy=2)[0]
            targets = [cmds.polyPlane(sx=2, sy=1)[0] for _ in range(2)]
            for i, target in enumerate(targets):
                cmds.move(0, i + 1, 0, target)
            root = cmds.group(driver, *targets, name="assembly")
            return driver, targets, root

        def sample(driver, targets):
            rows = []
            for angle in (0, 22, -36):
                cmds.setAttr(driver + ".rotateZ", angle)
                rows.append([cmds.pointPosition(target + ".vtx[0]", world=True) for target in targets])
            return rows

        with tempfile.TemporaryDirectory() as folder:
            drv, targets, root = setup()
            files = [Path(folder) / ("target%d.json" % i) for i in range(2)]
            for mesh, filename in zip(targets, files):
                cage.bind(drv, mesh)
                cage.save(mesh, filename)
            expected = sample(drv, targets)
            drv, targets, root = setup()
            for mesh, filename in zip(targets, files):
                cage.restore(drv, mesh, filename)
            cmds.setAttr(root + ".translateX", 20)
            actual = sample(drv, targets)
            for pose, shifted in zip(expected, actual):
                for a, b in zip(pose, shifted):
                    for axis, offset in enumerate((20, 0, 0)):
                        self.assertAlmostEqual(a[axis] + offset, b[axis], places=5)
            # Same vertex and face counts but different winding must be rejected.
            wrong = cmds.polyPlane(sx=2, sy=1)[0]
            cmds.polyNormal(wrong, normalMode=0, constructionHistory=False)
            with self.assertRaises(ValueError):
                cage.restore(drv, wrong, files[0])

    def test_two_vertices_repaired_without_weight_changes(self):
        """隣り合う2面の誤対応を直し、対象外の変形と全スキンウェイトを照合する。"""
        cmds.file(new=True, force=True)
        lower = cmds.polyPlane(sx=1, sy=1)[0]
        upper = cmds.duplicate(lower)[0]
        cmds.move(0, 0.2, 0, upper)
        driver = cmds.polyUnite(lower, upper, constructionHistory=False)[0]
        mesh = cmds.polyPlane(sx=2, sy=1)[0]
        cmds.select(clear=True)
        left = cmds.joint(position=(-1, 0, 0))
        right = cmds.joint(position=(1, 0, 0))
        skin = cmds.skinCluster(left, right, mesh, toSelectedBones=True)[0]

        def sample():
            return [cmds.pointPosition(f"{mesh}.vtx[{i}]", world=True) for i in range(6)]

        def weights():
            return [cmds.skinPercent(skin, f"{mesh}.vtx[{i}]", query=True, value=True) for i in range(6)]

        stored = weights()
        expected = sample()
        cage.bind(driver, mesh)
        cage.bind(driver, mesh, [1, 4], 1)
        cmds.move(0, 2, 0, driver + ".f[1]", relative=True)
        wrong = sample()
        cmds.undo()
        cage.bind(driver, mesh, [1, 4], 0)
        cmds.move(0, 2, 0, driver + ".f[1]", relative=True)
        fixed = sample()
        for i in (1, 4):
            self.assertAlmostEqual(wrong[i][1] - expected[i][1], 2)
            self.assertAlmostEqual(fixed[i][1], expected[i][1])
        self.assertEqual([p for i,p in enumerate(fixed) if i not in (1,4)], [p for i,p in enumerate(wrong) if i not in (1,4)])
        self.assertEqual(stored, weights())
