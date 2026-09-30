"""Maya の依存ノードと DAG ノードを扱う基底ラッパー。"""

from typing import Any

from .._core.collection import BulkCollection, bulk_api
from .._core.registry import collection_export

from ..decorators._fast import fast_edit
from .._core.coerce import (
    DeletedAttributeError,
    deleted_attribute_error,
    mplug_attribute_exists,
    selection_owner,
)
from .._core.fastWrite import set_attr

import maya.api.OpenMaya as om2
import maya.cmds as cmds

from ..decorators.undo import undo_chunk
from ..utils import raise_with_notify


def _resolve_node(node):
    """ノードを表す入力を MObject と MDagPath へ解決する。

    Node.__new__ (ラッパー型の選択)と Node._resolve が共有する下位の解決処理。
    Node(...) の生成では __new__ で1回だけ呼び、結果を __init__ へ引き継ぐ。Plug・MPlug は
    所有ノード、コンポーネント(単体・複数形)は所有シェイプへ解決する。

    Args:
        node (str | Node | Plug | Component | Components | om2.MObject | om2.MDagPath | om2.MPlug):
            対象ノードの名前、hlib のラッパー、または Maya API 2.0 オブジェクト。
            ``"node.attribute"`` や ``"pCube1.vtx[0]"`` のような文字列も所有ノードへ解決する
            (インスタンス化されたノードは、名前が指すインスタンスのパスを保持する)。

    Returns:
        tuple[om2.MObject, om2.MDagPath | None]: 解決した MObject と、DAG ノードで
            あれば対応する MDagPath(非DAGノードでは None)。

    Raises:
        TypeError: 対応しない入力型、または依存ノード以外(アトリビュートなど)を指す MObject の場合。
        ValueError: 所有ノードは有効で、アトリビュートが ``deleteAttr`` で削除済みの Plug・MPlug の場合
            (:class:`hlib._core.coerce.DeletedAttributeError`。``RuntimeError`` の派生でもある)。
        RuntimeError: 名前を解決できない(存在しない、または複数の対象に一致する)場合、
            または空・無効な(削除済みの)ラッパーや om2 オブジェクトを指定した場合。
    """
    if isinstance(node, str):
        selection = om2.MSelectionList()
        try:
            selection.add(node)
        except RuntimeError as original_error:
            # MSelectionList は複数のノードに一致する名前も「存在しない」として拒否するため、
            # 利用者が原因を判別できるよう maya.cmds で一致数を確かめてからメッセージを選ぶ。
            if node and len(cmds.ls(node) or []) > 1:
                message = f"名前が一意ではありません(複数のノードに一致します): {node}"
            else:
                message = f"ノードが見つかりません: {node}"
            raise_with_notify(RuntimeError, message, from_exception=original_error)
        if selection.length() != 1:
            # "dup.tx" のようなプラグ名・コンポーネント名は、同名ノードがあると複数の要素になる。
            raise_with_notify(
                RuntimeError,
                f"名前が一意ではありません(複数の対象に一致します): {node}",
                from_exception=None,
            )
        return selection_owner(selection, 0, node)
    if isinstance(node, om2.MDagPath):
        if not node.isValid() or not om2.MObjectHandle(node.node()).isValid():
            raise RuntimeError("無効な(削除済みの)MDagPath からノードは解決できません")
        dag_path = om2.MDagPath(node)
        return dag_path.node(), dag_path
    if isinstance(node, om2.MObject):
        if node.isNull():
            raise RuntimeError("空の MObject からノードは解決できません")
        if not om2.MObjectHandle(node).isValid():
            raise RuntimeError("削除済みノードの MObject からノードは解決できません")
        if not node.hasFn(om2.MFn.kDependencyNode):
            raise TypeError("MObject には依存ノードを指定してください(アトリビュート・コンポーネント・データは不可)")
        mobject = om2.MObject(node)
        dag_path = om2.MFnDagNode(mobject).getPath() if mobject.hasFn(om2.MFn.kDagNode) else None
        return mobject, dag_path
    if isinstance(node, om2.MPlug):
        if node.isNull:
            raise RuntimeError("空の MPlug からノードは解決できません")
        owner = node.node()
        # 所有ノードが有効でも、deleteAttr で削除されたアトリビュートの MPlug は削除済みの対象として扱う
        # (hlib のコマンドと同じ。所有ノードが削除済みなら下の MObject の解決で RuntimeError)。
        if om2.MObjectHandle(owner).isValid() and not mplug_attribute_exists(node, owner):
            raise DeletedAttributeError("削除済みのアトリビュートの MPlug からノードは解決できません")
        return _resolve_node(owner)
    if isinstance(node, Node):
        if not node.is_valid():
            raise RuntimeError("無効な(削除済みの)ノードは指定できません")
        dag_path = node._current_dag_path()
        return om2.MObject(node._mobject), om2.MDagPath(dag_path) if dag_path is not None else None
    # plugs/components は nodes を逆方向に import するため、循環回避のため遅延 import する。
    from ..components.component import Component, Components
    from ..plugs.plug import Plug

    if isinstance(node, Plug):
        error = deleted_attribute_error(node)
        if error is not None:
            raise error
        return _resolve_node(node.node)
    if isinstance(node, (Component, Components)):
        return _resolve_node(node.shape)
    raise TypeError(
        "node には名前、Node、Plug、Component、MObject、MDagPath、または MPlug を指定してください"
    )


def _is_deleted_api_object(value):
    """om2 オブジェクトが削除済みのノードを指すか判定する(空のオブジェクトは False)。

    Args:
        value (object): 判定する値。om2 の MObject・MDagPath・MPlug 以外は False。

    Returns:
        bool: 削除済みのノードを指す MObject・MDagPath・MPlug の場合は True。
            無効な MDagPath は、空のパスも含めて True(``Node(...)`` も区別しない)。
    """
    if isinstance(value, om2.MPlug):
        if value.isNull:
            return False
        value = value.node()
    if isinstance(value, om2.MDagPath):
        return not value.isValid() or not om2.MObjectHandle(value.node()).isValid()
    if isinstance(value, om2.MObject):
        return not value.isNull() and not om2.MObjectHandle(value).isValid()
    return False


def _query_target(other):
    """判定メソッド(``is_parent_of`` など)の対象をノードへ解決する。

    ``hlib._core.coerce.to_node`` と同じ規則で解決し、削除済みの対象(削除済みの Node、
    所有ノードが削除済みの Plug・Component、アトリビュートが ``deleteAttr`` で削除済みの Plug・MPlug、
    削除済みのノードを指す om2 オブジェクト)は例外にせず None を返す(判定は False)。

    Args:
        other (Node | str | Plug | Component | Components | om2.MObject | om2.MDagPath | om2.MPlug):
            判定対象。

    Returns:
        Node | None: 解決した有効なノード。削除済みの対象は None。

    Raises:
        TypeError: 対応しない型の場合。
        RuntimeError: 名前を解決できない(存在しない、または複数のノードに一致する)場合、
            または空の MObject・MPlug の場合。
    """
    from .._core.coerce import to_node

    try:
        node = to_node(other)
    except DeletedAttributeError:
        return None
    except RuntimeError:
        if _is_deleted_api_object(other):
            return None
        raise
    return node if node.is_valid() else None


_MOVABLE_NUMERIC_TYPES = {
    om2.MFnNumericData.kBoolean: "bool",
    om2.MFnNumericData.kByte: "byte",
    om2.MFnNumericData.kShort: "short",
    om2.MFnNumericData.kInt: "long",
    om2.MFnNumericData.kLong: "long",
    om2.MFnNumericData.kFloat: "float",
    om2.MFnNumericData.kDouble: "double",
}  #: move_attribute_order() が再作成できる数値アトリビュート型と cmds.addAttr(attributeType=) の対応。


def _dump_movable_attr(plug):
    """並び替え対応の単純な動的アトリビュートから再作成に必要な情報を集める。

    数値(bool/byte/short/long/float/double)、enum、文字列型の非複合・非配列
    トップレベル動的アトリビュートのみ対応する。

    Args:
        plug (Plug): ダンプ対象の動的アトリビュートプラグ。

    Returns:
        dict: add_attribute() での再作成と値・状態の復元に必要な情報。

    Raises:
        TypeError: 複合・配列アトリビュート、または対応しないアトリビュート型の場合。
    """
    if plug.is_array() or plug.is_compound():
        raise TypeError(f"Cannot reorder compound or array attributes: {plug.full_name()}")
    attr = plug.mplug().attribute()
    info = {
        "long_name": plug.attribute_name(),
        "nice_name": plug.nice_name(),
        "hidden": plug.is_hidden(),
        "keyable": plug.is_keyable(),
        "channel_box": bool(cmds.getAttr(plug.full_name(), channelBox=True)),
        "locked": plug.is_locked(),
        "value": plug.get(),
        "source": plug.source(),
        "destinations": plug.destinations(),
    }
    if attr.hasFn(om2.MFn.kNumericAttribute):
        numeric_type = om2.MFnNumericAttribute(attr).numericType()
        type_name = _MOVABLE_NUMERIC_TYPES.get(numeric_type)
        if type_name is None:
            raise TypeError(f"Unsupported numeric attribute type for reordering: {plug.full_name()}")
        info["attribute_type"] = type_name
        if plug.has_min():
            info["min"] = plug.min()
        if plug.has_max():
            info["max"] = plug.max()
        info["default_value"] = plug.default()
    elif attr.hasFn(om2.MFn.kEnumAttribute):
        info["attribute_type"] = "enum"
        info["enum_name"] = cmds.attributeQuery(plug.attribute_name(), node=plug.node.full_name(), listEnum=True)[0]
        info["default_value"] = plug.default()
    elif attr.hasFn(om2.MFn.kTypedAttribute) and om2.MFnTypedAttribute(attr).attrType() == om2.MFnData.kString:
        info["data_type"] = "string"
    else:
        raise TypeError(f"Unsupported attribute type for reordering: {plug.full_name()}")
    return info


def _create_movable_attr(node, info):
    """_dump_movable_attr() が集めた情報からアトリビュートを再作成し、値・状態を復元する。

    Args:
        node (Node): アトリビュートを追加する対象ノード。
        info (dict): _dump_movable_attr() が返した情報。

    Returns:
        Plug: 再作成したアトリビュートプラグ。
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
    plug = node.add_attribute(
        info["long_name"],
        attribute_type=info.get("attribute_type"),
        data_type=info.get("data_type"),
        default_value=info.get("default_value"),
        **kwargs,
    )
    plug.set(info["value"])
    plug.set_flags(keyable=info["keyable"])
    if not info["keyable"]:
        plug.set_flags(channel_box=info["channel_box"])
    if info["source"] is not None:
        info["source"].connect(plug)
    for destination in info["destinations"]:
        plug.connect(destination)
    if info["locked"]:
        plug.set_flags(locked=True)
    return plug


class Node:
    """Maya の依存ノード・DAG ノードを表す共通ラッパー。

    生成時は登録済みのノード型に対応するラッパーを選択する。
    ``Node(value)`` の value には名前、MObject、MDagPath に加え、既存の Node
    (同じノードを指す新しいラッパー)、Plug・MPlug(所有ノード)、
    Component・Components(所有シェイプ)も指定できる。名前が存在しない・
    複数の対象に一致する場合や、空・削除済みの対象は RuntimeError になる
    (``"bulk*"`` のように複数のノードに一致するパターンも最初の一致を返さない。
    パターンは ``hlib.ls`` を使う)。所有ノードは有効でアトリビュートだけが ``deleteAttr`` で
    削除された Plug・MPlug は ValueError(``hlib._core.coerce.DeletedAttributeError``。
    RuntimeError の派生でもあるため、従来どおり RuntimeError としても捕捉できる)。

    インスタンス化されたノードは、指定されたインスタンスの DAG パスを保持する。
    そのインスタンスだけが削除された場合は、パスを使う操作がRuntimeErrorになる。
    別インスタンスへ暗黙に切り替えない。ノード自体の有効性はis_validで照会する。

    ``str(node)`` は maya.cmds で一意に解決できる最短名(:meth:`name`)を返すため、
    Node はそのまま ``cmds.select(node)`` のように maya.cmds へ渡せる。名前は
    呼び出すたびに再計算するため、名前変更・親子付け替えに追従する。
    削除済みのノードは空文字列になる。"""

    _registry = None  #: hlib.__init__ が構築後に注入する NodeRegistry。
    _fn_cache = None  #: _dependency_fn() が初回に作る MFnDependencyNode(ノードごとに1つ)。

    def shading_engines(self):
        """自身から直接接続されているShadingEngineを重複なしで返す。

        Returns:
            list[ShadingEngine]: 直接接続先。テクスチャから履歴を辿る操作ではない。
        """
        from .shadingEngine import ShadingEngine
        names = cmds.listConnections(self.full_name(), source=False, destination=True,
                                     type="shadingEngine") or []
        return list(dict.fromkeys(ShadingEngine(name) for name in names))

    def assigned_objects(self):
        """接続先ShadingEngineのメンバーを重複なしで取得する。

        Returns:
            list[Node | Face]: 割り当て先オブジェクトまたはフェース。
        """
        result = []
        for group in self.shading_engines():
            for member in group.members():
                if member not in result:
                    result.append(member)
        return result

    def materials(self):
        """接続/割り当て先のサーフェスマテリアルを取得する。

        Returns:
            list[Node]: 重複なしのマテリアル。未接続のShadingEngineは除く。
        """
        result = []
        for group in self.shading_engines():
            material = group.get_shader()
            if material is not None and material not in result:
                result.append(material)
        return result

    def get_visibility(self):
        """bool: 自身のvisibilityアトリビュート値。親や表示レイヤーを含む最終可視性ではない。"""
        return bool(self.plug("visibility").get())

    @fast_edit
    @undo_chunk("hlibNodeSetVisible")
    def set_visibility(self, state, *, fast=False):
        """visibility を指定した状態に設定する。親やレイヤーの可視性は変更しない。

        Args:
            state (bool): visibilityへ設定する値。
            fast (bool): TrueはOpenMaya直接更新（Undoなし）。既定False。

        Returns:
            Node: 自身。

        ``fast=True`` はOpenMaya直接更新（Undoなし）。既定の ``False`` は通常処理。
        fastがbool以外ならTypeError。完了済みの直接更新は自動で戻さない。
        """
        if not isinstance(state, bool):
            raise TypeError("state must be a bool")
        self.plug("visibility").set(state)
        return self

    def get_outliner_visibility(self):
        """アウトライナーでの表示を許可する設定値を取得する。

        Returns:
            bool: hiddenInOutlinerがFalseならTrue。実際の画面上の可視性ではない。

        Raises:
            AttributeError: hiddenInOutlinerがないノードの場合。
            RuntimeError: ノードが無効な場合。

        エディターのフィルター・親の折り畳み・非表示ノード表示設定は判定しない。
        """
        return not bool(self.plug("hiddenInOutliner").get())

    @fast_edit
    @undo_chunk("hlibNodeSetOutlinerVisibility")
    def set_outliner_visibility(self, state, *, fast=False):
        """ノードのアウトライナー表示を切り替える。

        Args:
            state (bool): Trueで表示、Falseで非表示（hiddenInOutlinerを反転設定）。
            fast (bool): TrueはOpenMaya直接更新（Undoなし）。既定False。

        Returns:
            Node: 自身。Nodes・Transforms・Jointsからの一括操作にも対応する。

        Raises:
            TypeError: stateまたはfastがboolでない場合。
            AttributeError: 対応アトリビュートがない場合。
            RuntimeError: ロック・入力接続などで更新できない場合。

        ビューポートのvisibilityは変更しない。表示の最終結果は各Outlinerの
        フィルターや非表示ノード表示設定にも依存する。
        """
        if not isinstance(state, bool):
            raise TypeError("state must be a bool")
        self.plug("hiddenInOutliner").set(not state)
        return self

    def get_outliner_color(self):
        """Color: このノードのOutliner色。無効時はdisabledモード。"""
        from ..general.color import Color
        if not cmds.getAttr(self.full_name() + ".useOutlinerColor"):
            return Color.disabled()
        return Color(rgb=cmds.getAttr(self.full_name() + ".outlinerColor")[0])

    @fast_edit
    @undo_chunk("hlibNodeOutlinerColor")
    def set_outliner_color(self, color, *, fast=False):
        """このノードのOutliner色を設定する。色番号は保持RGBへ変換する。

        Args:
            color (Color | int | Iterable[float] | None): 表示色。None/disabledは無効化。
            fast (bool): TrueはOpenMaya直接更新でUndoなし。
        Returns:
            Node: 自身。入力Colorの変更は自動反映しない。
        Raises:
            ValueError: 色の値が不正な場合。
            RuntimeError: アトリビュートがない、ロック・接続済みなど変更できない場合。
        """
        from ..general.color import Color
        value = Color.coerce(color)
        self._set_display_color(self._display_color_updates(value, outliner=True))
        return self

    def get_override_color(self):
        """Color: 自身のDrawing Overrides色。最終表示色ではない。

        親・表示レイヤー・選択ハイライトは合成しない。
        アトリビュートがない場合はRuntimeError。無効時はdisabledモードを返す。
        """
        from ..general.color import Color
        name = self.full_name()
        if not cmds.getAttr(name + ".overrideEnabled"):
            return Color.disabled()
        if cmds.getAttr(name + ".overrideRGBColors"):
            return Color(rgb=cmds.getAttr(name + ".overrideColorRGB")[0])
        return Color(index=cmds.getAttr(name + ".overrideColor"))

    @fast_edit
    @undo_chunk("hlibNodeOverrideColor")
    def set_override_color(self, color, *, fast=False):
        """指定形式のままDrawing Overrides色を設定する。子Shapeへは転送しない。

        Args:
            color (Color | int | Iterable[float] | None): 0～31の番号、0～1のRGB、
                または表示色オブジェクト。None/disabledはoverrideEnabled全体を
                無効化するため、表示タイプ等にも影響する。
            fast (bool): TrueはOpenMaya直接更新でUndoなし。
        Returns:
            Node: 自身。RGBモードは近似番号ではなく元のRGBを適用する。
        Raises:
            ValueError: 色の値が不正な場合。
            RuntimeError: アトリビュートがない、ロック・接続済みなど変更できない場合。
        """
        from ..general.color import Color
        value = Color.coerce(color)
        self._set_display_color(self._display_color_updates(value))
        return self

    @staticmethod
    def _display_color_updates(value, outliner=False):
        """正規化済みColorから対象アトリビュートと値の更新計画を作る。"""
        if outliner:
            updates = [] if value.mode == "disabled" else [("outlinerColor", value.rgb)]
            return updates + [("useOutlinerColor", value.mode != "disabled")]
        updates = []
        if value.mode == "index":
            updates = [("overrideColor", value.index), ("overrideRGBColors", False)]
        elif value.mode == "rgb":
            updates = [("overrideColorRGB", value.rgb), ("overrideRGBColors", True)]
        return updates + [("overrideEnabled", value.mode != "disabled")]

    def _prepare_display_color(self, updates):
        """全アトリビュートの存在・書込み可否を検証してPlugと値の計画を返す。"""
        from .._core.fastWrite import writable
        if not self.is_valid():
            raise RuntimeError("Cannot color an invalid node")
        if cmds.lockNode(self.full_name(), query=True, lock=True)[0]:
            raise RuntimeError("Cannot color a locked node: " + self.full_name())
        if any(not cmds.objExists(self.full_name() + "." + name) for name, _ in updates):
            raise RuntimeError("Node does not have the requested display color attributes")
        plugs = [(self.plug(name), value) for name, value in updates]
        for plug, value in plugs:
            writable(plug.mplug())
            if isinstance(value, tuple):
                for child in plug.children():
                    writable(child.mplug())
        return plugs

    @staticmethod
    def _apply_display_color(plugs):
        """検証済みの計画を現在のfastモードで適用する。実行時失敗は伝播する。"""
        for plug, value in plugs:
            if isinstance(value, tuple):
                set_attr(plug.full_name(), *value, type="float3")
            else:
                set_attr(plug.full_name(), value)

    def _set_display_color(self, updates):
        """単体の表示色を全アトリビュート検証後に反映する。"""
        self._apply_display_color(self._prepare_display_color(updates))

    @classmethod
    @undo_chunk("hlib.nodes.node.create")
    def create(cls, type, **kwargs):
        """ノードを作成し、対応する hlib wrapper として返す。

        Args:
            type (str): Maya の nodeType 名。
            **kwargs: ``maya.cmds.createNode`` に渡すキーワード引数。``parent``/``p`` は
                Node・Plug・Component・MObject・MDagPath・MPlug も受け付ける。

        Returns:
            Node: 作成したノードに対応する wrapper。

        Raises:
            ValueError: type が空文字列または文字列以外の場合、または parent が
                削除済みの対象の場合。
            TypeError: parent が対応しない型の場合。
            RuntimeError: parent の名前を解決できない場合、または Maya が作成を拒否した場合。

        ``parent`` はノードが必要な引数として ``hlib._core.coerce.to_node_name`` で
        所有ノードの完全パスへ変換する。Plug・MPlug・``"node.attribute"`` は所有ノード、
        Component は所有シェイプを親にする(シェイプを親にした場合の配置は
        ``maya.cmds.createNode`` と同じ)。
        """
        from .._core.coerce import to_node_name

        if not isinstance(type, str) or not type:
            raise ValueError("type must be a non-empty string")
        from ..general import Plugin
        Plugin.ensure_node_plugin(type)
        for key in ("parent", "p"):
            if kwargs.get(key) is not None:
                kwargs[key] = to_node_name(kwargs[key])
        created_name = cmds.createNode(type, **kwargs)
        return cls(created_name)

    def __new__(cls, node, *args, **kwargs):
        """ノード型の登録情報に従ってラッパーを割り当てる。

        入力を一度だけ解決する。Nodeは登録済みの型を自動選択する。
        具体的なクラスを指定した場合は、そのクラスの派生型以外を拒否する。

        Args:
            node (str | Node | Plug | Component | om2.MObject | om2.MDagPath | om2.MPlug):
                対象ノードの名前、hlib のラッパー、または Maya API 2.0 オブジェクト。
                Plug・MPlug は所有ノード、Component は所有シェイプを指す。
            *args (object): 選んだクラスの ``__init__`` へ渡す位置引数。
            **kwargs (object): 選んだクラスの ``__init__`` へ渡すキーワード引数。

        Returns:
            Node: 登録済みの適合クラスのインスタンス。

        Raises:
            TypeError: ノード入力が対応しない型の場合。
            ValueError: アトリビュートが ``deleteAttr`` で削除済みの Plug・MPlug の場合
                (``DeletedAttributeError``。RuntimeError の派生でもある)。
            RuntimeError: ノードを解決できない場合。
        """
        registry = cls._registry
        if registry is None:
            return super().__new__(cls)
        # 入力の解決(名前の検索など)は1回だけ行い、結果を __init__ へ引き継ぐ。
        resolved = _resolve_node(node)
        resolved_class = registry.wrapper_class(om2.MFnDependencyNode(resolved[0]).typeName)
        if cls is not Node and not issubclass(resolved_class, cls):
            raise TypeError("{} requires a compatible node, got {}".format(cls.__name__, resolved_class.__name__))
        instance = super().__new__(resolved_class)
        instance._pending_resolution = resolved
        return instance

    def __init__(self, node):
        """ノード入力を解決し、MObject と必要に応じた MDagPath を保持する。

        既存の Node を渡した場合は、同じ MObject と DAG パス(インスタンス)を
        指す新しいラッパーになる。

        Args:
            node (str | Node | Plug | Component | om2.MObject | om2.MDagPath | om2.MPlug):
                対象ノードの名前、hlib のラッパー、または Maya API 2.0 オブジェクト。
                Plug・MPlug は所有ノード、Component は所有シェイプを指す。

        Returns:
            None: 値を返さない。

        Raises:
            TypeError: 対応しないノード入力型の場合。
            ValueError: アトリビュートが ``deleteAttr`` で削除済みの Plug・MPlug の場合
                (``DeletedAttributeError``。RuntimeError の派生でもある)。
            RuntimeError: ノード名を解決できない場合。
        """
        # __new__ が解決済みの結果を引き継いだ場合は、同じ入力を再び解決しない。
        resolved = self.__dict__.pop("_pending_resolution", None)
        if resolved is None:
            self._mobject = None
            self._dag_path = None
            self._handle = None
            self._resolve(node)
            return
        self._mobject, self._dag_path = resolved
        # 有効性の判定は名前の取得のたびに行うため、ハンドルは一度だけ作って再利用する。
        self._handle = om2.MObjectHandle(self._mobject)
        self._identity_hash = self._handle.hashCode()

    def _resolve(self, node):
        """ノードを表す入力を内部 API オブジェクトへ変換する。

        Args:
            node (str | Node | Plug | Component | om2.MObject | om2.MDagPath | om2.MPlug):
                対象ノードを表す入力(_resolve_node と同じ)。

        Returns:
            None: 値を返さない。

        Raises:
            TypeError: 対応しないノード入力型の場合。
            ValueError: アトリビュートが ``deleteAttr`` で削除済みの Plug・MPlug の場合
                (``DeletedAttributeError``。RuntimeError の派生でもある)。
            RuntimeError: ノード名を解決できない場合。
        """
        self._mobject, self._dag_path = _resolve_node(node)
        # 有効性の判定は名前の取得のたびに行うため、ハンドルは一度だけ作って再利用する。
        self._handle = om2.MObjectHandle(self._mobject)
        self._identity_hash = self._handle.hashCode()
        self._fn_cache = None

    def _dependency_fn(self):
        """保持するノードの MFnDependencyNode を返す(作成は初回の1回だけ)。

        名前・アトリビュートの問い合わせのたびに関数セットを作り直さないためのキャッシュ。
        ノードが有効(:meth:`is_valid`)であることを呼び出し側で確かめてから使う。

        Returns:
            om2.MFnDependencyNode: このノードの関数セット。
        """
        fn = self._fn_cache
        if fn is None:
            fn = self._fn_cache = om2.MFnDependencyNode(self._mobject)
        return fn

    def _current_dag_path(self):
        """保持パスを返す。消失したインスタンスを別パスへ切り替えない。

        Returns:
            om2.MDagPath | None: 保持しているパス。非DAGはNone。
        Raises:
            RuntimeError: 保持しているDAGインスタンスが削除された場合。
        """
        dag_path = self._dag_path
        if dag_path is not None and not dag_path.isValid():
            raise RuntimeError("The referenced DAG instance no longer exists")
        return dag_path

    def __hash__(self):
        """生成時のMayaハンドルのハッシュを返す。改名・削除後も変化しない。"""
        return self._identity_hash

    def __eq__(self, other):
        """生存中の同じ対象を比較する。DAGはインスタンスのパスも区別する。"""
        if not isinstance(other, Node):
            return NotImplemented
        if not self.is_alive() or not other.is_alive():
            return False
        if self._dag_path is not None and other._dag_path is not None:
            return self._dag_path == other._dag_path
        return self._mobject == other._mobject

    def same_node(self, other):
        """別インスタンスも含め、同じ生存中のMayaノードを指すか返す。"""
        return (isinstance(other, Node) and self.is_alive() and other.is_alive()
                and self._mobject == other._mobject)

    def same_instance(self, other):
        """同じ生存中のDAGインスタンスか返す。非DAGノードはFalse。"""
        return (isinstance(other, Node) and self._dag_path is not None
                and other._dag_path is not None and self == other)

    def is_valid(self):
        """Maya シーン上でノードが有効か判定する。

        Returns:
            bool: ノードハンドルが有効な場合は ``True``。
        """
        handle = self._handle
        return handle is not None and handle.isValid()

    def is_alive(self):
        """ノードの Maya オブジェクトがメモリ上に生存しているか判定する。

        Returns:
            bool: MObjectHandle.isAlive() の結果。Undo キューに保持された削除済みノードも生存と判定される場合がある。
        """
        handle = self._handle
        return handle is not None and handle.isAlive()

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

    def type_id(self):
        """Maya の内部 typeId を整数で返す。

        同一 Maya セッション内でノード型を高速に比較する用途に使う。
        プラグインの版数や環境によって値が変わりうるため、永続化には向かない。

        Returns:
            int: MTypeId の数値表現。
        """
        return om2.MFnDependencyNode(self._mobject).typeId.id()

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
        return node_type in (cmds.nodeType(self.full_name(), inherited=True) or [])

    def is_locked(self):
        """ノード自体がロックされているか判定する。

        アトリビュート単位のロックは Plug.is_locked() を参照する。

        Returns:
            bool: ロックされている場合は True。
        """
        return om2.MFnDependencyNode(self._mobject).isLocked

    def is_referenced(self):
        """ノードが参照ファイルから読み込まれたものか判定する。

        Returns:
            bool: 参照由来の場合は True。
        """
        return om2.MFnDependencyNode(self._mobject).isFromReferencedFile

    def is_ancestor_of(self, other):
        """other が自身の DAG 階層上の子孫か判定する。

        Args:
            other (Node | str | Plug | Component | om2.MObject | om2.MDagPath | om2.MPlug):
                判定対象のノード。Plug は所有ノード、Component は所有シェイプとして扱う。

        Returns:
            bool: other が自身より下の階層にある場合は True。自身自身や
                非DAGノード、無効なノード、削除済みの対象(アトリビュートが削除済みの Plug・MPlug、
                削除済みのノードを指す om2 オブジェクトを含む)では False。

        Raises:
            TypeError: other が対応しない型の場合(対応する型は hlib._core.coerce.to_node を参照)。
            RuntimeError: other の名前を解決できない場合、または空の MObject・MPlug の場合。
        """
        other_node = _query_target(other)
        self_full = self.full_name()
        if other_node is None or not self_full:
            return False
        other_full = other_node.full_name()
        return other_full != self_full and other_full.startswith(self_full + "|")

    def is_parent_of(self, other):
        """other が自身の直接の子か判定する（孫以下は対象外）。

        Args:
            other (Node | str | Plug | Component | om2.MObject | om2.MDagPath | om2.MPlug):
                判定対象のノード。Plug は所有ノード、Component は所有シェイプとして扱う。

        Returns:
            bool: other が自身の直接の子の場合は True。無効なノードと削除済みの対象
                (アトリビュートが削除済みの Plug・MPlug、削除済みのノードを指す om2 オブジェクトを
                含む)では False。

        Raises:
            TypeError: other が対応しない型の場合(対応する型は hlib._core.coerce.to_node を参照)。
            RuntimeError: other の名前を解決できない場合、または空の MObject・MPlug の場合。
        """
        other_node = _query_target(other)
        self_full = self.full_name()
        if other_node is None or not self_full:
            return False
        other_full = other_node.full_name()
        parent_prefix, separator, _ = other_full.rpartition("|")
        return bool(separator) and parent_prefix == self_full

    def is_child_of(self, other):
        """other が自身の直接の親か判定する（祖父母以上は対象外）。

        Args:
            other (Node | str | Plug | Component | om2.MObject | om2.MDagPath | om2.MPlug):
                判定対象のノード。Plug は所有ノード、Component は所有シェイプとして扱う。

        Returns:
            bool: other が自身の直接の親の場合は True。無効なノードと削除済みの対象
                (アトリビュートが削除済みの Plug・MPlug、削除済みのノードを指す om2 オブジェクトを
                含む)では False。

        Raises:
            TypeError: other が対応しない型の場合(対応する型は hlib._core.coerce.to_node を参照)。
            RuntimeError: other の名前を解決できない場合、または空の MObject・MPlug の場合。
        """
        other_node = _query_target(other)
        if other_node is None:
            return False
        return other_node.is_parent_of(self)

    def attribute_count(self):
        """ノードが持つアトリビュートの総数を取得する。

        Returns:
            int: アトリビュート数。
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
        dag_path = self._current_dag_path()
        if dag_path is None:
            raise RuntimeError("DAG ノードではありません")
        if full:
            return dag_path.fullPathName()
        return dag_path.partialPathName()

    def is_root(self):
        """DAG ノードがワールド直下か判定する。

        Returns:
            bool: 保持する DAG パスの長さが1なら True。

        Raises:
            RuntimeError: DAG パスを保持していない場合。
        """
        dag_path = self._current_dag_path()
        if dag_path is None:
            raise RuntimeError("DAG ノードではありません")
        return dag_path.length() == 1

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
        from ..general import Namespace

        node_name = self.node_name()
        if ":" not in node_name:
            return Namespace(":")
        return Namespace(node_name.rsplit(":", 1)[0])

    @undo_chunk("hlibNodeDelete")
    def delete(self):
        """自身をMaya標準の規則で削除する。

        DAGの子も削除し、一回のUndoで戻せる。
        派生クラスはこのメソッドを上書きして専用の削除処理を実装できる。

        Returns:
            None: 値を返さない。

        Raises:
            RuntimeError: 対象が無効、またはMayaが削除を拒否した場合。
        """
        if not self.is_valid():
            raise RuntimeError("Cannot delete an invalid node")
        cmds.delete(self.full_name())

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
        from ..general import Namespace

        if isinstance(namespace, Namespace):
            target_namespace = namespace
        elif isinstance(namespace, str) and namespace:
            target_namespace = Namespace(namespace)
        else:
            raise ValueError("namespace must be a non-empty string")
        if not target_namespace.exists() and target_namespace.name != ":":
            target_namespace = Namespace.create(target_namespace)
        namespace_name = target_namespace.name
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
        from .._core.coerce import plug_path, unique_node_name
        from ..plugs.plug import Plug

        plugs = []
        seen = set()
        for mplug in om2.MFnDependencyNode(self._mobject).getConnections():
            for connected in mplug.connectedTo(as_source, as_destination):
                # MPlug.name() は短いノード名しか含まず、同名ノード(grp1|dup と grp2|dup)の
                # プラグを同一視してしまうため、所有ノードの一意な名前とアトリビュートパスで重複を判定する
                # (MObjectHandle.hashCode() は別ノードで衝突しうるため使わない)。
                key = (unique_node_name(connected.node()), plug_path(connected))
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
            list[Plug]: 入力元の外部プラグ。同じノードの同じアトリビュートは1件にまとめる。接続がなければ空リスト。
        """
        return self._connected_plugs(True, False, type=type)

    def outputs(self, type=None):
        """このノードから出力する接続先Plugを返す。

        Args:
            type (str | None): 指定した場合、接続先ノードの nodeType で絞り込む
                (継承チェーンも判定)。

        Returns:
            list[Plug]: 出力先の外部プラグ。同じノードの同じアトリビュートは1件にまとめる。接続がなければ空リスト。
        """
        return self._connected_plugs(False, True, type=type)

    def connections(self, type=None):
        """このノードに接続された外部Plugを返す。

        Args:
            type (str | None): 指定した場合、接続先ノードの nodeType で絞り込む
                (継承チェーンも判定)。

        Returns:
            list[Plug]: 入力元と出力先の外部プラグ。一意なプラグ名(``full_name()``)で
                重複を除外する。接続がなければ空リスト。
        """
        plugs = []
        seen = set()
        for plug in self.inputs(type=type) + self.outputs(type=type):
            if plug.full_name() in seen:
                continue
            seen.add(plug.full_name())
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
        names = cmds.listHistory(self.full_name(), future=future) or []
        result, seen = [], {self.uuid()}
        for name in names:
            node = Node(name)
            if node.uuid() in seen:
                continue
            seen.add(node.uuid())
            if type is None or node.is_type(type):
                result.append(node)
        return result

    @undo_chunk("hlibNodeResetAttrs")
    def reset_attributes(self, attributes=None):
        """指定アトリビュート、または書き込み可能なキー設定対象アトリビュートを既定値へ戻す。

        Args:
            attributes (str | Iterable[str] | None): アトリビュート名。Noneはキー設定可能な
                数値・単位・enumアトリビュートを対象とし、ロック・入力接続・非対応型は除外する。
                明示指定したアトリビュートのエラーは除外せず送出する。

        Returns:
            list[Plug]: リセットしたアトリビュート。全変更を一回のUndoにまとめる。

        Raises:
            AttributeError: 指定アトリビュートが存在しない場合。
            TypeError: 明示指定したアトリビュートがリセット非対応の場合。
            RuntimeError: 明示指定したアトリビュートがロック・接続済みなどで書き込みできない場合。
        """
        if attributes is None:
            plugs = [plug for plug in self.plugs(keyable=True, scalar=True)
                     if plug.default() is not None and not plug.is_destination()
                     and cmds.getAttr(plug.full_name(), settable=True)]
        else:
            if isinstance(attributes, str):
                attributes = [attributes]
            plugs = [self.plug(name) for name in attributes]
        for plug in plugs:
            plug.reset()
        return plugs

    @fast_edit
    @undo_chunk("hlibNodeSetAttrFlags")
    def set_attribute_flags(self, attributes, locked=None, keyable=None, channel_box=None, *, fast=False):
        """指定したアトリビュートのロック・キー設定可否・Channel Box表示をまとめて変更する。

        Args:
            fast (bool): TrueはOpenMaya直接更新（Undoなし）。既定False。
            attributes (str | Iterable[str]): アトリビュート名。選択状態やChannel Box選択は使用しない。
                複合アトリビュートの子まで変更する場合は子アトリビュート名を明示する。
            locked (bool | None): ロック状態。Noneは変更しない。
            keyable (bool | None): キー設定可否。Noneは変更しない。
            channel_box (bool | None): Channel Box表示。Noneは変更しない。
                keyable=TrueのアトリビュートはMayaの仕様により表示される。

        Returns:
            Node: 自身。全変更を一回のUndoにまとめる。

        Raises:
            AttributeError: 指定アトリビュートが存在しない場合。全アトリビュートを変更前に解決する。
            TypeError: 状態にboolまたはNone以外を指定した場合。
            RuntimeError: Mayaが変更を拒否した場合。途中の変更は自動では戻さない。

        ``fast=True`` はOpenMaya直接更新（Undoなし）。既定の ``False`` は通常処理。
        fastがbool以外ならTypeError。完了済みの直接更新は自動で戻さない。
        """
        from ..plugs.plug import Plug
        flags = Plug._validated_flags(locked, keyable, channel_box)
        if isinstance(attributes, str):
            attributes = [attributes]
        plugs = [self.plug(name) for name in attributes]
        if flags:
            for plug in plugs:
                plug.set_flags(locked=locked, keyable=keyable, channel_box=channel_box)
        return self

    def plugs(self, **kwargs):
        """ノードのアトリビュートを Plug のリストとして列挙する。

        Args:
            kwargs: ``cmds.listAttr`` にそのまま渡す追加フラグ
                (``keyable=True``、``visible=True``、``write=True`` など)。

        Returns:
            list[Plug]: 該当するアトリビュートの Plug。``cmds.listAttr`` が返す名前のうち
                実際には評価できないもの（未確保の要素を持つ配列複合アトリビュートの子など）は
                黙ってスキップする。該当なしの場合は空リスト。

        Raises:
            RuntimeError: ノードが無効な場合。
        """
        if not self.is_valid():
            raise RuntimeError("無効なノードのアトリビュートは列挙できません")
        names = cmds.listAttr(self.full_name(), **kwargs) or []
        plugs = []
        for name in names:
            try:
                plugs.append(self.plug(name))
            except (AttributeError, RuntimeError, ValueError):
                continue
        return plugs

    def aliases(self):
        """このノードのアトリビュートエイリアスを取得する。

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

        flat = cmds.aliasAttr(self.full_name(), query=True) or []
        pairs = []
        for index in range(0, len(flat), 2):
            alias_name, attribute_name = flat[index], flat[index + 1]
            # 配列要素(例: "weight[0]")は findPlug が解決できないため、
            # ブラケット付きアトリビュートパスも扱える MSelectionList 経由で解決する。
            selection = om2.MSelectionList()
            selection.add(f"{self.full_name()}.{attribute_name}")
            pairs.append((alias_name, Plug(self, selection.getPlug(0))))
        return pairs

    @undo_chunk("hlibNodeAddAttr")
    def add_attribute(
        self,
        long_name,
        attribute_type=None,
        data_type=None,
        default_value=None,
        **kwargs,
    ):
        """アトリビュートを追加し、追加したPlugを返す。

        attribute_typeがdouble2/double3/float2/float3ならXYZの子も自動作成する。
        任意構成のcompoundはMaya標準addAttrで子まで定義してからplugで取得する。

        Args:
            long_name (str): 追加するアトリビュートのロング名。
            attribute_type (str | None): addAttr の attributeType。data_type と少なくとも一方が必要。
            data_type (str | None): addAttr の dataType。
            default_value (object | None): addAttr の defaultValue。None なら指定しない。
            **kwargs (object): addAttrへ渡す長名・短名フラグ。重複指定は拒否する。

        Returns:
            Plug: 追加したアトリビュートの型に対応するプラグ。

        Raises:
            ValueError: long_name が空または文字列以外、あるいはアトリビュート型の指定がない場合。
            RuntimeError: Maya がアトリビュート追加を拒否した場合。
        """
        if not isinstance(long_name, str) or not long_name:
            raise ValueError("long_name must be a non-empty string")
        from .._core.flags import normalize_flags
        from ..cmds.addAttr import addAttr
        add_kwargs = normalize_flags("addAttr", kwargs)
        if "longName" in add_kwargs:
            raise TypeError("long_name and longName cannot be specified together")
        add_kwargs["longName"] = long_name
        if attribute_type is not None:
            if "attributeType" in add_kwargs:
                raise TypeError("Specify attribute_type or attributeType, not both")
            add_kwargs["attributeType"] = attribute_type
        if data_type is not None:
            if "dataType" in add_kwargs:
                raise TypeError("Specify data_type or dataType, not both")
            add_kwargs["dataType"] = data_type
        if default_value is not None:
            if "defaultValue" in add_kwargs:
                raise TypeError("Specify default_value or defaultValue, not both")
            add_kwargs["defaultValue"] = default_value
        if not (add_kwargs.get("attributeType") or add_kwargs.get("dataType")):
            raise ValueError("attribute_type or data_type is required")
        vector_type = add_kwargs.get("attributeType")
        if vector_type in ("double2", "double3", "float2", "float3"):
            # Mayaは子が揃うまで複合Plugを公開しないため、XYZの子も同時に作る。
            if "numberOfChildren" in add_kwargs:
                raise ValueError("Vector child count is determined by attribute_type")
            cmds.addAttr(self.full_name(), **add_kwargs)
            for axis in "XYZ"[:int(vector_type[-1])]:
                cmds.addAttr(self.full_name(), longName=long_name + axis,
                             attributeType=vector_type[:-1], parent=long_name,
                             keyable=bool(add_kwargs.get("keyable", False)))
            return self.plug(long_name)
        return addAttr(self, **add_kwargs)

    def get_extra_attributes(self, include_children=False):
        """ユーザー追加のエクストラアトリビュートを型付きPlugで取得する。

        Args:
            include_children (bool): Trueは複合アトリビュートの子も含める。

        Returns:
            list[Plug]: Mayaの列挙順のプラグ。配列はArrayPlugとして返す。
                非表示・非keyableも含む。個別取得はplug("名前")を使用する。

        Raises:
            TypeError: include_childrenがboolでない場合。
            RuntimeError: ノードが無効な場合。
        """
        if not isinstance(include_children, bool):
            raise TypeError("include_children must be a bool")
        if not self.is_valid():
            raise RuntimeError("Cannot list attributes on an invalid node")
        names = (cmds.listAttr(self.full_name(), userDefined=True) or []) if include_children else self.user_attribute_names()
        return [self.plug(name) for name in names]

    def user_attribute_names(self):
        """トップレベルのユーザー定義アトリビュート名を現在の並び順で取得する。

        複合アトリビュートの子は含まない。

        Returns:
            list[str]: ロング名のリスト。並び順は Channel Box の表示順。

        Raises:
            RuntimeError: ノードが無効な場合。
        """
        if not self.is_valid():
            raise RuntimeError("無効なノードのアトリビュートは列挙できません")
        names = cmds.listAttr(self.full_name(), userDefined=True) or []
        return [name for name in names if not self.plug(name).is_child()]

    @undo_chunk("hlibNodeMoveAttribute")
    def move_attribute_order(self, name, offset):
        """ユーザー定義アトリビュートを Channel Box 上で前後に移動する。

        Maya にはアトリビュートの並び替え API が無いため、移動元と移動先のうち手前側の
        位置から末尾までのアトリビュートをまとめて削除し、新しい順序で再作成すること
        で実現する(移動先より後ろにある、移動と無関係なアトリビュートも再作成対象に
        含まれる。数値・enum・文字列型の非複合・非配列トップレベル動的アトリビュート
        のみ対応。対応しないアトリビュートが再作成対象に含まれる場合は何も変更せず
        例外を送出する)。

        Args:
            name (str): 移動するユーザー定義アトリビュートのロング名。
            offset (int): 正の値で末尾方向、負の値で先頭方向へ移動する位置数。
                範囲を超える指定は先頭・末尾で止まる。

        Returns:
            Node: 自身。全変更を一回の Undo にまとめる。

        Raises:
            ValueError: name がトップレベルのユーザー定義アトリビュート一覧に無い場合。
            TypeError: 移動範囲に複合・配列アトリビュート、または対応しないアトリビュート型が
                含まれる場合。
            RuntimeError: ノードが無効な場合。
        """
        names = self.user_attribute_names()
        if name not in names:
            raise ValueError(f"{name} is not a top-level user-defined attribute of {self.full_name()}")
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
            self.plug(attr_name).delete_attribute(force=True)
        for info in infos:
            _create_movable_attr(self, info)
        return self

    def plug(self, name):
        """アトリビュートを扱う Plug オブジェクトを取得する。

        ノードのアトリビュート操作には、このメソッドを使用します。
        返された Plug で値の取得・設定や、ほかのプラグとの接続を行えます。

        アトリビュート名(ロング名・ショート名・エイリアス)に加え、配列要素と子アトリビュートを含むアトリビュートパス
        (``input1D[3]``、``worldMatrix[0]``、``pnts[2].pntx``、
        ``inputTarget[0].inputTargetGroup[7].inputTargetItem[6000].inputComponentsTarget``)を
        指定できる。形式は ``str(plug)`` のアトリビュート部分(``Plug.full_name()`` の ``.`` 以降)と同じ。
        配列インデックスは 0〜2147483647(``MPlug.logicalIndex()`` の範囲)で指定する。
        存在しない配列要素の Plug を取得しても要素は作られない(値によって型が変わるアトリビュートの
        評価を除き、シーンを変更しない。:doc:`/cmds_interop` を参照)。

        Args:
            name (str): アトリビュート名またはアトリビュートパス(このノード自身のアトリビュートに限る)。

        Returns:
            Plug: 解決したアトリビュートプラグ。

        Raises:
            ValueError: 空文字列または文字列以外を指定した場合。
            RuntimeError: ノードが無効な場合。アトリビュート名が配列複合アトリビュートの子を配列要素の番号なしで
                指す場合(``input3Dx`` のような maya.cmds で解決できないプラグ。
                ``input3D[0].input3Dx`` のように番号を含めて指定する)。
            AttributeError: アトリビュート・アトリビュートパスを解決できない場合。配列インデックスが
                2147483647 を超える場合(``input1D[4294967296]`` のような番号を別の要素へ
                読み替えない)も含む。
        """
        if not isinstance(name, str) or not name:
            raise ValueError("name には空でないアトリビュートパスを指定してください")
        if not self.is_valid():
            raise RuntimeError("無効なノードのアトリビュートにはアクセスできません")
        # plugs.plug ⇔ nodes の相互依存を避けるための遅延 import。inputs()/outputs() と同じ理由。
        from ..plugs.plug import Plug

        if "[" not in name:
            # 配列インデックスを含まない名前(``boundingBox.boundingBoxMin`` のような子アトリビュートの
            # パスを含む)は、従来どおり findPlug で解決する。
            try:
                mplug = om2.MFnDependencyNode(self._mobject).findPlug(name, False)
            except RuntimeError:
                mplug = None  # エイリアス名は findPlug で解決できないため、下で解決する。
            if mplug is not None:
                return Plug(self, mplug)
        from .._core.coerce import MAX_LOGICAL_INDEX, attribute_path_plug, has_out_of_range_index

        mplug = attribute_path_plug(self._mobject, name)
        if mplug is None:
            if has_out_of_range_index(name):
                raise AttributeError(
                    f"配列インデックスは 0〜{MAX_LOGICAL_INDEX} で指定してください: {self.name()}.{name}"
                )
            raise AttributeError(f"アトリビュートが見つかりません: {self.name()}.{name}")
        return Plug(self, mplug)

    def has_attribute(self, name):
        """アトリビュートパスを解決できるか判定する。

        Args:
            name (str): アトリビュート名またはアトリビュートパス。

        Returns:
            bool: アトリビュートを解決できる場合は ``True``。
        """
        try:
            self.plug(name)
        except (AttributeError, RuntimeError, ValueError):
            return False
        return True

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
        handle = self._handle
        if handle is None or not handle.isValid():
            return ""
        dag_path = self._dag_path
        if dag_path is None:
            return self._dependency_fn().name()
        if not dag_path.isValid():
            dag_path = self._current_dag_path()
        return dag_path.partialPathName()

    def full_name(self):
        """Maya の完全 DAG パスまたは DG ノード名を返す。

        Returns:
            str: 無効なノードでは空文字列。
        """
        handle = self._handle
        if handle is None or not handle.isValid():
            return ""
        dag_path = self._dag_path
        if dag_path is None:
            return self._dependency_fn().name()
        if not dag_path.isValid():
            dag_path = self._current_dag_path()
        return dag_path.fullPathName()

    def __str__(self):
        """Maya の最短一意ノード名を文字列として返す。

        maya.cmds は文字列以外の引数に ``str()`` を適用するため、Node をそのまま
        ``cmds.select(node)`` のように渡せる。呼び出すたびに再計算するため、
        名前変更・親子付け替えに追従する。

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

    def __getattr__(self, name) -> Any:
        """通常アトリビュートにない名前を Maya Plug として動的に解決する。

        静的解析では、具象クラス(BlendShape 等)のメソッドを基底の Node 型で呼んだ場合に
        Plug 型と誤判定しないよう、戻り値の注釈は Any としている。

        Args:
            name (str): 取得しようとした Python アトリビュート名。

        Returns:
            Plug: 解決した Maya アトリビュートプラグ。

        Raises:
            AttributeError: 非公開名または存在しない Maya アトリビュートを指定した場合。
                :meth:`plug` が RuntimeError にする名前(``input3Dx`` のような、配列要素の
                番号を含まない配列複合アトリビュートの子)も、``hasattr``/``getattr(node, name, default)``
                が使えるよう AttributeError にする(原因の RuntimeError を ``__cause__`` に持つ)。
            RuntimeError: ノードが無効な場合。
        """
        if name.startswith("_"):
            raise AttributeError(name)
        if not self.is_valid():
            raise RuntimeError("無効なノードのアトリビュートにはアクセスできません")
        try:
            return self.plug(name)
        except (AttributeError, RuntimeError) as error:
            raise AttributeError(f"アトリビュートが見つかりません: {self.name()}.{name}") from error




@collection_export()
@bulk_api(Node)
class Nodes(BulkCollection):
    """型を検証し、入力順のノード参照を保持するコレクション。

    同一ノード・同一DAGパスの重複だけを除外する。異なるインスタンスパスは保持する。
    コピーやスライスは参照を共有し、シーンのノードは複製しない。
    """

    item_class = Node

    def __init__(self, names=()):
        """ノード入力を解決して構築する。検索やシーン変更は行わない。

        Args:
            names (object | Iterable[object]): 名前・Node・API参照等、またはその列。
                単一の名前も受け付ける。解決は共通coerce規則に従う。
        Raises:
            TypeError: 解決結果がitem_classの派生でない場合。
            RuntimeError: 名前を解決できない、または削除済みの対象の場合。
            ValueError: 共通入力解決が不正な参照を検出した場合。
        """
        from .._core.coerce import to_node
        if isinstance(names, (str, Node)):
            names = [names]
        else:
            try:
                names = iter(names)
            except TypeError:
                names = [names]
        from .._core.coerce import node_inputs
        names = node_inputs(names)
        items, seen = [], set()
        for value in names:
            node = to_node(value)
            if not node.is_valid():
                raise RuntimeError("Cannot collect an invalid node")
            if not isinstance(node, self.item_class):
                raise TypeError(f"{type(self).__name__} requires {self.item_class.__name__}, got {type(node).__name__}")
            # 構築時だけキーを使用。以後の改名・親変更はNode参照が追跡する。
            key = (node.uuid(), node.full_name())
            if key not in seen:
                seen.add(key)
                items.append(node)
        self._items = items

    def __getitem__(self, index):
        """Node | Nodes: 単体参照または同じ具象型のスライスを返す。

        構築後に削除された参照も保持し、要素数を暗黙に変更しない。
        """
        if not isinstance(index, slice):
            return self._items[index]
        result = self.copy()
        result._items = self._items[index]
        return result

    def copy(self):
        """Nodes: 同じ参照を共有する、同じ具象型の独立した容器を返す。"""
        result = object.__new__(type(self))
        result.__dict__.update(self.__dict__)
        result._items = list(self._items)
        return result

    def names(self):
        """list[str]: 保持順の現在のノード名。"""
        return [node.name() for node in self]

    def __repr__(self):
        """str: 具象コレクション名と保持参照を表示する。"""
        return f"{type(self).__name__}({self._items!r})"

    @undo_chunk("hlibNodesDelete")
    def delete(self):
        """各ノードの専用deleteを呼び、親削除で消えた後続対象はスキップする。

        Returns:
            None: 空なら何もしない。Jointsは専用の階層・ウェイト処理を優先する。
        Raises:
            RuntimeError: 実行前に削除済みの参照がある、または削除失敗。
                途中までの変更は自動で戻さない。全体は一回のUndoで戻せる。
        """
        for index, node in enumerate(self):
            if not node.is_valid():
                raise RuntimeError(f"{type(self).__name__}.delete invalid item {index}")
        for index, node in enumerate(self):
            if node.is_valid():
                try:
                    node.delete()
                except Exception as exc:
                    raise RuntimeError(f"{type(self).__name__}.delete failed at item {index}: {exc}") from exc

    def get_override_color(self):
        """Colors: 各対象のDrawing Overrides色。無効状態も保持順で返す。"""
        from ..general.color import Colors
        return Colors(node.get_override_color() for node in self)

    def get_outliner_color(self):
        """Colors: 各対象のOutliner色。無効状態も保持順で返す。"""
        from ..general.color import Colors
        return Colors(node.get_outliner_color() for node in self)

    @fast_edit
    @undo_chunk("hlibNodesOverrideColor")
    def set_override_color(self, color, *, fast=False):
        """全対象へ同じ表示色を設定する。全対象の事前検証後に反映する。

        Args:
            color (Color | int | Iterable[float] | None): 単一色。Noneは無効化。
            fast (bool): TrueはUndoなしのAPI直接更新。既定False。
        Returns:
            Nodes: 自身。
        Raises:
            ValueError: 色の値が不正。
            RuntimeError: 対象が無効、アトリビュートがない、編集不可または更新失敗。
        """
        from ..general.color import Color
        value = Color.coerce(color)
        return self._set_colors([value] * len(self), outliner=False)

    @fast_edit
    @undo_chunk("hlibNodesOutlinerColor")
    def set_outliner_color(self, color, *, fast=False):
        """全対象へ同じOutliner色を設定する。

        Args:
            color (Color | int | Iterable[float] | None): 単一色。番号はRGBへ変換。
            fast (bool): TrueはUndoなし。既定False。
        Returns:
            Nodes: 自身。全対象の事前検証・例外規則はset_override_colorと同じ。
        """
        from ..general.color import Color
        value = Color.coerce(color)
        return self._set_colors([value] * len(self), outliner=True)

    @fast_edit
    @undo_chunk("hlibNodesOverrideColors")
    def set_override_colors(self, colors, *, fast=False):
        """保持順に一色ずつDrawing Overridesを設定する。

        Args:
            colors (Colors | Iterable): 対象数と同数のColor・番号・RGB・Noneの列。
            fast (bool): TrueはUndoなし。既定False。
        Returns:
            Nodes: 自身。
        Raises:
            ValueError: 件数不一致、不正な色、共有アトリビュートに異なる値を要求した場合。
            RuntimeError: 事前検証または反映失敗。実行時失敗の自動ロールバックはしない。
        """
        from ..general.color import Colors
        return self._set_colors(Colors(colors), outliner=False)

    @fast_edit
    @undo_chunk("hlibNodesOutlinerColors")
    def set_outliner_colors(self, colors, *, fast=False):
        """保持順に一色ずつOutliner色を設定する。

        Args:
            colors (Colors | Iterable): 対象数と同数の色指定の列。
            fast (bool): TrueはUndoなし。既定False。
        Returns:
            Nodes: 自身。事前検証・例外規則はset_override_colorsと同じ。
        """
        from ..general.color import Colors
        return self._set_colors(Colors(colors), outliner=True)

    def _set_colors(self, colors, *, outliner):
        """全色・対象を検証し、共有アトリビュートの競合を除いて更新計画を実行する。"""
        if len(colors) != len(self):
            raise ValueError("Color count must match node count")
        plans, seen = [], {}
        for index, (node, color) in enumerate(zip(self, colors)):
            try:
                updates = node._display_color_updates(color, outliner=outliner)
                plugs = node._prepare_display_color(updates)
                key = node.uuid()
                if key in seen:
                    if seen[key] != updates:
                        raise ValueError("Conflicting colors for shared instance attributes")
                    continue
                seen[key] = updates
                plans.append((index, node, plugs))
            except ValueError:
                raise
            except Exception as exc:
                raise RuntimeError(f"{type(self).__name__} color validation failed at item {index}: {exc}") from exc
        for index, node, plugs in plans:
            try:
                node._apply_display_color(plugs)
            except Exception as exc:
                raise RuntimeError(f"{type(self).__name__} color update failed at item {index}: {exc}") from exc
        return self
