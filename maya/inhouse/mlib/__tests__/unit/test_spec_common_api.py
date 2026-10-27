"""mlib.common の公開APIの約束を固定する仕様テスト(担当D)。

units・CurveFit(Mayaの NURBS 評価との突き合わせ)・PluginPackage・undo・Deferred・
ScriptJob/ScriptJobs(バッチ時の拒否)・Namespace・Selection・references・Cycle を対象にする。
シーン・選択・UI単位・Undo設定・名前空間は各テストの後に元へ戻す。
"""

import math
import sys
import unittest
import uuid
from unittest import mock

import maya.api.OpenMaya as om2
import maya.cmds as cmds

import mlib
mlib.reload()
from mlib.common import LOADED
from mlib.common import MISSING
from mlib.common import SKIPPED
from mlib.common import CurveFit
from mlib.common import Cycle
from mlib.common import Deferred
from mlib.common import DrivenKey
from mlib.common import Namespace
from mlib.common import Plugin
from mlib.common import PluginPackage
from mlib.common import ScriptJob
from mlib.common import ScriptJobs
from mlib.common import Selection
from mlib.common import Version
from mlib.common import references
from mlib.common import undo
from mlib.common import units
from mlib.components import Vertex
from mlib.nodes import Node
from mlib.plugs import Plug


def _maya_year():
    """現在のMayaの年版を cmds から独立に求める。

    Returns:
        int: 2027などの年版。
    """
    return int(str(cmds.about(version=True)).split(".")[0])


class UnitsSpecTest(unittest.TestCase):
    """units の変換がUI単位に従い、シーン設定を変えないことを固定する。"""

    def setUp(self):
        """開始時のUI単位を保存する。"""
        self.linear = cmds.currentUnit(query=True, linear=True)
        self.angle = cmds.currentUnit(query=True, angle=True)
        self.time = cmds.currentUnit(query=True, time=True)

    def tearDown(self):
        """UI単位を開始時へ戻す。"""
        cmds.currentUnit(linear=self.linear, angle=self.angle, time=self.time)

    def test_distance_to_and_from_ui_follow_linear_unit(self):
        """distanceToUi/FromUiは現在の距離単位で換算し、互いに逆変換になる。"""
        cases = {"cm": 1.0, "mm": 10.0, "m": 0.01, "in": 1 / 2.54, "ft": 1 / 30.48, "km": 1e-5}
        for unit, factor in cases.items():
            cmds.currentUnit(linear=unit)
            self.assertAlmostEqual(units.distanceToUi(12.5), 12.5 * factor, places=9, msg=unit)
            self.assertAlmostEqual(units.distanceFromUi(12.5 * factor), 12.5, places=9, msg=unit)
            self.assertAlmostEqual(units.distanceFromUi(units.distanceToUi(-3.25)), -3.25, places=9)
            self.assertIsInstance(units.distanceToUi(1), float)
            self.assertEqual(cmds.currentUnit(query=True, linear=True), unit)

    def test_angle_to_and_from_ui_follow_angle_unit(self):
        """angleToUi/FromUiは度とradの設定に従い、互いに逆変換になる。"""
        cmds.currentUnit(angle="deg")
        self.assertAlmostEqual(units.angleToUi(1.0), 57.29577951308232, places=9)
        self.assertAlmostEqual(units.angleFromUi(180.0), 3.141592653589793, places=12)
        cmds.currentUnit(angle="rad")
        self.assertAlmostEqual(units.angleToUi(1.25), 1.25, places=12)
        self.assertAlmostEqual(units.angleFromUi(-0.5), -0.5, places=12)
        self.assertEqual(cmds.currentUnit(query=True, angle=True), "rad")
        cmds.currentUnit(angle="deg")
        self.assertAlmostEqual(units.angleFromUi(units.angleToUi(2.0)), 2.0, places=12)

    def test_seconds_per_frame_follows_time_unit(self):
        """secondsPerFrameは現在の時間単位の1フレームの秒数を返す。"""
        cases = {"film": 1 / 24.0, "ntsc": 1 / 30.0, "pal": 1 / 25.0, "game": 1 / 15.0,
                 "ntscf": 1 / 60.0, "120fps": 1 / 120.0}
        for unit, seconds in cases.items():
            cmds.currentUnit(time=unit)
            self.assertAlmostEqual(units.secondsPerFrame(), seconds, places=12, msg=unit)
            self.assertEqual(cmds.currentUnit(query=True, time=True), unit)

    def test_matches_om2_independently(self):
        """om2の単位クラスで独立に求めた値と一致する。"""
        cmds.currentUnit(linear="ft", angle="deg")
        self.assertAlmostEqual(units.distanceToUi(100.0),
                               om2.MDistance(100.0, om2.MDistance.kCentimeters).asUnits(om2.MDistance.kFeet))
        self.assertAlmostEqual(units.angleToUi(0.3),
                               om2.MAngle(0.3, om2.MAngle.kRadians).asUnits(om2.MAngle.kDegrees))

    def test_convert_distance_names_and_defaults(self):
        """convertDistanceは短名・長名を受け、Noneは現在の距離単位を使う。"""
        cmds.currentUnit(linear="cm")
        self.assertAlmostEqual(units.convertDistance(1.0, "m", "cm"), 100.0)
        self.assertAlmostEqual(units.convertDistance(1.0, "meter", "millimeter"), 1000.0)
        self.assertAlmostEqual(units.convertDistance(1.0, "inch", "cm"), 2.54)
        self.assertAlmostEqual(units.convertDistance(3.0, "yd", "ft"), 9.0)
        self.assertAlmostEqual(units.convertDistance(1.0, "mi", "km"), 1.609344)
        self.assertAlmostEqual(units.convertDistance(5.0, "mm"), 0.5)
        self.assertAlmostEqual(units.convertDistance(5.0, toUnit="mm"), 50.0)
        self.assertAlmostEqual(units.convertDistance(7.0), 7.0)
        cmds.currentUnit(linear="m")
        self.assertAlmostEqual(units.convertDistance(1.0, "cm"), 0.01)
        self.assertEqual(cmds.currentUnit(query=True, linear=True), "m")

    def test_convert_distance_rejects_unknown_units(self):
        """単位名が文字列以外ならTypeError、未対応ならValueError(大文字・Maya表記揺れも未対応)。"""
        with self.assertRaises(TypeError):
            units.convertDistance(1.0, 1)
        with self.assertRaises(TypeError):
            units.convertDistance(1.0, toUnit=om2.MDistance.kMeters)
        for name in ("CM", "meters", "", "pt"):
            with self.assertRaises(ValueError, msg=name):
                units.convertDistance(1.0, name)


class CurveFitMayaSpecTest(unittest.TestCase):
    """CurveFit.basisがMayaの3次clamped一様ノットのNURBS評価と一致することを確かめる。"""

    def setUp(self):
        """作成したノードを記録する一時名前空間を作る。"""
        self.ns = "mlibSpecDCurve_" + uuid.uuid4().hex[:8]
        cmds.namespace(add=self.ns)

    def tearDown(self):
        """一時名前空間を中身ごと削除する。"""
        cmds.namespace(removeNamespace=self.ns, deleteNamespaceContent=True)

    def test_basis_matches_maya_curve_evaluation(self):
        """CVを基底重みで混ぜた点は、MFnNurbsCurve.getPointAtParamと一致する。"""
        controls = [(0, 0, 0), (1, 2, 0), (3, -1, 1), (4, 3, 2), (6, 0, -1), (7, 1, 0), (9, 2, 3)]
        fn = self._maya_curve(controls)
        self.assertAlmostEqual(fn.knotDomain[0], 0.0)
        self.assertAlmostEqual(fn.knotDomain[1], 1.0)
        for step in range(21):
            parameter = step / 20.0
            weights = CurveFit.basis(len(controls), parameter)
            point = fn.getPointAtParam(parameter, om2.MSpace.kObject)
            for axis in range(3):
                mixed = sum(w * c[axis] for w, c in zip(weights, controls))
                self.assertAlmostEqual(mixed, point[axis], places=6, msg=(parameter, axis))

    def test_fit_controls_reproduce_samples_on_maya_curve(self):
        """fitしたCVでMayaカーブを作ると、直線上の等間隔サンプルを通る。"""
        points = [(i * 1.0, i * 0.5, 0.0) for i in range(16)]
        controls = CurveFit.fit(points, 5)
        fn = self._maya_curve([tuple(row) for row in controls])
        for point in points:
            closest = fn.closestPoint(om2.MPoint(*point), space=om2.MSpace.kObject)[0]
            self.assertLess(closest.distanceTo(om2.MPoint(*point)), 1e-4)

    def _maya_curve(self, controls):
        """同じノット列を持つMayaの3次カーブを作り、関数セットを返す。"""
        count = len(controls)
        spans = count - 3
        knots = [0.0] * 3 + [i / float(spans) for i in range(1, spans)] + [1.0] * 3
        name = cmds.curve(degree=3, point=controls, knot=knots, name=self.ns + ":curve")
        shape = cmds.listRelatives(name, shapes=True, fullPath=True)[0]
        return om2.MFnNurbsCurve(om2.MSelectionList().add(shape).getDagPath(0))


class PluginPackageSpecTest(unittest.TestCase):
    """PluginPackageのMaya版判定・生成時検証・ロードしない経路を固定する。"""

    missing_plugin = "mlibSpecDMissingPlugin"

    def test_is_maya_supported_compares_year(self):
        """minimumMayaが未指定または現在の年以下ならTrue、より新しい年ならFalse。"""
        year = _maya_year()
        self.assertTrue(PluginPackage("Product", [self.missing_plugin]).isMayaSupported())
        self.assertTrue(PluginPackage("Product", [self.missing_plugin], minimumMaya=year).isMayaSupported())
        self.assertTrue(PluginPackage("Product", [self.missing_plugin], minimumMaya=year - 1).isMayaSupported())
        self.assertFalse(PluginPackage("Product", [self.missing_plugin], minimumMaya=year + 1).isMayaSupported())
        # minimumMayaはint()で正規化して保持する。
        package = PluginPackage("Product", [self.missing_plugin], minimumMaya=str(year + 1))
        self.assertEqual(package.minimumMaya, year + 1)
        self.assertFalse(package.isMayaSupported())

    def test_unsupported_maya_skips_without_loading_or_notifying(self):
        """対象外のMayaではプラグインを照会・ロードせずSKIPPEDを返し、通知もしない。"""
        notified = []
        package = PluginPackage("Product", [self.missing_plugin], minimumMaya=_maya_year() + 1)
        with mock.patch.object(PluginPackage, "loadPlugins", side_effect=AssertionError("loaded")):
            self.assertEqual(package.tryLoad(dialog=notified.append, warn=False), SKIPPED)
        self.assertEqual(notified, [])

    def test_constructor_validation(self):
        """名前・プラグイン・最小版・最小Mayaの不正はValueError/TypeError。"""
        with self.assertRaises(ValueError):
            PluginPackage("", [self.missing_plugin])
        with self.assertRaises(TypeError):
            PluginPackage(None, [self.missing_plugin])
        with self.assertRaises(ValueError):
            PluginPackage("Product")
        with self.assertRaises(ValueError):
            PluginPackage("Product", [""])
        with self.assertRaises(TypeError):
            PluginPackage("Product", [5])
        with self.assertRaises(TypeError):
            PluginPackage("Product", 5)
        with self.assertRaises(ValueError):
            PluginPackage("Product", [self.missing_plugin], minimumVersion="beta")
        with self.assertRaises(TypeError):
            PluginPackage("Product", [self.missing_plugin], minimumMaya=[2025])

    def test_properties_do_not_query_maya_and_are_copies(self):
        """プロパティは保持値を返し、pluginsは独立したlist。"""
        package = PluginPackage("Product", ["a", "b"], minimumVersion="3.1", minimumMaya=2024)
        self.assertEqual(package.name, "Product")
        plugins = package.plugins
        self.assertEqual([plugin.name for plugin in plugins], ["a", "b"])
        plugins.append("c")
        self.assertEqual(len(package.plugins), 2)
        self.assertIsNone(package.module)
        self.assertEqual(package.minimumVersion, Version("3.1"))
        self.assertEqual(package.minimumMaya, 2024)
        self.assertIn("Product", repr(package))

    def test_missing_plugin_without_minimum_version_is_missing(self):
        """最小版なしで全プラグインのロードに失敗すればMISSINGとし、通知文を一度渡す。"""
        notified = []
        package = PluginPackage("Product", [self.missing_plugin])
        self.assertEqual(package.loadPlugins(), [self.missing_plugin])
        self.assertEqual(package.tryLoad(dialog=notified.append, warn=False), MISSING)
        self.assertEqual(len(notified), 1)
        self.assertIn("Product", notified[0])
        self.assertIn("Maya {}".format(_maya_year()), notified[0])

    def test_missing_minimum_version_skips_loading(self):
        """最小版を満たさない場合はロードせずMISSING。dialog=Falseは通知しない。"""
        package = PluginPackage("Product", [self.missing_plugin], minimumVersion="1.0")
        self.assertFalse(package.isInstalled())
        self.assertIsNone(package.getInstalledVersion())
        self.assertIsNone(package.getLoadedVersion())
        with mock.patch.object(PluginPackage, "loadPlugins", side_effect=AssertionError("loaded")):
            self.assertEqual(package.tryLoad(dialog=False, warn=False), MISSING)

    def test_show_dialog_does_nothing_in_batch(self):
        """バッチ・スタンドアロンではshowDialogはダイアログを出さずNoneを返す。"""
        if not cmds.about(batch=True):
            self.skipTest("UIを開くため、GUIでは確認しない")
        with mock.patch.object(cmds, "confirmDialog", side_effect=AssertionError("dialog")):
            self.assertIsNone(PluginPackage.showDialog("message"))

    def test_load_real_plugin_reports_loaded(self):
        """標準同梱プラグインはLOADEDとなり、版は取得できる。"""
        name = "matrixNodes"
        was_loaded = cmds.pluginInfo(name, query=True, loaded=True)
        try:
            package = PluginPackage("Matrix", [name])
            # 未ロードのプラグインは登録されていない場合があるため、ロード前のisInstalledは問わない。
            self.assertEqual(package.tryLoad(dialog=False, warn=False), LOADED)
            self.assertTrue(cmds.pluginInfo(name, query=True, loaded=True))
            self.assertIsNotNone(package.getLoadedVersion())
            self.assertTrue(package.isInstalled())
        finally:
            if not was_loaded and cmds.pluginInfo(name, query=True, loaded=True):
                cmds.unloadPlugin(name)


class PluginSpecTest(unittest.TestCase):
    """Pluginの値としての扱いとensureNodePluginの対象を固定する。"""

    def test_value_semantics_and_unknown_plugin(self):
        """名前で比較・ハッシュし、未知の名前は例外なしでFalse/Noneを返す。"""
        self.assertEqual(Plugin("a"), Plugin("a"))
        self.assertEqual(hash(Plugin("a")), hash(Plugin("a")))
        self.assertNotEqual(Plugin("a"), "a")
        self.assertEqual(str(Plugin("a")), "a")
        self.assertEqual(repr(Plugin("a")), "Plugin('a')")
        unknown = Plugin("mlibSpecDMissingPlugin")
        self.assertFalse(unknown.isRegistered())
        self.assertFalse(unknown.isLoaded())
        self.assertIsNone(unknown.getPath())
        self.assertIsNone(unknown.getVersion())
        self.assertFalse(unknown.isVersionAtLeast("1.0"))
        with self.assertRaises(ValueError):
            unknown.isVersionAtLeast("beta")
        with self.assertRaises(ValueError):
            Plugin("")
        for name in (None, 5):
            with self.assertRaises(TypeError):
                Plugin(name)
        with self.assertRaises(TypeError):
            unknown.unload(force=True, f=True)

    def test_ensure_node_plugin_targets_only_humanik(self):
        """HumanIKのノード型だけmayaHIKのロードを確かめ、他の型では何もしない。"""
        with mock.patch.object(Plugin, "ensureLoaded") as ensure:
            self.assertIsNone(Plugin.ensureNodePlugin("transform"))
            ensure.assert_not_called()
            Plugin.ensureNodePlugin("HIKCharacterNode")
            ensure.assert_called_once_with()

    def test_loaded_lists_plugins_in_maya_order(self):
        """loaded()はMayaが返す順のPluginのlist。"""
        names = cmds.pluginInfo(query=True, listPlugins=True) or []
        self.assertEqual([plugin.name for plugin in Plugin.loaded()], names)


class DrivenKeySpecTest(unittest.TestCase):
    """DrivenKeyの内部単位・検証・Undoを固定する。"""

    def setUp(self):
        """一時名前空間にドライバーと駆動先を作り、UI単位を保存する。"""
        self.linear = cmds.currentUnit(query=True, linear=True)
        self.angle = cmds.currentUnit(query=True, angle=True)
        self.undo_state = cmds.undoInfo(query=True, state=True)
        cmds.undoInfo(stateWithoutFlush=True)
        self.ns = "mlibSpecDDriven_" + uuid.uuid4().hex[:8]
        cmds.namespace(add=self.ns)
        self.driver = cmds.createNode("transform", name=self.ns + ":driver")
        self.driven = cmds.createNode("transform", name=self.ns + ":driven")

    def tearDown(self):
        """一時名前空間を削除し、UI単位とUndo設定を戻す。"""
        cmds.currentUnit(linear=self.linear, angle=self.angle)
        cmds.namespace(removeNamespace=self.ns, deleteNamespaceContent=True)
        cmds.undoInfo(state=self.undo_state)

    def test_set_key_uses_internal_units(self):
        """setKeyの値はrad・cmの内部単位で、UI単位がdeg・mmでも同じ関係になる。"""
        cmds.currentUnit(linear="mm", angle="deg")
        key = DrivenKey(self.driver + ".rx", self.driven + ".tx")
        self.assertFalse(key.exists())
        self.assertIs(key.setKey(0.0, 0.0), key)
        key.setKey(math.pi / 2, 1.0)
        self.assertTrue(key.exists())
        cmds.setAttr(self.driver + ".rx", 90.0)
        node = om2.MFnDependencyNode(om2.MSelectionList().add(self.driven).getDependNode(0))
        self.assertAlmostEqual(node.findPlug("translateX", False).asDouble(), 1.0, places=6)
        self.assertAlmostEqual(cmds.getAttr(self.driven + ".tx"), 10.0, places=4)
        found = DrivenKey.find(self.driven + ".tx")
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].getDriverPlug().getFullName(), key.getDriverPlug().getFullName())
        self.assertEqual(found[0].getDrivenPlug().getFullName(), key.getDrivenPlug().getFullName())
        self.assertEqual(len(key.getCurves()), 1)

    def test_one_undo_per_key(self):
        """setKeyは1回のUndoで戻る。"""
        key = DrivenKey(self.driver + ".tx", self.driven + ".ty")
        key.setKey(0.0, 0.0)
        cmds.undo()
        self.assertFalse(key.exists())

    def test_validation(self):
        """同じアトリビュート・非数値はValueError、型不正はTypeError、存在しないはRuntimeError。"""
        with self.assertRaises(ValueError):
            DrivenKey(self.driver + ".tx", self.driver + ".translateX")
        with self.assertRaises(ValueError):
            DrivenKey(self.driver + ".translate", self.driven + ".tx")
        with self.assertRaises(TypeError):
            DrivenKey(5, self.driven + ".tx")
        with self.assertRaises(RuntimeError):
            DrivenKey(self.driver + ".noSuchAttribute", self.driven + ".tx")
        key = DrivenKey(self.driver + ".tx", self.driven + ".tx")
        for value in (float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                key.setKey(value, 0.0)
        with self.assertRaises(ValueError):
            key.setKey("abc", 0.0)
        with self.assertRaises(TypeError):
            key.setKey(None, 0.0)
        self.assertFalse(key.exists())
        cmds.delete(self.driver)
        with self.assertRaises(RuntimeError):
            key.getDriverPlug()


class UndoAndDeferredSpecTest(unittest.TestCase):
    """undo.isEnabledとDeferred.callの委譲を固定する。"""

    def setUp(self):
        """開始時のUndo設定を保存する。"""
        self.state = cmds.undoInfo(query=True, state=True)

    def tearDown(self):
        """Undo設定を戻す。"""
        cmds.undoInfo(state=self.state)

    def test_is_enabled_follows_undo_state_without_changing_it(self):
        """isEnabledはundoInfoのstateをboolで返し、設定を変えない。"""
        cmds.undoInfo(stateWithoutFlush=True)
        self.assertIs(undo.isEnabled(), True)
        cmds.undoInfo(state=False)
        self.assertIs(undo.isEnabled(), False)
        self.assertFalse(cmds.undoInfo(query=True, state=True))

    def test_deferred_call_passes_arguments_to_execute_deferred(self):
        """callはcallbackと引数をそのままexecuteDeferredへ渡し、戻り値はNone。"""
        from maya import utils

        def callback(*args, **kwargs):
            """何もしない。"""

        with mock.patch.object(utils, "executeDeferred") as deferred:
            self.assertIsNone(Deferred.call(callback, 1, key="value"))
        deferred.assert_called_once_with(callback, 1, key="value")

    def test_deferred_call_rejects_non_callable(self):
        """コード文字列などcallableでない値はTypeError。"""
        from maya import utils

        with mock.patch.object(utils, "executeDeferred") as deferred:
            for value in ("print(1)", None, 5):
                with self.assertRaises(TypeError):
                    Deferred.call(value)
        deferred.assert_not_called()


class ScriptJobSpecTest(unittest.TestCase):
    """ScriptJobの入力検証と、バッチ時に登録しないことを固定する。"""

    def test_requires_exactly_one_of_event_and_attribute(self):
        """eventとattributeは片方だけ。両方・どちらもなしはValueError。"""
        with self.assertRaises(ValueError):
            ScriptJob(callback=lambda: None)
        with self.assertRaises(ValueError):
            ScriptJob(event="SelectionChanged", attribute="persp.tx", callback=lambda: None)

    def test_rejects_non_callable(self):
        """callbackが呼び出せない場合はTypeError(バッチ判定より前)。"""
        with self.assertRaises(TypeError):
            ScriptJob(event="SelectionChanged", callback="print(1)")

    def test_batch_session_is_rejected(self):
        """バッチ実行中はRuntimeErrorで、scriptJobを登録しない。"""
        if not cmds.about(batch=True):
            self.skipTest("GUIではscriptJobを登録できるため対象外")
        before = len(cmds.scriptJob(listJobs=True) or [])
        with self.assertRaises(RuntimeError):
            ScriptJob(event="SelectionChanged", callback=lambda: None)
        self.assertEqual(len(cmds.scriptJob(listJobs=True) or []), before)

    def test_script_jobs_group_empty_and_failed_add(self):
        """空のグループはexists()がFalse、登録失敗のキーは保持しない。"""
        group = ScriptJobs()
        self.assertFalse(group.exists())
        self.assertIsNone(group.stop())
        if cmds.about(batch=True):
            with self.assertRaises(RuntimeError):
                group.add("key", event="SelectionChanged", callback=lambda: None)
            self.assertFalse(group.exists())

    def test_script_jobs_temporary_cannot_nest(self):
        """同じインスタンスでtemporaryを入れ子にするとRuntimeError。外側は正常に終わる。"""
        group = ScriptJobs()
        with group.temporary() as active:
            self.assertIs(active, group)
            with self.assertRaises(RuntimeError):
                with group.temporary():
                    pass
        with group.temporary():
            pass


class NamespaceSpecTest(unittest.TestCase):
    """Namespaceの正規化・作成・変更・削除とUndoを固定する。"""

    def setUp(self):
        """一意な親名前空間名を決める。"""
        self.root = ":mlibSpecDNs_" + uuid.uuid4().hex[:8]
        self.current = cmds.namespaceInfo(currentNamespace=True, absoluteName=True)

    def tearDown(self):
        """作成した名前空間を中身ごと削除し、カレントを戻す。"""
        cmds.namespace(set=":")
        names = cmds.namespaceInfo(":", listOnlyNamespaces=True, recurse=True, absoluteName=True) or []
        for name in sorted(names, key=lambda item: item.count(":"), reverse=True):
            if name.startswith(self.root) and cmds.namespace(exists=name):
                cmds.namespace(removeNamespace=name, deleteNamespaceContent=True)
        if cmds.namespace(exists=self.current):
            cmds.namespace(set=self.current)

    def test_normalization_and_value_semantics(self):
        """/は:と同じ区切り、両端の:は除いて先頭に:を付ける。比較は保持名で行う。"""
        self.assertEqual(Namespace("a/b").name, ":a:b")
        self.assertEqual(Namespace("::a:b::").name, ":a:b")
        self.assertEqual(Namespace(":::").name, ":")
        self.assertEqual(Namespace().name, ":")
        self.assertEqual(Namespace(Namespace("x")).name, ":x")
        self.assertEqual(str(Namespace("x")), ":x")
        self.assertEqual(repr(Namespace("x")), "Namespace(':x')")
        self.assertEqual(Namespace("x"), Namespace(":x"))
        self.assertEqual(hash(Namespace("x")), hash(Namespace(":x")))
        self.assertNotEqual(Namespace("x"), ":x")
        with self.assertRaises(ValueError):
            Namespace("")
        for value in (None, 5):
            with self.assertRaises(TypeError):
                Namespace(value)

    def test_parent_is_computed_from_name(self):
        """getParentは名前から求め、ルートではNone。存在は確認しない。"""
        self.assertIsNone(Namespace(":").getParent())
        self.assertEqual(Namespace(":a:b:c").getParent(), Namespace(":a:b"))
        self.assertEqual(Namespace(":a").getParent(), Namespace(":"))
        missing = Namespace(self.root + ":nothing")
        self.assertFalse(missing.exists())
        self.assertEqual(missing.getChildren(), [])
        self.assertEqual(missing.getNodes(), [])

    def test_create_recursive_returns_existing_and_one_undo(self):
        """多段名は親から作り、既存なら同じ名前を返す。1回のUndoで全て戻る。"""
        created = Namespace.create(self.root + ":a:b")
        self.assertEqual(created.name, self.root + ":a:b")
        self.assertTrue(cmds.namespace(exists=self.root + ":a:b"))
        self.assertEqual(Namespace.getCurrent().name, self.current)
        self.assertEqual(Namespace.create(self.root + ":a:b"), created)
        cmds.undo()  # 既存を返しただけの2回目
        cmds.undo()
        self.assertFalse(cmds.namespace(exists=self.root))

    def test_create_relative_under_parent(self):
        """相対名はparent配下に作り、絶対名はparentを無視する。"""
        parent = Namespace.create(self.root)
        child = Namespace.create("child", parent=parent)
        self.assertEqual(child.name, self.root + ":child")
        absolute = Namespace.create(self.root + ":other", parent=child)
        self.assertEqual(absolute.name, self.root + ":other")
        self.assertIn(child, parent.getChildren())
        # ルートは常に存在するため、作成せずにルートの参照を返す。
        self.assertEqual(Namespace.create(":"), Namespace(":"))

    def test_set_current_and_as_current_restore(self):
        """存在しない名前空間のsetCurrentはRuntimeError。asCurrentは例外時も戻す。"""
        with self.assertRaises(RuntimeError):
            Namespace(self.root + ":missing").setCurrent()
        target = Namespace.create(self.root)
        with self.assertRaises(KeyError):
            with target.asCurrent() as active:
                self.assertIs(active, target)
                self.assertEqual(Namespace.getCurrent(), target)
                raise KeyError("boom")
        self.assertEqual(Namespace.getCurrent().name, self.current)

    def test_rename_move_and_remove(self):
        """renameは親を維持し、moveは既存の親へ移し、removeは内容を移動先へ移す。"""
        source = Namespace.create(self.root + ":src")
        node = cmds.createNode("transform", name=source.name + ":item")
        self.assertIs(source.rename("dst"), source)
        self.assertEqual(source.name, self.root + ":dst")
        self.assertTrue(cmds.objExists(self.root + ":dst:item"))
        self.assertFalse(cmds.namespace(exists=self.root + ":src"))
        holder = Namespace.create(self.root + ":holder")
        source.move(holder)
        self.assertEqual(source.name, self.root + ":holder:dst")
        with self.assertRaises(RuntimeError):
            source.move(self.root + ":missingParent")
        destination = source.remove(self.root)
        self.assertEqual(destination, Namespace(self.root))
        self.assertTrue(cmds.objExists(self.root + ":item"))
        self.assertFalse(cmds.namespace(exists=self.root + ":holder:dst"))
        del node

    def test_root_operations_and_conflicts_are_rejected(self):
        """ルートの変更はValueError、既存の移動先や長短名の同時指定は拒否する。"""
        root = Namespace(":")
        with self.assertRaises(ValueError):
            root.rename("x")
        with self.assertRaises(ValueError):
            root.move(":")
        with self.assertRaises(ValueError):
            root.remove()
        first = Namespace.create(self.root + ":first")
        Namespace.create(self.root + ":second")
        with self.assertRaises(RuntimeError):
            first.rename("second")
        with self.assertRaises(TypeError):
            first.remove(":", dst=":")
        with self.assertRaises(RuntimeError):
            first.remove(self.root + ":missing")
        self.assertTrue(first.exists())


class SelectionSpecTest(unittest.TestCase):
    """Selectionの展開・重複除去・選択反映・Undoを固定する。"""

    def setUp(self):
        """一時名前空間に立方体とtransformを作り、選択を保存する。"""
        self.ns = "mlibSpecDSel_" + uuid.uuid4().hex[:8]
        cmds.namespace(add=self.ns)
        self.mesh = cmds.polyCube(name=self.ns + ":mesh", constructionHistory=False)[0]
        self.node = cmds.createNode("transform", name=self.ns + ":node")
        self.previous = cmds.ls(selection=True, long=True)

    def tearDown(self):
        """選択を戻し、一時名前空間を削除する。"""
        cmds.select(clear=True)
        cmds.namespace(removeNamespace=self.ns, deleteNamespaceContent=True)
        existing = [name for name in self.previous if cmds.objExists(name)]
        if existing:
            cmds.select(existing, replace=True)

    def test_empty_and_duplicates(self):
        """空の集合は長さ0。同じ完全名は最初の1件だけを保持する。"""
        self.assertEqual(len(Selection()), 0)
        selection = Selection([self.node, Node(self.node), "|" + self.node])
        self.assertEqual(len(selection), 1)
        self.assertIsInstance(selection[0], Node)

    def test_ranges_expand_and_slices_are_tuples(self):
        """範囲名は単体コンポーネントへ展開し、sliceはtuple、itemsは独立したlist。"""
        selection = Selection(self.mesh + ".vtx[2:4]")
        self.assertEqual(len(selection), 3)
        self.assertTrue(all(isinstance(item, Vertex) for item in selection))
        self.assertEqual([item.index for item in selection], [2, 3, 4])
        self.assertIsInstance(selection[0:2], tuple)
        items = selection.items
        items.clear()
        self.assertEqual(len(selection), 3)
        self.assertIsInstance(selection[-1], Vertex)

    def test_mixed_items_and_owner(self):
        """ノード・アトリビュート・コンポーネントを保持順で持ち、所有ノードは重複を除く。"""
        selection = Selection([self.node, self.node + ".tx", self.mesh + ".f[0]", self.mesh + ".vtx[0]"])
        self.assertEqual(len(selection), 4)
        self.assertIsInstance(selection[1], Plug)
        self.assertEqual(len(selection.getPlugs()), 1)
        self.assertEqual(len(selection.getComponents()), 2)
        owners = [owner.getName() for owner in selection.getOwners()]
        self.assertEqual(len(owners), 2)
        self.assertEqual(len(selection.filter("plug")), 1)
        self.assertEqual(len(selection.filter("vertex")), len(selection.filter("vtx")))
        self.assertEqual(len(selection.filter("transform")), 1)

    def test_capture_is_a_snapshot(self):
        """captureは現在選択を取得時点の順で保持し、その後の選択変更に追従しない。"""
        cmds.select(self.node, self.mesh + ".vtx[1]", replace=True)
        captured = Selection.capture()
        cmds.select(clear=True)
        self.assertEqual(len(captured), 2)
        self.assertIsInstance(captured[0], Node)
        self.assertIsInstance(captured[1], Vertex)
        captured.select()
        self.assertEqual(len(cmds.ls(selection=True, flatten=True)), 2)

    def test_unsupported_item_is_rejected(self):
        """非対応型はTypeError、存在しない名前はRuntimeError。"""
        with self.assertRaises(TypeError):
            Selection([5])
        with self.assertRaises(RuntimeError):
            Selection([self.ns + ":missing"])

    def test_select_modes_and_undo(self):
        """replace/add/removeで選択を変え、1回のUndoで直前の選択へ戻る。"""
        cmds.select(self.node, replace=True)
        Selection(self.mesh).select(mode="add")
        self.assertEqual(len(cmds.ls(selection=True)), 2)
        Selection(self.node).select(mode="remove")
        self.assertEqual(cmds.ls(selection=True), [self.mesh])
        cmds.undo()
        self.assertEqual(len(cmds.ls(selection=True)), 2)
        Selection().select()
        self.assertEqual(cmds.ls(selection=True), [])
        Selection().select(mode="add")
        self.assertEqual(cmds.ls(selection=True), [])

    def test_select_validation(self):
        """modeとmissingの不正はValueError。missing=errorは変更前に失敗する。"""
        selection = Selection([self.node])
        with self.assertRaises(ValueError):
            selection.select(mode="toggle")
        with self.assertRaises(ValueError):
            Selection().select(missing="ignore")
        cmds.select(self.mesh, replace=True)
        cmds.delete(self.node)
        with self.assertRaises(RuntimeError):
            selection.select(missing="error")
        self.assertEqual(cmds.ls(selection=True), [self.mesh])
        self.assertEqual(selection.getNodes(), [])
        self.assertEqual(len(selection), 1)


class ReferencesSpecTest(unittest.TestCase):
    """references の入力検証と一覧の型を固定する。"""

    def test_list_references_excludes_shared_node(self):
        """listReferencesはsharedReferenceNodeを含めず、Referenceのlistを返す。"""
        from mlib.nodes import Reference

        result = references.listReferences()
        self.assertIsInstance(result, list)
        self.assertTrue(all(isinstance(item, Reference) for item in result))
        self.assertNotIn("sharedReferenceNode", [item.getName() for item in result])
        top = references.listReferences(topLevelOnly=True)
        self.assertTrue(all(item.getParentReference() is None for item in top))

    def test_create_reference_rejects_invalid_path_before_maya(self):
        """空・str/Path以外のpathはMayaへ渡す前にValueError。"""
        with mock.patch.object(cmds, "file", side_effect=AssertionError("file")):
            for path in ("", None, 5):
                with self.assertRaises(ValueError):
                    references.createReference(path)


class CycleSpecTest(unittest.TestCase):
    """Cycle.findの入力検証と検出結果の型を固定する。"""

    def setUp(self):
        """一時名前空間に2ノードの循環を作る。

        Maya 2027のmayapyではaddDoubleLinear同士の循環接続で異常終了するため、transformを使う。
        """
        self.ns = "mlibSpecDCycle_" + uuid.uuid4().hex[:8]
        cmds.namespace(add=self.ns)
        self.a = cmds.createNode("transform", name=self.ns + ":a")
        self.b = cmds.createNode("transform", name=self.ns + ":b")
        cmds.connectAttr(self.a + ".translateX", self.b + ".translateX")
        cmds.connectAttr(self.b + ".translateX", self.a + ".translateX")

    def tearDown(self):
        """一時名前空間を中身ごと削除する。"""
        cmds.namespace(removeNamespace=self.ns, deleteNamespaceContent=True)

    def test_find_returns_cycles_with_plugs(self):
        """循環を含む対象からCycleのlistを返し、経路はPlugのtuple。"""
        cycles = Cycle.find([self.a], includeDag=False, seconds=5.0)
        self.assertIsInstance(cycles, list)
        self.assertTrue(cycles)
        for cycle in cycles:
            self.assertIsInstance(cycle.plugs, tuple)
            self.assertTrue(all(isinstance(plug, Plug) for plug in cycle.plugs))
        names = {plug.getNode().getName() for cycle in cycles for plug in cycle.plugs}
        self.assertTrue({self.a, self.b} & names)
        connections = cycles[0].getConnections()
        self.assertTrue(all(isinstance(pair, tuple) and len(pair) == 2 for pair in connections))
        self.assertEqual(cycles[0].getParents(), [])

    def test_find_validation(self):
        """時間上限が0以下・非有限、対象が空ならValueError、型が不正ならTypeError。"""
        for seconds in (0, -1, float("inf"), float("nan")):
            with self.assertRaises(ValueError):
                Cycle.find([self.a], seconds=seconds)
        with self.assertRaises(ValueError):
            Cycle.find([])
        with self.assertRaises(TypeError):
            Cycle.find([5])

    def test_manual_cycle_keeps_order(self):
        """手動指定の経路は検証せず、指定順のPlugを保持する。"""
        cycle = Cycle([self.b + ".translateX", self.a + ".translateX"])
        self.assertEqual([plug.getNode().getName() for plug in cycle.plugs], [self.b, self.a])


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
