"""選択(ノードとコンポーネント)を選択順のまま保存・復元する。"""

import maya.api.OpenMaya as om2
import maya.cmds as cmds

from .. import logger
from .componentRef import ComponentRef
from .nodeRef import NodeRef
from .snapshot import Snapshot, ValidationReport

#: 記録するコンポーネントのMFn型と、Mayaの表記。
_COMPONENT_TYPES = (
    (om2.MFn.kMeshVertComponent, "vtx"),
    (om2.MFn.kMeshEdgeComponent, "e"),
    (om2.MFn.kMeshPolygonComponent, "f"),
    (om2.MFn.kMeshMapComponent, "map"),
    (om2.MFn.kCurveCVComponent, "cv"),
)


class SelectionSnapshot(Snapshot):
    """選択したノードとコンポーネント(頂点・エッジ・フェース・UV・カーブのCV)を選択順に保持する。

    コンポーネントは同じシェイプ・同じ種類が続く範囲を1つの :class:`ComponentRef` にまとめる。
    NURBSサーフェスのCV等、番号が1つで表せないコンポーネントは保存しない。

    データの形::

        {"items": [{"node": {<NodeRef>}}, {"components": {<ComponentRef>}}, ...]}

    Examples:
        >>> snap = SelectionSnapshot.capture()
        >>> snap.save("selection.json")
        >>> SelectionSnapshot.load("selection.json").apply(namespaceMap={"chrA": "chrB"})
    """

    FORMAT = "mlib.selection"
    VERSION = 1

    @classmethod
    def capture(cls, items=None):
        """選択、または指定したノード・コンポーネントを取得する。

        Noneは現在の選択を選択順(``ls -orderedSelection``)で取得する。選択順の記録
        (``selectPref -trackSelectionOrder``)が無効で順序が取れない場合は ``ls -selection`` の順にする。

        Args:
            items (Iterable[Node | Component | Components | str] | None): 記録するノード・コンポーネント。
                文字列は ``"pCube1.vtx[0:3]"`` のようなコンポーネントの表記も受け付ける。Noneは現在の選択。

        Returns:
            SelectionSnapshot: 選択順の項目を持つ新しいインスタンス。

        Raises:
            TypeError: itemsの型が違う場合。
            RuntimeError: 指定したノード・コンポーネントが存在しない場合。
        """
        groups = []
        for item in _selection_items(items):
            for ref in _capture_item(item):
                _append_ref(groups, ref)
        return cls({"items": [_item_data(ref) for ref in groups]})

    def apply(self, *, nameMap=None, replace=None, namespaceMap=None):
        """保存した項目を、対応付けたシーンのノード・コンポーネントで選択し直す(現在の選択を置き換える)。

        見つからないノードは ``missing``、範囲外の番号を含むコンポーネントは ``skipped`` に記録して飛ばし、
        まとめて警告する。見つかるものが無ければ選択を解除する。

        Args:
            nameMap (dict[str, str] | None): 名前空間を除いた名前の対応表。
            replace (Iterable[tuple[str, str]] | None): 順に当てる文字列置換。
            namespaceMap (dict[str, str] | None): 名前空間の対応。

        Returns:
            ValidationReport: 適用の結果。
        """
        return self._run_apply({"nameMap": nameMap, "replace": replace, "namespaceMap": namespaceMap}, {})

    def _check_data(self, data):
        """``items`` の各項目がノードまたはコンポーネントの参照か確かめる。

        Args:
            data (dict): 保持する前のデータ。

        Raises:
            ValueError: データの形が違う場合。
        """
        entries = data.get("items")
        if not isinstance(entries, list):
            raise ValueError("selection data must have an 'items' list")
        for entry in entries:
            if not isinstance(entry, dict) or len(entry) != 1:
                raise ValueError(f"Invalid selection entry: {entry!r}")
            if "node" in entry:
                NodeRef.fromData(entry["node"])
            elif "components" in entry:
                ComponentRef.fromData(entry["components"])
            else:
                raise ValueError(f"Invalid selection entry: {entry!r}")

    def _validate(self, mapping, report, options):
        """ノード・コンポーネントの対応を記録する。

        Args:
            mapping (NameMapping): 名前の対応付け。
            report (ValidationReport): 記録先。
            options (dict): 使わない。
        """
        self._plan(mapping, report)

    def _apply(self, mapping, report, options, fast):
        """見つかった項目で選択を置き換える。

        Args:
            mapping (NameMapping): 名前の対応付け。
            report (ValidationReport): 記録先(飛ばすものは :meth:`_validate` で記録済み)。
            options (dict): 使わない。
            fast (bool): 使わない。
        """
        names = self._plan(mapping, ValidationReport())
        if names:
            cmds.select(names, replace=True)
        else:
            cmds.select(clear=True)

    def _plan(self, mapping, report):
        """選択する名前を集め、見つからないもの・範囲外のものをreportへ記録する。

        Args:
            mapping (NameMapping): 名前の対応付け。
            report (ValidationReport): 記録先。

        Returns:
            list[str]: cmds.selectへ渡す名前(選択順)。
        """
        names = []
        for entry in self._data["items"]:
            if "node" in entry:
                ref = NodeRef.fromData(entry["node"])
                node = ref.resolve(mapping)
                if node is None:
                    report.addMissing(ref.mappedName(mapping))
                else:
                    names.append(node.getFullName())
                continue
            ref = ComponentRef.fromData(entry["components"])
            if ref.node.resolve(mapping) is None:
                report.addMissing(ref.node.mappedName(mapping))
                continue
            components = ref.resolve(mapping)
            if components is None:
                report.addSkipped(ref.mappedName(mapping), "index out of range")
                continue
            names.extend(str(component) for component in components)
        return names


def _selection_items(items):
    """記録する項目の指定を、順序付きのlistにする。

    Args:
        items (Iterable | None): 指定。Noneは現在の選択。

    Returns:
        list: 指定順の項目。

    Raises:
        TypeError: itemsが並びでない場合。
    """
    if items is None:
        return cmds.ls(orderedSelection=True, long=True) or cmds.ls(selection=True, long=True) or []
    # 循環参照の回避: components・nodesはノードのメソッドからmlib.jsonを使う。
    from ..components import Component, Components
    from ..nodes.node import Node
    if isinstance(items, (str, Node, Component, Components)):
        return [items]
    try:
        return list(items)
    except TypeError:
        raise TypeError("items must be an iterable of nodes or components") from None


def _capture_item(item):
    """1つの項目を参照にする。

    Args:
        item (Node | Component | Components | str | om2.MDagPath | om2.MObject): 項目。

    Returns:
        list[NodeRef | ComponentRef]: 参照。保存しない種類のコンポーネントは空list。

    Raises:
        TypeError: 対応しない型の場合。
        RuntimeError: 存在しない場合。
    """
    # 循環参照の回避: components・nodesはノードのメソッドからmlib.jsonを使う。
    from ..components import Component, Components
    from ..nodes.node import Node
    if isinstance(item, (Component, Components)):
        return [ComponentRef.capture(item)]
    if isinstance(item, (Node, om2.MObject, om2.MDagPath)):
        return [NodeRef.capture(item)]
    if not isinstance(item, str):
        raise TypeError(f"Cannot record {type(item).__name__} in a selection")
    selection = om2.MSelectionList()
    try:
        selection.add(item)
    except RuntimeError:
        raise RuntimeError(f"Node not found: {item}") from None
    refs = []
    for index in range(selection.length()):
        refs.extend(_capture_selection_entry(selection, index, item))
    return refs


def _capture_selection_entry(selection, index, label):
    """MSelectionListの1項目を参照にする。

    Args:
        selection (om2.MSelectionList): 選択の一覧。
        index (int): 項目の番号。
        label (str): 警告に使う名前。

    Returns:
        list[NodeRef | ComponentRef]: 参照。保存しない種類のコンポーネントは空list。
    """
    try:
        dag_path, component = selection.getComponent(index)
    except (RuntimeError, TypeError):
        # DGノードはDAGパスを持たない。
        return [NodeRef.capture(selection.getDependNode(index))]
    if component.isNull():
        return [NodeRef.capture(dag_path)]
    kind = next((name for fn_type, name in _COMPONENT_TYPES if component.apiType() == fn_type), None)
    if kind is None:
        logger.warning("SelectionSnapshot: skipped unsupported component %s", label)
        return []
    shape = om2.MDagPath(dag_path)
    if not shape.node().hasFn(om2.MFn.kShape):
        shape.extendToShape()
    indices = om2.MFnSingleIndexedComponent(component).getElements()
    return [ComponentRef(NodeRef.capture(shape), kind, list(indices))]


def _append_ref(groups, ref):
    """参照を並びへ足す。直前と同じシェイプ・種類のコンポーネントは1つにまとめる。

    Args:
        groups (list[NodeRef | ComponentRef]): これまでの参照。変更する。
        ref (NodeRef | ComponentRef): 足す参照。
    """
    if isinstance(ref, ComponentRef) and groups and isinstance(groups[-1], ComponentRef):
        last = groups[-1]
        if last.node == ref.node and last.type == ref.type:
            indices = list(last.indices)
            indices.extend(index for index in ref.indices if index not in last.indices)
            groups[-1] = ComponentRef(last.node, last.type, indices)
            return
    groups.append(ref)


def _item_data(ref):
    """参照を、選択のデータの1項目にする。

    Args:
        ref (NodeRef | ComponentRef): 参照。

    Returns:
        dict: ``{"node": ...}`` または ``{"components": ...}``。
    """
    if isinstance(ref, ComponentRef):
        return {"components": ref.toData()}
    return {"node": ref.toData()}
