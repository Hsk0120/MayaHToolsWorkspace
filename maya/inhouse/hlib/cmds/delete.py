"""
Synopsis
--------

.. code-block:: python

    hlib.delete(nodes)

指定したノードを削除します。

削除操作です。Maya の Undo に対応します。照会・編集用コマンドではありません。

Return value
------------

``None``
    値を返しません。

Related commands
----------------

:doc:`duplicate <../duplicate/index>` / :doc:`objExists <../objExists/index>`

Flags
-----

位置引数のみです。括弧内は Maya に渡せる短縮名です（該当なし）。

.. list-table::
   :header-rows: 1
   :widths: 20 25 15 40

   * - 引数
     - 型
     - 既定値
     - 説明
   * - ``nodes``
     - ``Node | str | Iterable[Node | str]``
     - 必須
     - 削除するノード、またはその列。

Examples
--------

.. code-block:: python

    import hlib

    node = hlib.createNode("transform", name="example")
    hlib.delete(node)
"""

from ..decorators.undo import undo_chunk

import maya.cmds as cmds


@undo_chunk("hlib.cmds.delete.delete")
def delete(nodes):
    """指定したノードを削除する。

    Args:
        nodes (Node | str | Iterable[Node | str]): 削除するノード、またはその列。

    Returns:
        None: 値を返さない。

    Raises:
        ValueError: nodes が空、または要素が空文字列の場合。
        TypeError: 要素が Node/str 以外の場合。
        RuntimeError: Maya が削除を拒否した場合。
    """
    from .._core.coerce import to_names

    names = to_names(nodes)
    if not names:
        raise ValueError("nodes には1つ以上のノードを指定してください")
    cmds.delete(*names)
