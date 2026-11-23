"""選択した clusterHandle 位置からカーブを生成するツール。"""

import maya.cmds as cmds

import mlib
from mlib.common import units

def _resolve_cluster_handle_transform(node):
    """cluster 関連ノードを clusterHandle の Transform へ解決します。

    Args:
        node (mlib.Node): cluster / clusterHandle / transform。

    Returns:
        mlib.Transform | None: clusterHandle Transform。解決できない場合は None。
    """
    node_type = node.getType()

    if node_type == "clusterHandle":
        # clusterHandle は shape なので、位置取得に使う親 Transform へ変換する。
        return node.getParent()

    if node_type == "cluster":
        handle = node.getConnections(type="clusterHandle", asNode=True, index=0)
        if handle is None:
            return None
        return handle.getParent()

    if node_type == "transform":
        for shape in node.getShapes():
            if shape.getType() == "clusterHandle":
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
    selection = mlib.ls(sl=True)
    if not selection:
        cmds.warning("Select clusters.")
        return None

    cluster_handles = []

    for node in selection:
        # コンポーネントはノードでないので、元と同じく cluster でないものとして飛ばす。
        handle_transform = _resolve_cluster_handle_transform(node) if isinstance(node, mlib.Node) else None
        if handle_transform:
            cluster_handles.append(handle_transform)
        else:
            cmds.warning(u"Skipped a node that is not a cluster: {0}".format(node.getFullName()))

    # 選択順を維持したまま重複ハンドルだけを除去する。
    cluster_handles = list(mlib.Nodes(cluster_handles))

    if len(cluster_handles) < 2:
        cmds.warning("Two or more clusters are required.")
        return None

    points = []
    for handle in cluster_handles:
        # 従来の処理と同じく、ワールド空間の回転ピボット位置を使う(cm)。
        points.append(handle.getPivot(ws=True, kind="rotate"))

    # degree が point数以上だと作れないので調整
    degree = min(degree, len(points) - 1)

    # 表示は元と同じく UI の距離単位で出す。
    print("points:", [tuple(units.distanceToUi(value) for value in point) for point in points])
    curve = mlib.createCurve(points, degree=degree, name="clusterPath_crv").getTransform()
    curve.select()
    return curve.getName()


if __name__ == "__main__":
    create_curve_from_selected_clusters()
