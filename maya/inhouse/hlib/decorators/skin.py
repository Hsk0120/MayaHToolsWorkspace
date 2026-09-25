"""skinClusterの変形を保ったままjointの姿勢を編集するコンテキストマネージャ。"""

import contextlib

import maya.cmds as cmds

from .undo import undo_chunk


@contextlib.contextmanager
def preserved_skin_shape(joints):
    """指定jointに影響するskinClusterの変形を保ったまま、jointの姿勢を編集する。

    対象に接続するskinClusterをmoveJointsModeへ切り替え、終了時に
    recacheBindMatricesを実行して、取得できた以前のモードへ戻す。
    現在の姿勢をスキニング基準へ反映するため、保存済みバインド行列を変更する。
    任意の階層変更・influence削除や全フレームの変形保持を保証するものではない。

    モード照会・切り替え・再キャッシュ・復元で発生したRuntimeErrorは抑制する。
    そのため復元に失敗した場合も通知されない。ブロック内の例外は伝播する。
    通常のUndo対象操作を一回のチャンクにまとめるが、fast=Trueの直接更新は戻せない。

    Args:
        joints (Iterable[Joint | str]): 姿勢を編集する対象のjoint群。
            joint以外の解決済みノードは除外する。未存在の名前等は解決時に例外となる。

    Yields:
        SkinClusters: 保護対象になった skinCluster のコレクション。
    """
    from ..nodes.joint import Joints

    skins = Joints(joints).skin_clusters()
    skin_names = [skin.full_name() for skin in skins]
    previous_modes = {}

    with undo_chunk("hlibPreservedSkinShape"):
        for name in skin_names:
            try:
                previous_modes[name] = bool(cmds.skinCluster(name, query=True, moveJointsMode=True))
                cmds.skinCluster(name, edit=True, moveJointsMode=True)
            except RuntimeError:
                continue
        try:
            yield skins
        finally:
            for name in skin_names:
                try:
                    cmds.skinCluster(name, edit=True, recacheBindMatrices=True)
                except RuntimeError:
                    pass
            for name, state in previous_modes.items():
                try:
                    cmds.skinCluster(name, edit=True, moveJointsMode=state)
                except RuntimeError:
                    pass
