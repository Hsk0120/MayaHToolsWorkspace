# -*- coding: utf-8 -*-
"""選択ジョイントのウェイトを親へ統合する LOD 補助ツール。"""

import maya.cmds as cmds

import mlib
from mlib.decorator import undoChunk

def _is_joint(node):
    """ノードが joint かどうかを判定します。

    Args:
        node: 処理対象のノード参照。
    """
    return mlib.objExists(node) and mlib.getNode(node).getType() == 'joint'

def _get_parent_joint(jnt):
    """親ジョイントを取得します。

    Args:
        jnt: 処理対象のジョイント。
    """
    parent = mlib.getNode(jnt).getParent()
    return parent if parent is not None and parent.getType() == 'joint' else None

def _find_skinclusters_using_influence(inf):
    """influence(inf) が接続されている skinCluster を列挙

    Args:
        inf: ウェイトを割り当てる、または移管するインフルエンス。
    """
    # 重複は除き、接続の順を保つ。
    return mlib.getNode(inf).getSkinClusters()

def _get_influences(sc):
    """skinCluster の influence 一覧を返します。

    Args:
        sc: ウェイトを照会・編集するskinCluster。
    """
    # 同名ノードがあっても曖昧にならないよう、最短一意名にする。
    return mlib.getNode(sc).getInfluences().getNames()

def _is_influence_in_skincluster(sc, inf):
    """指定 influence が skinCluster に登録済みか判定します。

    Args:
        sc: ウェイトを照会・編集するskinCluster。
        inf: ウェイトを割り当てる、または移管するインフルエンス。
    """
    # 名前でなくノード(UUID)で比べる。
    return mlib.getNode(sc).hasInfluence(inf)

def _get_geometries(sc):
    # skinCluster に紐づく shape を拾う
    """skinClusterに関連付けられたジオメトリを取得する。

    Args:
        sc: ウェイトを照会・編集するskinCluster。

    Returns:
        Nodes: 対象ジオメトリ。
    """
    return mlib.getNode(sc).getGeometry()

def _get_joint_liw(jnt):
    """ジョイントの lockInfluenceWeights 状態を取得します。

    Args:
        jnt: 処理対象のジョイント。
    """
    joint = mlib.getNode(jnt)
    if not joint.hasAttr('lockInfluenceWeights'):
        return None
    try:
        return joint.isInfluenceLocked()
    except RuntimeError:
        return None

def _set_joint_liw_safe(jnt, value):
    """lockInfluenceWeights を安全に設定します。

    Args:
        jnt: 処理対象のジョイント。
        value: 変換・設定する入力値。
    """
    joint = mlib.getNode(jnt)
    if not joint.hasAttr('lockInfluenceWeights'):
        return False
    try:
        joint.setInfluenceLocked(bool(value))
        return True
    except RuntimeError:
        return False

def _unlock_joint_liw_temporarily(jnt):
    """liw を一時解除し、元状態を返します。

    Args:
        jnt: 処理対象のジョイント。
    """
    prev = _get_joint_liw(jnt)
    if prev is None:
        return None
    _set_joint_liw_safe(jnt, 0)
    return prev

def _restore_joint_liw(jnt, prev):
    """liw を元の状態へ復元します。

    Args:
        jnt: 処理対象のジョイント。
        prev: 操作前に保存した状態。
    """
    if prev is None:
        return
    if not _set_joint_liw_safe(jnt, prev):
        cmds.warning("Failed to restore liw: %s" % jnt)

def _list_geo_vertices(geo):
    """ポリゴン頂点コンポーネント一覧を返します。

    Args:
        geo: 処理対象のメッシュ。
    """
    geometry = mlib.getNode(geo)
    if not isinstance(geometry, mlib.Mesh):
        return []
    return geometry.getVertices()

def _ensure_influence(sc, inf, weight=0.0):
    """influence 未登録時のみ addInfluence します。

    Args:
        sc: ウェイトを照会・編集するskinCluster。
        inf: ウェイトを割り当てる、または移管するインフルエンス。
        weight: 設定するウェイト値。
    """
    if _is_influence_in_skincluster(sc, inf):
        return
    prev_liw = _unlock_joint_liw_temporarily(inf)
    try:
        mlib.getNode(sc).addInfluences(inf, weight=weight, lockWeights=False)
    finally:
        _restore_joint_liw(inf, prev_liw)

def _transfer_weights_child_to_parent_for_geo(sc, geo, child, parent, eps=1e-8):
    """単一ジオメトリ(geo)上で child のウェイトを parent へ移管
    child が影響するコンポーネントだけを走査

    Args:
        child: ウェイトの移管元インフルエンス。
        sc: ウェイトを照会・編集するskinCluster。
        geo: 処理対象のメッシュ。
        parent: 親ウィジェット。Noneは親を指定しない。
        eps: ゼロ判定・収束判定の許容誤差。
    """
    # コンポーネント列挙
    affected = _list_geo_vertices(geo)
    if not affected:
        return

    skin = mlib.getNode(sc)
    geometries = skin.getGeometry()
    if not geometries[0].sameNode(geo):
        # SkinCluster のウェイトの読み書きは先頭の形状だけが対象のため、2つ目以降の形状は1頂点ずつ cmds で移す。
        for comp in affected:
            try:
                # byMlib-gap: htoolsRigA-46 SkinCluster.getWeights/setWeights で先頭以外の形状を指定する
                c_w = cmds.skinPercent(str(skin), str(comp), q=True, t=str(child)) or 0.0
            except RuntimeError:
                continue
            if c_w <= eps:
                continue
            try:
                p_w = cmds.skinPercent(str(skin), str(comp), q=True, t=str(parent)) or 0.0
            except RuntimeError:
                p_w = 0.0
            new_p = p_w + c_w
            cmds.skinPercent(str(skin), str(comp), tv=[(str(parent), new_p)], normalize=True)
            cmds.skinPercent(str(skin), str(comp), tv=[(str(child), 0.0)], normalize=True)
        return

    # child と parent のウェイトを全頂点まとめて読む(頂点ごとに [child, parent])。
    rows = skin.getWeights([child, parent], rows=True)

    # ウェイト転送
    # child のウェイトを parent へ加算してから child を 0 にする。
    for comp, (c_w, p_w) in zip(affected, rows):
        if c_w <= eps:
            continue

        new_p = p_w + c_w

        # まず parent を増やす → その後 child を 0 に
        # normalize=True で都度正規化される。厳密な “加算” を維持したい場合は
        # normalize=False にして最後に一括正規化も可だが、影響数が多いと破綻しやすい。
        skin.setVertexWeights(comp, {parent: new_p}, normalize=True)
        skin.setVertexWeights(comp, {child: 0.0}, normalize=True)

def _remove_influence_safe(sc, inf):
    """influence を安全に削除します。

    Args:
        sc: ウェイトを照会・編集するskinCluster。
        inf: ウェイトを割り当てる、または移管するインフルエンス。
    """
    if not _is_influence_in_skincluster(sc, inf):
        return
    prev_liw = _unlock_joint_liw_temporarily(inf)
    try:
        # removeInfluence は “ウェイトが残っている” と失敗することがあるので
        # 本スクリプトでは事前に 0 化している前提(残りの配り直しは Maya 標準に任せる)
        mlib.getNode(sc).removeInfluence(inf, transferToParent=False)
    finally:
        _restore_joint_liw(inf, prev_liw)

def _reparent_children(child_jnt, new_parent_jnt):
    """child_jnt の子ジョイントを new_parent_jnt に付け替え

    Args:
        child_jnt: 子ノードを付け替える対象ジョイント。
        new_parent_jnt: 付け替え先の親ジョイント。
    """
    for k in mlib.getNode(child_jnt).getChildren(type='joint'):
        try:
            k.setParent(new_parent_jnt)
        except RuntimeError:
            pass

def lod_like_collapse_selected_joints(
        delete_joint=True,
        reparent_children_to_parent=True,
        eps=1e-8
    ):
    """選択ジョイントのウェイトを親ジョイントに移管し、選択ジョイントを削除する。
    親が skinCluster に未登録なら addInfluence してから移管する。

    Args:
        delete_joint: 処理後に対象ジョイントを削除するか。
        reparent_children_to_parent: 子ジョイントを対象の親へ付け替えるか。
        eps: ゼロ判定・収束判定の許容誤差。
    """
    sel = mlib.ls(sl=True, type='joint')
    if not sel:
        cmds.warning("Select joints.")
        return

    # 処理順は子→親が安全。
    # 親を先に処理すると、後続子の親参照やスキン状態が変わって不安定になる。
    def depth(n):
        d = 0
        cur = n.getParent()
        while cur is not None:
            cur = cur.getParent()
            d += 1
        return d
    sel_sorted = sorted(sel, key=depth, reverse=True)

    # 複数ジョイントの移管・削除をまとめて1回の Undo で戻せるようにする。
    with undoChunk("collapseJointWeightsToParent"):
        for child in sel_sorted:
            if not child.isValid() or not _is_joint(child):
                continue

            parent = _get_parent_joint(child)
            if not parent:
                cmds.warning("Skipped because the parent joint was not found: %s" % child.getFullName())
                continue

            # child が入っている skinCluster を列挙
            skinclusters = _find_skinclusters_using_influence(child)
            if not skinclusters:
                # スキンに使われていないジョイントは、指定要件的には “削除だけ” でも良いはずだが
                # 事故防止で警告してから削除
                cmds.warning("skinCluster not found (the joint may not be used for skinning): %s" % child.getFullName())
                if reparent_children_to_parent:
                    _reparent_children(child, parent)
                if delete_joint:
                    try:
                        child.delete(removeInfluence=False)
                    except RuntimeError:
                        pass
                continue

            # 子が使われている全 skinCluster に対して転送処理を行う。
            for sc in skinclusters:
                # 親が未登録なら addInfluence
                _ensure_influence(sc, parent, weight=0.0)

                # 対象ジオメトリごとに移管
                geos = _get_geometries(sc)
                for geo in geos:
                    _transfer_weights_child_to_parent_for_geo(sc, geo, child, parent, eps=eps)

                # influence から child を外す
                _remove_influence_safe(sc, child)

            # 階層維持：子ジョイントを親へ付け替え
            if reparent_children_to_parent:
                _reparent_children(child, parent)

            # 最後に child 自体を削除
            if delete_joint:
                try:
                    child.delete(removeInfluence=False)
                except RuntimeError:
                    cmds.warning("Failed to delete: %s" % child.getFullName())


# 実行例：
# 選択ジョイントを親へウェイト移管して削除（子階層は親へ付け替え）
if __name__ == "__main__":
    lod_like_collapse_selected_joints()
