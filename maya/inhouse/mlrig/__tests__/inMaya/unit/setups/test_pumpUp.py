"""PumpUpの増幅した行列を、MTransformationMatrixで独立に分けて組み直した値と比べて確かめる。"""

import math
import unittest

from maya import cmds
from maya.api import OpenMaya as om

from mlrig.setups import PumpUp


def _local(node):
    """ノードの親の空間での行列(matrix · offsetParentMatrix)。"""
    return om.MMatrix(cmds.getAttr(node + ".matrix")) * om.MMatrix(cmds.getAttr(node + ".offsetParentMatrix"))


def _close(test, first, second, tolerance=1e-5):
    """2つの列の各成分が誤差の範囲で等しいことを確かめる。"""
    for a, b in zip(first, second):
        test.assertAlmostEqual(a, b, delta=tolerance)


class PumpUpTest(unittest.TestCase):
    """作成直後・独立計算との一致・pump/gain/offsetの変更・駆動するplug・UI単位・所有とUndo・引数を確かめる。"""

    def setUp(self):
        """回した親の下に、移動・回転・スケールを持つ補助骨を2つ(1つはoffsetParentMatrix付き)作る。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(angle="deg", linear="cm")
        self.parent = cmds.createNode("transform", name="upperArm")
        cmds.setAttr(self.parent + ".translate", 2, 10, -1)
        cmds.setAttr(self.parent + ".rotate", 10, -30, 45)
        self.helpers = []
        for index, (translate, rotate, scale) in enumerate((
            ((2.5, 0.3, 0.0), (0, 0, 15), (1, 1, 1)),
            ((1.0, -0.4, 0.6), (20, 10, -5), (1.1, 0.9, 1.2)),
        )):
            helper = cmds.createNode("joint", name="helper{}".format(index), parent=self.parent)
            cmds.setAttr(helper + ".translate", *translate)
            cmds.setAttr(helper + ".rotate", *rotate)
            cmds.setAttr(helper + ".scale", *scale)
            self.helpers.append(cmds.ls(helper, long=True)[0])
        offset = om.MTransformationMatrix()
        offset.setTranslation(om.MVector(0.2, 0.5, -0.3), om.MSpace.kTransform)
        offset.setRotation(om.MEulerRotation(0.1, 0.2, 0.3))
        cmds.setAttr(self.helpers[1] + ".offsetParentMatrix", list(offset.asMatrix()), type="matrix")
        self.rest = [om.MTransformationMatrix(_local(helper)) for helper in self.helpers]

    def _create(self, **flags):
        flags.setdefault("name", "pump")
        return PumpUp.create(self.helpers, **flags)

    def _expected(self, index, pump, gain=1.0, translateOffset=(0, 0, 0), scaleOffset=(0, 0, 0)):
        """補助骨indexの増幅した親の空間の行列を独立に求める。"""
        current = om.MTransformationMatrix(_local(self.helpers[index]))
        rest = self.rest[index]
        translate = current.translation(om.MSpace.kTransform)
        restTranslate = rest.translation(om.MSpace.kTransform)
        scale = current.scale(om.MSpace.kTransform)
        restScale = rest.scale(om.MSpace.kTransform)
        newTranslate = [translate[i] + (translate[i] - restTranslate[i]) * gain * pump + translateOffset[i] * pump
                        for i in range(3)]
        newScale = [scale[i] + (scale[i] - restScale[i]) * gain * pump + scaleOffset[i] * pump for i in range(3)]
        result = om.MTransformationMatrix()
        result.setScale(newScale, om.MSpace.kTransform)
        result.setRotation(current.rotation(asQuaternion=True))
        result.setTranslation(om.MVector(*newTranslate), om.MSpace.kTransform)
        return newTranslate, newScale, result.asMatrix()

    def _check(self, graph, pump, **flags):
        """全ての補助骨で、出力が独立計算と一致することを確かめる。"""
        owner = str(graph.container)
        parentWorld = om.MMatrix(cmds.getAttr(self.parent + ".worldMatrix[0]"))
        for index in range(len(self.helpers)):
            values = {key: value[index] for key, value in flags.items()}
            translate, scale, matrix = self._expected(index, pump, **values)
            _close(self, cmds.getAttr("{}.translate{}".format(owner, index))[0], translate)
            _close(self, cmds.getAttr("{}.scale{}".format(owner, index))[0], scale)
            _close(self, cmds.getAttr("{}.matrix{}".format(owner, index)), matrix)
            _close(self, cmds.getAttr("{}.worldMatrix{}".format(owner, index)), matrix * parentWorld)

    def _move(self):
        """既存の仕組みが補助骨を動かした状態にする。"""
        cmds.setAttr(self.helpers[0] + ".translate", 2.8, 0.6, 0.1)
        cmds.setAttr(self.helpers[0] + ".scale", 1.0, 1.3, 1.25)
        cmds.setAttr(self.helpers[1] + ".translate", 1.2, -0.2, 0.9)
        cmds.setAttr(self.helpers[1] + ".rotate", 35, 0, 10)
        cmds.setAttr(self.helpers[1] + ".scale", 1.0, 1.1, 1.4)

    def test_pump_zero_matches_helpers(self):
        """pump=0では、既存の仕組みが補助骨を動かしても出力は補助骨と一致する(作成時に跳ねない)。"""
        graph = self._create()
        owner = str(graph.container)
        for move in (False, True):
            if move:
                self._move()
            for index, helper in enumerate(self.helpers):
                _close(self, cmds.getAttr("{}.matrix{}".format(owner, index)), _local(helper))
                _close(self, cmds.getAttr("{}.worldMatrix{}".format(owner, index)),
                       cmds.getAttr(helper + ".worldMatrix[0]"))

    def test_matches_independent_computation(self):
        """補助骨を動かしてpumpを変えると、生成時からの変化が (1 + gain*pump) 倍になり、独立計算と一致する。"""
        graph = self._create()
        self._move()
        for pump in (0.5, 1.0, 2.0, -0.5):
            cmds.setAttr(str(graph.container) + ".pump", pump)
            self._check(graph, pump)
        # 生成時の姿勢のままなら、offsetが0なのでpumpを変えても変わらない。
        cmds.setAttr(self.helpers[0] + ".translate", 2.5, 0.3, 0.0)
        cmds.setAttr(self.helpers[0] + ".scale", 1, 1, 1)
        cmds.setAttr(str(graph.container) + ".pump", 3.0)
        _close(self, cmds.getAttr(str(graph.container) + ".matrix0"), _local(self.helpers[0]))

    def test_gain_and_offsets(self):
        """gain・translateOffset・scaleOffset の引数とアトリビュートの変更が式どおりに反映される。"""
        flags = {"gain": (0.5, 2.0), "translateOffset": ((0, 0.4, 0), (0.1, 0, -0.2)),
                 "scaleOffset": ((0, 0.3, 0.3), (0.2, 0, 0))}
        graph = self._create(gains=flags["gain"], translateOffsets=flags["translateOffset"],
                             scaleOffsets=flags["scaleOffset"])
        owner = str(graph.container)
        self._move()
        cmds.setAttr(owner + ".pump", 1.5)
        self._check(graph, 1.5, **flags)
        cmds.setAttr(owner + ".gain1", 0.0)
        cmds.setAttr(owner + ".scaleOffset0", 0.1, 0.5, 0.0, type="double3")
        flags = {"gain": (0.5, 0.0), "translateOffset": flags["translateOffset"],
                 "scaleOffset": ((0.1, 0.5, 0.0), (0.2, 0, 0))}
        self._check(graph, 1.5, **flags)
        for attr in ("pump", "gain0", "translateOffset0X", "scaleOffset1Z"):
            self.assertTrue(cmds.getAttr(owner + "." + attr, keyable=True), attr)

    def test_driver_plug(self):
        """driverを渡すと、そのplugの値がpumpになる。"""
        control = cmds.createNode("transform", name="pumpCtrl")
        graph = self._create(driver=control + ".translateY")
        owner = str(graph.container)
        self._move()
        cmds.setAttr(control + ".translateY", 1.25)
        self.assertAlmostEqual(cmds.getAttr(owner + ".pump"), 1.25)
        self._check(graph, 1.25)

    def test_ui_units(self):
        """UIの単位がmmでも、offsetは内部の単位(cm)のまま同じ結果になる。"""
        cmds.currentUnit(linear="mm", angle="rad")
        graph = self._create(translateOffsets=((0, 0.4, 0), (0, 0, 0)))
        cmds.currentUnit(linear="cm", angle="deg")
        self._move()
        cmds.setAttr(str(graph.container) + ".pump", 1.0)
        self._check(graph, 1.0, translateOffset=((0, 0.4, 0), (0, 0, 0)))

    def test_ownership_and_undo(self):
        """生成した計算ノードは全てcontainerが所有し、1回のUndoで全て消え、Redoで戻る。"""
        control = cmds.createNode("transform", name="pumpCtrl")
        cmds.currentUnit(linear="mm")  # 長さのdriverにMayaが単位変換を挟む場合も所有されること
        before = set(cmds.ls())
        cmds.undoInfo(stateWithoutFlush=True)
        graph = self._create(driver=control + ".translateY")
        owner = str(graph.container)
        created = set(cmds.ls()) - before - {owner} - set(cmds.ls(type="hyperLayout"))
        members = set(cmds.container(owner, query=True, nodeList=True) or [])
        self.assertTrue(created)
        self.assertEqual(created - members, set())
        cmds.undo()
        self.assertEqual(set(cmds.ls()) - before, set())
        cmds.redo()
        cmds.currentUnit(linear="cm")
        self._move()
        cmds.setAttr(control + ".translateY", 0.07)
        self._check(PumpUp(owner), cmds.getAttr(owner + ".pump"))

    def test_invalid_arguments(self):
        """不正な引数はValueErrorになる。"""
        control = cmds.createNode("transform", name="pumpCtrl")
        cases = [
            dict(gains=(1.0,)), dict(gains=(1.0, float("inf"))), dict(translateOffsets=((0, 0, 0),)),
            dict(scaleOffsets=((0, 0), (0, 0, 0))), dict(driver=control + ".worldMatrix[0]"),
        ]
        for flags in cases:
            with self.assertRaises(ValueError, msg=str(flags)):
                self._create(**flags)
        with self.assertRaises(ValueError):
            PumpUp.create([])
        with self.assertRaises(ValueError):
            PumpUp.create([self.helpers[0], self.helpers[0]])
        shape = cmds.createNode("locator", name="pumpShape", parent=control)
        with self.assertRaises(ValueError):
            PumpUp.create([shape])
        self._create(name="taken")
        with self.assertRaises(ValueError):
            self._create(name="taken")
        self.assertEqual(cmds.ls(type="container"), ["taken"])


if __name__ == "__main__":
    unittest.main(argv=["test_setup_pump_up"], exit=False, verbosity=2)
