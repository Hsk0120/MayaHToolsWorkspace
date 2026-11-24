"""選択メッシュを複製し、スキンウェイトと関連設定を引き継ぐツール。"""

import maya.cmds as cmds

import mlib
from mlib.decorator import undoChunk


def _connect_attr(src_attr, dst_attr):
    """接続先のロックを解除せずに src_attr から dst_attr へ強制接続する。

    ``cmds.connectAttr`` は同じ接続が既にある場合に警告だけで終わるため、
    接続済み・ロック済みを事前に判定して例外にし、呼び出し側の例外処理で扱えるようにする。

    Args:
        src_attr (mlib.Plug | str): 接続元アトリビュート。
        dst_attr (mlib.Plug | str): 接続先アトリビュート。

    Raises:
        RuntimeError: 接続先がロックされている、または既に同じ接続がある場合。
    """
    src_attr = mlib.getPlug(src_attr)
    dst_attr = mlib.getPlug(dst_attr)
    if dst_attr.isLocked():
        raise RuntimeError('Attribute is locked: {}'.format(dst_attr))
    if src_attr.isConnected(dst_attr, source=False):
        raise RuntimeError('Already connected: {} -> {}'.format(src_attr, dst_attr))
    dst_attr.connect(src_attr, force=True)


def _get_influence_names(skin_cluster):
    """skinCluster のインフルエンスを Maya のインフルエンス順に最短一意名で返す。

    名前が重複しても曖昧にならないよう、DAG パスの最短一意名で返す。

    Args:
        skin_cluster (mlib.SkinCluster): 対象の skinCluster。

    Returns:
        list[str]: インフルエンスの最短一意名。
    """
    return skin_cluster.getInfluences().getNames()


def get_skin_cluster(mesh_transform):
    """メッシュに接続されている skinCluster を返す

    Args:
        mesh_transform: 処理対象のメッシュまたはそのTransform。

    Returns:
        mlib.SkinCluster | None: 最初に見つかった skinCluster。
    """
    skins = mlib.getNode(mesh_transform).getHistory(type='skinCluster')
    return skins[0] if skins else None


def get_assigned_materials(mesh_transform):
    """メッシュに割り当てられているマテリアル一覧を返す

    Args:
        mesh_transform: 処理対象のメッシュまたはそのTransform。

    Returns:
        list[mlib.Node]: マテリアル。
    """
    materials = []
    for shape in get_mesh_shapes(mesh_transform):
        for sg in shape.getShadingEngines():
            if sg.getName() == 'initialShadingGroup':
                continue
            mat = sg.getShader()
            if mat is not None and mat not in materials:
                materials.append(mat)
    return materials


def get_or_create_shading_engine(material):
    """マテリアルに接続された shadingEngine を返す。無ければ作成する。

    Args:
        material: 割り当てるマテリアルのノード名。

    Returns:
        mlib.ShadingEngine | None: shadingEngine。
    """
    if not mlib.objExists(material):
        return None

    mat_node = mlib.getNode(material)

    target_sgs = mat_node.getConnections(source=False, destination=True, type='shadingEngine', asNode=True)
    if not target_sgs:
        target_sgs = mat_node.getConnections(source=True, destination=False, type='shadingEngine', asNode=True)

    if target_sgs:
        return target_sgs[0]

    mat_short = mat_node.getName(node=True)
    sg_name = mat_short + 'SG'
    try:
        sg = mlib.createShadingEngine(name=sg_name)
    except Exception:
        sg = mlib.createShadingEngine()

    try:
        if mat_node.hasAttr('outColor'):
            _connect_attr(mat_node.getPlug('outColor'), sg.getPlug('surfaceShader'))
        elif mat_node.hasAttr('outValue'):
            _connect_attr(mat_node.getPlug('outValue'), sg.getPlug('surfaceShader'))
        else:
            cmds.warning(u'Info: no connectable output attribute found on {}.'.format(mat_short))
            return None
    except Exception:
        cmds.warning(u'Info: failed to create a shadingEngine for {}.'.format(mat_short))
        return None

    return sg


def get_mesh_shapes(mesh_transform):
    """メッシュ transform から表示用 shape 一覧を返す

    Args:
        mesh_transform: 処理対象のメッシュまたはそのTransform。

    Returns:
        mlib.Nodes: 中間オブジェクトでない Shape。
    """
    return mlib.getNode(mesh_transform).getShape(all=True)


def build_shape_mapping(src_mesh, dup_mesh):
    """複製元 shape と複製先 shape の対応表を返す

    Args:
        src_mesh: 複製元または複製先のメッシュTransform。引数名のsrc/dupで区別する。
        dup_mesh: 複製元または複製先のメッシュTransform。引数名のsrc/dupで区別する。

    Returns:
        dict[str, str]: 複製元 shape の長い名前から複製先 shape の長い名前への対応。
    """
    src_shapes = get_mesh_shapes(src_mesh).getNames(full=True)
    dup_shapes = get_mesh_shapes(dup_mesh).getNames(full=True)

    if not src_shapes or not dup_shapes:
        return {}

    if len(src_shapes) != len(dup_shapes):
        cmds.warning(
            u'Info: the number of shapes does not match. {} -> {} ({} -> {})'.format(
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
    """set member が src_shape または src_mesh に属するか判定する

    Args:
        member: 所属または保存対象として扱うノード・コンポーネント。
        src_shape: 対応付ける複製元または複製先のShape名。
        src_mesh: 複製元または複製先のメッシュTransform。引数名のsrc/dupで区別する。
    """
    src_shape_short = src_shape.split('|')[-1]
    src_mesh_short = src_mesh.split('|')[-1]

    candidates = (src_shape, src_shape_short, src_mesh, src_mesh_short)
    for base in candidates:
        if member == base or member.startswith(base + '.'):
            return True
    return False


def remap_member_to_duplicate(member, src_shape, dup_shape, src_mesh, dup_mesh):
    """src 側 member 文字列を dup 側 member 文字列へ変換する

    Args:
        member: 所属または保存対象として扱うノード・コンポーネント。
        src_shape: 対応付ける複製元または複製先のShape名。
        dup_shape: 対応付ける複製元または複製先のShape名。
        src_mesh: 複製元または複製先のメッシュTransform。引数名のsrc/dupで区別する。
        dup_mesh: 複製元または複製先のメッシュTransform。引数名のsrc/dupで区別する。
    """
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
    """複製元のコンポーネント割り当てを維持したまま prefix 材質へ置換する

    Args:
        src_mesh: 複製元または複製先のメッシュTransform。引数名のsrc/dupで区別する。
        dup_mesh: 複製元または複製先のメッシュTransform。引数名のsrc/dupで区別する。
        prefix: 複製先で検索するマテリアル名の接頭辞。
    """
    shape_map = build_shape_mapping(src_mesh, dup_mesh)
    if not shape_map:
        return

    src_mesh = mlib.getNode(src_mesh).getName(full=True)
    dup_mesh = mlib.getNode(dup_mesh).getName(full=True)
    warned_missing = set()

    for src_shape, dup_shape in shape_map.items():
        for sg in mlib.getNode(src_shape).getShadingEngines():
            if sg.getName() == 'initialShadingGroup':
                continue

            src_mat = sg.getShader()
            if src_mat is None:
                continue

            src_short = src_mat.getName().split('|')[-1]
            target_mat = src_short if src_short.startswith(prefix) else prefix + src_short

            if not mlib.objExists(target_mat):
                if target_mat not in warned_missing:
                    warned_missing.add(target_mat)
                    cmds.warning(u'Info: {} does not exist, so the assignment is kept.'.format(target_mat))
                continue

            target_sg = get_or_create_shading_engine(target_mat)
            if not target_sg:
                cmds.warning(u'Info: shadingEngine for {} not found.'.format(target_mat))
                continue

            # 形状全体ならそのノード、フェースならフェース1つずつ。どちらも完全なパスで比べる。
            members = [member.getName(full=True) for member in sg.getMembers()]
            remapped_members = []
            for member in members:
                if not member_belongs_to_source(member, src_shape, src_mesh):
                    continue
                dup_member = remap_member_to_duplicate(member, src_shape, dup_shape, src_mesh, dup_mesh)
                if dup_member:
                    remapped_members.append(dup_member)

            if not remapped_members:
                continue

            remapped_members = sorted(set(remapped_members))
            try:
                target_sg.assign(remapped_members)
            except Exception:
                # まとめて割り当てられなければ、1つずつ割り当てて失敗したものを知らせる。
                for dup_member in remapped_members:
                    try:
                        target_sg.assign(dup_member)
                    except Exception:
                        cmds.warning(u'Info: failed to assign the material. {} -> {}'.format(dup_member, target_sg))


def connect_visibility_attr(src_mesh, dup_mesh):
    """複製元の visibility を複製先へ接続する

    Args:
        src_mesh: 複製元または複製先のメッシュTransform。引数名のsrc/dupで区別する。
        dup_mesh: 複製元または複製先のメッシュTransform。引数名のsrc/dupで区別する。
    """
    src_node = mlib.getNode(src_mesh)
    dup_node = mlib.getNode(dup_mesh)

    if not src_node.hasAttr('visibility') or not dup_node.hasAttr('visibility'):
        return

    src_attr = src_node.getPlug('visibility')
    dup_attr = dup_node.getPlug('visibility')

    if dup_attr.getConnections(input=True) is not None:
        try:
            dup_attr.disconnect()
        except Exception:
            pass

    try:
        _connect_attr(src_attr, dup_attr)
    except Exception:
        cmds.warning(u'Info: failed to connect visibility. {} -> {}'.format(src_mesh, dup_mesh))


def get_selected_mesh_transforms():
    """現在選択からメッシュ transform 一覧を返す（重複除去済み）

    Returns:
        list[mlib.Transform]: メッシュの Transform。
    """
    sels = mlib.ls(sl=True, long=True, objectsOnly=True)
    meshes = []

    for sel in sels:
        if sel.getType() == 'mesh':
            mesh = sel.getParent()
            if mesh is None:
                continue
        else:
            mesh = sel

        shapes = mesh.getShape(all=True) if isinstance(mesh, mlib.Transform) else []
        if not shapes or shapes[0].getType() != 'mesh':
            cmds.warning(u'Skip: {} is not a mesh.'.format(mesh.getName(full=True)))
            continue

        if mesh in meshes:
            continue

        meshes.append(mesh)

    return meshes


def duplicate_and_copy_skin_weights(prefix='prv_'):
    """選択メッシュを複製して同一インフルエンスで再バインドし、ウェイトをコピーします。

    全メッシュの処理を1回のUndoで戻せるように、Undoチャンクにまとめて実行する。

    Args:
        prefix (str): 複製メッシュ名・ターゲット材質探索に使う接頭辞。
    """
    meshes = get_selected_mesh_transforms()
    if not meshes:
        cmds.error(u'Select skinned meshes.')

    with undoChunk('duplicateAndCopySkinWeights'):
        _duplicate_and_copy_skin_weights(meshes, prefix)


def _duplicate_and_copy_skin_weights(meshes, prefix):
    """メッシュごとに複製・再バインド・ウェイトコピーを行う。

    Args:
        meshes (list[mlib.Transform]): 処理対象のメッシュTransform。
        prefix (str): 複製メッシュ名・ターゲット材質探索に使う接頭辞。
    """
    results = []

    for mesh in meshes:

        src_skin = get_skin_cluster(mesh)
        if not src_skin:
            cmds.warning(u'Skip: {} is not skinned.'.format(mesh.getName(full=True)))
            continue

        # 元 skinCluster から influence を取得
        influences = _get_influence_names(src_skin)
        if not influences:
            cmds.warning(u'Skip: could not get the influences of {}.'.format(mesh.getName(full=True)))
            continue

        # 複製名は接頭辞付きで生成する。
        # 既存命名規則に合わせるため短名ベースで組み立てる。
        short_name = mesh.getName(node=True)
        dup_name = prefix + short_name
        dup = mlib.duplicate(mesh, rr=True, name=dup_name)

        # Maya の自動リネームで末尾に 1 が付いたら可能な限り除去
        dup_short_name = dup.getName(node=True)
        if dup_short_name.endswith('1') and len(dup_short_name) > 1:
            target_name = dup_short_name[:-1]
            try:
                dup.rename(target_name)
            except Exception:
                cmds.warning(u'Info: could not remove the trailing 1 from {}.'.format(dup_short_name))

        # 複製元の visibility を複製先へ接続
        connect_visibility_attr(mesh, dup)

        # prefix 付きシェーダーが存在する場合は複製側へ適用
        assign_prefixed_shader_if_exists(mesh, dup, prefix=prefix)

        # 念のため shape の履歴を見て skinCluster が付いていたら削除
        dup_skin_old = get_skin_cluster(dup)
        if dup_skin_old:
            try:
                dup_skin_old.delete()
            except Exception:
                pass

        # 元 skinCluster の主要パラメータを複製側にも反映する。
        max_influences = src_skin.getMaxInfluences()
        maintain_max_influences = src_skin.getMaxInfluences(maintain=True)
        normalize_weights = src_skin.getPlug('normalizeWeights').get()

        # 複製メッシュを同じ joint で bind
        dup_skin = mlib.bindSkin(
            influences,
            dup,
            maximumInfluences=max_influences,
            toSelectedBones=True,
            obeyMaxInfluences=maintain_max_influences,
            normalizeWeights=normalize_weights,
            name='skinCluster_' + dup_name
        )

        # ノード属性も明示的に合わせておく
        dup_skin.setMaxInfluences(max_influences, maintain=maintain_max_influences)

        # コピー時は名前一致を優先し、補助として closestJoint/oneToOne を使う。
        src_skin.copyWeightsTo(
            dup_skin,
            surfaceAssociation='closestPoint',
            influenceAssociation=['name', 'closestJoint', 'oneToOne'],
            normalize=True
        )

        results.append(dup)

    if results:
        mlib.select(results, r=True)
        print(u'Created: {}'.format([dup.getName() for dup in results]))
    else:
        cmds.warning(u'Nothing to process.')


if __name__ == "__main__":
    # 実行
    duplicate_and_copy_skin_weights()
