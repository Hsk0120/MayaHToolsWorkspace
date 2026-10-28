"""skinClusterのウェイト移送とinfluence解除をOpenMayaで実行する。

influence解除のfast経路は、``cmds.skinCluster(edit=True, removeInfluence=...)`` の再配分を
Maya 2022/2027で実測した次の規則で再現する。

- 解除するinfluenceのウェイトの絶対値が ``1e-10`` 以下の頂点は変更しない。
- normalizeWeightsがInteractive(1)の場合、ロックしたinfluence(lockInfluenceWeights)の値は保ち、
  ロックしていない残りを ``1 - ロック合計`` (0未満は0)へ比例配分する。
- normalizeWeightsがNone(0)/Post(2)の場合、残りの合計が ``1e-10`` を超える頂点は値を変えない。
- 配分先の合計が ``1e-10`` 以下の頂点は、バインド時のinfluence形状からの距離で配り直す。
  距離は入力geometryの頂点(geomMatrix適用後)から、bindPreMatrixの逆が示すjoint位置までで、
  子jointを持つjointは子jointまでの線分(複数なら最短)を使う。登録中の子はbindPreMatrix、
  未登録の子はjoint自身のバインド時マトリクスと子のローカルマトリクスから位置を求める。
  ロックなしは ``距離 ** -dropoff`` (bindMethodがClosest distance(0)の場合だけ)、
  ロックありは ``1 / 距離`` で、近い順にmaxInfluences個へ配る(同距離は物理順が先)。
"""

import math

import maya.api.OpenMaya as om2

from ..util import _finite
from .fastWrite import _ancestor_plugs
from .nodeEdit import require_editable

#: Mayaの再配分で0とみなす値の上限(実測)。
_ZERO = 1e-10


def transfer_weights(skin, pairs):
    """skinPercentの移送とinteractive正規化を再現する。

    Args:
        skin (SkinCluster): 更新先。
        pairs (list[tuple[str, str]]): 検証済みのinfluence名ペア。

    Returns:
        None: 値を返さない。

    Raises:
        NotImplementedError: geometryが1個でない場合。
        RuntimeError: ウェイトがロック・接続されていて書き込めない場合。
    """
    if len(skin.mfn().getOutputGeometry()) != 1:
        raise NotImplementedError("fast weight transfer requires one geometry")
    names, values = skin._editable_weights()
    influences = skin.getInfluences()
    ids = [node.getUuid() for node in influences]
    width = len(names)
    # Nodeは循環import回避のため関数内で読み込む。
    from ..nodes.node import Node
    indices = [(ids.index(Node(source).getUuid()), ids.index(Node(target).getUuid()))
               for source, target in pairs]
    normalize = skin.getPlug("normalizeWeights").get() == 1
    for source, target in indices:
        for offset in range(0, len(values), width):
            if values[offset + source] <= 0:
                continue
            # MayaのtransformMoveWeightsは既存targetへ加算せず、
            # source値で置き換えてから正規化する。通常経路と同じ結果にする。
            values[offset + target] = values[offset + source]
            values[offset + source] = 0.0
            if normalize:
                total = sum(values[offset:offset + width])
                if total > 0:
                    values[offset:offset + width] = [v / total for v in values[offset:offset + width]]
    skin.setWeights(names, values, fast=True)


def remove_influence(skin, source):
    """残存ウェイトを通常経路と同じ規則で再配分し、influenceを登録解除する。

    Args:
        skin (SkinCluster): 対象skinCluster。単一meshに限定する。
        source (Joint): 登録解除するinfluence。

    Returns:
        None: 値を返さない。

    Raises:
        NotImplementedError: 再配分を再現できない条件の場合。シーンは変更しない。
        RuntimeError: ノード・ウェイト・構造プラグのロック等で編集できない場合。
    """
    require_editable(skin.mnode())
    _require_single_mesh(skin)
    _require_weight_plugs(skin)
    influences = skin.getInfluences()
    names = [node.getName() for node in influences]
    values = list(skin.getWeights(names))
    _require_finite_weights(values)
    index = _column(influences, source)
    logical = skin.mfn().indexForInfluenceObject(influences[index].mpath())
    state = _RemovalState(skin, influences, values)
    modified_vertices = state.remove(index)
    remove = _removal_structure(skin, source, logical)
    weight_list = skin.getPlug("weightList").mplug()
    for vertex in modified_vertices:
        row = weight_list.elementByLogicalIndex(vertex).child(0)
        if logical in row.getExistingArrayAttributeIndices():
            remove.append(row.elementByLogicalIndex(logical))
    _require_unlocked_removal(remove)
    # 再配分後の値。解除するinfluenceの列は0になっている。
    skin.setWeights(names, state.values(names), fast=True)
    # 切断・配列削除は一つのmodifierで実行する。ノード削除はこの中へ混在させない。
    modifier = om2.MDGModifier()
    for plug in remove:
        modifier.removeMultiInstance(plug, True)
    modifier.doIt()


def _removal_structure(skin, source, logical):
    """influenceとbindPoseの除去対象を、値を変更せず解決する。

    Args:
        skin (SkinCluster): 対象。
        source (Joint): 除去するinfluence。
        logical (int): influenceの論理番号。

    Returns:
        list[MPlug]: 除去する構造プラグ。
    """
    remove = []
    for attr in ("matrix", "lockWeights", "influenceColor"):
        array = skin.getPlug(attr).mplug()
        if logical in array.getExistingArrayAttributeIndices():
            remove.append(array.elementByLogicalIndex(logical))
    pose_source = skin.getPlug("bindPose").getSource(skipConversionNodes=False)
    if pose_source is not None:
        pose = pose_source.getNode()
        require_editable(pose.mnode())
        members = pose.getPlug("members").mplug()
        for member_index in members.getExistingArrayAttributeIndices():
            member = members.elementByLogicalIndex(member_index)
            origins = member.connectedTo(True, False)
            if not origins or origins[0].node() != source.mnode():
                continue
            for attr in ("members", "worldMatrix", "xformMatrix", "global", "parents"):
                array = pose.getPlug(attr).mplug()
                if member_index in array.getExistingArrayAttributeIndices():
                    remove.append(array.elementByLogicalIndex(member_index))
    return remove


def _require_unlocked_removal(remove):
    """親を含むロックを、全ての配列削除より前に確認する。

    Args:
        remove (list[MPlug]): 除去予定の配列要素。

    Returns:
        None: 値を返さない。

    Raises:
        RuntimeError: 要素自身、または親・配列がロックされている場合。
    """
    for plug in remove:
        for current in _ancestor_plugs(plug):
            if current.isLocked:
                raise RuntimeError(f"Attribute is locked: {plug.name()}")


def validate_removals(skin, steps, force=False):
    """同じskinClusterで続けて行う解除を、シーンを変えずに順に試算して確認する。

    Args:
        skin (SkinCluster): 対象。
        steps (list[tuple[Node, Node | str | None]]): 処理順の(解除するinfluence, 移送先)。
            単独の解除は ``[(source, target)]`` の1要素で渡す。
        force (bool): 解除前に不正ウェイトを除去するか。

    Returns:
        None: 値を返さない。

    Raises:
        NotImplementedError: geometryが1個のmeshでない、または再配分を再現できない場合。
        RuntimeError: ノード・ウェイト・構造プラグのロック等で編集できない場合。
    """
    require_editable(skin.mnode())
    _require_single_mesh(skin)
    _require_weight_plugs(skin)
    for source, _ in steps:
        logical = skin.mfn().indexForInfluenceObject(source.mpath())
        _require_unlocked_removal(_removal_structure(skin, source, logical))
    influences = skin.getInfluences()
    names = [node.getName() for node in influences]
    values = list(skin.getWeights(names))
    if force:
        # removeInvalidWeightsは不正要素を除去するため、既定値0として試算する。
        values = [v if math.isfinite(v) and v >= 0 else 0.0 for v in values]
    else:
        _require_finite_weights(values)
    state = _RemovalState(skin, influences, values)
    # 移送先の名前解決はNodeで行う。循環import回避のため関数内で読み込む。
    from ..nodes.node import Node
    for source, target in steps:
        index = _column(state.influences, source)
        if target is not None:
            state.transfer(index, _column(state.influences, Node(target)))
        state.remove(index)


def _require_single_mesh(skin):
    """fast解除が対象とする単一mesh構成かを確認する。

    Args:
        skin (SkinCluster): 対象。

    Returns:
        None: 値を返さない。

    Raises:
        NotImplementedError: geometryが1個でない場合。
        TypeError: geometryがmeshでない場合(``MFnMesh`` の構築が拒否する)。
    """
    if len(skin.mfn().getOutputGeometry()) != 1:
        raise NotImplementedError("fast removeInfluence requires one geometry")
    om2.MFnMesh(skin.mesh_path)


def _require_weight_plugs(skin):
    """レイヤーとweightListのロック・接続を確認する。

    通常経路のremoveInfluenceはlockInfluenceWeightsを拒否しないため、ここでも拒否しない。

    Args:
        skin (SkinCluster): 対象。

    Returns:
        None: 値を返さない。

    Raises:
        RuntimeError: weightListがロック・接続されている、または要素がロックされている場合。
        NotImplementedError: レイヤーを持つskinClusterの場合。
    """
    skin._raise_if_layers()
    weight_list = skin.getPlug("weightList").mplug()
    if weight_list.isLocked or weight_list.isDestination:
        raise RuntimeError("Weights are locked or connected")
    skin._validate_weight_locks(weight_list)


def _require_finite_weights(values):
    """再配分を再現できない負値・非有限値を拒否する。

    有限性の判定は :func:`mlib.util._finite` に合わせ、fastの未対応としてNotImplementedErrorにする。

    Args:
        values (list[float]): 全頂点・全influenceのウェイト。

    Returns:
        None: 値を返さない。

    Raises:
        NotImplementedError: 負値・無限大・NaNのウェイトがある場合。
    """
    try:
        finite = all(_finite(v, "weights") >= 0 for v in values)
    except (TypeError, ValueError):
        finite = False
    if not finite:
        raise NotImplementedError("fast removeInfluence requires finite non-negative weights")


def _column(influences, node):
    """influence一覧での物理順の列番号を返す。

    Args:
        influences (list[Node]): 現在の物理順のinfluence。
        node (Node): 探すinfluence。

    Returns:
        int: 列番号。
    """
    uuid = node.getUuid()
    return next(i for i, item in enumerate(influences) if item.getUuid() == uuid)


def _read_matrix(plug):
    """マトリクス型のプラグ値を取得する。

    Args:
        plug (MPlug): matrixアトリビュート。

    Returns:
        MMatrix: 値。
    """
    return om2.MFnMatrixData(plug.asMObject()).matrix()


def _translation_of(matrix):
    """マトリクスの移動成分を取得する。

    Args:
        matrix (MMatrix): 変換マトリクス。

    Returns:
        MVector: 移動成分。
    """
    return om2.MVector(matrix[12], matrix[13], matrix[14])


def _segment_distance(point, start, end):
    """点から線分までの距離を返す。

    Args:
        point (MVector): 点。
        start (MVector): 線分の始点。
        end (MVector): 線分の終点。

    Returns:
        float: 距離。
    """
    axis = end - start
    length = axis * axis
    if length <= 0:
        return (point - start).length()
    t = max(0.0, min(1.0, ((point - start) * axis) / length))
    return (point - (start + axis * t)).length()


class _RemovalState(object):
    """解除の試算・実行で、再配分後のウェイトとinfluence一覧を保持する。

    Args:
        skin (SkinCluster): 対象。
        influences (list[Node]): 物理順のinfluence。
        values (list[float]): 頂点ごとに物理順で並んだウェイト。
    """

    def __init__(self, skin, influences, values):
        """ウェイトを頂点ごとの行へ分け、正規化設定と形状キャッシュを初期化する。"""
        self.skin = skin
        self.influences = list(influences)
        width = len(influences)
        self.rows = [list(values[offset:offset + width]) for offset in range(0, len(values), width)]
        self.normalize = skin.getPlug("normalizeWeights").get()
        self._points = None
        self._shapes = {}

    def values(self, names):
        """現在の行を、指定した物理順の名前列に合わせて平坦化する。

        解除したinfluenceの列は0で埋める。

        Args:
            names (list[str]): 書き込み先の名前列。

        Returns:
            list[float]: 書き込む値。
        """
        current = {node.getName(): i for i, node in enumerate(self.influences)}
        flat = []
        for row in self.rows:
            flat.extend(row[current[name]] if name in current else 0.0 for name in names)
        return flat

    def transfer(self, source, target):
        """setWeightsでの祖先移送と同じく、sourceの値をtargetへ加算する。

        Args:
            source (int): 移送元の列番号。
            target (int): 移送先の列番号。

        Returns:
            None: 値を返さない。
        """
        for row in self.rows:
            row[target] += row[source]
            row[source] = 0.0

    def remove(self, index):
        """列を再配分して取り除き、変更した頂点番号を返す。

        Args:
            index (int): 解除するinfluenceの列番号。

        Returns:
            list[int]: 値を変更した頂点番号。
        """
        modified = []
        for vertex, row in enumerate(self.rows):
            if abs(row[index]) <= _ZERO:
                continue
            modified.append(vertex)
            row[index] = 0.0
            self._redistribute(vertex, row, index)
        # 列番号がずれるため、形状のキャッシュを破棄してから列を取り除く。
        self._shapes = {}
        self.influences.pop(index)
        for row in self.rows:
            row.pop(index)
        return modified

    def _redistribute(self, vertex, row, index):
        """1頂点の残りのウェイトを、通常経路の規則で配り直す。

        Args:
            vertex (int): 頂点番号。
            row (list[float]): 頂点のウェイト。直接更新する。
            index (int): 解除する列番号。

        Returns:
            None: 値を返さない。

        Raises:
            NotImplementedError: ロック無しの配分先が無い等、再配分を再現できない場合。
        """
        locked = [i for i, node in enumerate(self.influences) if i != index and self._locked(node)]
        free = [i for i in range(len(row)) if i != index and i not in locked]
        if self.normalize == 1:
            target = 1.0
            if locked:
                target = max(0.0, 1.0 - sum(row[i] for i in locked))
            total = sum(row[i] for i in free)
            if total > _ZERO:
                for i in free:
                    row[i] *= target / total
                return
            amount = target
        else:
            if sum(row[i] for i in range(len(row)) if i != index) > _ZERO:
                return
            amount = 1.0
        if not free or amount <= _ZERO:
            raise NotImplementedError(
                "fast removeInfluence cannot reproduce redistribution without unlocked influences")
        weights = self._distance_weights(vertex, index, free, bool(locked) and self.normalize == 1)
        for i in free:
            row[i] = amount * weights.get(i, 0.0)

    @staticmethod
    def _locked(node):
        """lockInfluenceWeightsが有効か返す。

        Args:
            node (Node): influence。

        Returns:
            bool: ロックされていればTrue。
        """
        return node.hasAttr("lockInfluenceWeights") and bool(node.getPlug("lockInfluenceWeights").get())

    def _distance_weights(self, vertex, index, columns, inverse):
        """バインド時のinfluence形状からの距離で配分比を求める。

        Args:
            vertex (int): 頂点番号。
            index (int): 解除する列番号。
            columns (list[int]): 配分先の列番号。
            inverse (bool): Trueは距離の逆数、Falseは距離のdropoff乗の逆数。

        Returns:
            dict[int, float]: 列番号と合計1の比率。
        """
        if not inverse and self.skin.getPlug("bindMethod").get() != 0:
            raise NotImplementedError(
                "fast removeInfluence reproduces zero-weight redistribution only for "
                "bindMethod closest distance")
        limit = self.skin.getPlug("maxInfluences").get()
        if limit < 1:
            raise NotImplementedError("fast removeInfluence requires maxInfluences of at least 1")
        point = self._vertex_points()[vertex]
        distances = []
        for column in columns:
            start, ends, dropoff = self._shape(column, index)
            if ends:
                distance = min(_segment_distance(point, start, end) for end in ends)
            else:
                distance = (point - start).length()
            if distance <= 0:
                raise NotImplementedError("fast removeInfluence cannot redistribute a vertex on an influence")
            distances.append((distance, column, dropoff))
        # 近い順、同距離は物理順。sortedは安定なので列番号順の入力をそのまま使う。
        chosen = sorted(distances, key=lambda item: item[0])[:limit]
        raw = {column: (1.0 / distance if inverse else distance ** -dropoff)
               for distance, column, dropoff in chosen}
        total = sum(raw.values())
        return {column: value / total for column, value in raw.items()}

    def _vertex_points(self):
        """skinClusterの入力geometryの頂点をgeomMatrix適用後の位置で返す。

        Returns:
            list[MVector]: 頂点位置。
        """
        if self._points is None:
            fn = self.skin.mfn()
            geometry = fn.indexForOutputShape(self.skin.mesh_path.node())
            plug = self.skin.getPlug("input").mplug().elementByLogicalIndex(geometry).child(0)
            matrix = _read_matrix(self.skin.getPlug("geomMatrix").mplug())
            self._points = [om2.MVector(p * matrix) for p in om2.MFnMesh(plug.asMObject()).getPoints()]
        return self._points

    def _bind_matrix(self, node):
        """登録中influenceのバインド時ワールドマトリクスを返す。

        Args:
            node (Node): influence。

        Returns:
            MMatrix: bindPreMatrixの逆。
        """
        logical = self.skin.mfn().indexForInfluenceObject(node.mpath())
        plug = self.skin.getPlug("bindPreMatrix").mplug().elementByLogicalIndex(logical)
        return _read_matrix(plug).inverse()

    def _shape(self, column, index):
        """距離計算に使うjoint位置・子joint位置・dropoffを返す。

        Args:
            column (int): 列番号。
            index (int): 解除中の列番号。解除中のinfluenceも子の位置にはbindPreMatrixを使う。

        Returns:
            tuple[MVector, list[MVector], float]: joint位置、子joint位置、dropoff。
        """
        if column in self._shapes:
            return self._shapes[column]
        node = self.influences[column]
        if not node.mnode().hasFn(om2.MFn.kJoint):
            raise NotImplementedError("fast removeInfluence redistributes only to joint influences")
        bind = self._bind_matrix(node)
        registered = {item.getUuid(): item for item in self.influences}
        ends = []
        dag = om2.MFnDagNode(node.mpath())
        for i in range(dag.childCount()):
            child = dag.child(i)
            if not child.hasFn(om2.MFn.kJoint):
                continue
            uuid = om2.MFnDependencyNode(child).uuid().asString()
            if uuid in registered:
                ends.append(_translation_of(self._bind_matrix(registered[uuid])))
            else:
                local = _read_matrix(om2.MFnDependencyNode(child).findPlug("matrix", False))
                ends.append(_translation_of(local * bind))
        logical = self.skin.mfn().indexForInfluenceObject(node.mpath())
        dropoff = self.skin.getPlug("dropoff").mplug().elementByLogicalIndex(logical).asDouble()
        self._shapes[column] = (_translation_of(bind), ends, dropoff)
        return self._shapes[column]
