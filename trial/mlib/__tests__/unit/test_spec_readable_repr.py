"""コンポーネント・Selectionの読みやすいrepr、Selection.getItems・getChannelBoxPlugsの仕様テスト。

reprはデバッグ用の表示で、maya.cmdsへ渡す__str__(完全パス名)は変えないことも確かめる。
"""

import sys
import unittest

import maya.cmds as cmds

import mlib
mlib.reload()
from mlib.common import Selection
from mlib.common import selection as selection_module
from mlib.components import CV
from mlib.components import CVs
from mlib.components import Edge
from mlib.components import Edges
from mlib.components import Face
from mlib.components import UV
from mlib.components import Vertex
from mlib.components import Vertices
from mlib.nodes import NurbsCurve
from support.specCase import NamespaceCase


class _Case(NamespaceCase):
    PREFIX = "mlibSpecRepr_"

    def setUp(self):
        super().setUp()
        transform = cmds.polyCube(name=self.name("box"), constructionHistory=False)[0]
        self.mesh = mlib.getNode(cmds.listRelatives(transform, shapes=True, fullPath=True)[0])
        self.mesh_name = self.mesh.getName()


class ComponentReprTest(_Case):

    def test_single_components(self):
        name = self.mesh_name
        for component, text in ((Vertex(self.mesh, 5), f"Vertex('{name}.vtx[5]')"),
                                (Edge(self.mesh, 2), f"Edge('{name}.e[2]')"),
                                (Face(self.mesh, 1), f"Face('{name}.f[1]')"),
                                (UV(self.mesh, 3), f"UV('{name}.map[3]')")):
            with self.subTest(text=text):
                self.assertEqual(repr(component), text)
                self.assertEqual(str(component), component.getFullName())
                self.assertTrue(cmds.objExists(str(component)))

    def test_collections(self):
        name = self.mesh_name
        self.assertEqual(repr(Vertices(self.mesh)), f"Vertices('{name}.vtx[0:7]')")
        self.assertEqual(repr(Vertices(self.mesh, [0, 1, 2, 5])), f"Vertices('{name}.vtx[0:2]', '{name}.vtx[5]')")
        self.assertEqual(repr(Vertices(self.mesh, [])), f"Vertices('{name}', count=0)")
        many = Vertices(self.mesh, [0, 2, 4, 6, 7, 1])
        self.assertEqual(repr(many), f"Vertices('{name}.vtx[0]', '{name}.vtx[2]', '{name}.vtx[4]', "
                                     f"'{name}.vtx[6:7]', ..., count=6)")

    def test_curve_cvs(self):
        curve = NurbsCurve.create([(0, 0, 0), (1, 0, 0), (1, 0, 1), (0, 0, 1)], degree=3, closed=True,
                                  name=self.name("crv"))
        name = curve.getName()
        self.assertEqual(repr(CV(curve, 2)), f"CV('{name}.cv[2]')")
        # 周期カーブの末尾の重複CVは先頭の独立CVと同じ名前になるため、表示では重複を除く。
        self.assertEqual(repr(CVs(curve)), f"CVs('{name}.cv[0:3]')")
        self.assertEqual(repr(CV(curve, 5)), f"CV('{name}.cv[1]')")

    def test_invalid(self):
        vertex = Vertex(self.mesh, 5)
        vertices = Vertices(self.mesh, [0, 1])
        selection = Selection([vertex, self.mesh])
        cmds.delete(self.mesh.getFullName())
        self.assertEqual(repr(vertex), "<Vertex invalid>")
        self.assertEqual(repr(vertices), "<Vertices invalid>")
        self.assertEqual(repr(selection), "Selection([<Vertex invalid>, <Mesh invalid>])")


class SelectionTest(_Case):

    def test_repr_and_get_items(self):
        transform = self.mesh.getParent()
        plug = transform.getPlug("translateX")
        selection = Selection([transform, Vertex(self.mesh, 1), plug])
        self.assertEqual(repr(selection),
                         f"Selection([{transform!r}, Vertex('{self.mesh_name}.vtx[1]'), {plug!r}])")
        items = selection.getItems()
        self.assertEqual(items, selection.items)
        self.assertEqual(items, [transform, Vertex(self.mesh, 1), plug])
        items.append("extra")
        self.assertEqual(len(selection), 3)
        self.assertEqual(repr(Selection()), "Selection([])")
        many = Selection([Vertices(self.mesh), Edges(self.mesh)])
        text = repr(many)
        self.assertTrue(text.startswith("Selection([Vertex("))
        self.assertTrue(text.endswith(", ...], count=20)"))
        self.assertEqual(text.count("Vertex("), 8)
        self.assertEqual(text.count("Edge("), 2)

    @unittest.skipUnless(cmds.about(batch=True), "Batch-only empty result")
    def test_channel_box_plugs_are_empty_in_batch(self):
        self.assertEqual(Selection.getChannelBoxPlugs(), [])

    @unittest.skipIf(cmds.about(batch=True), "Requires the Maya GUI channel box")
    def test_channel_box_plugs_match_cmds_in_gui(self):
        """GUIでは、現在のChannel Boxの照会結果から組み立てたPlugと一致する。"""
        name = "mainChannelBox"
        expected = []
        for attributes_flag, objects_flag in selection_module._CHANNEL_BOX_SECTIONS:
            attributes = cmds.channelBox(name, query=True, **{attributes_flag: True}) or []
            for owner in cmds.channelBox(name, query=True, **{objects_flag: True}) or [] if attributes else []:
                for attribute in attributes:
                    if cmds.objExists(owner + "." + attribute):
                        expected.append(mlib.getPlug(owner + "." + attribute).getFullName())
        actual = [plug.getFullName() for plug in Selection.getChannelBoxPlugs()]
        self.assertEqual(actual, list(dict.fromkeys(expected)))

    def test_channel_box_plugs_from_simulated_channel_box(self):
        """Channel Boxの各区分の選択を、区分の順・選択順のPlugへ変換し、存在しない組合せと重複を除く。"""
        transform = self.mesh.getParent().getFullName()
        mesh = self.mesh.getFullName()
        other = self.make("transform", "other")
        answers = {
            "selectedMainAttributes": ["ty", "tx"],
            "mainObjectList": [transform, other],
            "selectedShapeAttributes": ["castsShadows", "noSuchAttr"],
            "shapeObjectList": [mesh],
            "selectedHistoryAttributes": None,
            "historyObjectList": [transform],
            "selectedOutputAttributes": ["tx"],
            "outputObjectList": [transform],
        }
        original_about = cmds.about
        original_channel_box = cmds.channelBox
        original_mel = selection_module.mel

        class _Mel(object):
            @staticmethod
            def eval(command):
                return "mainChannelBox"

        def about(*args, **kwargs):
            if kwargs.get("batch") or kwargs.get("b"):
                return False
            return original_about(*args, **kwargs)

        def channel_box(name, **kwargs):
            if kwargs.get("exists"):
                return True
            for flag, value in answers.items():
                if kwargs.get(flag):
                    return value
            raise AssertionError(kwargs)

        cmds.about = about
        cmds.channelBox = channel_box
        selection_module.mel = _Mel
        try:
            plugs = Selection.getChannelBoxPlugs()
        finally:
            cmds.about = original_about
            cmds.channelBox = original_channel_box
            selection_module.mel = original_mel
        self.assertEqual([plug.getFullName() for plug in plugs],
                         [mlib.getPlug(name).getFullName() for name in (
                             transform + ".ty", transform + ".tx", other + ".ty", other + ".tx",
                             mesh + ".castsShadows")])


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
