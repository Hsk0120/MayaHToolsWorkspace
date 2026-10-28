"""Undoチャンクと、Mayaの単位・選択・スキン・表示状態の一時変更を提供する。

公開6入口のほかに、fast/safeの状態管理とフラグ正規化の内部補助(先頭_)を集約する。
"""

import contextlib
from contextvars import ContextVar

import maya.api.OpenMaya as om2
import maya.cmds as cmds

from . import logger
from .util import _ArgumentError, _UNSET

__all__ = ["nativeUnits", "preservedSelection", "preservedSkinShape", "undoChunk", "undoTransaction", "viewportOff"]

# 外側のundoChunkの状態。Falseはチャンク外、Trueは開いたチャンク内、
# _CHUNK_SKIPPEDはUndo無効のため開閉を省いたチャンク内。
_chunk_active = ContextVar("mlib_undo_chunk_active", default=False)
_CHUNK_SKIPPED = "skipped"

# reloadはモジュール辞書を維持するため、廃止済みの公開名を取り除く。
for _obsolete_name in ("undoable", "undo_chunk", "undo_transaction", "native_units",
                       "preserved_selection", "preserved_skin_shape", "viewport_off", "is_fast",
                       "_fast_active", "_fast_edit", "_is_fast", "_safe_edit",
                       "_flag_aliases", "_normalize_flags", "_maya_aliases"):
    globals().pop(_obsolete_name, None)


class _UndoChunk(contextlib.ContextDecorator):
    """undoChunkの実体。withと関数デコレーターの両方で使う。

    generatorの生成を避け、Undoが無効な場合はチャンクの開閉を省略する。
    デコレーターとして使う場合は呼出しごとに新しいインスタンスを作るため、
    再帰や入れ子の呼出しでも状態を共有しない。
    """

    __slots__ = ("_name", "_opened", "_token")

    def __init__(self, name):
        """チャンク名を保持する。Undoキューはwithの開始まで変更しない。

        Args:
            name (str | None): Undoキューのチャンク名。
        """
        self._name = name
        self._opened = False
        self._token = None

    def __enter__(self):
        """外側のチャンクが無く、Undoが有効ならチャンクを開く。

        Returns:
            None: withの ``as`` で受け取る値。
        """
        if _chunk_active.get():
            return None
        if not cmds.undoInfo(query=True, state=True):
            # Undoが無効なら記録されないため、チャンクを開かない。入れ子の
            # 問い合わせも省くため、外側のチャンクとして扱う。
            self._token = _chunk_active.set(_CHUNK_SKIPPED)
            return None
        if self._name:
            cmds.undoInfo(openChunk=True, chunkName=str(self._name))
        else:
            cmds.undoInfo(openChunk=True)
        self._opened = True
        self._token = _chunk_active.set(True)
        return None

    def __exit__(self, exc_type, exc_value, traceback):
        """開いたチャンクを閉じる。閉じる失敗は警告し、ブロック内の例外は抑制しない。

        Returns:
            bool: 常にFalse。
        """
        token = self._token
        if token is not None:
            self._token = None
            _chunk_active.reset(token)
        if self._opened:
            self._opened = False
            try:
                cmds.undoInfo(closeChunk=True)
            except Exception as exc:
                logger.warning("Undo chunk close failed: %s", exc)
        return False

    def _recreate_cm(self):
        """デコレーター呼出しごとに独立したインスタンスを返す。"""
        return type(self)(self._name)


def _undo_recording():
    """現在の操作がUndoへ記録される状態か判定する。

    Undo有効時に開いたundoChunkの内側では、開いた時点の問い合わせ結果を使って
    ``cmds.undoInfo`` の問い合わせを省く。それ以外は毎回問い合わせる。
    ブロック内でUndoを無効にした場合もTrueを返し得るため、Falseのときに
    Undo用だけの処理を省く判定にだけ使う。Falseは毎回の問い合わせ結果なので正確。

    Returns:
        bool: Undoへ記録される状態ならTrue。
    """
    if _chunk_active.get() is True:
        return True
    return bool(cmds.undoInfo(query=True, state=True))


def _require_bool(value, name):
    """bool型の引数を検証する。

    Args:
        value (bool): 検証する値。
        name (str): 例外メッセージに使う引数名。

    Returns:
        bool: 検証済みの値。

    Raises:
        TypeError: bool以外の場合。
    """
    if type(value) is not bool:
        raise TypeError(f"{name} must be a bool")
    return value


def _pick_alias(long, short, longName, shortName, default=_UNSET):
    """長短の別名引数から指定された値を選ぶ。

    Args:
        long (object): 長名側の値。未指定は ``_UNSET``。
        short (object): 短名側の値。未指定は ``_UNSET``。
        longName (str): 長名の引数名。例外メッセージに使う。
        shortName (str): 短名の引数名。例外メッセージに使う。
        default (object): 両方未指定のときに返す値。``_UNSET`` なら必須引数として拒否する。

    Returns:
        object: 指定された値、または既定値。

    Raises:
        TypeError: 長短を同時に指定した場合、または既定値が無く両方未指定の場合
            (いずれも ``_ArgumentError``)。
    """
    if short is not _UNSET:
        if long is not _UNSET:
            raise _ArgumentError(f"Specify only one of '{longName}' and '{shortName}'")
        return short
    if long is not _UNSET:
        return long
    if default is _UNSET:
        raise _ArgumentError(f"Missing required argument: '{longName}'")
    return default


def _merge_flags(kwargs, pairs):
    """長短の別名で受けたcmdsのフラグ群を、指定分だけ長名で辞書へ詰める。

    Args:
        kwargs (dict): 詰める先。Mayaコマンドへ ``**kwargs`` で渡す辞書。
        pairs (Iterable[tuple[object, object, str, str]]): (長名の値, 短名の値, 長名, 短名) の列。
            未指定の値は ``_UNSET``。

    Returns:
        dict: 渡されたkwargs自身。省略したフラグは追加しない。

    Raises:
        TypeError: 同じフラグの長短を同時に指定した場合(``_ArgumentError``)。
    """
    for long, short, long_name, short_name in pairs:
        if short is not _UNSET:
            if long is not _UNSET:
                raise _ArgumentError(f"Specify only one of '{long_name}' and '{short_name}'")
            kwargs[long_name] = short
        elif long is not _UNSET:
            kwargs[long_name] = long
    return kwargs


def _validated_flags(locked=None, keyable=None, channelBox=None):
    """アトリビュートの状態値を全件検証し、Mayaのフラグ名へ変換する。

    Args:
        locked (bool | None): ロック状態。Noneは変更しない。
        keyable (bool | None): キー可能状態。
        channelBox (bool | None): Channel Box表示状態。

    Returns:
        dict[str, bool]: 指定されたMayaフラグ(``lock``・``keyable``・``channelBox``)だけを含む辞書。

    Raises:
        TypeError: boolまたはNone以外の状態がある場合。
    """
    flags = {}
    for name, value in (("lock", locked), ("keyable", keyable), ("channelBox", channelBox)):
        if value is not None:
            if type(value) is not bool:
                raise TypeError(f"{name} must be bool or None")
            flags[name] = value
    return flags


def _edit_context(name, fast, *, transaction=False):
    """fastを検証し、書込みメソッドの本体を包むUndo文脈を返す。

    ``with _edit_context("mlibClassMethod", fast):`` の形で、fastの定型
    (``nullcontext() if fast else undoChunk(name)``)を1行にする。

    Args:
        name (str): 通常経路のUndoチャンク名(``mlib<Class><Method>``)。
        fast (bool): TrueはUndoなしのOpenMaya更新。
        transaction (bool): Trueなら通常経路に ``undoTransaction`` を使う
            (Undo無効時に拒否する必要がある構築処理用)。既定は ``undoChunk``。

    Returns:
        contextlib.AbstractContextManager: fastはnullcontext、通常はundoChunkまたはundoTransaction。

    Raises:
        TypeError: fastがbool以外の場合。
    """
    _require_bool(fast, "fast")
    if fast:
        return contextlib.nullcontext()
    return undoTransaction(name) if transaction else undoChunk(name)


def undoChunk(name=None):
    """MayaのUndo対象操作を一つのチャンクへまとめる。

    with undoChunk(name)と@undoChunk(name)で使う。通常の入れ子は外側の
    名前とチャンクを使い、undoTransactionの独立チャンクは省略しない。
    終了時は例外の有無によらずチャンクを閉じる。閉じる失敗は警告し、
    ブロック内の例外は再送出する。自動ロールバックやfastのUndo対応は行わない。

    開始時にUndoが無効(``cmds.undoInfo(query=True, state=True)`` がFalse)なら、
    記録されないためチャンクを開閉しない。ブロック内でUndoを有効にしても、
    そのブロックの操作は一つのチャンクにまとめない。

    Args:
        name (str | None): Undoキューのチャンク名。省略時はMayaの既定表示。

    Returns:
        contextlib.ContextDecorator: withまたはデコレーターとして使うコンテキスト。
            withの ``as`` で受け取る値はNone。
    """
    return _UndoChunk(name)


@contextlib.contextmanager
def undoTransaction(name=None):
    """例外時にUndoを一回実行し、ブロック内の変更の巻戻しを試みる。

    with undoTransaction(name)と@undoTransaction(name)で使う。Undo有効時が前提で、
    正常終了時は独立した一つのチャンクを残す。fastの直接更新やファイル操作は戻せない。

    例外時はnetworkノードを作成・削除してUndoエントリを確保してから閉じる。
    空チャンクによって直前の別操作を戻すのを防ぐため、ガード作成かチャンク終了に
    失敗した場合はUndoしない。復旧の失敗は警告し、元の例外を再送出する。
    巻戻しの完了は保証しない。

    名前を指定した場合、ブロック内のundoChunkはこのチャンクの内側として扱い、Mayaの
    チャンクを入れ子に開かない(Mayaは入れ子のチャンクを外側の一つへまとめ、表示名は
    最初に開いた名前付きチャンクの名前になるため、Undoの単位と名前は同じ)。この扱いは
    外側にundoChunkも名前付きのundoTransactionも無い場合だけ、開始時のUndoの状態を
    一度問い合わせて決め、無効ならブロック内のundoChunkも従来どおり開閉しない。
    名前を省略した場合は、最初の内側のチャンク名が表示名になるため従来どおり開く。

    Args:
        name (str | None): Undoキューのチャンク名。省略時はMayaの既定表示。
    """
    token = None
    outermost = bool(name) and not _chunk_active.get()
    if outermost:
        recording = cmds.undoInfo(query=True, state=True)
    kwargs = {"openChunk": True}
    if name:
        kwargs["chunkName"] = str(name)
    cmds.undoInfo(**kwargs)
    if outermost:
        token = _chunk_active.set(True if recording else _CHUNK_SKIPPED)
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
            logger.warning("Undo guard creation failed: %s", exc)
        try:
            cmds.undoInfo(closeChunk=True)
            closed = True
        except Exception as exc:
            logger.warning("Undo chunk close failed: %s", exc)
        if guard_created and closed:
            try:
                cmds.undo()
            except Exception as exc:
                logger.warning("Undo rollback failed: %s", exc)
        else:
            logger.warning("Undo rollback skipped: guard creation or chunk close did not succeed")
        raise
    else:
        cmds.undoInfo(closeChunk=True)
    finally:
        if token is not None:
            _chunk_active.reset(token)


@contextlib.contextmanager
def nativeUnits():
    """距離と角度のUI単位を、ブロック内だけcm・radへ切り替える。

    OpenMayaのsetUIUnitで変更し、例外時も開始時の単位へ戻す。
    時間単位とシーンの値は変更しない。この単位切替自体はUndoへ記録しない。
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
    """現在の選択を保存し、ブロック終了時に復元する。

    コンポーネント選択を含む選択リストを保存し、終了時に存在する選択名を
    cmds.selectで復元する。例外時も復元し、ブロック全体を一つのUndoチャンクへ
    まとめる。内部で行った変更のロールバックはしない。
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
    """jointに接続するskinClusterをmoveJointsModeへ切り替えて姿勢を編集する。

    終了時はrecacheBindMatricesで現在姿勢をバインドマトリクスへ反映し、取得できた
    以前のモードへ戻す。任意の階層変更・influence削除や全フレームの変形保持は保証しない。
    モード照会・切替・再キャッシュ・復元のRuntimeErrorは警告して継続し、
    ブロック内の例外は伝播する。警告時は保護や復元が未完了の可能性がある。
    通常の変更を一つのUndoチャンクへまとめるが、fastの直接更新は戻せない。

    Args:
        joints (Iterable[Joint | str]): 対象joint。非JointはTypeError、解決できない入力も例外。

    Yields:
        SkinClusters: 保護対象のコレクション。
    """
    from .nodes.joint import Joints

    skins = Joints(joints).getSkinClusters()
    skin_names = [skin.getFullName() for skin in skins]
    previous_modes = {}

    with undoChunk("mlibPreservedSkinShape"):
        for name in skin_names:
            try:
                previous_modes[name] = bool(cmds.skinCluster(name, query=True, moveJointsMode=True))
            except RuntimeError as exc:
                logger.warning("Skin shape protection could not query moveJointsMode: %s (%s)", name, exc)
                continue
            try:
                cmds.skinCluster(name, edit=True, moveJointsMode=True)
            except RuntimeError as exc:
                logger.warning("Skin shape protection could not enable moveJointsMode: %s (%s)", name, exc)
                continue
        try:
            yield skins
        finally:
            for name in skin_names:
                try:
                    cmds.skinCluster(name, edit=True, recacheBindMatrices=True)
                except RuntimeError as exc:
                    logger.warning("Skin shape protection could not recache bind matrices: %s (%s)", name, exc)
            for name, state in previous_modes.items():
                try:
                    cmds.skinCluster(name, edit=True, moveJointsMode=state)
                except RuntimeError as exc:
                    logger.warning("Skin shape protection could not restore moveJointsMode: %s (%s)", name, exc)


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
