"""デフォーマー(delta mush・cluster 等)を含む変形を、スキンのウェイトへ焼き込み、skinCluster を返す(``cmds.bakeDeformer`` 相当)。

Maya の Bake Deformers to Skin Weights と同じく ``cmds.bakeDeformer`` で、ジョイントを動かしたときの
変形を元の形状から測り、変形先の形状の skinCluster のウェイトにする。変形先を省略すると元の形状自身を
skinCluster だけの変形へ置き換える(元のデフォーマーは除かれる)。

.. code-block:: python

    import mlib

    skin = mlib.bakeDeformer("body_geo", "root_JNT", "body_game_geo", maxInfluences=4)
"""

import maya.cmds as cmds

from ..core.object import Object
from ..decorator import undoChunk

#: 引数で受けるため、``**kwargs`` では受け付けないフラグ(長名・短名)。
_ARGUMENT_FLAGS = frozenset(("srcMeshName", "sm", "srcSkeletonName", "ss", "dstMeshName", "dm",
                             "dstSkeletonName", "ds", "maxInfluences", "mi"))

#: 照会・編集のフラグ(bakeDeformer は作成専用)。
_REJECTED_FLAGS = frozenset(("query", "q", "edit", "e"))


def bakeDeformer(source, skeleton, destination=None, destinationSkeleton=None, maxInfluences=4, **kwargs):
    """元の形状の変形を、変形先の形状の skinCluster のウェイトへ焼き込む。

    選択状態は参照しない。変形先が既にバインドされていれば、その skinCluster のウェイトを書き換える。
    fast引数は持たない(OpenMayaに同等機能が無い)。Undo有効時は1回で戻せる。

    Args:
        source (Node | str): 変形を測る元の形状(またはその transform)。デフォーマーで変形していること。
        skeleton (Joint | str): 元の形状を動かすスケルトンのルートの joint。
        destination (Node | str | None): ウェイトを焼き込む形状。None は source 自身(元のデフォーマーを除き、
            skinCluster だけの変形にする)。
        destinationSkeleton (Joint | str | None): 変形先のスケルトンのルート。None は skeleton と同じ。
        maxInfluences (int): 1頂点の最大influence数。正の整数。既定4。
        **kwargs (object): ``cmds.bakeDeformer`` のその他のフラグ(``influences``・``pruneWeights``・
            ``smoothWeights``・``hierarchy``・``customRangeOfMotion``・``bakeRangeOfMotion``・
            ``colorizeSkeleton``。長名・短名とも可)。

    Returns:
        SkinCluster: 変形先の形状の skinCluster。

    Raises:
        TypeError: 引数で受けるフラグ・query・editフラグを ``**kwargs`` に渡した場合。
        ValueError: maxInfluencesが正の整数でない場合。
        RuntimeError: 名前を解決できない、Mayaが焼き込みを拒否した、または変形先に skinCluster が見つからない場合。
    """
    # nodes はcmdsを参照するため、循環importを避けて関数内で読み込む。
    from ..nodes.node import Node
    from ..nodes.skinCluster import SkinCluster

    duplicated = sorted(_ARGUMENT_FLAGS.intersection(kwargs))
    if duplicated:
        raise TypeError(f"Pass these as arguments of bakeDeformer: {', '.join(duplicated)}")
    rejected = sorted(_REJECTED_FLAGS.intersection(kwargs))
    if rejected:
        raise TypeError(f"bakeDeformer does not accept: {', '.join(rejected)}")
    if isinstance(maxInfluences, bool) or not isinstance(maxInfluences, int) or maxInfluences < 1:
        raise ValueError("maxInfluences must be a positive int")
    source_node = Node(Object._input_name(source))
    target = source_node if destination is None else Node(Object._input_name(destination))
    root = Node(Object._input_name(skeleton))
    target_root = root if destinationSkeleton is None else Node(Object._input_name(destinationSkeleton))
    with undoChunk("mlibBakeDeformer"):
        cmds.bakeDeformer(srcMeshName=source_node.getFullName(), srcSkeletonName=root.getFullName(),
                          dstMeshName=target.getFullName(), dstSkeletonName=target_root.getFullName(),
                          maxInfluences=maxInfluences, **kwargs)
    # 結果の照会はUndoのまとまりの外で行う(中で行うとRedoでウェイトが焼き込み前の値になる)。
    skins = cmds.ls(cmds.listHistory(target.getFullName()) or [], type="skinCluster")
    if not skins:
        raise RuntimeError(f"bakeDeformer did not create a skinCluster: {target.getFullName()}")
    return SkinCluster(skins[0])
