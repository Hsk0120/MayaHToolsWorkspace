"""選択メッシュの skinCluster.maxInfluences を収集するユーティリティ。"""

import maya.cmds as cmds

import mlib
from mlib.common import Selection


def _get_renderable_mesh_shapes(dag):
    """transform/shape から、intermediate ではない mesh shape を返す

    Args:
        dag: 選択されたノード(コンポーネントはそれを持つ shape)。
    """
    if dag is None or not dag.isValid() or not dag.isType("dagNode"):
        return []

    # すでに shape の場合
    if dag.getType() == "mesh":
        shapes = [dag]
    else:
        shapes = dag.getChildren(shapes=True, intermediates=True, type="mesh")

    # intermediateObject を除外
    return [s for s in shapes if s.getType() == "mesh" and not s.isIntermediateObject()]

def _find_skin_clusters_from_shape(shape):
    """shape から skinCluster を探索（deformableShape->inMesh 経由優先）

    Args:
        shape: 処理対象のShape。
    """
    # まず「deformableShape」由来の接続で拾う（参照でも比較的安定）
    skins = shape.getConnections(type="skinCluster", asNode=True)
    if skins:
        return list(dict.fromkeys(skins))  # 重複除去

    # fallback: 履歴から拾う
    return list(dict.fromkeys(shape.getHistory(type="skinCluster")))

def get_max_influences_from_selection(verbose=True):
    """選択中メッシュ shape ごとの maxInfluences を取得します。

    Args:
        verbose (bool): 取得ログを出力するか。

    Returns:
        dict[str, dict[str, int]]: ``shape -> {skinCluster: maxInfluences}``。
    """
    # コンポーネントの選択は、それを持つ shape にまとめる。
    sel = Selection.capture().getOwners()
    if not sel:
        cmds.warning("No object is selected.")
        return {}

    results = {}  # {shape: {skinCluster: maxInf}}
    for raw in sel:
        shapes = _get_renderable_mesh_shapes(raw)
        if not shapes:
            if verbose:
                cmds.warning(f"Mesh shape not found: {raw.getName(full=True)}")
            continue

        for shape in shapes:
            skins = _find_skin_clusters_from_shape(shape)
            shape_name = shape.getName(full=True)
            if not skins:
                if verbose:
                    cmds.warning(f"skinCluster not found: {shape_name}")
                continue

            # 1 shape に複数 skinCluster があるケースも全件収集する。
            for skin in skins:
                skin_name = skin.getName()
                try:
                    max_inf = skin.getMaxInfluences()
                except Exception as e:
                    if verbose:
                        cmds.warning(f"Failed to get {skin_name}.maxInfluences ({e})")
                    continue

                results.setdefault(shape_name, {})[skin_name] = max_inf
                if verbose:
                    ref = shape.isFromReferencedFile()
                    print(f"[{ 'REF' if ref else 'LOCAL' }] {shape_name}  |  {skin_name}.maxInfluences = {max_inf}")

    return results

if __name__ == "__main__":
    # 実行
    get_max_influences_from_selection()
