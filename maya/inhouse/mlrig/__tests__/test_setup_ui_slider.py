"""UiSliderの正規化した位置・方向と角の重み・移動の制限を、Pythonで独立に求めた値と比べて確かめる。"""

import unittest

from maya import cmds

from mlrig.setups import UiSlider
from mlrig.setups.uiSlider import OUTPUTS


def _expected(dx, dy, size, rangeX=(-1.0, 1.0), rangeY=(-1.0, 1.0)):
    """生成時からの移動量(cm)から、出力を独立に求める。"""
    x = min(max(dx / size, rangeX[0]), rangeX[1])
    y = min(max(dy / size, rangeY[0]), rangeY[1])
    right, left = max(x, 0.0), max(-x, 0.0)
    up, down = max(y, 0.0), max(-y, 0.0)
    return {"x": x, "y": y, "right": right, "left": left, "up": up, "down": down,
            "upRight": up * right, "upLeft": up * left, "downRight": down * right, "downLeft": down * left}


class UiSliderTest(unittest.TestCase):
    """作成直後・独立計算との一致・移動の制限・片側の範囲・チャンネル・UI単位・所有とUndo・引数を確かめる。"""

    REST = (1.5, -0.5, 0.25)

    def setUp(self):
        """回した枠の下に、原点から離れた位置のスライダーのコントロールを作る。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(angle="deg", linear="cm")
        self.border = cmds.createNode("transform", name="sliderBorder")
        cmds.setAttr(self.border + ".translate", 3, 12, 1)
        cmds.setAttr(self.border + ".rotate", 0, 20, 10)
        self.control = cmds.createNode("transform", name="sliderCtrl", parent=self.border)
        self.control = cmds.ls(self.control, long=True)[0]
        cmds.setAttr(self.control + ".translate", *self.REST)

    def _create(self, **flags):
        flags.setdefault("name", "slider")
        return UiSlider.create(self.control, **flags)

    def _move(self, dx, dy):
        cmds.setAttr(self.control + ".translate", self.REST[0] + dx, self.REST[1] + dy, self.REST[2])

    def _check(self, graph, expected, tolerance=1e-6):
        owner = str(graph.container)
        for attribute in OUTPUTS:
            self.assertAlmostEqual(cmds.getAttr(owner + "." + attribute), expected[attribute], delta=tolerance,
                                   msg=attribute)
        self.assertEqual(UiSlider.weights(expected["x"], expected["y"]), expected)

    def test_rest_is_zero(self):
        """作成直後は全ての出力が0で、コントロールは動かない。"""
        graph = self._create(size=2.0)
        self._check(graph, _expected(0, 0, 2.0))
        for value, rest in zip(cmds.getAttr(self.control + ".translate")[0], self.REST):
            self.assertAlmostEqual(value, rest)

    def test_matches_independent_computation(self):
        """制限を切った状態で格子の各位置(範囲の外を含む)に動かすと、clamp・方向・角の重みが独立計算と一致する。"""
        size = 2.0
        graph = self._create(size=size, limit=False)
        steps = [-3.0, -2.0, -1.3, -0.4, 0.0, 0.5, 1.1, 2.0, 2.7]
        for dx in steps:
            for dy in steps:
                self._move(dx, dy)
                self._check(graph, _expected(dx, dy, size))
        # 斜めの角では角の重みが1、反対の角と辺の中央は0。
        self._move(size, size)
        owner = str(graph.container)
        self.assertAlmostEqual(cmds.getAttr(owner + ".upRight"), 1.0)
        self.assertAlmostEqual(cmds.getAttr(owner + ".downLeft"), 0.0)
        self._move(size, 0)
        self.assertAlmostEqual(cmds.getAttr(owner + ".right"), 1.0)
        self.assertAlmostEqual(cmds.getAttr(owner + ".upRight"), 0.0)

    def test_transform_limits(self):
        """制限を有効にすると、コントロールは枠の外へ出ず(Zは生成時のまま)、出力は枠の端の値になる。"""
        size = 1.5
        graph = self._create(size=size)
        self._move(5.0, -4.0)
        cmds.setAttr(self.control + ".translateZ", 3.0)
        translate = cmds.getAttr(self.control + ".translate")[0]
        self.assertAlmostEqual(translate[0], self.REST[0] + size, places=5)
        self.assertAlmostEqual(translate[1], self.REST[1] - size, places=5)
        self.assertAlmostEqual(translate[2], self.REST[2], places=5)
        self._check(graph, _expected(size, -size, size))
        for axis, low, high in (("X", -1, 1), ("Y", -1, 1), ("Z", 0, 0)):
            index = "XYZ".index(axis)
            self.assertAlmostEqual(cmds.getAttr(self.control + ".minTrans" + axis + "Limit"),
                                   self.REST[index] + low * size)
            self.assertAlmostEqual(cmds.getAttr(self.control + ".maxTrans" + axis + "Limit"),
                                   self.REST[index] + high * size)
            self.assertTrue(cmds.getAttr(self.control + ".minTrans" + axis + "LimitEnable"))
            self.assertTrue(cmds.getAttr(self.control + ".maxTrans" + axis + "LimitEnable"))

    def test_one_sided_and_single_axis(self):
        """縦が上だけ・横なしの範囲では、下と左右の重みは常に0で、横の移動は止まる。"""
        size = 1.0
        graph = self._create(size=size, rangeX=(0.0, 0.0), rangeY=(0.0, 1.0), limit=False)
        for dx, dy in ((0.7, 0.4), (-1.0, -0.8), (0.0, 1.6), (2.0, 0.9)):
            self._move(dx, dy)
            expected = _expected(dx, dy, size, (0.0, 0.0), (0.0, 1.0))
            self._check(graph, expected)
            owner = str(graph.container)
            for attribute in ("down", "right", "left", "downRight", "upLeft"):
                self.assertEqual(cmds.getAttr(owner + "." + attribute), 0.0)
        owner = str(graph.container)
        self.assertEqual(tuple(cmds.getAttr(owner + ".rangeY")[0]), (0.0, 1.0))
        self.assertAlmostEqual(cmds.getAttr(owner + ".size"), 1.0)
        # 制限ありで作り直すと、横は生成時の位置に止まる。
        cmds.delete(owner)
        self._move(0, 0)
        self._create(name="slider2", size=size, rangeX=(0.0, 0.0), rangeY=(-0.5, 1.0))
        self._move(3.0, -3.0)
        translate = cmds.getAttr(self.control + ".translate")[0]
        self.assertAlmostEqual(translate[0], self.REST[0], places=5)
        self.assertAlmostEqual(translate[1], self.REST[1] - 0.5, places=5)
        self.assertAlmostEqual(cmds.getAttr("slider2.down"), 0.5, places=5)

    def test_lock_channels(self):
        """使わないチャンネル(translateZ・回転・スケール・範囲0の軸)はkeyableから外れ、lockChannels=Falseなら変えない。"""
        self._create(rangeY=(0.0, 0.0))
        keyable = set(cmds.listAttr(self.control, keyable=True) or [])
        self.assertIn("translateX", keyable)
        for attribute in ("translateY", "translateZ", "rotateX", "rotateZ", "scaleY"):
            self.assertNotIn(attribute, keyable)
        other = cmds.createNode("transform", name="otherCtrl")
        UiSlider.create(other, name="other", lockChannels=False)
        keyable = set(cmds.listAttr(other, keyable=True) or [])
        for attribute in ("translateZ", "rotateX", "scaleZ"):
            self.assertIn(attribute, keyable)

    def test_ui_units(self):
        """UIの単位がmmでも、size・制限は内部の単位(cm)で扱い、同じ移動量で同じ出力になる。"""
        cmds.currentUnit(linear="mm")
        graph = self._create(size=2.0, limit=False)
        cmds.setAttr(self.control + ".translateX", (self.REST[0] + 1.0) * 10.0)  # mm
        cmds.setAttr(self.control + ".translateY", (self.REST[1] - 0.5) * 10.0)
        self._check(graph, _expected(1.0, -0.5, 2.0))
        cmds.currentUnit(linear="cm")
        self._check(graph, _expected(1.0, -0.5, 2.0))
        other = cmds.createNode("transform", name="otherCtrl")
        cmds.currentUnit(linear="mm")
        UiSlider.create(other, name="other", size=1.5)
        cmds.currentUnit(linear="cm")
        self.assertAlmostEqual(cmds.getAttr(other + ".maxTransXLimit"), 1.5)

    def test_ownership_and_undo(self):
        """計算ノードは全てcontainerが所有し、1回のUndoでノード・制限・keyableが戻り、Redoで再び作られる。"""
        before = set(cmds.ls())
        cmds.undoInfo(stateWithoutFlush=True)
        graph = self._create(size=2.0)
        owner = str(graph.container)
        created = set(cmds.ls()) - before - {owner} - set(cmds.ls(type="hyperLayout"))
        members = set(cmds.container(owner, query=True, nodeList=True) or [])
        self.assertTrue(created)
        self.assertEqual(created - members, set())
        cmds.undo()
        self.assertEqual(set(cmds.ls()) - before, set())
        self.assertFalse(cmds.getAttr(self.control + ".maxTransXLimitEnable"))
        self.assertTrue(cmds.getAttr(self.control + ".rotateX", keyable=True))
        cmds.redo()
        self.assertTrue(cmds.getAttr(self.control + ".maxTransXLimitEnable"))
        self._move(1.0, 1.0)
        self._check(UiSlider(owner), _expected(1.0, 1.0, 2.0))

    def test_invalid_arguments(self):
        """不正な引数はValueErrorになる。"""
        cases = [
            dict(size=0.0), dict(size=-1.0), dict(size=float("nan")), dict(rangeX=(0.5, 1.0)),
            dict(rangeX=(-1.0, -0.2)), dict(rangeY=(-2.0, 1.0)), dict(rangeY=(0.0, 1.5)), dict(rangeX=(0.0,)),
            dict(rangeX=(0.0, 0.0), rangeY=(0.0, 0.0)),
        ]
        for flags in cases:
            with self.assertRaises(ValueError, msg=str(flags)):
                self._create(**flags)
        shape = cmds.createNode("locator", name="sliderShape", parent=self.control)
        with self.assertRaises(ValueError):
            UiSlider.create(shape)
        self._create(name="taken")
        with self.assertRaises(ValueError):
            self._create(name="taken")
        self.assertEqual(cmds.ls(type="container"), ["taken"])


if __name__ == "__main__":
    unittest.main(argv=["test_setup_ui_slider"], exit=False, verbosity=2)
