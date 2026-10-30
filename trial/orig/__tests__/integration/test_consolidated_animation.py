"""アニメーションのAPI読取とfast編集を通常のMaya編集と比較する。"""

import math
import unittest
from unittest.mock import patch
from contextlib import ExitStack

import maya.api.OpenMaya as om2
import maya.api.OpenMayaAnim as oma2
import maya.cmds as cmds
import mlib


class ConsolidatedAnimationTest(unittest.TestCase):
    """全8型・単位・接線・キー順・Undoの境界を検証する。"""

    def setUp(self):
        """独立シーンとUI単位を初期化する。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(linear="cm", angle="deg", time="film")
        cmds.undoInfo(state=True)

    def tearDown(self):
        """基準の表示単位へ戻す。"""
        cmds.currentUnit(linear="cm", angle="deg", time="film")

    def create(self, suffix, fast=False):
        """同じ3キーを持つ検証カーブを作る。"""
        curve = mlib.createNode("animCurve" + suffix)
        for x, y in ((-1, 1), (.25, 4), (2, 2)):
            curve.setKey(x, y, fast=fast)
        return curve

    def assert_curves(self, normal, fast):
        """入力・値・評価・全キーの接線状態が一致することを確認する。"""
        self.assertEqual(normal.getKeyCount(), fast.getKeyCount())
        for actual, expected in zip(fast.getKeyInputs(), normal.getKeyInputs()):
            self.assertAlmostEqual(actual, expected, delta=1e-6)
        for actual, expected in zip(fast.getKeyValues(), normal.getKeyValues()):
            self.assertAlmostEqual(actual, expected, delta=1e-6)
        for x in (-2, -.5, 0, .5, 1, 2.5, 4):
            self.assertAlmostEqual(fast.evaluate(x), normal.evaluate(x), delta=2e-5)
        for i in range(normal.getKeyCount()):
            left, right = normal.getTangent(i), fast.getTangent(i)
            for key in left:
                if isinstance(left[key], float):
                    self.assertAlmostEqual(left[key], right[key], delta=2e-5, msg=key)
                else:
                    self.assertEqual(left[key], right[key], key)

    def test_all_types_read_update_remove_and_fast_undo(self):
        """時間出力も秒で保持し、キー更新・削除は通常と一致する。"""
        for suffix in ("TA", "TL", "TT", "TU", "UA", "UL", "UT", "UU"):
            with self.subTest(suffix=suffix):
                normal, fast = self.create(suffix), self.create(suffix, fast=True)
                self.assert_curves(normal, fast)
                normal.setKey(.25, 7)
                before = cmds.undoInfo(q=True, undoName=True)
                with patch.object(cmds, "setKeyframe", side_effect=AssertionError("cmds key")), \
                        patch.object(cmds, "setAttr", side_effect=AssertionError("cmds set")), \
                        patch.object(cmds, "cutKey", side_effect=AssertionError("cmds cut")), \
                        patch.object(cmds, "undoInfo", side_effect=AssertionError("cmds undo")):
                    fast.setKey(.25, 7, fast=True)
                self.assertEqual(cmds.undoInfo(q=True, undoName=True), before)
                self.assert_curves(normal, fast)
                normal.removeKey(2)
                fast.removeKey(2, fast=True)
                self.assert_curves(normal, fast)

    def test_readers_are_api_only_and_match_maya_tangent_units(self):
        """UI単位を変えても読取はコマンド照会を使わず、Maya接線値と一致する。"""
        for linear, angle, time in (("cm", "deg", "film"), ("m", "rad", "ntsc")):
            cmds.currentUnit(linear=linear, angle=angle, time=time)
            curve = self.create("TA")
            expected = {}
            for name in ("inTangentType", "outTangentType", "inAngle", "outAngle", "inWeight", "outWeight", "lock", "weightLock", "weightedTangents"):
                value = cmds.keyTangent(str(curve), q=True, index=(1, 1), **{name: True})[0]
                if name.endswith("Angle"):
                    value = om2.MAngle(value, om2.MAngle.uiUnit()).asRadians()
                expected[name] = value
            with ExitStack() as stack:
                for command in ("keyframe", "keyTangent", "getAttr"):
                    stack.enter_context(patch.object(cmds, command, side_effect=AssertionError(command)))
                self.assertEqual(curve.getKeyCount(), 3)
                self.assertEqual(curve.getKeyInputs(), [-1, .25, 2])
                # setKeyの角度出力の既定は度。
                self.assertEqual([round(v, 9) for v in curve.getKeyValues()], [1, 4, 2])
                self.assertTrue(math.isfinite(curve.evaluate(0)))
                actual = curve.getTangent(1, unit="rad")
                in_degrees = curve.getTangent(1)
            for key in expected:
                if isinstance(expected[key], float):
                    self.assertAlmostEqual(actual[key], expected[key], places=6)
                else:
                    self.assertEqual(actual[key], expected[key])
            # 接線の角度の既定は度。
            self.assertAlmostEqual(in_degrees["inAngle"], math.degrees(expected["inAngle"]), places=6)

    def test_tangent_lock_weight_and_mode_flags_match_commands(self):
        """角度・ウェイト・ロックと全体モード旗の優先順位を維持する。"""
        options = ({"outTangentType": "flat"},
                   {"lock": False, "inAngle": .2, "outAngle": .5},
                   {"weightedTangents": True, "inAngle": .3, "outWeight": .7},
                   {"lock": False, "weightLock": False, "inAngle": .3,
                    "outAngle": -.5, "inWeight": 1.2, "outWeight": .7},
                   {"lock": True, "inAngle": .6},
                   {"weightLock": True, "outWeight": 2})
        for suffix in ("TA", "TL", "TT", "TU", "UA", "UL", "UT", "UU"):
            normal, fast = self.create(suffix), self.create(suffix)
            for kwargs in options:
                with self.subTest(suffix=suffix, flags=kwargs):
                    normal.setTangent(1, **kwargs)
                    with patch.object(cmds, "keyTangent", side_effect=AssertionError("cmds tangent")):
                        fast.setTangent(1, fast=True, **kwargs)
                    self.assert_curves(normal, fast)

    def test_tangent_type_names_match_maya_commands(self):
        """splineや自動接線の標準名で作成・編集・照会できる。"""
        names = (("fixed", "Fixed"), ("linear", "Linear"),
                 ("flat", "Flat"), ("spline", "Smooth"), ("step", "Step"),
                 ("slow", "Slow"), ("fast", "Fast"), ("clamped", "Clamped"),
                 ("plateau", "Plateau"), ("stepnext", "StepNext"), ("auto", "Auto"),
                 ("autocustom", "AutoCustom"), ("autoease", "AutoEase"),
                 ("automix", "AutoMix"))
        for name, suffix in names:
            if not hasattr(oma2.MFnAnimCurve, "kTangent" + suffix):
                continue
            with self.subTest(tangent=name):
                normal, fast = self.create("UU"), self.create("UU")
                # step系はMayaが出力接線として扱う。固定接線は既存キーだけで編集する。
                incoming = "auto" if name in ("step", "stepnext") else name
                normal.setTangent(1, inTangentType=incoming, outTangentType=name)
                with patch.object(cmds, "keyTangent", side_effect=AssertionError("cmds tangent")):
                    fast.setTangent(1, inTangentType=incoming, outTangentType=name, fast=True)
                for flag in ("inTangentType", "outTangentType"):
                    expected = cmds.keyTangent(str(normal), q=True, index=(1, 1), **{flag: True})[0]
                    self.assertEqual(fast.getTangent(1)[flag], expected)
                    self.assertEqual(normal.getTangent(1)[flag], expected)
                self.assert_curves(normal, fast)
                if name == "fixed":
                    continue
                normal.setKey(4, 5, inTangentType=incoming, outTangentType=name)
                with patch.object(cmds, "setKeyframe", side_effect=AssertionError("cmds key")):
                    fast.setKey(4, 5, inTangentType=incoming, outTangentType=name, fast=True)
                self.assert_curves(normal, fast)

    def test_shift_and_positive_scale_preserve_fixed_tangent_shape(self):
        """移動・正の入力倍率の拡縮は固定/重み付き接線まで通常と一致する。"""
        for suffix in ("TA", "TL", "TT", "TU", "UA", "UL", "UT", "UU"):
            for weighted in (False, True):
                with self.subTest(suffix=suffix, weighted=weighted):
                    normal, fast = self.create(suffix), self.create(suffix)
                    for curve in (normal, fast):
                        curve.setTangent(1, weightedTangents=weighted)
                        curve.setTangent(1, lock=False, inAngle=.3, outAngle=-.6)
                    normal.shiftKeys(.5, 1.25)
                    with patch.object(cmds, "keyframe", side_effect=AssertionError("cmds shift")):
                        fast.shiftKeys(.5, 1.25, fast=True)
                    self.assert_curves(normal, fast)
                    normal.scaleKeys(1.75, -.5, .2, 2)
                    with patch.object(cmds, "scaleKey", side_effect=AssertionError("cmds scale")):
                        fast.scaleKeys(1.75, -.5, .2, 2, fast=True)
                    self.assert_curves(normal, fast)

    def test_stationary_inputs_allow_value_edits_and_pivot_scaling(self):
        """入力を保つ値編集・無変更・ピボット上のキーも通常と一致する。"""
        for suffix in ("TA", "TL", "TT", "TU", "UA", "UL", "UT", "UU"):
            with self.subTest(suffix=suffix):
                normal = mlib.createNode("animCurve" + suffix)
                fast = mlib.createNode("animCurve" + suffix, fast=True)
                for x, y in ((0, 0), (1, 10)):
                    normal.setKey(x, y)
                    fast.setKey(x, y, fast=True)
                operations = (("shiftKeys", {"inputOffset": 2}),
                              ("scaleKeys", {"valueScale": .5}),
                              ("shiftKeys", {"valueOffset": 1}),
                              ("shiftKeys", {}),
                              ("scaleKeys", {}),
                              ("scaleKeys", {"inputScale": 2, "inputPivot": 2}),
                              ("scaleKeys", {"inputScale": .5, "inputPivot": 2}),
                              ("mirror", {}))
                for method, kwargs in operations:
                    getattr(normal, method)(**kwargs)
                    before = cmds.undoInfo(q=True, undoName=True)
                    with ExitStack() as stack:
                        for command in ("keyframe", "scaleKey", "setAttr", "undoInfo"):
                            stack.enter_context(patch.object(cmds, command, side_effect=AssertionError(command)))
                        self.assertIs(getattr(fast, method)(fast=True, **kwargs), fast)
                    self.assertEqual(cmds.undoInfo(q=True, undoName=True), before)
                    self.assert_curves(normal, fast)

    def test_fast_tangent_restrictions_are_checked_before_updates(self):
        """不正型・未対応の入力stepnextは値・接線・ロックを変更しない。"""
        for name in ("fixed", "global", "smooth"):
            for side in ("in", "out"):
                with self.subTest(tangent=name, side=side):
                    curve = self.create("UU")
                    before = (curve.getKeyInputs(), curve.getKeyValues(), curve.getTangent(1))
                    flags = {side + "TangentType": name}
                    for position in (.25, 4):
                        with self.assertRaises(RuntimeError):
                            curve.setKey(position, 99, **flags)
                        with self.assertRaises(ValueError):
                            curve.setKey(position, 99, fast=True, **flags)
                    if name != "fixed":
                        with self.assertRaises(RuntimeError):
                            curve.setTangent(1, **flags)
                        with self.assertRaises(ValueError):
                            curve.setTangent(1, fast=True, lock=False, **flags)
                    self.assertEqual((curve.getKeyInputs(), curve.getKeyValues(), curve.getTangent(1)), before)
        for method, args, flags in (("setKey", (4, 99), {}),
                                    ("setTangent", (1,), {"lock": False, "weightedTangents": True})):
            curve = self.create("UU")
            before = (curve.getKeyInputs(), curve.getKeyValues(), curve.getTangent(1))
            with self.assertRaises(NotImplementedError):
                getattr(curve, method)(*args, inTangentType="stepnext", fast=True, **flags)
            self.assertEqual((curve.getKeyInputs(), curve.getKeyValues(), curve.getTangent(1)), before)
        for method, args in (("setKey", (4, 99)), ("setTangent", (1,))):
            normal, fast = self.create("UU"), self.create("UU")
            getattr(normal, method)(*args, inTangentType="step")
            getattr(fast, method)(*args, inTangentType="step", fast=True)
            self.assert_curves(normal, fast)

    def test_plug_key_tangents_validate_before_curve_creation(self):
        """Plugの接線既定はMayaに従い、不正指定ではカーブも接続も作らない。"""
        for name in ("fixed", "global", "smooth", "stepnext"):
            plug = mlib.createNode("transform").getPlug("translateX")
            before = set(cmds.ls(type="animCurve") or [])
            with self.assertRaises((ValueError, NotImplementedError)):
                plug.setKey(time=1, value=2, inTangentType=name, fast=True)
            self.assertIsNone(plug.getSource())
            self.assertEqual(set(cmds.ls(type="animCurve") or []), before)
        normal = mlib.createNode("transform").getPlug("translateX")
        fast = mlib.createNode("transform").getPlug("translateX")
        normal.setKey(time=1, value=2)
        with patch.object(cmds, "setKeyframe", side_effect=AssertionError("cmds key")):
            fast.setKey(time=1, value=2, fast=True)
        self.assert_curves(normal.getSource().getNode(), fast.getSource().getNode())

    def test_unsupported_or_locked_fast_edit_has_no_partial_change(self):
        """未対応の入力反転・不正値・ロックはキーを変更する前に拒否する。"""
        curve = self.create("TT")
        before = (curve.getKeyInputs(), curve.getKeyValues())
        for call in (lambda: curve.scaleKeys(-1, fast=True),
                     lambda: curve.scaleKeys(0, fast=True),
                     lambda: curve.shiftKeys(float("inf"), fast=True),
                     lambda: curve.setTangent(1, inWeight=-1, fast=True)):
            with self.assertRaises((NotImplementedError, ValueError)):
                call()
            self.assertEqual((curve.getKeyInputs(), curve.getKeyValues()), before)
        curve.getPlug("ktv").setLocked(True)
        with self.assertRaises(RuntimeError):
            curve.setKey(.25, 10, fast=True)
        self.assertEqual((curve.getKeyInputs(), curve.getKeyValues()), before)


if __name__ == "__main__":
    unittest.main()
