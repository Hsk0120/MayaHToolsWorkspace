"""選択メッシュのスキニング influence ジョイントを選択するツール。"""

import maya.cmds as cmds
import maya.api.OpenMaya as om2
import maya.api.OpenMayaAnim as oma2


def select_skinning_joints_from_selection():
    """現在選択の先頭メッシュから influence ジョイントを選択します。"""
    # 選択取得
    sel = cmds.ls(sl=True, long=True)
    if not sel:
        cmds.error("No mesh is selected.")

    mesh = sel[0]

    # shape を取得
    shapes = cmds.listRelatives(mesh, shapes=True, fullPath=True) or []
    if not shapes:
        cmds.error("The selected object has no shape.")

    shape = shapes[0]

    # skinCluster を取得
    skin_clusters = cmds.ls(cmds.listHistory(shape), type="skinCluster")
    if not skin_clusters:
        cmds.error("skinCluster not found.")

    skin = skin_clusters[0]

    # influence joint を取得して選択
    # 名前が重複しても一意になるよう、OpenMaya の DAG パスから完全パスを取得する。
    skin_sel = om2.MSelectionList()
    skin_sel.add(skin)
    skin_fn = oma2.MFnSkinCluster(skin_sel.getDependNode(0))
    joints = [path.fullPathName() for path in skin_fn.influenceObjects()]
    cmds.select(joints, replace=True)


if __name__ == "__main__":
    select_skinning_joints_from_selection()
