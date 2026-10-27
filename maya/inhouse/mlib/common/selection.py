"""ノード・アトリビュート・コンポーネントの取得時点の選択を保持する。"""

import maya.api.OpenMaya as om2
import maya.cmds as cmds

from ..components.component import Component, Components
from ..components.cv import CV, CVs
from ..components.edge import Edge, Edges
from ..components.face import Face, Faces
from ..components.uv import UV, UVs
from ..components.vertex import Vertex, Vertices
from ..decorator import undoChunk
from ..nodes.node import Node
from ..plugs.plug import Plug


# まとめて解決するときに1つの選択リストへ続けて追加する名前の数。MSelectionList.add は追加のたびに
# 既存の要素との重複を照合するため、全件を1つのリストへ追加すると件数の2乗に比例して遅くなる。
_NAME_CHUNK = 16


class Selection:
    """取得時点の順序で単数参照を保持する。現在選択には自動追従しない。

    コンポーネントは単体へ展開し、同じ完全名は最初だけ残す。
    トポロジーやUVセット変更後の要素の同一性は保証しない。
    選択の復元には :meth:`select` を使い、無効参照はmissingで扱う。
    maya.cmdsへ直接渡す場合、複合・配列Plugは文字列化が必要。
    """

    def __init__(self, items=()):
        """明示した対象を保持する。省略時は空。

        Args:
            items (Iterable[Node | Plug | Component | Components | Selection | str |
                om2.MObject | om2.MDagPath | om2.MPlug | om2.MSelectionList]): 対象。
                文字列には範囲指定も使える。単一対象も指定可能。MObject・MDagPath は
                ノード、MPlug はアトリビュート、MSelectionList と Selection はその要素として扱う。
                fullName が重複する対象は最初の1件のみを保持する。

        Raises:
            TypeError: 非対応型、またはMesh/NurbsCurve以外のコンポーネントの場合。
            RuntimeError: 名前が解決できない場合。

        ノード名だけの文字列(「.」・ワイルドカードを含まないもの)は1つの選択リストへまとめて
        解決するが、対応付けは文字列の順に行うため、保持順と重複の除き方は名前ごとの解決と同じ。
        """
        from ..plugs.plug import Plug as _InputPlug
        singles = (
            str,
            Node,
            Plug,
            Component,
            Components,
            Selection,
            om2.MObject,
            om2.MDagPath,
            om2.MPlug,
            om2.MSelectionList,
        )
        if isinstance(items, singles):
            items = [items]
        else:
            items = list(items)
        # ノード名(「.」もワイルドカードも含まない文字列)は、名前ごとに選択リストを作らずまとめて解決する。
        # 対応付けられなかった名前とそれ以外の文字列は、従来どおり名前ごとの選択リストで解決する。
        bulk_names = [item for item in items if isinstance(item, str) and _is_plain_node_name(item)]
        bulk = iter(_resolve_names(bulk_names))
        resolved = []
        for item in items:
            if isinstance(item, Components):
                resolved.extend(item)
            elif isinstance(item, Selection):
                resolved.extend(item._items)
            elif isinstance(item, (Node, Plug, Component)):
                resolved.append(item)
            elif isinstance(item, str):
                found = next(bulk) if _is_plain_node_name(item) else None
                if found is not None:
                    resolved.append(Node._wrap_resolved(found[0], found[1]))
                    continue
                selection = om2.MSelectionList()
                selection.add(item)
                resolved.extend(self._resolve(selection, item))
            elif isinstance(item, om2.MSelectionList):
                resolved.extend(self._resolve(item))
            elif isinstance(item, om2.MPlug):
                resolved.append(_InputPlug._resolve_input(item))
            elif isinstance(item, (om2.MObject, om2.MDagPath)):
                resolved.append(Node(item))
            else:
                raise TypeError("Unsupported selection item")
        unique = {}
        for item in resolved:
            unique.setdefault(item.getFullName(), item)
        self._items = tuple(unique.values())

    def __len__(self):
        """保持している単体参照の数を返す。

        fullName が重複する対象は構築時に除かれている(__init__ 参照)。

        Returns:
            int: コンポーネントは単体で数え、削除済み参照も含む保持数。
        """
        return len(self._items)

    def __iter__(self):
        """保持順に参照を返す。

        Returns:
            Iterator: 保持順に参照を返す。
        """
        return iter(self._items)

    def __getitem__(self, index):
        """単体参照、またはsliceに対応する参照のtupleを返す。

        Args:
            index (int | slice): 保持順の番号または範囲。負の番号もPythonのtupleと同じ意味。

        Returns:
            Node | Plug | Component | tuple: 番号に対応する単体参照、またはsliceに対応するtuple。
        """
        return self._items[index]

    @classmethod
    def capture(cls):
        """Mayaの現在選択を保持する。Channel Boxのアトリビュート選択は含めない。

        Returns:
            Selection: Mayaの現在選択を保持する。Channel Boxのアトリビュート選択は含めない。
        """
        return cls(cls._resolve(om2.MGlobal.getActiveSelectionList()))

    @property
    def items(self):
        """list[Node | Plug | Component]: 保持順の対象。削除済み参照も保持する。
        fullName が重複する対象は構築時に除かれている(__init__ 参照)。"""
        return list(self._items)

    def getNodes(self, type=None):
        """ノードとして選ばれた対象を取得する。

        Args:
            type (str | None): 継承型を含むノード型。Noneは全型。

        Returns:
            list[Node]: 有効なノード。コンポーネントの所有者は含めない。
        """
        return [
            item
            for item in self._items
            if isinstance(item, Node) and item.isValid() and (type is None or item.isType(type))
        ]

    def getPlugs(self):
        """有効なアトリビュート参照。Channel Box選択は自動取得しない。

        Returns:
            list[Plug]: 有効なアトリビュート参照。Channel Box選択は自動取得しない。
        """
        return [item for item in self._items if isinstance(item, Plug) and self._valid(item)]

    def getComponents(self):
        """有効な要素をshapeのDAGパス・種類ごとにまとめる。

        Returns:
            list[Components]: 有効な要素をshapeのDAGパス・種類ごとにまとめる。
        """
        groups = {}
        classes = {Vertex: Vertices, Edge: Edges, Face: Faces, UV: UVs, CV: CVs}
        for item in self._items:
            if isinstance(item, Component) and self._valid(item):
                key = (item.shape.getFullName(), item.__class__)
                groups.setdefault(key, (item.shape, []))[1].append(item.index)
        return [classes[kind](shape, indices) for (_, kind), (shape, indices) in groups.items()]

    def getOwners(self):
        """有効な対象の所有ノード。DAGパス別に重複を除く。

        Returns:
            list[Node]: 有効な対象の所有ノード。DAGパス別に重複を除く。
        """
        result = {}
        for item in self._items:
            if self._valid(item):
                node = (
                    item
                    if isinstance(item, Node)
                    else item.shape if isinstance(item, Component) else item.getNode()
                )
                result.setdefault(node.getFullName(), node)
        return list(result.values())

    def filter(self, type):
        """ノード型、またはコンポーネント種類で絞った新しい集合を返す。

        Args:
            type (str): joint等のノード型、vertex/edge/face/uv/controlVertex、またはplug。
                コンポーネント記号vtx/e/f/map/cvも使用できる。

        Returns:
            Selection: 有効な該当要素。元の集合は変更しない。
        """
        component_type = {
            "vertex": "vtx", "edge": "e", "face": "f", "uv": "map", "controlVertex": "cv",
        }.get(type, type) if isinstance(type, str) else type
        result = []
        for item in self._items:
            if not self._valid(item):
                continue
            if isinstance(item, Node) and item.isType(type):
                result.append(item)
            elif isinstance(item, Component) and item.component_type == component_type:
                result.append(item)
            elif isinstance(item, Plug) and type == "plug":
                result.append(item)
        return Selection(result)

    @undoChunk("mlibSelectionSelect")
    def select(self, mode="replace", missing="skip"):
        """保持した対象を現在の選択に反映する。

        Args:
            mode (str): replaceは置換、addは追加、removeは除外。
            missing (str): skipは無効対象を除外、errorは変更前に例外。

        Returns:
            Selection: 自身。空集合はreplaceだけ選択を解除する。

        Raises:
            ValueError: modeまたはmissingが未対応の場合。
            RuntimeError: missingがerrorで対象が削除済みの場合。
        """
        if mode not in ("replace", "add", "remove"):
            raise ValueError("mode must be replace, add or remove")
        names = self._names(missing)
        if names:
            flag = {"replace": "replace", "add": "add", "remove": "deselect"}[mode]
            cmds.select(names, noExpand=True, **{flag: True})
        elif mode == "replace":
            cmds.select(clear=True)
        return self

    @staticmethod
    def _resolve(selection, name=None):
        """MSelectionListをmlibの単体参照へ変換する。非対応要素はTypeError。

        name は要素を追加したときの文字列で、1要素の場合にインスタンス化された
        ノードのアトリビュートの所有インスタンスを求めるために使う(selection_owner 参照)。

        Args:
            selection (om2.MSelectionList): 変換元の選択リスト。
            name (str | None): 単一要素を追加した際の入力名。所有するDAGインスタンスの解決に使う。

        Returns:
            list[Node | Plug | Component]: 選択要素の順序を維持した単数参照の列。
        """
        from ..nodes.node import Node as _InputNode
        result = []
        for index in range(selection.length()):
            try:
                plug = selection.getPlug(index)
            except (RuntimeError, TypeError):
                plug = None
            if plug is not None and not plug.isNull:
                # インスタンス化されたノードのアトリビュートは、選択されたインスタンスのノードを所有ノードにする。
                hint = name if selection.length() == 1 else None
                mobject, path = _InputNode._selection_owner(selection, index, hint, plug=True)
                result.append(Plug(Node(path if path is not None else mobject), plug))
                continue
            try:
                path, component = selection.getComponent(index)
            except (RuntimeError, TypeError):
                result.append(Node(selection.getDependNode(index)))
                continue
            if component.isNull():
                result.append(Node(path))
                continue
            result.extend(Component._from_api(path, component))
        return result

    def _valid(self, item):
        """削除されたノード・アトリビュート・範囲外要素を検出する。

        Args:
            item (Node | Plug | Component): 有効性を確認する保持参照。

        Returns:
            bool: 参照先が存在し、種類に応じた有効条件を満たすか。
        """
        try:
            if isinstance(item, Node):
                return item.isValid()
            if isinstance(item, Plug) and not item.isValid():
                # 所有ノードの削除に加え、deleteAttr で削除された動的アトリビュートも無効として扱う。
                return False
            return bool(cmds.objExists(item.getFullName()))
        except (RuntimeError, ValueError, IndexError):
            return False

    def _names(self, missing):
        """変更前に有効な名前を解決する。missing不正はValueError、欠落はRuntimeError。

        Args:
            missing (str): skipなら欠落を除外し、errorなら変更前に例外を送出する。

        Returns:
            list[str]: 有効な対象のフル名。missingがskipなら欠落した参照を除く。
        """
        if missing not in ("skip", "error"):
            raise ValueError("missing must be 'skip' or 'error'")
        names = []
        for item in self._items:
            if self._valid(item):
                names.append(item.getFullName())
            elif missing == "error":
                raise RuntimeError("Selection contains a missing item")
        return names


def _is_plain_node_name(name):
    """ワイルドカード・アトリビュート・コンポーネントを含まない、ノード名だけの文字列か判定する。

    Args:
        name (str): 判定する名前。

    Returns:
        bool: 「.」「*」「?」のいずれも含まない空でない文字列なら True。
    """
    return bool(name) and "." not in name and "*" not in name and "?" not in name


def _resolve_names(names, plugs=False):
    """名前の列を、名前ごとに選択リストを作らずに解決する(ls・Selection の内部補助)。

    ``_NAME_CHUNK`` 件ずつ同じ選択リストを使い回して追加し、追加で要素が丁度1つ増えた名前だけを
    その要素へ対応付ける。対応付けは選択リストの並びではなく names の順に行うため、戻り値の順は
    names と同じになる。次の名前は対応付けず None とし、呼出し元が従来の名前ごとの経路で解決する
    (結果と例外は名前ごとの解決と同じになる)。

    - 解決できない名前(存在しない・一意でない)。
    - 同じリストに既にある要素と重複・統合されて要素が増えない名前(重複は統合せず、名前ごとに返す)。
    - 複数の要素に一致する名前、ワイルドカード(「*」「?」)を含む名前。
    - plugs が True で、要素がアトリビュート(MPlug)にならない名前(コンポーネントなど)。

    Args:
        names (Sequence[str]): 解決する名前。ノード名とアトリビュート名は混ぜずに渡す。
        plugs (bool): True はアトリビュート名(「.」を含む名前)、False はノード名として対応付ける。

    Returns:
        list[tuple | None]: names と同じ長さの列。対応付けた名前は
            ``(MObject, MDagPath | None, MPlug | None)`` (DG ノードの DAG パスと、ノード名の MPlug は None)。
    """
    from ..nodes.node import Node as _InputNode
    result = [None] * len(names)
    selection = om2.MSelectionList()
    for start in range(0, len(names), _NAME_CHUNK):
        selection.clear()
        added = []
        for position in range(start, min(start + _NAME_CHUNK, len(names))):
            name = names[position]
            if "*" in name or "?" in name:
                continue
            before = selection.length()
            try:
                selection.add(name)
            except RuntimeError:
                continue
            if selection.length() == before + 1:
                added.append((position, before))
        for position, index in added:
            name = names[position]
            if plugs:
                try:
                    mplug = selection.getPlug(index)
                except (RuntimeError, TypeError):
                    continue
                if mplug.isNull:
                    continue
                mobject, dag_path = _InputNode._selection_owner(selection, index, name, plug=True)
                result[position] = (mobject, dag_path, mplug)
            else:
                mobject, dag_path = _InputNode._selection_owner(selection, index, name)
                result[position] = (mobject, dag_path, None)
    return result
