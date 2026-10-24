"""
Synopsis
--------

.. code-block:: python

    mlib.createNode(type, fast=False, **kwargs)

指定した Maya ノードを作成し、型に応じた mlib ラッパーを返します。

作成操作です。Maya の Undo に対応します。照会・編集用コマンドではありません。

``fast=True`` は対応する範囲をAPI 2.0で直接変更し、Undo履歴を追加しません。
未対応条件は変更前に拒否します。詳細は関数のdocstringを参照してください。

Return value
------------

``Node``
    作成したノードに対応するラッパー。

Related commands
----------------

:doc:`ls <../ls/index>` / :meth:`~mlib.nodes.transform.Transform.addConstraint`

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
   * - ``type``
     - ``str``
     - 必須
     - 作成する Maya ノード型名。
   * - ``name (n)``
     - ``str``
     - Maya の既定値
     - ノード名。maya.cmds.createNode へ渡します。
   * - ``parent (p)``
     - ``Node | Plug | Component | str | MObject | MDagPath | MPlug``
     - Maya の既定値
     - 親ノード。所有ノードの完全パスに変換して maya.cmds.createNode へ渡します。Plug と ``"node.attribute"`` は所有ノード、Component は所有シェイプを親にします。受け付ける型は :doc:`/cmds_interop` を参照。
   * - ``**kwargs``
     - ``object``
     - 省略可
     - その他の createNode フラグをそのまま渡します。

Examples
--------

.. code-block:: python

    import mlib

    node = mlib.createNode("transform", name="example")
    print(node.getFullName())
"""

from contextlib import nullcontext

from ..decorator import undoChunk
from ..util import _ArgumentError, _UNSET


def createNode(type, *, fast=False,
        name=_UNSET, n=_UNSET,
        parent=_UNSET, p=_UNSET,
        shared=_UNSET, s=_UNSET,
        skipSelect=_UNSET, ss=_UNSET,
        query=_UNSET, q=_UNSET,
        edit=_UNSET, e=_UNSET,
        **kwargs):
    """Mayaノードを作成し、実際の型に対応するラッパーを返す。

    フラグの ``_UNSET`` は省略判定専用。省略したフラグはMayaへ渡さず、Mayaの既定動作を保つ。
    長名と短名の同時指定は入力解決やUndo開始の前に拒否する。対応しないMaya版のフラグはMayaが拒否する。

    Args:
        type (str): Mayaノード型名。
        fast (bool): TrueはOpenMaya直接更新でUndoなし。既定Falseは通常処理。
        name (str): Mayaへ渡すノード名。
        n (str): nameの短縮名。同時指定はできない。
        parent (object): 親ノード。Node・Plug・Component・API参照は所有ノードの完全パスへ変換する。
        p (object): parentの短縮名。同時指定はできない。
        shared (bool): 同名の共有ノードがある場合のMaya標準の共有指定。
        s (bool): sharedの短縮名。同時指定はできない。
        skipSelect (bool): 作成したノードを選択しない指定。
        ss (bool): skipSelectの短縮名。同時指定はできない。
        query (bool): 照会モード。コマンドが対応しない場合はMayaが拒否する。
        q (bool): queryの短縮名。同時指定はできない。
        edit (bool): 編集モード。コマンドが対応しない場合はMayaが拒否する。
        e (bool): editの短縮名。同時指定はできない。
        **kwargs (object): 通常処理では追加のMayaフラグをそのまま渡す。
            fast=Trueでは対応しないフラグを作成前に拒否する。

    Returns:
        Node: 作成したノードのラッパー。

    Raises:
        TypeError: 長名・短名の同時指定、fastがbool以外、またはparentが対応しない型の場合。
        ValueError: parent が空文字列、または削除済みの対象の場合。
        RuntimeError: parent を解決できない場合、またはMayaが作成を拒否した場合。
        NotImplementedError: fast=Trueで未対応のフラグを指定した場合。
    """
    if name is not _UNSET:
        if n is not _UNSET:
            raise _ArgumentError("Specify only one of 'name' and 'n'")
        kwargs["name"] = name
    elif n is not _UNSET:
        kwargs["name"] = n
    if parent is not _UNSET:
        if p is not _UNSET:
            raise _ArgumentError("Specify only one of 'parent' and 'p'")
        kwargs["parent"] = parent
    elif p is not _UNSET:
        kwargs["parent"] = p
    if shared is not _UNSET:
        if s is not _UNSET:
            raise _ArgumentError("Specify only one of 'shared' and 's'")
        kwargs["shared"] = shared
    elif s is not _UNSET:
        kwargs["shared"] = s
    if skipSelect is not _UNSET:
        if ss is not _UNSET:
            raise _ArgumentError("Specify only one of 'skipSelect' and 'ss'")
        kwargs["skipSelect"] = skipSelect
    elif ss is not _UNSET:
        kwargs["skipSelect"] = ss
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
    if not isinstance(fast, bool):
        raise TypeError("fast must be a bool")
    with nullcontext() if fast else undoChunk("mlib.cmds.createNode.createNode"):
        from ..nodes import Node

        return Node.create(type, **kwargs, fast=fast)
