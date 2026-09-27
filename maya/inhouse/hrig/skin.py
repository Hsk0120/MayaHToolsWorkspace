"""既存メッシュを変更しないスキンLOD作成と表示・評価切替。"""

from maya import cmds

import hlib
from hlib.decorators.undo import undo_chunk


@undo_chunk('hrig.bind_mesh')
def bind_mesh(rig, mesh, helpers=True):
    """未スキニングのメッシュを部位の変形骨へバインドする。

    Args:
        rig (LimbRig): 構築済み部位。
        mesh (str): メッシュまたは親transform。
        helpers (bool): 補助骨をinfluenceへ含める。

    Returns:
        str: 作成したskinCluster。
    """
    if cmds.ls(cmds.listHistory(mesh) or [], type='skinCluster'):
        raise ValueError('Mesh already has a skinCluster')
    joints = rig.joints() if helpers else rig.joints()[:3]
    return cmds.skinCluster(list(joints), mesh, toSelectedBones=True,
                            maximumInfluences=4, normalizeWeights=1)[0]


@undo_chunk('hrig.create_skin_lod')
def create_skin_lod(rig, source, proxy, source_skin):
    """別トポロジーの軽量モデルへウェイトを転送し、補助骨を使わずバインドする。

    Args:
        rig (LimbRig): 使用する部位。
        source (str): 高詳細モデル。
        proxy (str): ユーザーが用意した未スキニングの軽量モデル。
        source_skin (str): 高詳細モデルのskinCluster。

    Returns:
        str: proxy側skinCluster。

    Note:
        closestPoint/closestJointによる近似転送。自動メッシュ削減や
        異なる姿勢のモデルの補正は行わない。基準姿勢で実行する。
    """
    if hlib.node(source_skin).type() != 'skinCluster':
        raise TypeError('Expected a skinCluster')
    if source_skin not in (cmds.ls(cmds.listHistory(source) or [], type='skinCluster') or []):
        raise ValueError('source_skin does not deform source')
    if cmds.ls(source, long=True) == cmds.ls(proxy, long=True):
        raise ValueError('Source and proxy must be different')
    target_skin = bind_mesh(rig, proxy, helpers=False)
    try:
        cmds.copySkinWeights(sourceSkin=source_skin, destinationSkin=target_skin,
                             noMirror=True, surfaceAssociation='closestPoint',
                             influenceAssociation=['name', 'closestJoint'], normalize=True)
    except Exception:
        hlib.delete(target_skin)
        raise
    return target_skin


@undo_chunk('hrig.set_mesh_lod')
def set_mesh_lod(high_mesh, high_skin, proxy_mesh, proxy_skin, proxy=False):
    """表示とskinClusterのenvelope/nodeStateをセットで切り替える。

    Args:
        high_mesh (str): 高詳細モデル。
        high_skin (str): 高詳細モデルのskinCluster。
        proxy_mesh (str): 軽量モデル。
        proxy_skin (str): 軽量モデルのskinCluster。
        proxy (bool): 軽量側を有効にする。

    Note:
        この関数がenvelopeとnodeStateを管理する。キーや接続がある場合は拒否する。
        変形履歴の他のノードまで停止する保証はない。
    """
    pairs = ((high_mesh, high_skin, not proxy), (proxy_mesh, proxy_skin, proxy))
    for mesh, skin, active in pairs:
        if hlib.node(skin).type() != 'skinCluster':
            raise TypeError('Expected a skinCluster')
        for attr in (mesh + '.visibility', skin + '.envelope', skin + '.nodeState'):
            if not cmds.getAttr(attr, settable=True):
                raise ValueError('LOD attribute is not editable: ' + attr)
    for mesh, skin, active in pairs:
        hlib.plug(mesh + '.visibility').set(active)
        hlib.plug(skin + '.envelope').set(1 if active else 0)
        # skinClusterはBlockingを受け付けないためHasNoEffectを使う。
        hlib.plug(skin + '.nodeState').set(0 if active else 1)
