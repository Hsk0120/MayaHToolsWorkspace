"""function set の取得入口 ``mfn()`` への統合(2.1.0)の仕様テスト。

旧 ``cameraFn``・``meshFn``・``curveFn``・``referenceFn`` が無いこと、各クラスの ``mfn()`` が最も具体的な
function set を毎回新しく返すこと、形状データを持たない空の mesh・nurbsCurve では ``om2.MFnDagNode`` を
返して DagNode 共通の照会が使え、形状を要する照会は RuntimeError になることを確かめる。
"""

import sys
import unittest

import maya.api.OpenMaya as om2
import maya.cmds as cmds

import mlib
mlib.reload()
from mlib.components import Vertices
from mlib.nodes import Camera, Mesh, Node, NurbsCurve, Reference
from support.specCase import NamespaceCase


class MfnSpecTest(NamespaceCase):
    """mfn() の型・新規性・空のシェイプでの扱いを固定する。"""

    PREFIX = "mlibSpecMfn_"

    def test_old_function_set_names_are_removed(self):
        """互換別名を残さない。"""
        for cls, old in ((Camera, "cameraFn"), (Mesh, "meshFn"), (NurbsCurve, "curveFn"),
                         (Reference, "referenceFn")):
            with self.subTest(old=old):
                self.assertFalse(hasattr(cls, old))

    def test_most_specific_function_set_each_call(self):
        """camera・mesh・nurbsCurve は専用の function set を呼び出しごとに新しく作る。"""
        box = cmds.polyCube(name=self.name("box"))[0]
        curve = cmds.curve(degree=1, point=[(0, 0, 0), (1, 0, 0)], name=self.name("crv"))
        camera = cmds.camera(name=self.name("cam"))[0]
        for transform, expected in ((box, om2.MFnMesh), (curve, om2.MFnNurbsCurve), (camera, om2.MFnCamera)):
            shape = Node(transform).getShape()
            with self.subTest(shape=shape.getName()):
                first, second = shape.mfn(), shape.mfn()
                self.assertIsInstance(first, expected)
                self.assertIsNot(first, second)
                self.assertEqual(first.fullPathName(), shape.mpath().fullPathName())
        mesh = Node(box).getShape()
        self.assertEqual(mesh.mfn().numVertices, mesh.getNumVertices())
        self.assertEqual(Node(curve).getShape().mfn().numCVs, 2)
        self.assertAlmostEqual(Node(camera).getShape().mfn().focalLength,
                               cmds.getAttr(Node(camera).getShape().getFullName() + ".focalLength"))

    def test_empty_shapes_fall_back_to_dag_node(self):
        """形状データの無い mesh・nurbsCurve は MFnDagNode を返し、DagNode 共通の照会が使える。"""
        parent = self.make("transform", "emptyParent")
        for kind, cls, query in (("mesh", Mesh, "getNumVertices"), ("nurbsCurve", NurbsCurve, "getNumCVs")):
            with self.subTest(kind=kind):
                shape = mlib.createNode(kind, name=self.name(kind + "Empty"), parent=parent)
                self.assertIsInstance(shape, cls)
                fn = shape.mfn()
                self.assertIs(type(fn), om2.MFnDagNode)
                self.assertEqual(fn.fullPathName(), shape.mpath().fullPathName())
                self.assertFalse(shape.isIntermediateObject())
                self.assertEqual([p.getFullName() for p in shape.getParents()], ["|" + parent])
                with self.assertRaises(RuntimeError):
                    getattr(shape, query)()

    def test_empty_mesh_components_raise_runtime_error(self):
        """空の mesh のコンポーネント照会も RuntimeError。"""
        mesh = mlib.createNode("mesh", name=self.name("noData"), parent=self.make("transform", "noDataParent"))
        with self.assertRaises(RuntimeError):
            Vertices(mesh)
        with self.assertRaises(RuntimeError):
            mesh.getPoints()

    def test_empty_mesh_becomes_mesh_after_geometry_arrives(self):
        """形状が入った後の呼出しでは MFnMesh を返す(戻り値をキャッシュしない)。"""
        transform = self.make("transform", "filled")
        mesh = mlib.createNode("mesh", name=self.name("filledShape"), parent=transform)
        self.assertIs(type(mesh.mfn()), om2.MFnDagNode)
        creator = cmds.polyCube(name=self.name("source"))[1]
        cmds.connectAttr(creator + ".output", mesh.getFullName() + ".inMesh")
        cmds.getAttr(mesh.getFullName() + ".outMesh", size=True)
        self.assertIsInstance(mesh.mfn(), om2.MFnMesh)
        self.assertEqual(mesh.getNumVertices(), 8)

    def test_deleted_shape_raises_runtime_error(self):
        """削除後の mfn() は RuntimeError。"""
        mesh = Node(cmds.polyCube(name=self.name("gone"))[0]).getShape()
        cmds.delete(mesh.getParent().getFullName())
        with self.assertRaises(RuntimeError):
            mesh.mfn()


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
