"""
Synopsis
--------

.. code-block:: python

    hlib.cmds.constraint(sources, target, type="parent", maintainOffset=False)

拘束元 sources から拘束先 target へのコンストレイントを作成します。選択状態は使用しません。

作成操作は1回の Undo で戻せます。照会・編集モードや短縮フラグはありません。poleVector は RP IK ハンドル、geometry / normal / pointOnPoly は適切な形状、tangent は NURBS カーブが必要です。

Return value
------------

``Constraint``
    作成したコンストレイントの具象ラッパー。既存の拘束へターゲットが追加される場合はそのラッパー。

Related commands
----------------

:doc:`createNode <../createNode/index>` / :doc:`ls <../ls/index>`

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
   * - ``sources``
     - ``Node | str | Iterable[Node | str]``
     - 必須
     - 拘束元のノードまたはノード列。
   * - ``target``
     - ``Node | str``
     - 必須
     - 拘束される Transform または IkHandle。
   * - ``type``
     - ``str``
     - "parent"
     - parent、point、orient、scale、aim、poleVector、geometry、normal、tangent、pointOnPoly。Constraint 接尾辞付きの型名も使用可能。
   * - ``maintainOffset``
     - ``bool``
     - False
     - parent、point、orient、scale、aim の作成時に相対関係を維持します。他の型では使用されません。

Examples
--------

.. code-block:: python

    import hlib

    source = hlib.cmds.createNode("transform", name="source")
    target = hlib.cmds.createNode("transform", name="target")
    result = hlib.cmds.constraint(source, target, type="point", maintainOffset=True)
"""

def constraint(sources, target, type="parent", maintainOffset=False):
    """ソースノードからターゲットノードへのコンストレイントを作成する。"""
    from .._core.coerce import to_node

    target_node = to_node(target)
    return target_node.add_constraint(
        sources,
        type=type,
        maintainOffset=maintainOffset,
    )
