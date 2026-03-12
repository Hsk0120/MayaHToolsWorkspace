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
_DEBUG_ORIENT = True

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

def _compute_primary_world_vector(joint_name):
    """ジョイントの主軸方向（ワールド）を計算します。"""
    joint_pos = _compute_world_position(joint_name)
    child_joints = cmds.listRelatives(joint_name, c=True, type="joint", f=True) or []

    if child_joints:
        vec = _compute_world_position(child_joints[0]) - joint_pos
        nvec = _compute_normalized_vector(vec)
        if nvec is not None:
            return nvec

    parent = cmds.listRelatives(joint_name, p=True, type="joint", f=True)
    if parent:
        vec = joint_pos - _compute_world_position(parent[0])
        nvec = _compute_normalized_vector(vec)
        if nvec is not None:
            return nvec

    return None

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

def _compute_up_world_vector(joint_name, up_axis, up_direction, up_space):
    """UI 設定に基づく up ベクトル（ワールド）を計算します。"""
    sign = -1.0 if up_direction == "-" else 1.0
    if up_space == "next/children":
        up_vec = _compute_primary_world_vector(joint_name)
        if up_vec is None:
            return None
        return up_vec * sign
    if up_space == "local":
        world_matrix = _compute_world_matrix(joint_name)
        return _compute_axis_world_vector_from_matrix(world_matrix, up_axis) * sign
    return _compute_axis_vector(up_axis) * sign

def _compute_fallback_secondary_vector(primary_vec):
    """主軸とほぼ平行な up 指定時のフォールバック副軸を返します。"""
    world_y = _compute_axis_vector("y")
    world_x = _compute_axis_vector("x")
    ref = world_y if abs(primary_vec * world_y) < 0.999 else world_x
    return _compute_normalized_vector(ref ^ primary_vec)

def _compute_secondary_world_vector(primary_vec, up_vec):
    """主軸に直交する副軸を up ベクトルから計算します。"""
    secondary_vec = up_vec - (primary_vec * (primary_vec * up_vec))
    nvec = _compute_normalized_vector(secondary_vec)
    if nvec is None:
        return _compute_fallback_secondary_vector(primary_vec)
    return nvec

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

    target_secondary = _compute_secondary_world_vector(primary_vec, up_vec)
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
    up_dot, up_angle = _compute_debug_angle_deg(current_up_axis, _compute_normalized_vector(up_vec))

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
):
    """UI 設定から `jointOrient` に設定する XYZ 角度（度）を計算します。"""
    primary_vec = _compute_primary_vector_from_mode(
        joint_name,
        primary_axis,
        primary_space,
        primary_ref_axis,
    )

    if primary_vec is None:
        return None

    if primary_direction == "-":
        primary_vec *= -1.0

    up_vec = _compute_up_world_vector(joint_name, up_axis, up_direction, up_space)

    if up_vec is None:
        return None

    secondary_vec = _compute_secondary_world_vector(primary_vec, up_vec)
    axes = _compute_axis_basis_from_ui(primary_axis, secondary_axis, primary_vec, secondary_vec)
    if any(v is None for v in axes.values()):
        return None

    target_world_rot = _compute_rotation_matrix_from_axes(axes)

    parent = cmds.listRelatives(joint_name, p=True, type="joint", f=True)
    if parent:
        parent_world_matrix = _compute_world_matrix(parent[0])
        parent_world_rot = om2.MTransformationMatrix(parent_world_matrix).asRotateMatrix()
        local_rot = parent_world_rot.inverse() * target_world_rot
    else:
        local_rot = target_world_rot

    euler = om2.MTransformationMatrix(local_rot).rotation()
    return [math.degrees(euler.x), math.degrees(euler.y), math.degrees(euler.z)]

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

    try:
        for j in joints:
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

            if _DEBUG_ORIENT:
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
