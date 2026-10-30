"""形状座標の照会と通常/fast更新。通常はcmds、fastは履歴なし形状へ直接書く。"""

from collections import namedtuple

import maya.api.OpenMaya as om2
import maya.cmds as cmds

from ..maths.vector import _vectors_of_points
from ..util import _finite_vector
from .fastWrite import require_writable

#: 点として受け付ける、wを持つom2の型。XYZだけを使い、wでは割らない。
_OM2_POINTS = (om2.MPoint, om2.MFloatPoint)

#: :func:`geometry` の戻り値。保持DAGパス・関数セット・Meshかどうか。
_Geometry = namedtuple("_Geometry", ("path", "fn", "is_mesh"))


def geometry(shape, indices, edit=False):
    """Shapeの保持DAGパスと関数セットを取得し、必要なら直接編集の前提を検査する。

    呼出し側がShape型と番号範囲を検証済みであることを前提とする。edit=Trueでは
    周期カーブ、inMesh/createへの入力、Shapeノードのロックを検査する。
    指定点のpnts/controlPointsとその子についても、上位を含むロック・入力接続と、各対象アトリビュートの書込み可否を調べる。
    indicesが空のUV更新では、点Plugごとの検査は行わない。

    Args:
        shape (Mesh | NurbsCurve): 型を解決済みのShapeラッパー。
        indices (Iterable[int]): 範囲検証済みのAPI点番号。UV番号ではない。
        edit (bool): Trueで直接編集の制限を検査する。Falseは照会用。

    Returns:
        _Geometry: ``path`` (保持DAGパス)・``fn`` (MFnMeshまたはMFnNurbsCurve)・``is_mesh`` (MeshならTrue)
            のnamedtuple。tupleとして展開できる。関数セットの取得自体では座標を書き換えない。

    Raises:
        RuntimeError: 直接編集時のロック・入力接続・書込み禁止、またはShapeを参照できない場合。
        NotImplementedError: edit=Trueで周期カーブまたはinMesh/create入力がある場合。
    """
    path = shape.mpath()
    mesh = path.node().hasFn(om2.MFn.kMesh)
    fn = om2.MFnMesh(path) if mesh else om2.MFnNurbsCurve(path)
    if edit:
        if not mesh and fn.form == om2.MFnNurbsCurve.kPeriodic:
            raise NotImplementedError("fast edits of periodic curves are not supported")
        dependency = om2.MFnDependencyNode(path.node())
        source = dependency.findPlug("inMesh" if mesh else "create", False)
        if source.isDestination:
            raise NotImplementedError("fast geometry edits require a shape without input history")
        if dependency.isLocked:
            raise RuntimeError("Shape node is locked")
        points = dependency.findPlug("pnts" if mesh else "controlPoints", False)
        for index in indices:
            point = points.elementByLogicalIndex(index)
            require_writable(point)
            for child in range(point.numChildren()):
                require_writable(point.child(child))
    return _Geometry(path, fn, mesh)


def _points(shape, indices, ws=False):
    """指定した点のom2.MPointを保持順に返す。単点では全点を取得しない。

    Args:
        shape (Shape): 有効なMeshまたはNurbsCurve。
        indices (Sequence[int]): 検証済みの点番号。
        ws (bool): Trueならワールド空間へ変換する。

    Returns:
        Iterable[om2.MPoint]: 指定順の点。距離はcm。
    """
    path, fn, mesh = geometry(shape, indices)
    space = om2.MSpace.kWorld if ws else om2.MSpace.kObject
    if len(indices) == 1:
        if mesh:
            return [fn.getPoint(indices[0], space)]
        return [fn.cvPosition(indices[0], space)]
    all_points = fn.getPoints(space) if mesh else fn.cvPositions(space)
    return (all_points[i] for i in indices)


def positions(shape, indices, ws=False):
    """指定した点を保持順・cm単位のtupleで取得する(内部の座標計算用)。

    Args:
        shape (Shape): 有効なMeshまたはNurbsCurve。
        indices (Sequence[int]): 検証済みの点番号。
        ws (bool): Trueならワールド空間へ変換する。

    Returns:
        list[tuple[float, float, float]]: 指定順の座標。単点では全点を取得しない。
    """
    return [(point.x, point.y, point.z) for point in _points(shape, indices, ws)]


def vectors(shape, indices, ws=False):
    """指定した点を保持順・cm単位の :class:`~mlib.maths.vector.Vector` で取得する。

    Args:
        shape (Shape): 有効なMeshまたはNurbsCurve。
        indices (Sequence[int]): 検証済みの点番号。
        ws (bool): Trueならワールド空間へ変換する。

    Returns:
        list[Vector]: 指定順の新しい座標値。CVのwでは割らない。
    """
    return _vectors_of_points(_points(shape, indices, ws))


def command_indices(shape, indices):
    """検証済みのAPI番号をcmds用番号へ写す。順序と重複は維持する。

    Args:
        shape (Shape): MeshまたはNurbsCurve。
        indices (Sequence[int]): APIの番号。

    Returns:
        list[int]: 周期カーブでは末尾の重複CVを先頭の独立CVへ写した番号。
    """
    _, fn, mesh = geometry(shape, indices)
    if not mesh and fn.form == om2.MFnNurbsCurve.kPeriodic:
        return [index % (fn.numCVs - fn.degree) for index in indices]
    return list(indices)


def set_positions(shape, indices, values, ws=False, *, fast=False):
    """検証済みのcm座標を書き込む。Undo範囲は呼出元が管理する。

    Args:
        shape (Shape): MeshまたはNurbsCurve。
        indices (Sequence[int]): 検証済みのAPI番号。重複は後の値を優先。
        values (Sequence[Sequence[float]]): 番号と同数の有限なXYZ。
        ws (bool): Trueならワールド座標。
        fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

    Returns:
        None: 値を返さない。

    Raises:
        RuntimeError: Mayaが書込みを拒否した場合。完了済みの変更は戻さない。
        NotImplementedError: fastで未対応の形状の場合。
    """
    if not indices:
        return
    if fast:
        _set_positions_fast(shape, indices, values, ws)
        return
    _, _, mesh = geometry(shape, indices)
    if ws and not mesh:
        values = object_positions(shape, indices, values)
        ws = False
    numbers = command_indices(shape, indices)
    name, token = shape.getFullName(), "vtx" if mesh else "cv"
    unit = om2.MDistance.uiUnit()
    for index, value in zip(numbers, values):
        coordinates = [om2.MDistance(v).asUnits(unit) for v in value]
        cmds.xform(f"{name}.{token}[{index}]", absolute=True,
                   translation=coordinates, worldSpace=ws, objectSpace=not ws)


def _set_positions_fast(shape, indices, values, ws=False):
    """検証済みのcm座標をOpenMayaで一括設定する。CVのwは変更しない。

    Args:
        shape (Shape): 履歴なしMeshまたは非周期NurbsCurve。
        indices (Sequence[int]): 検証済みの番号。
        values (Sequence[Sequence[float]]): 設定するXYZ。
        ws (bool): TrueならAPIワールド座標、Falseならローカル座標。

    Returns:
        None: 値を返さない。

    Raises:
        ValueError: ワールド空間で変換マトリクスが特異な場合。
        RuntimeError: ロック・入力接続・書込み禁止がある場合。
        NotImplementedError: 周期カーブまたは入力履歴のある形状の場合。
    """
    if not indices:
        return
    path, fn, mesh = geometry(shape, indices, edit=True)
    points = fn.getPoints() if mesh else fn.cvPositions()
    transform = path.inclusiveMatrix()
    if ws and abs(transform.det4x4()) < 1e-12:
        raise ValueError("Cannot edit in world space with a singular transform")
    inverse = transform.inverse() if ws else om2.MMatrix()
    for index, value in zip(indices, values):
        # cvPositions(kWorld)はCVのwもマトリクスの積に使う。同じwで逆変換して往復を保つ。
        point = om2.MPoint(value[0], value[1], value[2], points[index].w) * inverse
        point.w = points[index].w
        points[index] = point
    if mesh:
        fn.setPoints(points)
        fn.updateSurface()
    else:
        fn.setCVPositions(points)
        fn.updateCurve()


def object_positions(shape, indices, values):
    """APIのワールド座標を、CVのウェイトを保持したローカルXYZへ変換する。

    Args:
        shape (Shape): MeshまたはNurbsCurve。
        indices (Sequence[int]): 検証済みの番号。
        values (Sequence[Sequence[float]]): APIのワールドXYZ。距離はcm。

    Returns:
        list[tuple[float, float, float]]: cmdsのobjectSpaceへ渡すcmの座標。

    Raises:
        ValueError: ワールドマトリクスが特異な場合。
    """
    path, fn, mesh = geometry(shape, indices)
    matrix = path.inclusiveMatrix()
    if abs(matrix.det4x4()) < 1e-12:
        raise ValueError("Cannot edit in world space with a singular transform")
    inverse = matrix.inverse()
    if mesh:
        weights = [1.0] * len(indices)
    elif len(indices) == 1:
        weights = [fn.cvPosition(indices[0]).w]
    else:
        cvs = fn.cvPositions()
        weights = [cvs[i].w for i in indices]
    points = [om2.MPoint(row[0], row[1], row[2], weight) * inverse
              for row, weight in zip(values, weights)]
    return [(point.x, point.y, point.z) for point in points]


def point_list(points):
    """点列を検証し、XYZのfloat tupleのリストへ変換する。

    Args:
        points (Iterable[Sequence[float] | om2.MPoint | om2.MVector]): 点列。

    Returns:
        list[tuple[float, float, float]]: 変換済みの点。

    Raises:
        TypeError: 点列が反復できない、または点・成分の型が不正な場合。
        ValueError: 成分数が3でない、または有限でない場合。
    """
    if isinstance(points, (str, bytes)) or isinstance(points, _OM2_POINTS + (om2.MVector,)):
        raise TypeError("points must be an iterable of points")
    try:
        items = list(points)
    except TypeError:
        raise TypeError("points must be an iterable of points") from None
    result = []
    for item in items:
        if isinstance(item, _OM2_POINTS):
            item = (item.x, item.y, item.z)
        elif isinstance(item, (str, bytes)):
            raise TypeError("each point must be a sequence of 3 numbers")
        result.append(_finite_vector(item, 3, "point"))
    return result
