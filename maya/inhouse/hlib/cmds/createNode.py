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

:doc:`ls <../ls/index>` / :doc:`constraint <../addConstraint/index>`

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

    import hlib

    node = hlib.createNode("transform", name="example")
    print(node.fullName())
"""

from .._core.flags import flag_aliases

from ..decorators.undo import undoChunk

@flag_aliases("createNode")
@undoChunk("hlib.cmds.createNode.createNode")
def createNode(type, **kwargs):
    """Mayaノードを作成し、実際の型に対応するラッパーを返す。

    Args:
        type (str): Mayaノード型名。
        **kwargs (object): maya.cmds.createNodeへ渡すフラグ。parent(p)はノードが必要な
            引数として所有ノードの完全パスへ変換する(Plug・MPlug・"node.attribute" は
            所有ノード、Component は所有シェイプ)。
    Returns:
        Node: 作成したノードのラッパー。
    Raises:
        TypeError: parent が対応しない型の場合。
        ValueError: parent が空文字列、または削除済みの対象の場合。
        RuntimeError: parent を解決できない場合、またはMayaが作成を拒否した場合。"""
    from ..nodes import Node

    return Node.create(type, **kwargs)
