"""Maya の依存ノードと DAG ノードを扱う基底ラッパー。"""

from ..decorators._fast import fast_edit
from .._core.fast_write import set_attr

import maya.api.OpenMaya as om2
import maya.cmds as cmds

from ..decorators.undo import undo_chunk
from ..utils import raise_with_notify


def _resolve_node(node):
    """ノード名、MObject、または MDagPath を MObject と MDagPath へ解決する。

    Node._resolve と _node_type_of が共有する下位の解決処理。

    Args:
        node (str | om2.MObject | om2.MDagPath): 対象ノードの名前または Maya API 2.0 オブジェクト。

    Returns:
        tuple[om2.MObject, om2.MDagPath | None]: 解決した MObject と、DAG ノードで
            あれば対応する MDagPath(非DAGノードでは None)。

    Raises:
        TypeError: 対応しない入力型の場合。
        RuntimeError: ノード名を解決できない場合。
    """
    if isinstance(node, str):
        selection = om2.MSelectionList()
        try:
            selection.add(node)
        except RuntimeError as original_error:
            raise_with_notify(RuntimeError, f"ノードが見つかりません: {node}", from_exception=original_error)
        mobject = selection.getDependNode(0)
        dag_path = selection.getDagPath(0) if mobject.hasFn(om2.MFn.kDagNode) else None
        return mobject, dag_path
    if isinstance(node, om2.MDagPath):
        dag_path = om2.MDagPath(node)
        return dag_path.node(), dag_path
    if isinstance(node, om2.MObject):
        mobject = om2.MObject(node)
        dag_path = om2.MFnDagNode(mobject).getPath() if mobject.hasFn(om2.MFn.kDagNode) else None
        return mobject, dag_path
    raise TypeError("node には名前、MObject、または MDagPath を指定してください")


_MOVABLE_NUMERIC_TYPES = {
    om2.MFnNumericData.kBoolean: "bool",
    om2.MFnNumericData.kByte: "byte",
    om2.MFnNumericData.kShort: "short",
    om2.MFnNumericData.kInt: "long",
    om2.MFnNumericData.kLong: "long",
    om2.MFnNumericData.kFloat: "float",
    om2.MFnNumericData.kDouble: "double",
}  #: move_attribute() が再作成できる数値属性型と cmds.addAttr(attributeType=) の対応。


def _dump_movable_attr(plug):
    """並び替え対応の単純な動的属性から再作成に必要な情報を集める。

    数値(bool/byte/short/long/float/double)、enum、文字列型の非複合・非配列
    トップレベル動的属性のみ対応する。

    Args:
        plug (Plug): ダンプ対象の動的属性プラグ。

    Returns:
        dict: add_attr() での再作成と値・状態の復元に必要な情報。

    Raises:
        TypeError: 複合・配列属性、または対応しない属性型の場合。
    """
    if plug.is_array or plug.is_compound:
        raise TypeError(f"Cannot reorder compound or array attributes: {plug.full_name}")
    attr = plug.mplug().attribute()
    info = {
        "long_name": plug.attribute,
        "nice_name": plug.nice_name(),
        "hidden": plug.is_hidden,
        "keyable": plug.is_keyable,
        "channel_box": bool(cmds.getAttr(plug.full_name, channelBox=True)),
        "locked": plug.is_locked,
        "value": plug.get(),
        "source": plug.source(),
        "destinations": plug.destinations(),
    }
    if attr.hasFn(om2.MFn.kNumericAttribute):
        numeric_type = om2.MFnNumericAttribute(attr).numericType()
        type_name = _MOVABLE_NUMERIC_TYPES.get(numeric_type)
        if type_name is None:
            raise TypeError(f"Unsupported numeric attribute type for reordering: {plug.full_name}")
        info["attribute_type"] = type_name
        if plug.has_min:
            info["min"] = plug.min
        if plug.has_max:
            info["max"] = plug.max
        info["default_value"] = plug.default
    elif attr.hasFn(om2.MFn.kEnumAttribute):
        info["attribute_type"] = "enum"
        info["enum_name"] = cmds.attributeQuery(plug.attribute, node=plug.node.full_name, listEnum=True)[0]
        info["default_value"] = plug.default
    elif attr.hasFn(om2.MFn.kTypedAttribute) and om2.MFnTypedAttribute(attr).attrType() == om2.MFnData.kString:
        info["data_type"] = "string"
    else:
        raise TypeError(f"Unsupported attribute type for reordering: {plug.full_name}")
    return info


def _create_movable_attr(node, info):
    """_dump_movable_attr() が集めた情報から属性を再作成し、値・状態を復元する。

    Args:
        node (Node): 属性を追加する対象ノード。
        info (dict): _dump_movable_attr() が返した情報。

    Returns:
        Plug: 再作成した属性プラグ。
    """
    kwargs = {"hidden": info["hidden"]}
    if info["nice_name"]:
        kwargs["niceName"] = info["nice_name"]
    if "min" in info:
        kwargs["minValue"] = info["min"]
    if "max" in info:
        kwargs["maxValue"] = info["max"]
    if "enum_name" in info:
        kwargs["enumName"] = info["enum_name"]
    plug = node.add_attr(
        info["long_name"],
        attribute_type=info.get("attribute_type"),
        data_type=info.get("data_type"),
        default_value=info.get("default_value"),
        **kwargs,
    )
    plug.set(info["value"])
    plug.set_keyable(info["keyable"])
    if not info["keyable"]:
        plug.set_channel_box(info["channel_box"])
    if info["source"] is not None:
        info["source"].connect(plug)
    for destination in info["destinations"]:
        plug.connect(destination)
    if info["locked"]:
        plug.set_locked(True)
    return plug


def _node_type_of(node):
    """ノード名、MObject、または MDagPath から Maya nodeType 名を得る。

    Args:
        node (str | om2.MObject | om2.MDagPath): 対象ノードの名前または Maya API 2.0 オブジェクト。

    Returns:
        str: Maya のノード型名。

    Raises:
        TypeError: 対応しない入力型の場合。
        RuntimeError: ノード名を解決できない場合。
    """
    mobject, _ = _resolve_node(node)
    return om2.MFnDependencyNode(mobject).typeName


class Node:
    """Maya の依存ノード・DAG ノードを表す共通ラッパー。

    生成時は登録済みのノード型に対応するラッパーを選択する。"""

    _registry = None  #: hlib.__init__ が構築後に注入する NodeRegistry。

    @staticmethod
    def _display_rgb(value):
        """0～1の有限なRGB三要素を返す。不正値はValueError。"""
        import math

        values = tuple(float(v) for v in value)
        if len(values) != 3 or not all(math.isfinite(v) and 0 <= v <= 1 for v in values):
            raise ValueError("Expected three finite RGB values between 0 and 1")
        return values

    def outliner_color(self):
        """tuple[float, float, float] | None: Outliner色。無効ならNone。"""
        if not cmds.getAttr(self.full_name + ".useOutlinerColor"):
            return None
        return tuple(cmds.getAttr(self.full_name + ".outlinerColor")[0])

    @fast_edit
    @undo_chunk("hlibNodeOutlinerColor")
    def set_outliner_color(self, color, *, fast=False):
        """このノードのOutliner色を設定する。

        Args:
            fast (bool): TrueはOpenMaya直接更新（Undoなし）。既定False。
            color (Iterable[float] | None): 0～1のRGB。Noneでカスタム色を無効化。
        Returns:
            Node: 自身。
        Raises:
            ValueError: RGBの値・要素数が不正な場合。
            RuntimeError: 属性がない、ロックされているなど変更できない場合。

        ``fast=True`` はOpenMaya直接更新（Undoなし）。既定の ``False`` は通常処理。
        fastがbool以外ならTypeError。完了済みの直接更新は自動で戻さない。
        """
        values = None if color is None else self._display_rgb(color)
        if values is not None:
            set_attr(self.full_name + ".outlinerColor", *values, type="float3")
        set_attr(self.full_name + ".useOutlinerColor", values is not None)
        return self

    def override_color(self):
        """int | tuple[float, float, float] | None: このノードの表示色設定。

        無効ならNone。親や表示レイヤー、選択ハイライトを合成した最終表示色ではない。
        属性を持たないノードはRuntimeError。
        """
        if not cmds.getAttr(self.full_name + ".overrideEnabled"):
            return None
        if cmds.getAttr(self.full_name + ".overrideRGBColors"):
            return tuple(cmds.getAttr(self.full_name + ".overrideColorRGB")[0])
        return cmds.getAttr(self.full_name + ".overrideColor")

    @fast_edit
    @undo_chunk("hlibNodeOverrideColor")
    def set_override_color(self, color, *, fast=False):
        """このノードのDrawing Overrides色を設定する。子Shapeへは転送しない。

        Args:
            fast (bool): TrueはOpenMaya直接更新（Undoなし）。既定False。
            color (int | Iterable[float] | None): 0～31のインデックス、0～1のRGB、
                またはNone。NoneはoverrideEnabledを無効化するため表示タイプ等にも影響する。
        Returns:
            Node: 自身。
        Raises:
            ValueError: インデックスやRGBが不正な場合。
            RuntimeError: 属性がない、ロックされているなど変更できない場合。

        ``fast=True`` はOpenMaya直接更新（Undoなし）。既定の ``False`` は通常処理。
        fastがbool以外ならTypeError。完了済みの直接更新は自動で戻さない。
        """
        if color is None:
            set_attr(self.full_name + ".overrideEnabled", False)
            return self
        if isinstance(color, bool):
            raise ValueError("Color index must be an integer from 0 to 31")
        if isinstance(color, int):
            if not 0 <= color <= 31:
                raise ValueError("Color index must be between 0 and 31")
            set_attr(self.full_name + ".overrideColor", color)
            set_attr(self.full_name + ".overrideRGBColors", False)
        else:
            values = self._display_rgb(color)
            set_attr(self.full_name + ".overrideColorRGB", *values, type="float3")
            set_attr(self.full_name + ".overrideRGBColors", True)
        set_attr(self.full_name + ".overrideEnabled", True)
        return self

    @classmethod
    @undo_chunk("hlib.nodes.node.create")
    def create(cls, type, **kwargs):
        """ノードを作成し、対応する hlib wrapper として返す。

        Args:
            type (str): Maya の nodeType 名。
            **kwargs: ``maya.cmds.createNode`` に渡すキーワード引数。

        Returns:
            Node: 作成したノードに対応する wrapper。

        Raises:
            ValueError: type が空文字列または文字列以外の場合。
        """
        if not isinstance(type, str) or not type:
            raise ValueError("type must be a non-empty string")
        created_name = cmds.createNode(type, **kwargs)
        return cls(created_name)

    def __new__(cls, node, *args, **kwargs):
        """ノード型の登録情報に従ってラッパーを割り当てる。

        Args:
            node (str | om2.MObject | om2.MDagPath): 対象ノードの名前または Maya API 2.0 オブジェクト。
            *args (object): 別の登録クラスに委譲する位置引数。
            **kwargs (object): 別の登録クラスに委譲するキーワード引数。

        Returns:
            Node: 登録クラスのインスタンス。登録情報がなければ呼び出したクラスの未初期化インスタンス。

        Raises:
            TypeError: ノード入力が対応しない型の場合。
            RuntimeError: ノードを解決できない場合。
        """
        registry = cls._registry
        if registry is not None:
            node_type = _node_type_of(node)
            resolved_class = registry.wrapper_class(node_type)
            if resolved_class is not cls:
                return resolved_class(node, *args, **kwargs)
        return super().__new__(cls)

    def __init__(self, node):
        """ノード入力を解決し、MObject と必要に応じた MDagPath を保持する。

        Args:
            node (str | om2.MObject | om2.MDagPath): 対象ノードの名前または Maya API 2.0 オブジェクト。

        Returns:
            None: 値を返さない。

        Raises:
            TypeError: 対応しないノード入力型の場合。
            RuntimeError: ノード名を解決できない場合。
        """
        self._mobject = None
        self._dag_path = None
        self._resolve(node)

    def _resolve(self, node):
        """ノード名、MObject、または MDagPath を内部 API オブジェクトへ変換する。

        Args:
            node (str | om2.MObject | om2.MDagPath): 対象ノードの名前または Maya API 2.0 オブジェクト。

        Returns:
            None: 値を返さない。

        Raises:
            TypeError: 対応しないノード入力型の場合。
            RuntimeError: ノード名を解決できない場合。
        """
        self._mobject, self._dag_path = _resolve_node(node)

    def is_valid(self):
        """Maya シーン上でノードが有効か判定する。

        Returns:
            bool: ノードハンドルが有効な場合は ``True``。
        """
        return bool(
            self._mobject is not None
            and not self._mobject.isNull()
            and om2.MObjectHandle(self._mobject).isValid()
        )

    def is_alive(self):
        """ノードの Maya オブジェクトがメモリ上に生存しているか判定する。

        Returns:
            bool: MObjectHandle.isAlive() の結果。Undo キューに保持された削除済みノードも生存と判定される場合がある。
        """
        return bool(
            self._mobject is not None
            and not self._mobject.isNull()
            and om2.MObjectHandle(self._mobject).isAlive()
        )

    def mobject(self):
        """保持している Maya API 2.0 MObject を返す。

        Returns:
            om2.MObject | None: ラップ対象の MObject。
        """
        return self._mobject

    def type(self):
        """Maya の nodeType 名を返す。

        Returns:
            str: 対応する Maya nodeType。
        """
        return om2.MFnDependencyNode(self._mobject).typeName

    @property
    def type_id(self):
        """Maya の内部 typeId を整数で返す。

        同一 Maya セッション内でノード型を高速に比較する用途に使う。
        プラグインの版数や環境によって値が変わりうるため、永続化には向かない。

        Returns:
            int: MTypeId の数値表現。
        """
        return om2.MFnDependencyNode(self._mobject).typeId.id()

    @property
    def plugin_name(self):
        """ノード型がプラグイン由来の場合、そのプラグイン名を取得する。

        Returns:
            str: プラグイン名。Maya組み込みのノード型では空文字列。
        """
        return om2.MFnDependencyNode(self._mobject).pluginName

    def classification(self):
        """ノード型の分類文字列を取得する。

        Returns:
            list[str]: ``cmds.getClassification`` が返す分類文字列のリスト。
                該当が無い nodeType では空リスト。
        """
        return cmds.getClassification(self.type())

    def is_type(self, node_type):
        """自身の nodeType が指定型そのもの、またはその派生型か判定する。

        ``cmds.nodeType(inherited=True)`` による継承チェーンで判定するため、
        例えば mesh ノードは ``is_type("shape")`` で True になる。

        Args:
            node_type (str): 判定する Maya nodeType 名。

        Returns:
            bool: 継承チェーンに node_type が含まれる場合は True。

        Raises:
            ValueError: node_type が空文字列または文字列以外の場合。
        """
        if not isinstance(node_type, str) or not node_type:
            raise ValueError("node_type must be a non-empty string")
        if not self.is_valid():
            return False
        return node_type in (cmds.nodeType(self.full_name, inherited=True) or [])

    @property
    def is_locked(self):
        """ノード自体がロックされているか判定する。

        属性単位のロックは Plug.is_locked を参照する。

        Returns:
            bool: ロックされている場合は True。
        """
        return om2.MFnDependencyNode(self._mobject).isLocked

    @property
    def is_referenced(self):
        """ノードが参照ファイルから読み込まれたものか判定する。

        Returns:
            bool: 参照由来の場合は True。
        """
        return om2.MFnDependencyNode(self._mobject).isFromReferencedFile

    def is_ancestor_of(self, other):
        """other が自身の DAG 階層上の子孫か判定する。

        Args:
            other (Node | str): 判定対象のノード。

        Returns:
            bool: other が自身より下の階層にある場合は True。自身自身や
                非DAGノード、無効なノードでは False。

        Raises:
            TypeError: other が Node/str 以外の場合。
        """
        from .._core.coerce import to_node

        other_node = to_node(other)
        self_full = self.full_name
        other_full = other_node.full_name
        if not self_full or not other_full:
            return False
        return other_full != self_full and other_full.startswith(self_full + "|")

    def is_parent_of(self, other):
        """other が自身の直接の子か判定する（孫以下は対象外）。

        Args:
            other (Node | str): 判定対象のノード。

        Returns:
            bool: other が自身の直接の子の場合は True。

        Raises:
            TypeError: other が Node/str 以外の場合。
        """
        from .._core.coerce import to_node

        other_node = to_node(other)
        self_full = self.full_name
        other_full = other_node.full_name
        if not self_full or not other_full:
            return False
        parent_prefix, separator, _ = other_full.rpartition("|")
        return bool(separator) and parent_prefix == self_full

    def is_child_of(self, other):
        """other が自身の直接の親か判定する（祖父母以上は対象外）。

        Args:
            other (Node | str): 判定対象のノード。

        Returns:
            bool: other が自身の直接の親の場合は True。

        Raises:
            TypeError: other が Node/str 以外の場合。
        """
        from .._core.coerce import to_node

        other_node = to_node(other)
        return other_node.is_parent_of(self)

    def attribute_count(self):
        """ノードが持つ属性の総数を取得する。

        Returns:
            int: 属性数。
        """
        return om2.MFnDependencyNode(self._mobject).attributeCount()

    def path(self, full=False):
        """DAG ノードのパス名を返す。

        Args:
            full (bool): ``True`` の場合はフルDAGパス、``False`` の場合は
                パーシャルパスを返す。

        Returns:
            str: 指定形式の DAG パス名。

        Raises:
            RuntimeError: DAG パスを保持していない場合。
        """
        if self._dag_path is None:
            raise RuntimeError("DAG ノードではありません")
        if full:
            return self._dag_path.fullPathName()
        return self._dag_path.partialPathName()

    def partial_path(self):
        """DAG ノードのパーシャルパス名を返す互換メソッド。

        Returns:
            str: 指定形式の DAG パス名。

        Raises:
            RuntimeError: DAG パスを保持していない場合。
        """
        return self.path()

    def full_path(self):
        """DAG ノードのフルパス名を返す互換メソッド。

        Returns:
            str: 完全 DAG パス名。

        Raises:
            RuntimeError: DAG パスを保持していない場合。
        """
        return self.path(full=True)

    def is_root(self):
        """DAG ノードがワールド直下か判定する。

        Returns:
            bool: 保持する DAG パスの長さが1なら True。

        Raises:
            RuntimeError: DAG パスを保持していない場合。
        """
        if self._dag_path is None:
            raise RuntimeError("DAG ノードではありません")
        return self._dag_path.length() == 1

    def node_name(self, remove_namespace=False):
        """DAG パスを除いたノード名を返す。

        Args:
            remove_namespace (bool): ``True`` の場合はnamespaceも除外する。

        Returns:
            str: namespaceを含むノード名。``remove_namespace`` が ``True`` の場合は
                namespaceを含まないノード名。
        """
        node_name = om2.MFnDependencyNode(self._mobject).name()
        if remove_namespace:
            node_name = node_name.rsplit(":", 1)[-1]
        return node_name

    def namespace(self):
        """ノードが属するネームスペースを返す。

        Returns:
            Namespace: ノードが属するNamespace。
        """
        # namespaces.namespace が ..nodes を逆方向 import するため、
        # 循環回避のためここで遅延 import する（hlib で意図的な相互依存の一つ）。
        from ..namespaces import Namespace

        node_name = self.node_name()
        if ":" not in node_name:
            return Namespace(":")
        return Namespace(node_name.rsplit(":", 1)[0])

    @undo_chunk("hlibNodeRename")
    def rename(self, name, ignore_shape=False):
        """ノード名を変更し、変更後の名前を返す。

        Args:
            name (str): 新しいノード名。
            ignore_shape (bool): ``True`` の場合はShapeの名前変更を抑制する。

        Returns:
            str: Mayaが確定した変更後のノード名。

        Raises:
            RuntimeError: ノード名を変更できない場合。
        """
        return cmds.rename(self.name(), name, ignoreShape=ignore_shape)

    @undo_chunk("hlibNodeSetNamespace")
    def set_namespace(self, namespace):
        """ノードを指定したネームスペースへ移動する。

        Args:
            namespace (str | Namespace): 移動先のnamespace名。末尾の ``":"`` は任意。

        Returns:
            str: Mayaが確定したnamespace付きノード名。

        Raises:
            ValueError: namespaceが空文字列または文字列でない場合。
            RuntimeError: namespace移動に失敗した場合。
        """
        # namespaces.namespace ⇔ nodes の相互依存を避けるための遅延 import。namespace() と同じ理由。
        from ..namespaces import Namespace

        if isinstance(namespace, Namespace):
            target_namespace = namespace
        elif isinstance(namespace, str) and namespace:
            target_namespace = Namespace(namespace)
        else:
            raise ValueError("namespace must be a non-empty string")
        if not target_namespace.exists() and target_namespace.name() != ":":
            target_namespace = Namespace.create(target_namespace)
        namespace_name = target_namespace.name()
        node_name = self.node_name(True)
        new_name = (
            f"{namespace_name}:{node_name}"
            if namespace_name != ":"
            else node_name
        )
        return cmds.rename(self.name(), new_name)

    def _connected_plugs(self, as_source, as_destination, type=None):
        """ノードの指定方向に接続された外部Plugを収集する。

        Args:
            as_source (bool): 接続元Plugを検索対象に含めるかどうか。
            as_destination (bool): 接続先Plugを検索対象に含めるかどうか。
            type (str | None): 指定した場合、接続先ノードの nodeType が
                ``is_type`` で一致するものだけに絞り込む(継承チェーンも判定)。

        Returns:
            list[Plug]: 接続先の外部Plugを重複なしで格納したリスト。
        """
        # plugs.plug が ..nodes.node を逆方向 import するため、
        # 循環回避のためここで遅延 import する（hlib で意図的な相互依存の一つ）。
        from ..plugs.plug import Plug

        plugs = []
        seen = set()
        for mplug in om2.MFnDependencyNode(self._mobject).getConnections():
            for connected in mplug.connectedTo(as_source, as_destination):
                key = connected.name()
                if key in seen:
                    continue
                node = Node(connected.node())
                if type is not None and not node.is_type(type):
                    continue
                seen.add(key)
                plugs.append(Plug(node, connected))
        return plugs

    def inputs(self, type=None):
        """このノードへ入力する接続元Plugを返す。

        Args:
            type (str | None): 指定した場合、接続元ノードの nodeType で絞り込む
                (継承チェーンも判定。例: ``type="animCurve"``)。

        Returns:
            list[Plug]: 入力元の外部プラグ。名前で重複を除外する。接続がなければ空リスト。
        """
        return self._connected_plugs(True, False, type=type)

    def outputs(self, type=None):
        """このノードから出力する接続先Plugを返す。

        Args:
            type (str | None): 指定した場合、接続先ノードの nodeType で絞り込む
                (継承チェーンも判定)。

        Returns:
            list[Plug]: 出力先の外部プラグ。名前で重複を除外する。接続がなければ空リスト。
        """
        return self._connected_plugs(False, True, type=type)

    def connections(self, type=None):
        """このノードに接続された外部Plugを返す。

        Args:
            type (str | None): 指定した場合、接続先ノードの nodeType で絞り込む
                (継承チェーンも判定)。

        Returns:
            list[Plug]: 入力元と出力先の外部プラグ。名前で重複を除外する。接続がなければ空リスト。
        """
        plugs = []
        seen = set()
        for plug in self.inputs(type=type) + self.outputs(type=type):
            if plug.full_name in seen:
                continue
            seen.add(plug.full_name)
            plugs.append(plug)
        return plugs

    def history(self, type=None, future=False):
        """構築履歴を検索し、対応するノードラッパーを返す。

        Args:
            type (str | None): 継承型を含むノード型フィルター。Noneは全型。
            future (bool): Trueは下流、Falseは上流を検索する。

        Returns:
            list[Node]: Mayaの履歴順。自身と重複を除く。該当なしなら空リスト。

        Raises:
            RuntimeError: 無効なノード、またはMayaの履歴検索が失敗した場合。
        """
        names = cmds.listHistory(self.full_name, future=future) or []
        result, seen = [], {self.uuid}
        for name in names:
            node = Node(name)
            if node.uuid in seen:
                continue
            seen.add(node.uuid)
            if type is None or node.is_type(type):
                result.append(node)
        return result

    @undo_chunk("hlibNodeResetAttrs")
    def reset_attrs(self, attributes=None):
        """指定属性、または書き込み可能なキー設定対象属性を既定値へ戻す。

        Args:
            attributes (str | Iterable[str] | None): 属性名。Noneはキー設定可能な
                数値・単位・enum属性を対象とし、ロック・入力接続・非対応型は除外する。
                明示指定した属性のエラーは除外せず送出する。

        Returns:
            list[Plug]: リセットした属性。全変更を一回のUndoにまとめる。

        Raises:
            AttributeError: 指定属性が存在しない場合。
            TypeError: 明示指定した属性がリセット非対応の場合。
            RuntimeError: 明示指定した属性がロック・接続済みなどで書き込みできない場合。
        """
        if attributes is None:
            plugs = [plug for plug in self.plugs(keyable=True, scalar=True)
                     if plug.default is not None and not plug.is_destination
                     and cmds.getAttr(plug.full_name, settable=True)]
        else:
            if isinstance(attributes, str):
                attributes = [attributes]
            plugs = [self.plug(name) for name in attributes]
        for plug in plugs:
            plug.reset()
        return plugs

    @fast_edit
    @undo_chunk("hlibNodeSetAttrFlags")
    def set_attr_flags(self, attributes, locked=None, keyable=None, channel_box=None, *, fast=False):
        """指定した属性のロック・キー設定可否・Channel Box表示をまとめて変更する。

        Args:
            fast (bool): TrueはOpenMaya直接更新（Undoなし）。既定False。
            attributes (str | Iterable[str]): 属性名。選択状態やChannel Box選択は使用しない。
                複合属性の子まで変更する場合は子属性名を明示する。
            locked (bool | None): ロック状態。Noneは変更しない。
            keyable (bool | None): キー設定可否。Noneは変更しない。
            channel_box (bool | None): Channel Box表示。Noneは変更しない。
                keyable=Trueの属性はMayaの仕様により表示される。

        Returns:
            Node: 自身。全変更を一回のUndoにまとめる。

        Raises:
            AttributeError: 指定属性が存在しない場合。全属性を変更前に解決する。
            TypeError: 状態にboolまたはNone以外を指定した場合。
            RuntimeError: Mayaが変更を拒否した場合。途中の変更は自動では戻さない。

        ``fast=True`` はOpenMaya直接更新（Undoなし）。既定の ``False`` は通常処理。
        fastがbool以外ならTypeError。完了済みの直接更新は自動で戻さない。
        """
        flags = {}
        for name, value in (("lock", locked), ("keyable", keyable), ("channelBox", channel_box)):
            if value is not None:
                if not isinstance(value, bool):
                    raise TypeError(f"{name} must be bool or None")
                flags[name] = value
        if isinstance(attributes, str):
            attributes = [attributes]
        plugs = [self.plug(name) for name in attributes]
        if flags:
            for plug in plugs:
                set_attr(plug.full_name, **flags)
        return self

    def plugs(self, **kwargs):
        """ノードの属性を Plug のリストとして列挙する。

        Args:
            kwargs: ``cmds.listAttr`` にそのまま渡す追加フラグ
                (``keyable=True``、``visible=True``、``write=True`` など)。

        Returns:
            list[Plug]: 該当する属性の Plug。``cmds.listAttr`` が返す名前のうち
                実際には評価できないもの（未確保の要素を持つ配列複合属性の子など）は
                黙ってスキップする。該当なしの場合は空リスト。

        Raises:
            RuntimeError: ノードが無効な場合。
        """
        if not self.is_valid():
            raise RuntimeError("無効なノードの属性は列挙できません")
        names = cmds.listAttr(self.full_name, **kwargs) or []
        plugs = []
        for name in names:
            try:
                plugs.append(self.plug(name))
            except (AttributeError, RuntimeError, ValueError):
                continue
        return plugs

    def aliases(self):
        """このノードの属性エイリアスを取得する。

        Returns:
            list[tuple[str, Plug]]: ``(エイリアス名, 対応するPlug)`` のリスト。
                エイリアスが無ければ空リスト。

        Raises:
            RuntimeError: ノードが無効な場合。
        """
        if not self.is_valid():
            raise RuntimeError("無効なノードのエイリアスは取得できません")
        # plugs.plug が ..nodes.node を逆方向 import するため、
        # 循環回避のためここで遅延 import する（plug() と同じ理由）。
        from ..plugs.plug import Plug

        flat = cmds.aliasAttr(self.full_name, query=True) or []
        pairs = []
        for index in range(0, len(flat), 2):
            alias_name, attribute_name = flat[index], flat[index + 1]
            # 配列要素(例: "weight[0]")は findPlug が解決できないため、
            # ブラケット付き属性パスも扱える MSelectionList 経由で解決する。
            selection = om2.MSelectionList()
            selection.add(f"{self.full_name}.{attribute_name}")
            pairs.append((alias_name, Plug(self, selection.getPlug(0))))
        return pairs

    @undo_chunk("hlibNodeAddAttr")
    def add_attr(
        self,
        long_name,
        attribute_type=None,
        data_type=None,
        default_value=None,
        **kwargs,
    ):
        """属性を追加し、追加したPlugを返す。

        Args:
            long_name (str): 追加する属性のロング名。
            attribute_type (str | None): addAttr の attributeType。data_type と少なくとも一方が必要。
            data_type (str | None): addAttr の dataType。
            default_value (object | None): addAttr の defaultValue。None なら指定しない。
            **kwargs (object): addAttr に渡す追加フラグ。明示引数に対応する短縮フラグは上書きする。

        Returns:
            Plug: 追加した属性の型に対応するプラグ。

        Raises:
            ValueError: long_name が空または文字列以外、あるいは属性型の指定がない場合。
            RuntimeError: Maya が属性追加を拒否した場合。
        """
        if not isinstance(long_name, str) or not long_name:
            raise ValueError("long_name must be a non-empty string")
        if attribute_type is None and data_type is None:
            raise ValueError("attribute_type or data_type is required")
        add_kwargs = dict(kwargs)
        add_kwargs["ln"] = long_name
        if attribute_type is not None:
            add_kwargs["at"] = attribute_type
        if data_type is not None:
            add_kwargs["dt"] = data_type
        if default_value is not None:
            add_kwargs["dv"] = default_value
        cmds.addAttr(self.name(), **add_kwargs)
        return self.plug(long_name)

    def user_attribute_names(self):
        """トップレベルのユーザー定義属性名を現在の並び順で取得する。

        複合属性の子は含まない。

        Returns:
            list[str]: ロング名のリスト。並び順は Channel Box の表示順。

        Raises:
            RuntimeError: ノードが無効な場合。
        """
        if not self.is_valid():
            raise RuntimeError("無効なノードの属性は列挙できません")
        names = cmds.listAttr(self.full_name, userDefined=True) or []
        return [name for name in names if not self.plug(name).is_child]

    @undo_chunk("hlibNodeMoveAttribute")
    def move_attribute(self, name, offset):
        """ユーザー定義属性を Channel Box 上で前後に移動する。

        Maya には属性の並び替え API が無いため、移動元と移動先のうち手前側の
        位置から末尾までの属性をまとめて削除し、新しい順序で再作成すること
        で実現する(移動先より後ろにある、移動と無関係な属性も再作成対象に
        含まれる。数値・enum・文字列型の非複合・非配列トップレベル動的属性
        のみ対応。対応しない属性が再作成対象に含まれる場合は何も変更せず
        例外を送出する)。

        Args:
            name (str): 移動するユーザー定義属性のロング名。
            offset (int): 正の値で末尾方向、負の値で先頭方向へ移動する位置数。
                範囲を超える指定は先頭・末尾で止まる。

        Returns:
            Node: 自身。全変更を一回の Undo にまとめる。

        Raises:
            ValueError: name がトップレベルのユーザー定義属性一覧に無い場合。
            TypeError: 移動範囲に複合・配列属性、または対応しない属性型が
                含まれる場合。
            RuntimeError: ノードが無効な場合。
        """
        names = self.user_attribute_names()
        if name not in names:
            raise ValueError(f"{name} is not a top-level user-defined attribute of {self.full_name}")
        old_index = names.index(name)
        new_index = max(0, min(len(names) - 1, old_index + offset))
        if new_index == old_index:
            return self
        names.remove(name)
        names.insert(new_index, name)
        window_start = min(old_index, new_index)
        to_recreate = names[window_start:]

        infos = [_dump_movable_attr(self.plug(attr_name)) for attr_name in to_recreate]
        for attr_name in to_recreate:
            self.plug(attr_name).delete_attr(force=True)
        for info in infos:
            _create_movable_attr(self, info)
        return self

    def plug(self, name):
        """アトリビュートを扱う Plug オブジェクトを取得する。

        ノードのアトリビュート操作には、このメソッドを使用します。
        返された Plug で値の取得・設定や、ほかのプラグとの接続を行えます。

        Args:
            name (str): 属性名または Maya が解決可能な属性パス。

        Returns:
            Plug: 解決した属性プラグ。

        Raises:
            ValueError: 空文字列または文字列以外を指定した場合。
            RuntimeError: ノードが無効な場合。
            AttributeError: 属性を解決できない場合。
        """
        if not isinstance(name, str) or not name:
            raise ValueError("name には空でない属性パスを指定してください")
        if not self.is_valid():
            raise RuntimeError("無効なノードの属性にはアクセスできません")
        # plugs.plug ⇔ nodes の相互依存を避けるための遅延 import。inputs()/outputs() と同じ理由。
        from ..plugs.plug import Plug

        try:
            mplug = om2.MFnDependencyNode(self._mobject).findPlug(name, False)
        except RuntimeError as error:
            raise AttributeError(f"属性が見つかりません: {self.name()}.{name}") from error
        return Plug(self, mplug)

    def attr(self, name):
        """互換用の別名。使い方・引数・戻り値は :meth:`plug` を参照してください。"""
        return self.plug(name)

    def has_attr(self, name):
        """属性パスを解決できるか判定する。

        Args:
            name (str): 属性名または属性パス。

        Returns:
            bool: 属性を解決できる場合は ``True``。
        """
        try:
            self.plug(name)
        except (AttributeError, RuntimeError, ValueError):
            return False
        return True

    @property
    def uuid(self):
        """ノードの Maya UUID を返す。

        Returns:
            str | None: 有効なノードの UUID。無効な場合は ``None``。
        """
        if not self.is_valid():
            return None
        return om2.MFnDependencyNode(self._mobject).uuid().asString()

    def name(self):
        """Maya の最短一意ノード名を返す。

        Returns:
            str: 無効なノードでは空文字列。
        """
        if not self.is_valid():
            return ""
        if self._dag_path is not None:
            return self._dag_path.partialPathName()
        return om2.MFnDependencyNode(self._mobject).name()

    @property
    def full_name(self):
        """Maya の完全 DAG パスまたは DG ノード名を返す。

        Returns:
            str: 無効なノードでは空文字列。
        """
        if not self.is_valid():
            return ""
        if self._dag_path is not None:
            return self._dag_path.fullPathName()
        return om2.MFnDependencyNode(self._mobject).name()

    def __str__(self):
        """Maya の最短一意ノード名を文字列として返す。

        Returns:
            str: 最短一意名。無効なノードでは空文字列。
        """
        return self.name()

    def __repr__(self):
        """デバッグ用にクラス名とノード名を含む表現を返す。

        Returns:
            str: 有効なら型名とノード名、無効なら型名と invalid を含む文字列。
        """
        if self.is_valid():
            return f"{type(self).__name__}({self.name()!r})"
        return f"<{type(self).__name__} invalid>"

    def __getattr__(self, name):
        """通常属性にない名前を Maya Plug として動的に解決する。

        Args:
            name (str): 取得しようとした Python 属性名。

        Returns:
            Plug: 解決した Maya 属性プラグ。

        Raises:
            AttributeError: 非公開名または存在しない Maya 属性を指定した場合。
            RuntimeError: ノードが無効な場合。
        """
        if name.startswith("_"):
            raise AttributeError(name)
        try:
            return self.plug(name)
        except AttributeError as error:
            raise AttributeError(f"属性が見つかりません: {self.name()}.{name}") from error


