"""
Synopsis
--------

.. code-block:: python

    hlib.group(nodes=None, **kwargs)

指定したノードをまとめる新規 Transform を作成し、そのラッパーを返します。
``nodes`` を省略すると maya.cmds.group と同じく現在の選択をグループ化します。
空のグループを作る場合は ``empty=True`` を指定してください（``nodes`` 省略かつ
選択も無い状態で ``empty`` も指定しないと Maya が RuntimeError を送出します）。

作成操作です。Maya の Undo に対応します。照会・編集用コマンドではありません。

Return value
------------

``Node``
    作成したグループの Transform ラッパー。

Related commands
----------------

:doc:`createNode <../createNode/index>` / :doc:`duplicate <../duplicate/index>`

Flags
-----

位置引数も含めた入力一覧です。括弧内は Maya に渡せる短縮名です。

.. list-table::
   :header-rows: 1
   :widths: 20 25 15 40

   * - 引数 / フラグ
     - 型
     - 既定値
     - 説明
   * - ``nodes``
     - ``Node | str | Iterable[Node | str] | None``
     - None
     - グループ化するノード。None は現在の選択を使う。
   * - ``name (n)``
     - ``str``
     - Maya の既定値
     - グループ名。maya.cmds.group へ渡します。
   * - ``world (w)``
     - ``bool``
     - False
     - ワールド直下にグループを作成します。
   * - ``empty (em)``
     - ``bool``
     - False
     - True で空のグループを作成します（nodes 指定時と併用不可）。
   * - ``**kwargs``
     - ``object``
     - 省略可
     - その他の group フラグをそのまま渡します。

Examples
--------

.. code-block:: python

    import hlib

    a = hlib.createNode("transform", name="a")
    b = hlib.createNode("transform", name="b")
    parent = hlib.group([a, b], name="grp")
    empty = hlib.group(name="emptyGrp", world=True, empty=True)
"""

from ..decorators.undo import undo_chunk

import maya.cmds as cmds


@undo_chunk("hlib.cmds.group.group")
def group(nodes=None, **kwargs):
    """指定したノードを新規 Transform でグループ化し、そのラッパーを返す。

    Args:
        nodes (Node | str | Iterable[Node | str] | None): グループ化するノード。
            None は maya.cmds.group と同じく現在の選択を使う。空のグループを
            作る場合は kwargs に empty=True を指定する。
        **kwargs (object): maya.cmds.group に渡すキーワード引数。

    Returns:
        Node: 作成したグループの Transform ラッパー。

    Raises:
        TypeError: nodes の要素が Node/str 以外の場合。
        ValueError: nodes の要素に空文字列が含まれる場合。
        RuntimeError: Maya がグループ作成を拒否した場合。
    """
    from ..nodes import Node
    from .._core.coerce import to_names

    if nodes is None:
        result = cmds.group(**kwargs)
        return Node(result)
    names = to_names(nodes)
    result = cmds.group(*names, **kwargs)
    return Node(result)
