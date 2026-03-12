import maya.cmds as cmds

def _safe_name(base):
    if not cmds.objExists(base):
        return base
    i = 1
    while cmds.objExists(f"{base}{i}"):
        i += 1
    return f"{base}{i}"

def _incoming_plugs(dest_plug):
    try:
        return cmds.listConnections(dest_plug, s=True, d=False, p=True) or []
    except Exception:
        return []

def _is_animcurve(node):
    try:
        nt = cmds.nodeType(node)
    except Exception:
        return False
    return bool(nt and nt.startswith("animCurve"))

def _find_direct_animcurve(dest_plug):
    """dest_plug の入力に直結している animCurve ノードを返す（なければ None）"""
    for src_plug in _incoming_plugs(dest_plug):
        src_node = src_plug.split(".", 1)[0]
        if _is_animcurve(src_node):
            return src_node
    return None

def _list_keyable_scalar_plugs(node):
    """
    keyable 属性の plug を列挙（compound は子へ展開）。
    """
    plugs = []
    attrs = cmds.listAttr(node, keyable=True) or []
    for a in attrs:
        # compound（translate等）は子へ
        try:
            children = cmds.attributeQuery(a, node=node, listChildren=True) or []
        except Exception:
            children = []

        if children:
            for c in children:
                p = f"{node}.{c}"
                if cmds.objExists(p):
                    plugs.append(p)
            continue

        p = f"{node}.{a}"
        if not cmds.objExists(p):
            continue

        # lock / multi は除外
        try:
            if cmds.getAttr(p, lock=True):
                continue
        except Exception:
            continue

        try:
            if cmds.attributeQuery(a, node=node, multi=True):
                continue
        except Exception:
            pass

        plugs.append(p)

    return sorted(set(plugs))

def _clone_animcurve_via_keys(src_anim, suffix="_bak"):
    """
    cmds.duplicate() を使わず、同型 animCurve を作って copyKey/pasteKey で複製する。
    失敗時は None。
    """
    if not src_anim or not cmds.objExists(src_anim):
        return None

    try:
        src_type = cmds.nodeType(src_anim)  # 例: animCurveTL / animCurveTA / animCurveTU ...
        dst_anim = cmds.createNode(src_type)
        dst_anim = cmds.rename(dst_anim, _safe_name(f"{src_anim}{suffix}"))
    except Exception:
        return None

    # 主要設定の複製（存在する範囲で）
    for attr in ("preInfinity", "postInfinity", "useWeightedTangents"):
        try:
            if cmds.attributeQuery(attr, node=src_anim, exists=True) and cmds.attributeQuery(attr, node=dst_anim, exists=True):
                cmds.setAttr(f"{dst_anim}.{attr}", cmds.getAttr(f"{src_anim}.{attr}"))
        except Exception:
            pass

    # キー複製（copyKey/pasteKey は animCurve で安定しやすい）
    try:
        cmds.copyKey(src_anim)  # 全キー
        # replaceCompletely: dst の内容を完全置換
        cmds.pasteKey(dst_anim, option="replaceCompletely")
    except Exception:
        # キーが無い等で例外になる可能性があるので掃除して抜ける
        try:
            cmds.delete(dst_anim)
        except Exception:
            pass
        return None

    # 接線/タンジェント設定も可能な範囲で引き継ぎ（保険）
    # pasteKeyで大抵入りますが、必要ならここを拡張してください
    return dst_anim

def duplicate_anim_only_and_rewire_selected_v2(
    suffix="_bak",
    disconnect_old=True,
    keep_old_curve=True,
    verbose=True
):
    """
    選択ノードの keyable 属性について、直結 animCurve を「キー複製方式」で作り直して差し替える。
    """
    sels = cmds.ls(sl=True, long=True) or []
    if not sels:
        cmds.warning("対象が選択されていません。")
        return []

    results = []
    for n in sels:
        # shape選択だった場合は transform に寄せる
        try:
            if cmds.nodeType(n) != "transform":
                parents = cmds.listRelatives(n, parent=True, fullPath=True) or []
                if parents:
                    n = parents[0]
        except Exception:
            if verbose:
                cmds.warning(f"スキップ: ノード解決失敗 -> {n}")
            continue

        rewired = 0
        skipped = 0
        old_deleted = 0

        for dest_plug in _list_keyable_scalar_plugs(n):
            src_anim = _find_direct_animcurve(dest_plug)
            if not src_anim:
                skipped += 1
                continue

            dst_anim = _clone_animcurve_via_keys(src_anim, suffix=suffix)
            if not dst_anim:
                skipped += 1
                if verbose:
                    cmds.warning(f"複製失敗（キー複製方式でもNG）: {src_anim} -> {dest_plug}")
                continue

            # 旧カーブの切断（想定: src_anim.output -> dest_plug）
            if disconnect_old:
                try:
                    cmds.disconnectAttr(f"{src_anim}.output", dest_plug)
                except Exception:
                    pass

            # 新カーブ接続
            try:
                cmds.connectAttr(f"{dst_anim}.output", dest_plug, f=True)
                rewired += 1
            except Exception:
                skipped += 1
                if verbose:
                    cmds.warning(f"接続失敗: {dst_anim}.output -> {dest_plug}（新規カーブ削除）")
                try:
                    cmds.delete(dst_anim)
                except Exception:
                    pass
                continue

            # 旧カーブ削除オプション
            if disconnect_old and (not keep_old_curve):
                try:
                    cmds.delete(src_anim)
                    old_deleted += 1
                except Exception:
                    pass

        results.append({
            "node": n,
            "rewired": rewired,
            "skipped": skipped,
            "old_deleted": old_deleted
        })

    return results


if __name__ == "__main__":
    # 実行例：
    # 選択コントローラの animCurve をキー複製で作り直して同じ属性へ差し替え（旧カーブは残す）
    duplicate_anim_only_and_rewire_selected_v2(suffix="_bak", disconnect_old=True, keep_old_curve=True, verbose=True)