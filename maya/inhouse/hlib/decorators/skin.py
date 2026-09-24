"""skinClusterの変形を保ったままjointの姿勢を編集するコンテキストマネージャ。"""

import contextlib

import maya.cmds as cmds

from .undo import undo_chunk


@contextlib.contextmanager
def preserved_skin_shape(joints):
    """指定jointに影響するskinClusterの変形を保ったまま、jointの姿勢を編集する。

    Maya標準の ``skinCluster -moveJointsMode`` を使う(``HTools/rigging/
    advancedOrientJointUI.py`` の Orient Joint ツールと同じ仕組み)。ブロック内で
    jointの translate/rotate/jointOrient/rotateAxis 等をどう変更しても、ブロックを
    抜けた時点でメッシュの見た目はブロック開始前と変わらない
    (``recacheBindMatrices`` によって、その時点の joint 姿勢を新しいバインド姿勢として
    バインド行列を再計算するため)。関節の向きを付け直す、階層構造を組み替える、
    ジョイントを移動するなど、スキニング後にリグを調整する場面全般で使える。

    頂点位置の編集(``hlib.components`` の ``Vertex``/``CV`` の ``set_position()``)は
    ``cmds.xform`` 経由でtweakノードを介して書き込むため、既にスキニングを崩さない。
    このコンテキストマネージャは joint の姿勢変更にのみ必要。

    ブロック全体(moveJointsModeの切り替え、ブロック内の編集、bind行列の再計算)を
    一回の Undo にまとめる。ブロックを抜ける際(例外時を含む)に必ず
    moveJointsMode を元の状態へ戻す。

    Args:
        joints (Iterable[Joint | str]): 姿勢を編集する対象の joint 群。joint 以外や
            無効な要素は ``hlib.nodes.joint.Joints`` と同様に黙って除外する。

    Yields:
        SkinClusters: 保護対象になった skinCluster のコレクション。
    """
    from ..nodes.joint import Joints

    skins = Joints(joints).skin_clusters()
    skin_names = [skin.full_name for skin in skins]
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
