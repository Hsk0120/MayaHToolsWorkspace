"""Maya操作の一時状態とUndoを扱うコンテキストマネージャを提供する。"""

import contextlib
from contextlib import contextmanager
from contextvars import ContextVar

import maya.api.OpenMaya as om2
import maya.cmds as cmds

from .common._fast import is_fast

__all__ = ["nativeUnits", "preservedSelection", "preservedSkinShape", "undoChunk", "undoTransaction", "viewportOff"]

_chunk_active = ContextVar("hlib_undo_chunk_active", default=False)

# reloadはモジュール辞書を維持するため、廃止済みの公開名を取り除く。
for _obsolete_name in ("undoable", "undo_chunk", "undo_transaction", "native_units",
                       "preserved_selection", "preserved_skin_shape", "viewport_off"):
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
    if is_fast() or _chunk_active.get():
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


@contextmanager
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
    with undoChunk("hlibPreservedSelection"):
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

    with undoChunk("hlibPreservedSkinShape"):
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


@contextmanager
def viewportOff():
    """メインペインを非表示にし、終了時に以前の表示状態へ戻す。

    ``@viewportOff()`` と ``with viewportOff():`` の両方で使用できる。
    GUIではViewport.suspendと同じpaneLayoutのmanage方式を使用する。
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
    from .common.viewport import Viewport

    with Viewport.suspend():
        yield
