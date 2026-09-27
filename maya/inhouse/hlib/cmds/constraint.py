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
     - ``Node | Plug | Component | Components | str | MObject | MDagPath | MPlug | Iterable``
     - 必須
     - 拘束元のノードまたはノード列。文字列も含めて所有ノードへ解決し、Plug・MPlug・``"node.attribute"`` は所有ノード、Component・Components・``"pCube1.vtx[0]"`` は所有シェイプとして扱います（:doc:`/cmds_interop`）。parent、point、orient、scale、aim、poleVector では拘束元が Transform（joint・IkHandle を含む）に解決される必要があり、シェイプ（シェイプの Plug、Component などの所有シェイプ）や DG ノードは ``TypeError`` です（maya.cmds はターゲットの無い、追従しない拘束を黙って作るため）。シェイプ・Component を使えるのは geometry、normal、tangent、pointOnPoly です。削除済みの対象は ``RuntimeError``、``deleteAttr`` で属性が削除された Plug・MPlug は ``ValueError`` (``RuntimeError`` としても捕捉できます)です。
   * - ``target``
     - ``Node | Plug | Component | str | MObject | MDagPath | MPlug``
     - 必須
     - 拘束される Transform または IkHandle。sources と同じ型を受け付けます。解決したノードが
       Transform でない場合(シェイプ、Component の所有シェイプなど)は ``TypeError``。
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
        sources (Node | str | Plug | Component | Components | om2.MObject | om2.MDagPath | om2.MPlug | Iterable):
            拘束元。Plug・MPlug・``"node.attribute"`` は所有ノード、Component・
            ``"pCube1.vtx[0]"`` は所有シェイプとして扱う。parent/point/orient/scale/aim/
            poleVector では Transform(joint・IkHandle を含む)に解決される必要がある。
        target (Node | str | Plug | Component | om2.MObject | om2.MDagPath | om2.MPlug):
            拘束されるTransformまたはIkHandle。
        type (str): parent等の型名。既定parent。短縮typ。
        maintainOffset (bool): parent/point/orient/scale/aimで相対関係を維持する。他の型では未使用。短縮mo。
    Returns:
        Constraint: 作成またはターゲット追加された拘束ノード。
    Raises:
        ValueError: 未対応型・空の拘束元の場合。拘束元・拘束先に、所有ノードは有効で属性が
            ``deleteAttr`` で削除済みの Plug・MPlug を渡した場合
            (``hlib._core.coerce.DeletedAttributeError``。RuntimeError の派生でもある)。
        TypeError: 入力の型が不正な場合、target が Transform(IkHandle・joint を含む)に
            解決されない場合(シェイプや Component の所有シェイプなど)、または
            parent/point/orient/scale/aim/poleVector の拘束元が Transform に解決されない場合。
        RuntimeError: 拘束元・拘束先を解決できない(存在しない、複数の対象に一致する、
            削除済みの)場合、またはMayaが作成またはフラグを拒否した場合。

    長名と短名の同時指定はTypeError。"""
    from .._core.coerce import to_node
    from ..nodes.transform import Transform

    target_node = to_node(target)
    if not isinstance(target_node, Transform):
        raise TypeError(
            f"target には Transform(joint・IkHandle を含む)を指定してください: "
            f"{target_node.__class__.__name__} {target_node.name()!r}"
        )
    return target_node.add_constraint(
        sources,
        type=type,
        maintainOffset=maintainOffset,
    )
