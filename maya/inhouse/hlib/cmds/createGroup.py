"""
Synopsis
--------

.. code-block:: python

    hlib.createGroup(nodes=None, **kwargs)

指定したノードをまとめる新規 Transform を作成し、そのラッパーを返します。
``nodes`` を省略すると maya.cmds.group と同じく現在の選択をグループ化します。
空のグループを作る場合は ``empty=True`` を指定してください（``nodes`` 省略かつ
選択も無い状態で ``empty`` も指定しないと Maya が RuntimeError を送出します）。
``nodes`` に空の列(``[]`` や空のジェネレーター)を渡すと、現在の選択をグループ化せず
``ValueError`` になります(``empty=True`` を指定した場合を除く)。

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
   * - ``nodes``
     - ``Node | Plug | Component | Components | Selection | str | MObject | MDagPath | MPlug | Iterable | None``
     - None
     - グループ化するノード、またはその列。None は現在の選択を使う。空の列は ``ValueError``。受け付ける型は :doc:`/cmds_interop` を参照。
   * - ``name (n)``
     - ``str``
     - Maya の既定値
     - グループ名。maya.cmds.group へ渡します。
   * - ``parent (p)``
     - ``Node | Plug | Component | str | MObject | MDagPath | MPlug``
     - Maya の既定値
     - グループの親。所有ノードの完全パスに変換して maya.cmds.group へ渡します(Plug は所有ノード)。
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
    parent = hlib.createGroup([a, b], name="grp")
    empty = hlib.createGroup(name="emptyGrp", world=True, empty=True)
"""

from ..decorators.undo import undo_chunk

from .._core.flags import flag_aliases

import maya.cmds as cmds


@flag_aliases("group")
@undo_chunk("hlib.cmds.createGroup.group")
def createGroup(nodes=None, **kwargs):
    """指定したノードを新規 Transform でグループ化し、そのラッパーを返す。

    Args:
        nodes (Node | Plug | Component | Components | Selection | str | om2.MObject | om2.MDagPath | om2.MPlug | Iterable | None):
            グループ化するノード、またはその列。None は maya.cmds.group と同じく
            現在の選択を使う。空のグループを作る場合は kwargs に empty=True を指定する。
        **kwargs (object): maya.cmds.group に渡すキーワード引数。parent はノードが
            必要な引数として所有ノードの完全パスへ変換する(Plug・MPlug は所有ノード)。

    Returns:
        Node: 作成したグループの Transform ラッパー。

    Raises:
        TypeError: nodes または parent の要素が対応しない型の場合。
        ValueError: nodes が空の列の場合(empty=True を除く。現在の選択をグループ化しない
            ため)、または nodes・parent に空文字列や削除済みの対象が含まれる場合。
        RuntimeError: parent の名前を解決できない場合、または Maya がグループ作成を拒否した場合。
    """
    from ..nodes import Node
    from .._core.coerce import to_names, to_node_name

    if kwargs.get("parent") is not None:
        kwargs["parent"] = to_node_name(kwargs["parent"])
    if nodes is None:
        result = cmds.group(**kwargs)
        return Node(result)
    names = to_names(nodes)
    if not names and not kwargs.get("empty"):
        # maya.cmds.group は対象が無いと現在の選択をグループ化するため、明示的に拒否する。
        raise ValueError("グループ化する対象がありません(空のグループは empty=True で作成してください)")
    result = cmds.group(*names, **kwargs)
    return Node(result)
