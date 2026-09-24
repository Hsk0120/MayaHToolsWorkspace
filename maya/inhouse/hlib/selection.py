"""ノード・属性・コンポーネントの取得時点の選択を保持する。"""

import maya.api.OpenMaya as om2
import maya.cmds as cmds

from .components import Component, Components, Vertex, Vertices, CV, CVs, Edge, Edges, Face, Faces, UV, UVs
from .decorators.undo import undo_chunk
from .nodes.node import Node
from .plugs.plug import Plug


class Selection:
    """取得時点の順序で対象を保持する。現在選択には自動追従しない。

    コンポーネントは単体に展開する。トポロジー変更後の番号の同一性、
    UVセット変更後のUVの同一性は保証しない。
    """

    def __init__(self, items=()):
        """明示した対象を保持する。省略時は空。

        Args:
            items (Iterable[Node | Plug | Component | Components | str]): 対象。
                文字列には範囲指定も使える。単一対象も指定可能。

        Raises:
            TypeError: 非対応型、またはMesh/NurbsCurve以外のコンポーネントの場合。
            RuntimeError: 名前が解決できない場合。
        """
        if isinstance(items, (str, Node, Plug, Component, Components)):
            items = [items]
        resolved = []
        for item in items:
            if isinstance(item, Components):
                resolved.extend(item)
            elif isinstance(item, (Node, Plug, Component)):
                resolved.append(item)
            elif isinstance(item, str):
                selection = om2.MSelectionList()
                selection.add(item)
                resolved.extend(self._resolve(selection))
            else:
                raise TypeError("Unsupported selection item")
        unique = {}
        for item in resolved:
            unique.setdefault(item.full_name, item)
        self._items = tuple(unique.values())
        self._attributes = {id(item): om2.MObjectHandle(item.mplug().attribute())
                            for item in self._items if isinstance(item, Plug)}

    @staticmethod
    def _resolve(selection):
        """MSelectionListをhlibの単体参照へ変換する。非対応要素はTypeError。"""
        types = {om2.MFn.kMeshVertComponent: Vertex, om2.MFn.kMeshEdgeComponent: Edge,
                 om2.MFn.kMeshPolygonComponent: Face, om2.MFn.kMeshMapComponent: UV,
                 om2.MFn.kCurveCVComponent: CV}
        result = []
        for index in range(selection.length()):
            try:
                plug = selection.getPlug(index)
            except (RuntimeError, TypeError):
                plug = None
            if plug is not None and not plug.isNull:
                result.append(Plug(Node(plug.node()), plug))
                continue
            try:
                path, component = selection.getComponent(index)
            except (RuntimeError, TypeError):
                result.append(Node(selection.getDependNode(index)))
                continue
            if component.isNull():
                result.append(Node(path))
                continue
            cls = types.get(component.apiType())
            if cls is None:
                raise TypeError("Only mesh vertices/edges/faces/UVs and curve CVs are supported")
            shape = Node(path)
            fn = om2.MFnSingleIndexedComponent(component)
            indices = range(getattr(shape, cls.count_attribute)) if fn.isComplete else fn.getElements()
            result.extend(cls(shape, i) for i in indices)
        return result

    @classmethod
    def capture(cls):
        """Selection: Mayaの現在選択を保持する。Channel Boxの属性選択は含めない。"""
        return cls(cls._resolve(om2.MGlobal.getActiveSelectionList()))

    def items(self):
        """list[Node | Plug | Component]: 保持順の対象。削除済み参照も保持する。"""
        return list(self._items)

    def nodes(self, type=None):
        """ノードとして選ばれた対象を取得する。

        Args:
            type (str | None): 継承型を含むノード型。Noneは全型。

        Returns:
            list[Node]: 有効なノード。コンポーネントの所有者は含めない。
        """
        return [item for item in self._items if isinstance(item, Node) and item.is_valid()
                and (type is None or item.is_type(type))]

    def plugs(self):
        """list[Plug]: 有効な属性参照。Channel Box選択は自動取得しない。"""
        return [item for item in self._items if isinstance(item, Plug) and self._valid(item)]

    def components(self):
        """list[Components]: 有効な要素をshapeのDAGパス・種類ごとにまとめる。"""
        groups = {}
        classes = {Vertex: Vertices, Edge: Edges, Face: Faces, UV: UVs, CV: CVs}
        for item in self._items:
            if isinstance(item, Component) and self._valid(item):
                key = (item.shape.full_name, item.__class__)
                groups.setdefault(key, (item.shape, []))[1].append(item.index)
        return [classes[kind](shape, indices) for (_, kind), (shape, indices) in groups.items()]

    def owners(self):
        """list[Node]: 有効な対象の所有ノード。DAGパス別に重複を除く。"""
        result = {}
        for item in self._items:
            if self._valid(item):
                node = item if isinstance(item, Node) else item.shape if isinstance(item, Component) else item.node
                result.setdefault(node.full_name, node)
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
            if isinstance(item, Node) and item.is_type(type):
                result.append(item)
            elif isinstance(item, Component) and item.component_type == type:
                result.append(item)
            elif isinstance(item, Plug) and type == "plug":
                result.append(item)
        return Selection(result)

    def _valid(self, item):
        """削除されたノード・属性・範囲外要素を検出する。"""
        try:
            if isinstance(item, Node):
                return item.is_valid()
            if isinstance(item, Plug):
                if not item.node.is_valid() or not self._attributes[id(item)].isValid():
                    return False
            return bool(cmds.objExists(item.full_name))
        except (RuntimeError, ValueError, IndexError):
            return False

    def _names(self, missing):
        """変更前に有効な名前を解決する。missing不正はValueError、欠落はRuntimeError。"""
        if missing not in ("skip", "error"):
            raise ValueError("missing must be 'skip' or 'error'")
        names = []
        for item in self._items:
            if self._valid(item):
                names.append(item.full_name)
            elif missing == "error":
                raise RuntimeError("Selection contains a missing item")
        return names

    @undo_chunk("hlibSelectionRestore")
    def restore(self, missing="skip"):
        """保持した対象で現在選択を置き換える。空なら選択解除。

        Args:
            missing (str): skipは無効対象を除外、errorは変更前にRuntimeError。

        Returns:
            Selection: 自身。選択変更は一回のUndoに対応。
        """
        names = self._names(missing)
        cmds.select(names, replace=True, noExpand=True) if names else cmds.select(clear=True)
        return self

    @undo_chunk("hlibSelectionAdd")
    def add_to_selection(self, missing="skip"):
        """保持対象を現在選択へ追加する。missingはrestoreと同じ。自身を返す。"""
        names = self._names(missing)
        if names:
            cmds.select(names, add=True, noExpand=True)
        return self

    @undo_chunk("hlibSelectionRemove")
    def remove_from_selection(self, missing="skip"):
        """保持対象を現在選択から除外する。missingはrestoreと同じ。自身を返す。"""
        names = self._names(missing)
        if names:
            cmds.select(names, deselect=True, noExpand=True)
        return self

    def __len__(self):
        """int: 保持数。コンポーネントは単体で数え、削除済み参照も含む。"""
        return len(self._items)

    def __iter__(self):
        """Iterator: 保持順に参照を返す。"""
        return iter(self._items)

    def __getitem__(self, index):
        """単体参照、またはsliceに対応する参照のtupleを返す。"""
        return self._items[index]
