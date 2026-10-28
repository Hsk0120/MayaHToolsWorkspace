"""influence 解除の fast 経路が、通常経路(cmds.skinCluster -removeInfluence)と同じ生ウェイトになることを固定する(2.1.0 担当E)。

- 解除する influence の値が 0 でない頂点だけを再配分する。normalizeWeights=Interactive はロックしていない
  残りを ``1 - ロック合計`` へ比例配分し、None/Post は残りの合計が 0 でなければ値を変えない。
- 残りの合計が 0 になった頂点は、バインド時の joint 位置(子 joint があれば線分)からの距離で配る。
  ロックなしは ``距離 ** -dropoff``(bindMethod=Closest distance のみ)、ロックありは ``1 / 距離``、
  近い順に maxInfluences 個。2.0.0 以前の fast は等分していた。
- 再現できない条件(bindMethod が Closest distance 以外でロックなしの 0 合計の頂点が出る等)は、
  連続解除の後半で起きる場合も含め、どの skinCluster も変更する前に NotImplementedError。
- fast は cmds を呼ばず Undo に記録しない。通常経路は Undo 1 回で戻る。
"""

import unittest
from contextlib import ExitStack
from unittest.mock import patch

import maya.cmds as cmds

import mlib
mlib.reload()
from mlib.nodes import Joint, SkinCluster, SkinClusters
from support.specCase import NamespaceCase

TOLERANCE = 1e-6


class _Rig(object):
    """root→mid→tip の chain と、別階層の other(子 otherEnd を持つ)にバインドした円柱。

    Args:
        case (NamespaceCase): 名前を作るテスト。
        tag (str): 名前の接頭辞。通常経路と fast で同じ形の別リグを作る。
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
        """normalizeWeights・ロック・dropoff を両経路で同じに設定する。"""
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


class RemoveInfluenceFastTest(NamespaceCase):
    """fast と通常経路の生ウェイトの一致。"""

    PREFIX = "mlibSpecSkinRemoveFast_"

    def setUp(self):
        super().setUp()
        self.selection = cmds.ls(selection=True, long=True)

    def tearDown(self):
        if self.selection:
            cmds.select(self.selection, replace=True)
        else:
            cmds.select(clear=True)
        super().tearDown()

    def no_cmds(self):
        stack = ExitStack()
        for name in ("skinCluster", "skinPercent", "setAttr", "undoInfo", "removeMultiInstance"):
            stack.enter_context(patch.object(cmds, name, side_effect=AssertionError(name)))
        return stack

    def assertSameRaw(self, actual, expected):
        self.assertEqual(len(actual), len(expected))
        for (names, rows), (expected_names, expected_rows) in zip(actual, expected):
            self.assertEqual(names, expected_names)
            self.assertEqual(sorted(rows), sorted(expected_rows))
            for vertex in expected_rows:
                indices = set(rows[vertex]) | set(expected_rows[vertex])
                for index in indices:
                    value = rows[vertex].get(index, 0.0)
                    expected_value = expected_rows[vertex].get(index, 0.0)
                    if abs(value - expected_value) > TOLERANCE:
                        self.fail("vertex {} index {}: fast {} != normal {}".format(
                            vertex, index, value, expected_value))

    def run_both(self, action, **rig_options):
        """同じリグを2つ作り、通常経路と fast で action を実行して生ウェイトを返す。"""
        config = rig_options.pop("config", {})
        normal = _Rig(self, "n", **rig_options).configure(**config)
        fast = _Rig(self, "f", **rig_options).configure(**config)
        action(normal, False)
        cmds.flushUndo()
        with self.no_cmds():
            action(fast, True)
        self.assertUndoEmpty()
        return normal.raw(), fast.raw()

    def test_matches_normal(self):
        """単発・連続・一括、transferToParent、normalizeWeights、ロック、dropoff の組合せで一致する。"""

        def single(rig, fast):
            rig.skins[0].removeInfluence(rig.tip, transferToParent=transfer, fast=fast)

        def chained(rig, fast):
            # 2.0.0 以前の不具合の条件: tip を外した後、同じ skin から mid を外す。
            rig.skins[0].removeInfluence(rig.tip, transferToParent=transfer, fast=fast)
            rig.skins[0].removeInfluence(rig.mid, transferToParent=transfer, fast=fast)

        def joint_chain(rig, fast):
            Joint(rig.tip).removeInfluence(transferToParent=transfer, fast=fast)
            Joint(rig.mid).removeInfluence(transferToParent=transfer, fast=fast)

        def bulk(rig, fast):
            SkinClusters(rig.skins).removeInfluences([rig.tip, rig.mid], transferToParent=transfer, fast=fast)

        def root_side(rig, fast):
            # 子を持つ root を外し、mid・tip・other へ配る。
            rig.skins[0].removeInfluence(rig.root, transferToParent=transfer, fast=fast)

        actions = {"single": single, "chained": chained, "joint": joint_chain, "bulk": bulk, "root": root_side}
        for transfer in (False, True):
            for normalize in (0, 1, 2):
                for locked in (False, True):
                    if locked and transfer:
                        # 祖先移送は両経路とも lockInfluenceWeights を拒否する(下の test で確認)。
                        continue
                    for label, action in actions.items():
                        for max_influences in (2, 4):
                            meshes = 2 if label in ("joint", "bulk") else 1
                            options = dict(meshes=meshes, max_influences=max_influences,
                                           config=dict(normalize=normalize, locked=locked,
                                                       dropoff=2.5 if max_influences == 4 else None))
                            with self.subTest(action=label, transferToParent=transfer, normalizeWeights=normalize,
                                              lockInfluenceWeights=locked, maxInfluences=max_influences):
                                normal, fast = self.run_both(action, **options)
                                self.assertSameRaw(fast, normal)

    def test_zero_total_uses_distance(self):
        """不具合の条件: 合計 0 になった頂点が等分ではなく通常経路と同じ距離の配分になる。"""

        def chained(rig, fast):
            rig.skins[0].removeInfluence(rig.tip, transferToParent=False, fast=fast)
            rig.skins[0].removeInfluence(rig.mid, transferToParent=False, fast=fast)

        normal, fast = self.run_both(chained)
        self.assertSameRaw(fast, normal)
        top = max(normal[0][1])
        self.assertNotAlmostEqual(normal[0][1][top].get(0, 0.0), 0.5, places=3)

    def test_locked_transfer_rejected_on_both(self):
        """祖先移送でロックがあれば、両経路とも RuntimeError で何も変えない。"""
        for fast in (False, True):
            with self.subTest(fast=fast):
                rig = _Rig(self, "f" if fast else "n").configure(locked=True)
                before = rig.raw()
                with self.assertRaises(RuntimeError):
                    rig.skins[0].removeInfluence(rig.tip, transferToParent=True, fast=fast)
                self.assertEqual(rig.raw(), before)

    def test_not_implemented_before_change(self):
        """Closest in hierarchy で 0 合計の頂点が出る解除は、fast だけ変更前に NotImplementedError。"""
        cases = {
            "single": lambda rig: rig.skins[-1].removeInfluence(rig.mid, transferToParent=False, fast=True),
            # 2つ目の skin だけが未対応でも、1つ目を変更しない。
            "joint": lambda rig: Joint(rig.mid).removeInfluence(transferToParent=False, fast=True),
            # 1本目(tip)は再現できるが2本目(mid)で 0 合計が出る。1本目も変更しない。
            "bulk": lambda rig: SkinClusters(rig.skins).removeInfluences(
                [rig.tip, rig.mid], transferToParent=False, fast=True),
        }
        for label, action in cases.items():
            with self.subTest(case=label):
                rig = _Rig(self, "f" + label, meshes=2, bind_method=1)
                if label != "bulk":
                    skin = rig.skins[-1]
                    cmds.skinPercent(skin.getFullName(), skin.mesh + ".vtx[60:99]", transformValue=[(rig.mid, 1.0)])
                before = rig.raw()
                with self.assertRaises(NotImplementedError):
                    action(rig)
                self.assertEqual(rig.raw(), before)
        # 通常経路は同じ条件でも処理できる。
        rig = _Rig(self, "n", bind_method=1)
        SkinClusters(rig.skins).removeInfluences([rig.tip, rig.mid], transferToParent=False)
        self.assertEqual(len(rig.skins[0].getInfluences()), 2)

    def test_normal_undo_once(self):
        """通常経路は Undo 1 回でウェイトと登録が戻る。"""
        rig = _Rig(self, "n")
        before = rig.raw()
        cmds.flushUndo()
        rig.skins[0].removeInfluence(rig.tip, transferToParent=False)
        self.assertEqual(cmds.undoInfo(query=True, undoName=True), "mlib.nodes.skinCluster.removeInfluence")
        cmds.undo()
        self.assertEqual(rig.raw(), before)


if __name__ == "__main__":
    unittest.main()
