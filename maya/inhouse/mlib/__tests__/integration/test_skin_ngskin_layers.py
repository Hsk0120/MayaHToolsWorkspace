"""ngSkinTools2 のレイヤーがある skinCluster の influence 解除を確かめる。

実物の ngSkinTools2 を読み込む。同梱のプラグインが無い Maya の版では飛ばす。
"""

import os
import sys
import unittest

import maya.cmds as cmds
import maya.mel as mel

import mlib
mlib.reload()
from mlib.nodes import Joints, SkinCluster
from support.specCase import NamespaceCase

CONTENTS = r"C:\ProgramData\Autodesk\ApplicationPlugins\ngskintools2\Contents"
VERSION = cmds.about(version=True).split()[0][:4]
PLUGIN = os.path.join(CONTENTS, "plug-ins", VERSION, "ngSkinTools2.mll")


@unittest.skipUnless(os.path.exists(PLUGIN), "ngSkinTools2 is not available for this Maya version")
class NgSkinLayersTest(NamespaceCase):
    """root→mid→tip と other にバインドし、2 枚のレイヤーで確かめる。"""

    PREFIX = "mlibSpecNgSkin_"
    ENABLE_UNDO = True

    @classmethod
    def setUpClass(cls):
        scripts = os.path.join(CONTENTS, "scripts")
        if scripts not in sys.path:
            sys.path.insert(0, scripts)
        cmds.loadPlugin(PLUGIN, quiet=True)

    def setUp(self):
        super().setUp()
        from ngSkinTools2 import api

        self.api = api
        cmds.select(clear=True)
        self.root = mlib.getNode(cmds.joint(name=self.name("root"), position=(0, 0, 0)))
        self.mid = mlib.getNode(cmds.joint(name=self.name("mid"), position=(1, 0, 0)))
        self.tip = mlib.getNode(cmds.joint(name=self.name("tip"), position=(2, 0, 0)))
        cmds.select(clear=True)
        self.other = mlib.getNode(cmds.joint(name=self.name("other"), position=(0, 2, 0)))
        cmds.select(clear=True)
        self.joints = (self.root, self.mid, self.tip, self.other)
        mesh = cmds.polyPlane(name=self.name("mesh"), constructionHistory=False, subdivisionsX=1, subdivisionsY=1)[0]
        name = cmds.skinCluster([joint.getFullName() for joint in self.joints], mesh, toSelectedBones=True)[0]
        cmds.select(clear=True)
        self.skin = SkinCluster(name)
        self.count = 4
        self.layers = api.init_layers(name)
        self.base = self.layers.add("base")
        for index, value in enumerate((.5, .2, .2, .1)):
            self.base.set_weights(index, [value] * self.count)
        self.top = self.layers.add("top")
        self.top.set_weights(2, [.25] * self.count)
        self.top.set_weights(1, [.25] * self.count)

    def tearDown(self):
        self.layers.clear()
        super().tearDown()

    def assertSkin(self, expected):
        """{joint: 値} が全頂点の skinCluster のウェイトであることを確かめる。"""
        joints = list(expected)
        values = list(self.skin.getWeights([joint.getFullName() for joint in joints]))
        for position, value in enumerate(values):
            self.assertAlmostEqual(value, expected[joints[position % len(joints)]], places=5)

    def assertLayer(self, layer, index, value):
        """レイヤーの列が全頂点 value であることを確かめる。"""
        weights = layer.get_weights(index)
        self.assertEqual(len(weights), self.count)
        for actual in weights:
            self.assertAlmostEqual(actual, value, places=5)

    def _fresh_layers(self):
        """layers.list() から base と top を取り直す。"""
        return {layer.name: layer for layer in self.layers.list()}

    def test_starting_composite(self):
        self.assertSkin({self.root: .25, self.mid: .35, self.tip: .35, self.other: .05})

    def test_remove_moves_weight_in_every_layer(self):
        """レイヤーごとに移送し、合成結果は親子の和になる。Undo 1 回で戻る。"""
        cmds.flushUndo()
        Joints([self.tip]).removeInfluence()
        self.assertFalse(self.skin.hasInfluence(self.tip.getFullName()))
        layers = self._fresh_layers()
        self.assertLayer(layers["base"], 1, .4)
        self.assertLayer(layers["top"], 1, .5)
        self.assertLayer(layers["base"], 0, .5)
        self.assertLayer(layers["base"], 3, .1)
        self.assertNotIn(2, layers["base"].get_used_influences())
        self.assertSkin({self.root: .25, self.mid: .7, self.other: .05})
        cmds.undo()
        self.assertTrue(self.skin.hasInfluence(self.tip.getFullName()))
        layers = self._fresh_layers()
        self.assertLayer(layers["base"], 2, .2)
        self.assertLayer(layers["top"], 2, .25)
        self.assertSkin({self.root: .25, self.mid: .35, self.tip: .35, self.other: .05})

    def test_chain_collapses_to_remaining_ancestor(self):
        """親子を同時に外すと残る祖先へ集まる。"""
        Joints([self.tip, self.mid]).removeInfluence()
        layers = self._fresh_layers()
        self.assertLayer(layers["base"], 0, .9)
        self.assertLayer(layers["top"], 0, .5)
        self.assertSkin({self.root: .95, self.other: .05})

    def test_delete_and_fast_match(self):
        """delete も fast も同じ結果で、fast は Undo を積まない。"""
        self.tip.delete()
        self.assertSkin({self.root: .25, self.mid: .7, self.other: .05})
        cmds.undo()
        cmds.flushUndo()
        self.tip.delete(fast=True)
        self.assertTrue(cmds.undoInfo(query=True, undoQueueEmpty=True))
        self.assertTrue(cmds.undoInfo(query=True, state=True))
        layers = self._fresh_layers()
        self.assertLayer(layers["base"], 1, .4)
        self.assertSkin({self.root: .25, self.mid: .7, self.other: .05})

    def test_no_ancestor_redistributes_within_layer(self):
        """移送先が無ければ、レイヤーの中で残りへ比率を保って配る。"""
        self.other.delete(transferToParent=False)
        layers = self._fresh_layers()
        self.assertLayer(layers["base"], 0, .5 / .9)
        self.assertLayer(layers["base"], 1, .2 / .9)
        self.assertLayer(layers["base"], 2, .2 / .9)
        self.assertNotIn(3, layers["base"].get_used_influences())

    def test_locked_weight_is_restored(self):
        """ウェイトのロックがあっても移送し、元へ戻す。"""
        cmds.setAttr(self.other.getFullName() + ".liw", True)
        self.tip.delete()
        self.assertTrue(cmds.getAttr(self.other.getFullName() + ".liw"))
        self.assertSkin({self.root: .25, self.mid: .7, self.other: .05})

    def test_layers_keep_working_after_removal(self):
        """解除の後もレイヤーを編集できる。"""
        self.tip.delete()
        layers = self._fresh_layers()
        layers["top"].set_weights(0, [.5] * self.count)
        self.assertEqual(mel.eval("pluginInfo -q -loaded ngSkinTools2"), True)
        self.assertEqual(len(self.layers.list()), 2)
        self.assertLayer(self._fresh_layers()["top"], 0, .5)


if __name__ == "__main__":
    unittest.main()
