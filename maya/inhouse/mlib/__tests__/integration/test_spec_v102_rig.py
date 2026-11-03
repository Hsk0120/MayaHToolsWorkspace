"""10.2.0 で足したリグ・スキン向けの API の契約を固定する。

- SkinCluster.unlockedInfluences: ロックの一時解除と復元(例外時も)・Undo 1回。
- SkinCluster.invertShape: 結果を blendShape で足すと現在のポーズで sculpted と一致する・Undo 1回・不正入力。
- GeometryFilter.dump/loadDeformerWeights・copyDeformerWeightsTo: 往復・照合・fast・skinCluster は TypeError。
- Joint.insertJoints・getPolePosition、mlib.cmds.createJointChain。
"""

import json
import math
import os
import shutil
import tempfile
import unittest

import maya.api.OpenMaya as om2
import maya.cmds as cmds

import mlib
mlib.reload()
from mlib.cmds.createJointChain import createJointChain
from mlib.nodes import Joint, Mesh, SkinCluster
from support.specCase import NamespaceCase


def _distance(first, second):
    """2点の距離(Python 3.7 には math.dist が無いため)。"""
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(first, second)))


def _world_points(name):
    selection = om2.MSelectionList()
    selection.add(name)
    path = selection.getDagPath(0)
    path.extendToShape()
    return [(p.x, p.y, p.z) for p in om2.MFnMesh(path).getPoints(om2.MSpace.kObject)]


class _RigCase(NamespaceCase):
    """root→mid→tip の chain と、それにバインドした円柱を作る。"""

    def chain(self):
        cmds.select(clear=True)
        self.root = cmds.joint(name=self.name("root"), position=(0, -2, 0))
        self.mid = cmds.joint(name=self.name("mid"), position=(0, 0, 0))
        self.tip = cmds.joint(name=self.name("tip"), position=(0, 2, 0))
        cmds.select(clear=True)
        return [self.root, self.mid, self.tip]

    def skinned(self, offset=(0, 0, 0)):
        joints = self.chain()
        self.mesh = cmds.polyCylinder(name=self.name("geo"), height=4, subdivisionsHeight=8)[0]
        cmds.move(offset[0], offset[1], offset[2], self.mesh)
        self.skin = SkinCluster(cmds.skinCluster(joints, self.mesh, toSelectedBones=True, maximumInfluences=3)[0])
        cmds.select(clear=True)
        return self.skin


class UnlockedInfluencesTest(_RigCase):

    def test_unlock_and_restore(self):
        """ロックしていたものだけを外し、抜けると戻す。中で書いたウェイトは残る。"""
        skin = self.skinned()
        skin.setInfluencesLocked([self.root, self.tip], True)
        with skin.unlockedInfluences() as value:
            self.assertIs(value, skin)
            self.assertEqual(skin.getLockedInfluences(), [])
            skin.setWeights([self.root], [1.0], vertices=[0], normalize=True)
        self.assertEqual(sorted(n.getName() for n in skin.getLockedInfluences()),
                         sorted(mlib.getNode(n).getName() for n in (self.root, self.tip)))
        self.assertAlmostEqual(skin.getWeights([self.root], vertices=[0])[0], 1.0, places=6)

    def test_subset_and_exception(self):
        """指定したものだけを外し、例外でも戻す。"""
        skin = self.skinned()
        skin.setInfluencesLocked([self.root, self.tip], True)
        with self.assertRaises(KeyError):
            with skin.unlockedInfluences([self.root]):
                self.assertFalse(cmds.getAttr(self.root + ".lockInfluenceWeights"))
                self.assertTrue(cmds.getAttr(self.tip + ".lockInfluenceWeights"))
                raise KeyError("test")
        self.assertTrue(cmds.getAttr(self.root + ".lockInfluenceWeights"))
        self.assertTrue(cmds.getAttr(self.tip + ".lockInfluenceWeights"))

    def test_undo_once(self):
        """抜けた後の Undo 1回で、ロックしたまま元のウェイトへ戻る。"""
        skin = self.skinned()
        skin.setInfluencesLocked([self.tip], True)
        before = skin.getWeights([self.root, self.mid, self.tip])
        self.flushUndo()
        with skin.unlockedInfluences():
            skin.setWeights([self.tip], [1.0], vertices=[0], normalize=True)
        self.assertTrue(cmds.getAttr(self.tip + ".lockInfluenceWeights"))
        cmds.undo()
        self.assertTrue(cmds.getAttr(self.tip + ".lockInfluenceWeights"))
        self.assertSequenceAlmostEqual(skin.getWeights([self.root, self.mid, self.tip]), before, places=6)
        self.assertUndoEmpty()

    def test_undo_inside(self):
        """with の中で Undo しても(ロックの解除まで戻しても)、抜けるとロックへ戻る。"""
        skin = self.skinned()
        skin.setInfluencesLocked([self.tip], True)
        with skin.unlockedInfluences():
            cmds.undo()
            self.assertTrue(cmds.getAttr(self.tip + ".lockInfluenceWeights"))
        self.assertTrue(cmds.getAttr(self.tip + ".lockInfluenceWeights"))
        with skin.unlockedInfluences():
            skin.setWeights([self.tip], [1.0], vertices=[0], normalize=True)
            cmds.undo()
        self.assertTrue(cmds.getAttr(self.tip + ".lockInfluenceWeights"))

    def test_errors(self):
        skin = self.skinned()
        cmds.select(clear=True)
        other = cmds.joint(name=self.name("other"))

        def enter(joints):
            with skin.unlockedInfluences(joints):
                pass
        self.assertRaises(ValueError, enter, [other])
        self.assertRaises(ValueError, enter, [])


class InvertShapeTest(_RigCase):

    def posed_and_sculpted(self, offset=(0, 0, 0)):
        skin = self.skinned(offset)
        cmds.setAttr(self.mid + ".rotateZ", 40)
        cmds.setAttr(self.root + ".rotateX", 10)
        sculpt = cmds.duplicate(self.mesh, name=self.name("sculpt"))[0]
        for shape in cmds.listRelatives(sculpt, shapes=True, fullPath=True):
            if cmds.getAttr(shape + ".intermediateObject"):
                cmds.delete(shape)
        cmds.move(5, 0, 0, sculpt, relative=True)
        for index in (3, 12, 20, 33):
            cmds.move(0.3, 0.2, -0.4, f"{sculpt}.vtx[{index}]", relative=True, objectSpace=True)
        return skin, sculpt

    def check_matches(self, offset=(0, 0, 0), front=None):
        skin, sculpt = self.posed_and_sculpted(offset)
        if front is not None:
            front()
        result = skin.invertShape(sculpt)
        self.assertIsInstance(result, Mesh)
        blend = cmds.blendShape(result.getParent().getFullName(), self.mesh, frontOfChain=True,
                                name=self.name("corrective"))[0]
        cmds.setAttr(blend + ".weight[0]", 1.0)
        for actual, expected in zip(_world_points(self.mesh), _world_points(sculpt)):
            self.assertLess(_distance(actual, expected), 1e-3)
        return result

    def test_matches_sculpted(self):
        """補正形状を blendShape で足すと、現在のポーズで sculpted と一致する。"""
        result = self.check_matches()
        self.assertTrue(result.getParent().getName().endswith("sculpt_inverted"))

    def test_moved_mesh(self):
        """メッシュを動かしてからバインドした(geomMatrix が単位でない)場合も一致する。"""
        self.check_matches(offset=(1.5, 0.5, -2))

    def test_existing_blend_shape(self):
        """skinCluster より前に、値の入った blendShape(ターゲットの形状は削除済み)があっても一致する。"""
        def front():
            target = cmds.polyCylinder(name=self.name("bump"), height=4, subdivisionsHeight=8)[0]
            cmds.move(0, 0, 0.5, target + ".vtx[0:20]", relative=True)
            blend = cmds.blendShape(target, self.mesh, frontOfChain=True, name=self.name("bumpBlend"))[0]
            cmds.setAttr(blend + ".weight[0]", 0.7)
            # ターゲットの形状を残すと blendShape は入力に対する絶対位置として働くため、差分だけにする。
            cmds.delete(target)
        self.check_matches(front=front)

    def test_undo_once(self):
        skin, sculpt = self.posed_and_sculpted()
        before = set(cmds.ls(self.ns + ":*"))
        self.flushUndo()
        skin.invertShape(sculpt, name=self.name("fix"))
        self.assertTrue(cmds.objExists(self.name("fix")))
        cmds.undo()
        self.assertEqual(set(cmds.ls(self.ns + ":*")), before)
        self.assertUndoEmpty()

    def test_errors(self):
        skin, sculpt = self.posed_and_sculpted()
        other = cmds.polyCube(name=self.name("cube"))[0]
        self.assertRaises(ValueError, skin.invertShape, other)
        self.assertRaises(TypeError, skin.invertShape, self.root)
        self.assertRaises(TypeError, skin.invertShape, sculpt, name=1)
        self.assertRaises(ValueError, skin.invertShape, sculpt, name="")


class DeformerWeightsFileTest(_RigCase):

    def setUp(self):
        super().setUp()
        self.directory = tempfile.mkdtemp(prefix="mlibRig")
        self.path = os.path.join(self.directory, "deformer.json")

    def tearDown(self):
        shutil.rmtree(self.directory, ignore_errors=True)
        super().tearDown()

    def two_cubes(self):
        first = cmds.polyCube(name=self.name("a"))[0]
        second = cmds.polyCube(name=self.name("b"))[0]
        cluster = mlib.getNode(cmds.cluster(first, second, name=self.name("cl"))[0])
        return cluster

    def test_roundtrip_all_geometries(self):
        """全形状を書き、読み込むと同じ値に戻る。通常は Undo 1回。"""
        cluster = self.two_cubes()
        cluster.setDeformerWeights([0.1 * i for i in range(8)], geometryIndex=0)
        cluster.setDeformerWeights([0.5] * 8, geometryIndex=1)
        expected = [cluster.getDeformerWeights(geometryIndex=i) for i in (0, 1)]
        cluster.dumpDeformerWeights(self.path)
        with open(self.path, encoding="utf-8") as file:
            payload = json.load(file)
        self.assertEqual(payload["version"], 1)
        self.assertEqual([g["index"] for g in payload["geometries"]], [0, 1])
        self.assertEqual([g["numVertices"] for g in payload["geometries"]], [8, 8])
        cluster.setDeformerWeights([1.0] * 8, geometryIndex=0)
        cluster.setDeformerWeights([1.0] * 8, geometryIndex=1)
        self.flushUndo()
        self.assertIsNone(cluster.loadDeformerWeights(self.path))
        for index in (0, 1):
            self.assertSequenceAlmostEqual(cluster.getDeformerWeights(geometryIndex=index), expected[index], places=6)
        cmds.undo()
        for index in (0, 1):
            self.assertEqual(cluster.getDeformerWeights(geometryIndex=index), [1.0] * 8)
        self.assertUndoEmpty()

    def test_single_geometry_and_fast(self):
        """geometryIndex を指定すると1つだけ書く。fast は Undo に積まない。"""
        cluster = self.two_cubes()
        cluster.setDeformerWeights([0.25] * 8, geometryIndex=1)
        cluster.dumpDeformerWeights(self.path, geometryIndex=1)
        with open(self.path, encoding="utf-8") as file:
            self.assertEqual([g["index"] for g in json.load(file)["geometries"]], [1])
        cluster.setDeformerWeights([1.0] * 8, geometryIndex=1)
        self.flushUndo()
        cluster.loadDeformerWeights(self.path, fast=True)
        self.assertSequenceAlmostEqual(cluster.getDeformerWeights(geometryIndex=1), [0.25] * 8, places=6)
        self.assertUndoEmpty()

    def test_load_mismatch(self):
        """番号の無い形状・頂点数の違い・版の違いは ValueError で、何も変えない。"""
        cluster = self.two_cubes()
        cluster.dumpDeformerWeights(self.path)
        sphere = cmds.polySphere(name=self.name("sphere"))[0]
        single = mlib.getNode(cmds.cluster(sphere, name=self.name("cl2"))[0])
        self.assertRaises(ValueError, single.loadDeformerWeights, self.path)
        cube = cmds.polyCube(name=self.name("c"))[0]
        other = mlib.getNode(cmds.cluster(cube, name=self.name("cl3"))[0])
        self.assertRaises(ValueError, other.loadDeformerWeights, self.path)
        self.assertEqual(other.getDeformerWeights(), [1.0] * 8)
        with open(self.path, "w", encoding="utf-8") as file:
            json.dump({"version": 99, "geometries": []}, file)
        self.assertRaises(ValueError, cluster.loadDeformerWeights, self.path)
        self.assertRaises(TypeError, cluster.loadDeformerWeights, self.path, fast=1)

    def test_skin_cluster_rejected(self):
        skin = self.skinned()
        cluster = self.two_cubes()
        self.assertRaises(TypeError, skin.dumpDeformerWeights, self.path)
        self.assertRaises(TypeError, skin.loadDeformerWeights, self.path)
        self.assertRaises(TypeError, skin.copyDeformerWeightsTo, cluster)
        self.assertRaises(TypeError, cluster.copyDeformerWeightsTo, skin)
        self.assertRaises(IndexError, cluster.dumpDeformerWeights, self.path, geometryIndex=5)


class CopyDeformerWeightsTest(_RigCase):

    def test_copy_and_undo(self):
        first = cmds.polyCube(name=self.name("a"))[0]
        second = cmds.polyCube(name=self.name("b"))[0]
        source = mlib.getNode(cmds.cluster(first, name=self.name("src"))[0])
        target = mlib.getNode(cmds.cluster(second, name=self.name("dst"))[0])
        values = [0.1 * i for i in range(8)]
        source.setDeformerWeights(values)
        self.flushUndo()
        result = source.copyDeformerWeightsTo(target.getName())
        self.assertEqual(result.getUuid(), target.getUuid())
        self.assertSequenceAlmostEqual(target.getDeformerWeights(), values, places=6)
        cmds.undo()
        self.assertEqual(target.getDeformerWeights(), [1.0] * 8)
        self.assertUndoEmpty()
        target.setDeformerWeights([1.0] * 8)
        self.flushUndo()
        source.copyDeformerWeightsTo(target, fast=True)
        self.assertSequenceAlmostEqual(target.getDeformerWeights(), values, places=6)
        self.assertUndoEmpty()

    def test_other_geometry_and_errors(self):
        first = cmds.polyCube(name=self.name("a"))[0]
        second = cmds.polyCube(name=self.name("b"))[0]
        sphere = cmds.polySphere(name=self.name("s"))[0]
        cluster = mlib.getNode(cmds.cluster(first, second, name=self.name("cl"))[0])
        cluster.setDeformerWeights([0.3] * 8, geometryIndex=0)
        cluster.copyDeformerWeightsTo(cluster, geometryIndex=0, otherGeometryIndex=1)
        self.assertSequenceAlmostEqual(cluster.getDeformerWeights(geometryIndex=1), [0.3] * 8, places=6)
        other = mlib.getNode(cmds.cluster(sphere, name=self.name("cls"))[0])
        self.assertRaises(ValueError, cluster.copyDeformerWeightsTo, other)
        self.assertRaises(TypeError, cluster.copyDeformerWeightsTo, first)
        self.assertRaises(IndexError, cluster.copyDeformerWeightsTo, cluster, otherGeometryIndex=4)
        self.assertRaises(TypeError, cluster.copyDeformerWeightsTo, cluster, fast=1)


class InsertJointsTest(_RigCase):

    def test_insert(self):
        """等間隔に挿入し、元の子は最後の新しいjointの子でワールドの位置・向きが同じ。Undo 1回。"""
        self.chain()
        cmds.setAttr(self.root + ".rotateZ", 20)
        cmds.setAttr(self.mid + ".jointOrientY", 15)
        root = Joint(self.root)
        child_matrix = cmds.xform(self.mid, query=True, matrix=True, worldSpace=True)
        root_rotation = Joint(self.root).getMatrix(worldSpace=True)
        start = cmds.xform(self.root, query=True, translation=True, worldSpace=True)
        end = cmds.xform(self.mid, query=True, translation=True, worldSpace=True)
        self.flushUndo()
        created = root.insertJoints(3)
        self.assertEqual(len(created), 3)
        self.assertTrue(all(isinstance(joint, Joint) for joint in created))
        for number, joint in enumerate(created, 1):
            with self.subTest(number=number):
                position = cmds.xform(joint.getFullName(), query=True, translation=True, worldSpace=True)
                expected = [a + (b - a) * number / 4.0 for a, b in zip(start, end)]
                self.assertSequenceAlmostEqual(position, expected, places=6)
                self.assertSequenceAlmostEqual(cmds.getAttr(joint.getFullName() + ".jointOrient")[0], (0, 0, 0))
                matrix = joint.getMatrix(worldSpace=True)
                for row in range(3):
                    for column in range(3):
                        self.assertAlmostEqual(matrix.getElement(row, column), root_rotation.getElement(row, column), places=6)
        self.assertEqual(created[0].getParent().getUuid(), root.getUuid())
        self.assertEqual(Joint(self.mid).getParent().getUuid(), created[-1].getUuid())
        self.assertTrue(cmds.isConnected(created[0].getFullName() + ".scale", created[1].getFullName() + ".inverseScale"))
        self.assertTrue(cmds.isConnected(created[-1].getFullName() + ".scale", cmds.ls(self.mid, long=True)[0] + ".inverseScale"))
        self.assertSequenceAlmostEqual(cmds.xform(self.mid, query=True, matrix=True, worldSpace=True), child_matrix, places=6)
        cmds.undo()
        self.assertEqual(cmds.listRelatives(self.mid, parent=True, fullPath=True)[0],
                         cmds.ls(self.root, long=True)[0])
        self.assertFalse(cmds.ls(self.ns + ":*_insert*"))
        self.assertUndoEmpty()

    def test_errors(self):
        self.chain()
        root, tip = Joint(self.root), Joint(self.tip)
        cmds.select(clear=True)
        extra = cmds.joint(name=self.name("extra"))
        cmds.parent(extra, self.root)
        self.assertRaises(TypeError, Joint(self.mid).insertJoints, 1.0)
        self.assertRaises(TypeError, Joint(self.mid).insertJoints, True)
        self.assertRaises(ValueError, Joint(self.mid).insertJoints, 0)
        self.assertRaises(ValueError, tip.insertJoints, 1)
        self.assertRaises(ValueError, root.insertJoints, 1)


class PolePositionTest(_RigCase):

    def test_bend_side(self):
        """曲がる側(子の位置から下ろした垂線の向き)へ、既定はチェーンの長さだけ離す。"""
        cmds.select(clear=True)
        a = cmds.joint(name=self.name("a"), position=(0, 0, 0))
        b = cmds.joint(name=self.name("b"), position=(3, 0, -1))
        cmds.joint(name=self.name("c"), position=(6, 0, 0))
        length = 2 * math.sqrt(10)
        self.assertSequenceAlmostEqual(Joint(a).getPolePosition(), (3, 0, -1 - length), places=6)
        self.assertSequenceAlmostEqual(Joint(a).getPolePosition(distance=2), (3, 0, -3), places=6)
        self.assertIsInstance(Joint(a).getPolePosition(), mlib.maths.Vector)
        self.assertEqual(cmds.xform(b, query=True, translation=True, worldSpace=True), [3, 0, -1])

    def test_errors(self):
        self.chain()
        root = Joint(self.root)
        self.assertRaises(ValueError, root.getPolePosition)
        cmds.setAttr(self.mid + ".rotateZ", 30)
        self.assertRaises(TypeError, root.getPolePosition, "1")
        self.assertRaises(ValueError, root.getPolePosition, -1)
        self.assertRaises(ValueError, root.getPolePosition, math.inf)
        self.assertRaises(ValueError, Joint(self.mid).getPolePosition)


class CreateJointChainTest(NamespaceCase):

    def axes(self, joint):
        matrix = cmds.xform(joint.getFullName(), query=True, matrix=True, worldSpace=True)
        return [matrix[0:3], matrix[4:7], matrix[8:11]]

    def test_default_axes(self):
        """x を次の点へ、y を up へ向け、rotate は0。最後は1つ前と同じ向き。Undo 1回。"""
        points = [(0, 0, 0), (4, 0, -1), (8, 0, 0)]
        names = [self.name(n) for n in ("a", "b", "c")]
        self.flushUndo()
        joints = createJointChain(points, names=names)
        self.assertEqual([j.getName() for j in joints], [n for n in names])
        for joint, point in zip(joints, points):
            self.assertSequenceAlmostEqual(cmds.xform(joint.getFullName(), query=True, translation=True, worldSpace=True),
                                           point, places=6)
            self.assertSequenceAlmostEqual(cmds.getAttr(joint.getFullName() + ".rotate")[0], (0, 0, 0))
        for index in range(2):
            aim = om2.MVector(*points[index + 1]) - om2.MVector(*points[index])
            x_axis, y_axis, z_axis = self.axes(joints[index])
            self.assertSequenceAlmostEqual(x_axis, list(aim.normal()), places=6)
            self.assertSequenceAlmostEqual(y_axis, (0, 1, 0), places=6)
        self.assertSequenceAlmostEqual(sum(self.axes(joints[2]), []), sum(self.axes(joints[1]), []), places=6)
        self.assertEqual(joints[1].getParent().getUuid(), joints[0].getUuid())
        self.assertTrue(cmds.isConnected(names[0] + ".scale", names[1] + ".inverseScale"))
        cmds.undo()
        self.assertFalse(cmds.ls(names))
        self.assertUndoEmpty()

    def test_axes_and_parent(self):
        """-y を向け z を up に、親(回転・移動した transform)の下でもワールドの位置・向きが合う。"""
        parent = cmds.createNode("transform", name=self.name("grp"), skipSelect=True)
        cmds.setAttr(parent + ".translate", 1, 2, 3)
        cmds.setAttr(parent + ".rotate", 10, 20, 30)
        points = [(0, 5, 0), (0, 0, 0)]
        joints = createJointChain(points, aimAxis="-y", upAxis="z", up=(0, 0, 1), parent=parent)
        self.assertEqual(joints[0].getParent().getUuid(), mlib.getNode(parent).getUuid())
        x_axis, y_axis, z_axis = self.axes(joints[0])
        self.assertSequenceAlmostEqual(y_axis, (0, 1, 0), places=6)
        self.assertSequenceAlmostEqual(z_axis, (0, 0, 1), places=6)
        self.assertSequenceAlmostEqual(x_axis, (1, 0, 0), places=6)
        self.assertSequenceAlmostEqual(cmds.xform(joints[1].getFullName(), query=True, translation=True, worldSpace=True),
                                       (0, 0, 0), places=6)

    def test_errors(self):
        transform = cmds.createNode("joint", name=self.name("j"), skipSelect=True)
        cases = (
            (ValueError, lambda: createJointChain([(0, 0, 0)])),
            (ValueError, lambda: createJointChain([(0, 0, 0), (0, 0, 0)])),
            (TypeError, lambda: createJointChain([(0, 0, "a"), (1, 0, 0)])),
            (TypeError, lambda: createJointChain("abc")),
            (ValueError, lambda: createJointChain([(0, 0, 0), (1, 0, 0)], aimAxis="w")),
            (TypeError, lambda: createJointChain([(0, 0, 0), (1, 0, 0)], aimAxis=0)),
            (ValueError, lambda: createJointChain([(0, 0, 0), (1, 0, 0)], aimAxis="x", upAxis="-x")),
            (ValueError, lambda: createJointChain([(0, 0, 0), (1, 0, 0)], up=(1, 0, 0))),
            (ValueError, lambda: createJointChain([(0, 0, 0), (1, 0, 0)], up=(0, 0, 0))),
            (ValueError, lambda: createJointChain([(0, 0, 0), (1, 0, 0)], names=["a"])),
            (TypeError, lambda: createJointChain([(0, 0, 0), (1, 0, 0)], names=["a", 1])),
            (TypeError, lambda: createJointChain([(0, 0, 0), (1, 0, 0)], parent=cmds.createNode("network", name=self.name("n"), skipSelect=True))),
        )
        before = set(cmds.ls(type="joint"))
        for error, call in cases:
            with self.subTest(error=error.__name__):
                self.assertRaises(error, call)
        self.assertEqual(set(cmds.ls(type="joint")), before)
        self.assertTrue(cmds.objExists(transform))


if __name__ == "__main__":
    unittest.main()
