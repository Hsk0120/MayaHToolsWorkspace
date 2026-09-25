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
    print(node.full_name())
"""

from .._core.flags import flag_aliases

from ..decorators.undo import undo_chunk

@flag_aliases("createNode")
@undo_chunk("hlib.cmds.createNode.createNode")
def createNode(type, **kwargs):
    """Mayaノードを作成し、実際の型に対応するラッパーを返す。

    Args:
        type (str): Mayaノード型名。
        **kwargs (object): maya.cmds.createNodeへ渡すフラグ。
    Returns:
        Node: 作成したノードのラッパー。
    Raises:
        RuntimeError: Mayaが作成を拒否した場合。"""
    from ..nodes import Node

    return Node.create(type, **kwargs)
