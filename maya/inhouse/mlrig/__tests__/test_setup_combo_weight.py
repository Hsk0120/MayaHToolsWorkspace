"""ComboWeightの組み合わせ・途中のウェイトを、独立に書いた式と実際のブレンドシェイプで確かめる。"""

import itertools
import random
import unittest

from maya import cmds

from mlrig.setups import ComboWeight

#: 値の許容。clamp・condition は単精度なので、倍精度の 1e-9 ではなく単精度の誤差の範囲で確かめる。
TOLERANCE = 1e-6

COMBOS = {"pullBoth": ["pullL", "pullR"], "pullAll": ["pullL", "pullR", "funnel"]}
INBETWEENS = {"pullLHalf": ("pullL", 0.5), "funnelEarly": ("funnel", 0.25)}


def _clamp(value):
    return min(max(value, 0.0), 1.0)


def _expected(values, method):
    """試験側の独立計算(積・最小・山形)。"""
    a, b, c = (_clamp(values[name]) for name in ("pullL", "pullR", "funnel"))
    if method == "multiply":
        result = {"pullBoth": a * b, "pullAll": a * b * c}
    else:
        result = {"pullBoth": min(a, b), "pullAll": min(a, b, c)}
    result["pullLHalf"] = 2.0 * a if a <= 0.5 else 2.0 * (1.0 - a)
    result["funnelEarly"] = 4.0 * c if c <= 0.25 else (1.0 - c) / 0.75
    return result


class ComboWeightTest(unittest.TestCase):
    """積・最小・山形の値、範囲外の入力、入力の接続、ブレンドシェイプでの補正、所有とUndo・引数を確認する。"""

    def setUp(self):
        """3つのドライバー(container のアトリビュート)を持つ ComboWeight を作る。"""
        cmds.file(new=True, force=True)
        self.setup = ComboWeight.create(["pullL", "pullR", "funnel"], COMBOS, INBETWEENS, name="combo")
        self.owner = str(self.setup.container)

    def _set(self, owner, values):
        for name, value in values.items():
            cmds.setAttr(owner + "." + name, value)

    def _check(self, owner, values, method):
        expected = _expected(values, method)
        python = ComboWeight.evaluate(values, COMBOS, INBETWEENS, method)
        for name, value in expected.items():
            self.assertAlmostEqual(python[name], value, places=12, msg=name)
            self.assertLess(abs(cmds.getAttr(owner + "." + name) - value), TOLERANCE, (name, values))

    def test_rest_is_zero(self):
        """作成直後(ドライバーが0)はすべての出力が0で、出力は keyable でない。"""
        for name in list(COMBOS) + list(INBETWEENS):
            self.assertEqual(cmds.getAttr(self.owner + "." + name), 0.0)
            self.assertFalse(cmds.getAttr(self.owner + "." + name, keyable=True))
        for name in ("pullL", "pullR", "funnel"):
            self.assertTrue(cmds.getAttr(self.owner + "." + name, keyable=True))
        self.assertEqual(self.setup.getDrivers(), ["pullL", "pullR", "funnel"])
        self.assertEqual(self.setup.getOutputs(), ["pullBoth", "pullAll", "pullLHalf", "funnelEarly"])

    def test_multiply(self):
        """格子の値と範囲外を含む乱数で、積と山形がPython版・独立計算と一致する。"""
        grid = (0.0, 0.25, 0.5, 0.8, 1.0)
        cases = [dict(zip(("pullL", "pullR", "funnel"), item)) for item in itertools.product(grid, repeat=3)]
        generator = random.Random(7)
        cases += [{name: generator.uniform(-0.5, 1.5) for name in ("pullL", "pullR", "funnel")}
                  for _ in range(20)]
        for values in cases:
            self._set(self.owner, values)
            self._check(self.owner, values, "multiply")

    def test_lowest(self):
        """method=lowest では最小になり、山形は同じ。"""
        setup = ComboWeight.create(["pullL", "pullR", "funnel"], COMBOS, INBETWEENS, method="lowest",
                                   name="lowest")
        owner = str(setup.container)
        self.assertEqual(cmds.getAttr(owner + ".comboMethod"), 1)
        generator = random.Random(11)
        for _ in range(30):
            values = {name: generator.uniform(-0.5, 1.5) for name in ("pullL", "pullR", "funnel")}
            self._set(owner, values)
            self._check(owner, values, "lowest")

    def test_inbetween_peak(self):
        """山形は位置で1、0と1で0、位置の前後で一次式。"""
        for value, expected in ((0.0, 0.0), (0.25, 0.5), (0.5, 1.0), (0.75, 0.5), (1.0, 0.0), (1.4, 0.0)):
            cmds.setAttr(self.owner + ".pullL", value)
            self.assertLess(abs(cmds.getAttr(self.owner + ".pullLHalf") - expected), TOLERANCE, value)
        for value, expected in ((0.25, 1.0), (0.1, 0.4), (0.625, 0.5)):
            cmds.setAttr(self.owner + ".funnel", value)
            self.assertLess(abs(cmds.getAttr(self.owner + ".funnelEarly") - expected), TOLERANCE, value)

    def test_sources(self):
        """入力のアトリビュートを渡すと、その値で動く(container のアトリビュートは入力から接続される)。"""
        left = cmds.createNode("transform", name="leftCtrl")
        right = cmds.createNode("transform", name="rightCtrl")
        setup = ComboWeight.create({"left": left + ".translateY", "right": right + ".translateY", "free": None},
                                   {"both": ["left", "right"]}, {"leftHalf": ("left", 0.5)}, name="sourced")
        owner = str(setup.container)
        self.assertEqual(cmds.listConnections(owner + ".left", source=True, destination=False, plugs=True),
                         [left + ".translateY"])
        self.assertFalse(cmds.listConnections(owner + ".free", source=True, destination=False))
        cmds.setAttr(left + ".translateY", 0.6)
        cmds.setAttr(right + ".translateY", 0.5)
        self.assertLess(abs(cmds.getAttr(owner + ".both") - 0.3), TOLERANCE)
        self.assertLess(abs(cmds.getAttr(owner + ".leftHalf") - 0.8), TOLERANCE)

    def test_blend_shape_corrective(self):
        """左右のシェイプを足すと崩れる頂点を、組み合わせのウェイトで動かす補正シェイプが直す。"""
        base = cmds.polyPlane(name="mouth", width=2, height=1, subdivisionsX=2, subdivisionsY=1,
                              constructionHistory=False)[0]
        targets = {}
        for item in ("left", "right", "fix"):
            targets[item] = cmds.duplicate(base, name="mouth_" + item)[0]
        # 頂点0〜2が下の辺、3〜5が上の辺。真ん中の上の頂点4は、左右それぞれで +1 上がる。
        cmds.move(0, 1, 0, targets["left"] + ".vtx[4]", targets["left"] + ".vtx[5]", relative=True)
        cmds.move(0, 1, 0, targets["right"] + ".vtx[3]", targets["right"] + ".vtx[4]", relative=True)
        # 同時に動かすと頂点4は +2 になるので、補正で -1 戻して +1 にしたい。
        cmds.move(0, -1, 0, targets["fix"] + ".vtx[4]", relative=True)
        blend = cmds.blendShape(targets["left"], targets["right"], targets["fix"], base, name="mouthBlend")[0]
        setup = ComboWeight.create(["left", "right"], {"both": ["left", "right"]}, name="mouthCombo")
        owner = str(setup.container)
        for index, attribute in enumerate(("left", "right")):
            cmds.connectAttr(owner + "." + attribute, "{}.weight[{}]".format(blend, index))
        cmds.connectAttr(owner + ".both", blend + ".weight[2]")
        rest = cmds.pointPosition(base + ".vtx[4]", world=True)[1]
        for left, right, expected in ((1, 0, 1.0), (0, 1, 1.0), (1, 1, 1.0), (0.5, 0.5, 0.75), (0, 0, 0.0)):
            cmds.setAttr(owner + ".left", left)
            cmds.setAttr(owner + ".right", right)
            height = cmds.pointPosition(base + ".vtx[4]", world=True)[1] - rest
            self.assertLess(abs(height - expected), TOLERANCE, (left, right))

    def test_container_and_undo(self):
        """生成ノードはcontainerが所有し、作成はUndoで消えRedoで戻る。"""
        members = set(cmds.container(self.owner, query=True, nodeList=True) or [])
        created = {node for node in cmds.ls("combo_*") if cmds.nodeType(node) != "hyperLayout"}
        self.assertTrue(created)
        self.assertTrue(created <= members)
        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)
        cmds.flushUndo()
        ComboWeight.create(["a", "b"], {"ab": ["a", "b"]}, name="combo")
        self.assertTrue(cmds.objExists("combo.ab"))
        cmds.undo()
        self.assertFalse(cmds.objExists("combo"))
        self.assertFalse(cmds.ls("combo_*"))
        cmds.redo()
        self.assertTrue(cmds.objExists("combo.ab"))

    def test_arguments(self):
        """不正な名前・重複・未知のドライバー・1つだけの組み合わせ・位置・method・入力・名前の重複を拒否する。"""
        cases = (
            {"drivers": []},
            {"combos": {}},
            {"combos": {"ab": ["a"]}},
            {"combos": {"ab": ["a", "a"]}},
            {"combos": {"ab": ["a", "x"]}},
            {"combos": {"a": ["a", "b"]}},
            {"combos": {"bad name": ["a", "b"]}},
            {"combos": {"comboMethod": ["a", "b"]}},
            {"inbetweens": {"half": ("a", 0.0)}},
            {"inbetweens": {"half": ("a", 1.0)}},
            {"inbetweens": {"half": ("a", float("nan"))}},
            {"inbetweens": {"half": ("x", 0.5)}},
            {"method": "smooth"},
            {"drivers": {"a": "missingNode.translateY", "b": None}},
        )
        for kwargs in cases:
            arguments = {"drivers": ["a", "b"], "combos": {"ab": ["a", "b"]}}
            arguments.update(kwargs)
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                ComboWeight.create(name="bad", **arguments)
        with self.assertRaises(ValueError):
            ComboWeight.create(["a", "b"], {"ab": ["a", "b"]}, name="combo")
        self.assertFalse(cmds.objExists("bad"))


if __name__ == "__main__":
    unittest.main()
