"""形状座標の照会と通常/fast更新。通常はcmds、fastは履歴なし形状へ直接書く。"""

import maya.api.OpenMaya as om2
import maya.cmds as cmds

from .fastWrite import writable


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
        tuple: 保持DAGパス、MFnMeshまたはMFnNurbsCurve、MeshならTrue。
            関数セットの取得自体では座標を書き換えない。

    Raises:
        NotImplementedError: edit=Trueで周期カーブまたはinMesh/create入力がある場合。
        RuntimeError: 直接編集時のロック・入力接続・書込み禁止、またはShapeを参照できない場合。
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
            writable(point)
            for child in range(point.numChildren()):
                writable(point.child(child))
    return path, fn, mesh


def positions(shape, indices, ws=False):
    """指定した点を保持順・cm単位で取得する。

    Args:
        shape (Shape): 有効なMeshまたはNurbsCurve。
        indices (Sequence[int]): 検証済みの点番号。
        ws (bool): Trueならワールド空間へ変換する。

    Returns:
        list[tuple[float, float, float]]: 指定順の座標。単点では全点を取得しない。
    """
    path, fn, mesh = geometry(shape, indices)
    space = om2.MSpace.kWorld if ws else om2.MSpace.kObject
    if len(indices) == 1:
        if mesh:
            points = [fn.getPoint(indices[0], space)]
        else:
            points = [fn.cvPosition(indices[0], space)]
    else:
        if mesh:
            all_points = fn.getPoints(space)
        else:
            all_points = fn.cvPositions(space)
        points = (all_points[i] for i in indices)
    return [(point.x, point.y, point.z) for point in points]


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


def setPositions(shape, indices, values, ws=False, *, fast=False):
    """検証済みのcm座標を書き込む。Undo範囲は呼出元が管理する。

    Args:
        shape (Shape): MeshまたはNurbsCurve。
        indices (Sequence[int]): 検証済みのAPI番号。重複は後の値を優先。
        values (Sequence[Sequence[float]]): 番号と同数の有限なXYZ。
        ws (bool): Trueならワールド座標。
        fast (bool): TrueはOpenMaya直接更新。通常はcmds.xformを使う。

    Raises:
        NotImplementedError: fastで未対応の形状の場合。
        RuntimeError: Mayaが書込みを拒否した場合。完了済みの変更は戻さない。
    """
    if not indices:
        return
    if fast:
        _set_positions_direct(shape, indices, values, ws)
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
        cmds.xform("{}.{}[{}]".format(name, token, index), absolute=True,
                   translation=coordinates, worldSpace=ws, objectSpace=not ws)


def _set_positions_direct(shape, indices, values, ws=False):
    """検証済みのcm座標を一括設定する。CVのwは変更しない。

    Args:
        shape (Shape): 履歴なしMeshまたは非周期NurbsCurve。
        indices (Sequence[int]): 検証済みの番号。
        values (Sequence[Sequence[float]]): 設定するXYZ。
        ws (bool): TrueならAPIワールド座標、Falseならローカル座標。
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
    """APIのワールド座標を、CVの重みを保持したローカルXYZへ変換する。

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


def set_uvs(shape, indices, values):
    """現在のUV配列を読み、指定番号のU/Vを置換してOpenMayaへ一括設定する。

    空の番号列はMayaへ問い合わせず戻る。非空なら入力履歴とShapeノードのロックを検査するが、
    個々のUV-set Plugの書込み可否は検査しない。UV割当てやセットは作成しない。
    Undoへ記録せず、Undo設定も変更しない。呼出し側が座標・件数・番号範囲を検証する。

    Args:
        shape (Mesh): 対象Mesh。
        indices (Sequence[int]): 検証済みのUV番号。
        values (Sequence[Sequence[float]]): indicesに対応する無次元の(U, V)行。

    Raises:
        NotImplementedError: inMeshへの入力がある場合。
        RuntimeError: Shapeがロックされている、またはMayaの読取り・設定・更新に失敗した場合。

    Note:
        指定外の番号は読み出した値を保持する。setUVs後にupdateSurfaceを呼び、
        後段の失敗時に自動で元の配列へ戻す処理は持たない。
    """
    if not indices:
        return
    _, fn, _ = geometry(shape, [], edit=True)
    uv_set = fn.currentUVSetName()
    us, vs = fn.getUVs(uvSet=uv_set)
    for index, (u, v) in zip(indices, values):
        us[index], vs[index] = u, v
    fn.setUVs(us, vs, uvSet=uv_set)
    fn.updateSurface()
