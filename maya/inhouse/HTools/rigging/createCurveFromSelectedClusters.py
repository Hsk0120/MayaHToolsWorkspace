import maya.cmds as cmds
import cymel.core as cm

def _resolve_cluster_handle_transform(node):
    """Resolve any cluster-related node to its clusterHandle transform path."""
    node_type = cmds.nodeType(node)

    if node_type == "clusterHandle":
        # clusterHandle is a shape node; use its parent transform for world position.
        parents = cmds.listRelatives(node, parent=True, fullPath=True) or []
        return parents[0] if parents else None

    if node_type == "cluster":
        handles = cmds.listConnections(node, type="clusterHandle") or []
        if not handles:
            return None
        parents = cmds.listRelatives(handles[0], parent=True, fullPath=True) or []
        return parents[0] if parents else None

    if node_type == "transform":
        shapes = cmds.listRelatives(node, shapes=True, fullPath=True) or []
        for shape in shapes:
            if cmds.nodeType(shape) == "clusterHandle":
                return node

    return None


def create_curve_from_selected_clusters(degree=3, use_handle=True):
    """
    選択中の cluster に沿って nurbsCurve を作成する

    Args:
        degree (int): カーブの degree
        use_handle (bool): Trueなら clusterHandle の位置を使う
                           Falseなら deformer(cluster) から handle を辿る
    Returns:
        str | None: 作成された curve 名
    """

    selection = cmds.ls(sl=True, long=True) or []
    if not selection:
        cmds.warning("クラスターを選択してください。")
        return None

    cluster_handles = []

    for node in selection:
        handle_transform = _resolve_cluster_handle_transform(node)
        if handle_transform:
            cluster_handles.append(handle_transform)
        else:
            cmds.warning(u"クラスターではないノードをスキップしました: {0}".format(node))

    # Keep selection order while dropping duplicates.
    cluster_handles = list(dict.fromkeys(cluster_handles))

    if len(cluster_handles) < 2:
        cmds.warning("2つ以上のクラスターが必要です。")
        return None

    points = []
    for handle in cluster_handles:
        sel = cm.CyObject(handle)
        pos = sel.getTranslation(ws=True)
        points.append((pos[0], pos[1], pos[2]))

    # degree が point数以上だと作れないので調整
    degree = min(degree, len(points) - 1)

    print("points:", points)
    curve = cmds.curve(p=points, d=degree, name="clusterPath_crv")
    cmds.select(curve)
    return curve


create_curve_from_selected_clusters()