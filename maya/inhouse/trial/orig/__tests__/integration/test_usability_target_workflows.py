"""BlendShapeのweight参照と既存項目編集を隔離シーンで検証する。"""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

import mlib
import maya.cmds as cmds


class TargetWorkflowTest(unittest.TestCase):
    """返却Plug再利用・全件検証・一時shapeのUndo境界を確認する。"""

    def setUp(self):
        """独立したベースとliveターゲットを用意する。"""
        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)
        self.base = mlib.getNode(cmds.polyCube(ch=False)[0])
        self.target = mlib.getNode(cmds.duplicate(self.base.getFullName())[0])
        cmds.move(0, 2, 0, self.target.getFullName() + ".vtx[0]", relative=True)
        self.bs = mlib.getNode(cmds.blendShape(self.base.getFullName())[0])
        self.weight = self.bs.addTarget(self.target)
        self.weight.setAlias("smile")
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "delta.json"

    def tearDown(self):
        """一時ファイルとテストシーンを破棄する。"""
        self.directory.cleanup()
        cmds.undoInfo(state=True)
        cmds.file(new=True, force=True)

    def point(self, index=0):
        """オブジェクト空間cmのベース頂点を取得する。"""
        return tuple(self.base.getShape().getPoints()[index])[:3]

    def test_returned_weight_plug_is_reusable_after_alias_rename(self):
        """返却参照はalias変更後もgetter・setter・編集へ渡せる。"""
        self.weight.setAlias("renamedSmile")
        self.assertEqual(self.bs.getTargetPlug(self.weight), self.weight)
        self.assertEqual(self.bs.getTargetDeltas(self.weight), self.bs.getTargetDeltas("renamedSmile"))
        self.assertEqual(self.bs.getTargetVertices(self.weight).indices, (0,))
        self.assertEqual(self.bs.getInBetweenWeights(self.weight), [])
        self.bs.setTargetWeights(self.weight, {0: 0.25})
        self.assertAlmostEqual(self.bs.getTargetWeights(self.weight)[0], 0.25)
        self.bs.resetTargetVertices(self.weight, self.base.getShape().getVertex(0))
        self.assertEqual(self.bs.getTargetVertices(self.weight).indices, ())
        cmds.undo()
        self.assertEqual(self.bs.getTargetVertices(self.weight).indices, (0,))
        self.bs.reduceTargetDeltas(self.weight, 3)
        self.assertEqual(self.bs.getTargetVertices(self.weight).indices, ())

    def test_target_plug_must_be_own_existing_weight_element(self):
        """別ノード・別アトリビュート・配列親・空要素を更新前に拒否する。"""
        other = mlib.getNode(cmds.blendShape(self.target.getFullName(), cmds.polyCube(ch=False)[0])[0])
        extra = self.bs.addAttr("extra", multi=True)
        self.bs.getPlug("weight")[8].set(0)
        candidates = (other.getTargetPlug(0), self.target.getPlug("tx"),
                      self.bs.getPlug("weight"), extra[0], self.bs.getPlug("weight")[8])
        for plug in candidates:
            with self.subTest(plug=str(plug)):
                with self.assertRaises(ValueError):
                    self.bs.setTargetDeltas(plug, {0: (0, 1, 0)}, disconnect=True)
        self.assertIsNotNone(self.bs.getPlug('inputTarget[0].inputTargetGroup[0].inputTargetItem[6000].inputGeomTarget').getSource(skipConversionNodes=False))
        extra.delete()
        with self.assertRaises(RuntimeError):
            self.bs.getTargetPlug(extra)

    def test_weight_plug_inbetween_replace_duplicate_and_remove(self):
        """全target解決APIが同じ参照を使い、作成の返却も再利用できる。"""
        half = mlib.getNode(cmds.duplicate(self.target.getFullName())[0])
        self.bs.addInBetween(self.weight, half, 0.5)
        self.assertEqual(self.bs.getInBetweenWeights(self.weight), [0.5])
        replacement = mlib.getNode(cmds.duplicate(half.getFullName())[0])
        self.bs.replaceTarget(self.weight, replacement, fullWeight=0.5)
        self.bs.removeInBetween(self.weight, 0.5)
        self.assertEqual(self.bs.getInBetweenWeights(self.weight), [])
        copied = self.bs.duplicateTarget(self.weight, alias="copy")
        self.assertEqual(self.bs.getTargetVertices(copied).indices, (0,))
        self.bs.flipTarget(copied)
        self.bs.mirrorTarget(copied)
        self.bs.removeTarget(copied)
        self.assertEqual(self.bs.getTargetIndices(), [0])

    def test_target_edit_false_ignores_invalid_target_reference(self):
        """編集終了は以前どおりtargetとfullWeightを使用しない。"""
        with mock.patch("mlib.nodes.blendShape.cmds.sculptTarget") as sculpt:
            self.assertIs(self.bs.targetEdit(self.target.getPlug("tx"), state=False,
                                             fullWeight=object()), self.bs)
            self.assertEqual(sculpt.call_args[1]["target"], -1)




    def test_add_delta_target_uses_input_mesh_and_has_single_undo(self):
        """変形中のbaseでも入力基準を使い、一時shapeを残さずUndo/Redoできる。"""
        self.weight.set(1)
        before = self.point()
        shapes = set(cmds.ls(type="mesh", long=True))
        transforms = set(cmds.ls(type="transform", long=True))
        copied = self.bs.addTargetDeltas({0: (0, 3, 0)}, weightIndex=4, alias="deltaOnly")
        self.assertEqual(self.bs.getTargetIndices(), [0, 4])
        self.assertEqual(copied.get(), 0)
        self.assertEqual(self.bs.getTargetDeltas(copied)[0], mlib.maths.Vector(0, 3, 0))
        self.assertEqual(self.point(), before)
        self.assertEqual(set(cmds.ls(type="mesh", long=True)), shapes)
        self.assertEqual(set(cmds.ls(type="transform", long=True)), transforms)
        cmds.undo()
        self.assertEqual(self.bs.getTargetIndices(), [0])
        cmds.redo()
        copied = self.bs.getTargetPlug(4)
        copied.set(1)
        self.assertAlmostEqual(self.point()[1], before[1] + 3)

    def test_add_delta_target_preserves_world_origin_and_base_transform(self):
        """非identityのbaseとlocal/world originでもobject-spaceデルタを保持する。"""
        self.base.setTranslate((10, 0, 0))
        self.base.setRotate((10, 20, 30), unit="deg")
        self.base.setScale((2, 1.5, 0.75))
        before = self.point()
        for origin in (0, 1):
            with self.subTest(origin=origin):
                self.bs.getPlug("origin").set(origin)
                weight = self.bs.addTargetDeltas({1: (2, 0, 0)})
                weight.set(1)
                point = self.point(1)
                self.assertEqual(self.bs.getTargetDeltas(weight)[1], mlib.maths.Vector(2, 0, 0))
                self.assertAlmostEqual(self.point()[0], before[0])
                self.assertAlmostEqual(point[0], 2.5)
                weight.set(0)


    def test_cleanup_failure_keeps_primary_error_and_rollback_removes_temporary(self):
        """登録と一時shape削除が両方失敗しても元原因を保ち、Undoで一時ノードを戻す。"""
        before = set(cmds.ls(long=True))
        native_delete = cmds.delete

        def refuse_temporary_parent(target, *args, **kwargs):
            """一時メッシュの親削除だけ故障注入し、Undoガードの削除は許可する。"""
            if isinstance(target, str) and target not in before and cmds.nodeType(target) == "transform":
                raise RuntimeError("cleanup injected")
            return native_delete(target, *args, **kwargs)

        with mock.patch.object(type(self.bs), "setTargetDeltas", side_effect=ValueError("primary injected")), \
                mock.patch("mlib.nodes.blendShape.cmds.delete", side_effect=refuse_temporary_parent), \
                mock.patch("mlib.logger.warning") as warning:
            with self.assertRaisesRegex(ValueError, "primary injected"):
                self.bs.addTargetDeltas({0: (0, 1, 0)}, alias="failed")
            warning.assert_called_once()
        self.assertEqual(self.bs.getTargetIndices(), [0])
        self.assertEqual(set(cmds.ls(long=True)), before)

    def test_add_delta_preflight_and_failure_cleanup(self):
        """不正入力は作成前、登録途中の例外は一時shapeとtargetを巻き戻す。"""
        before = set(cmds.ls(long=True))
        for flags in ({"alias": "smile"}, {"weightIndex": 0}, {"alias": "bad.alias"}):
            with self.assertRaises(ValueError):
                self.bs.addTargetDeltas({0: (0, 1, 0)}, **flags)
            self.assertEqual(set(cmds.ls(long=True)), before)
        with self.assertRaises(ValueError):
            self.bs.addTargetDeltas({0: (0, 1, 0), 8: (0, 1, 0)})
        with mock.patch.object(type(self.bs), "setTargetDeltas", side_effect=RuntimeError("injected")):
            with self.assertRaisesRegex(RuntimeError, "injected"):
                self.bs.addTargetDeltas({0: (0, 1, 0)}, alias="failed")
        self.assertEqual(self.bs.getTargetIndices(), [0])
        self.assertEqual(set(cmds.ls(long=True)), before)
        cmds.undoInfo(state=False)
        with self.assertRaises(RuntimeError):
            self.bs.addTargetDeltas({0: (0, 1, 0)}, alias="undoDisabled")
        self.assertEqual(set(cmds.ls(long=True)), before)


if __name__ == "__main__":
    unittest.main()
