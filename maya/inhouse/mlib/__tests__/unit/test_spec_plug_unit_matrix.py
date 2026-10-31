"""Plug.get/setを、アトリビュートの型 × UI単位 × 通常/fast の組み合わせで cmds と突き合わせる。

UI単位を cm/deg/film 以外(m・rad・ntsc 等)にしても、mlib の既定(距離cm・角度度・時間はUIのフレーム)と
uiUnits=True(UI単位)が ``cmds.getAttr`` の値と換算で一致すること、set の後に cmds で読んだ値が
期待どおりになること、通常経路は1回のUndoで戻りfastはUndoに記録しないことを確かめる。
"""

import itertools
import math
import random
import sys
import unittest

import maya.cmds as cmds

import mlib
mlib.reload()
from support.specCase import NamespaceCase

#: 距離のUI単位と、1UI単位あたりのcm。
LINEAR = {"cm": 1.0, "mm": 0.1, "m": 100.0, "in": 2.54}

#: 角度のUI単位と、1UI単位あたりの度。
ANGLE = {"deg": 1.0, "rad": 180.0 / math.pi}

#: 時間のUI単位と、1フレームの秒。
TIME = {"film": 1 / 24.0, "ntsc": 1 / 30.0, "pal": 1 / 25.0}


class PlugUnitMatrixTest(NamespaceCase):
    """型・単位・経路の組み合わせごとの往復。"""

    PREFIX = "mlibPlugUnits_"

    def setUp(self):
        """UI単位を保存し、各型のアトリビュートを持つノードを作る。"""
        super().setUp()
        self.units = (cmds.currentUnit(query=True, linear=True), cmds.currentUnit(query=True, angle=True),
                      cmds.currentUnit(query=True, time=True))
        cmds.currentUnit(linear="cm", angle="deg", time="film")
        self.node = mlib.createNode("transform", name=self.name("node"), skipSelect=True)
        name = self.node.getFullName()
        cmds.addAttr(name, longName="dist", attributeType="doubleLinear")
        cmds.addAttr(name, longName="ang", attributeType="doubleAngle")
        cmds.addAttr(name, longName="tm", attributeType="time")
        cmds.addAttr(name, longName="plain", attributeType="double")
        cmds.addAttr(name, longName="count", attributeType="long")
        cmds.addAttr(name, longName="flag", attributeType="bool")
        cmds.addAttr(name, longName="mode", attributeType="enum", enumName="a:b:c")
        cmds.addAttr(name, longName="text", dataType="string")
        cmds.addAttr(name, longName="vec", attributeType="double3")
        for axis in "XYZ":
            cmds.addAttr(name, longName="vec" + axis, attributeType="doubleLinear", parent="vec")

    def tearDown(self):
        """UI単位を戻す。"""
        cmds.currentUnit(linear=self.units[0], angle=self.units[1], time=self.units[2])
        super().tearDown()

    def test_unit_conversions_for_get_and_set(self):
        """距離・角度・時間・3成分の距離を、全UI単位の組み合わせで往復させる。"""
        rng = random.Random(31)
        name = self.node.getFullName()
        for linear, angle, time in itertools.product(LINEAR, ANGLE, TIME):
            cmds.currentUnit(linear=linear, angle=angle, time=time)
            for fast in (False, True):
                distance, degrees, frames = rng.uniform(-50, 50), rng.uniform(-170, 170), rng.uniform(0, 100)
                vector = tuple(rng.uniform(-50, 50) for _ in range(3))
                with self.subTest(linear=linear, angle=angle, time=time, fast=fast):
                    self.node.getPlug("dist").set(distance, fast=fast)
                    self.assertAlmostEqual(cmds.getAttr(name + ".dist") * LINEAR[linear], distance, places=6)
                    self.assertAlmostEqual(self.node.getPlug("dist").get(), distance, places=6)
                    self.assertAlmostEqual(self.node.getPlug("dist").get(uiUnits=True), distance / LINEAR[linear], places=6)
                    self.node.getPlug("ang").set(degrees, fast=fast)
                    self.assertAlmostEqual(cmds.getAttr(name + ".ang") * ANGLE[angle], degrees, places=6)
                    self.assertAlmostEqual(self.node.getPlug("ang").get(), degrees, places=6)
                    self.assertAlmostEqual(self.node.getPlug("ang").get(unit="rad"), math.radians(degrees), places=9)
                    self.node.getPlug("ang").set(math.radians(degrees), unit="rad", fast=fast)
                    self.assertAlmostEqual(self.node.getPlug("ang").get(), degrees, places=6)
                    self.node.getPlug("tm").set(frames, fast=fast)
                    self.assertAlmostEqual(cmds.getAttr(name + ".tm"), frames, places=4)
                    # MTimeは内部で刻み(tick)に丸めるため、秒の比較は1e-6で行う。
                    self.assertAlmostEqual(self.node.getPlug("tm").get(timeUnit="sec"), frames * TIME[time], places=6)
                    self.node.getPlug("tm").set(1.5, timeUnit="sec", fast=fast)
                    self.assertAlmostEqual(cmds.getAttr(name + ".tm"), 1.5 / TIME[time], places=4)
                    self.node.getPlug("vec").set(vector, fast=fast)
                    for actual, expected in zip(cmds.getAttr(name + ".vec")[0], vector):
                        self.assertAlmostEqual(actual * LINEAR[linear], expected, places=6)
                    for actual, expected in zip(self.node.getPlug("vec").get(), vector):
                        self.assertAlmostEqual(actual, expected, places=6)

    def test_unitless_types_and_undo(self):
        """無単位の型は単位に関係なくそのまま往復し、通常は1回のUndoで戻り、fastは記録しない。"""
        name = self.node.getFullName()
        cmds.currentUnit(linear="m", angle="rad", time="ntsc")
        values = (("plain", 2.5, 2.5), ("count", 7, 7), ("flag", True, True), ("mode", 2, 2),
                  ("text", "日本語 text", "日本語 text"))
        for attribute, value, expected in values:
            for fast in (False, True):
                with self.subTest(attribute=attribute, fast=fast):
                    plug = self.node.getPlug(attribute)
                    before = cmds.getAttr(name + "." + attribute)
                    cmds.flushUndo()
                    plug.set(value, fast=fast)
                    self.assertEqual(cmds.getAttr(name + "." + attribute), expected)
                    self.assertEqual(plug.get(), expected)
                    if fast:
                        self.assertTrue(cmds.undoInfo(query=True, undoQueueEmpty=True))
                        cmds.setAttr(name + "." + attribute, *([before] if attribute != "text" else [before or ""]),
                                     **({"type": "string"} if attribute == "text" else {}))
                    else:
                        cmds.undo()
                        self.assertEqual(cmds.getAttr(name + "." + attribute), before)

    def test_invalid_values_are_rejected_before_writing(self):
        """型の合わない値は書き込む前に拒否し、元の値を保つ(通常・fast)。"""
        name = self.node.getFullName()
        cases = (("dist", "abc"), ("flag", "yes"), ("vec", (1, 2)), ("mode", 9), ("text", 5))
        for attribute, value in cases:
            for fast in (False, True):
                with self.subTest(attribute=attribute, value=value, fast=fast):
                    before = cmds.getAttr(name + "." + attribute)
                    with self.assertRaises((TypeError, ValueError, RuntimeError)):
                        self.node.getPlug(attribute).set(value, fast=fast)
                    self.assertEqual(cmds.getAttr(name + "." + attribute), before)

    def test_integer_types_round_fractions(self):
        """整数・bool・enumへの小数は、通常・fastとも四捨五入して書く(Plug.setの仕様)。"""
        name = self.node.getFullName()
        for attribute, value, expected in (("count", 1.6, 2), ("count", -2.4, -2), ("mode", 1.6, 2), ("flag", 0.7, True)):
            for fast in (False, True):
                with self.subTest(attribute=attribute, value=value, fast=fast):
                    self.node.getPlug(attribute).set(value, fast=fast)
                    self.assertEqual(cmds.getAttr(name + "." + attribute), expected)


if __name__ == "__main__":
    result = unittest.main(exit=False, verbosity=1).result
    sys.exit(0 if result.wasSuccessful() else 1)
