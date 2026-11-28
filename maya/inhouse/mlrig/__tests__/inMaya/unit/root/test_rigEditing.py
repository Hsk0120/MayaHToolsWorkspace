"""補正先の列編集と形状ポートで、対象外の状態とUndoを確認する。"""

import tempfile
import unittest
from pathlib import Path

from maya import cmds

from mlrig import publishedChannels, skinDriverTargets, skinSurface


class RigEditingTest(unittest.TestCase):
    def setUp(self):
        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)

    def test_new_column_keeps_existing_weights(self):
        """ゼロ列の追加・解除とUndoで、元の仕上がりを保つ。"""
        mesh = cmds.polyPlane(subdivisionsX=1, subdivisionsY=1)[0]
        shape = cmds.listRelatives(mesh, shapes=True, fullPath=True)[0]
        joint = cmds.createNode("joint")
        skin = cmds.skinCluster(joint, mesh, toSelectedBones=True)[0]
        locator = cmds.spaceLocator()[0]
        driver = skinDriverTargets.create(shape, locator)
        index, added = skinDriverTargets.addColumn(driver, locator + ".scaleX")
        self.assertEqual(skinDriverTargets.apply(driver)[cmds.ls(locator, long=True)[0] + ".scaleX"], 0.0)
        skinDriverTargets.removeTarget(driver, index)
        self.assertEqual(cmds.skinCluster(skin, query=True, influence=True), [joint])
        cmds.undo()
        self.assertIn(added, cmds.skinCluster(skin, query=True, influence=True))
        for i in range(4):
            self.assertEqual(cmds.skinPercent(skin, mesh + ".vtx[{}]".format(i), query=True, transform=joint), 1.0)

    def test_skin_sample_uses_world_distance_and_face_scope(self):
        """非一様スケールで最近面が逆転する2面の既知ウェイトを照合する。"""
        first = cmds.polyCreateFacet(point=[(1, -1, -1), (1, 1, -1), (1, 0, 1)])[0]
        second = cmds.polyCreateFacet(point=[(-1, -1, 2), (1, -1, 2), (0, 1, 2)])[0]
        mesh = cmds.polyUnite(first, second, constructionHistory=False)[0]
        cmds.setAttr(mesh + ".scale", 10, 1, 0.1)
        shape = cmds.listRelatives(mesh, shapes=True, fullPath=True)[0]
        joints = [cmds.createNode("joint") for _ in range(2)]
        skin = cmds.skinCluster(joints, mesh, toSelectedBones=True)[0]
        for i, weight in enumerate((1, 1, 1, 0, 0, 1)):
            cmds.skinPercent(skin, mesh + ".vtx[{}]".format(i), transformValue=[(joints[0], weight), (joints[1], 1 - weight)])
        locator = cmds.spaceLocator()[0]
        joint = cmds.ls(joints[0], long=True)[0]
        # 原点はローカルではx=1の面に近く、ワールドではz=0.2の面に近い。
        for restrict, expected_face, expected_weight in ((None, 1, 0.5), (1, 1, 0.5), (0, 0, 1.0)):
            face, result = skinSurface.sample(shape, locator, restrict)
            self.assertEqual(face, expected_face)
            self.assertAlmostEqual(result[joint], expected_weight)

    def test_geometry_port_cycle_and_library_subset(self):
        """直接接続した形状の逆接続を拒否し、ライブラリの他の登録を残す。"""
        roots = [cmds.polyPlane(name=name, constructionHistory=False)[0] for name in ("rigA", "rigB")]
        for root, src, dst in zip(roots, ("outMesh", "inMesh"), ("inMesh", "outMesh")):
            shape = cmds.listRelatives(root, shapes=True)[0]
            ports = {"forward": dict(kind="geometry", path=shape, attribute=src),
                     "reverse": dict(kind="geometry", path=shape, attribute=dst)}
            publishedChannels.setPorts(root, ports)
        publishedChannels.connectExternalPorts(*roots, ["forward"])
        with self.assertRaises(ValueError):
            publishedChannels.connectExternalPorts(*reversed(roots), ["reverse"])
        # 2つの役割は同じ向きのPlug対を逆から公開している。
        publishedChannels.disconnectExternalPorts(*roots, ["forward"])
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ports.json"
            publishedChannels.updatePortLibrary(roots[0], path, ["forward"])
            publishedChannels.updatePortLibrary(roots[0], path, ["reverse"])
            saved = publishedChannels.updatePortLibrary(roots[0], path, ["forward"], remove=True)
            self.assertEqual(list(saved), ["reverse"])
