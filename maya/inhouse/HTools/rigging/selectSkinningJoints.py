import maya.cmds as cmds


if __name__ == "__main__":
    # 選択取得
    sel = cmds.ls(sl=True, long=True)
    if not sel:
        cmds.error("メッシュが選択されていません")

    mesh = sel[0]

    # shape を取得
    shapes = cmds.listRelatives(mesh, shapes=True, fullPath=True) or []
    if not shapes:
        cmds.error("選択オブジェクトに shape がありません")

    shape = shapes[0]

    # skinCluster を取得
    skin_clusters = cmds.ls(cmds.listHistory(shape), type="skinCluster")
    if not skin_clusters:
        cmds.error("skinCluster が見つかりません")

    skin = skin_clusters[0]

    # influence joint を取得
    joints = cmds.skinCluster(skin, q=True, influence=True)

    # 選択
    cmds.select(joints, replace=True)
