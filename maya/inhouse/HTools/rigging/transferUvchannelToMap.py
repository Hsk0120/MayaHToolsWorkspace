import maya.cmds as cmds

def transfer_uvchannel_to_map():
    # 選択中のトランスフォーム/シェイプからメッシュシェイプを収集
    selection = cmds.ls(sl=True, long=True) or []
    if not selection:
        cmds.warning(u'メッシュを選択してください。')
        return

    mesh_shapes = []

    for node in selection:
        if cmds.nodeType(node) == 'mesh':
            mesh_shapes.append(node)
        else:
            shapes = cmds.listRelatives(node, shapes=True, fullPath=True) or []
            mesh_shapes.extend([s for s in shapes if cmds.nodeType(s) == 'mesh'])

    mesh_shapes = list(set(mesh_shapes))

    if not mesh_shapes:
        cmds.warning(u'選択中にメッシュShapeが見つかりません。')
        return

    for mesh in mesh_shapes:
        uv_sets = cmds.polyUVSet(mesh, q=True, allUVSets=True) or []

        if 'UVChannel_1' not in uv_sets:
            cmds.warning(u'{} : UVChannel_1 が存在しないためスキップしました。'.format(mesh))
            continue

        # map1 が存在しない場合は作成
        if 'map1' not in uv_sets:
            cmds.polyUVSet(mesh, create=True, uvSet='map1')

        try:
            # UVChannel_1 を current にして map1 へコピー
            cmds.polyUVSet(mesh, currentUVSet=True, uvSet='UVChannel_1')
            cmds.polyCopyUV(mesh, uvSetNameInput='UVChannel_1', uvSetName='map1', ch=False)

            # current が削除対象だと失敗しやすいので map1 を current に変更
            cmds.polyUVSet(mesh, currentUVSet=True, uvSet='map1')

            # UVChannel_1 を削除
            cmds.polyUVSet(mesh, delete=True, uvSet='UVChannel_1')

            print(u'完了: {} | UVChannel_1 -> map1 転送後に削除'.format(mesh))

        except Exception as e:
            cmds.warning(u'{} : 処理中にエラーが発生しました - {}'.format(mesh, e))

transfer_uvchannel_to_map()