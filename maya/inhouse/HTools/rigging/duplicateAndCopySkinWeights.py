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


def assign_prefixed_shader_if_exists(src_mesh, dup_mesh, prefix='prv_'):
    """元メッシュのマテリアルに対応する prefix 付きマテリアルがあれば複製側へ割り当てる"""
    src_materials = get_assigned_materials(src_mesh)
    if not src_materials:
        return

    src_mat = src_materials[0]
    src_short = src_mat.split('|')[-1]
    target_mat = src_short if src_short.startswith(prefix) else prefix + src_short

    if not cmds.objExists(target_mat):
        return

    target_sgs = cmds.listConnections(target_mat, type='shadingEngine') or []
    if not target_sgs:
        cmds.warning(u'Info: {} の shadingEngine が見つかりません。'.format(target_mat))
        return

    cmds.sets(dup_mesh, e=True, forceElement=target_sgs[0])


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


def duplicate_and_copy_skin_weights(prefix='prv_'):
    sels = cmds.ls(sl=True, long=True) or []
    if not sels:
        cmds.error(u'スキニング済みメッシュを選択してください。')

    results = []

    for sel in sels:
        # shape選択でも transform に寄せる
        if cmds.nodeType(sel) == 'mesh':
            parents = cmds.listRelatives(sel, parent=True, fullPath=True) or []
            if not parents:
                continue
            mesh = parents[0]
        else:
            mesh = sel

        # mesh transform か確認
        shapes = cmds.listRelatives(mesh, shapes=True, noIntermediate=True, fullPath=True) or []
        if not shapes or cmds.nodeType(shapes[0]) != 'mesh':
            cmds.warning(u'Skip: {} はメッシュではありません。'.format(mesh))
            continue

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