"""既存メッシュを変更しないスキンLOD作成と表示・評価切替。"""

import mlib

from mlib.decorator import undoChunk


@undoChunk("mlrig.bind_mesh")
def bind_mesh(rig, mesh, helpers=True):
    """未スキニングのメッシュを部位の変形骨へバインドする。

    Args:
        rig (LimbRig): 構築済み部位。
        mesh (str): メッシュまたは親transform。
        helpers (bool): 通常・ツイスト・曲げ補助骨をinfluenceへ含める。

    Returns:
        str: 作成したskinCluster。
    """
    joints = rig.getJoints() if helpers else rig.getJoints()[:3]
    return mlib.bindSkin(joints, mesh, maximumInfluences=4).getFullName()


@undoChunk("mlrig.create_skin_lod")
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
    if mlib.nodes.Node(source_skin).getType() != "skinCluster":
        raise TypeError("Expected a skinCluster")
    if not mlib.nodes.SkinCluster(source_skin).deforms(source):
        raise ValueError("source_skin does not deform source")
    if [item.getFullName() for item in mlib.ls(source, long=True)] == [
        item.getFullName() for item in mlib.ls(proxy, long=True)
    ]:
        raise ValueError("Source and proxy must be different")
    target_skin = bind_mesh(rig, proxy, helpers=False)
    try:
        mlib.nodes.SkinCluster(source_skin).copyWeightsTo(target_skin)
    except Exception:
        mlib.delete(target_skin)
        raise
    return target_skin


@undoChunk("mlrig.set_mesh_lod")
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
        if mlib.nodes.Node(skin).getType() != "skinCluster":
            raise TypeError("Expected a skinCluster")
        for attr in (mesh + ".visibility", skin + ".envelope", skin + ".nodeState"):
            if not mlib.getPlug(attr).isSettable():
                raise ValueError("LOD attribute is not editable: " + attr)
    for mesh, skin, active in pairs:
        mlib.getPlug(mesh + ".visibility").set(active)
        mlib.getPlug(skin + ".envelope").set(1 if active else 0)
        # skinClusterはBlockingを受け付けないためHasNoEffectを使う。
        mlib.getPlug(skin + ".nodeState").set(0 if active else 1)
