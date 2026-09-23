"""
Synopsis
--------

.. code-block:: python

    hlib.createNode(type, **kwargs)

指定した Maya ノードを作成し、型に応じた hlib ラッパーを返します。

作成操作です。Maya の Undo に対応します。照会・編集用コマンドではありません。

Return value
------------

``Node``
    作成したノードに対応するラッパー。

Related commands
----------------

:doc:`ls <../ls/index>` / :doc:`constraint <../constraint/index>`

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
   * - ``type``
     - ``str``
     - 必須
     - 作成する Maya ノード型名。
   * - ``name (n)``
     - ``str``
     - Maya の既定値
     - ノード名。maya.cmds.createNode へ渡します。
   * - ``parent (p)``
     - ``str``
     - Maya の既定値
     - 親ノード名。maya.cmds.createNode へ渡します。
   * - ``**kwargs``
     - ``object``
     - 省略可
     - その他の createNode フラグをそのまま渡します。

Examples
--------

.. code-block:: python

    import hlib

    node = hlib.createNode("transform", name="example")
    print(node.full_name)
"""

def createNode(type, **kwargs):
    """Mayaノードを作成し、対応するhlib wrapperとして返す。"""
    from ..nodes import Node

    return Node.create(type, **kwargs)
