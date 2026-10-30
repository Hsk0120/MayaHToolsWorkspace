"""mlib.decorator・mlib.util・mlib.logger の約束を固定する仕様テスト(担当D)。

decoratorは入れ子・例外時・Undo無効時のチャンクの開閉、単位・選択・表示の復元を、
utilは名前の整形・計測・ミラー引数の検証を、loggerは出力先と例外の連鎖を確かめる。
Undo設定・UI単位・選択・シーンは各テストの後に元へ戻す。
"""

import io
import logging
import sys
import unittest
import uuid
from unittest import mock

import maya.api.OpenMaya as om2
import maya.cmds as cmds

import mlib
mlib.reload()
from mlib import decorator
from mlib import logger
from mlib import util
from mlib.decorator import nativeUnits
from mlib.decorator import preservedSelection
from mlib.decorator import preservedSkinShape
from mlib.decorator import undoChunk
from mlib.decorator import undoTransaction
from mlib.decorator import viewportOff


class _SceneCase(unittest.TestCase):
    """一時名前空間とUndo設定・UI単位・選択の保存と復元を共通にする。"""

    @staticmethod
    def opened(spy):
        """mockの呼出しからopenChunkの回数を数える。Python 3.7のため call[1] でキーワードを読む。"""
        return sum(1 for call in spy.call_args_list if call[1].get("openChunk"))

    def setUp(self):
        """状態を保存し、Undoを有効にして一時名前空間を作る。"""
        self.undo_state = cmds.undoInfo(query=True, state=True)
        self.linear = cmds.currentUnit(query=True, linear=True)
        self.angle = cmds.currentUnit(query=True, angle=True)
        self.time = cmds.currentUnit(query=True, time=True)
        self.selection = cmds.ls(selection=True, long=True)
        cmds.undoInfo(stateWithoutFlush=True)
        self.ns = "mlibSpecDDeco_" + uuid.uuid4().hex[:8]
        cmds.namespace(add=self.ns)

    def tearDown(self):
        """一時名前空間を削除し、保存した状態へ戻す。"""
        cmds.undoInfo(stateWithoutFlush=True)
        cmds.namespace(removeNamespace=self.ns, deleteNamespaceContent=True)
        cmds.currentUnit(linear=self.linear, angle=self.angle, time=self.time)
        existing = [name for name in self.selection if cmds.objExists(name)]
        if existing:
            cmds.select(existing, replace=True)
        else:
            cmds.select(clear=True)
        cmds.undoInfo(state=self.undo_state)

    def name(self, leaf):
        """一時名前空間内の名前を返す。"""
        return self.ns + ":" + leaf

    def chunk_calls(self):
        """decoratorが呼ぶcmds.undoInfoを記録するmockを返す。"""
        return mock.patch.object(decorator.cmds, "undoInfo", wraps=cmds.undoInfo)


class UndoChunkSpecTest(_SceneCase):
    """undoChunkの入れ子・Undo無効時・名前・戻り値を固定する。"""

    def test_with_value_and_decorator_return(self):
        """withのasはNone、デコレーターは戻り値と関数名を保つ。"""
        with undoChunk("mlibSpecD") as value:
            self.assertIsNone(value)

        @undoChunk("mlibSpecD")
        def make(name):
            """ノードを作る。"""
            return cmds.createNode("transform", name=name)

        self.assertEqual(make(self.name("made")), self.name("made"))
        self.assertEqual(make.__name__, "make")
        cmds.undo()
        self.assertFalse(cmds.objExists(self.name("made")))

    def test_nested_chunks_open_once(self):
        """入れ子のundoChunkは外側の1チャンクだけを開き、1回のUndoで全て戻る。"""
        with self.chunk_calls() as spy:
            with undoChunk("outer"):
                cmds.createNode("transform", name=self.name("a"))
                with undoChunk("inner"):
                    cmds.createNode("transform", name=self.name("b"))
                    with undoChunk():
                        cmds.createNode("transform", name=self.name("c"))
        self.assertEqual(self.opened(spy), 1)
        cmds.undo()
        self.assertFalse(any(cmds.objExists(self.name(n)) for n in "abc"))

    def test_disabled_undo_does_not_open_chunk(self):
        """開始時にUndoが無効ならチャンクを開閉せず、入れ子でも問い合わせを繰り返さない。"""
        cmds.undoInfo(state=False)
        with self.chunk_calls() as spy:
            with undoChunk("off"):
                with undoChunk("inner"):
                    # Undo無効時のMaya 2027では名前空間付きの名前が外れる場合があるため戻り値で確かめる。
                    created = cmds.createNode("transform", name=self.name("off"))
        try:
            self.assertEqual(self.opened(spy), 0)
            self.assertEqual(sum(1 for call in spy.call_args_list if call[1].get("closeChunk")), 0)
            self.assertEqual(len(spy.call_args_list), 1)
            self.assertTrue(cmds.objExists(created))
        finally:
            if cmds.objExists(created):
                cmds.delete(created)

    def test_exception_propagates_and_keeps_changes(self):
        """例外は再送出し、先行した変更は巻き戻さない。チャンクは閉じて後の操作は別の段になる。"""
        with self.assertRaises(KeyError):
            with undoChunk("failing"):
                cmds.createNode("transform", name=self.name("kept"))
                raise KeyError("boom")
        self.assertTrue(cmds.objExists(self.name("kept")))
        cmds.createNode("transform", name=self.name("after"))
        cmds.undo()
        self.assertFalse(cmds.objExists(self.name("after")))
        self.assertTrue(cmds.objExists(self.name("kept")))
        cmds.undo()
        self.assertFalse(cmds.objExists(self.name("kept")))

    def test_recursive_decorator_calls_share_one_chunk(self):
        """再帰呼出しでも外側の1チャンクだけを開く。"""
        @undoChunk("recursive")
        def build(count):
            """countの数だけノードを作る。"""
            cmds.createNode("transform", name=self.name("r%d" % count))
            if count:
                build(count - 1)

        with self.chunk_calls() as spy:
            build(3)
        self.assertEqual(self.opened(spy), 1)
        cmds.undo()
        self.assertFalse(cmds.objExists(self.name("r0")))
        self.assertFalse(cmds.objExists(self.name("r3")))


class UndoTransactionSpecTest(_SceneCase):
    """undoTransactionの巻戻しと内側のundoChunkの扱いを固定する。"""

    def test_rolls_back_on_base_exception(self):
        """BaseExceptionでもブロック内の変更を巻き戻し、元の例外を再送出する。"""
        with self.assertRaises(KeyboardInterrupt):
            with undoTransaction("mlibSpecDTx"):
                cmds.createNode("transform", name=self.name("tx"))
                raise KeyboardInterrupt()
        self.assertFalse(cmds.objExists(self.name("tx")))

    def test_named_transaction_does_not_open_inner_chunks(self):
        """名前付きのトランザクション内のundoChunkはMayaのチャンクを入れ子に開かない。"""
        with self.chunk_calls() as spy:
            with undoTransaction("named"):
                with undoChunk("inner"):
                    cmds.createNode("transform", name=self.name("inner"))
        self.assertEqual(self.opened(spy), 1)
        cmds.undo()
        self.assertFalse(cmds.objExists(self.name("inner")))

    def test_unnamed_transaction_opens_inner_chunk(self):
        """名前を省略したトランザクションでは内側のundoChunkも従来どおり開く。"""
        with self.chunk_calls() as spy:
            with undoTransaction():
                with undoChunk("inner"):
                    cmds.createNode("transform", name=self.name("inner"))
        self.assertEqual(self.opened(spy), 2)

    def test_decorator_success_commits_one_step(self):
        """デコレーターとして正常終了した場合は1段のUndoとして残る。"""
        @undoTransaction("mlibSpecDTx")
        def make():
            """2つのノードを作る。"""
            cmds.createNode("transform", name=self.name("x1"))
            cmds.createNode("transform", name=self.name("x2"))

        make()
        self.assertTrue(cmds.objExists(self.name("x2")))
        cmds.undo()
        self.assertFalse(cmds.objExists(self.name("x1")))


class NativeUnitsSpecTest(_SceneCase):
    """nativeUnitsの切替・入れ子・時間単位・Undoへの影響を固定する。"""

    def test_nested_restore_and_time_unit_unchanged(self):
        """入れ子でも外側の終了で開始時の単位へ戻り、時間単位は変えない。"""
        cmds.currentUnit(linear="mm", angle="deg", time="ntsc")
        with nativeUnits():
            with nativeUnits():
                self.assertEqual(cmds.currentUnit(query=True, linear=True), "cm")
                self.assertEqual(cmds.currentUnit(query=True, angle=True), "rad")
            self.assertEqual(cmds.currentUnit(query=True, linear=True), "cm")
            self.assertEqual(cmds.currentUnit(query=True, time=True), "ntsc")
        self.assertEqual(cmds.currentUnit(query=True, linear=True), "mm")
        self.assertEqual(cmds.currentUnit(query=True, angle=True), "deg")
        self.assertEqual(cmds.currentUnit(query=True, time=True), "ntsc")

    def test_values_are_read_in_native_units(self):
        """ブロック内のcmdsの値はcm・radで読み書きされる。"""
        node = cmds.createNode("transform", name=self.name("units"))
        cmds.currentUnit(linear="m", angle="deg")
        cmds.setAttr(node + ".tx", 2.0)
        cmds.setAttr(node + ".rx", 90.0)
        with nativeUnits():
            self.assertAlmostEqual(cmds.getAttr(node + ".tx"), 200.0)
            self.assertAlmostEqual(cmds.getAttr(node + ".rx"), om2.MAngle(90.0, om2.MAngle.kDegrees).asRadians())

    def test_not_recorded_in_undo(self):
        """単位の切替自体はUndoへ記録しない。"""
        cmds.select(clear=True)
        marker = cmds.undoInfo(query=True, undoName=True)
        with nativeUnits():
            pass
        self.assertEqual(cmds.undoInfo(query=True, undoName=True), marker)


class PreservedSelectionSpecTest(_SceneCase):
    """preservedSelectionの復元規則を固定する。"""

    def test_component_selection_is_restored(self):
        """コンポーネント選択を含む選択を、例外時も復元する。"""
        cube = cmds.polyCube(name=self.name("cube"), constructionHistory=False)[0]
        node = cmds.createNode("transform", name=self.name("node"))
        cmds.select(cube + ".vtx[0:2]", node, replace=True)
        before = cmds.ls(selection=True, flatten=True)
        with self.assertRaises(KeyError):
            with preservedSelection():
                cmds.select(clear=True)
                raise KeyError("boom")
        self.assertEqual(cmds.ls(selection=True, flatten=True), before)

    def test_deleted_items_are_dropped(self):
        """ブロック内で削除された対象は除き、残りがなければ選択を解除する。"""
        a = cmds.createNode("transform", name=self.name("a"))
        b = cmds.createNode("transform", name=self.name("b"))
        cmds.select(a, b, replace=True)
        with preservedSelection():
            cmds.delete(a)
        self.assertEqual(cmds.ls(selection=True), [b])
        with preservedSelection():
            cmds.delete(b)
        self.assertEqual(cmds.ls(selection=True), [])


class OtherContextSpecTest(_SceneCase):
    """viewportOffとpreservedSkinShapeのバッチ・入力検証を固定する。"""

    def test_viewport_off_in_batch_touches_no_ui(self):
        """バッチではメインペインを操作せず、withとデコレーターの両方で使える。"""
        if not cmds.about(batch=True):
            self.skipTest("GUIでは表示を操作するため対象外")
        with mock.patch.object(decorator.cmds, "paneLayout", side_effect=AssertionError("ui")):
            with viewportOff() as value:
                self.assertIsNone(value)

            @viewportOff()
            def compute():
                """値を返す。"""
                return 42

            self.assertEqual(compute(), 42)
            with self.assertRaises(KeyError):
                with viewportOff():
                    raise KeyError("boom")

    def test_preserved_skin_shape_input_validation(self):
        """joint以外はTypeError、skinClusterのないjointでは空のSkinClustersを渡す。"""
        node = cmds.createNode("transform", name=self.name("notJoint"))
        with self.assertRaises(TypeError):
            with preservedSkinShape([node]):
                pass
        joint = cmds.createNode("joint", name=self.name("joint"))
        with preservedSkinShape([joint]) as skins:
            self.assertEqual(len(skins), 0)
            self.assertEqual(type(skins).__name__, "SkinClusters")


class UtilSpecTest(unittest.TestCase):
    """legalizeName・measure・mirrorArgumentsの約束を固定する。"""

    def test_public_names(self):
        """utilの公開名は3件。"""
        self.assertEqual(sorted(util.__all__), ["legalizeName", "measure", "mirrorArguments"])

    def test_legalize_name_cases(self):
        """区間ごとに不正文字の連続を一つの_へ、数字始まりへ_を付け、空区間を捨てる。"""
        cases = {
            "rig:2nd joint": "rig:_2nd_joint", "  pad  ": "pad", "": "_", ":::": "_", "   ": "_",
            ":root:a": ":root:a", "a::b": "a:b", "a--b": "a_b", "a_ b": "a__b", "a\tb": "a_b",
            "1": "_1", "日本語": "_", "a日本b": "a_b", "x.y|z": "x_y_z", "name_": "name_",
            "ns : leaf": "ns:leaf", "a!": "a_", "１a": "_a",
        }
        for value, expected in cases.items():
            self.assertEqual(util.legalizeName(value), expected, msg=repr(value))
        for value in (None, 5, b"name"):
            with self.assertRaises(TypeError):
                util.legalizeName(value)

    def test_legalized_names_are_accepted_by_maya(self):
        """整形した名前はMayaのノード名として変更されずに使える。"""
        name = util.legalizeName("2nd joint-L")
        node = cmds.createNode("transform", name=name)
        try:
            self.assertEqual(node, name)
        finally:
            cmds.delete(node)

    def test_measure(self):
        """warmup+samples回呼び、samples件の統計を秒で返す。不正な回数はValueError。"""
        calls = []
        result = util.measure(lambda: calls.append(1), samples=5, warmup=2)
        self.assertEqual(len(calls), 7)
        self.assertEqual(set(result), {"samples", "median_seconds", "min_seconds", "max_seconds"})
        self.assertEqual(result["samples"], 5)
        self.assertLessEqual(result["min_seconds"], result["median_seconds"])
        self.assertLessEqual(result["median_seconds"], result["max_seconds"])
        self.assertGreaterEqual(result["min_seconds"], 0.0)
        util.measure(lambda: None, samples=1, warmup=0)
        with self.assertRaises(TypeError):
            util.measure("not callable")
        for kwargs in (dict(samples=0), dict(samples=True), dict(samples=1.0), dict(warmup=-1), dict(warmup=None)):
            with self.assertRaises(ValueError, msg=repr(kwargs)):
                util.measure(lambda: None, **kwargs)

    def test_mirror_arguments(self):
        """軸は反転する軸(x/y/z、0/1/2)かミラー面(YZ/XZ/XY)、中心は有限な3成分。戻り値は番号1つと中心のtuple。"""
        self.assertEqual(util.mirrorArguments("x", (0, 0, 0)), ((0,), (0.0, 0.0, 0.0)))
        self.assertEqual(util.mirrorArguments("YZ", (0, 0, 0)), ((0,), (0.0, 0.0, 0.0)))
        self.assertEqual(util.mirrorArguments("ZX", [1, 2, 3]), ((1,), (1.0, 2.0, 3.0)))
        self.assertEqual(util.mirrorArguments(1, iter((1, 2, 3))), ((1,), (1.0, 2.0, 3.0)))
        for axis in ("", "xx", "w", "xyz", "xw", 3, -1):
            with self.assertRaises(ValueError, msg=repr(axis)):
                util.mirrorArguments(axis, (0, 0, 0))
        for axis in (True, None, 1.0):
            with self.assertRaises(TypeError, msg=repr(axis)):
                util.mirrorArguments(axis, (0, 0, 0))
        for pivot in ((0, 0), (0, 0, 0, 0), (float("nan"), 0, 0), ("a", 0, 0), 5):
            with self.assertRaises(ValueError, msg=repr(pivot)):
                util.mirrorArguments("x", pivot)


class LoggerSpecTest(unittest.TestCase):
    """loggerの出力先と例外の連鎖を固定する。"""

    def setUp(self):
        """記録用のハンドラを共有ロガーへ追加する。"""
        self.records = []
        handler = logging.Handler()
        handler.emit = self.records.append
        self.handler = handler
        logger.getLogger().addHandler(handler)

    def tearDown(self):
        """記録用のハンドラを外す。"""
        logger.getLogger().removeHandler(self.handler)

    def test_shared_logger_configuration(self):
        """共有ロガーはパッケージ名・DEBUG・伝播なしで、MayaHandlerは1つだけ。"""
        first = logger.getLogger()
        self.assertIs(logger.getLogger(), first)
        self.assertEqual(first.name, "mlib")
        self.assertEqual(first.level, logging.DEBUG)
        self.assertFalse(first.propagate)
        self.assertEqual(sum(isinstance(h, logger.MayaHandler) for h in first.handlers), 1)

    def test_levels_and_format_arguments(self):
        """各関数は対応するレベルで記録し、書式引数を標準loggingと同じく適用する。"""
        logger.debug("d %s", 1)
        logger.info("i %d", 2)
        logger.warning("w %s", "x")
        self.assertIsNone(logger.error("e %s", "y"))
        levels = [(record.levelno, record.getMessage()) for record in self.records]
        self.assertEqual(levels, [(logging.DEBUG, "d 1"), (logging.INFO, "i 2"),
                                  (logging.WARNING, "w x"), (logging.ERROR, "e y")])

    def test_print_defaults_and_no_log_record(self):
        """printはNoneの区切り・末尾を標準値として扱い、ログには記録しない。"""
        stream = io.StringIO()
        logger.print("a", "b", sep=None, end=None, file=stream)
        logger.print("c", end="", file=stream)
        self.assertEqual(stream.getvalue(), "a b\nc")
        self.assertEqual(self.records, [])

    def test_raise_with_notify(self):
        """通知してから例外を送出し、from_exceptionで連鎖を指定・抑制できる。"""
        with self.assertRaises(KeyError) as context:
            logger.raiseWithNotify(KeyError, "missing")
        self.assertEqual(context.exception.args, ("missing",))
        self.assertEqual(self.records[-1].levelno, logging.ERROR)
        cause = ValueError("cause")
        with self.assertRaises(RuntimeError) as context:
            logger.raiseWithNotify(RuntimeError, "chained", fromException=cause)
        self.assertIs(context.exception.__cause__, cause)
        try:
            raise ValueError("inner")
        except ValueError:
            with self.assertRaises(RuntimeError) as context:
                logger.raiseWithNotify(RuntimeError, "plain", fromException=None)
        self.assertTrue(context.exception.__suppress_context__)
        self.assertIsNone(context.exception.__cause__)

    def test_handler_survives_formatter_failure(self):
        """MayaHandlerは書式の失敗で例外を送出しない。"""
        handler = logger.MayaHandler()

        class Broken(logging.Formatter):
            """常に失敗する書式。"""

            def format(self, record):
                """例外を送出する。"""
                raise ValueError("format failed")

        handler.setFormatter(Broken())
        record = logging.LogRecord("mlib", logging.INFO, __file__, 1, "message", (), None)
        handler.emit(record)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
