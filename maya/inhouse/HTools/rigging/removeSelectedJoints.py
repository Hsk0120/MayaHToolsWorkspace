"""Menu-compatible entry point for selected joint removal."""

import maya.api.OpenMaya as om2
import maya.api.OpenMayaAnim as oma2
import maya.cmds as cmds

# skinCluster に接続したノードの名前・型名にこれらが含まれればスキニングレイヤーとみなす。
_LAYER_TOKENS = ("ngskin", "ngst", "ngskintools", "skinlayer", "skinninglayer", "layerdata")


def _dag_path(name):
    """ノード名から MDagPath を取得する。

    Args:
        name (str): DAG ノード名。

    Returns:
        om2.MDagPath: 名前が指すインスタンスのパス。
    """
    selection = om2.MSelectionList()
    selection.add(name)
    return selection.getDagPath(0)


def _uuid(node):
    """ノードの UUID を取得する。

    Args:
        node (om2.MObject): 対象ノード。

    Returns:
        str: UUID 文字列。
    """
    return om2.MFnDependencyNode(node).uuid().asString()


def _parent_path(path):
    """保持するインスタンスの直接の親パスを取得する。

    Args:
        path (om2.MDagPath): 子のパス。

    Returns:
        om2.MDagPath | None: 親のパス。ワールド直下なら None。
    """
    if path.length() <= 1:
        return None
    parent = om2.MDagPath(path)
    parent.pop()
    return parent


def _parent_joint_path(path):
    """直接の親が joint の場合だけ親パスを取得する。

    Args:
        path (om2.MDagPath): 子のパス。

    Returns:
        om2.MDagPath | None: 親 joint のパス。親が joint でなければ None。
    """
    parent = _parent_path(path)
    if parent is None or not parent.node().hasFn(om2.MFn.kJoint):
        return None
    return parent


def _joint_depth(path):
    """joint だけを数えた階層の深さを取得する。

    Args:
        path (om2.MDagPath): 対象 joint のパス。

    Returns:
        int: root joint を 0 とする深さ。joint 以外の親で数え終わる。
    """
    depth = 0
    current = _parent_joint_path(path)
    while current is not None:
        depth += 1
        current = _parent_joint_path(current)
    return depth


def _skin_name(skin):
    """skinCluster の現在のノード名を取得する。

    Args:
        skin (om2.MObject): skinCluster ノード。

    Returns:
        str: ノード名。
    """
    return om2.MFnDependencyNode(skin).name()


def _skin_clusters(path):
    """joint に接続する skinCluster を重複なしで取得する。

    Args:
        path (om2.MDagPath): 対象 joint のパス。

    Returns:
        list[om2.MObject]: 接続順の skinCluster。
    """
    result, seen = [], set()
    for name in cmds.listConnections(path.fullPathName(), type="skinCluster") or []:
        selection = om2.MSelectionList()
        selection.add(name)
        node = selection.getDependNode(0)
        key = _uuid(node)
        if key not in seen:
            seen.add(key)
            result.append(node)
    return result


def _influence_paths(skin):
    """skinCluster の influence のパスを登録順に取得する。

    Args:
        skin (om2.MObject): skinCluster ノード。

    Returns:
        om2.MDagPathArray: influence のパス。
    """
    return oma2.MFnSkinCluster(skin).influenceObjects()


def _has_influence(skin, path):
    """指定ノードが skinCluster の influence か UUID で判定する。

    Args:
        skin (om2.MObject): skinCluster ノード。
        path (om2.MDagPath): 判定するノードのパス。

    Returns:
        bool: influence に含まれる場合は True。
    """
    key = _uuid(path.node())
    return any(_uuid(influence.node()) == key for influence in _influence_paths(skin))


def _transfer_target(path, skin):
    """ウェイト移送先となる、同じ skinCluster の最も近い祖先 influence を探す。

    Args:
        path (om2.MDagPath): 移送元 joint のパス。
        skin (om2.MObject): influence を調べる skinCluster。

    Returns:
        om2.MDagPath | None: 移送先 joint のパス。見つからなければ None。
    """
    ancestor = _parent_joint_path(path)
    while ancestor is not None:
        if _has_influence(skin, ancestor):
            return ancestor
        ancestor = _parent_joint_path(ancestor)
    return None


def _raise_if_layers(skin):
    """スキニングレイヤーを検出したら安全のため処理を中断する。

    接続ノードの名前と型名だけで判定し、実際のレイヤーデータの有無は調べない。

    Args:
        skin (om2.MObject): 検査する skinCluster。

    Raises:
        RuntimeError: レイヤー関連ノードが接続されている場合。
    """
    for name in cmds.listConnections(_skin_name(skin), source=True, destination=True) or []:
        node_name = name.lower()
        node_type = cmds.nodeType(name).lower()
        if any(token in node_name or token in node_type for token in _LAYER_TOKENS):
            raise RuntimeError("Cannot run because skinning layers exist.")


def _raise_if_not_editable(skin, source, target):
    """移送で書き換える influence とウェイト配列が編集可能か確認する。

    書き込みは weightList への直接の setAttr なので、Maya の正規化やロックの
    考慮を経ない。ロックされた influence の値を黙って変えないよう事前に拒否する。

    Args:
        skin (om2.MObject): 対象の skinCluster。
        source (om2.MDagPath): 移送元 influence。
        target (om2.MDagPath): 移送先 influence。

    Raises:
        RuntimeError: influence のウェイトがロック、または weightList がロック・入力接続済みの場合。
    """
    for path in (source, target):
        name = path.fullPathName()
        if cmds.attributeQuery("lockInfluenceWeights", node=name, exists=True) \
                and cmds.getAttr(name + ".lockInfluenceWeights"):
            raise RuntimeError("Influence is locked: " + path.partialPathName())
    weight_list = om2.MFnDependencyNode(skin).findPlug("weightList", False)
    if weight_list.isLocked or cmds.listConnections(
            _skin_name(skin) + ".weightList", source=True, destination=False):
        raise RuntimeError("Weights are locked or connected")


def _transfer_weights(skin, source, target):
    """source influence のウェイトを target influence へ加算し、source を 0 にする。

    各頂点で ``target = 元のtarget + 元のsource``、``source = 0`` とし、他の influence の
    値は変えないので頂点ごとの合計は保たれる。skinPercent -transformMoveWeights は
    正規化の影響で移送先を置き換えてしまうため使わない。値の読み取りは OpenMaya で行い、
    書き込みは Undo に乗る setAttr で source を持つ頂点だけに行う。選択状態は変更しない。

    Args:
        skin (om2.MObject): 対象の skinCluster。
        source (om2.MDagPath): 移送元 influence。
        target (om2.MDagPath): 移送先 influence。

    Raises:
        RuntimeError: スキニングレイヤー、ロック・接続済みのウェイトを検出した場合。
        ValueError: どちらかが skinCluster の influence でない場合。
    """
    _raise_if_layers(skin)
    if not (source.isValid() and target.isValid()
            and _has_influence(skin, source) and _has_influence(skin, target)):
        raise ValueError("Both nodes must be influences of this skinCluster")
    if _uuid(source.node()) == _uuid(target.node()):
        return
    _raise_if_not_editable(skin, source, target)
    fn = oma2.MFnSkinCluster(skin)
    source_index = fn.indexForInfluenceObject(source)
    target_index = fn.indexForInfluenceObject(target)
    weight_list = fn.findPlug("weightList", False)
    # 書き込み前に全頂点の新しい値を計算する（論理番号で疎な配列を辿る）。
    edits = []
    for vertex in weight_list.getExistingArrayAttributeIndices():
        row = weight_list.elementByLogicalIndex(vertex).child(0)
        existing = set(row.getExistingArrayAttributeIndices())
        if source_index not in existing:
            continue
        source_value = row.elementByLogicalIndex(source_index).asDouble()
        if source_value == 0.0:
            continue
        target_value = (row.elementByLogicalIndex(target_index).asDouble()
                        if target_index in existing else 0.0)
        edits.append((vertex, target_value + source_value))
    skin_name = _skin_name(skin)
    template = skin_name + ".weightList[{}].weights[{}]"
    for vertex, value in edits:
        cmds.setAttr(template.format(vertex, target_index), value)
        cmds.setAttr(template.format(vertex, source_index), 0.0)


def _remove_influence(skin, path):
    """ウェイトを再配分せずに influence の登録を外す。joint 自体は残す。

    Args:
        skin (om2.MObject): 対象の skinCluster。
        path (om2.MDagPath): 登録を外す influence。

    Raises:
        RuntimeError: スキニングレイヤーを検出した場合。
        ValueError: 未登録、または最後の一つの influence の場合。
    """
    _raise_if_layers(skin)
    if not path.isValid() or not _has_influence(skin, path):
        raise ValueError("Joint is not an influence of this skinCluster")
    if len(_influence_paths(skin)) <= 1:
        raise ValueError("Cannot remove the last influence")
    cmds.skinCluster(_skin_name(skin), edit=True, removeInfluence=path.fullPathName())


def _child_transform_paths(path):
    """中間オブジェクトを除いた直接の子 Transform（joint を含む）を取得する。

    Args:
        path (om2.MDagPath): 親のパス。

    Returns:
        list[om2.MDagPath]: DAG の子順に並んだパス。Shape は含めない。
    """
    fn = om2.MFnDagNode(path)
    children = []
    for index in range(fn.childCount()):
        child = om2.MDagPath(path)
        child.push(fn.child(index))
        if child.node().hasFn(om2.MFn.kTransform) and not om2.MFnDagNode(child).isIntermediateObject:
            children.append(child)
    return children


def _delete_joints(names):
    """joint を深い順に処理し、ウェイトを祖先 influence へ移してから削除する。

    同じ joint の複数インスタンスパスはノード単位で一度だけ処理する。未スキニングの
    joint も削除する。子 Transform（joint を含む）は直接の親へ、親がなければワールドへ
    移す。同じ skinCluster の祖先 influence がある場合だけウェイトを移送し、移送先が
    なければ cmds.delete の標準処理に任せる。途中の失敗は例外で停止し、完了済みの
    変更は自動では戻さない（呼び出し側の Undo チャンクで戻せる）。

    Args:
        names (list[str]): 削除する joint の名前。

    Raises:
        RuntimeError: 無効な joint、移送対象のスキニングレイヤー、
            またはウェイト移送・再親付け・削除に失敗した場合。
    """
    paths = []
    for name in names:
        try:
            paths.append(_dag_path(name))
        except RuntimeError:
            raise RuntimeError("Cannot delete an invalid joint")
    # 深い joint から処理する。sorted は安定ソートなので同じ深さは入力順を保つ。
    paths.sort(key=_joint_depth, reverse=True)
    # 削除・ウェイト移送はノード全体の操作。同一 UUID の別パスを二度処理しない。
    targets, seen = [], set()
    for path in paths:
        if not path.isValid():
            raise RuntimeError("Cannot delete an invalid joint")
        key = _uuid(path.node())
        if key not in seen:
            seen.add(key)
            targets.append(path)
    # 祖先 influence へ加算できる組だけを、シーンを変更する前に計画する。
    plans = []
    for path in targets:
        if not path.node().hasFn(om2.MFn.kJoint):
            raise RuntimeError("Cannot delete an invalid joint")
        transfers = []
        for skin in _skin_clusters(path):
            target = _transfer_target(path, skin)
            if target is not None:
                _raise_if_layers(skin)
                _raise_if_not_editable(skin, path, target)
                transfers.append((skin, target))
        plans.append((path, transfers))
    for path, transfers in plans:
        name = path.fullPathName()
        stage = "transfer weights"
        try:
            for skin, target in transfers:
                _transfer_weights(skin, path, target)
                stage = "remove influence"
                _remove_influence(skin, path)
                stage = "transfer weights"
            stage = "reparent children"
            parent = _parent_path(path)
            for child in _child_transform_paths(path):
                if parent is None:
                    cmds.parent(child.fullPathName(), world=True)
                else:
                    cmds.parent(child.fullPathName(), parent.fullPathName())
            stage = "delete joint"
            cmds.delete(path.fullPathName())
        except Exception as exc:
            raise RuntimeError("Failed to {} for {}: {}".format(stage, name, exc)) from exc


def remove_selected_joint():
    """Move selected joint weights to parent influences and delete them."""
    # 全体を一回の Undo にまとめる。
    cmds.undoInfo(openChunk=True, chunkName="removeSelectedJoints")
    try:
        joints = cmds.ls(sl=True, type="joint", long=True) or []
        _delete_joints(joints)
    finally:
        cmds.undoInfo(closeChunk=True)


if __name__ == "__main__":
    remove_selected_joint()
