"""Undoチャンクと、Mayaの単位・選択・スキン・表示状態の一時変更を提供する。"""

import contextlib
from contextvars import ContextVar

import maya.api.OpenMaya as om2
import maya.cmds as cmds

__all__ = ["nativeUnits", "preservedSelection", "preservedSkinShape", "undoChunk", "undoTransaction", "viewportOff"]

_chunk_active = ContextVar("mlib_undo_chunk_active", default=False)

# reloadはモジュール辞書を維持するため、廃止済みの公開名を取り除く。
for _obsolete_name in ("undoable", "undo_chunk", "undo_transaction", "native_units",
                       "preserved_selection", "preserved_skin_shape", "viewport_off", "is_fast",
                       "_fast_active", "_fast_edit", "_is_fast", "_safe_edit",
                       "_flag_aliases", "_normalize_flags", "_maya_aliases"):
    globals().pop(_obsolete_name, None)


@contextlib.contextmanager
def undoChunk(name=None):
    """MayaのUndo対象操作を一つのチャンクへまとめる。

    with undoChunk(name)と@undoChunk(name)で使う。通常の入れ子は外側の
    名前とチャンクを使い、undoTransactionの独立チャンクは省略しない。
    終了時は例外の有無によらずチャンクを閉じる。閉じる失敗は警告し、
    ブロック内の例外は再送出する。自動ロールバックやfastのUndo対応は行わない。

    Args:
        name (str | None): Undoキューのチャンク名。省略時はMayaの既定表示。
    """
    if _chunk_active.get():
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
    """例外時にUndoを一回実行し、ブロック内の変更の巻戻しを試みる。

    with undoTransaction(name)と@undoTransaction(name)で使う。Undo有効時が前提で、
    正常終了時は独立した一つのチャンクを残す。fastの直接更新やファイル操作は戻せない。

    例外時はnetworkノードを作成・削除してUndoエントリを確保してから閉じる。
    空チャンクによって直前の別操作を戻すのを防ぐため、ガード作成かチャンク終了に
    失敗した場合はUndoしない。復旧の失敗は警告し、元の例外を再送出する。
    巻戻しの完了は保証しない。

    Args:
        name (str | None): Undoキューのチャンク名。省略時はMayaの既定表示。
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

    終了時はrecacheBindMatricesで現在姿勢をバインド行列へ反映し、取得できた
    以前のモードへ戻す。任意の階層変更・influence削除や全フレームの変形保持は保証しない。
    モード照会・切替・再キャッシュ・復元のRuntimeErrorは警告して継続し、
    ブロック内の例外は伝播する。警告時は保護や復元が未完了の可能性がある。
    通常の変更を一つのUndoチャンクへまとめるが、fastの直接更新は戻せない。

    Args:
        joints (Iterable[Joint | str]): 対象joint。非JointはTypeError、解決できない入力も例外。

    Yields:
        SkinClusters: 保護対象のコレクション。
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
