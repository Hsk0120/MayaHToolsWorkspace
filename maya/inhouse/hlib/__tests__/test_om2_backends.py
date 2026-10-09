"""om2取得・fast更新のコマンド非依存性と従来値・Undoの一致を検証する。"""
from maya.api.OpenMaya import MSpace
from contextlib import ExitStack
import sys
import unittest
from unittest.mock import patch

import maya.cmds as cmds
import maya.api.OpenMaya as om2
import hlib

hlib.reload()


class Om2BackendsTest(unittest.TestCase):
    """保持参照からの取得と、明示したfast更新の境界を確認する。"""

    def setUp(self):
        """テスト専用の新規シーンを作る。"""
        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)
        cmds.currentUnit(linear="cm", angle="deg", time="film")

    def forbidden(self, *names):
        """指定したコマンドが呼ばれると失敗するコンテキストを返す。"""
        stack = ExitStack()
        for name in names:
            stack.enter_context(patch.object(cmds, name, side_effect=AssertionError(name)))
        return stack

    def assert_points(self, actual, expected):
        """座標列をMeshのfloat精度の範囲で比較する。"""
        self.assertEqual(len(actual), len(expected))
        for first, second in zip(actual, expected):
            for a, b in zip(first, second):
                self.assertAlmostEqual(a, b, delta=1e-5)

    def test_geometry_reads_units_instances_and_history(self):
        """通常読取りは履歴・インスタンスを維持しxformを呼ばない。"""
        mesh = cmds.polyCube()[0]
        curve = cmds.curve(degree=1, point=[(0, 0, 0), (1, 2, 3), (4, 5, 6)])
        rational = cmds.curve(degree=2, pointWeight=[(0, 0, 0, 1), (1, 2, 3, .5), (4, 5, 6, 2)])
        for transform in (mesh, curve, rational):
            instance = cmds.instance(transform)[0]
            cmds.setAttr(instance + '.translate', 4, 5, 6)
            cmds.setAttr(instance + '.scale', -2, 3, 4)
            shape = hlib.getNode(cmds.listRelatives(instance, shapes=True, fullPath=True)[0])
            items = shape.getVertices([2, 0]) if shape.getType() == 'mesh' else shape.cvs([2, 0])
            for unit in ('cm', 'm'):
                cmds.currentUnit(linear=unit)
                for ws in (False, True):
                    space = om2.MSpace.kWorld if ws else om2.MSpace.kObject
                    fn = shape.meshFn() if shape.getType() == 'mesh' else shape.curveFn()
                    raw = fn.getPoints(space) if shape.getType() == 'mesh' else fn.cvPositions(space)
                    expected = [(raw[i].x, raw[i].y, raw[i].z) for i in items.indices]
                    with self.forbidden('xform', 'getAttr'):
                        self.assert_points(items.getPosition(ws), expected)
                        self.assert_points([items[0].getPosition(ws)], expected[:1])
                cmds.currentUnit(linear='cm')
        deleted = items
        cmds.delete(curve, instance)
        with self.assertRaises(RuntimeError):
            deleted.getPosition()

    def test_periodic_cv_uses_api_addressing(self):
        """周期CVの重複領域はAPIの番号解釈に従う。"""
        transform = cmds.circle(ch=False)[0]
        shape = hlib.getNode(cmds.listRelatives(transform, shapes=True, fullPath=True)[0])
        items = shape.cvs()
        expected = [(p.x, p.y, p.z) for p in shape.curveFn().cvPositions()]
        self.assert_points(items.getPosition(), expected)

    def test_component_range_rejected_before_expansion(self):
        """単数解決で広い範囲のラッパーを生成しない。"""
        from hlib.components import Component
        mesh = cmds.polyPlane(subdivisionsX=20, subdivisionsY=20)[0]
        with patch.object(Component, '_from_api', side_effect=AssertionError('expanded')):
            with self.assertRaises(ValueError):
                Component._resolve_input(mesh + '.vtx[*]')

    def test_fast_new_array_matrix_and_normal_undo(self):
        """fastの新規配列要素はgetAttrやsetAttrを使わず値を書き込む。"""
        node = hlib.createNode('multMatrix')
        matrix = hlib.maths.Matrix(translate=(1, 2, 3))
        before = cmds.undoInfo(q=True, undoName=True)
        with self.forbidden('getAttr', 'setAttr', 'undoInfo'):
            node.setInput(37, matrix, fast=True)
        self.assertEqual(cmds.undoInfo(q=True, undoName=True), before)
        self.assertEqual(list(node.getInput(37)), list(matrix))
        node.setInput(37, hlib.maths.Matrix())
        cmds.undo()
        self.assertEqual(list(node.getInput(37)), list(matrix))
        cmds.redo()
        self.assertEqual(list(node.getInput(37)), list(hlib.maths.Matrix()))
        node.getInputPlug(37).setFlags(locked=True)
        with self.assertRaises(RuntimeError):
            node.setInput(37, matrix, fast=True)

    def test_typed_arrays_keep_empty_and_singleton_shapes(self):
        """型付き配列のnull・空・一要素・複数要素の返却形式を維持する。"""
        node = hlib.createNode('network')
        arrays = [('doubleArray', [1., 2.]), ('Int32Array', [1, 2]),
                  ('stringArray', ['a', 'b']), ('vectorArray', [(1, 2, 3), (4, 5, 6)]),
                  ('pointArray', [(1, 2, 3, 1), (4, 5, 6, 2)])]
        for kind, rows in arrays:
            plug = node.addAttr(kind, dataType=kind)
            states = [None, [], rows[:1], rows]
            for values in states:
                if values is not None:
                    args = (values,) if kind in ('doubleArray', 'Int32Array') else (len(values), *values)
                    cmds.setAttr(plug.getFullName(), *args, type=kind)
                expected = values
                with self.forbidden('getAttr'):
                    self.assertEqual(plug.get(), expected, (kind, values))

    def test_json_capture_preserves_units_and_value_shapes(self):
        """JSONの取得はAPIを使い、保存値のUI単位・複合値の形を保つ。"""
        from hlib.json.references import NodeRef
        from hlib.json.snapshots import _attribute
        node = hlib.createNode('transform')
        node.setTranslate((3, 4, 5), at=4)
        node.setRotate((10, 20, 30), unit='deg')
        node.addAttr('text', dataType='string')
        for angular, linear in [('deg', 'cm'), ('rad', 'm')]:
            cmds.currentUnit(angle=angular, linear=linear)
            for name in ('tx', 'rx', 'translate', 'rotate', 'offsetParentMatrix', 'text'):
                expected = cmds.getAttr(node.getFullName() + '.' + name)
                with self.forbidden('getAttr', 'attributeQuery', 'ls', 'nodeType'):
                    record = _attribute(node, name)
                    reference = NodeRef.capture(node.getFullName())
                self.assertEqual(record['value'], expected, name)
                self.assertEqual(reference.uuid, node.getUuid())
        cmds.currentUnit(angle='deg', linear='cm')

    def test_display_and_skin_fast_preflight(self):
        """表示色とスキン設定の照会・fast事前検証でgetAttrを使わない。"""
        node = hlib.createNode('transform')
        node.setOverrideColor((.1, .2, .3))
        node.setOutlinerColor((.4, .5, .6))
        expected = (node.getOverrideColor().rgb, node.getOutlinerColor().rgb)
        with self.forbidden('getAttr'):
            self.assertEqual((node.getOverrideColor().rgb, node.getOutlinerColor().rgb), expected)
        joints = [cmds.createNode('joint') for _ in range(2)]
        mesh = cmds.polyCube(ch=False)[0]
        skin = hlib.getNode(cmds.skinCluster(joints, mesh, tsb=True)[0])
        with self.forbidden('getAttr', 'setAttr', 'undoInfo', 'listAttr'):
            skin.setMaxInfluences(2, fast=True)
            skin.normalizeWeights(fast=True)
            self.assertEqual(skin.getMaxInfluences(), 2)

    def test_vector_add_rejects_query_before_mutation(self):
        """ベクトル型もquery/editを共通検証で拒否する。"""
        node = hlib.createNode('network')
        for flag in ('q', 'e', 'query', 'edit'):
            with self.assertRaises(ValueError):
                node.addAttr('bad', attributeType='double3', **{flag: True})
            self.assertFalse(node.hasAttr('bad'))

    def test_scale_geometry_bulk_read_and_fast_units(self):
        """拡縮の取得をAPIへ寄せ、通常Undoとfastの値・単位・インスタンスを比較する。"""
        factories = (
            lambda: cmds.polyCube(ch=False)[0],
            lambda: cmds.curve(d=1, pw=[(1, 2, 3, 1), (3, 4, 5, 2), (2, -1, 4, .5)]),
        )
        for factory in factories:
            source = factory()
            instance = cmds.instance(source)[0]
            cmds.setAttr(instance + '.translate', 5, 3, -2)
            cmds.setAttr(instance + '.rotate', 15, 30, 45)
            cmds.setAttr(instance + '.scale', -2, 3, .5)
            node = hlib.getNode(instance)
            shape = node.getShape()
            points = shape.getVertices() if shape.getType() == 'mesh' else shape.cvs()
            for unit in ('cm', 'm'):
                cmds.currentUnit(linear=unit)
                for space in (MSpace.kObject, MSpace.kWorld):
                    before = points.getPosition(ws=(space == MSpace.kWorld))
                    factors, pivot = (2, .5, -1), (1, 2, 3)
                    expected = [tuple(pivot[i] + (p[i] - pivot[i]) * factors[i] for i in range(3))
                                if index in (0, 2) else p for index, p in enumerate(before)]
                    with patch.object(cmds, 'xform', wraps=cmds.xform) as xform:
                        node.scaleGeometry(factors, ws=(space == MSpace.kWorld), pivot=pivot, indices=[2, 0, 2])
                    self.assertEqual(len(xform.call_args_list), 2)
                    self.assertTrue(all(not call[1].get('query') for call in xform.call_args_list))
                    self.assert_points(points.getPosition(ws=(space == MSpace.kWorld)), expected)
                    cmds.undo()
                    self.assert_points(points.getPosition(ws=(space == MSpace.kWorld)), before)
                    cmds.redo()
                    self.assert_points(points.getPosition(ws=(space == MSpace.kWorld)), expected)
                    cmds.undo()
                    queue = cmds.undoInfo(query=True, undoName=True)
                    weights = None if shape.getType() == 'mesh' else [p.w for p in shape.curveFn().cvPositions()]
                    with self.forbidden('xform', 'ls', 'getAttr', 'setAttr', 'undoInfo'):
                        node.scaleGeometry(factors, ws=(space == MSpace.kWorld), pivot=pivot, indices=[2, 0, 2], fast=True)
                    self.assert_points(points.getPosition(ws=(space == MSpace.kWorld)), expected)
                    self.assertEqual(cmds.undoInfo(query=True, undoName=True), queue)
                    if weights is not None:
                        self.assertEqual([p.w for p in shape.curveFn().cvPositions()], weights)
                cmds.currentUnit(linear='cm')

    def test_scale_geometry_fast_rejections_preserve_points(self):
        """履歴・周期・サーフェス・ロック・不正番号を直接更新前に拒否する。"""
        for name in (cmds.polyCube(ch=True)[0], cmds.circle(ch=False)[0], cmds.nurbsPlane(ch=False)[0]):
            node = hlib.getNode(name)
            shape = node.getShape()
            token = '.vtx[*]' if shape.getType() == 'mesh' else '.cv[*][*]' if shape.getType() == 'nurbsSurface' else '.cv[*]'
            before = cmds.xform(shape.getFullName() + token, query=True, translation=True)
            with self.assertRaises(NotImplementedError):
                node.scaleGeometry(2, fast=True)
            self.assertEqual(cmds.xform(shape.getFullName() + token, query=True, translation=True), before)
        shape = hlib.getNode(cmds.polyCube(ch=False)[0]).getShape()
        before = shape.getVertices().getPosition()
        for indices, exception in (([0, 999], IndexError), ([True], TypeError)):
            with self.assertRaises(exception):
                shape.scaleGeometry(2, indices=indices, fast=True)
            self.assert_points(shape.getVertices().getPosition(), before)
        cmds.setAttr(shape.getFullName() + '.pnts[2].pntx', lock=True)
        with self.assertRaises(RuntimeError):
            shape.scaleGeometry(2, indices=[0, 2], fast=True)
        self.assert_points(shape.getVertices().getPosition(), before)
        with self.assertRaises(TypeError):
            shape.scaleGeometry(2, fast=1)

    def test_periodic_scaling_maps_duplicate_cv_once(self):
        """API末尾と先頭の同一CVを通常モードで一回だけ拡縮する。"""
        shape = hlib.getNode(cmds.circle(ch=False)[0]).getShape()
        end = shape.getNumCVs() - shape.curveFn().degree
        before = shape.cvs().getPosition()
        shape.scaleGeometry(2, indices=[0, end, 0])
        expected = [tuple(v * 2 for v in point) if i in (0, end) else point for i, point in enumerate(before)]
        self.assert_points(shape.cvs().getPosition(), expected)
        cmds.undo()
        self.assert_points(shape.cvs().getPosition(), before)

    def test_rational_cv_world_position_roundtrip(self):
        """重み付きCVはAPIワールドXYZの取得と通常・fast設定で往復する。"""
        node = hlib.getNode(cmds.curve(d=1, pw=[(1, 2, 3, 2), (3, 4, 5, .5)]))
        node.setTranslate((10, 20, 30), at=4)
        node.setScale((-2, 3, .5))
        cvs = node.getShape().cvs()
        cmds.currentUnit(linear='m')
        try:
            before = cvs.getPosition(True)
            cvs.setPositions(before, ws=True)
            self.assert_points(cvs.getPosition(True), before)
            changed = [tuple(v + 1 for v in point) for point in before]
            cvs.setPositions(changed, ws=True)
            self.assert_points(cvs.getPosition(True), changed)
            cmds.undo()
            self.assert_points(cvs.getPosition(True), before)
            with self.forbidden('xform', 'setAttr', 'undoInfo'):
                cvs.setPositions(changed, ws=True, fast=True)
            self.assert_points(cvs.getPosition(True), changed)
        finally:
            cmds.currentUnit(linear='cm')

    def test_aliases_use_api_for_sparse_and_renamed_nodes(self):
        """配列要素のalias取得はcmdsを使わず、改名・削除Undoを追跡する。"""
        node = hlib.createNode('blendShape')
        cmds.setAttr(node.getFullName() + '.weight[7]', .5)
        cmds.aliasAttr('sparseWeight', node.getFullName() + '.weight[7]')
        cmds.aliasAttr('envelopeAlias', node.getFullName() + '.envelope')
        expected = cmds.aliasAttr(node.getFullName(), query=True)
        node.rename('aliasRenamed')
        with self.forbidden('aliasAttr', 'ls', 'getAttr'):
            pairs = node.getAliases()
        self.assertEqual([alias for alias, _ in pairs], expected[::2])
        self.assertEqual(dict(pairs)['sparseWeight'], node.getPlug('weight[7]'))
        cmds.aliasAttr(node.getFullName() + '.sparseWeight', remove=True)
        self.assertNotIn('sparseWeight', dict(node.getAliases()))
        cmds.undo()
        self.assertIn('sparseWeight', dict(node.getAliases()))


if __name__ == '__main__':
    unittest.main(argv=[sys.argv[0]])
