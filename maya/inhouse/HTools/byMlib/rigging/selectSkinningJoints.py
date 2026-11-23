"""選択メッシュのスキニング influence ジョイントを選択するツール。"""

import maya.cmds as cmds

import mlib


def select_skinning_joints_from_selection():
    """現在選択の先頭メッシュから influence ジョイントを選択します。"""
    # 選択取得
    sel = mlib.ls(sl=True, long=True)
    if not sel:
        cmds.error("No mesh is selected.")

    mesh = sel[0]

    # shape を取得
    shapes = mesh.getChildren(shapes=True, intermediates=True, type="shape") if isinstance(mesh, mlib.Transform) else []
    if not shapes:
        cmds.error("The selected object has no shape.")

    shape = shapes[0]

    # skinCluster を取得
    skin_clusters = shape.getHistory(type="skinCluster")
    if not skin_clusters:
        cmds.error("skinCluster not found.")

    skin = skin_clusters[0]

    # influence joint を取得して選択
    # インフルエンスは DAG パスを持つオブジェクトなので、名前が重複しても一意に選択できる。
    mlib.select(skin.getInfluences(), replace=True)


if __name__ == "__main__":
    select_skinning_joints_from_selection()
