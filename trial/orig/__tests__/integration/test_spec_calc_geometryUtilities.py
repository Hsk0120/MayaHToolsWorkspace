"""テクスチャ配置のユーティリティノードの仕様を固定する。

担当A。file・texture2d・place2dTexture のパス・色空間・接続の約束を確かめる。
"""

import unittest

import maya.api.OpenMaya as om2
import maya.cmds as cmds
import mlib
from mlib.util import _ArgumentError


def _dag(name):
    """名前からMDagPathを返す。"""
    selection = om2.MSelectionList()
    selection.add(name)
    return selection.getDagPath(0)


class _GeometryCase(unittest.TestCase):
    """専用名前空間・cm/rad・Undo有効で実行し、終了時に戻す。"""

    def setUp(self):
        self.units = (cmds.currentUnit(query=True, linear=True), cmds.currentUnit(query=True, angle=True))
        self.undo_state = cmds.undoInfo(query=True, state=True)
        cmds.undoInfo(state=True)
        cmds.currentUnit(linear="cm", angle="rad")
        self.old_namespace = cmds.namespaceInfo(currentNamespace=True)
        self.namespace = cmds.namespace(add="mlibSpecAGeometry")
        cmds.namespace(set=self.namespace)

    def tearDown(self):
        cmds.namespace(set=self.old_namespace)
        cmds.namespace(removeNamespace=self.namespace, deleteNamespaceContent=True)
        cmds.currentUnit(linear=self.units[0], angle=self.units[1])
        cmds.undoInfo(state=self.undo_state)


class TextureNodesTest(_GeometryCase):
    """file・texture2d・place2dTexture。"""

    def test_file_path(self):
        """パスはトークンを展開せずそのまま保持し、str以外はTypeError。Undoで戻る。"""
        node = mlib.createNode("file")
        self.assertEqual(node.getFilePath(), "")
        for path in ("C:/tex/a.<UDIM>.png", "relative/b_<f>.exr", "", "no_such_file_specA.tif"):
            with self.subTest(path=path):
                self.assertIs(node.setFilePath(path), node)
                self.assertEqual(node.getFilePath(), path)
                self.assertEqual(cmds.getAttr(node.getFullName() + ".fileTextureName"), path)
        node.setFilePath("first.png")
        node.setFilePath("second.png")
        self.assertEqual(cmds.undoInfo(query=True, undoName=True), "mlibFileSetFilePath")
        cmds.undo()
        self.assertEqual(node.getFilePath(), "first.png")
        for bad in (None, b"x.png", 5):
            with self.assertRaisesRegex(TypeError, "path must be a string"):
                node.setFilePath(bad)
        self.assertEqual(node.getFilePath(), "first.png")

    def test_file_color_space(self):
        """利用可能な色空間名を往復し、Undoで戻る。

        名前は検証せずに保持する(色管理の設定で変わるため)。str以外は値を変えずにTypeError
        (setFilePathと同じ)。
        """
        node = mlib.createNode("file")
        names = cmds.colorManagementPrefs(query=True, inputSpaceNames=True)
        before = node.getColorSpace()
        self.assertIn(before, names)
        target = [name for name in names if name != before][0]
        self.assertIs(node.setColorSpace(target), node)
        self.assertEqual(node.getColorSpace(), target)
        self.assertEqual(cmds.undoInfo(query=True, undoName=True), "mlibFileSetColorSpace")
        cmds.undo()
        self.assertEqual(node.getColorSpace(), before)
        node.setColorSpace("NoSuchColorSpace_specA")
        self.assertEqual(node.getColorSpace(), "NoSuchColorSpace_specA")
        for bad in (3, None, b"sRGB", ("sRGB",)):
            with self.subTest(bad=bad):
                with self.assertRaisesRegex(TypeError, "name must be a string"):
                    node.setColorSpace(bad)
                self.assertEqual(node.getColorSpace(), "NoSuchColorSpace_specA")

    def test_place2d_connect_texture(self):
        """標準の配置アトリビュートをすべて接続し、getPlacementで取得できる。再実行は何もしない。"""
        texture = mlib.createNode("file")
        self.assertIsNone(texture.getPlacement())
        place = mlib.createNode("place2dTexture")
        self.assertIs(place.connectTexture(texture), place)
        self.assertEqual(cmds.undoInfo(query=True, undoName=True), "mlibPlace2dTextureConnectTexture")
        names = ("coverage", "translateFrame", "rotateFrame", "mirrorU", "mirrorV", "stagger", "wrapU", "wrapV",
                 "repeatUV", "offset", "rotateUV", "noiseUV", "vertexUvOne", "vertexUvTwo", "vertexUvThree",
                 "vertexCameraOne")
        pairs = [(n, n) for n in names] + [("outUV", "uvCoord"), ("outUvFilterSize", "uvFilterSize")]
        expected = [(o, d) for o, d in pairs if cmds.attributeQuery(d, node=texture.getFullName(), exists=True)]
        for origin, destination in expected:
            with self.subTest(attr=destination):
                source = cmds.listConnections("%s.%s" % (texture.getFullName(), destination),
                                              source=True, destination=False)
                self.assertEqual(source, [place.getName()])
        connections = cmds.listConnections(place.getFullName(), source=False, destination=True, connections=True)
        self.assertEqual(len(connections) // 2, len(expected))
        placement = texture.getPlacement()
        self.assertIsInstance(placement, mlib.nodes.Place2dTexture)
        self.assertTrue(placement.sameNode(place))
        # 接続済みの再実行は何も変えず、Undoの記録も残さない。
        undo_name = cmds.undoInfo(query=True, undoName=True)
        place.connectTexture(texture)
        self.assertEqual(len(cmds.listConnections(place.getFullName(), source=False, destination=True,
                                                  connections=True)) // 2, len(expected))
        self.assertEqual(cmds.undoInfo(query=True, undoName=True), undo_name)
        cmds.undo()
        self.assertIsNone(texture.getPlacement())
        self.assertIsNone(cmds.listConnections(place.getFullName(), source=False, destination=True))

    def test_place2d_force_and_errors(self):
        """別の配置ノードの接続はforce/fでだけ置き換える。Texture2d以外はTypeError。"""
        texture = mlib.createNode("checker")
        self.assertIsInstance(texture, mlib.nodes.Texture2d)
        first = mlib.createNode("place2dTexture").connectTexture(texture)
        second = mlib.createNode("place2dTexture")
        with self.assertRaises(RuntimeError):
            second.connectTexture(texture)
        self.assertTrue(texture.getPlacement().sameNode(first))
        second.connectTexture(texture, force=True)
        self.assertTrue(texture.getPlacement().sameNode(second))
        self.assertIsNone(cmds.listConnections(first.getFullName(), source=False, destination=True))
        for bad in (mlib.createNode("composeMatrix"), cmds.createNode("transform")):
            with self.assertRaisesRegex(TypeError, "texture must be Texture2d"):
                second.connectTexture(bad)

    def test_get_placement_other_source(self):
        """uvCoordの入力元が配置ノード以外でも、その入力元ノードを返す。"""
        texture = mlib.createNode("file")
        source = mlib.createNode("place2dTexture")
        cmds.connectAttr(source.getFullName() + ".outUV", texture.getFullName() + ".uvCoord")
        self.assertTrue(texture.getPlacement().sameNode(source))
        cmds.disconnectAttr(source.getFullName() + ".outUV", texture.getFullName() + ".uvCoord")
        other = cmds.createNode("transform")
        cmds.addAttr(other, longName="uvSpecA", attributeType="float2")
        cmds.addAttr(other, longName="uvSpecAU", attributeType="float", parent="uvSpecA")
        cmds.addAttr(other, longName="uvSpecAV", attributeType="float", parent="uvSpecA")
        cmds.connectAttr(other + ".uvSpecA", texture.getFullName() + ".uvCoord")
        placement = texture.getPlacement()
        self.assertIsInstance(placement, mlib.nodes.Transform)
        self.assertEqual(placement.getName(), other)


if __name__ == "__main__":
    unittest.main()
