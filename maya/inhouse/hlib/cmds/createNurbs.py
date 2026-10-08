"""MayaのCreate > NURBS Primitivesに対応する形状を生成する。

``type`` (短名 ``typ``) はcircle（既定）、square、sphere、cube、cylinder、
cone、plane、torus。nurbsSquare、nurbsCube、nurbsPlaneというコマンド名も使用可能。
各Mayaコマンドの長名・短名フラグで寸法や履歴を指定する。
circleはNurbsCurve、単一曲面はNurbsSurface、squareは4本のNurbsCurveのリスト、
cubeは6枚のNurbsSurfaceのリストを返す。nameは最上位Transformの名前。
query/edit、object=False、polygonによる非NURBS出力は受け付けない。
生成全体を1回のUndoで戻せる。
"""

import maya.cmds as cmds

from .._core.flags import flag_aliases, normalize_flags
from ..decorator import undoChunk

_PRIMITIVES = {
    "circle": "circle",
    "square": "nurbsSquare",
    "sphere": "sphere",
    "cube": "nurbsCube",
    "cylinder": "cylinder",
    "cone": "cone",
    "plane": "nurbsPlane",
    "torus": "torus",
}


@flag_aliases(typ="type")
@undoChunk("hlib.cmds.createNurbs")
def createNurbs(type="circle", **kwargs):
    """種類を指定してNURBSプリミティブのシェイプを生成する。

    Args:
        type (str): 形状の種類またはMayaコマンド名。既定circle。短名typ。
        **kwargs (object): 寸法・名前・履歴等の生成フラグ。長短名の重複は拒否する。

    Returns:
        NurbsCurve | NurbsSurface | list[NurbsCurve] | list[NurbsSurface]:
            cube/squareは全構成シェイプのリスト、他は単一シェイプ。
            履歴設定によって戻り値の形式は変わらない。

    Raises:
        TypeError: typeが文字列でない、またはフラグが重複する場合。
        ValueError: 未対応の種類・モード、非NURBS出力を指定した場合。
        RuntimeError: Mayaが生成を拒否する、またはシェイプを取得できない場合。
    """
    from ..nodes.node import Node
    from ..nodes.nurbsCurve import NurbsCurve
    from ..nodes.nurbsSurface import NurbsSurface

    if not isinstance(type, str):
        raise TypeError("type must be a string")
    command = _PRIMITIVES.get(type, type)
    if command not in _PRIMITIVES.values():
        raise ValueError("Unsupported NURBS primitive: " + type)
    options = normalize_flags(command, kwargs)
    if options.get("query") or options.get("edit"):
        raise ValueError("createNurbs supports creation only")
    if not options.get("object", True):
        raise ValueError("createNurbs requires object=True")
    curves = command in {"circle", "nurbsSquare"}
    if not curves:
        if options.get("polygon", 0) != 0:
            raise ValueError("createNurbs requires polygon=0 (NURBS)")
        options["polygon"] = 0
    result = getattr(cmds, command)(**options)
    kind = "nurbsCurve" if curves else "nurbsSurface"
    shapes = [
        Node(name)
        for name in (
            cmds.listRelatives(result[0], allDescendents=True, type=kind, fullPath=True) or []
        )
    ]
    expected = NurbsCurve if curves else NurbsSurface
    if not shapes or not all(isinstance(shape, expected) for shape in shapes):
        raise RuntimeError("NURBS primitive did not produce expected shapes: " + command)
    return shapes if command in {"nurbsCube", "nurbsSquare"} else shapes[0]
