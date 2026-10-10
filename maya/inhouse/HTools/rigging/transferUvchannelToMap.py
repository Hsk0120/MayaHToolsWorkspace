"""UVChannel_1 を map1 に転送し、元 UV セットを削除するツール。"""

import maya.cmds as cmds

def transfer_uvchannel_to_map():
    """選択メッシュの UVChannel_1 を map1 へコピーして置換します。"""
    # 選択中のトランスフォーム/シェイプからメッシュシェイプを収集
    selection = cmds.ls(sl=True, long=True) or []
    if not selection:
        cmds.warning(u'Select meshes.')
        return

    mesh_shapes = []

    for node in selection:
        if cmds.nodeType(node) == 'mesh':
            mesh_shapes.append(node)
        else:
            shapes = cmds.listRelatives(node, shapes=True, fullPath=True) or []
            mesh_shapes.extend([s for s in shapes if cmds.nodeType(s) == 'mesh'])

    # 重複 shape を排除して同一メッシュの二重処理を防ぐ。
    mesh_shapes = list(set(mesh_shapes))

    if not mesh_shapes:
        cmds.warning(u'No mesh shape found in the selection.')
        return

    for mesh in mesh_shapes:
        uv_sets = cmds.polyUVSet(mesh, q=True, allUVSets=True) or []

        if 'UVChannel_1' not in uv_sets:
            cmds.warning(u'{}: skipped because UVChannel_1 does not exist.'.format(mesh))
            continue

        # map1 が存在しない場合は作成
        if 'map1' not in uv_sets:
            cmds.polyUVSet(mesh, create=True, uvSet='map1')

        try:
            # UVChannel_1 を current にして map1 へコピー
            cmds.polyUVSet(mesh, currentUVSet=True, uvSet='UVChannel_1')
            cmds.polyCopyUV(mesh, uvSetNameInput='UVChannel_1', uvSetName='UVMap', ch=False)

            # current が削除対象だと失敗しやすいので map1 を current に変更
            cmds.polyUVSet(mesh, currentUVSet=True, uvSet='map1')

            # UVChannel_1 を削除
            cmds.polyUVSet(mesh, delete=True, uvSet='UVChannel_1')

            print(u'Done: {} | UVChannel_1 -> map1 transferred, then deleted'.format(mesh))

        except Exception as e:
            cmds.warning(u'{}: an error occurred - {}'.format(mesh, e))

if __name__ == "__main__":
    transfer_uvchannel_to_map()
