"""ノードのローカルなアトリビュートの値(ポーズ)を保存・復元する。"""

import maya.api.OpenMaya as om2
import maya.cmds as cmds

from .nodeRef import NodeRef
from .snapshot import Snapshot, ValidationReport


class PoseSnapshot(Snapshot):
    """キー可能なアトリビュートと、チャンネルボックスに表示されるアトリビュートの値を保持する。

    値はスカラー(数値・bool・enumの番号)だけで、mlibの既定の単位(角度は度、距離はcm)で保存するため、
    保存時・適用時のUI単位に左右されない。ロック・接続中のアトリビュートも保存し、適用時に書けないものは
    飛ばして報告する。適用でキーは打たず、ワールド空間は扱わない。

    データの形::

        {"nodes": [{"node": {<NodeRef>}, "attrs": {"translateX": 1.0, "rotateY": 45.0, ...}}, ...]}

    Examples:
        >>> pose = PoseSnapshot.capture(mlib.ls(type="joint"))
        >>> pose.save("pose.json")
        >>> PoseSnapshot.load("pose.json").apply(namespaceMap={"chrA": "chrB"})
    """

    FORMAT = "mlib.pose"
    VERSION = 1

    @classmethod
    def capture(cls, nodes):
        """ノードのキー可能・チャンネルボックス表示のアトリビュートの現在値を取得する。

        ユーザー定義アトリビュートも含む。スカラー以外の値になるものは保存しない。
        同じノードを複数回指定した場合は最初の1回だけ記録する。

        Args:
            nodes (Iterable[Node | str]): 対象のノード。1つのNode・名前も受け付ける。

        Returns:
            PoseSnapshot: 取得した値を持つ新しいインスタンス。

        Raises:
            TypeError: nodesがノードまたはその並びでない場合。
            RuntimeError: ノードが存在しない場合。
        """
        entries = []
        seen = set()
        for node in _require_nodes(nodes):
            full = node.getFullName()
            if full in seen:
                continue
            seen.add(full)
            entries.append({"node": NodeRef.capture(node).toData(), "attrs": _capture_pose_attributes(node)})
        return cls({"nodes": entries})

    def apply(self, *, nameMap=None, replace=None, namespaceMap=None):
        """保存した値を、対応付けたノードのアトリビュートへ書き戻す。

        1回のUndoにまとめる。見つからないノードは ``missing``、ロック・入力接続(アニメカーブを含む)・
        対象に無いアトリビュートは ``skipped`` に記録して飛ばし、まとめて警告する。キーは打たない。

        Args:
            nameMap (dict[str, str] | None): 名前空間を除いた名前の対応表。
            replace (Iterable[tuple[str, str]] | None): 順に当てる文字列置換。
            namespaceMap (dict[str, str] | None): 名前空間の対応。

        Returns:
            ValidationReport: 適用の結果。
        """
        return self._run_apply({"nameMap": nameMap, "replace": replace, "namespaceMap": namespaceMap}, {})

    def _check_data(self, data):
        """``nodes`` の各項目がノード参照とスカラー値の辞書を持つか確かめる。

        Args:
            data (dict): 保持する前のデータ。

        Raises:
            ValueError: データの形が違う場合。
        """
        entries = data.get("nodes")
        if not isinstance(entries, list):
            raise ValueError("pose data must have a 'nodes' list")
        for entry in entries:
            if not isinstance(entry, dict) or not isinstance(entry.get("attrs"), dict):
                raise ValueError(f"Invalid pose entry: {entry!r}")
            NodeRef.fromData(entry.get("node"))
            for name, value in entry["attrs"].items():
                if not isinstance(name, str) or not name:
                    raise ValueError(f"Invalid attribute name in pose data: {name!r}")
                if not isinstance(value, (bool, int, float)):
                    raise ValueError(f"Pose values must be numbers or bools: {name!r}={value!r}")

    def _validate(self, mapping, report, options):
        """ノードの対応と、書けないアトリビュートを記録する。

        Args:
            mapping (NameMapping): 名前の対応付け。
            report (ValidationReport): 記録先。
            options (dict): 使わない。
        """
        self._plan(mapping, report)

    def _apply(self, mapping, report, options, fast):
        """書けるアトリビュートへ値を書き込む。

        飛ばすものは :meth:`_validate` で記録済みのため、ここでは書込みに失敗したものだけを記録する。

        Args:
            mapping (NameMapping): 名前の対応付け。
            report (ValidationReport): 記録先。
            options (dict): 使わない。
            fast (bool): 使わない(常にcmdsで書く)。
        """
        for plug, value in self._plan(mapping, ValidationReport()):
            _write_plug(plug, value, report)

    def _plan(self, mapping, report):
        """書き込む (Plug, 値) を集め、見つからないもの・書けないものをreportへ記録する。

        Args:
            mapping (NameMapping): 名前の対応付け。
            report (ValidationReport): 記録先。

        Returns:
            list[tuple[Plug, object]]: 書き込める組。
        """
        writes = []
        for entry in self._data["nodes"]:
            ref = NodeRef.fromData(entry["node"])
            node = ref.resolve(mapping)
            if node is None:
                report.addMissing(ref.mappedName(mapping))
                continue
            for name, value in entry["attrs"].items():
                plug = _find_plug(node, name)
                label = node.getName() + "." + name
                if plug is None:
                    report.addSkipped(label, "missing attribute")
                    continue
                reason = _block_reason(plug.mplug())
                if reason:
                    report.addSkipped(label, reason)
                    continue
                writes.append((plug, value))
        return writes


def _require_nodes(nodes):
    """ノードの指定をmlibのNodeのlistにする。

    Args:
        nodes (Iterable[Node | str] | Node | str): ノードの指定。

    Returns:
        list[Node]: 指定順のNode。

    Raises:
        TypeError: nodesがノードまたはその並びでない場合。
        RuntimeError: ノードが存在しない場合。
    """
    # 循環参照の回避: nodesはノードのメソッドからmlib.jsonを使う。
    from ..nodes.node import Node
    if isinstance(nodes, (str, Node)):
        nodes = [nodes]
    try:
        items = list(nodes)
    except TypeError:
        raise TypeError("nodes must be a node or an iterable of nodes") from None
    return [item if isinstance(item, Node) else Node(item) for item in items]


def _capture_pose_attributes(node):
    """キー可能・チャンネルボックス表示のアトリビュートのスカラー値を集める。

    Args:
        node (Node): 対象のノード。

    Returns:
        dict[str, bool | int | float]: ロング名のアトリビュートパスと値。listAttrの順。
    """
    name = node.getFullName()
    names = (cmds.listAttr(name, keyable=True) or []) + (cmds.listAttr(name, channelBox=True) or [])
    values = {}
    for attribute in names:
        plug = _find_plug(node, attribute)
        if plug is None or plug.mplug().isCompound or plug.mplug().isArray:
            continue
        path = _attribute_path(plug.mplug())
        if path in values:
            continue
        try:
            value = plug.get()
        except (RuntimeError, TypeError, ValueError):
            continue
        if isinstance(value, (bool, int, float)):
            values[path] = value
    return values


def _find_plug(node, attribute):
    """ノードのアトリビュートを探す。

    Args:
        node (Node): 対象のノード。
        attribute (str): アトリビュートのパス。

    Returns:
        Plug | None: 見つかったPlug。無ければNone。
    """
    try:
        return node.getPlug(attribute)
    except (AttributeError, RuntimeError, ValueError):
        return None


def _attribute_path(mplug):
    """ノード名を含めない、ロング名のアトリビュートパスを返す。

    Args:
        mplug (om2.MPlug): 対象のPlug。

    Returns:
        str: ``"translateX"``・``"weight[3]"`` 等。
    """
    return mplug.partialName(includeNodeName=False, includeNonMandatoryIndices=True,
                             includeInstancedIndices=True, useLongNames=True)


def _block_reason(mplug):
    """アトリビュートへ値を書けない理由を返す。

    自身・コンパウンドアトリビュートの親と子のロック、入力接続(アニメカーブを含む)を見る。

    Args:
        mplug (om2.MPlug): 対象のPlug。

    Returns:
        str | None: ``"locked"``・``"connected"``・``"not settable"``。書けるならNone。
    """
    related = [mplug]
    parent = mplug
    while parent.isChild:
        parent = parent.parent()
        related.append(parent)
    pending = [mplug]
    while pending:
        current = pending.pop()
        if current.isCompound:
            children = [current.child(index) for index in range(current.numChildren())]
            related.extend(children)
            pending.extend(children)
    if any(item.isLocked for item in related):
        return "locked"
    if any(item.isDestination for item in related):
        return "connected"
    if mplug.isFreeToChange() != om2.MPlug.kFreeToChange:
        return "not settable"
    return None


def _write_plug(plug, value, report):
    """値を書き込み、失敗したものをreportへ記録する。

    Args:
        plug (Plug): 書き込み先。
        value (object): mlibの既定の単位の値。
        report (ValidationReport): 記録先。
    """
    try:
        plug.set(value)
    except (RuntimeError, TypeError, ValueError) as error:
        report.addSkipped(plug.getName(), f"failed ({error})")
