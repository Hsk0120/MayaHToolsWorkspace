"""選択ノードの直結 animCurve を複製して再配線するツール。"""

import maya.cmds as cmds

import mlib
from mlib.decorator import undoChunk


def _safe_name(base):
    """衝突しないノード名を返します。

    Args:
        base: 重複回避や連番付加に使う元の名前。
    """
    if not mlib.objExists(base):
        return base
    i = 1
    while mlib.objExists(f"{base}{i}"):
        i += 1
    return f"{base}{i}"

def _connect_attr(src_attr, dst_attr):
    """接続先のロックを解除せずに src_attr から dst_attr へ強制接続する。

    同じ接続が既にある場合と接続先がロックされている場合を事前に判定して例外にし、
    呼び出し側の例外処理で扱えるようにする。

    Args:
        src_attr (mlib.Plug): 接続元アトリビュート。
        dst_attr (mlib.Plug): 接続先アトリビュート。

    Raises:
        RuntimeError: 接続先がロックされている、または既に同じ接続がある場合。
    """
    if dst_attr.isLocked():
        raise RuntimeError(f"Attribute is locked: {dst_attr.getName(full=True)}")
    if dst_attr.isConnected(src_attr, destination=False):
        raise RuntimeError(f"Already connected: {src_attr.getName(full=True)} -> {dst_attr.getName(full=True)}")
    dst_attr.connect(src_attr, force=True, unlock=False)

def _incoming_plugs(dest_plug):
    """指定プラグへの入力接続プラグ一覧を取得します。

    Args:
        dest_plug (mlib.Plug): 照会または更新するアトリビュート参照。
    """
    try:
        return dest_plug.getConnections(source=True, destination=False)
    except Exception:
        return []

def _is_animcurve(node):
    """ノードが animCurve 系か判定します。

    Args:
        node (mlib.Node): 処理対象のノード参照。
    """
    try:
        nt = node.getType()
    except Exception:
        return False
    return bool(nt and nt.startswith("animCurve"))

def _find_direct_animcurve(dest_plug):
    """dest_plug の入力に直結している animCurve ノードを返す（なければ None）

    Args:
        dest_plug (mlib.Plug): 照会または更新するアトリビュート参照。
    """
    for src_plug in _incoming_plugs(dest_plug):
        src_node = src_plug.getNode()
        if _is_animcurve(src_node):
            return src_node
    return None

def _list_keyable_scalar_plugs(node):
    """
    keyable 属性の plug を列挙（compound は子へ展開）。

    Args:
        node (mlib.Node): 対象ノード。

    Returns:
        list[tuple[str, mlib.Plug]]: 複製対象プラグの名前(``<ノードの完全な名前>.<アトリビュート>``)と Plug。名前順。
    """
    node_name = node.getName(full=True)
    plugs = {}
    for plug in node.getPlugs(keyable=True):
        # compound（translate 等）は子属性に展開して処理する。
        if plug.isCompound():
            for child in plug.getChildren():
                plugs[f"{node_name}.{child.getAttributeName()}"] = child
            continue

        # lock / multi は安全のため除外。
        if plug.isLocked():
            continue
        if plug.isMulti():
            continue

        plugs[f"{node_name}.{plug.getAttributeName()}"] = plug

    return [(name, plugs[name]) for name in sorted(plugs)]

def _clone_animcurve_via_keys(src_anim, suffix="_bak"):
    """
    duplicate を使わず、同型 animCurve を作って copyKey/pasteKey で複製する。

    Args:
        src_anim (mlib.AnimCurve): 複製元 animCurve。
        suffix (str): 複製ノード名サフィックス。

    Returns:
        mlib.AnimCurve | None: 複製後 animCurve。失敗時は None。
    """
    if src_anim is None or not src_anim.isValid():
        return None

    try:
        src_type = src_anim.getType()  # 例: animCurveTL / animCurveTA / animCurveTU ...
        dst_anim = mlib.createNode(src_type)
        dst_anim.rename(_safe_name(f"{src_anim.getName()}{suffix}"))
    except Exception:
        return None

    # 主要設定の複製（存在する範囲で）
    for attr in ("preInfinity", "postInfinity", "useWeightedTangents"):
        try:
            if src_anim.hasAttr(attr) and dst_anim.hasAttr(attr):
                dst_anim.getPlug(attr).set(src_anim.getPlug(attr).get())
        except Exception:
            pass

    # キー複製（copyKey/pasteKey は animCurve で比較的安定）。
    try:
        # 元の版の copyKey/pasteKey と同じく、キーの無いカーブは失敗として扱う。
        if not src_anim.getKeyCount():
            raise RuntimeError("No keys to copy.")
        # 接線・ブレークダウン・ウェイトを含めて dst のキーを完全に置き換える(クリップボードは使わない)。
        dst_anim.replaceKeys(src_anim)
    except Exception:
        # キーが無い等で例外になる可能性があるので掃除して抜ける
        try:
            dst_anim.delete()
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

    Args:
        suffix (str): 複製 animCurve 名のサフィックス。
        disconnect_old (bool): 旧カーブ接続を外すか。
        keep_old_curve (bool): 旧カーブを削除せず残すか。
        verbose (bool): 警告ログを出すか。

    Returns:
        list[dict[str, str | int]]: ノードごとの処理結果サマリ。
    """
    sels = mlib.ls(sl=True)
    if not sels:
        cmds.warning("Nothing is selected.")
        return []

    # 全ノードの差し替えを1回のUndoで戻せるようにまとめる。
    with undoChunk("duplicateAnimCurve"):
        results = []
        for n in sels:
            # shape 選択時は親 Transform を実処理対象にする。
            try:
                if n.getType() != "transform":
                    parent = n.getParent()
                    if parent is not None:
                        n = parent
            except Exception:
                if verbose:
                    cmds.warning(f"Skip: could not resolve node -> {n.getName(full=True)}")
                continue

            rewired = 0
            skipped = 0
            old_deleted = 0

            for dest_name, dest_plug in _list_keyable_scalar_plugs(n):
                src_anim = _find_direct_animcurve(dest_plug)
                if not src_anim:
                    skipped += 1
                    continue

                dst_anim = _clone_animcurve_via_keys(src_anim, suffix=suffix)
                if not dst_anim:
                    skipped += 1
                    if verbose:
                        cmds.warning(f"Duplicate failed (also with the key copy method): {src_anim.getName()} -> {dest_name}")
                    continue

                # 旧カーブの切断（想定: src_anim.output -> dest_plug）。
                # ロックされた接続先は下の接続で失敗扱いにし、旧カーブの接続を残す。
                if disconnect_old and not dest_plug.isLocked():
                    try:
                        dest_plug.disconnect(src_anim.getPlug("output"))
                    except Exception:
                        pass

                # 新カーブを同じ属性へ接続して差し替える。
                try:
                    _connect_attr(dst_anim.getPlug("output"), dest_plug)
                    rewired += 1
                except Exception:
                    skipped += 1
                    if verbose:
                        cmds.warning(f"Connection failed: {dst_anim.getName()}.output -> {dest_name} (new curve deleted)")
                    try:
                        dst_anim.delete()
                    except Exception:
                        pass
                    continue

                # 旧カーブ削除オプション
                if disconnect_old and (not keep_old_curve):
                    try:
                        src_anim.delete()
                        old_deleted += 1
                    except Exception:
                        pass

            results.append({
                "node": n.getName(full=True),
                "rewired": rewired,
                "skipped": skipped,
                "old_deleted": old_deleted
            })

    return results


if __name__ == "__main__":
    # 実行例：
    # 選択コントローラの animCurve をキー複製で作り直して同じ属性へ差し替え（旧カーブは残す）
    duplicate_anim_only_and_rewire_selected_v2(suffix="_bak", disconnect_old=True, keep_old_curve=True, verbose=True)