import maya.cmds as cmds


def get_skin_cluster(mesh_transform):
    """メッシュに接続されている skinCluster を返す"""
    history = cmds.listHistory(mesh_transform, pruneDagObjects=True) or []
    skins = cmds.ls(history, type='skinCluster') or []
    return skins[0] if skins else None


def get_assigned_materials(mesh_transform):
    """メッシュに割り当てられているマテリアル一覧を返す"""
    materials = []
    shapes = cmds.listRelatives(mesh_transform, shapes=True, noIntermediate=True, fullPath=True) or []
    for shape in shapes:
        shading_engines = cmds.listConnections(shape, type='shadingEngine') or []
        for sg in shading_engines:
            if sg == 'initialShadingGroup':
                continue
            mats = cmds.listConnections(sg + '.surfaceShader', source=True, destination=False) or []
            for mat in mats:
                if mat not in materials:
                    materials.append(mat)
    return materials


def get_or_create_shading_engine(material):
    """マテリアルに接続された shadingEngine を返す。無ければ作成する。"""
    if not cmds.objExists(material):
        return None

    mat_nodes = cmds.ls(material, long=True) or [material]
    mat_node = mat_nodes[0]

    target_sgs = cmds.listConnections(mat_node, source=False, destination=True, type='shadingEngine') or []
    if not target_sgs:
        target_sgs = cmds.listConnections(mat_node, source=True, destination=False, type='shadingEngine') or []

    if target_sgs:
        return target_sgs[0]

    mat_short = mat_node.split('|')[-1]
    sg_name = mat_short + 'SG'
    try:
        sg = cmds.sets(renderable=True, noSurfaceShader=True, empty=True, name=sg_name)
    except Exception:
        sg = cmds.sets(renderable=True, noSurfaceShader=True, empty=True)

    try:
        if cmds.attributeQuery('outColor', node=mat_node, exists=True):
            cmds.connectAttr(mat_node + '.outColor', sg + '.surfaceShader', force=True)
        elif cmds.attributeQuery('outValue', node=mat_node, exists=True):
            cmds.connectAttr(mat_node + '.outValue', sg + '.surfaceShader', force=True)
        else:
            cmds.warning(u'Info: {} に接続可能な出力属性が見つかりません。'.format(mat_short))
            return None
    except Exception:
        cmds.warning(u'Info: {} の shadingEngine 作成に失敗しました。'.format(mat_short))
        return None

    return sg


def get_mesh_shapes(mesh_transform):
    """メッシュ transform から表示用 shape 一覧を返す"""
    return cmds.listRelatives(mesh_transform, shapes=True, noIntermediate=True, fullPath=True) or []


def build_shape_mapping(src_mesh, dup_mesh):
    """複製元 shape と複製先 shape の対応表を返す"""
    src_shapes = get_mesh_shapes(src_mesh)
    dup_shapes = get_mesh_shapes(dup_mesh)

    if not src_shapes or not dup_shapes:
        return {}

    if len(src_shapes) != len(dup_shapes):
        cmds.warning(
            u'Info: shape 数が一致しません。 {} -> {} ({} -> {})'.format(
                src_mesh,
                dup_mesh,
                len(src_shapes),
                len(dup_shapes)
            )
        )

    shape_map = {}
    for src_shape, dup_shape in zip(src_shapes, dup_shapes):
        shape_map[src_shape] = dup_shape

    return shape_map


def member_belongs_to_source(member, src_shape, src_mesh):
    """set member が src_shape または src_mesh に属するか判定する"""
    src_shape_short = src_shape.split('|')[-1]
    src_mesh_short = src_mesh.split('|')[-1]

    candidates = (src_shape, src_shape_short, src_mesh, src_mesh_short)
    for base in candidates:
        if member == base or member.startswith(base + '.'):
            return True
    return False


def remap_member_to_duplicate(member, src_shape, dup_shape, src_mesh, dup_mesh):
    """src 側 member 文字列を dup 側 member 文字列へ変換する"""
    pairs = [
        (src_shape, dup_shape),
        (src_shape.split('|')[-1], dup_shape.split('|')[-1]),
        (src_mesh, dup_mesh),
        (src_mesh.split('|')[-1], dup_mesh.split('|')[-1]),
    ]

    for src_name, dup_name in pairs:
        if member == src_name:
            return dup_name
        if member.startswith(src_name + '.'):
            return dup_name + member[len(src_name):]

    return None


def assign_prefixed_shader_if_exists(src_mesh, dup_mesh, prefix='prv_'):
    """複製元のコンポーネント割り当てを維持したまま prefix 材質へ置換する"""
    shape_map = build_shape_mapping(src_mesh, dup_mesh)
    if not shape_map:
        return

    warned_missing = set()

    for src_shape, dup_shape in shape_map.items():
        shading_engines = cmds.listConnections(src_shape, type='shadingEngine') or []
        if not shading_engines:
            continue

        for sg in shading_engines:
            if sg == 'initialShadingGroup':
                continue

            mats = cmds.listConnections(sg + '.surfaceShader', source=True, destination=False) or []
            if not mats:
                continue

            src_mat = mats[0]
            src_short = src_mat.split('|')[-1]
            target_mat = src_short if src_short.startswith(prefix) else prefix + src_short

            if not cmds.objExists(target_mat):
                if target_mat not in warned_missing:
                    warned_missing.add(target_mat)
                    cmds.warning(u'Info: {} が存在しないため割り当てを維持します。'.format(target_mat))
                continue

            target_sg = get_or_create_shading_engine(target_mat)
            if not target_sg:
                cmds.warning(u'Info: {} の shadingEngine が見つかりません。'.format(target_mat))
                continue

            members = cmds.sets(sg, q=True) or []
            remapped_members = []
            for member in members:
                if not member_belongs_to_source(member, src_shape, src_mesh):
                    continue
                dup_member = remap_member_to_duplicate(member, src_shape, dup_shape, src_mesh, dup_mesh)
                if dup_member:
                    remapped_members.append(dup_member)

            if not remapped_members:
                continue

            for dup_member in sorted(set(remapped_members)):
                try:
                    cmds.sets(dup_member, e=True, forceElement=target_sg)
                except Exception:
                    cmds.warning(u'Info: マテリアル適用に失敗しました。 {} -> {}'.format(dup_member, target_sg))


def connect_visibility_attr(src_mesh, dup_mesh):
    """複製元の visibility を複製先へ接続する"""
    src_attr = src_mesh + '.visibility'
    dup_attr = dup_mesh + '.visibility'

    if not cmds.objExists(src_attr) or not cmds.objExists(dup_attr):
        return

    incoming = cmds.listConnections(dup_attr, source=True, destination=False, plugs=True) or []
    for src_plug in incoming:
        try:
            cmds.disconnectAttr(src_plug, dup_attr)
        except Exception:
            pass

    try:
        cmds.connectAttr(src_attr, dup_attr, force=True)
    except Exception:
        cmds.warning(u'Info: visibility の接続に失敗しました。 {} -> {}'.format(src_mesh, dup_mesh))


def get_selected_mesh_transforms():
    """現在選択からメッシュ transform 一覧を返す（重複除去済み）"""
    sels = cmds.ls(sl=True, long=True, objectsOnly=True) or []
    meshes = []
    seen = set()

    for sel in sels:
        if cmds.nodeType(sel) == 'mesh':
            parents = cmds.listRelatives(sel, parent=True, fullPath=True) or []
            if not parents:
                continue
            mesh = parents[0]
        else:
            mesh = sel

        shapes = cmds.listRelatives(mesh, shapes=True, noIntermediate=True, fullPath=True) or []
        if not shapes or cmds.nodeType(shapes[0]) != 'mesh':
            cmds.warning(u'Skip: {} はメッシュではありません。'.format(mesh))
            continue

        if mesh in seen:
            continue

        seen.add(mesh)
        meshes.append(mesh)

    return meshes


def duplicate_and_copy_skin_weights(prefix='prv_'):
    meshes = get_selected_mesh_transforms()
    if not meshes:
        cmds.error(u'スキニング済みメッシュを選択してください。')

    results = []

    for mesh in meshes:

        src_skin = get_skin_cluster(mesh)
        if not src_skin:
            cmds.warning(u'Skip: {} はスキニングされていません。'.format(mesh))
            continue

        # 元 skinCluster から influence を取得
        influences = cmds.skinCluster(src_skin, q=True, influence=True) or []
        if not influences:
            cmds.warning(u'Skip: {} の influence が取得できません。'.format(mesh))
            continue

        # duplicate
        short_name = mesh.split('|')[-1]
        dup_name = prefix + short_name
        dup = cmds.duplicate(mesh, rr=True, name=dup_name)[0]

        # Maya の自動リネームで末尾に 1 が付いたら可能な限り除去
        dup_short_name = dup.split('|')[-1]
        if dup_short_name.endswith('1') and len(dup_short_name) > 1:
            target_name = dup_short_name[:-1]
            try:
                dup = cmds.rename(dup, target_name)
            except Exception:
                cmds.warning(u'Info: {} の末尾 1 を除去できませんでした。'.format(dup_short_name))

        # 複製元の visibility を複製先へ接続
        connect_visibility_attr(mesh, dup)

        # prefix 付きシェーダーが存在する場合は複製側へ適用
        assign_prefixed_shader_if_exists(mesh, dup, prefix=prefix)

        # 念のため shape の履歴を見て skinCluster が付いていたら削除
        dup_skin_old = get_skin_cluster(dup)
        if dup_skin_old:
            try:
                cmds.delete(dup_skin_old)
            except Exception:
                pass

        # 元 skinCluster の主な設定を引き継ぎ
        max_influences = cmds.skinCluster(src_skin, q=True, maximumInfluences=True)
        maintain_max_influences = cmds.getAttr(src_skin + '.maintainMaxInfluences')
        normalize_weights = cmds.getAttr(src_skin + '.normalizeWeights')

        # 複製メッシュを同じ joint で bind
        dup_skin = cmds.skinCluster(
            influences,
            dup,
            toSelectedBones=True,
            maximumInfluences=max_influences,
            obeyMaxInfluences=maintain_max_influences,
            normalizeWeights=normalize_weights,
            name='skinCluster_' + dup_name
        )[0]

        # ノード属性も明示的に合わせておく
        cmds.setAttr(dup_skin + '.maxInfluences', max_influences)
        cmds.setAttr(dup_skin + '.maintainMaxInfluences', maintain_max_influences)

        # スキンウェイトをコピー
        cmds.copySkinWeights(
            sourceSkin=src_skin,
            destinationSkin=dup_skin,
            noMirror=True,
            surfaceAssociation='closestPoint',
            influenceAssociation=['name', 'closestJoint', 'oneToOne'],
            normalize=True
        )

        results.append(dup)

    if results:
        cmds.select(results, r=True)
        print(u'Created: {}'.format(results))
    else:
        cmds.warning(u'処理対象がありませんでした。')


# 実行
duplicate_and_copy_skin_weights()