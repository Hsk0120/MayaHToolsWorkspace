"""選択した clusterHandle 位置からカーブを生成するツール。"""

import maya.cmds as cmds
import cymel.core as cm

def _resolve_cluster_handle_transform(node):
    """cluster 関連ノードを clusterHandle の Transform へ解決します。

    Args:
        node (str): cluster / clusterHandle / transform。

    Returns:
        str | None: clusterHandle Transform。解決できない場合は None。
    """
    node_type = cmds.nodeType(node)

    if node_type == "clusterHandle":
        # clusterHandle は shape なので、位置取得に使う親 Transform へ変換する。
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
        use_handle (bool): 互換引数（現在は常に handle 解決を行う）。
    Returns:
        str | None: 作成された curve 名
    """

    # 選択順をそのままカーブ通過順として使う。
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

    # 選択順を維持したまま重複ハンドルだけを除去する。
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