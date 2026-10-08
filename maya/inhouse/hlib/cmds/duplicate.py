"""
Synopsis
--------

.. code-block:: python

    hlib.duplicate(node, **kwargs)

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

    import hlib

    node = hlib.createNode("transform", name="example")
    copy = hlib.duplicate(node, name="exampleCopy")
"""

import maya.cmds as cmds

from .._core.flags import flag_aliases
from ..decorator import undoChunk


@flag_aliases("duplicate")
@undoChunk("hlib.cmds.duplicate.duplicate")
def duplicate(node, **kwargs):
    """指定したノードを複製し、対応する hlib wrapper として返す。

    Args:
        node (Node | Plug | Component | str | om2.MObject | om2.MDagPath | om2.MPlug): 複製元。Plug・Component も
            一意な名前に変換して渡し、その扱いは maya.cmds.duplicate に従う。
        **kwargs (object): maya.cmds.duplicate に渡すキーワード引数。

    Returns:
        Node: 複製された起点ノードに対応するラッパー。

    Raises:
        TypeError: node が対応しない型の場合。
        ValueError: node が空文字列、または削除済みの対象の場合。
        RuntimeError: Maya が複製を拒否した場合。
    """
    from .._core.object import Object as _InputObject
    from ..nodes import Node

    name = _InputObject._input_name(node)
    result = cmds.duplicate(name, **kwargs)
    return Node(result[0])
