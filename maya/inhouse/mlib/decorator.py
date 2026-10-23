"""Maya操作の一時状態・Undoと、内部の呼出し規約を扱う。"""

import contextlib
import inspect
import re
from contextvars import ContextVar
from functools import lru_cache, wraps

import maya.api.OpenMaya as om2
import maya.cmds as cmds

__all__ = ["nativeUnits", "preservedSelection", "preservedSkinShape", "undoChunk", "undoTransaction", "viewportOff"]

_chunk_active = ContextVar("mlib_undo_chunk_active", default=False)
_fast_active = ContextVar("mlib_fast_edit", default=False)

# reloadはモジュール辞書を維持するため、廃止済みの公開名を取り除く。
for _obsolete_name in ("undoable", "undo_chunk", "undo_transaction", "native_units",
                       "preserved_selection", "preserved_skin_shape", "viewport_off", "is_fast"):
    globals().pop(_obsolete_name, None)


@contextlib.contextmanager
def undoChunk(name=None):
    """複数の Maya 操作を 1 回の Undo チャンクにまとめる。

    ``with undoChunk("処理名"):`` と ``@undoChunk("処理名")`` の両方で使用できる。
    デコレータには括弧が必要。関数の戻り値・メタデータを保持し、反復呼び出しも可能。

    チャンクを開いた場合は finally で閉じる。閉じる際の例外は抑制する。コンテキスト内部の例外は抑制せず、自動ロールバックもしない。

    入れ子の通常チャンクは外側へまとめ、名前も外側を使う。
    undoTransaction の独立したチャンクは省略しない。
    Undo非対応の操作やfast=Trueの直接更新を取り消せるようにはしない。

    Args:
        name (str | None): Maya Undo キューに表示するチャンク名。省略時は
            関数名を自動設定せず、Mayaの既定表示を使う。

    Yields:
        None: コンテキスト内で実行した Maya 操作を同じ Undo として扱う。
    """
    if _is_fast() or _chunk_active.get():
        yield
        return
    opened = False
    token = None
    try:
        kwargs = {"openChunk": True}
        if name:
            kwargs["chunkName"] = str(name)
        cmds.undoInfo(**kwargs)
        opened = True
        token = _chunk_active.set(True)
        yield
    finally:
        if token is not None:
            _chunk_active.reset(token)
        if opened:
            try:
                cmds.undoInfo(closeChunk=True)
            except Exception as exc:
                from . import logger
                logger.warning("Undo chunk close failed: %s", exc)


@contextlib.contextmanager
def undoTransaction(name=None):
    """例外発生時に自動でロールバックする Undo トランザクション。

    ``with undoTransaction("処理名"):`` と ``@undoTransaction("処理名")`` の
    両方で使用できる。デコレータには括弧が必要。

    ブロック内で例外が発生した場合、チャンクを閉じたうえで ``cmds.undo()`` を
    1回実行してブロック内のUndo対象操作を巻き戻してから、元の例外をそのまま
    再送出する。正常終了時はロールバックせず、undoChunk と同様に1回の
    Undo にまとまったチャンクとして履歴に残る。

    Undoが有効であることが前提。fast=True・ファイル操作等は巻き戻せない。
    ガード作成・チャンク終了・undoの失敗は警告し、元の例外を優先するため、
    ロールバック完了を保証するものではない。

    チャンク内で実際の変更が一件も無いまま例外になった場合、``cmds.undo()``
    は空のチャンクを素通りして本トランザクションと無関係な直前の操作を
    巻き戻してしまう(Maya の undo キューの既定挙動)。これを避けるため、
    ロールバック直前に軽量なダミーノードを作成・削除してチャンクへ必ず
    1件の Undo エントリを積んでから閉じる。ガード作成またはチャンク終了が
    失敗した場合、無関係な履歴の巻き戻しを避けるためundoは実行しない。

    Args:
        name (str | None): Maya Undo キューに表示するチャンク名。省略時は
            関数名を自動設定せず、Mayaの既定表示を使う。

    Yields:
        None: コンテキスト内で実行した Maya 操作を同じ Undo として扱う。

    Raises:
        Exception: ブロック内で送出された例外は、ロールバック後にそのまま再送出する。
    """
    kwargs = {"openChunk": True}
    if name:
        kwargs["chunkName"] = str(name)
    cmds.undoInfo(**kwargs)
    try:
        yield
    except BaseException:
        guard_created = False
        closed = False
        try:
            guard = cmds.createNode("network", skipSelect=True)
            guard_created = True
            cmds.delete(guard)
        except Exception as exc:
            from . import logger
            logger.warning("Undo guard creation failed: %s", exc)
        try:
            cmds.undoInfo(closeChunk=True)
            closed = True
        except Exception as exc:
            from . import logger
            logger.warning("Undo chunk close failed: %s", exc)
        if guard_created and closed:
            try:
                cmds.undo()
            except Exception as exc:
                from . import logger
                logger.warning("Undo rollback failed: %s", exc)
        else:
            from . import logger
            logger.warning("Undo rollback skipped: guard creation or chunk close did not succeed")
        raise
    else:
        cmds.undoInfo(closeChunk=True)


@contextlib.contextmanager
def nativeUnits():
    """ブロック内だけ内部単位(距離=cm、角度=radian)を強制する。

    行列やベクトルの演算など、シーンの表示単位に依存しない計算をしたい場合に
    使う。ブロックを抜ける際(例外時を含む)に開始時点の UI 単位へ復元する。
    ``om2.MDistance``/``om2.MAngle`` の ``setUIUnit`` を直接呼ぶため MEL の
    往復が無く、時間単位には影響しない。表示単位の変更はシーンデータ自体を
    変更しないため、この切り替え自体は Maya の Undo キューに乗らない
    （計算中の単位変換用の一時状態であり、操作そのもののロールバックは行わない）。

    Yields:
        None: ブロック内では距離=センチメートル、角度=ラジアンとして扱ってよい。
    """
    previous_linear = om2.MDistance.uiUnit()
    previous_angle = om2.MAngle.uiUnit()
    try:
        om2.MDistance.setUIUnit(om2.MDistance.kCentimeters)
        om2.MAngle.setUIUnit(om2.MAngle.kRadians)
        yield
    finally:
        om2.MDistance.setUIUnit(previous_linear)
        om2.MAngle.setUIUnit(previous_angle)


@contextlib.contextmanager
def preservedSelection():
    """ブロックの前後で Maya の選択状態を保存・復元する。

    ブロック内で選択状態を変更する操作を行っても、ブロックを抜ける際（例外時を含む）に
    開始時点の選択状態へ復元する。undoChunk と同様、復元は cleanup であり、ブロック内で
    行った操作そのもののロールバックは行わない。
    選択の復元にはUndo対応のselectを使い、ブロック全体を一回のUndoにまとめる。
    コンポーネント選択も保持する。ブロック内で削除された対象は復元対象から除く。

    Yields:
        None: ブロック内で自由に選択状態を変更してよい。
    """
    original = om2.MGlobal.getActiveSelectionList()
    with undoChunk("mlibPreservedSelection"):
        try:
            yield
        finally:
            names = original.getSelectionStrings()
            surviving = [name for name in names if cmds.objExists(name)]
            if surviving:
                cmds.select(surviving, replace=True, noExpand=True)
            else:
                cmds.select(clear=True)


@contextlib.contextmanager
def preservedSkinShape(joints):
    """指定jointに影響するskinClusterの変形を保ったまま、jointの姿勢を編集する。

    対象に接続するskinClusterをmoveJointsModeへ切り替え、終了時に
    recacheBindMatricesを実行して、取得できた以前のモードへ戻す。
    現在の姿勢をスキニング基準へ反映するため、保存済みバインド行列を変更する。
    任意の階層変更・influence削除や全フレームの変形保持を保証するものではない。

    モード照会・切り替え・再キャッシュ・復元で発生したRuntimeErrorは抑制し、
    対象と失敗した処理をloggerへ警告する。ブロック内の例外は伝播する。
    警告が出た場合は保護・復元が完了したとは限らないため、対象の状態を確認する。
    通常のUndo対象操作を一回のチャンクにまとめるが、fast=Trueの直接更新は戻せない。

    Args:
        joints (Iterable[Joint | str]): 姿勢を編集する対象のjoint群。
            joint以外の解決済みノードは除外する。未存在の名前等は解決時に例外となる。

    Yields:
        SkinClusters: 保護対象になった skinCluster のコレクション。
    """
    from . import logger
    from .nodes.joint import Joints

    skins = Joints(joints).getSkinClusters()
    skin_names = [skin.getFullName() for skin in skins]
    previous_modes = {}

    with undoChunk("mlibPreservedSkinShape"):
        for name in skin_names:
            try:
                previous_modes[name] = bool(cmds.skinCluster(name, query=True, moveJointsMode=True))
            except RuntimeError as exc:
                logger.warning("スキン保護のモード照会に失敗しました: %s (%s)", name, exc)
                continue
            try:
                cmds.skinCluster(name, edit=True, moveJointsMode=True)
            except RuntimeError as exc:
                logger.warning("スキン保護のモード切替に失敗しました: %s (%s)", name, exc)
                continue
        try:
            yield skins
        finally:
            for name in skin_names:
                try:
                    cmds.skinCluster(name, edit=True, recacheBindMatrices=True)
                except RuntimeError as exc:
                    logger.warning("スキン保護のバインド行列再キャッシュに失敗しました: %s (%s)", name, exc)
            for name, state in previous_modes.items():
                try:
                    cmds.skinCluster(name, edit=True, moveJointsMode=state)
                except RuntimeError as exc:
                    logger.warning("スキン保護のモード復元に失敗しました: %s (%s)", name, exc)


@contextlib.contextmanager
def viewportOff():
    """メインペインを非表示にし、終了時に以前の表示状態へ戻す。

    ``@viewportOff()`` と ``with viewportOff():`` の両方で使用できる。
    GUIではメインペインのpaneLayoutのmanageを一時的に解除する。
    バッチ実行では表示操作を行わない。OGS・refresh・評価設定は変更しない。
    入れ子でも元の状態を維持し、処理中の例外は再実行せず伝播する。

    Yields:
        None: 表示を停止している間に処理を実行する。

    Raises:
        RuntimeError: GUIのメインペインを取得・編集できない場合。
    """
    if cmds.about(batch=True):
        yield
        return
    import maya.mel as mel

    pane = mel.eval("global string $gMainPane; $mlibMainPane = $gMainPane;")
    if not pane or not cmds.paneLayout(pane, exists=True):
        raise RuntimeError("Maya main pane is unavailable")
    previous = cmds.paneLayout(pane, query=True, manage=True)
    try:
        cmds.paneLayout(pane, edit=True, manage=False)
        yield
    finally:
        if cmds.paneLayout(pane, exists=True):
            cmds.paneLayout(pane, edit=True, manage=previous)


def _is_fast():
    """現在の呼出しがOpenMaya直接編集を要求しているか。

    Returns:
        bool: 現在の呼出しがOpenMaya直接編集を要求しているか。
    """
    return _fast_active.get()


def _fast_edit(function):
    """fast引数を検証し、内側の対応メソッドへ実行モードを伝える。

    外側がfastなら、省略・fast=Falseでも内側は直接更新を継承する。
    各呼出しの引数は継承中もboolを検証し、開始した範囲だけを終了時に復元する。

    Args:
        function (callable): fast 引数を持つ編集関数。

    Returns:
        callable: fast の検証と実行モードの伝播を行う関数。
    """
    signature = inspect.signature(function)
    parameter = signature.parameters.get("fast")
    keyword_only = parameter is not None and parameter.kind == inspect.Parameter.KEYWORD_ONLY

    @wraps(function)
    def wrapped(*args, **kwargs):
        """fastの型を検証し、有効範囲を復元しながら元の関数を実行する。

        Args:
            *args (object): 元の関数へ渡す位置引数。
            **kwargs (object): fastを含む元の関数のキーワード引数。

        Returns:
            object: 元の関数の戻り値。

        Raises:
            TypeError: fastがboolでない場合、または元の関数の引数が不正な場合。
        """
        # keyword-only は呼出しごとの Signature.bind を避ける。
        # その他の引数の正当性は元関数の Python 呼出しが検証する。
        if keyword_only:
            requested = kwargs.get("fast", False)
        else:
            requested = signature.bind(*args, **kwargs).arguments.get("fast", False)
        if type(requested) is not bool:
            raise TypeError("fast must be a bool")
        # Falseは通常モードへの強制切替ではなく、外側の指定を維持する。
        if _is_fast() or not requested:
            return function(*args, **kwargs)
        token = _fast_active.set(True)
        try:
            return function(*args, **kwargs)
        finally:
            _fast_active.reset(token)
    return wrapped


def _safe_edit(function):
    """safe=Trueで書込み失敗を数え、複合値は書ける子を更新する。

    Args:
        function (callable): valueとsafe引数を持つPlugのsetter。

    Returns:
        callable: 通常時は元の戻り値、safe時は失敗数を返す関数。
    """
    signature = inspect.signature(function)

    @wraps(function)
    def wrapped(self, *args, **kwargs):
        """通常の戻り値を維持し、safe指定時だけ成分ごとの書込み失敗を数える。

        Args:
            *args (object): 元のsetterへ渡す位置引数。
            **kwargs (object): safeを含む元のsetterのキーワード引数。

        Returns:
            object | int: 通常時は元の戻り値、safe指定時は失敗した成分数。

        Raises:
            NotImplementedError: 対象のfast更新が未対応の場合。
        """
        if len(args) <= 1 and not kwargs.get("safe", False):
            return function(self, *args, **kwargs)
        bound = signature.bind(self, *args, **kwargs)
        if not bound.arguments.get("safe", False):
            return function(self, *args, **kwargs)
        bound.arguments["safe"] = False
        # multi全体へのsetはsafeでも許可しない。
        if self.isArray():
            return function(*bound.args, **bound.kwargs)
        try:
            function(*bound.args, **bound.kwargs)
            return 0
        except NotImplementedError:
            # 非対応fastを部分更新へ読み替えず、更新前の拒否を維持する。
            raise
        except (RuntimeError, TypeError, ValueError):
            if not self.isValid() or not self.mplug().isCompound:
                return 1
            try:
                values = bound.arguments["value"]
                ui_units = bound.arguments.get("uiUnits", False)
                if hasattr(self, "_set_components"):
                    if ui_units:
                        from .core.attributeType import _convert_units
                        unit = bound.arguments.get("unit", "rad")
                        if unit != "rad":
                            raise ValueError("uiUnits=True cannot be combined with a non-default unit")
                        values = (self._ui_components(values) if hasattr(self, "_ui_components")
                                  else _convert_units(self.mplug(), values, to_ui=False))
                        ui_units = False
                    values = self._set_components(values, bound.arguments.get("unit", "rad"))
                values = tuple(values)
                if len(values) != self.mplug().numChildren():
                    return 1
                return sum(getattr(self[i], function.__name__)(v, safe=True, uiUnits=ui_units)
                           for i, v in enumerate(values))
            except (RuntimeError, TypeError, ValueError):
                return 1
    return wrapped


@lru_cache(maxsize=None)
def _maya_aliases(command):
    """実行中のMayaが公開するフラグ一覧を取得する。初回呼び出し時のみ照会。

    Args:
        command: フラグを照会するMayaコマンド名。
    """
    help_text = cmds.help(command)
    aliases = dict(re.findall(r"^\s+-(\w+)\s+-(\w+)\b", help_text, re.MULTILINE))
    if not aliases:
        raise RuntimeError("Cannot read Maya flag definitions: " + command)
    # query/editはhelpのフラグ一覧に含まれないコマンドもある。
    # 対応モードかどうかの検査は元のMayaコマンドに任せる。
    aliases.update(q="query", e="edit")
    return aliases


def _normalize_flags(function, kwargs):
    """関数の登録済み別名またはMayaコマンド名からフラグを正規化する。

    長名と短名の重複は拒否し、入力辞書は変更しない。

    Args:
        function (callable | str): 登録済み関数または Maya コマンド名。
        kwargs (dict): 正規化するキーワード引数。

    Returns:
        dict: 短名を長名に置き換えた新しい辞書。
    """
    if not kwargs:
        return {}
    aliases = getattr(function, "__mlib_flag_aliases__", {})
    command = function if isinstance(function, str) else getattr(function, "__mlib_maya_command__", None)
    if command:
        aliases = dict(_maya_aliases(command), **aliases)
    result = dict(kwargs)
    for short, long in aliases.items():
        if short not in result or short == long:
            continue
        if long in result:
            raise TypeError("Specify only one of {!r} and {!r}".format(long, short))
        result[long] = result.pop(short)
    return result


def _flag_aliases(command=None, **aliases):
    """Mayaコマンド名または明示した短名=長名の対応を関数へ付与する。

    シグネチャとdocstringを保持する。別名の競合と位置引数との重複は
    関数本体（Undoチャンク等を含む）の実行前に検出する。

    Args:
        command (str | None): Maya コマンド名。
        **aliases: 短名をキー、長名を値とする対応。

    Returns:
        callable: フラグを正規化するデコレータ。
    """
    def decorate(function):
        signature = inspect.signature(function)

        @lru_cache(maxsize=128)
        def validate_shape(positional_count, names):
            """値に依存しない引数の形だけを検証し、成功した形を上限付きで保持する。

            値・ノード・Plugを保持しない。装飾ごとのキャッシュなのでreloadで
            新しい関数が作られたときに古いsignatureを再利用しない。
            """
            signature.bind(*([None] * positional_count), **dict.fromkeys(names))

        @wraps(function)
        def wrapped(*args, **kwargs):
            normalized = _normalize_flags(wrapped, kwargs)
            validate_shape(len(args), tuple(normalized))
            return function(*args, **normalized)

        wrapped.__mlib_flag_aliases__ = dict(aliases)
        wrapped.__mlib_maya_command__ = command
        return wrapped
    return decorate
