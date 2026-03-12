# -*- coding: utf-8 -*-
import maya.cmds as cmds

def _is_joint(node):
    return cmds.objExists(node) and cmds.nodeType(node) == 'joint'

def _get_parent_joint(jnt):
    parents = cmds.listRelatives(jnt, parent=True, type='joint', fullPath=True) or []
    return parents[0] if parents else None

def _find_skinclusters_using_influence(inf):
    """
    influence(inf) が接続されている skinCluster を列挙
    """
    scs = cmds.listConnections(inf, type='skinCluster') or []
    # 重複排除しつつ順序維持
    seen = set()
    out = []
    for sc in scs:
        if sc not in seen:
            seen.add(sc)
            out.append(sc)
    return out

def _get_influences(sc):
    return cmds.skinCluster(sc, q=True, inf=True) or []

def _get_uuid(node):
    uuids = cmds.ls(node, uuid=True) or []
    return uuids[0] if len(uuids) == 1 else None

def _is_influence_in_skincluster(sc, inf):
    target_uuid = _get_uuid(inf)
    if not target_uuid:
        return False
    for influence in _get_influences(sc):
        uuids = cmds.ls(influence, uuid=True) or []
        if target_uuid in uuids:
            return True
    return False

def _get_geometries(sc):
    # skinCluster に紐づく shape / transform を拾う
    geos = cmds.skinCluster(sc, q=True, g=True) or []
    return geos

def _get_joint_liw(jnt):
    attr = jnt + ".liw"
    if not cmds.objExists(attr):
        return None
    try:
        return bool(cmds.getAttr(attr))
    except RuntimeError:
        return None

def _set_joint_liw_safe(jnt, value):
    attr = jnt + ".liw"
    if not cmds.objExists(attr):
        return False
    try:
        cmds.setAttr(attr, int(bool(value)))
        return True
    except RuntimeError:
        return False

def _unlock_joint_liw_temporarily(jnt):
    prev = _get_joint_liw(jnt)
    if prev is None:
        return None
    _set_joint_liw_safe(jnt, 0)
    return prev

def _restore_joint_liw(jnt, prev):
    if prev is None:
        return
    if not _set_joint_liw_safe(jnt, prev):
        cmds.warning("liw 復元に失敗: %s" % jnt)

def _list_geo_vertices(geo):
    try:
        vtx_count = cmds.polyEvaluate(geo, v=True)
    except RuntimeError:
        return []
    if vtx_count is None:
        return []
    return ["%s.vtx[%d]" % (geo, i) for i in range(vtx_count)]

def _ensure_influence(sc, inf, weight=0.0):
    if _is_influence_in_skincluster(sc, inf):
        return
    prev_liw = _unlock_joint_liw_temporarily(inf)
    try:
        cmds.skinCluster(sc, e=True, ai=inf, wt=weight, lw=False)
    finally:
        _restore_joint_liw(inf, prev_liw)

def _transfer_weights_child_to_parent_for_geo(sc, geo, child, parent, eps=1e-8):
    """
    単一ジオメトリ(geo)上で child のウェイトを parent へ移管
    child が影響するコンポーネントだけを走査
    """
    # コンポーネント列挙
    # q=True 時の skinCluster.geometry は bool フラグのため、文字列 geo は渡せない
    affected = _list_geo_vertices(geo)
    if not affected:
        return

    # ウェイト転送
    for comp in affected:
        try:
            c_w = cmds.skinPercent(sc, comp, q=True, t=child) or 0.0
        except RuntimeError:
            # コンポーネントが無効など
            continue
        if c_w <= eps:
            continue

        try:
            p_w = cmds.skinPercent(sc, comp, q=True, t=parent) or 0.0
        except RuntimeError:
            p_w = 0.0

        new_p = p_w + c_w

        # まず parent を増やす → その後 child を 0 に
        # normalize=True で都度正規化される。厳密な “加算” を維持したい場合は
        # normalize=False にして最後に一括正規化も可だが、影響数が多いと破綻しやすい。
        cmds.skinPercent(sc, comp, tv=[(parent, new_p)], normalize=True)
        cmds.skinPercent(sc, comp, tv=[(child, 0.0)], normalize=True)

def _remove_influence_safe(sc, inf):
    if not _is_influence_in_skincluster(sc, inf):
        return
    prev_liw = _unlock_joint_liw_temporarily(inf)
    try:
        # removeInfluence は “ウェイトが残っている” と失敗することがあるので
        # 本スクリプトでは事前に 0 化している前提
        cmds.skinCluster(sc, e=True, ri=inf)
    finally:
        _restore_joint_liw(inf, prev_liw)

def _reparent_children(child_jnt, new_parent_jnt):
    """
    child_jnt の子ジョイントを new_parent_jnt に付け替え
    """
    kids = cmds.listRelatives(child_jnt, children=True, type='joint') or []
    for k in kids:
        try:
            cmds.parent(k, new_parent_jnt)
        except RuntimeError:
            pass

def lod_like_collapse_selected_joints(
        delete_joint=True,
        reparent_children_to_parent=True,
        eps=1e-8
    ):
    """
    選択ジョイントのウェイトを親ジョイントに移管し、選択ジョイントを削除する。
    親が skinCluster に未登録なら addInfluence してから移管する。
    """
    sel = cmds.ls(sl=True, type='joint', long=True) or []
    if not sel:
        cmds.warning("joint を選択してください。")
        return

    # 処理順：子→親の順が安全（階層が混ざって選択されていても崩れにくい）
    # DAG 深度でソート（深い＝子を先）
    def depth(n):
        p = cmds.listRelatives(n, parent=True, fullPath=True) or []
        d = 0
        cur = n
        while True:
            ps = cmds.listRelatives(cur, parent=True, fullPath=True) or []
            if not ps:
                break
            cur = ps[0]
            d += 1
        return d
    sel_sorted = sorted(sel, key=depth, reverse=True)

    for child in sel_sorted:
        if not _is_joint(child):
            continue

        parent = _get_parent_joint(child)
        if not parent:
            cmds.warning("親ジョイントが見つからないためスキップ: %s" % child)
            continue

        # child が入っている skinCluster を列挙
        skinclusters = _find_skinclusters_using_influence(child)
        if not skinclusters:
            # スキンに使われていないジョイントは、指定要件的には “削除だけ” でも良いはずだが
            # 事故防止で警告してから削除
            cmds.warning("skinCluster が見つからない（スキン未使用の可能性）: %s" % child)
            if reparent_children_to_parent:
                _reparent_children(child, parent)
            if delete_joint:
                try:
                    cmds.delete(child)
                except RuntimeError:
                    pass
            continue

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
                cmds.delete(child)
            except RuntimeError:
                cmds.warning("削除に失敗: %s" % child)


# 実行例：
# 選択ジョイントを親へウェイト移管して削除（子階層は親へ付け替え）
lod_like_collapse_selected_joints()