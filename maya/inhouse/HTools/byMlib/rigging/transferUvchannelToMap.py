"""UVChannel_1 を map1 に転送し、元 UV セットを削除するツール。"""

import maya.cmds as cmds

import mlib
from mlib.common import Selection

def transfer_uvchannel_to_map():
    """選択メッシュの UVChannel_1 を map1 へコピーして置換します。"""
    # 選択中のトランスフォーム/シェイプからメッシュシェイプを収集
    # (コンポーネントの選択は、それを持つ shape にまとめる)
    selection = Selection.capture().getOwners()
    if not selection:
        cmds.warning(u'Select meshes.')
        return

    mesh_shapes = []

    for node in selection:
        if node.getType() == 'mesh':
            mesh_shapes.append(node)
        elif node.isType('dagNode'):
            mesh_shapes.extend(node.getChildren(shapes=True, intermediates=True, type='mesh'))

    # 重複 shape を排除して同一メッシュの二重処理を防ぐ。
    mesh_shapes = list({mesh.getName(full=True): mesh for mesh in mesh_shapes}.values())

    if not mesh_shapes:
        cmds.warning(u'No mesh shape found in the selection.')
        return

    for mesh in mesh_shapes:
        uv_sets = mesh.getSetNames()

        if 'UVChannel_1' not in uv_sets:
            cmds.warning(u'{}: skipped because UVChannel_1 does not exist.'.format(mesh.getName(full=True)))
            continue

        # map1 が存在しない場合は作成
        if 'map1' not in uv_sets:
            mesh.createSet('map1')

        try:
            # UVChannel_1 を current にして map1 へコピー
            mesh.setCurrentSet('UVChannel_1')
            # 元の polyCopyUV と同じく、コピー先の UVMap が無ければ失敗にする(UVMap は作らない)。
            if 'UVMap' not in mesh.getSetNames():
                raise RuntimeError('UV set "UVMap" does not exist.\nCommand polyCopyUV failed. Open Script Editor for details.\n')
            mesh.copySet('UVChannel_1', 'UVMap', overwrite=True)

            # current が削除対象だと失敗しやすいので map1 を current に変更
            mesh.setCurrentSet('map1')

            # UVChannel_1 を削除
            mesh.deleteSet('UVChannel_1')

            print(u'Done: {} | UVChannel_1 -> map1 transferred, then deleted'.format(mesh.getName(full=True)))

        except Exception as e:
            cmds.warning(u'{}: an error occurred - {}'.format(mesh.getName(full=True), e))

if __name__ == "__main__":
    transfer_uvchannel_to_map()
