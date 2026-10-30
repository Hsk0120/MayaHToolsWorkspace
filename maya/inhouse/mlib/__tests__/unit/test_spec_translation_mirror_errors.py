"""6.0.0 の Transform・Joint・ミラー軸・エラー文の約束を固定する。

対象: getTranslation/setTranslation(旧 getTranslate/setTranslate)の基準位置と旧名の不在、
addConstraint の引数順の誤りの案内、setParent で自身・子孫を親にした場合の文言(通常/fast/Nodes)、
ミラーの axis の2つの書き方(反転する軸 ``"x"`` とミラー面 ``"YZ"``)。
"""

import unittest

import maya.cmds as cmds

import mlib
mlib.reload()
from mlib.maths import EulerRotate, Matrix, Quaternion, Translate, Vector
from mlib.nodes import Joint, Node, Nodes, Transform
from support.specCase import NamespaceCase

#: 同じ鏡映になる axis の書き方(反転する軸、ミラー面、面の順序違い・小文字、番号)。
_EQUIVALENT_AXES = (
    ("x", "YZ", "zy", "X", 0),
    ("y", "XZ", "ZX", "zx", 1),
    ("z", "XY", "YX", "xy", 2),
)


class _SpecCase(NamespaceCase):
    """このテストファイルの名前空間の先頭と、共通基底からの差分。"""

    PREFIX = "mlibSpecTransMirErr_"
    CLEAR_SELECTION = True


class TranslationTest(_SpecCase):
    """getTranslation/setTranslation の基準位置と、旧名を残さないこと。"""

    def setUp(self):
        super().setUp()
        self.parent_name = self.make("transform", "parent")
        cmds.setAttr(self.parent_name + ".translate", 10, 0, 0)
        self.name_ = self.make("transform", "node", parent=self.parent_name)
        cmds.setAttr(self.name_ + ".translate", 1, 2, 3)
        cmds.setAttr(self.name_ + ".rotatePivot", 0, 1, 0)
        self.node = Node(self.name_)

    def test_default_is_rotate_pivot_not_translate_channel(self):
        """既定 at=2 は回転ピボットの位置で、translate チャンネルの値は t.get()。"""
        pivot = cmds.xform(self.name_, query=True, worldSpace=True, rotatePivot=True)
        self.assertSequenceAlmostEqual(self.node.getTranslation(worldSpace=True), pivot)
        self.assertSequenceAlmostEqual(self.node.getTranslation(), (1, 3, 3))
        self.assertSequenceAlmostEqual(self.node.t.get(), (1, 2, 3))
        self.assertSequenceAlmostEqual(self.node.getTranslation(at=1), (1, 2, 3))
        self.assertIsInstance(self.node.getTranslation(), Translate)
        self.assertSequenceAlmostEqual(self.node.getTranslation(worldSpace=True, at=4), (11, 2, 3))

    def test_set_translation_moves_rotate_pivot_with_one_undo(self):
        """setTranslation は回転ピボットを指定位置へ合わせ、Undo 1回で戻る。fast は Undo に残さない。"""
        self.assertEqual(self.node.setTranslation((20, 5, 0), worldSpace=True, get=True), [10.0, 4.0, 0.0])
        self.assertSequenceAlmostEqual(cmds.getAttr(self.name_ + ".translate")[0], (1, 2, 3))
        cmds.flushUndo()
        self.assertIs(self.node.setTranslation((20, 5, 0), worldSpace=True), self.node)
        self.assertSequenceAlmostEqual(
            cmds.xform(self.name_, query=True, worldSpace=True, rotatePivot=True), (20, 5, 0))
        self.assertRegex(cmds.undoInfo(query=True, undoName=True), r"^mlib setTranslation ")
        cmds.undo()
        self.assertSequenceAlmostEqual(cmds.getAttr(self.name_ + ".translate")[0], (1, 2, 3))
        cmds.flushUndo()
        self.assertIs(self.node.setTranslation((4, 5, 6), at=1, fast=True), self.node)
        self.assertSequenceAlmostEqual(cmds.getAttr(self.name_ + ".translate")[0], (4, 5, 6))
        self.assertTrue(cmds.undoInfo(query=True, undoQueueEmpty=True))

    def test_former_names_are_removed_with_hint(self):
        """旧名 getTranslate/setTranslate は無く、AttributeError が新しい名前を案内する。"""
        for old, new in (("getTranslate", "getTranslation"), ("setTranslate", "setTranslation")):
            with self.subTest(old=old):
                self.assertFalse(hasattr(Transform, old))
                with self.assertRaisesRegex(AttributeError, new):
                    getattr(self.node, old)

    def test_spread_components_and_space_keyword_are_guided(self):
        """成分を分けた呼出しと space= は、新しい名前で案内する TypeError。"""
        with self.assertRaisesRegex(TypeError, r"setTranslation\(\(x, y, z\)\)"):
            self.node.setTranslation(1, 2, 3)
        with self.assertRaisesRegex(TypeError, "worldSpace=True"):
            self.node.getTranslation(space="world")


class AddConstraintOrderTest(_SpecCase):
    """型名をターゲットの位置へ渡した場合に、正しい引数の順を案内する。"""

    def test_swapped_type_and_target_are_guided(self):
        """addConstraint("parent", ctrl) は addConstraint(target, type="parent") を案内する TypeError。"""
        node = Node(self.make("transform", "driven"))
        ctrl = Node(self.make("transform", "ctrl"))
        before = cmds.ls(type="constraint")
        for kind in ("parent", "pointConstraint", "aim"):
            with self.subTest(kind=kind):
                with self.assertRaisesRegex(TypeError, r"addConstraint\(target, type='%s'\)" % kind):
                    node.addConstraint(kind, ctrl)
        with self.assertRaisesRegex(TypeError, r"type must be a string.*addConstraint\(target, type=\"parent\"\)"):
            node.addConstraint(ctrl, 1)
        self.assertEqual(cmds.ls(type="constraint"), before)
        constraint = node.addConstraint(ctrl, type="parent")
        self.assertTrue(constraint.isType("parentConstraint"))


class SetParentCycleTest(_SpecCase):
    """自身・子孫を親にした場合は、Maya の分かりにくいエラーでなく原因が分かる RuntimeError。"""

    MESSAGE = "Cannot parent a node under itself or one of its descendants"

    def setUp(self):
        super().setUp()
        self.root_name = self.make("transform", "root")
        self.child_name = self.make("transform", "child", parent=self.root_name)
        self.grandchild_name = self.make("transform", "grandchild", parent=self.child_name)

    def hierarchy(self):
        return [cmds.ls(name, long=True)[0] for name in (self.root_name, self.child_name, self.grandchild_name)]

    def test_transform_self_and_descendant(self):
        """通常経路と fast のどちらも、変更の前に同じ型・文言で拒否する。"""
        before = self.hierarchy()
        root = Node(self.root_name)
        for fast in (False, True):
            for parent in (self.root_name, self.child_name, Node(self.grandchild_name)):
                with self.subTest(fast=fast, parent=parent):
                    with self.assertRaisesRegex(RuntimeError, self.MESSAGE):
                        root.setParent(parent, fast=fast)
                    self.assertEqual(self.hierarchy(), before)

    def test_joint_and_fast_joint(self):
        """Joint も同じ文言。fast の Joint 未対応より先に親の検査を行う。"""
        root = Node(self.make("joint", "jointRoot"))
        child = Node(self.make("joint", "jointChild", parent=root.getFullName()))
        for fast in (False, True):
            with self.subTest(fast=fast):
                with self.assertRaisesRegex(RuntimeError, self.MESSAGE):
                    root.setParent(child, fast=fast)
                with self.assertRaisesRegex(RuntimeError, self.MESSAGE):
                    root.setParent(root, fast=fast)
        self.assertEqual(child.getParent(), root)
        with self.assertRaises(NotImplementedError):
            child.setParent(None, fast=True)

    def test_nodes_set_parent_checks_every_item_before_editing(self):
        """Nodes.setParent は1つでも該当すれば、どの要素も変更しない。"""
        other_name = self.make("transform", "other")
        before = self.hierarchy() + cmds.ls(other_name, long=True)
        for fast in (False, True):
            with self.subTest(fast=fast):
                nodes = Nodes([Node(other_name), Node(self.root_name)])
                with self.assertRaisesRegex(RuntimeError, self.MESSAGE):
                    nodes.setParent(self.child_name, fast=fast)
                self.assertEqual(self.hierarchy() + cmds.ls(other_name, long=True), before)
        Nodes([Node(other_name)]).setParent(self.grandchild_name)
        self.assertEqual(Node(other_name).getParent(), Node(self.grandchild_name))


class MirrorAxisNotationTest(_SpecCase):
    """ミラーの axis は反転する軸とミラー面のどちらの書き方でも同じ結果。"""

    def test_math_values(self):
        """Vector・EulerRotate・Quaternion・Matrix の mirror/mirrorIt。"""
        vector = Vector(1, 2, 3)
        rotation = EulerRotate(0.3, -0.4, 0.7, "zxy")
        matrix = Matrix(translate=(1, 2, 3), rotate=rotation, scale=(2, 3, 4))
        for group in _EQUIVALENT_AXES:
            expected_vector = vector.mirror(group[0], pivot=(1, 1, 1))
            expected_matrix = matrix.mirror(group[0], (1, 1, 1))
            expected_rotation = rotation.mirror(group[0])
            for axis in group[1:]:
                with self.subTest(axis=axis):
                    self.assertEqual(tuple(vector.mirror(axis, pivot=(1, 1, 1))), tuple(expected_vector))
                    self.assertTrue(matrix.mirror(axis, (1, 1, 1)).isEquivalent(expected_matrix, 1e-12))
                    self.assertTrue(rotation.mirror(axis).isEquivalent(expected_rotation, 1e-12))
                    quaternion = rotation.asQuaternion()
                    self.assertTrue(quaternion.mirror(axis).isEquivalent(quaternion.mirror(group[0]), 1e-12))
                    copy = Vector(vector)
                    self.assertIs(copy.mirrorIt(axis, pivot=(1, 1, 1)), copy)
                    self.assertEqual(tuple(copy), tuple(expected_vector))
        self.assertEqual(tuple(vector.mirror("YZ")), (-1.0, 2.0, 3.0))
        for axis, error in (("xyz", ValueError), ("xx", ValueError), ("w", ValueError), (None, TypeError),
                            (True, TypeError)):
            with self.subTest(axis=axis), self.assertRaises(error):
                vector.mirror(axis)

    def test_mirror_transform(self):
        """Transform.mirrorTransform の "x" と "YZ" は同じマトリクス。"""
        name = self.make("transform", "mirrored")
        cmds.setAttr(name + ".translate", 1, 2, 3)
        cmds.setAttr(name + ".rotate", 12, 23, 34)
        node = Node(name)
        original = node.getMatrix(worldSpace=True)
        for group in _EQUIVALENT_AXES:
            expected = original.mirror(group[0], (4, 5, 6))
            for axis in group:
                with self.subTest(axis=axis):
                    node.setMatrix(original, worldSpace=True)
                    node.mirrorTransform(axis, worldSpace=True, pivot=(4, 5, 6))
                    self.assertTrue(node.getMatrix(worldSpace=True).isEquivalent(expected, 1e-7))

    def test_joint_mirror_accepts_flip_axis(self):
        """Joint.mirror("x") は "YZ" と同じ面で鏡映する。"""
        root = self.make("joint", "L_root")
        cmds.setAttr(root + ".translate", 2, 1, 0)
        tip = self.make("joint", "L_tip", parent=root)
        cmds.setAttr(tip + ".translate", 3, 0, 1)
        results = []
        for axis in ("YZ", "x", "zy"):
            new_root = Joint(root).mirror(axis, searchReplace=("L_", "R_"))
            results.append([cmds.xform(n, query=True, worldSpace=True, translation=True)
                            for n in [new_root.getFullName()]
                            + cmds.listRelatives(new_root.getFullName(), allDescendents=True, fullPath=True)])
            cmds.delete(new_root.getFullName())
        for result in results[1:]:
            for actual, wanted in zip(result, results[0]):
                self.assertSequenceAlmostEqual(actual, wanted, places=6)
        self.assertSequenceAlmostEqual(results[0][0], (-2, 1, 0), places=6)

    def test_skin_cluster_mirror_weights_accepts_flip_axis(self):
        """SkinCluster.mirrorWeights("x") は "YZ" と同じウェイトになる。"""
        mesh = cmds.polyCube(name=self.name("mesh"), width=4, subdivisionsWidth=4, constructionHistory=False)[0]
        cmds.select(clear=True)
        left = cmds.joint(name=self.name("L_jnt"), position=(2, 0, 0))
        cmds.select(clear=True)
        right = cmds.joint(name=self.name("R_jnt"), position=(-2, 0, 0))
        skin_name = cmds.skinCluster(left, right, mesh, toSelectedBones=True)[0]
        skin = Node(skin_name)
        vertices = "%s.vtx[*]" % mesh
        results = []
        for axis in ("YZ", "x", "ZY"):
            cmds.skinPercent(skin_name, vertices, transformValue=[(left, 1.0)])
            skin.mirrorWeights(axis, influenceAssociation=("closestJoint",))
            results.append(cmds.getAttr(skin_name + ".weightList[*].weights[*]"))
        self.assertEqual(len(results[0]), len(results[1]))
        for result in results[1:]:
            self.assertSequenceAlmostEqual(result, results[0], places=6)


if __name__ == "__main__":
    unittest.main()
