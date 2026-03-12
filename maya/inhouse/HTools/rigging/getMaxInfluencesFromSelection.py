import maya.cmds as cmds

def _to_dag_object(node):
    """コンポーネント選択を transform / shape に寄せる"""
    if not node:
        return None
    # vtx 等のコンポーネントは 'pSphere1.vtx[0]' のような形式
    return node.split('.', 1)[0]

def _get_renderable_mesh_shapes(dag):
    """transform/shape から、intermediate ではない mesh shape を返す"""
    dag = _to_dag_object(dag)
    if not dag or not cmds.objExists(dag):
        return []

    # すでに shape の場合
    if cmds.nodeType(dag) == "mesh":
        shapes = [dag]
    else:
        shapes = cmds.listRelatives(dag, shapes=True, fullPath=True) or []

    out = []
    for s in shapes:
        if cmds.nodeType(s) != "mesh":
            continue
        # intermediateObject を除外
        if cmds.getAttr(s + ".intermediateObject"):
            continue
        out.append(s)
    return out

def _find_skin_clusters_from_shape(shape):
    """shape から skinCluster を探索（deformableShape->inMesh 経由優先）"""
    # まず「deformableShape」由来の接続で拾う（参照でも比較的安定）
    skins = cmds.ls(cmds.listConnections(shape, type="skinCluster") or [], type="skinCluster")
    if skins:
        return list(dict.fromkeys(skins))  # 重複除去

    # fallback: 履歴から拾う
    hist = cmds.listHistory(shape, pruneDagObjects=True) or []
    skins = cmds.ls(hist, type="skinCluster") or []
    return list(dict.fromkeys(skins))

def get_max_influences_from_selection(verbose=True):
    sel = cmds.ls(sl=True, long=True) or []
    if not sel:
        cmds.warning("オブジェクトが選択されていません。")
        return {}

    results = {}  # {shape: {skinCluster: maxInf}}
    for raw in sel:
        dag = _to_dag_object(raw)
        shapes = _get_renderable_mesh_shapes(dag)
        if not shapes:
            if verbose:
                cmds.warning(f"メッシュ shape が見つかりません: {raw}")
            continue

        for shape in shapes:
            skins = _find_skin_clusters_from_shape(shape)
            if not skins:
                if verbose:
                    cmds.warning(f"skinCluster が見つかりません: {shape}")
                continue

            for skin in skins:
                try:
                    max_inf = cmds.getAttr(f"{skin}.maxInfluences")
                except Exception as e:
                    if verbose:
                        cmds.warning(f"取得失敗: {skin}.maxInfluences ({e})")
                    continue

                results.setdefault(shape, {})[skin] = max_inf
                if verbose:
                    ref = cmds.referenceQuery(shape, isNodeReferenced=True)
                    print(f"[{ 'REF' if ref else 'LOCAL' }] {shape}  |  {skin}.maxInfluences = {max_inf}")

    return results

if __name__ == "__main__":
    # 実行
    get_max_influences_from_selection()