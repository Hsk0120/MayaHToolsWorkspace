# -*- coding: utf-8 -*-
import maya.cmds as cmds
import maya.mel as mel


def _to_shape(mesh):
    """
    transform / shape どちらが来ても mesh shape を返す
    """
    if not cmds.objExists(mesh):
        raise RuntimeError(u'Object does not exist: {}'.format(mesh))

    if cmds.nodeType(mesh) == 'mesh':
        return mesh

    shapes = cmds.listRelatives(mesh, shapes=True, fullPath=True, noIntermediate=True) or []
    for s in shapes:
        if cmds.nodeType(s) == 'mesh':
            return s

    raise RuntimeError(u'Mesh shape not found under: {}'.format(mesh))


def _get_skin_cluster(mesh):
    """
    mesh から関連 skinCluster を取得
    """
    shape = _to_shape(mesh)
    history = cmds.listHistory(shape, pruneDagObjects=True) or []
    skins = cmds.ls(history, type='skinCluster') or []
    if not skins:
        raise RuntimeError(u'skinCluster not found: {}'.format(mesh))
    return skins[0]


def _get_axis_index(axis):
    axis = axis.lower()
    table = {'x': 0, 'y': 1, 'z': 2}
    if axis not in table:
        raise RuntimeError(u'axis must be x, y, or z.')
    return table[axis]


def _all_vertices(mesh):
    shape = _to_shape(mesh)
    return cmds.ls('{}.vtx[*]'.format(shape), fl=True) or []


def _get_selected_mesh():
    """
    現在選択から最初のメッシュ(transform/shape/component)を返す
    """
    selection = cmds.ls(sl=True, long=True) or []
    for item in selection:
        node = item.split('.')[0]
        if not cmds.objExists(node):
            continue
        try:
            _to_shape(node)
            return node
        except RuntimeError:
            continue

    raise RuntimeError(u'No mesh selected. Please select a mesh object.')


def _get_selected_meshes():
    """
    現在選択からメッシュ(transform/shape/component)を重複なしで返す
    """
    selection = cmds.ls(sl=True, long=True) or []
    meshes = []
    seen = set()
    for item in selection:
        node = item.split('.')[0]
        if not cmds.objExists(node):
            continue
        try:
            _to_shape(node)
        except RuntimeError:
            continue

        if node in seen:
            continue
        seen.add(node)
        meshes.append(node)

    if not meshes:
        raise RuntimeError(u'No mesh selected. Please select at least one mesh object.')

    return meshes


def _pick_top_bottom_influences(skin_cluster, axis='y'):
    """
    skinCluster の influence から軸方向の最下端/最上端を返す
    可能なら joint のみを対象にする
    """
    axis_index = _get_axis_index(axis)
    influences = cmds.skinCluster(skin_cluster, q=True, influence=True) or []

    if len(influences) < 2:
        raise RuntimeError(u'Not enough influences in {}.'.format(skin_cluster))

    def _collect(nodes, joints_only):
        pairs = []
        for inf in nodes:
            if not cmds.objExists(inf):
                continue
            if joints_only and cmds.nodeType(inf) != 'joint':
                continue
            try:
                pos = cmds.xform(inf, q=True, ws=True, t=True)
                pairs.append((inf, pos[axis_index]))
            except Exception:
                continue
        return pairs

    candidates = _collect(influences, joints_only=True)
    if len(candidates) < 2:
        candidates = _collect(influences, joints_only=False)

    if len(candidates) < 2:
        raise RuntimeError(u'Could not determine top/bottom influences from {}'.format(skin_cluster))

    bottom_influence = min(candidates, key=lambda x: x[1])[0]
    top_influence = max(candidates, key=lambda x: x[1])[0]

    if bottom_influence == top_influence:
        raise RuntimeError(u'Failed to resolve distinct top/bottom influences in {}'.format(skin_cluster))

    return bottom_influence, top_influence


def get_vertices_by_world_band(mesh, axis='y', top_range=1.0, bottom_range=1.0):
    """
    ワールド座標の高さ帯で上端・下端・中間頂点を返す
    """
    axis_index = _get_axis_index(axis)
    vtx_list = _all_vertices(mesh)

    if not vtx_list:
        raise RuntimeError(u'No vertices found: {}'.format(mesh))

    values = []
    for vtx in vtx_list:
        pos = cmds.pointPosition(vtx, world=True)
        values.append((vtx, pos[axis_index]))

    min_val = min(v for _, v in values)
    max_val = max(v for _, v in values)

    bottom_limit = min_val + bottom_range
    top_limit = max_val - top_range

    if bottom_limit >= top_limit:
        raise RuntimeError(
            u'top_range + bottom_range is too large. '
            u'No middle band remains. '
            u'(min={:.6f}, max={:.6f}, bottom_limit={:.6f}, top_limit={:.6f})'.format(
                min_val, max_val, bottom_limit, top_limit
            )
        )

    bottom_vertices = [vtx for vtx, v in values if v <= bottom_limit]
    top_vertices = [vtx for vtx, v in values if v >= top_limit]
    middle_vertices = [vtx for vtx, v in values if bottom_limit < v < top_limit]

    return {
        'top': top_vertices,
        'bottom': bottom_vertices,
        'middle': middle_vertices,
        'min_val': min_val,
        'max_val': max_val,
        'bottom_limit': bottom_limit,
        'top_limit': top_limit,
    }


def set_two_influence_weights(skin_cluster, vertices, bottom_influence, top_influence,
                              bottom_weight, top_weight, normalize=True):
    """
    2インフルエンス分のウェイトを明示設定
    """
    if not vertices:
        return

    for vtx in vertices:
        cmds.skinPercent(
            skin_cluster,
            vtx,
            transformValue=[
                (bottom_influence, float(bottom_weight)),
                (top_influence, float(top_weight)),
            ],
            normalize=normalize
        )


def smooth_skincluster_weights(skin_cluster, smooth_weights=0.0, max_iterations=5,
                               obey_max_influences=2, normalize_after_change=True,
                               preserve_maintain_max_influences=True):
    """
    SIWeightEditor と同系統の skinCluster 平滑化を実行
    smooth_weights: weightChangeTolerance (sw)
    max_iterations: numIterations (swi)
    obey_max_influences: obeyMaxInfluences (omi)
    """
    mmi = None
    has_mmi = cmds.attributeQuery('maintainMaxInfluences', node=skin_cluster, exists=True)
    if preserve_maintain_max_influences and has_mmi:
        mmi = cmds.getAttr(skin_cluster + '.maintainMaxInfluences')

    try:
        cmds.skinCluster(
            skin_cluster,
            edit=True,
            sw=float(smooth_weights),
            swi=int(max_iterations),
            omi=int(obey_max_influences),
        )
        if normalize_after_change:
            cmds.skinCluster(skin_cluster, edit=True, fnw=True)
    finally:
        if preserve_maintain_max_influences and has_mmi and mmi is not None:
            cmds.setAttr(skin_cluster + '.maintainMaxInfluences', mmi)


def open_paint_skin_weights_tool():
    """
    任意: Paint Skin Weights Tool を開く
    UI確認用。バッチ本処理には不要。
    """
    try:
        mel.eval('ArtPaintSkinWeightsToolOptions;')
    except Exception:
        # Maya バージョン差の保険
        try:
            mel.eval('ArtPaintSkinWeightsTool;')
        except Exception:
            cmds.warning(u'Could not open Paint Skin Weights Tool.')


def auto_two_influence_band_smooth(
        mesh=None,
        bottom_influence=None,
        top_influence=None,
        skin_cluster=None,
        axis='y',
        bottom_range=1.0,
        top_range=1.0,
        smooth_weights=0.0,
        smooth_iterations=5,
        smooth_passes=1,
        reselect_middle=True,
        verbose=True):
    """
    2インフルエンス前提:
      1) ワールド座標で上端帯・下端帯を抽出
      2) 下端=bottom 100%, 上端=top 100% を設定
      3) skinCluster の標準 smooth を実行
      4) 最後に上下端を再固定

    Parameters
    ----------
    mesh : str or list[str]
        メッシュ transform または shape。None なら選択から自動取得
    bottom_influence : str
        下端側インフルエンス。None なら skinCluster から自動推定
    top_influence : str
        上端側インフルエンス。None なら skinCluster から自動推定
    skin_cluster : str or None
        指定しなければ mesh から自動取得
    axis : str
        'x' / 'y' / 'z'
    bottom_range : float
        最下点からこの距離以内を下端帯にする
    top_range : float
        最上点からこの距離以内を上端帯にする
    smooth_weights : float
        skinCluster -sw (weightChangeTolerance) 値
    smooth_iterations : int
        skinCluster -swi (numIterations) 値
    smooth_passes : int
        上記 smooth を何回回すか
    reselect_middle : bool
        終了時に middle 頂点を選択し直す
    verbose : bool
        ログ出力
    """
    if mesh is None:
        mesh_list = _get_selected_meshes()
    elif isinstance(mesh, (list, tuple)):
        mesh_list = list(mesh)
    else:
        mesh_list = [mesh]

    if len(mesh_list) > 1 and skin_cluster is not None:
        raise RuntimeError(
            u'When processing multiple meshes, skin_cluster must be None.'
        )

    all_middle_vertices = []
    results = []

    for target_mesh in mesh_list:
        target_skin_cluster = skin_cluster or _get_skin_cluster(target_mesh)

        target_bottom_influence = bottom_influence
        target_top_influence = top_influence
        if target_bottom_influence is None or target_top_influence is None:
            auto_bottom, auto_top = _pick_top_bottom_influences(target_skin_cluster, axis=axis)
            if target_bottom_influence is None:
                target_bottom_influence = auto_bottom
            if target_top_influence is None:
                target_top_influence = auto_top

        if not cmds.objExists(target_bottom_influence):
            raise RuntimeError(u'Bottom influence does not exist: {}'.format(target_bottom_influence))
        if not cmds.objExists(target_top_influence):
            raise RuntimeError(u'Top influence does not exist: {}'.format(target_top_influence))

        influences = cmds.skinCluster(target_skin_cluster, q=True, influence=True) or []
        if target_bottom_influence not in influences:
            raise RuntimeError(u'{} is not connected to {}'.format(target_bottom_influence, target_skin_cluster))
        if target_top_influence not in influences:
            raise RuntimeError(u'{} is not connected to {}'.format(target_top_influence, target_skin_cluster))

        band = get_vertices_by_world_band(
            mesh=target_mesh,
            axis=axis,
            top_range=top_range,
            bottom_range=bottom_range
        )

        top_vertices = band['top']
        bottom_vertices = band['bottom']
        middle_vertices = band['middle']

        if not top_vertices:
            raise RuntimeError(u'No top vertices found: {}'.format(target_mesh))
        if not bottom_vertices:
            raise RuntimeError(u'No bottom vertices found: {}'.format(target_mesh))
        if not middle_vertices:
            raise RuntimeError(u'No middle vertices found: {}'.format(target_mesh))

        # 1. 端部をベタ固定
        set_two_influence_weights(
            target_skin_cluster, bottom_vertices,
            target_bottom_influence, target_top_influence,
            bottom_weight=0.0, top_weight=1.0,
            normalize=True
        )
        set_two_influence_weights(
            target_skin_cluster, top_vertices,
            target_bottom_influence, target_top_influence,
            bottom_weight=1.0, top_weight=0.0,
            normalize=True
        )

        # 2. middle を選択しておく
        cmds.select(middle_vertices, r=True)

        # 3. Maya 標準 smooth 実行
        for _ in range(max(1, int(smooth_passes))):
            smooth_skincluster_weights(
                skin_cluster=target_skin_cluster,
                smooth_weights=smooth_weights,
                max_iterations=smooth_iterations
            )

        # 4. 端部を再固定
        set_two_influence_weights(
            target_skin_cluster, bottom_vertices,
            target_bottom_influence, target_top_influence,
            bottom_weight=0.0, top_weight=1.0,
            normalize=True
        )
        set_two_influence_weights(
            target_skin_cluster, top_vertices,
            target_bottom_influence, target_top_influence,
            bottom_weight=1.0, top_weight=0.0,
            normalize=True
        )

        all_middle_vertices.extend(middle_vertices)

        result = {
            'mesh': target_mesh,
            'skinCluster': target_skin_cluster,
            'bottomInfluence': target_bottom_influence,
            'topInfluence': target_top_influence,
            'topVertices': top_vertices,
            'bottomVertices': bottom_vertices,
            'middleVertices': middle_vertices,
            'minVal': band['min_val'],
            'maxVal': band['max_val'],
            'bottomLimit': band['bottom_limit'],
            'topLimit': band['top_limit'],
        }
        results.append(result)

        if verbose:
            print(u'=== auto_two_influence_band_smooth done ===')
            print(u'mesh           : {}'.format(target_mesh))
            print(u'skinCluster    : {}'.format(target_skin_cluster))
            print(u'bottom influence: {}'.format(target_bottom_influence))
            print(u'top influence   : {}'.format(target_top_influence))
            print(u'axis           : {}'.format(axis))
            print(u'min/max        : {:.6f} / {:.6f}'.format(result['minVal'], result['maxVal']))
            print(u'bottom/top lim : {:.6f} / {:.6f}'.format(result['bottomLimit'], result['topLimit']))
            print(u'bottom count   : {}'.format(len(bottom_vertices)))
            print(u'top count      : {}'.format(len(top_vertices)))
            print(u'middle count   : {}'.format(len(middle_vertices)))

    if reselect_middle and all_middle_vertices:
        cmds.select(all_middle_vertices, r=True)

    if len(results) == 1:
        return results[0]
    return results

if __name__ == '__main__':
    auto_two_influence_band_smooth(
        # mesh / skin_cluster / influence 未指定時は選択とskinClusterから自動推定
        axis='y',
        bottom_range=9.0,
        top_range=3.0,
        smooth_weights=0.0,
        smooth_iterations=5,
        smooth_passes=2
    )