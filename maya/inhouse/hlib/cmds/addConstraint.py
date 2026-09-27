"""拘束元から対象へコンストレイントを追加する。

``hlib.addConstraint(sources, target, type="parent", maintainOffset=False)``
で単一のConstraintを返す。照会はConstraint.targets()/weight_plugs()、
ウェイト編集はset_weight()、他の属性はPlugで操作する。query/editは受け付けない。
種類はparent、point、orient、scale、aim、poleVector、geometry、normal、tangent、
pointOnPoly。Constraint接尾辞付きの型名も指定できる。
"""

from .._core.flags import flag_aliases
from ..decorators.undo import undo_chunk


@flag_aliases(typ="type", mo="maintainOffset")
@undo_chunk("hlib.cmds.addConstraint")
def addConstraint(sources, target, type="parent", maintainOffset=False, **kwargs):
    """対象へ拘束を追加する。選択状態から対象を補完しない。

    Args:
        sources (Node | Plug | Component | str | MObject | MDagPath | MPlug | Iterable):
            拘束元。属性は所有ノード、コンポーネントは所有シェイプへ解決する。
            parent/point/orient/scale/aim/poleVectorはTransformの拘束元が必要。
        target (Node | Plug | str | MObject | MDagPath | MPlug): 拘束されるTransform。
        type (str): 拘束の種類。短名typ。既定parent。
        maintainOffset (bool): 相対関係を維持する。短名mo。
        **kwargs (object): aimVector/worldUpObject等の作成フラグ。長短名を使用可能。

    Returns:
        Constraint: 作成または拘束元を追加したノード。

    Raises:
        TypeError: 入力型が不正、長短フラグが重複、またはTransformでない場合。
        ValueError: 未対応の種類、空の拘束元、照会・編集モードを指定した場合。
        RuntimeError: 対象が無効、またはMayaが操作を拒否した場合。
    """
    from .._core.coerce import to_node
    from ..nodes.transform import Transform

    target_node = to_node(target)
    if not isinstance(target_node, Transform):
        raise TypeError("target must resolve to a Transform")
    return target_node.add_constraint(sources, type=type, maintainOffset=maintainOffset, **kwargs)
