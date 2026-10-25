"""LeafJointsの枝と葉のjointを、OpenMayaで独立に求めた行列と、segmentScaleCompensateを使わない親子の積で確かめる。"""

import random
import unittest

from maya import cmds
from maya.api import OpenMaya as om

from mlrig.setups import LeafJoints


def _matrix(plug):
    """plugの行列。"""
    return om.MMatrix(cmds.getAttr(plug))


def _flat(matrix):
    """行列から scale と shear を除いた、位置と回転だけの行列(独立計算)。"""
    transform = om.MTransformationMatrix(matrix)
    result = om.MTransformationMatrix()
    result.setTranslation(transform.translation(om.MSpace.kWorld), om.MSpace.kWorld)
    result.setRotation(transform.rotation(asQuaternion=True))
    return result.asMatrix()


def _scaleOnly(matrix):
    """行列から shear を除いた行列(scale・回転・位置は残す、独立計算)。"""
    transform = om.MTransformationMatrix(matrix)
    result = om.MTransformationMatrix()
    result.setScale(transform.scale(om.MSpace.kWorld), om.MSpace.kWorld)
    result.setRotation(transform.rotation(asQuaternion=True))
    result.setTranslation(transform.translation(om.MSpace.kWorld), om.MSpace.kWorld)
    return result.asMatrix()


def _engineWorld(joint):
    """segmentScaleCompensate と jointOrient を使わず、translate・rotate・scale・shear の親子の積だけで求めた
    ワールド行列(書き出し先と同じ計算)。jointでない親に着いたら、そのワールド行列を掛けて止める。"""
    transform = om.MTransformationMatrix()
    transform.setScale(cmds.getAttr(joint + ".scale")[0], om.MSpace.kTransform)
    transform.setShear(cmds.getAttr(joint + ".shear")[0], om.MSpace.kTransform)
    # getAttrの値はUI単位なので、内部単位(cm・radian)へ直してから組む。
    values = cmds.getAttr(joint + ".rotate")[0]
    transform.setRotation(om.MEulerRotation([om.MAngle.uiToInternal(value) for value in values]))
    translate = [om.MDistance.uiToInternal(value) for value in cmds.getAttr(joint + ".translate")[0]]
    transform.setTranslation(om.MVector(translate), om.MSpace.kTransform)
    local = transform.asMatrix()
    parent = (cmds.listRelatives(joint, parent=True, fullPath=True) or [None])[0]
    if parent is None:
        return local
    if cmds.nodeType(parent) != "joint":
        return local * _matrix(parent + ".worldMatrix[0]")
    return local * _engineWorld(parent)


class LeafJointsTest(unittest.TestCase):
    """作成時の一致・各姿勢での独立計算・scaleの分離・剪断・親と順序・UI単位・所有・引数を確かめる。"""

    def setUp(self):
        """回転した胴の下に、肩・肘・手首・手の先(segmentScaleCompensate付きjoint)の腕を作る。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(angle="deg", linear="cm")
        self.body = cmds.createNode("transform", name="body")
        cmds.setAttr(self.body + ".translate", 3, 12, -2)
        cmds.setAttr(self.body + ".rotate", 15, -30, 10)
        self.arm, parent = [], self.body
        for index, (move, orient) in enumerate((((0, 0, 0), (0, 0, -20)), ((4, 0, 0), (0, 15, 5)),
                                                 ((3.5, 0.2, 0), (10, 0, -10)), ((1.5, 0, 0), (0, 0, 0)))):
            joint = cmds.createNode("joint", name="arm{}".format(index), parent=parent)
            if index:
                # jointツールで作った骨と同じく、親のscaleを inverseScale へ繋いで segmentScaleCompensate を効かせる。
                cmds.connectAttr(parent + ".scale", joint + ".inverseScale")
            cmds.setAttr(joint + ".translate", *move)
            cmds.setAttr(joint + ".jointOrient", *orient)
            self.arm.append(cmds.ls(joint, long=True)[0])
            parent = joint
        cmds.setAttr(self.arm[1] + ".scale", 0.7, 1.6, 1.3)

    def assertMatrix(self, actual, expected, tolerance=1e-5):
        """行列の各成分の差が許容以内。"""
        for index in range(16):
            self.assertAlmostEqual(actual[index], expected[index], delta=tolerance, msg=str(index))

    def check(self, setup, sources, shear=True):
        """枝・葉のjointが、入力のワールド行列と独立計算と書き出し先の積に一致する。"""
        branches, leaves = setup.getJoints()
        for source, branch, leaf in zip(sources, branches, leaves):
            world = _matrix(source + ".worldMatrix[0]")
            self.assertMatrix(_matrix(str(branch) + ".worldMatrix[0]"), _flat(world))
            self.assertMatrix(_engineWorld(str(branch)), _flat(world))
            expected = world if shear else _scaleOnly(world)
            self.assertMatrix(_matrix(str(leaf) + ".worldMatrix[0]"), expected)
            self.assertMatrix(_engineWorld(str(leaf)), expected)
            for value in cmds.getAttr(str(branch) + ".scale")[0]:
                self.assertAlmostEqual(value, 1.0, delta=1e-5)
            for value in cmds.getAttr(str(leaf) + ".translate")[0] + cmds.getAttr(str(leaf) + ".rotate")[0]:
                self.assertAlmostEqual(value, 0.0, delta=1e-4)
            for joint in (branch, leaf):
                self.assertFalse(cmds.getAttr(str(joint) + ".segmentScaleCompensate"))
                self.assertEqual(cmds.getAttr(str(joint) + ".jointOrient")[0], (0.0, 0.0, 0.0))

    def test_rest_and_hierarchy(self):
        """作成直後に一致し、枝は入力と同じ親子、葉は枝の子(末端)になる。"""
        setup = LeafJoints.create(self.arm, name="leaf")
        branches, leaves = setup.getJoints()
        self.assertEqual(len(branches), 4)
        self.check(setup, self.arm)
        self.assertIsNone(cmds.listRelatives(str(branches[0]), parent=True))
        for index in range(1, 4):
            self.assertEqual(cmds.listRelatives(str(branches[index]), parent=True), [branches[index - 1].getName()])
        for branch, leaf in zip(branches, leaves):
            self.assertEqual(cmds.listRelatives(str(leaf), parent=True), [branch.getName()])
            self.assertIsNone(cmds.listRelatives(str(leaf), children=True))
        for actual, expected in zip(cmds.getAttr(str(leaves[1]) + ".scale")[0], (0.7, 1.6, 1.3)):
            self.assertAlmostEqual(actual, expected, delta=1e-9)

    def test_random_poses(self):
        """回転・位置・不均一なscaleを各節へ与えた姿勢で、独立計算と書き出し先の積に一致する。"""
        setup = LeafJoints.create(self.arm, name="leaf")
        generator = random.Random(7)
        for _ in range(12):
            for joint in self.arm:
                cmds.setAttr(joint + ".rotate", *[generator.uniform(-120, 120) for _ in range(3)])
                cmds.setAttr(joint + ".scale", *[generator.uniform(0.4, 2.5) for _ in range(3)])
            cmds.setAttr(self.arm[0] + ".translate", *[generator.uniform(-3, 3) for _ in range(3)])
            cmds.setAttr(self.body + ".rotate", *[generator.uniform(-90, 90) for _ in range(3)])
            self.check(setup, self.arm)

    def test_scale_stays_in_the_leaf(self):
        """肘を不均一に拡大縮小しても、scaleは肘の葉だけに現れ、肩の枝と葉は変わらず、前腕より先の枝と葉は
        scale 1 のまま入力に追従する(segmentScaleCompensate の入力どおり、手首の位置は肘の長さに合わせて動く)。
        同じ値を親子の積だけで子へ掛けると(書き出し先へそのまま出した場合)、手首は肘のscaleを受けて歪む。"""
        setup = LeafJoints.create(self.arm, name="leaf")
        branches, leaves = setup.getJoints()
        joints = [str(joint) for joint in branches + leaves]
        before = [_matrix(joint + ".worldMatrix[0]") for joint in joints]
        cmds.setAttr(self.arm[1] + ".scale", 0.5, 2.2, 2.0)
        after = [_matrix(joint + ".worldMatrix[0]") for joint in joints]
        self.check(setup, self.arm)
        for index in (0, 4):
            self.assertMatrix(after[index], before[index])
        self.assertFalse(after[5].isEquivalent(before[5], 1e-3))
        for index, matrix in enumerate(after):
            scale = om.MTransformationMatrix(matrix).scale(om.MSpace.kWorld)
            expected = (0.5, 2.2, 2.0) if index == 5 else (1.0, 1.0, 1.0)
            for actual, value in zip(scale, expected):
                self.assertAlmostEqual(actual, value, delta=1e-5)
        # 手首の回転・jointOrient・位置を、inverseScale(segmentScaleCompensate)なしで肘のワールド行列へ掛ける。
        local = om.MTransformationMatrix()
        orient = om.MEulerRotation([om.MAngle.uiToInternal(v) for v in cmds.getAttr(self.arm[2] + ".jointOrient")[0]])
        rotate = om.MEulerRotation([om.MAngle.uiToInternal(v) for v in cmds.getAttr(self.arm[2] + ".rotate")[0]])
        local.setRotation(rotate.asQuaternion() * orient.asQuaternion())
        local.setTranslation(om.MVector(cmds.getAttr(self.arm[2] + ".translate")[0]), om.MSpace.kTransform)
        naive = om.MTransformationMatrix(local.asMatrix() * _matrix(self.arm[1] + ".worldMatrix[0]"))
        self.assertGreater(max(abs(value - 1.0) for value in naive.scale(om.MSpace.kWorld)), 0.3)

    def test_shear(self):
        """segmentScaleCompensate の無い入力で、親の不均一なscaleと子の回転が作る剪断を、shear=Falseは
        除いて scale だけを渡し、shear=Trueは葉へ渡して入力と一致させる。"""
        chain, parent = [], self.body
        for index in range(3):
            node = cmds.createNode("transform", name="plain{}".format(index), parent=parent)
            cmds.setAttr(node + ".translate", 2 if index else 0, 0, 0)
            cmds.setAttr(node + ".rotate", 0, 20 * index, 35 * index)
            chain.append(cmds.ls(node, long=True)[0])
            parent = node
        cmds.setAttr(chain[0] + ".scale", 1.0, 2.0, 0.6)
        shear = om.MTransformationMatrix(_matrix(chain[2] + ".worldMatrix[0]")).shear(om.MSpace.kWorld)
        self.assertGreater(max(abs(value) for value in shear), 0.05)
        plain = LeafJoints.create(chain, name="plainLeaf")
        self.check(plain, chain, shear=False)
        sheared = LeafJoints.create(chain, name="shearLeaf", shear=True)
        self.check(sheared, chain, shear=True)

    def test_parent_order_and_branching(self):
        """入力の順を入れ替え、間に入力でないtransformを挟み、枝分かれ(2本の指)があっても、最も近い入力の祖先を
        親にする。根は parent(移動・回転した書き出しの根)の下に置く。"""
        extra = cmds.createNode("transform", name="extra", parent=self.arm[2])
        cmds.setAttr(extra + ".rotate", 0, 0, 30)
        fingers = []
        for index, z in enumerate((0.5, -0.5)):
            finger = cmds.createNode("joint", name="finger{}".format(index), parent=extra)
            cmds.setAttr(finger + ".translate", 1, 0, z)
            cmds.setAttr(finger + ".scale", 1.0, 0.5 + index, 1.0)
            fingers.append(cmds.ls(finger, long=True)[0])
        root = cmds.createNode("transform", name="exportRoot")
        cmds.setAttr(root + ".translate", -5, 1, 2)
        cmds.setAttr(root + ".rotate", 0, 40, 0)
        sources = [fingers[1], self.arm[2], self.arm[0], fingers[0], self.arm[1]]
        setup = LeafJoints.create(sources, name="leaf", parent=root)
        branches, _ = setup.getJoints()
        parents = [cmds.listRelatives(str(branch), parent=True)[0] for branch in branches]
        self.assertEqual(parents, [branches[1].getName(), branches[4].getName(), "exportRoot",
                                   branches[1].getName(), branches[0 + 2].getName()])
        self.check(setup, sources)
        cmds.setAttr(self.arm[0] + ".rotate", 10, 50, -20)
        cmds.setAttr(root + ".translate", 4, 0, 0)
        self.check(setup, sources)

    def test_ui_units(self):
        """UI単位がmm・radでも同じ行列になり、自動の単位変換ノードが入らない。"""
        cmds.currentUnit(linear="mm", angle="rad")
        try:
            setup = LeafJoints.create(self.arm, name="leaf")
            cmds.setAttr(self.arm[2] + ".rotate", 0.3, -0.5, 1.0)
            self.check(setup, self.arm)
        finally:
            cmds.currentUnit(linear="cm", angle="deg")
        self.assertFalse(cmds.ls(type="unitConversion"))

    def test_ownership_and_undo(self):
        """演算ノードとjointはcontainerが所有し、1回のUndoで全体が消え、Redoで戻る。"""
        before = set(cmds.ls())
        setup = LeafJoints.create(self.arm, name="leaf")
        owner = str(setup.container)
        added = set(cmds.ls()) - before - {owner}
        members = set(cmds.ls(cmds.container(owner, query=True, nodeList=True) or []))
        self.assertTrue(added)
        self.assertEqual({node for node in added if cmds.nodeType(node) != "hyperLayout"} - members, set())
        branches, leaves = setup.getJoints()
        self.assertEqual({joint.getName() for joint in branches + leaves} - members, set())
        cmds.undo()
        self.assertFalse(cmds.objExists(owner))
        self.assertEqual(set(cmds.ls()) - before, set())
        cmds.redo()
        self.assertTrue(cmds.objExists(owner))
        self.check(LeafJoints(owner), self.arm)

    def test_arguments(self):
        """不正な入力・重複・入力と同じparent・既存の名前を拒否する。"""
        with self.assertRaises(ValueError):
            LeafJoints.create([], name="bad")
        with self.assertRaises(ValueError):
            LeafJoints.create(self.arm[0], name="bad")
        with self.assertRaises(ValueError):
            LeafJoints.create([self.arm[0], self.arm[0]], name="bad")
        with self.assertRaises(ValueError):
            LeafJoints.create([cmds.createNode("multMatrix")], name="bad")
        with self.assertRaises(ValueError):
            LeafJoints.create(self.arm, name="bad", parent=self.arm[0])
        with self.assertRaises(ValueError):
            LeafJoints.create(self.arm, name="bad", parent=cmds.createNode("multMatrix"))
        self.assertFalse(cmds.objExists("bad"))
        LeafJoints.create(self.arm, name="good")
        with self.assertRaises(ValueError):
            LeafJoints.create(self.arm, name="good")


if __name__ == "__main__":
    unittest.main()
