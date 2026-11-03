# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
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
from mlib.nodes.joint import Joint
from mlib.nodes.node import Node
from mlib.nodes.skinCluster import SkinCluster

_ARGUMENT_FLAGS: frozenset
_REJECTED_FLAGS: frozenset

def bakeDeformer(source: Node | str, skeleton: Joint | str, destination: Node | str | None = ..., destinationSkeleton: Joint | str | None = ..., maxInfluences: int = ..., **kwargs: object) -> SkinCluster:
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
    ...
