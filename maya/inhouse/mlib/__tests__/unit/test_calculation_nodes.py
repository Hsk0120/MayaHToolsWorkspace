"""計算ノードを実際のMaya DGで評価し、継承・単位・Undoを検証する。"""
import math
import sys
import unittest
import maya.cmds as cmds
import mlib
from mlib.maths import Matrix


class CalculationNodesTest(unittest.TestCase):
    """専用namespaceに作成し、終了時に対象だけを削除する。"""

    def setUp(self):
        """Maya付属の行列ノードとテスト専用namespaceを用意する。"""
        cmds.loadPlugin("matrixNodes", quiet=True)
        self.old_namespace = cmds.namespaceInfo(currentNamespace=True)
        self.namespace = cmds.namespace(add="mlibCalculationTest")
        cmds.namespace(set=self.namespace)

    def tearDown(self):
        """テスト対象を削除し、namespaceを復元する。"""
        cmds.namespace(set=self.old_namespace)
        cmds.namespace(removeNamespace=self.namespace, deleteNamespaceContent=True)

    def assertVector(self, actual, expected):
        """3要素の計算結果を許容誤差付きで比較する。"""
        self.assertEqual(len(tuple(actual)), len(tuple(expected)))
        for a, e in zip(actual, expected):
            self.assertAlmostEqual(a, e, places=5)

    def test_native_types(self):
        """公開クラスとMayaの実型・継承列が一致する。"""
        types = "multiplyDivide plusMinusAverage condition clamp reverse remapValue setRange vectorProduct angleBetween composeMatrix inverseMatrix pickMatrix blendMatrix aimMatrix fourByFourMatrix pairBlend addDoubleLinear multDoubleLinear unitConversion curveInfo pointOnCurveInfo pointOnSurfaceInfo".split()
        for kind in types:
            with self.subTest(kind=kind):
                node = mlib.createNode(kind)
                actual = cmds.nodeType(node.getFullName())
                self.assertIs(type(node), mlib.nodes.Node._registry.lookup(actual))
                native = cmds.nodeType(node.getFullName(), inherited=True)
                declared = {cls: name for name, cls in mlib.nodes._WRAPPER_CLASSES.items()}
                for cls in type(node).__mro__:
                    name = declared.get(cls)
                    if name and name != "dependNode":
                        self.assertIn(name, native)


    def test_vector_and_angle(self):
        """内積・外積と角度出力を検証する。"""
        node = mlib.createNode("vectorProduct")
        node.setInput(1, (1, 0, 0)).setInput(2, (0, 1, 0)).setOperation("cross")
        self.assertVector(node.getResult(), (0, 0, 1))
        node.setOperation("dot")
        self.assertVector(node.getResult(), (0, 0, 0))
        angle = mlib.createNode("angleBetween")
        angle.setInput(1, (1, 0, 0)).setInput(2, (0, 1, 0))
        self.assertAlmostEqual(angle.getResult(), math.pi / 2)
        self.assertVector(angle.getAxis(), (0, 0, 1))
        # 既定値(0, 0, 1)と異なる軸も評価済みの値を返す(FINDINGS A-5 で修正)。
        angle.setInput(2, (0, 0, 1))
        self.assertVector(angle.getAxis(), (0, -1, 0))

    def test_matrix_nodes(self):
        """行列の合成・逆行列・成分選択・16要素設定を検証する。"""
        compose = mlib.createNode("composeMatrix")
        compose.setTranslate((3, 4, 5)).setScale((2, 2, 2))
        matrix = compose.getResult()
        inverse = mlib.createNode("inverseMatrix")
        inverse.connectInput(compose.getOutputPlug())
        self.assertVector(tuple(matrix * inverse.getResult()), tuple(Matrix()))
        pick = mlib.createNode("pickMatrix")
        pick.connectInput(compose.getOutputPlug()).setUseScale(False)
        self.assertAlmostEqual(pick.getResult()[0], 1)
        self.assertAlmostEqual(pick.getResult()[12], 3)
        four = mlib.createNode("fourByFourMatrix")
        four.setMatrix(matrix)
        self.assertVector(tuple(four.getResult()), tuple(matrix))
        cmds.undo()
        self.assertVector(tuple(four.getMatrix()), tuple(Matrix()))
        compose.setRotate((0, 0, math.pi / 2))
        self.assertAlmostEqual(compose.getResult()[1], 2)
        compose.setQuaternion((0, 0, 0, 1)).setUseEulerRotation(False)
        self.assertAlmostEqual(compose.getResult()[0], 2)

    def test_blend_and_aim(self):
        """行列ブレンドの重みとAimの向きを検証する。"""
        compose = mlib.createNode("composeMatrix")
        compose.setTranslate((10, 0, 0))
        blend = mlib.createNode("blendMatrix")
        blend.setTarget(3, compose.getResult(), .25)
        self.assertAlmostEqual(blend.getResult()[12], 2.5)
        self.assertEqual(blend.getTargetIndices(), [3])
        self.assertEqual(blend.getTarget(3)["weight"], .25)
        blend.removeTarget(3)
        cmds.undo()
        self.assertAlmostEqual(blend.getResult()[12], 2.5)
        aim = mlib.createNode("aimMatrix")
        compose.setTranslate((0, 10, 0))
        aim.connectPrimaryMatrix(compose.getOutputPlug())
        aim.setPrimaryAxis((1, 0, 0)).setPrimaryMode("aim").setSecondaryMode("none")
        self.assertAlmostEqual(aim.getResult()[1], 1)


    def test_pair_blend(self):
        """移動とQuaternion補間の回転結果を検証する。"""
        node = mlib.createNode("pairBlend")
        node.setTranslate(1, (0, 0, 0)).setTranslate(2, (10, 0, 0))
        node.setRotate(1, (0, 0, 0)).setRotate(2, (0, 0, math.pi / 2))
        node.setRotateInterpolation("quaternion").setWeight(.5)
        self.assertVector(node.getResult(), (5, 0, 0))
        self.assertVector(node.getResult("rotate"), (0, 0, math.pi / 4))


    def test_curve_queries(self):
        """ローカル/ワールド空間のカーブ長・位置と接線を検証する。"""
        curve = mlib.getNode(cmds.curve(d=1, p=[(0, 0, 0), (10, 0, 0)]))
        curve.getPlug("scale").set((2, 2, 2))
        info = mlib.createNode("curveInfo")
        info.connectCurve(curve, ws=False)
        self.assertAlmostEqual(info.getPlug('arcLength').get(), 10)
        info.connectCurve(curve, force=True)
        self.assertAlmostEqual(info.getPlug('arcLength').get(), 20)
        point = mlib.createNode("pointOnCurveInfo")
        point.connectCurve(curve).setParameter(.5, percentage=True)
        self.assertVector(point.getPosition(), (10, 0, 0))
        self.assertVector(point.getTangent(), (1, 0, 0))

    def test_surface_queries(self):
        """サーフェスの位置・法線・接線を実形状で検証する。"""
        surface = mlib.getNode(cmds.nurbsPlane(axis=(0, 1, 0), width=4)[0])
        point = mlib.createNode("pointOnSurfaceInfo")
        point.connectSurface(surface).setParameters(.5, .5, percentage=True)
        self.assertVector(point.getPosition(), (0, 0, 0))
        self.assertAlmostEqual(point.getNormal().length(), 1)
        self.assertAlmostEqual(point.getTangent("u").length(), 1)
        self.assertAlmostEqual(point.getTangent("v").length(), 1)
        with self.assertRaises(TypeError):
            point.connectSurface(mlib.getNode(cmds.polyCube()[0]).getShape())


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
