"""単一の対象を複製し、複製結果の先頭ノードを型に応じたラッパーで返す。

``maya.cmds.duplicate`` に委ね、MayaのUndoに対応する(1回のUndoで戻せる)。fast引数は持たない。

.. code-block:: python

    import mlib

    node = mlib.createNode("transform", name="example")
    copied = mlib.duplicate(node, name="exampleCopy")
"""

import maya.cmds as cmds

from ..decorator import _merge_flags, undoChunk
from ..util import _UNSET


def duplicate(node, *,
        fullPath=_UNSET, f=_UNSET,
        inputConnections=_UNSET, ic=_UNSET,
        instanceLeaf=_UNSET, ilf=_UNSET,
        name=_UNSET, n=_UNSET,
        parentOnly=_UNSET, po=_UNSET,
        renameChildren=_UNSET, rc=_UNSET,
        returnRootsOnly=_UNSET, rr=_UNSET,
        smartTransform=_UNSET, st=_UNSET,
        transformsOnly=_UNSET, to=_UNSET,
        upstreamNodes=_UNSET, un=_UNSET,
        query=_UNSET, q=_UNSET,
        edit=_UNSET, e=_UNSET,
        **kwargs):
    """指定したノードを複製し、対応する mlib wrapper として返す。

    フラグの ``_UNSET`` は省略判定専用。省略したフラグはMayaへ渡さず、Mayaの既定動作を保つ。
    長名と短名の同時指定は入力解決やUndo開始の前に拒否する。対応しないMaya版のフラグはMayaが拒否する。

    Args:
        node (object): 複製元のNode・Plug・Component・API参照または名前。Mayaへ渡す一意な名前へ変換する。
        fullPath (bool): Mayaの複製結果を完全DAGパスで受け取る指定。mlibの戻り型は変わらない。
        f (bool): fullPathの短縮名。同時指定はできない。
        inputConnections (bool): 入力接続も複製する指定。
        ic (bool): inputConnectionsの短縮名。同時指定はできない。
        instanceLeaf (bool): 末端ノードを複製せずインスタンス化する指定。
        ilf (bool): instanceLeafの短縮名。同時指定はできない。
        name (str): Mayaへ渡すノード名。
        n (str): nameの短縮名。同時指定はできない。
        parentOnly (bool): 指定した対象だけを複製し、子階層を含めない指定。
        po (bool): parentOnlyの短縮名。同時指定はできない。
        renameChildren (bool): 複製した子の名前をMayaの規則で補正する指定。
        rc (bool): renameChildrenの短縮名。同時指定はできない。
        returnRootsOnly (bool): Maya側の戻り値を複製ルートだけにする指定。mlibは先頭をラップする。
        rr (bool): returnRootsOnlyの短縮名。同時指定はできない。
        smartTransform (bool): 前回の複製からの変換差を使うMayaの複製指定。
        st (bool): smartTransformの短縮名。同時指定はできない。
        transformsOnly (bool): Transformのみを複製するMayaフラグ。
        to (bool): transformsOnlyの短縮名。同時指定はできない。
        upstreamNodes (bool): 上流の依存ノードも複製する指定。
        un (bool): upstreamNodesの短縮名。同時指定はできない。
        query (bool): 照会モード。コマンドが対応しない場合はMayaが拒否する。
        q (bool): queryの短縮名。同時指定はできない。
        edit (bool): 編集モード。コマンドが対応しない場合はMayaが拒否する。
        e (bool): editの短縮名。同時指定はできない。
        **kwargs (object): 今後追加される未知のMayaフラグ。そのままMayaへ渡す。

    Returns:
        Node: 複製された起点ノードに対応するラッパー。

    Raises:
        TypeError: 長名・短名を同時指定した場合、またはnodeが対応しない型の場合。
        ValueError: node が空文字列・存在しない名前・複数に一致する名前、または削除済みの対象の場合。
        RuntimeError: Maya が複製を拒否した場合。
    """
    _merge_flags(kwargs, (
        (fullPath, f, "fullPath", "f"),
        (inputConnections, ic, "inputConnections", "ic"),
        (instanceLeaf, ilf, "instanceLeaf", "ilf"),
        (name, n, "name", "n"),
        (parentOnly, po, "parentOnly", "po"),
        (renameChildren, rc, "renameChildren", "rc"),
        (returnRootsOnly, rr, "returnRootsOnly", "rr"),
        (smartTransform, st, "smartTransform", "st"),
        (transformsOnly, to, "transformsOnly", "to"),
        (upstreamNodes, un, "upstreamNodes", "un"),
        (query, q, "query", "q"),
        (edit, e, "edit", "e"),
    ))
    with undoChunk("mlibDuplicate"):
        # nodesはcmdsを参照するため、循環importを避けて関数内で読み込む。
        from ..core.object import Object as _InputObject
        from ..nodes import Node

        name = _InputObject._input_name(node)
        result = cmds.duplicate(name, **kwargs)
        return Node(result[0])
