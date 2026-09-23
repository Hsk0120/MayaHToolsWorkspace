"""
Synopsis
--------

.. code-block:: python

    hlib.cmds.duplicate(node, **kwargs)

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

位置引数も含めた入力一覧です。括弧内は Maya に渡せる短縮名です。

.. list-table::
   :header-rows: 1
   :widths: 20 25 15 40

   * - 引数 / フラグ
     - 型
     - 既定値
     - 説明
   * - ``node``
     - ``Node | str``
     - 必須
     - 複製元のノード。
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

    import hlib

    node = hlib.cmds.createNode("transform", name="example")
    copy = hlib.cmds.duplicate(node, name="exampleCopy")
"""

import maya.cmds as cmds


def duplicate(node, **kwargs):
    """指定したノードを複製し、対応する hlib wrapper として返す。

    Args:
        node (Node | str): 複製元のノード。
        **kwargs (object): maya.cmds.duplicate に渡すキーワード引数。

    Returns:
        Node: 複製された起点ノードに対応するラッパー。

    Raises:
        TypeError: node が Node/str 以外の場合。
        ValueError: node が空文字列の場合。
        RuntimeError: Maya が複製を拒否した場合。
    """
    from ..nodes import Node
    from .._core.coerce import to_name

    name = to_name(node)
    result = cmds.duplicate(name, **kwargs)
    return Node(result[0])
