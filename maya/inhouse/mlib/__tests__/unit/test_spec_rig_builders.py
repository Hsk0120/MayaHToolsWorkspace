"""リグ構築の補助API(5.0.0)の約束を固定する。

対象: BlendShape(create・getTargetNames・getTargetIndex・getWeightPlug・addTarget・removeTarget・in)、
IkHandle.create・getEffector・getCurve、Joint.orient・Joints.orient、Joint.mirror、
mlib.duplicate(suffix=...)。いずれも cmds の結果と突き合わせ、Undo 1回で戻ること、
不正入力が編集前に型付きの例外になることを確かめる。
"""

import unittest

import maya.cmds as cmds

import mlib
mlib.reload()
from mlib.nodes import BlendShape, IkHandle, Joint, Joints, Node
from mlib.plugs import Plug
from support.specCase import NamespaceCase


class _SpecCase(NamespaceCase):
    """このテストファイルの名前空間の先頭と、共通基底からの差分。"""

    PREFIX = "mlibSpecRigBuilders_"
    CLEAR_SELECTION = True

    def setUp(self):
        super().setUp()
        # Maya が現在の名前空間へ作るノード(エフェクター・自動カーブ・名前空間を外した鏡映)も片付ける。
        self.existing = set(cmds.ls(long=True))

    def tearDown(self):
        for name in cmds.ls(long=True):
            if (name not in self.existing and cmds.objExists(name) and not cmds.lockNode(name, query=True)[0]
                    and not cmds.objectType(name, isAType="ikSolver")):
                cmds.delete(name)
        super().tearDown()

    def chain(self, *items):
        """(名前, 位置) の並びで、選択を使わずに親子の joint を作る。"""
        cmds.select(clear=True)
        names = [cmds.joint(name=self.name(text), position=position) for text, position in items]
        cmds.select(clear=True)
        return [cmds.ls(name, long=True)[0] for name in names]

    def sphere(self, text):
        """構築履歴の無い polySphere の transform を作る。"""
        return cmds.polySphere(name=self.name(text), constructionHistory=False)[0]

    def aliases(self, blend):
        """aliasAttr の照会から、weight のエイリアスを論理番号順に返す。"""
        items = cmds.aliasAttr(str(blend), query=True) or []
        pairs = [(int(target[target.index("[") + 1:-1]), alias)
                 for alias, target in zip(items[::2], items[1::2]) if target.startswith("weight[")]
        return [alias for _index, alias in sorted(pairs)]

    def leaf(self, name):
        """完全パス・名前空間を除いた名前を返す。"""
        return name.split("|")[-1].split(":")[-1]


class BlendShapeCreateTest(_SpecCase):
    """BlendShape.create は cmds.blendShape と同じターゲット構成を作る。"""

    def setUp(self):
        super().setUp()
        self.base = self.sphere("base")
        self.smile = self.sphere("smile_L")
        self.blink = self.sphere("blink")

    def test_registered_class(self):
        """blendShape は手書きの BlendShape として包まれる。"""
        node = Node(cmds.blendShape(self.smile, self.base)[0])
        self.assertIs(type(node), BlendShape)
        self.assertIn("BlendShape", mlib.nodes.__all__)

    def test_create_matches_cmds(self):
        """ターゲットは指定順に 0 から並び、名前・ウェイトは cmds の照会と一致する。frontOfChain が既定。"""
        bs = BlendShape.create(self.base, [self.smile, self.blink], name=self.name("bs"))
        self.assertIs(type(bs), BlendShape)
        self.assertEqual(bs.getName(), self.name("bs"))
        self.assertEqual(bs.getTargetNames(), self.aliases(bs))
        self.assertEqual(bs.getTargetNames(), ["smile_L", "blink"])
        self.assertEqual(bs.getTargetIndex("blink"), 1)
        self.assertEqual([n.getFullName() for n in bs.getBaseGeometry()],
                         cmds.ls(cmds.blendShape(bs.getFullName(), query=True, geometry=True), long=True))

    def test_front_of_chain(self):
        """既定はスキンより前(履歴の上流)、frontOfChain=False は最後に置く。"""
        cmds.select(clear=True)
        joint = cmds.joint(name=self.name("bind"))
        cmds.select(clear=True)
        skin = cmds.skinCluster(joint, self.base, toSelectedBones=True)[0]
        front = BlendShape.create(self.base, self.smile, name=self.name("front"))
        last = BlendShape.create(self.base, self.blink, name=self.name("last"), frontOfChain=False)
        history = cmds.listHistory(self.base, pruneDagObjects=True, interestLevel=1)
        self.assertLess(history.index(skin), history.index(front.getName()))
        self.assertLess(history.index(last.getName()), history.index(skin))

    def test_empty_create_and_undo(self):
        """ターゲット省略で空の blendShape を作る。作成は Undo 1回で戻る。"""
        self.flushUndo()
        bs = BlendShape.create(self.base, name=self.name("empty"))
        name = bs.getFullName()
        self.assertEqual(bs.getTargetNames(), [])
        self.assertUndoesInOneStep(lambda: self.assertFalse(cmds.objExists(name)),
                                   lambda: self.assertTrue(cmds.objExists(name)))

    def test_create_errors(self):
        """不正な引数は作成前に型付きの例外になり、blendShape を残さない。"""
        before = cmds.ls(type="blendShape")
        with self.assertRaisesRegex(TypeError, "frontOfChain must be a bool"):
            BlendShape.create(self.base, self.smile, frontOfChain=1)
        with self.assertRaises(TypeError):
            BlendShape.create(self.base, self.smile, name=1)
        with self.assertRaises(ValueError):
            BlendShape.create(self.base, self.smile, name="")
        with self.assertRaises(RuntimeError):
            BlendShape.create(self.name("missing"), self.smile)
        self.assertEqual(cmds.ls(type="blendShape"), before)


class BlendShapeTargetTest(_SpecCase):
    """ターゲット名による照会・追加・除去。"""

    def setUp(self):
        super().setUp()
        self.base = self.sphere("base")
        self.smile = self.sphere("smile_L")
        self.frown = self.sphere("frown")
        self.blink = self.sphere("blink")
        self.bs = BlendShape.create(self.base, [self.smile, self.frown], name=self.name("bs"))
        self.full = self.bs.getFullName()

    def test_membership_and_weight_plug(self):
        """in はターゲット名の有無、getWeightPlug は weight[i] の Plug を返す。"""
        self.assertIn("smile_L", self.bs)
        self.assertNotIn("missing", self.bs)
        plug = self.bs.getWeightPlug("frown")
        self.assertIsInstance(plug, Plug)
        self.assertEqual((plug.getMulti().getLongName(), plug.getIndex()), ("weight", 1))
        plug.set(0.25)
        self.assertAlmostEqual(cmds.getAttr(self.full + ".frown"), 0.25)

    def test_lookup_errors(self):
        """存在しない名前は ValueError、文字列以外は TypeError。"""
        with self.assertRaisesRegex(ValueError, "No blendShape target named 'missing'"):
            self.bs.getTargetIndex("missing")
        with self.assertRaises(ValueError):
            self.bs.getWeightPlug("missing")
        with self.assertRaises(TypeError):
            self.bs.getTargetIndex(0)
        with self.assertRaises(TypeError):
            0 in self.bs

    def test_add_target_and_undo(self):
        """次の番号へ追加し、name でエイリアスを付ける。cmds の照会と一致し、Undo 1回で戻る。"""
        self.flushUndo()
        plug = self.bs.addTarget(self.blink, name="eyeBlink")
        self.assertEqual((plug.getMulti().getLongName(), plug.getIndex()), ("weight", 2))
        self.assertEqual(self.bs.getTargetNames(), ["smile_L", "frown", "eyeBlink"])
        self.assertEqual(self.bs.getTargetNames(), self.aliases(self.bs))
        self.assertUndoesInOneStep(
            lambda: self.assertEqual(self.bs.getTargetNames(), ["smile_L", "frown"]),
            lambda: self.assertIn("eyeBlink", self.bs))

    def test_add_target_default_name(self):
        """name を省略すると Maya の既定(メッシュの名前)になる。"""
        self.bs.addTarget(self.blink)
        self.assertEqual(self.bs.getTargetNames(), ["smile_L", "frown", "blink"])

    def test_add_target_errors(self):
        """重複名・不正な name・存在しないメッシュは追加前に拒否する。"""
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.bs.addTarget(self.blink, name="frown")
        with self.assertRaises(ValueError):
            self.bs.addTarget(self.blink, name="")
        with self.assertRaises(TypeError):
            self.bs.addTarget(self.blink, name=3)
        with self.assertRaises(RuntimeError):
            self.bs.addTarget(self.name("missing"))
        self.assertEqual(self.bs.getTargetNames(), ["smile_L", "frown"])

    def test_remove_target_fully(self):
        """weight の要素・エイリアス・inputTargetGroup を消す(cmds の remove と同じ)。Undo 1回で戻る。"""
        self.flushUndo()
        self.assertIs(self.bs.removeTarget("smile_L"), self.bs)
        self.assertEqual(self.bs.getTargetNames(), ["frown"])
        self.assertEqual(cmds.getAttr(self.full + ".weight", multiIndices=True), [1])
        self.assertEqual(cmds.getAttr(self.full + ".inputTarget[0].inputTargetGroup", multiIndices=True), [1])
        self.assertNotIn("smile_L", cmds.aliasAttr(self.full, query=True))
        self.assertUndoesInOneStep(
            lambda: self.assertEqual(self.bs.getTargetNames(), ["smile_L", "frown"]),
            lambda: self.assertNotIn("smile_L", self.bs))
        self.assertEqual(cmds.getAttr(self.full + ".inputTarget[0].inputTargetGroup", multiIndices=True), [0, 1])

    def test_remove_matches_cmds_remove(self):
        """cmds.blendShape(edit=True, remove=True) と同じ属性の状態になる。"""
        other_base = self.sphere("otherBase")
        other = cmds.blendShape(self.smile, self.frown, other_base, name=self.name("other"))[0]
        cmds.blendShape(other, edit=True, remove=True, target=(other_base, 0, self.smile, 1.0))
        self.bs.removeTarget("smile_L")
        for attribute in ("weight", "inputTarget[0].inputTargetGroup"):
            self.assertEqual(cmds.getAttr(self.full + "." + attribute, multiIndices=True),
                             cmds.getAttr(other + "." + attribute, multiIndices=True))
        self.assertEqual(self.bs.getTargetNames(), self.aliases(other))

    def test_remove_with_deleted_target_mesh(self):
        """ターゲットのメッシュを削除した後でも除去できる。"""
        cmds.delete(self.smile)
        self.bs.removeTarget("smile_L")
        self.assertEqual(self.bs.getTargetNames(), ["frown"])
        self.assertEqual(cmds.getAttr(self.full + ".inputTarget[0].inputTargetGroup", multiIndices=True), [1])

    def test_remove_errors(self):
        """存在しない名前は ValueError、ロックしたウェイトは RuntimeError で、何も変えない。"""
        with self.assertRaises(ValueError):
            self.bs.removeTarget("missing")
        cmds.setAttr(self.full + ".weight[0]", lock=True)
        with self.assertRaisesRegex(RuntimeError, "locked"):
            self.bs.removeTarget("smile_L")
        self.assertEqual(self.bs.getTargetNames(), ["smile_L", "frown"])

    def test_deleted_node(self):
        """削除済みの blendShape の照会は RuntimeError。"""
        cmds.delete(self.full)
        with self.assertRaises(RuntimeError):
            self.bs.getTargetNames()


class IkHandleCreateTest(_SpecCase):
    """IkHandle.create は cmds.ikHandle と同じハンドル・エフェクターを作る。"""

    def setUp(self):
        super().setUp()
        self.j1, self.j2, self.j3 = self.chain(("a", (0, 0, 0)), ("b", (2, 0, -1)), ("c", (4, 0, 0)))

    def test_rp_solver(self):
        """既定は ikRPsolver。エフェクターは end joint の1つ上の子で、getJoints が cmds と一致する。"""
        handle = IkHandle.create(self.j1, self.j3, name=self.name("hdl"))
        self.assertIs(type(handle), IkHandle)
        self.assertEqual(handle.getName(), self.name("hdl"))
        self.assertEqual(cmds.ikHandle(handle.getFullName(), query=True, solver=True), "ikRPsolver")
        effector = handle.getEffector()
        self.assertTrue(effector.isType("ikEffector"))
        self.assertEqual(effector.getParent().getFullName(), self.j2)
        self.assertEqual(effector.getFullName(),
                         cmds.ls(cmds.ikHandle(handle.getFullName(), query=True, endEffector=True), long=True)[0])
        self.assertEqual([j.getFullName() for j in handle.getJoints()],
                         cmds.ls(cmds.ikHandle(handle.getFullName(), query=True, jointList=True), long=True))
        self.assertEqual(handle.getEndJoint(), Joint(self.j3))
        self.assertIsNone(handle.getCurve())

    def test_sc_and_extra_flags(self):
        """ikSCsolver と、Maya の他のフラグ(priority)をそのまま渡せる。"""
        handle = IkHandle.create(self.j1, self.j3, solver="ikSCsolver", priority=3)
        self.assertEqual(cmds.ikHandle(handle.getFullName(), query=True, solver=True), "ikSCsolver")
        self.assertEqual(cmds.ikHandle(handle.getFullName(), query=True, priority=True), 3)

    def test_spline_auto_curve(self):
        """ikSplineSolver で curve を省略すると Maya がカーブを作り、getCurve で取得できる。"""
        handle = IkHandle.create(self.j1, self.j3, solver="ikSplineSolver")
        curve = handle.getCurve()
        self.assertIsNotNone(curve)
        self.assertTrue(curve.getShape().isType("nurbsCurve"))
        self.assertEqual(cmds.ikHandle(handle.getFullName(), query=True, curve=True).split("|")[-1],
                         curve.getShape().getName().split("|")[-1])

    def test_spline_existing_curve(self):
        """既存カーブを指定すると、そのカーブを使い新しいカーブは作らない。"""
        curve = cmds.curve(name=self.name("crv"), degree=3,
                           point=[(0, 0, 0), (1, 0, 0), (3, 0, 0), (4, 0, 0)])
        before = set(cmds.ls(type="nurbsCurve", long=True))
        handle = IkHandle.create(self.j1, self.j3, solver="ikSplineSolver", curve=curve)
        self.assertEqual(set(cmds.ls(type="nurbsCurve", long=True)), before)
        self.assertEqual(handle.getCurve(), Node(curve))

    def test_undo_once(self):
        """作成(ハンドル・エフェクター・Maya が設定する preferredAngle)は Undo 1回で戻る。"""
        # シーンで最初の IK ハンドルが作るソルバーは Undo で消えない(cmds.ikHandle と同じ)ので先に作る。
        warm = self.chain(("w0", (0, 0, 5)), ("w1", (1, 0, 5)))
        IkHandle.create(warm[0], warm[1], solver="ikSCsolver")
        cmds.delete(warm[0])
        # まっすぐな連鎖では Maya が中間 joint の preferredAngle を設定する。
        straight = self.chain(("s0", (0, 0, 0)), ("s1", (0, 1, 0)), ("s2", (0, 2, 0)))
        self.flushUndo()
        before = cmds.getAttr(straight[1] + ".preferredAngle")[0]
        IkHandle.create(straight[0], straight[2], name=self.name("hdl"))

        def unchanged():
            self.assertEqual(cmds.ls(type=("ikHandle", "ikEffector")), [])
            self.assertEqual(cmds.getAttr(straight[1] + ".preferredAngle")[0], before)

        def changed():
            self.assertEqual(len(cmds.ls(type=("ikHandle", "ikEffector"))), 2)
            self.assertNotEqual(cmds.getAttr(straight[1] + ".preferredAngle")[0], before)

        self.assertUndoesInOneStep(unchanged, changed)

    def test_errors(self):
        """不正な引数は作成前に型付きの例外になり、ノードを残さない。"""
        other, = self.chain(("other", (0, 5, 0)))
        cases = [
            (ValueError, dict(startJoint=self.j1, endJoint=self.j3, solver="badSolver")),
            (ValueError, dict(startJoint=self.j1, endJoint=self.j3, curve=self.j1)),
            (ValueError, dict(startJoint=self.j3, endJoint=self.j1)),
            (ValueError, dict(startJoint=self.j1, endJoint=other)),
            (ValueError, dict(startJoint=self.j1, endJoint=self.j3, name="")),
            (TypeError, dict(startJoint=self.j1, endJoint=self.j3, name=1)),
            (TypeError, dict(startJoint=self.j1, endJoint=self.j3, sol="ikSCsolver")),
            (RuntimeError, dict(startJoint=self.name("missing"), endJoint=self.j3)),
        ]
        transform = cmds.createNode("transform", name=self.name("xform"), parent=self.j2, skipSelect=True)
        cases.append((ValueError, dict(startJoint=self.j1, endJoint=transform)))
        for error, flags in cases:
            with self.subTest(flags=flags):
                with self.assertRaises(error):
                    IkHandle.create(**flags)
        self.assertEqual(cmds.ls(type=("ikHandle", "ikEffector")), [])

    def test_get_effector_on_unconnected_handle(self):
        """createNode で作った未接続のハンドルの getEffector は None。"""
        handle = mlib.createNode("ikHandle", name=self.name("bare"))
        self.assertIsNone(handle.getEffector())
        self.assertIsNone(handle.getCurve())


class JointOrientTest(_SpecCase):
    """Joint.orient は cmds.joint(edit=True, orientJoint=...) と同じ向きにし、末端を 0 にする。"""

    def setUp(self):
        super().setUp()
        items = (("a", (0, 0, 0)), ("b", (2, 1, -1)), ("c", (4, 0, 1)), ("d", (5, 2, 1)))
        self.joints = self.chain(*items)
        self.reference = self.chain(*(("ref_" + text, position) for text, position in items))
        for name in (self.joints[-1], self.reference[-1]):
            cmds.setAttr(name + ".jointOrient", 10, 20, 30)

    def orients(self, names):
        return [cmds.getAttr(name + ".jointOrient")[0] for name in names]

    def assertOrients(self, actual, expected):
        self.assertEqual(len(actual), len(expected))
        for a, e in zip(actual, expected):
            self.assertSequenceAlmostEqual(a, e, places=6)

    def positions(self, names):
        return [cmds.xform(name, query=True, worldSpace=True, translation=True) for name in names]

    def test_matches_cmds_and_zeroes_end(self):
        """末端以外は cmds.joint と同じ jointOrient、末端は 0。子の位置は変わらない。"""
        positions = self.positions(self.joints)
        cmds.joint(self.reference[0], edit=True, orientJoint="xyz", secondaryAxisOrient="yup",
                   children=True, zeroScaleOrient=True)
        joint = Joint(self.joints[0])
        self.assertIs(joint.orient(), joint)
        for actual, expected in zip(self.orients(self.joints[:-1]), self.orients(self.reference[:-1])):
            self.assertSequenceAlmostEqual(actual, expected)
        self.assertSequenceAlmostEqual(self.orients(self.joints[-1:])[0], (0, 0, 0))
        for actual, expected in zip(self.positions(self.joints), positions):
            self.assertSequenceAlmostEqual(actual, expected, places=6)

    def test_flags(self):
        """orientation・secondaryAxisOrient・children=False は cmds の同じフラグと一致する。"""
        for orientation, secondary in (("yzx", "zup"), ("zxy", "xdown"), ("none", "yup")):
            with self.subTest(orientation=orientation, secondary=secondary):
                cmds.joint(self.reference[1], edit=True, orientJoint=orientation,
                           secondaryAxisOrient=secondary, children=False, zeroScaleOrient=True)
                Joint(self.joints[1]).orient(orientation, secondary, children=False)
                self.assertSequenceAlmostEqual(self.orients(self.joints[1:2])[0], self.orients(self.reference[1:2])[0])
        # children=False では子孫の末端を触らない。
        self.assertSequenceAlmostEqual(self.orients(self.joints[-1:])[0], (10, 20, 30))

    def test_undo_once(self):
        """全 joint の変更が Undo 1回で戻る。"""
        before = self.orients(self.joints)
        self.flushUndo()
        Joint(self.joints[0]).orient()
        after = self.orients(self.joints)
        self.assertUndoesInOneStep(lambda: self.assertOrients(self.orients(self.joints), before),
                                   lambda: self.assertOrients(self.orients(self.joints), after))

    def test_joints_collection(self):
        """Joints.orient は各要素へ適用し、Undo 1回で戻る。"""
        cmds.joint(self.reference[0], edit=True, orientJoint="xyz", secondaryAxisOrient="yup",
                   children=False, zeroScaleOrient=True)
        cmds.joint(self.reference[1], edit=True, orientJoint="xyz", secondaryAxisOrient="yup",
                   children=False, zeroScaleOrient=True)
        self.flushUndo()
        joints = Joints([self.joints[0], self.joints[1]])
        self.assertIs(joints.orient(children=False), joints)
        for actual, expected in zip(self.orients(self.joints[:2]), self.orients(self.reference[:2])):
            self.assertSequenceAlmostEqual(actual, expected)
        cmds.undo()
        self.assertSequenceAlmostEqual(self.orients(self.joints[:1])[0], (0, 0, 0))
        self.assertTrue(cmds.undoInfo(query=True, undoQueueEmpty=True))

    def test_errors(self):
        """不正な引数は編集前に型付きの例外になる。ロックした末端は RuntimeError。"""
        joint = Joint(self.joints[0])
        before = self.orients(self.joints)
        for error, args in ((ValueError, ("abc",)), (ValueError, ("xyz", "up")), (TypeError, (1,)),
                            (TypeError, ("xyz", None))):
            with self.subTest(args=args):
                with self.assertRaises(error):
                    joint.orient(*args)
        with self.assertRaisesRegex(TypeError, "children must be a bool"):
            joint.orient(children=1)
        with self.assertRaisesRegex(TypeError, "zeroScaleOrient must be a bool"):
            Joints(self.joints).orient(zeroScaleOrient=None)
        self.assertOrients(self.orients(self.joints), before)
        cmds.setAttr(self.joints[-1] + ".jointOrient", lock=True)
        with self.assertRaises(RuntimeError):
            joint.orient()


class JointMirrorTest(_SpecCase):
    """Joint.mirror は cmds.mirrorJoint と同じチェーンを作り、新しいルートを返す。"""

    def setUp(self):
        super().setUp()
        self.group = cmds.createNode("transform", name=self.name("grp"), skipSelect=True)
        self.joints = self.chain(("L_a", (1, 0, 0)), ("L_b", (3, 1, -1)), ("L_c", (5, 0, 1)))
        cmds.parent(self.joints[0], self.group)
        self.joints = cmds.ls(cmds.listRelatives(self.group, allDescendents=True, fullPath=True), long=True)[::-1]
        Joint(self.joints[0]).orient()

    def matrices(self, root):
        names = [root] + (cmds.listRelatives(root, allDescendents=True, fullPath=True) or [])[::-1]
        return [cmds.xform(name, query=True, worldSpace=True, matrix=True) for name in names]

    def test_matches_cmds(self):
        """全フラグの組み合わせで、新しいルートの名前・親・ワールドマトリクスが cmds と一致する。"""
        for axis in ("YZ", "XY", "xz"):
            for behavior in (True, False):
                with self.subTest(axis=axis, behavior=behavior):
                    flag = "mirror" + axis.upper()
                    expected = cmds.mirrorJoint(self.joints[0], mirrorBehavior=behavior,
                                                searchReplace=("L_", "E_"), **{flag: True})
                    expected_root = self.group + "|" + expected[0]
                    root = Joint(self.joints[0]).mirror(axis, behavior, searchReplace=("L_", "R_"))
                    self.assertIs(type(root), Joint)
                    self.assertEqual(root.getParent(), Node(self.group))
                    self.assertEqual(self.leaf(root.getName()), "R_a")
                    self.assertEqual([self.leaf(n.getName()) for n in root.getChainFromHere()],
                                     ["R_a", "R_b", "R_c"])
                    for actual, wanted in zip(self.matrices(root.getFullName()), self.matrices(expected_root)):
                        self.assertSequenceAlmostEqual(actual, wanted, places=6)
                    cmds.delete(root.getFullName(), expected_root)

    def test_world_root_and_auto_name(self):
        """親の無いルートでも新しいルートを一意に返す。searchReplace 省略は Maya の自動命名。"""
        cmds.parent(self.joints[0], world=True)
        root_name = cmds.ls(self.name("L_a"), long=True)[0]
        root = Joint(root_name).mirror()
        self.assertIsNone(root.getParent())
        self.assertNotEqual(root, Joint(root_name))
        self.assertEqual(len(root.getChainFromHere()), 3)

    def test_undo_once(self):
        """鏡映は Undo 1回で戻り、選択も元に戻る。新しいルートを選択する。元のチェーンは変わらない。"""
        before = self.matrices(self.joints[0])
        cmds.select(clear=True)
        self.flushUndo()
        root = Joint(self.joints[0]).mirror(searchReplace=("L_", "R_"))
        self.assertEqual(cmds.ls(selection=True, long=True), [root.getFullName()])
        self.assertUndoesInOneStep(
            lambda: self.assertEqual((cmds.ls(self.name("R_*")), cmds.ls(selection=True)), ([], [])),
            lambda: self.assertEqual(len(cmds.ls(self.name("R_*"))), 3))
        self.assertEqual(self.matrices(self.joints[0]), before)

    def test_errors(self):
        """不正な引数は編集前に型付きの例外になる。"""
        joint = Joint(self.joints[0])
        cases = ((ValueError, dict(axis="X")), (TypeError, dict(axis=1)), (TypeError, dict(behavior=1)),
                 (TypeError, dict(searchReplace="L_")), (TypeError, dict(searchReplace=("L_",))),
                 (TypeError, dict(searchReplace=("L_", 1))), (ValueError, dict(searchReplace=("", "R_"))))
        before = cmds.ls(type="joint")
        for error, flags in cases:
            with self.subTest(flags=flags):
                with self.assertRaises(error):
                    joint.mirror(**flags)
        self.assertEqual(cmds.ls(type="joint"), before)
        cmds.delete(self.joints[0])
        with self.assertRaises(RuntimeError):
            joint.mirror()


class DuplicateSuffixTest(_SpecCase):
    """mlib.duplicate(suffix=...) は複製の起点と全 DAG 子孫へ接尾辞を付ける。"""

    def setUp(self):
        super().setUp()
        self.joints = self.chain(("L_hip", (0, 5, 0)), ("L_knee", (0, 3, 1)), ("L_ankle", (0, 1, 0)))
        self.cube = cmds.polyCube(name=self.name("box"), constructionHistory=False)[0]
        cmds.parent(self.cube, self.joints[1])

    def names(self, root):
        """root と DAG 子孫の名前(名前空間付き)を並べ替えて返す。"""
        names = [root] + (cmds.listRelatives(root, allDescendents=True, fullPath=True) or [])
        return sorted(name.split("|")[-1] for name in cmds.ls(names, long=True))

    def leaves(self, root):
        """root と DAG 子孫の、名前空間を除いた名前を並べ替えて返す。"""
        return sorted(self.leaf(name) for name in self.names(root))

    def test_suffix_renames_chain(self):
        """L_hip|L_knee|... が L_hip_FK|L_knee_FK|... になり、shape にも付く。

        名前空間は Maya が複製を置いた名前空間(現在の名前空間)のまま。
        """
        copy = mlib.duplicate(self.joints[0], suffix="_FK")
        self.assertIs(type(copy), Joint)
        self.assertEqual(copy.getName(), "L_hip_FK")
        self.assertEqual(self.names(copy.getFullName()),
                         sorted(("L_hip_FK", "L_knee_FK", "L_ankle_FK", "box_FK", "boxShape_FK")))
        cmds.namespace(set=self.ns)
        try:
            copy = mlib.duplicate(self.joints[0], suffix="_IK")
        finally:
            cmds.namespace(set=":")
        self.assertEqual(self.names(copy.getFullName()), sorted(self.name(text) for text in (
            "L_hip_IK", "L_knee_IK", "L_ankle_IK", "box_IK", "boxShape_IK")))
        self.assertEqual(cmds.ls(self.joints[0], long=True), [self.joints[0]])
        self.assertEqual(self.names(self.joints[0]), sorted(self.name(text) for text in (
            "L_hip", "L_knee", "L_ankle", "box", "boxShape")))

    def test_name_keeps_root(self):
        """name を指定すると起点は name のまま、子孫だけに接尾辞を付ける。"""
        copy = mlib.duplicate(self.joints[0], name=self.name("hipRoot"), suffix="_IK")
        self.assertEqual(copy.getName(), self.name("hipRoot"))
        self.assertEqual(self.leaves(copy.getFullName()),
                         sorted(("hipRoot", "L_knee_IK", "L_ankle_IK", "box_IK", "boxShape_IK")))

    def test_parent_only_and_instance_leaf(self):
        """parentOnly は起点だけ、instanceLeaf の共有 shape は改名しない。"""
        copy = mlib.duplicate(self.joints[0], parentOnly=True, suffix="_P")
        self.assertEqual(self.leaves(copy.getFullName()), ["L_hip_P"])
        copy = mlib.duplicate(self.cube, instanceLeaf=True, suffix="_I")
        self.assertEqual(self.leaf(copy.getName()), "box_I")
        self.assertTrue(cmds.objExists(self.name("boxShape")))
        self.assertFalse(cmds.objExists(self.name("boxShape_I")))

    def test_without_suffix_unchanged(self):
        """suffix を省略すると従来どおり Maya の自動命名。"""
        copy = mlib.duplicate(self.joints[0])
        self.assertEqual(self.leaves(copy.getFullName()), sorted(("L_hip", "L_knee", "L_ankle", "box", "boxShape")))

    def test_undo_once(self):
        """複製と改名が Undo 1回で戻る。"""
        self.flushUndo()
        mlib.duplicate(self.joints[0], suffix="_FK")
        self.assertUndoesInOneStep(lambda: self.assertEqual(cmds.ls("*_FK"), []),
                                   lambda: self.assertEqual(len(cmds.ls("*_FK")), 5))

    def test_errors(self):
        """不正な suffix・renameChildren との併用は複製前に拒否する。"""
        before = cmds.ls(type="joint")
        for error, flags in ((TypeError, dict(suffix=1)), (ValueError, dict(suffix="")),
                             (ValueError, dict(suffix="a b")), (ValueError, dict(suffix="_FK", renameChildren=True)),
                             (ValueError, dict(suffix="_FK", rc=True))):
            with self.subTest(flags=flags):
                with self.assertRaises(error):
                    mlib.duplicate(self.joints[0], **flags)
        self.assertEqual(cmds.ls(type="joint"), before)


if __name__ == "__main__":
    unittest.main()
