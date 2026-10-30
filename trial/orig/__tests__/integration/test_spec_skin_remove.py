"""influence 解除(cmds.skinCluster -removeInfluence)の通常経路の契約を固定する。

- 祖先移送でロックがあれば RuntimeError で何も変えない。
- Closest in hierarchy の連続解除も処理でき、Undo 1 回でウェイトと登録が戻る。
- 3.0.0 で fast 引数は外した(``docs/mlib-api-design.md`` の「fast を持たない書き込み」)。
"""

import unittest

import maya.cmds as cmds

import mlib
mlib.reload()
from mlib.nodes import SkinCluster
from support.specCase import NamespaceCase


class _Rig(object):
    """root→mid→tip の chain と、別階層の other(子 otherEnd を持つ)にバインドした円柱。

    Args:
        case (NamespaceCase): 名前を作るテスト。
        tag (str): 名前の接頭辞。
        meshes (int): 同じ joint にバインドする円柱の数。
        bind_method (int): skinCluster.bindMethod。
        max_influences (int): skinCluster の maximumInfluences。
    """

    def __init__(self, case, tag, meshes=1, bind_method=0, max_influences=2):
        name = case.name
        cmds.select(clear=True)
        self.root = cmds.joint(name=name(tag + "root"), position=(0, 0, 0))
        self.mid = cmds.joint(name=name(tag + "mid"), position=(0.2, 1, 0))
        self.tip = cmds.joint(name=name(tag + "tip"), position=(0, 2, 0.1))
        cmds.select(clear=True)
        self.other = cmds.joint(name=name(tag + "other"), position=(1.5, 0.3, 0))
        self.other_end = cmds.joint(name=name(tag + "otherEnd"), position=(2.5, 1.5, 0))
        cmds.select(clear=True)
        self.joints = [self.root, self.mid, self.tip, self.other]
        self.skins = []
        for _ in range(meshes):
            mesh = cmds.polyCylinder(name=name(tag + "mesh#"), height=2, subdivisionsHeight=4)[0]
            cmds.move(0, 1, 0, mesh)
            skin = cmds.skinCluster(self.joints, mesh, toSelectedBones=True,
                                    maximumInfluences=max_influences)[0]
            cmds.setAttr(skin + ".bindMethod", bind_method)
            self.skins.append(SkinCluster(skin))
        cmds.select(clear=True)

    def configure(self, normalize=1, locked=False, dropoff=None):
        """normalizeWeights・ロック・dropoff を設定する。"""
        for skin in self.skins:
            cmds.setAttr(skin.getFullName() + ".normalizeWeights", normalize)
            if dropoff is not None:
                cmds.setAttr(skin.getFullName() + ".dropoff[0]", dropoff)
        cmds.setAttr(self.other + ".liw", locked)
        return self

    def raw(self):
        """全 skinCluster の weightList を {頂点: {論理番号: 値}} で返す(存在しない要素は 0 扱い)。"""
        result = []
        for skin in self.skins:
            name = skin.getFullName()
            rows = {}
            for vertex in cmds.getAttr(name + ".weightList", multiIndices=True) or []:
                prefix = "{}.weightList[{}].weights".format(name, vertex)
                indices = cmds.getAttr(prefix, multiIndices=True) or []
                rows[vertex] = {index: cmds.getAttr("{}[{}]".format(prefix, index)) for index in indices}
            influences = [node.getName().rsplit(":", 1)[-1][1:] for node in skin.getInfluences()]
            result.append((influences, rows))
        return result


class RemoveInfluenceTest(NamespaceCase):
    """通常経路の influence 解除。"""

    PREFIX = "mlibSpecSkinRemove_"

    def setUp(self):
        super().setUp()
        self.selection = cmds.ls(selection=True, long=True)

    def tearDown(self):
        if self.selection:
            cmds.select(self.selection, replace=True)
        else:
            cmds.select(clear=True)
        super().tearDown()

    def test_locked_transfer_rejected(self):
        """祖先移送でロックがあれば、RuntimeError で何も変えない。"""
        rig = _Rig(self, "n").configure(locked=True)
        before = rig.raw()
        with self.assertRaises(RuntimeError):
            rig.skins[0].removeInfluence(rig.tip, transferToParent=True)
        self.assertEqual(rig.raw(), before)

    def test_closest_in_hierarchy_consecutive(self):
        """Closest in hierarchy の連続解除も処理できる。"""
        rig = _Rig(self, "n", bind_method=1)
        for skin in rig.skins:
            for joint in (rig.tip, rig.mid):
                skin.removeInfluence(joint, transferToParent=False)
        self.assertEqual(len(rig.skins[0].getInfluences()), 2)

    def test_normal_undo_once(self):
        """通常経路は Undo 1 回でウェイトと登録が戻る。"""
        rig = _Rig(self, "n")
        before = rig.raw()
        cmds.flushUndo()
        rig.skins[0].removeInfluence(rig.tip, transferToParent=False)
        self.assertRegex(cmds.undoInfo(query=True, undoName=True), r"^mlib removeInfluence( |$)")
        cmds.undo()
        self.assertEqual(rig.raw(), before)


if __name__ == "__main__":
    unittest.main()
