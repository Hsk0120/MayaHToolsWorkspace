# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""形状にblendShapeを作成し、ターゲットを登録する(``cmds.blendShape`` 相当)。

.. code-block:: python

    import mlib

    blend = mlib.createBlendShape(body, [smile, frown], name="face_blendShape")
"""

from typing import Any, Dict
import maya.cmds as cmds
from ..core.object import Object
from ..decorator import _pick_alias, _require_bool, undoChunk
from ..util import _UNSET
from typing import Iterable
from mlib.nodes.blendShape import BlendShape
from mlib.nodes.node import Node


def createBlendShape(base: str | Node, targets: str | Node | Iterable[str | Node] = ..., name: str | None = ..., frontOfChain: bool = ..., *, n: str | None = ..., foc: bool = ...) -> BlendShape:
    """形状にblendShapeを作成し、ターゲットを登録する(``cmds.blendShape`` 相当)。

    ターゲットは指定順に論理番号0から登録し、
    ターゲット名はMayaの規則どおりターゲットのtransform名(名前空間を除いた名前)になる。
    ターゲット形状との接続はMayaの既定どおり残す。Undo有効時は1回で戻せる。
    name・frontOfChainは ``cmds.blendShape`` と同じ短縮名 ``n``・``foc`` でも受ける(長名と短縮名の同時指定はできない)。

    Args:
        base (str | Node): 変形するメッシュ等の形状またはtransform。
        targets (str | Node | Iterable[str | Node]): ターゲットの形状またはtransform。
            省略時はターゲットの無いblendShapeを作る(後から :meth:`~mlib.nodes.BlendShape.addTarget` で追加する)。
        name (str | None): 作成名。NoneならMayaの自動命名。既定None。
        frontOfChain (bool): Trueは既存デフォーマ(skinCluster等)より前、つまり変形の最初に
            置く(リグで一般的な「ブレンドシェイプ → スキン」の順)。Falseは最後に置く。既定True。
        n (str | None): nameの短縮名。同時指定はできない。
        foc (bool): frontOfChainの短縮名。同時指定はできない。

    Returns:
        BlendShape: 作成したblendShape。

    Raises:
        TypeError: 長名と短縮名を同時に指定した場合、frontOfChainがbool以外、nameが文字列・None以外、
            または対象が対応しない型の場合。
        ValueError: nameが空文字列、または対象が空・無効な場合。
        RuntimeError: 名前を解決できない、またはMayaが作成を拒否した場合。
    """
    ...
