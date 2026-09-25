"""
Synopsis
--------

.. code-block:: python

    hlib.constraint(sources, target, type="parent", maintainOffset=False)

拘束元 sources から拘束先 target へのコンストレイントを作成します。選択状態は使用しません。

作成操作は1回の Undo で戻せます。照会・編集モードはありません。短縮フラグは typ / mo を使用できます。poleVector は RP IK ハンドル、geometry / normal / pointOnPoly は適切な形状、tangent は NURBS カーブが必要です。

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
     - parent、point、orient、scale、aim の作成時に相対関係を維持します。他の型では使用しません。

Examples
--------

.. code-block:: python

    import hlib

    source = hlib.createNode("transform", name="source")
    target = hlib.createNode("transform", name="target")
    result = hlib.constraint(source, target, type="point", maintainOffset=True)
"""

from .._core.flags import flag_aliases

from ..decorators.undo import undo_chunk

@flag_aliases(typ="type", mo="maintainOffset")
@undo_chunk("hlib.cmds.constraint.constraint")
def constraint(sources, target, type="parent", maintainOffset=False):
    """拘束元から対象へのコンストレイントを作成する。

    Args:
        sources (Node | str | Iterable[Node | str]): 拘束元。
        target (Node | str): 拘束されるTransformまたはIkHandle。
        type (str): parent等の型名。既定parent。短縮typ。
        maintainOffset (bool): parent/point/orient/scale/aimで相対関係を維持する。他の型では未使用。短縮mo。
    Returns:
        Constraint: 作成またはターゲット追加された拘束ノード。
    Raises:
        ValueError: 未対応型・空の拘束元の場合。
        TypeError: 入力の型が不正な場合。
        AttributeError: targetにadd_constraintがない場合。
        RuntimeError: Mayaが作成またはフラグを拒否した場合。

    長名と短名の同時指定はTypeError。"""
    from .._core.coerce import to_node

    target_node = to_node(target)
    return target_node.add_constraint(
        sources,
        type=type,
        maintainOffset=maintainOffset,
    )
