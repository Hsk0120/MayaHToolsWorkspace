"""Maya 用の Orient Joint UI 補助ユーティリティ。

このモジュールは、向き指定文字列の計算、対象ジョイントの収集、
skinCluster 状態の退避/復元、および UI から Orient Joint を適用する
ウィンドウ作成のためのヘルパー関数を提供します。
"""

import maya.cmds as cmds
import maya.api.OpenMaya as om2
import math

_WIN = "OrientJointLikeWin"
_AXES = ("x", "y", "z")
_AXIS_VECTORS = {
    "x": om2.MVector.kXaxisVector,
    "y": om2.MVector.kYaxisVector,
    "z": om2.MVector.kZaxisVector,
}
_ROTATE_ORDER_LABELS = {
    0: "xyz",
    1: "yzx",
    2: "zxy",
    3: "xzy",
    4: "yxz",
    5: "zyx",
}
_ROTATE_ORDER_ENUMS = {
    0: om2.MEulerRotation.kXYZ,
    1: om2.MEulerRotation.kYZX,
    2: om2.MEulerRotation.kZXY,
    3: om2.MEulerRotation.kXZY,
    4: om2.MEulerRotation.kYXZ,
    5: om2.MEulerRotation.kZYX,
}
_DEBUG_ORIENT = True
_DEBUG_ORIENT_VERBOSE_NEXT_CHILDREN = True

def _compute_axis_vector(axis_name):
    """軸名から `om2.MVector` を返します。"""
    return om2.MVector(_AXIS_VECTORS.get(axis_name, om2.MVector.kYaxisVector))

def _compute_normalized_vector(vec):
    """ベクトルを安全に正規化して返します。"""
    nvec = om2.MVector(vec)
    if nvec.length() <= 1e-8:
        return None
    nvec.normalize()
    return nvec

def _compute_joint_orient_order(primary, secondary):
    """Primary/Secondary 軸から Maya の `oj` 軸順文字列を作成します。

    Args:
        primary (str): 主軸。``x`` / ``y`` / ``z`` のいずれか。
        secondary (str): 副軸。``x`` / ``y`` / ``z`` のいずれかで、
            ``primary`` と異なる値。

    Returns:
        str: ``xyz`` のような 3 文字の orient 順序文字列。

    Raises:
        ValueError: 軸指定が不正、または重複している場合。
    """
    if primary not in _AXES or secondary not in _AXES or primary == secondary:
        raise ValueError("Primary/Secondary axis must be different and one of x/y/z.")

    third = next(a for a in _AXES if a not in (primary, secondary))
    return primary + secondary + third

def _compute_dag_path(node_name):
    """ノード名から `MDagPath` を解決します。

    Args:
        node_name (str): Maya DAG ノード名。

    Returns:
        maya.api.OpenMaya.MDagPath: 解決済み DAG パス。
    """
    sel = om2.MSelectionList()
    sel.add(node_name)
    return sel.getDagPath(0)

def _compute_world_axis_label(vec):
    """ワールドベクトルを Maya の up/down 軸指定文字列へ変換します。

    Args:
        vec (maya.api.OpenMaya.MVector): ワールド空間の入力ベクトル。

    Returns:
        str: ``xup`` や ``ydown`` のような軸指定文字列。
    """
    world_axes = {
        "x": om2.MVector.kXaxisVector,
        "y": om2.MVector.kYaxisVector,
        "z": om2.MVector.kZaxisVector,
    }

    if vec.length() < 1e-8:
        return "yup"

    nvec = om2.MVector(vec)
    nvec.normalize()

    best_axis = "y"
    best_abs_dot = -1.0
    best_sign = 1.0
    for axis_name, axis_vec in world_axes.items():
        dot = nvec * axis_vec
        abs_dot = abs(dot)
        if abs_dot > best_abs_dot:
            best_abs_dot = abs_dot
            best_axis = axis_name
            best_sign = dot

    return "{}{}".format(best_axis, "up" if best_sign >= 0.0 else "down")

def _compute_flipped_direction_label(axis_label):
    """Secondary Orient 指定文字列の `up`/`down` 接尾辞を反転します。

    Args:
        axis_label (str): ``up`` または ``down`` で終わる指定文字列。

    Returns:
        str: 反転後の指定文字列。対象接尾辞がなければ元の値。
    """
    if axis_label.endswith("up"):
        return axis_label[:-2] + "down"
    if axis_label.endswith("down"):
        return axis_label[:-4] + "up"
    return axis_label

def _compute_secondary_orient_local(joint_name, local_reference_axis, direction):
    """ジョイントのローカル空間基準で `secondaryAxisOrient` を計算します。

    Args:
        joint_name (str): ジョイントノード名。
        local_reference_axis (str): 基準に使うローカル軸キー
            （``x`` / ``y`` / ``z``）。
        direction (str): 方向記号（``+`` または ``-``）。

    Returns:
        str: ワールド軸形式の Secondary Orient 指定文字列。
    """
    dag_path = _compute_dag_path(joint_name)
    world_q = om2.MTransformationMatrix(dag_path.inclusiveMatrix()).rotation(asQuaternion=True)

    local_axes = {
        "x": om2.MVector.kXaxisVector,
        "y": om2.MVector.kYaxisVector,
        "z": om2.MVector.kZaxisVector,
    }
    axis = local_reference_axis if local_reference_axis in _AXES else "y"
    ref_world_vec = om2.MVector(local_axes[axis]).rotateBy(world_q)
    axis_label = _compute_world_axis_label(ref_world_vec)
    return _compute_flipped_direction_label(axis_label) if direction == "-" else axis_label

def _compute_target_joints(joints, include_children):
    """対象ジョイントを収集し、重複のないロングネームで返します。

    Args:
        joints (list[str]): 元になるジョイント一覧。
        include_children (bool): 子孫ジョイントを含めるかどうか。

    Returns:
        list[str]: 重複除去済みのロングパスジョイント名。
    """
    targets = list(joints)
    if include_children:
        for j in joints:
            children = cmds.listRelatives(j, ad=True, type='joint', f=True) or []
            targets.extend(children)

    long_names = cmds.ls(targets, l=True) or []
    unique = []
    seen = set()
    for name in long_names:
        if name in seen:
            continue
        seen.add(name)
        unique.append(name)
    return unique

def _compute_skin_clusters_from_joints(joints):
    """指定ジョイントに接続された skinCluster を取得します。

    Args:
        joints (list[str]): ジョイント名一覧。

    Returns:
        list[str]: 重複のない skinCluster ノード名一覧。
    """
    clusters = []
    seen = set()
    for j in joints:
        connected = cmds.listConnections(j, type='skinCluster') or []
        for sc in connected:
            if sc in seen:
                continue
            seen.add(sc)
            clusters.append(sc)
    return clusters

def _compute_world_matrix(node_name):
    """ノードのワールド行列を `om2.MMatrix` として取得します。"""
    return om2.MMatrix(cmds.xform(node_name, q=True, ws=True, m=True))

def _compute_world_position(node_name):
    """ノードのワールド座標を `om2.MVector` として取得します。"""
    x, y, z = cmds.xform(node_name, q=True, ws=True, t=True)
    return om2.MVector(x, y, z)

def _compute_primary_world_vector(joint_name, return_debug=False):
    """ジョイントの主軸方向（ワールド）を計算します。"""
    joint_pos = _compute_world_position(joint_name)
    child_joints = cmds.listRelatives(joint_name, c=True, type="joint", f=True) or []
    debug_info = {
        "source": "none",
        "driver_joint": None,
        "raw_vector": None,
        "normalized_vector": None,
    }

    if child_joints:
        vec = _compute_world_position(child_joints[0]) - joint_pos
        debug_info["source"] = "child"
        debug_info["driver_joint"] = child_joints[0]
        debug_info["raw_vector"] = vec
        nvec = _compute_normalized_vector(vec)
        debug_info["normalized_vector"] = nvec
        if nvec is not None:
            return (nvec, debug_info) if return_debug else nvec

    parent = cmds.listRelatives(joint_name, p=True, type="joint", f=True)
    if parent:
        vec = joint_pos - _compute_world_position(parent[0])
        debug_info["source"] = "parentFallback"
        debug_info["driver_joint"] = parent[0]
        debug_info["raw_vector"] = vec
        nvec = _compute_normalized_vector(vec)
        debug_info["normalized_vector"] = nvec
        if nvec is not None:
            return (nvec, debug_info) if return_debug else nvec

    return (None, debug_info) if return_debug else None

def _compute_primary_space_mode(primary_space_value):
    """UI 表示文字列を primary_space の内部キーに正規化します。"""
    value = (primary_space_value or "").strip().lower()
    if value in ("world", "world axis"):
        return "world"
    if value == "local":
        return "local"
    return "chain"

def _compute_primary_vector_from_mode(joint_name, primary_axis, primary_space, primary_ref_axis):
    """primary_space の内部キーに応じて主軸ベクトル（ワールド）を返します。"""
    if primary_space == "local":
        world_matrix = _compute_world_matrix(joint_name)
        return _compute_axis_world_vector_from_matrix(world_matrix, primary_ref_axis)
    if primary_space == "world":
        return _compute_axis_vector(primary_ref_axis)
    return _compute_primary_world_vector(joint_name)

def _compute_vector_to_first_child(joint_name):
    """最初の子ジョイントへの方向ベクトル（正規化）を返します。"""
    child_joints = cmds.listRelatives(joint_name, c=True, type="joint", f=True) or []
    if not child_joints:
        return None
    joint_pos = _compute_world_position(joint_name)
    child_pos = _compute_world_position(child_joints[0])
    return _compute_normalized_vector(child_pos - joint_pos)

def _compute_axis_world_vector_from_matrix(world_matrix, axis_name):
    """ワールド行列から指定ローカル軸のワールド方向ベクトルを得ます。"""
    base = _compute_axis_vector(axis_name)
    return _compute_normalized_vector(base * world_matrix)

def _compute_up_world_vector(joint_name, up_axis, up_direction, up_space, return_debug=False):
    """UI 設定に基づく up ベクトル（ワールド）を計算します。"""
    sign = -1.0 if up_direction == "-" else 1.0
    debug_info = {
        "space": up_space,
        "sign": sign,
        "source": "axis",
        "base_vector": None,
        "vector": None,
        "base_info": None,
    }
    if up_space == "next/children":
        up_vec, base_info = _compute_primary_world_vector(joint_name, return_debug=True)
        debug_info["source"] = "next/children"
        debug_info["base_info"] = base_info
        if up_vec is None:
            return (None, debug_info) if return_debug else None
        debug_info["base_vector"] = up_vec
        debug_info["vector"] = up_vec * sign
        return (debug_info["vector"], debug_info) if return_debug else debug_info["vector"]
    if up_space == "local":
        world_matrix = _compute_world_matrix(joint_name)
        base_vec = _compute_axis_world_vector_from_matrix(world_matrix, up_axis)
        debug_info["source"] = "local"
        debug_info["base_vector"] = base_vec
        debug_info["vector"] = base_vec * sign if base_vec is not None else None
        return (debug_info["vector"], debug_info) if return_debug else debug_info["vector"]
    base_vec = _compute_axis_vector(up_axis)
    debug_info["source"] = "world"
    debug_info["base_vector"] = base_vec
    debug_info["vector"] = base_vec * sign
    return (debug_info["vector"], debug_info) if return_debug else debug_info["vector"]

def _compute_fallback_secondary_vector(primary_vec):
    """主軸とほぼ平行な up 指定時のフォールバック副軸を返します。"""
    world_y = _compute_axis_vector("y")
    world_x = _compute_axis_vector("x")
    ref = world_y if abs(primary_vec * world_y) < 0.999 else world_x
    return _compute_normalized_vector(ref ^ primary_vec)

def _compute_secondary_world_vector(primary_vec, up_vec, return_debug=False):
    """主軸に直交する副軸を up ベクトルから計算します。"""
    projected_component = primary_vec * (primary_vec * up_vec)
    secondary_vec = up_vec - projected_component
    nvec = _compute_normalized_vector(secondary_vec)
    debug_info = {
        "projected_component": projected_component,
        "orthogonal_component": secondary_vec,
        "fallback_used": False,
    }
    if nvec is None:
        fallback_vec = _compute_fallback_secondary_vector(primary_vec)
        debug_info["fallback_used"] = True
        if return_debug:
            return fallback_vec, True, debug_info
        return fallback_vec, True
    if return_debug:
        return nvec, False, debug_info
    return nvec, False

def _compute_debug_vector_label(vec):
    """デバッグ表示用のベクトル文字列を返します。"""
    if vec is None:
        return "None"
    return "({:.6f}, {:.6f}, {:.6f})".format(vec.x, vec.y, vec.z)

def _compute_is_next_children_debug_enabled(primary_space, up_space):
    """Next/Children 詳細ログを有効化するかどうかを返します。"""
    if not _DEBUG_ORIENT or not _DEBUG_ORIENT_VERBOSE_NEXT_CHILDREN:
        return False
    return primary_space == "chain" or up_space == "next/children"

def _compute_debug_log_matrix_axes(joint_name, label, matrix_obj):
    """回転行列の XYZ 軸ベクトルをログ出力します。"""
    x_vec = _compute_axis_world_vector_from_matrix(matrix_obj, "x")
    y_vec = _compute_axis_world_vector_from_matrix(matrix_obj, "y")
    z_vec = _compute_axis_world_vector_from_matrix(matrix_obj, "z")
    om2.MGlobal.displayInfo(
        "[OrientDebug][NextChildren] {}: {} X={} Y={} Z={}".format(
            joint_name,
            label,
            _compute_debug_vector_label(x_vec),
            _compute_debug_vector_label(y_vec),
            _compute_debug_vector_label(z_vec),
        )
    )

def _compute_debug_log_matrix_alignment(joint_name, label_a, matrix_a, label_b, matrix_b):
    """2つの回転行列の軸整合性をログ出力します。"""
    x_a = _compute_axis_world_vector_from_matrix(matrix_a, "x")
    y_a = _compute_axis_world_vector_from_matrix(matrix_a, "y")
    z_a = _compute_axis_world_vector_from_matrix(matrix_a, "z")
    x_b = _compute_axis_world_vector_from_matrix(matrix_b, "x")
    y_b = _compute_axis_world_vector_from_matrix(matrix_b, "y")
    z_b = _compute_axis_world_vector_from_matrix(matrix_b, "z")

    x_dot, x_angle = _compute_debug_angle_deg(x_a, x_b)
    y_dot, y_angle = _compute_debug_angle_deg(y_a, y_b)
    z_dot, z_angle = _compute_debug_angle_deg(z_a, z_b)

    om2.MGlobal.displayInfo(
        "[OrientDebug][NextChildren] {}: {} vs {} | X={:.6f}/{:.3f}deg Y={:.6f}/{:.3f}deg Z={:.6f}/{:.3f}deg".format(
            joint_name,
            label_a,
            label_b,
            x_dot, x_angle,
            y_dot, y_angle,
            z_dot, z_angle,
        )
    )

def _compute_debug_log_euler_rebuild(joint_name, euler_rotation, target_matrix):
    """Euler 再構築行列と目標行列の一致度をログ出力します。"""
    rotate_order_index = int(cmds.getAttr("{}.rotateOrder".format(joint_name)))
    rotate_order_enum = _ROTATE_ORDER_ENUMS.get(rotate_order_index, om2.MEulerRotation.kXYZ)
    rotate_order_label = _ROTATE_ORDER_LABELS.get(rotate_order_index, "xyz")

    rebuilt_xyz = om2.MEulerRotation(
        euler_rotation.x,
        euler_rotation.y,
        euler_rotation.z,
    ).asMatrix()
    rebuilt_ro = om2.MEulerRotation(
        euler_rotation.x,
        euler_rotation.y,
        euler_rotation.z,
        rotate_order_enum,
    ).asMatrix()
    om2.MGlobal.displayInfo(
        "[OrientDebug][NextChildren] {}: EulerDeg=({:.6f}, {:.6f}, {:.6f}) rotateOrder={}".format(
            joint_name,
            math.degrees(euler_rotation.x),
            math.degrees(euler_rotation.y),
            math.degrees(euler_rotation.z),
            rotate_order_label,
        )
    )
    _compute_debug_log_matrix_axes(joint_name, "EulerRebuildXYZ", rebuilt_xyz)
    _compute_debug_log_matrix_axes(joint_name, "EulerRebuildRotateOrder", rebuilt_ro)
    _compute_debug_log_matrix_alignment(
        joint_name,
        "EulerRebuildXYZ",
        rebuilt_xyz,
        "JointOrientRot",
        target_matrix,
    )
    _compute_debug_log_matrix_alignment(
        joint_name,
        "EulerRebuildRotateOrder",
        rebuilt_ro,
        "JointOrientRot",
        target_matrix,
    )
    return {
        "xyz": rebuilt_xyz,
        "rotate_order": rebuilt_ro,
        "rotate_order_label": rotate_order_label,
    }

def _compute_debug_log_joint_orient_order_hypothesis(joint_name, orient_degrees, current_local_rot):
    """jointOrient の角度解釈順を総当たりで推定してログ出力します。"""
    rx = math.radians(orient_degrees[0])
    ry = math.radians(orient_degrees[1])
    rz = math.radians(orient_degrees[2])

    best = None
    xyz = None
    for order_index, order_enum in _ROTATE_ORDER_ENUMS.items():
        order_label = _ROTATE_ORDER_LABELS[order_index]
        mat = om2.MEulerRotation(rx, ry, rz, order_enum).asMatrix()

        x_a = _compute_axis_world_vector_from_matrix(mat, "x")
        y_a = _compute_axis_world_vector_from_matrix(mat, "y")
        z_a = _compute_axis_world_vector_from_matrix(mat, "z")
        x_b = _compute_axis_world_vector_from_matrix(current_local_rot, "x")
        y_b = _compute_axis_world_vector_from_matrix(current_local_rot, "y")
        z_b = _compute_axis_world_vector_from_matrix(current_local_rot, "z")

        _, x_angle = _compute_debug_angle_deg(x_a, x_b)
        _, y_angle = _compute_debug_angle_deg(y_a, y_b)
        _, z_angle = _compute_debug_angle_deg(z_a, z_b)
        score = x_angle + y_angle + z_angle

        result = {
            "label": order_label,
            "score": score,
            "x_angle": x_angle,
            "y_angle": y_angle,
            "z_angle": z_angle,
        }

        if order_label == "xyz":
            xyz = result
        if best is None or score < best["score"]:
            best = result

    if xyz is not None:
        om2.MGlobal.displayInfo(
            "[OrientDebug][NextChildren] {}: JO order hypothesis xyz score={:.3f} (X={:.3f}, Y={:.3f}, Z={:.3f})".format(
                joint_name,
                xyz["score"],
                xyz["x_angle"],
                xyz["y_angle"],
                xyz["z_angle"],
            )
        )

    if best is not None:
        om2.MGlobal.displayInfo(
            "[OrientDebug][NextChildren] {}: JO order hypothesis best={} score={:.3f} (X={:.3f}, Y={:.3f}, Z={:.3f})".format(
                joint_name,
                best["label"],
                best["score"],
                best["x_angle"],
                best["y_angle"],
                best["z_angle"],
            )
        )

def _compute_debug_log_post_apply_attr_state(joint_name, expected_orient_degrees):
    """jointOrient/rotate の設定反映状態と接続をログ出力します。"""
    actual_orient = cmds.getAttr("{}.jointOrient".format(joint_name))[0]
    actual_rotate = cmds.getAttr("{}.rotate".format(joint_name))[0]
    rotate_order_index = int(cmds.getAttr("{}.rotateOrder".format(joint_name)))
    rotate_order_label = _ROTATE_ORDER_LABELS.get(rotate_order_index, "xyz")

    delta_orient = [
        actual_orient[0] - expected_orient_degrees[0],
        actual_orient[1] - expected_orient_degrees[1],
        actual_orient[2] - expected_orient_degrees[2],
    ]

    rotate_inputs = cmds.listConnections("{}.rotate".format(joint_name), s=True, d=False, p=True) or []
    jo_inputs = cmds.listConnections("{}.jointOrient".format(joint_name), s=True, d=False, p=True) or []

    om2.MGlobal.displayInfo(
        "[OrientDebug][NextChildren] {}: Readback JO=({:.6f}, {:.6f}, {:.6f}) Expected=({:.6f}, {:.6f}, {:.6f}) Delta=({:.6f}, {:.6f}, {:.6f})".format(
            joint_name,
            actual_orient[0], actual_orient[1], actual_orient[2],
            expected_orient_degrees[0], expected_orient_degrees[1], expected_orient_degrees[2],
            delta_orient[0], delta_orient[1], delta_orient[2],
        )
    )
    om2.MGlobal.displayInfo(
        "[OrientDebug][NextChildren] {}: Readback rotate=({:.6f}, {:.6f}, {:.6f}) rotateOrder={}".format(
            joint_name,
            actual_rotate[0], actual_rotate[1], actual_rotate[2],
            rotate_order_label,
        )
    )
    if rotate_inputs:
        om2.MGlobal.displayWarning(
            "[OrientDebug][NextChildren] {}: rotate input connections={}".format(
                joint_name,
                ", ".join(rotate_inputs),
            )
        )
    if jo_inputs:
        om2.MGlobal.displayWarning(
            "[OrientDebug][NextChildren] {}: jointOrient input connections={}".format(
                joint_name,
                ", ".join(jo_inputs),
            )
        )

def _compute_debug_log_next_children_inputs(
    joint_name,
    primary_space,
    primary_direction,
    up_direction,
    up_space,
):
    """Next/Children 利用時の入力ベクトル由来を詳細ログ出力します。"""
    primary_vec_for_secondary = None
    up_vec_for_secondary = None

    if primary_space == "chain":
        primary_vec_raw, primary_info = _compute_primary_world_vector(joint_name, return_debug=True)
        primary_vec_for_secondary = primary_vec_raw
        if primary_vec_for_secondary is not None and primary_direction == "-":
            primary_vec_for_secondary *= -1.0

        om2.MGlobal.displayInfo(
            "[OrientDebug][NextChildren] {}: Primary source={} driver={} raw={} normalized={} signed={}".format(
                joint_name,
                primary_info["source"],
                primary_info["driver_joint"] or "None",
                _compute_debug_vector_label(primary_info["raw_vector"]),
                _compute_debug_vector_label(primary_info["normalized_vector"]),
                _compute_debug_vector_label(primary_vec_for_secondary),
            )
        )

    if up_space == "next/children":
        up_vec, up_info = _compute_up_world_vector(
            joint_name,
            up_axis="y",
            up_direction=up_direction,
            up_space=up_space,
            return_debug=True,
        )
        up_vec_for_secondary = up_vec
        base_info = up_info.get("base_info") or {}
        om2.MGlobal.displayInfo(
            "[OrientDebug][NextChildren] {}: Up source={} driver={} base={} signed={} sign={:+.1f}".format(
                joint_name,
                base_info.get("source", "none"),
                base_info.get("driver_joint") or "None",
                _compute_debug_vector_label(up_info.get("base_vector")),
                _compute_debug_vector_label(up_info.get("vector")),
                up_info["sign"],
            )
        )

    if primary_vec_for_secondary is not None and up_vec_for_secondary is not None:
        secondary_vec, used_fallback, sec_debug = _compute_secondary_world_vector(
            primary_vec_for_secondary,
            up_vec_for_secondary,
            return_debug=True,
        )
        om2.MGlobal.displayInfo(
            "[OrientDebug][NextChildren] {}: Projection={} Orthogonal={} Secondary={}{}".format(
                joint_name,
                _compute_debug_vector_label(sec_debug["projected_component"]),
                _compute_debug_vector_label(sec_debug["orthogonal_component"]),
                _compute_debug_vector_label(secondary_vec),
                " (fallback)" if used_fallback else "",
            )
        )

def _compute_axis_basis_from_ui(primary_axis, secondary_axis, primary_vec, secondary_vec):
    """主軸/副軸指定と方向ベクトルから右手系の XYZ 基底を組み立てます。"""
    axes = {
        primary_axis: primary_vec,
        secondary_axis: secondary_vec,
    }

    if "x" not in axes:
        axes["x"] = _compute_normalized_vector(axes["y"] ^ axes["z"])
    elif "y" not in axes:
        axes["y"] = _compute_normalized_vector(axes["z"] ^ axes["x"])
    elif "z" not in axes:
        axes["z"] = _compute_normalized_vector(axes["x"] ^ axes["y"])

    if secondary_axis == "x":
        axes["x"] = _compute_normalized_vector(axes["y"] ^ axes["z"])
    elif secondary_axis == "y":
        axes["y"] = _compute_normalized_vector(axes["z"] ^ axes["x"])
    elif secondary_axis == "z":
        axes["z"] = _compute_normalized_vector(axes["x"] ^ axes["y"])

    return axes

def _compute_rotation_matrix_from_axes(axes):
    """XYZ 軸ベクトルから回転行列を生成します。"""
    x_axis = axes["x"]
    y_axis = axes["y"]
    z_axis = axes["z"]
    return om2.MMatrix([
        x_axis.x, x_axis.y, x_axis.z, 0.0,
        y_axis.x, y_axis.y, y_axis.z, 0.0,
        z_axis.x, z_axis.y, z_axis.z, 0.0,
        0.0,      0.0,      0.0,      1.0,
    ])

def _compute_rotate_axis_matrix(joint_name):
    """ジョイントの rotateAxis 行列を返します（度指定）。"""
    rx = math.radians(cmds.getAttr("{}.rotateAxisX".format(joint_name)))
    ry = math.radians(cmds.getAttr("{}.rotateAxisY".format(joint_name)))
    rz = math.radians(cmds.getAttr("{}.rotateAxisZ".format(joint_name)))
    return om2.MEulerRotation(rx, ry, rz).asMatrix()

def _compute_has_non_zero_rotate_axis(joint_name):
    """rotateAxis が実質ゼロかどうかを返します。"""
    vals = [
        cmds.getAttr("{}.rotateAxisX".format(joint_name)),
        cmds.getAttr("{}.rotateAxisY".format(joint_name)),
        cmds.getAttr("{}.rotateAxisZ".format(joint_name)),
    ]
    return any(abs(v) > 1e-6 for v in vals)

def _compute_debug_log_joint_axis_alignment(joint_name):
    """ジョイント X 軸と最初の子方向の整合性をログ出力します。"""
    child_dir = _compute_vector_to_first_child(joint_name)
    if child_dir is None:
        om2.MGlobal.displayInfo("[OrientDebug] {}: no child joint".format(joint_name))
        return

    world_rot = om2.MTransformationMatrix(_compute_world_matrix(joint_name)).asRotateMatrix()
    x_axis_world = _compute_axis_world_vector_from_matrix(world_rot, "x")
    if x_axis_world is None:
        om2.MGlobal.displayWarning("[OrientDebug] {}: failed to compute world X axis".format(joint_name))
        return

    dot = x_axis_world * child_dir
    angle = math.degrees(math.acos(max(-1.0, min(1.0, dot))))
    om2.MGlobal.displayInfo(
        "[OrientDebug] {}: X·Child={:.6f}, Angle={:.3f}deg".format(joint_name, dot, angle)
    )

def _compute_debug_angle_deg(vec_a, vec_b):
    """2ベクトルの内積と角度(度)を返します。"""
    dot = vec_a * vec_b
    dot_clamped = max(-1.0, min(1.0, dot))
    return dot, math.degrees(math.acos(dot_clamped))

def _compute_debug_log_secondary_up_alignment(
    joint_name,
    primary_axis,
    primary_space,
    primary_ref_axis,
    primary_direction,
    secondary_axis,
    up_axis,
    up_direction,
    up_space,
):
    """Secondary / Up の整合性をログ出力します。"""
    primary_vec = _compute_primary_vector_from_mode(
        joint_name,
        primary_axis,
        primary_space,
        primary_ref_axis,
    )

    if primary_vec is None:
        om2.MGlobal.displayWarning("[OrientDebug] {}: no primary vector".format(joint_name))
        return

    if primary_direction == "-":
        primary_vec *= -1.0

    up_vec = _compute_up_world_vector(joint_name, up_axis, up_direction, up_space)

    if up_vec is None:
        om2.MGlobal.displayWarning("[OrientDebug] {}: no up vector".format(joint_name))
        return

    up_nvec = _compute_normalized_vector(up_vec)
    primary_up_dot = primary_vec * up_nvec if up_nvec is not None else 0.0

    target_secondary, used_fallback = _compute_secondary_world_vector(primary_vec, up_vec)
    if target_secondary is None:
        om2.MGlobal.displayWarning("[OrientDebug] {}: no secondary vector".format(joint_name))
        return

    world_rot = om2.MTransformationMatrix(_compute_world_matrix(joint_name)).asRotateMatrix()
    current_secondary = _compute_axis_world_vector_from_matrix(world_rot, secondary_axis)
    current_up_axis = _compute_axis_world_vector_from_matrix(world_rot, up_axis)
    if current_secondary is None or current_up_axis is None:
        om2.MGlobal.displayWarning("[OrientDebug] {}: failed current axis resolve".format(joint_name))
        return

    sec_dot, sec_angle = _compute_debug_angle_deg(current_secondary, target_secondary)
    up_dot, up_angle = _compute_debug_angle_deg(current_up_axis, up_nvec)

    om2.MGlobal.displayInfo(
        "[OrientDebug] {}: Primary={} Up={} TargetSec={} | Primary·Up={:.6f}{}".format(
            joint_name,
            _compute_debug_vector_label(primary_vec),
            _compute_debug_vector_label(up_nvec),
            _compute_debug_vector_label(target_secondary),
            primary_up_dot,
            " (fallback)" if used_fallback else "",
        )
    )

    om2.MGlobal.displayInfo(
        "[OrientDebug] {}: {}·TargetSec={:.6f}, SecAngle={:.3f}deg | {}·Up={:.6f}, UpAngle={:.3f}deg".format(
            joint_name,
            secondary_axis.upper(), sec_dot, sec_angle,
            up_axis.upper(), up_dot, up_angle,
        )
    )

def _compute_joint_orient_degrees(
    joint_name,
    primary_axis,
    primary_space,
    primary_ref_axis,
    primary_direction,
    secondary_axis,
    up_axis,
    up_direction,
    up_space,
    debug_verbose=False,
    return_debug_data=False,
):
    """UI 設定から `jointOrient` に設定する XYZ 角度（度）を計算します。"""
    primary_vec = _compute_primary_vector_from_mode(
        joint_name,
        primary_axis,
        primary_space,
        primary_ref_axis,
    )

    if primary_vec is None:
        return (None, None) if return_debug_data else None

    if primary_direction == "-":
        primary_vec *= -1.0

    up_vec = _compute_up_world_vector(joint_name, up_axis, up_direction, up_space)

    if up_vec is None:
        return (None, None) if return_debug_data else None

    if debug_verbose:
        secondary_vec, _, secondary_debug = _compute_secondary_world_vector(primary_vec, up_vec, return_debug=True)
    else:
        secondary_vec, _ = _compute_secondary_world_vector(primary_vec, up_vec)
        secondary_debug = None
    axes = _compute_axis_basis_from_ui(primary_axis, secondary_axis, primary_vec, secondary_vec)
    if any(v is None for v in axes.values()):
        return (None, None) if return_debug_data else None

    target_world_rot = _compute_rotation_matrix_from_axes(axes)

    parent = cmds.listRelatives(joint_name, p=True, type="joint", f=True)
    if parent:
        parent_world_matrix = _compute_world_matrix(parent[0])
        parent_world_rot = om2.MTransformationMatrix(parent_world_matrix).asRotateMatrix()
        local_rot = target_world_rot * parent_world_rot.inverse()
    else:
        local_rot = target_world_rot

    rotate_axis_matrix = _compute_rotate_axis_matrix(joint_name)
    joint_orient_rot = local_rot * rotate_axis_matrix.inverse()

    if debug_verbose:
        om2.MGlobal.displayInfo(
            "[OrientDebug][NextChildren] {}: parent={}".format(joint_name, parent[0] if parent else "None")
        )
        if secondary_debug is not None:
            om2.MGlobal.displayInfo(
                "[OrientDebug][NextChildren] {}: Stage Projection={} Orthogonal={}".format(
                    joint_name,
                    _compute_debug_vector_label(secondary_debug["projected_component"]),
                    _compute_debug_vector_label(secondary_debug["orthogonal_component"]),
                )
            )
        _compute_debug_log_matrix_axes(joint_name, "TargetWorld", target_world_rot)
        _compute_debug_log_matrix_axes(joint_name, "LocalToParent", local_rot)
        _compute_debug_log_matrix_axes(joint_name, "JointOrientRot", joint_orient_rot)

    euler = om2.MTransformationMatrix(joint_orient_rot).rotation()
    euler_rebuild = None
    if debug_verbose:
        euler_rebuild = _compute_debug_log_euler_rebuild(joint_name, euler, joint_orient_rot)

    orient_degrees = [math.degrees(euler.x), math.degrees(euler.y), math.degrees(euler.z)]

    if return_debug_data:
        return orient_degrees, {
            "target_world_rot": target_world_rot,
            "local_rot": local_rot,
            "joint_orient_rot": joint_orient_rot,
            "euler_rebuild": euler_rebuild,
            "orient_degrees": orient_degrees,
            "parent_joint": parent[0] if parent else None,
        }

    return orient_degrees

def _compute_descendant_world_matrices(joint_name):
    """子孫ジョイントのワールド行列を退避します。"""
    descendants = cmds.listRelatives(joint_name, ad=True, type="joint", f=True) or []
    descendants = sorted(set(descendants), key=lambda n: n.count("|"))
    return {
        node: cmds.xform(node, q=True, ws=True, m=True)
        for node in descendants
    }

def _compute_restore_world_matrices(node_to_world_matrix):
    """退避済みワールド行列を復元します。"""
    restore_nodes = sorted(node_to_world_matrix.keys(), key=lambda n: n.count("|"))
    for node in restore_nodes:
        if not cmds.objExists(node):
            continue
        try:
            cmds.xform(node, ws=True, m=node_to_world_matrix[node])
        except Exception:
            pass

def _preserve_enable_move_joints_mode(skin_clusters):
    """`moveJointsMode` を有効化し、以前の状態を退避します。

    Args:
        skin_clusters (list[str]): skinCluster ノード名一覧。

    Returns:
        dict[str, bool]: skinCluster ごとの退避済み `moveJointsMode`。
    """
    previous_modes = {}
    for sc in skin_clusters:
        try:
            previous_modes[sc] = bool(cmds.skinCluster(sc, q=True, moveJointsMode=True))
            cmds.skinCluster(sc, e=True, moveJointsMode=True)
        except Exception:
            pass
    return previous_modes

def _preserve_restore_move_joints_mode(previous_modes):
    """退避しておいた `moveJointsMode` の状態を復元します。

    Args:
        previous_modes (dict[str, bool]): 退避済み状態のマッピング。
    """
    for sc, state in previous_modes.items():
        try:
            cmds.skinCluster(sc, e=True, moveJointsMode=state)
        except Exception:
            pass

def _preserve_recache_bind_matrices(skin_clusters):
    """skinCluster の bind 行列を再キャッシュして変形差分を抑えます。

    Args:
        skin_clusters (list[str]): skinCluster ノード名一覧。
    """
    for sc in skin_clusters:
        try:
            cmds.skinCluster(sc, e=True, recacheBindMatrices=True)
        except Exception:
            pass

def _apply_orient_from_ui(*_):
    """現在の UI 設定に基づいて Orient Joint を適用します。

    Args:
        *_: Maya コールバック用の未使用引数。
    """
    primary = cmds.optionMenuGrp("oj_primary", q=True, v=True).lower()
    primary_space = _compute_primary_space_mode(cmds.optionMenuGrp("oj_primary_space", q=True, v=True))
    primary_ref_axis = cmds.optionMenuGrp("oj_primary_ref_axis", q=True, v=True).lower()
    primary_direction = cmds.optionMenuGrp("oj_primary_dir", q=True, v=True)
    secondary = cmds.optionMenuGrp("oj_secondary", q=True, v=True).lower()
    up_axis = cmds.optionMenuGrp("oj_up_axis", q=True, v=True).lower()
    up_direction = cmds.optionMenuGrp("oj_up_dir", q=True, v=True)
    up_space = cmds.optionMenuGrp("oj_up_space", q=True, v=True).lower()

    joints = cmds.ls(sl=True, type="joint")
    if not joints:
        cmds.warning("Select joint(s) first.")
        return

    try:
        _compute_joint_orient_order(primary, secondary)
    except ValueError as e:
        cmds.warning(str(e))
        return

    target_joints = _compute_target_joints(joints, include_children=True)
    skin_clusters = _compute_skin_clusters_from_joints(target_joints)
    previous_modes = _preserve_enable_move_joints_mode(skin_clusters)
    next_children_debug = _compute_is_next_children_debug_enabled(primary_space, up_space)

    try:
        for j in joints:
            if next_children_debug:
                _compute_debug_log_next_children_inputs(
                    j,
                    primary_space=primary_space,
                    primary_direction=primary_direction,
                    up_direction=up_direction,
                    up_space=up_space,
                )

            if next_children_debug:
                orient_degrees, orient_debug_data = _compute_joint_orient_degrees(
                    j,
                    primary_axis=primary,
                    primary_space=primary_space,
                    primary_ref_axis=primary_ref_axis,
                    primary_direction=primary_direction,
                    secondary_axis=secondary,
                    up_axis=up_axis,
                    up_direction=up_direction,
                    up_space=up_space,
                    debug_verbose=True,
                    return_debug_data=True,
                )
            else:
                orient_degrees = _compute_joint_orient_degrees(
                    j,
                    primary_axis=primary,
                    primary_space=primary_space,
                    primary_ref_axis=primary_ref_axis,
                    primary_direction=primary_direction,
                    secondary_axis=secondary,
                    up_axis=up_axis,
                    up_direction=up_direction,
                    up_space=up_space,
                )
                orient_debug_data = None

            if orient_degrees is None:
                cmds.warning("Skip {}: could not resolve orient direction.".format(j))
                continue

            child_world_matrices = _compute_descendant_world_matrices(j)

            cmds.setAttr(
                "{}.jointOrient".format(j),
                orient_degrees[0], orient_degrees[1], orient_degrees[2],
                type="double3"
            )
            cmds.setAttr("{}.rotate".format(j), 0.0, 0.0, 0.0, type="double3")

            if child_world_matrices:
                _compute_restore_world_matrices(child_world_matrices)

            if next_children_debug and orient_debug_data is not None:
                _compute_debug_log_post_apply_attr_state(j, orient_degrees)
                current_world_rot = om2.MTransformationMatrix(_compute_world_matrix(j)).asRotateMatrix()
                _compute_debug_log_matrix_axes(j, "CurrentWorldAfterApply", current_world_rot)
                _compute_debug_log_matrix_alignment(
                    j,
                    "CurrentWorldAfterApply",
                    current_world_rot,
                    "TargetWorld",
                    orient_debug_data["target_world_rot"],
                )

                parent_name = orient_debug_data.get("parent_joint")
                if parent_name:
                    parent_world_rot = om2.MTransformationMatrix(_compute_world_matrix(parent_name)).asRotateMatrix()
                    current_local_rot = parent_world_rot.inverse() * current_world_rot
                    _compute_debug_log_matrix_axes(j, "CurrentLocalAfterApply", current_local_rot)
                    _compute_debug_log_matrix_alignment(
                        j,
                        "CurrentLocalAfterApply",
                        current_local_rot,
                        "ExpectedLocal",
                        orient_debug_data["local_rot"],
                    )
                    if orient_debug_data.get("euler_rebuild") is not None:
                        _compute_debug_log_matrix_alignment(
                            j,
                            "CurrentLocalAfterApply",
                            current_local_rot,
                            "EulerRebuildXYZ",
                            orient_debug_data["euler_rebuild"]["xyz"],
                        )
                        _compute_debug_log_matrix_alignment(
                            j,
                            "CurrentLocalAfterApply",
                            current_local_rot,
                            "EulerRebuildRotateOrder({})".format(
                                orient_debug_data["euler_rebuild"]["rotate_order_label"]
                            ),
                            orient_debug_data["euler_rebuild"]["rotate_order"],
                        )
                        _compute_debug_log_joint_orient_order_hypothesis(
                            j,
                            orient_debug_data["orient_degrees"],
                            current_local_rot,
                        )

            if _DEBUG_ORIENT:
                if _compute_has_non_zero_rotate_axis(j):
                    om2.MGlobal.displayInfo(
                        "[OrientDebug] {}: rotateAxis=({:.6f}, {:.6f}, {:.6f})deg".format(
                            j,
                            cmds.getAttr("{}.rotateAxisX".format(j)),
                            cmds.getAttr("{}.rotateAxisY".format(j)),
                            cmds.getAttr("{}.rotateAxisZ".format(j)),
                        )
                    )
                _compute_debug_log_joint_axis_alignment(j)
                _compute_debug_log_secondary_up_alignment(
                    j,
                    primary_axis=primary,
                    primary_space=primary_space,
                    primary_ref_axis=primary_ref_axis,
                    primary_direction=primary_direction,
                    secondary_axis=secondary,
                    up_axis=up_axis,
                    up_direction=up_direction,
                    up_space=up_space,
                )
    finally:
        if skin_clusters:
            _preserve_recache_bind_matrices(skin_clusters)
        if previous_modes:
            _preserve_restore_move_joints_mode(previous_modes)

    cmds.inViewMessage(amg="Orient Joint applied.", pos="midCenterTop", fade=True)

def _ui_update_state(*_):
    """UI の有効/無効状態を更新します。

    Args:
        *_: Maya コールバック用の未使用引数。
    """
    primary_space = _compute_primary_space_mode(cmds.optionMenuGrp("oj_primary_space", q=True, v=True))
    secondary_space = cmds.optionMenuGrp("oj_up_space", q=True, v=True).lower()
    cmds.optionMenuGrp("oj_primary_ref_axis", e=True, en=(primary_space in ("world", "local")))
    cmds.optionMenuGrp("oj_up_axis", e=True, en=(secondary_space in ("world", "local")))

def show_orient_joint_like_window():
    """カスタム Orient Joint オプションウィンドウを作成して表示します。"""
    if cmds.windowPref(_WIN, exists=True):
        cmds.windowPref(_WIN, remove=True)

    if cmds.window(_WIN, exists=True):
        cmds.deleteUI(_WIN)

    cmds.window(_WIN, title="Orient Joint Options (Custom)", sizeable=False, widthHeight=(460, 1))
    cmds.columnLayout(adj=True, rs=8)
    label_width = 170
    field_width = 180

    # Primary Settings
    cmds.frameLayout(label="Primary Settings", collapsable=True, collapse=False, mw=10, mh=10)
    cmds.columnLayout(adj=True, rs=6)

    cmds.separator(h=6, style="none")
    cmds.optionMenuGrp("oj_primary", label="Primary Axis", cw2=(label_width, field_width))
    for a in ("X", "Y", "Z"):
        cmds.menuItem(label=a)
    cmds.optionMenuGrp("oj_primary", e=True, v="X")

    cmds.optionMenuGrp("oj_primary_dir", label="Primary Direction", cw2=(label_width, field_width))
    for a in ("+", "-"):
        cmds.menuItem(label=a)
    cmds.optionMenuGrp("oj_primary_dir", e=True, v="+")

    cmds.optionMenuGrp("oj_primary_space", label="Primary Axis Source", cw2=(label_width, field_width))
    for a in ("World", "Local", "Next/Children"):
        cmds.menuItem(label=a)
    cmds.optionMenuGrp("oj_primary_space", e=True, v="Next/Children", cc=_ui_update_state)

    cmds.optionMenuGrp("oj_primary_ref_axis", label="Primary Reference Axis", cw2=(label_width, field_width))
    for a in ("X", "Y", "Z"):
        cmds.menuItem(label=a)
    cmds.optionMenuGrp("oj_primary_ref_axis", e=True, v="Z")

    cmds.setParent("..")
    cmds.setParent("..")

    # Secondary Settings
    cmds.frameLayout(label="Secondary Settings", collapsable=True, collapse=False, mw=10, mh=10)
    cmds.columnLayout(adj=True, rs=6)

    cmds.optionMenuGrp("oj_secondary", label="Secondary Axis", cw2=(label_width, field_width))
    for a in ("X", "Y", "Z", "None"):
        cmds.menuItem(label=a)
    cmds.optionMenuGrp("oj_secondary", e=True, v="Y")

    cmds.optionMenuGrp("oj_up_dir", label="Secondary Direction", cw2=(label_width, field_width))
    for a in ("+", "-"):
        cmds.menuItem(label=a)
    cmds.optionMenuGrp("oj_up_dir", e=True, v="+")

    cmds.optionMenuGrp("oj_up_space", label="Secondary Axis Source", cw2=(label_width, field_width))
    for a in ("World", "Local", "Next/Children"):
        cmds.menuItem(label=a)
    cmds.optionMenuGrp("oj_up_space", e=True, v="World", cc=_ui_update_state)

    cmds.optionMenuGrp("oj_up_axis", label="Secondary Reference Axis", cw2=(label_width, field_width))
    for a in ("X", "Y", "Z"):
        cmds.menuItem(label=a)
    cmds.optionMenuGrp("oj_up_axis", e=True, v="Y")

    cmds.separator(h=4, style="in")

    cmds.setParent("..")
    cmds.setParent("..")

    # Buttons
    cmds.separator(h=4, style="none")
    cmds.rowLayout(nc=2, cw2=(210,210), ct2=("both","both"))
    cmds.button(label="Apply", c=_apply_orient_from_ui)
    cmds.button(label="Close",  c=lambda *_: cmds.deleteUI(_WIN))
    cmds.setParent("..")

    _ui_update_state()
    cmds.showWindow(_WIN)
    cmds.window(_WIN, e=True, resizeToFitChildren=True)

# 起動
show_orient_joint_like_window()
