"""Menu-compatible entry point for selected joint removal."""

import mlib
from mlib.decorator import undoChunk

# skinCluster に接続したノードの名前・型名にこれらが含まれればスキニングレイヤーとみなす。
_LAYER_TOKENS = ("ngskin", "ngst", "ngskintools", "skinlayer", "skinninglayer", "layerdata")


def _parent_joint(node):
    """直接の親が joint の場合だけ親を取得する。

    Args:
        node (mlib.DagNode): 子。保持するインスタンスのパスで親をたどる。

    Returns:
        mlib.Joint | None: 親 joint。親が joint でなければ None。
    """
    parent = node.getParent()
    if parent is None or not parent.isType("joint"):
        return None
    return parent


def _joint_depth(joint):
    """joint だけを数えた階層の深さを取得する。

    Args:
        joint (mlib.Joint): 対象 joint。

    Returns:
        int: root joint を 0 とする深さ。joint 以外の親で数え終わる。
    """
    depth = 0
    current = _parent_joint(joint)
    while current is not None:
        depth += 1
        current = _parent_joint(current)
    return depth


def _has_influence(skin, node):
    """指定ノードが skinCluster の influence か UUID で判定する。

    Args:
        skin (mlib.SkinCluster): skinCluster ノード。
        node (mlib.DagNode): 判定するノード。

    Returns:
        bool: influence に含まれる場合は True。
    """
    key = node.getUuid()
    return any(influence.getUuid() == key for influence in skin.getInfluences())


def _transfer_target(joint, skin):
    """ウェイト移送先となる、同じ skinCluster の最も近い祖先 influence を探す。

    Args:
        joint (mlib.Joint): 移送元 joint。
        skin (mlib.SkinCluster): influence を調べる skinCluster。

    Returns:
        mlib.Joint | None: 移送先 joint。見つからなければ None。
    """
    ancestor = _parent_joint(joint)
    while ancestor is not None:
        if _has_influence(skin, ancestor):
            return ancestor
        ancestor = _parent_joint(ancestor)
    return None


def _raise_if_layers(skin):
    """スキニングレイヤーを検出したら安全のため処理を中断する。

    接続ノードの名前と型名だけで判定し、実際のレイヤーデータの有無は調べない。

    Args:
        skin (mlib.SkinCluster): 検査する skinCluster。

    Raises:
        RuntimeError: レイヤー関連ノードが接続されている場合。
    """
    for node in skin.getConnections(asNode=True):
        node_name = node.getName().lower()
        node_type = node.getType().lower()
        if any(token in node_name or token in node_type for token in _LAYER_TOKENS):
            raise RuntimeError("Cannot run because skinning layers exist.")


def _raise_if_not_editable(skin, source, target):
    """移送で書き換える influence とウェイト配列が編集可能か確認する。

    書き込みは weightList への直接の setAttr なので、Maya の正規化やロックの
    考慮を経ない。ロックされた influence の値を黙って変えないよう事前に拒否する。

    Args:
        skin (mlib.SkinCluster): 対象の skinCluster。
        source (mlib.Joint): 移送元 influence。
        target (mlib.Joint): 移送先 influence。

    Raises:
        RuntimeError: influence のウェイトがロック、または weightList がロック・入力接続済みの場合。
    """
    for node in (source, target):
        if node.isInfluenceLocked():
            raise RuntimeError("Influence is locked: " + node.getName())
    weight_list = skin.getPlug("weightList")
    if weight_list.isLocked() or weight_list.getConnections(source=True, destination=False):
        raise RuntimeError("Weights are locked or connected")


def _transfer_weights(skin, source, target):
    """source influence のウェイトを target influence へ加算し、source を 0 にする。

    各頂点で ``target = 元のtarget + 元のsource``、``source = 0`` とし、他の influence の
    値は変えないので頂点ごとの合計は保たれる。skinPercent -transformMoveWeights は
    正規化の影響で移送先を置き換えてしまうため使わない。値は weightList の Plug で
    読み書きし、書き込みは Undo に乗る通常の経路で source を持つ頂点だけに行う。選択状態は変更しない。

    Args:
        skin (mlib.SkinCluster): 対象の skinCluster。
        source (mlib.Joint): 移送元 influence。
        target (mlib.Joint): 移送先 influence。

    Raises:
        RuntimeError: スキニングレイヤー、ロック・接続済みのウェイトを検出した場合。
        ValueError: どちらかが skinCluster の influence でない場合。
    """
    _raise_if_layers(skin)
    if not (source.isValid() and target.isValid()
            and _has_influence(skin, source) and _has_influence(skin, target)):
        raise ValueError("Both nodes must be influences of this skinCluster")
    if source.getUuid() == target.getUuid():
        return
    _raise_if_not_editable(skin, source, target)
    source_index = skin.getInfluenceIndex(source)
    target_index = skin.getInfluenceIndex(target)
    weight_list = skin.getPlug("weightList")
    # 書き込み前に全頂点の新しい値を計算する（論理番号で疎なマルチアトリビュートを辿る）。
    edits = []
    for vertex in weight_list.getIndices():
        row = weight_list[vertex]["weights"]
        existing = set(row.getIndices())
        if source_index not in existing:
            continue
        source_value = row[source_index].get()
        if source_value == 0.0:
            continue
        target_value = row[target_index].get() if target_index in existing else 0.0
        edits.append((row, target_value + source_value))
    for row, value in edits:
        row[target_index].set(value)
        row[source_index].set(0.0)


def _remove_influence(skin, joint):
    """ウェイトを再配分せずに influence の登録を外す。joint 自体は残す。

    Args:
        skin (mlib.SkinCluster): 対象の skinCluster。
        joint (mlib.Joint): 登録を外す influence。

    Raises:
        RuntimeError: スキニングレイヤーを検出した場合。
        ValueError: 未登録、または最後の一つの influence の場合。
    """
    _raise_if_layers(skin)
    if not joint.isValid() or not _has_influence(skin, joint):
        raise ValueError("Joint is not an influence of this skinCluster")
    if len(skin.getInfluences()) <= 1:
        raise ValueError("Cannot remove the last influence")
    # ウェイトは移送済み(source は 0)なので、祖先へは移さずに登録だけを外す。
    skin.removeInfluences(joint, transferToParent=False)


def _delete_joints(joints):
    """joint を深い順に処理し、ウェイトを祖先 influence へ移してから削除する。

    同じ joint の複数インスタンスパスはノード単位で一度だけ処理する。未スキニングの
    joint も削除する。子 Transform（joint を含む）は直接の親へ、親がなければワールドへ
    移す。同じ skinCluster の祖先 influence がある場合だけウェイトを移送し、移送先が
    なければ Maya の標準の削除処理に任せる。途中の失敗は例外で停止し、完了済みの
    変更は自動では戻さない（呼び出し側の Undo チャンクで戻せる）。

    Args:
        joints (Iterable[mlib.Joint]): 削除する joint。

    Raises:
        RuntimeError: 無効な joint、移送対象のスキニングレイヤー、
            またはウェイト移送・再親付け・削除に失敗した場合。
    """
    joints = list(joints)
    # 深い joint から処理する。sorted は安定ソートなので同じ深さは入力順を保つ。
    joints.sort(key=_joint_depth, reverse=True)
    # 削除・ウェイト移送はノード全体の操作。同一 UUID の別パスを二度処理しない。
    targets, seen = [], set()
    for joint in joints:
        if not joint.isValid():
            raise RuntimeError("Cannot delete an invalid joint")
        key = joint.getUuid()
        if key not in seen:
            seen.add(key)
            targets.append(joint)
    # 祖先 influence へ加算できる組だけを、シーンを変更する前に計画する。
    plans = []
    for joint in targets:
        if not joint.isType("joint"):
            raise RuntimeError("Cannot delete an invalid joint")
        transfers = []
        for skin in joint.getSkinClusters(influence=True):
            target = _transfer_target(joint, skin)
            if target is not None:
                _raise_if_layers(skin)
                _raise_if_not_editable(skin, joint, target)
                transfers.append((skin, target))
        plans.append((joint, transfers))
    for joint, transfers in plans:
        name = joint.getName(full=True)
        stage = "transfer weights"
        try:
            for skin, target in transfers:
                _transfer_weights(skin, joint, target)
                stage = "remove influence"
                _remove_influence(skin, joint)
                stage = "transfer weights"
            stage = "reparent children"
            parent = joint.getParent()
            # 中間オブジェクトを除いた直接の子 Transform（joint を含む）。Shape は含めない。
            for child in joint.getChildren():
                child.setParent(parent)
            stage = "delete joint"
            joint.delete(removeInfluence=False)
        except Exception as exc:
            raise RuntimeError("Failed to {} for {}: {}".format(stage, name, exc)) from exc


def remove_selected_joint():
    """Move selected joint weights to parent influences and delete them."""
    # 全体を一回の Undo にまとめる。
    with undoChunk("removeSelectedJoints"):
        joints = mlib.ls(sl=True, type="joint", long=True)
        _delete_joints(joints)


if __name__ == "__main__":
    remove_selected_joint()
