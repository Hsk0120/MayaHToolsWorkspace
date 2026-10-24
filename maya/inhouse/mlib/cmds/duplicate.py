"""
Synopsis
--------

.. code-block:: python

    mlib.duplicate(node, **kwargs)

指定したノードを複製し、複製された Transform を返します。

作成操作です。Maya の Undo に対応します。照会・編集用コマンドではありません。

Return value
------------

``Node``
    複製の起点ノードに対応するラッパー。``cmds.duplicate`` が複数名を返す場合も
    先頭（複製の起点）だけをラップする。

Related commands
----------------

:doc:`createNode <../createNode/index>` / :doc:`delete <../delete/index>`

Flags
-----

Mayaの長名・短名を受け付けます。同じフラグの長名と短名を同時に渡すと、
処理前に ``TypeError`` になります。戻り値は表記によって変わりません。

位置引数も含めた入力一覧です。括弧内は Maya に渡せる短縮名です。

.. list-table::
   :header-rows: 1
   :widths: 20 25 15 40

   * - 引数 / フラグ
     - 型
     - 既定値
     - 説明
   * - ``node``
     - ``Node | Plug | Component | str | MObject | MDagPath | MPlug``
     - 必須
     - 複製元。1つの対象を指定します(Components などの複数の対象は ``TypeError``)。Plug・Component も一意な名前に変換して渡し、その扱いは maya.cmds.duplicate に従います(:doc:`/cmds_interop` の「コマンドごとの注意」を参照)。
   * - ``name (n)``
     - ``str``
     - Maya の既定値
     - 複製後のノード名。maya.cmds.duplicate へ渡します。
   * - ``**kwargs``
     - ``object``
     - 省略可
     - その他の duplicate フラグをそのまま渡します。

Examples
--------

.. code-block:: python

    import mlib

    node = mlib.createNode("transform", name="example")
    copy = mlib.duplicate(node, name="exampleCopy")
"""

import maya.cmds as cmds

from ..decorator import undoChunk
from ..util import _ArgumentError, _UNSET


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
        ValueError: node が空文字列、または削除済みの対象の場合。
        RuntimeError: Maya が複製を拒否した場合。
    """
    if fullPath is not _UNSET:
        if f is not _UNSET:
            raise _ArgumentError("Specify only one of 'fullPath' and 'f'")
        kwargs["fullPath"] = fullPath
    elif f is not _UNSET:
        kwargs["fullPath"] = f
    if inputConnections is not _UNSET:
        if ic is not _UNSET:
            raise _ArgumentError("Specify only one of 'inputConnections' and 'ic'")
        kwargs["inputConnections"] = inputConnections
    elif ic is not _UNSET:
        kwargs["inputConnections"] = ic
    if instanceLeaf is not _UNSET:
        if ilf is not _UNSET:
            raise _ArgumentError("Specify only one of 'instanceLeaf' and 'ilf'")
        kwargs["instanceLeaf"] = instanceLeaf
    elif ilf is not _UNSET:
        kwargs["instanceLeaf"] = ilf
    if name is not _UNSET:
        if n is not _UNSET:
            raise _ArgumentError("Specify only one of 'name' and 'n'")
        kwargs["name"] = name
    elif n is not _UNSET:
        kwargs["name"] = n
    if parentOnly is not _UNSET:
        if po is not _UNSET:
            raise _ArgumentError("Specify only one of 'parentOnly' and 'po'")
        kwargs["parentOnly"] = parentOnly
    elif po is not _UNSET:
        kwargs["parentOnly"] = po
    if renameChildren is not _UNSET:
        if rc is not _UNSET:
            raise _ArgumentError("Specify only one of 'renameChildren' and 'rc'")
        kwargs["renameChildren"] = renameChildren
    elif rc is not _UNSET:
        kwargs["renameChildren"] = rc
    if returnRootsOnly is not _UNSET:
        if rr is not _UNSET:
            raise _ArgumentError("Specify only one of 'returnRootsOnly' and 'rr'")
        kwargs["returnRootsOnly"] = returnRootsOnly
    elif rr is not _UNSET:
        kwargs["returnRootsOnly"] = rr
    if smartTransform is not _UNSET:
        if st is not _UNSET:
            raise _ArgumentError("Specify only one of 'smartTransform' and 'st'")
        kwargs["smartTransform"] = smartTransform
    elif st is not _UNSET:
        kwargs["smartTransform"] = st
    if transformsOnly is not _UNSET:
        if to is not _UNSET:
            raise _ArgumentError("Specify only one of 'transformsOnly' and 'to'")
        kwargs["transformsOnly"] = transformsOnly
    elif to is not _UNSET:
        kwargs["transformsOnly"] = to
    if upstreamNodes is not _UNSET:
        if un is not _UNSET:
            raise _ArgumentError("Specify only one of 'upstreamNodes' and 'un'")
        kwargs["upstreamNodes"] = upstreamNodes
    elif un is not _UNSET:
        kwargs["upstreamNodes"] = un
    if query is not _UNSET:
        if q is not _UNSET:
            raise _ArgumentError("Specify only one of 'query' and 'q'")
        kwargs["query"] = query
    elif q is not _UNSET:
        kwargs["query"] = q
    if edit is not _UNSET:
        if e is not _UNSET:
            raise _ArgumentError("Specify only one of 'edit' and 'e'")
        kwargs["edit"] = edit
    elif e is not _UNSET:
        kwargs["edit"] = e
    with undoChunk("mlib.cmds.duplicate.duplicate"):
        from ..core.object import Object as _InputObject
        from ..nodes import Node

        name = _InputObject._input_name(node)
        result = cmds.duplicate(name, **kwargs)
        return Node(result[0])
