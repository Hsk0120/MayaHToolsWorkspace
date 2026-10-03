"""ノード・アトリビュート・コンポーネントの取得時点の選択を保持する。"""

import maya.api.OpenMaya as om2
import maya.cmds as cmds

from hlib.components import Component, Components, Vertex, Vertices, CV, CVs, Edge, Edges, Face, Faces, UV, UVs
from ..decorators.undo import undoChunk
from hlib.nodes.node import Node
from hlib.plugs.plug import Plug


class Selection:
    """取得時点の順序で対象を保持する。現在選択には自動追従しない。

    コンポーネントは単体に展開する。トポロジー変更後の番号の同一性、
    UVセット変更後のUVの同一性は保証しない。

    反復可能なため、``cmds.select(selection)`` のように maya.cmds へそのまま渡すと
    各要素(Node・Plug・Component)の一意な名前へ展開される。削除済みの要素を
    含むと maya.cmds の呼び出しが失敗するため、選択の復元には :meth:`restore` を使う。
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
        """
        from hlib.plugs.plug import Plug as _InputPlug
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
        resolved = []
        for item in items:
            if isinstance(item, Components):
                resolved.extend(item)
            elif isinstance(item, Selection):
                resolved.extend(item._items)
            elif isinstance(item, (Node, Plug, Component)):
                resolved.append(item)
            elif isinstance(item, str):
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
            unique.setdefault(item.fullName(), item)
        self._items = tuple(unique.values())

    @staticmethod
    def _resolve(selection, name=None):
        """MSelectionListをhlibの単体参照へ変換する。非対応要素はTypeError。

        name は要素を追加したときの文字列で、1要素の場合にインスタンス化された
        ノードのアトリビュートの所有インスタンスを求めるために使う(selection_owner 参照)。
        """
        from hlib.nodes.node import Node as _InputNode
        result = []
        for index in range(selection.length()):
            try:
                plug = selection.getPlug(index)
            except (RuntimeError, TypeError):
                plug = None
            if plug is not None and not plug.isNull:
                # インスタンス化されたノードのアトリビュートは、選択されたインスタンスのノードを所有ノードにする。
                hint = name if selection.length() == 1 else None
                mobject, path = _InputNode._selection_owner(selection, index, hint)
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

    @classmethod
    def capture(cls):
        """Selection: Mayaの現在選択を保持する。Channel Boxのアトリビュート選択は含めない。"""
        return cls(cls._resolve(om2.MGlobal.getActiveSelectionList()))

    @property
    def items(self):
        """list[Node | Plug | Component]: 保持順の対象。削除済み参照も保持する。
        fullName が重複する対象は構築時に除かれている(__init__ 参照)。"""
        return list(self._items)

    def nodes(self, type=None):
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

    def plugs(self):
        """list[Plug]: 有効なアトリビュート参照。Channel Box選択は自動取得しない。"""
        return [item for item in self._items if isinstance(item, Plug) and self._valid(item)]

    def components(self):
        """list[Components]: 有効な要素をshapeのDAGパス・種類ごとにまとめる。"""
        groups = {}
        classes = {Vertex: Vertices, Edge: Edges, Face: Faces, UV: UVs, CV: CVs}
        for item in self._items:
            if isinstance(item, Component) and self._valid(item):
                key = (item.shape.fullName(), item.__class__)
                groups.setdefault(key, (item.shape, []))[1].append(item.index)
        return [classes[kind](shape, indices) for (_, kind), (shape, indices) in groups.items()]

    def owners(self):
        """list[Node]: 有効な対象の所有ノード。DAGパス別に重複を除く。"""
        result = {}
        for item in self._items:
            if self._valid(item):
                node = (
                    item
                    if isinstance(item, Node)
                    else item.shape if isinstance(item, Component) else item.node
                )
                result.setdefault(node.fullName(), node)
        return list(result.values())

    def filter(self, type):
        """ノード型、またはコンポーネント記号で絞った新しい集合を返す。

        Args:
            type (str): joint等のノード型、vtx/e/f/map/cv、またはplug。

        Returns:
            Selection: 有効な該当要素。元の集合は変更しない。
        """
        result = []
        for item in self._items:
            if not self._valid(item):
                continue
            if isinstance(item, Node) and item.isType(type):
                result.append(item)
            elif isinstance(item, Component) and item.component_type == type:
                result.append(item)
            elif isinstance(item, Plug) and type == "plug":
                result.append(item)
        return Selection(result)

    def _valid(self, item):
        """削除されたノード・アトリビュート・範囲外要素を検出する。"""
        try:
            if isinstance(item, Node):
                return item.isValid()
            if isinstance(item, Plug) and not item.isValid():
                # 所有ノードの削除に加え、deleteAttr で削除された動的アトリビュートも無効として扱う。
                return False
            return bool(cmds.objExists(item.fullName()))
        except (RuntimeError, ValueError, IndexError):
            return False

    def _names(self, missing):
        """変更前に有効な名前を解決する。missing不正はValueError、欠落はRuntimeError。"""
        if missing not in ("skip", "error"):
            raise ValueError("missing must be 'skip' or 'error'")
        names = []
        for item in self._items:
            if self._valid(item):
                names.append(item.fullName())
            elif missing == "error":
                raise RuntimeError("Selection contains a missing item")
        return names

    @undoChunk("hlibSelectionSelect")
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

    def __len__(self):
        """int: 保持数。コンポーネントは単体で数え、削除済み参照も含む。
        fullName が重複する対象は構築時に除かれている(__init__ 参照)。"""
        return len(self._items)

    def __iter__(self):
        """Iterator: 保持順に参照を返す。"""
        return iter(self._items)

    def __getitem__(self, index):
        """単体参照、またはsliceに対応する参照のtupleを返す。"""
        return self._items[index]
