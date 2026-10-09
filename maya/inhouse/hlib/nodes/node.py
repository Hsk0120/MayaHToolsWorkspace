"""Maya の依存ノードと DAG ノードを扱う基底ラッパー。"""

import contextlib
import inspect
import re
from typing import Any

import maya.api.OpenMaya as om2
import maya.cmds as cmds

from .._core.flags import flag_aliases
from .._core.flags import normalize_flags
from .._core.getterAlias import _getter_alias, _is_alias
from .._core.object import Object
from ..common._fast import fast_edit
from ..decorator import undoChunk
from ..logger import raise_with_notify

_MOVABLE_NUMERIC_TYPES = {
    om2.MFnNumericData.kBoolean: "bool",
    om2.MFnNumericData.kByte: "byte",
    om2.MFnNumericData.kShort: "short",
    om2.MFnNumericData.kInt: "long",
    om2.MFnNumericData.kLong: "long",
    om2.MFnNumericData.kFloat: "float",
    om2.MFnNumericData.kDouble: "double",
}  #: moveAttributeOrder() が再作成できる数値アトリビュート型と cmds.addAttr(attributeType=) の対応。


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
            (:class:`hlib.plugs.plug.DeletedAttributeError`。``RuntimeError`` の派生でもある)。
        RuntimeError: 名前を解決できない(存在しない、または複数の対象に一致する)場合、
            または空・無効な(削除済みの)ラッパーや om2 オブジェクトを指定した場合。
    """
    from ..plugs.plug import Plug as _InputPlug
    from ..plugs.plug import DeletedAttributeError
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
        return Node._selection_owner(selection, 0, node)
    if isinstance(node, om2.MDagPath):
        if not node.isValid() or not om2.MObjectHandle(node.node()).isValid():
            raise RuntimeError("無効な(削除済みの)MDagPath からノードは解決できません")
        dagPath = om2.MDagPath(node)
        return dagPath.node(), dagPath
    if isinstance(node, om2.MObject):
        if node.isNull():
            raise RuntimeError("空の MObject からノードは解決できません")
        if not om2.MObjectHandle(node).isValid():
            raise RuntimeError("削除済みノードの MObject からノードは解決できません")
        if not node.hasFn(om2.MFn.kDependencyNode):
            raise TypeError("MObject には依存ノードを指定してください(アトリビュート・コンポーネント・データは不可)")
        mobject = om2.MObject(node)
        dagPath = om2.MFnDagNode(mobject).getPath() if mobject.hasFn(om2.MFn.kDagNode) else None
        return mobject, dagPath
    if isinstance(node, om2.MPlug):
        if node.isNull:
            raise RuntimeError("空の MPlug からノードは解決できません")
        owner = node.node()
        # 所有ノードが有効でも、deleteAttr で削除されたアトリビュートの MPlug は削除済みの対象として扱う
        # (hlib のコマンドと同じ。所有ノードが削除済みなら下の MObject の解決で RuntimeError)。
        if om2.MObjectHandle(owner).isValid() and not _InputPlug._mplug_attribute_exists(node, owner):
            raise DeletedAttributeError("削除済みのアトリビュートの MPlug からノードは解決できません")
        return _resolve_node(owner)
    if isinstance(node, Node):
        if not node.isValid():
            raise RuntimeError("無効な(削除済みの)ノードは指定できません")
        dagPath = node._current_dag_path()
        return om2.MObject(node._mobject), om2.MDagPath(dagPath) if dagPath is not None else None
    # plugs/components は nodes を逆方向に import するため、循環回避のため遅延 import する。
    from ..components.component import Component, Components
    from ..plugs.plug import Plug

    if isinstance(node, Plug):
        error = _InputPlug._deleted_attribute_error(node)
        if error is not None:
            raise error
        return _resolve_node(node.getNode())
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
    """判定メソッド(``isParentOf`` など)の対象をノードへ解決する。

    ``hlib.nodes.Node._resolve_input`` と同じ規則で解決し、削除済みの対象(削除済みの Node、
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
    from ..plugs.plug import DeletedAttributeError

    try:
        node = Node._resolve_input(other)
    except DeletedAttributeError:
        return None
    except RuntimeError:
        if _is_deleted_api_object(other):
            return None
        raise
    return node if node.isValid() else None


def _dump_movable_attr(plug):
    """並び替え対応の単純な動的アトリビュートから再作成に必要な情報を集める。

    数値(bool/byte/short/long/float/double)、enum、文字列型の非複合・非配列
    トップレベル動的アトリビュートのみ対応する。

    Args:
        plug (Plug): ダンプ対象の動的アトリビュートプラグ。

    Returns:
        dict: addAttr() での再作成と値・状態の復元に必要な情報。

    Raises:
        TypeError: 複合・配列アトリビュート、または対応しないアトリビュート型の場合。
    """
    if plug.isArray() or plug.isCompound():
        raise TypeError(f"Cannot reorder compound or array attributes: {plug.getFullName()}")
    attr = plug.mplug().attribute()
    info = {
        "longName": plug.getLongName(),
        "niceName": plug.getNiceName(),
        "hidden": plug.isHidden(),
        "keyable": plug.isKeyable(),
        "channelBox": bool(cmds.getAttr(plug.getFullName(), channelBox=True)),
        "locked": plug.isLocked(),
        "value": plug.get(),
        "source": plug.getSourceWithConversion(),
        "destinations": plug.getDestinationsWithConversions(),
    }
    if attr.hasFn(om2.MFn.kNumericAttribute):
        numeric_type = om2.MFnNumericAttribute(attr).numericType()
        type_name = _MOVABLE_NUMERIC_TYPES.get(numeric_type)
        if type_name is None:
            raise TypeError(f"Unsupported numeric attribute type for reordering: {plug.getFullName()}")
        info["attributeType"] = type_name
        if plug.hasMin():
            info["min"] = plug.getMin()
        if plug.hasMax():
            info["max"] = plug.getMax()
        info["defaultValue"] = plug.getDefault()
    elif attr.hasFn(om2.MFn.kEnumAttribute):
        info["attributeType"] = "enum"
        info["enumName"] = cmds.attributeQuery(plug.getLongName(), node=plug.getNode().getFullName(), listEnum=True)[0]
        info["defaultValue"] = plug.getDefault()
    elif attr.hasFn(om2.MFn.kTypedAttribute) and om2.MFnTypedAttribute(attr).attrType() == om2.MFnData.kString:
        info["dataType"] = "string"
    else:
        raise TypeError(f"Unsupported attribute type for reordering: {plug.getFullName()}")
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
    if info["niceName"]:
        kwargs["niceName"] = info["niceName"]
    if "min" in info:
        kwargs["minValue"] = info["min"]
    if "max" in info:
        kwargs["maxValue"] = info["max"]
    if "enumName" in info:
        kwargs["enumName"] = info["enumName"]
    plug = node.addAttr(
        info["longName"],
        attributeType=info.get("attributeType"),
        dataType=info.get("dataType"),
        defaultValue=info.get("defaultValue"),
        **kwargs,
    )
    plug.set(info["value"])
    plug.setFlags(keyable=info["keyable"])
    if not info["keyable"]:
        plug.setFlags(channelBox=info["channelBox"])
    if info["source"] is not None:
        info["source"].connectTo(plug)
    for destination in info["destinations"]:
        plug.connectTo(destination)
    if info["locked"]:
        plug.setFlags(locked=True)
    return plug


class Node(Object):
    """Maya の依存ノード・DAG ノードを表す共通ラッパー。

    生成時は登録済みのノード型に対応するラッパーを選択する。
    ``Node(value)`` の value には名前、MObject、MDagPath に加え、既存の Node
    (同じノードを指す新しいラッパー)、Plug・MPlug(所有ノード)、
    Component・Components(所有シェイプ)も指定できる。名前が存在しない・
    複数の対象に一致する場合や、空・削除済みの対象は RuntimeError になる
    (``"bulk*"`` のように複数のノードに一致するパターンも最初の一致を返さない。
    パターンは ``hlib.ls`` を使う)。所有ノードは有効でアトリビュートだけが ``deleteAttr`` で
    削除された Plug・MPlug は ValueError(``hlib.plugs.plug.DeletedAttributeError``。
    RuntimeError の派生でもあるため、従来どおり RuntimeError としても捕捉できる)。

    インスタンス化されたノードは、指定されたインスタンスの DAG パスを保持する。
    そのインスタンスだけが削除された場合は、パスを使う操作がRuntimeErrorになる。
    別インスタンスへ暗黙に切り替えない。ノード自体の有効性はis_validで照会する。

    ``Joint("newJoint", create=True)`` 等、具体的なノードクラスでは指定名で新規作成できる。
    createはキーワード専用のboolで、既定Falseは既存対象の取得のまま。
    作成はMaya標準のcreateNodeとUndoを使用し、同名の連番・シェイプの親作成・選択は
    Mayaに従う。型を特定できない基底クラス、抽象ノード型、出力geometryが必要な
    SkinClusterは作成前に拒否する。汎用の作成はNode.create(type, name=...)を使用する。

    ``str(node)`` は maya.cmds で一意に解決できる最短名(:meth:`name`)を返すため、
    Node はそのまま ``cmds.select(node)`` のように maya.cmds へ渡せる。名前は
    呼び出すたびに再計算するため、名前変更・親子付け替えに追従する。
    削除済みのノードは空文字列になる。"""

    _registry = None  #: hlib.__init__ が構築後に注入する NodeRegistry。
    _fn_cache = None  #: _dependency_fn() が初回に作る MFnDependencyNode(ノードごとに1つ)。
    _constructor_create = True  #: geometry等の追加入力を必要としないクラスは名前だけで作成できる。

    def __new__(cls, node, *args, create=False, **kwargs):
        """ノード型の登録情報に従ってラッパーを割り当てる。

        入力を一度だけ解決する。Nodeは登録済みの型を自動選択する。
        具体的なクラスを指定した場合は、そのクラスの派生型以外を拒否する。

        Args:
            node (str | Node | Plug | Component | om2.MObject | om2.MDagPath | om2.MPlug):
                対象ノードの名前、hlib のラッパー、または Maya API 2.0 オブジェクト。
                Plug・MPlug は所有ノード、Component は所有シェイプを指す。
            *args (object): 選んだクラスの ``__init__`` へ渡す位置引数。
            create (bool): Trueなら指定名でこのクラスのMayaノードを新規作成する。
                キーワード専用。既定Falseは既存対象の取得。同名の連番はMayaに従う。
            **kwargs (object): 選んだクラスの ``__init__`` へ渡すキーワード引数。

        Returns:
            Node: 登録済みの適合クラスのインスタンス。

        Raises:
            TypeError: ノード入力が対応しない型、createがbool以外、または作成対象の
                型が一意でない・抽象型・名前だけでは初期化できない場合。
            ValueError: create=Trueの名前が空文字列、またはアトリビュートが
                ``deleteAttr`` で削除済みの Plug・MPlug の場合
                (``DeletedAttributeError``。RuntimeError の派生でもある)。
            RuntimeError: ノードを解決できない、またはMayaが作成を拒否した場合。
        """
        if type(create) is not bool:
            raise TypeError("create must be a bool")
        registry = cls._registry
        if create:
            if not isinstance(node, str):
                raise TypeError("create=True requires a node name string")
            if not node:
                raise ValueError("create=True requires a non-empty node name")
            if registry is None:
                raise TypeError("Node type registration is not initialized")
            node_type = registry._node_type_for_class(cls)
            if not cls._constructor_create:
                raise TypeError("{} cannot be initialized from an empty node; use its bind API"
                                .format(cls.__name__))
            # __init__で拒否される引数によって、ノードだけがシーンに残ることを防ぐ。
            inspect.signature(cls.__init__).bind(None, node, *args, create=create, **kwargs)
            with undoChunk("hlib.nodes.node.create"):
                node = Node._create_node_name(node_type, {"name": node}, require_creatable=True)
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

    def __init__(self, node, *, create=False):
        """ノード入力を解決し、MObject と必要に応じた MDagPath を保持する。

        既存の Node を渡した場合は、同じ MObject と DAG パス(インスタンス)を
        指す新しいラッパーになる。

        Args:
            node (str | Node | Plug | Component | om2.MObject | om2.MDagPath | om2.MPlug):
                対象ノードの名前、hlib のラッパー、または Maya API 2.0 オブジェクト。
                Plug・MPlug は所有ノード、Component は所有シェイプを指す。
            create (bool): Trueなら__new__で新規作成したノードを初期化する。
                キーワード専用。既定Falseは既存対象の取得。

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

    def __eq__(self, other):
        """生存中の同じ対象を比較する。DAGはインスタンスのパスも区別する。

        Args:
            other: 比較・演算の相手。
        """
        if not isinstance(other, Node):
            return NotImplemented
        if not self.isAlive() or not other.isAlive():
            return False
        if self._dag_path is not None and other._dag_path is not None:
            return self._dag_path == other._dag_path
        return self._mobject == other._mobject

    def __hash__(self):
        """生成時のMayaハンドルのハッシュを返す。改名・削除後も変化しない。"""
        return self._identity_hash

    def __repr__(self):
        """デバッグ用にクラス名とノード名を含む表現を返す。

        Returns:
            str: 有効なら型名とノード名、無効なら型名と invalid を含む文字列。
        """
        if self.isValid():
            return f"{type(self).__name__}({self.getName()!r})"
        return f"<{type(self).__name__} invalid>"

    def __str__(self):
        """Maya の最短一意ノード名を文字列として返す。

        maya.cmds は文字列以外の引数に ``str()`` を適用するため、Node をそのまま
        ``cmds.select(node)`` のように渡せる。呼び出すたびに再計算するため、
        名前変更・親子付け替えに追従する。

        Returns:
            str: 最短一意名。無効なノードでは空文字列。
        """
        return self.getName()

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
        if not self.isValid():
            raise RuntimeError("無効なノードのアトリビュートにはアクセスできません")
        try:
            return self.getPlug(name)
        except (AttributeError, RuntimeError) as error:
            raise AttributeError(f"アトリビュートが見つかりません: {self.getName()}.{name}") from error

    @classmethod
    @undoChunk("hlib.nodes.node.create")
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

        ``parent`` はノードが必要な引数として ``hlib.nodes.Node._input_name`` で
        所有ノードの完全パスへ変換する。Plug・MPlug・``"node.attribute"`` は所有ノード、
        Component は所有シェイプを親にする(シェイプを親にした場合の配置は
        ``maya.cmds.createNode`` と同じ)。
        """

        return cls(Node._create_node_name(type, kwargs))

    def getShadingEngines(self):
        """自身から直接接続されているShadingEngineを重複なしで返す。

        Returns:
            list[ShadingEngine]: 直接接続先。テクスチャから履歴を辿る操作ではない。
        """
        from .shadingEngine import ShadingEngine
        names = cmds.listConnections(self.getFullName(), source=False, destination=True,
                                     type="shadingEngine") or []
        return list(dict.fromkeys(ShadingEngine(name) for name in names))

    def getAssignedObjects(self):
        """接続先ShadingEngineのメンバーを重複なしで取得する。

        Returns:
            list[Node | Face]: 割り当て先オブジェクトまたはフェース。
        """
        result = []
        for group in self.getShadingEngines():
            for member in group.getMembers():
                if member not in result:
                    result.append(member)
        return result

    def getMaterials(self):
        """接続/割り当て先のサーフェスマテリアルを取得する。

        Returns:
            list[Node]: 重複なしのマテリアル。未接続のShadingEngineは除く。
        """
        result = []
        for group in self.getShadingEngines():
            material = group.getShader()
            if material is not None and material not in result:
                result.append(material)
        return result

    def sameNode(self, other):
        """別インスタンスも含め、同じ生存中のMayaノードを指すか返す。

        Args:
            other (object): 比較対象。Node 以外は False。

        Returns:
            bool: 両者が生存し、同じ Maya ノードを指す場合は True。
        """
        return (isinstance(other, Node) and self.isAlive() and other.isAlive()
                and self._mobject == other._mobject)

    def sameInstance(self, other):
        """同じ生存中のDAGインスタンスか返す。非DAGノードはFalse。

        Args:
            other (object): 比較対象。Node 以外は False。

        Returns:
            bool: 同じ生存中の DAG インスタンスの場合は True。非 DAG は False。
        """
        return (isinstance(other, Node) and self._dag_path is not None
                and other._dag_path is not None and self == other)

    def isValid(self):
        """Maya シーン上でノードが有効か判定する。

        Returns:
            bool: ノードハンドルが有効な場合は ``True``。
        """
        handle = self._handle
        return handle is not None and handle.isValid()

    @_is_alias(isValid)
    def valid(self, *args, **kwargs):
        """isValidへ委譲するis省略の判定入口。

        Args:
            *args: 判定本体へ渡す位置引数。
            **kwargs: 判定本体へ渡すキーワード引数。

        Returns:
            object: 判定本体と同じ結果。
        """
        return self.isValid(*args, **kwargs)

    def isAlive(self):
        """ノードの Maya オブジェクトがメモリ上に生存しているか判定する。

        Returns:
            bool: MObjectHandle.isAlive() の結果。Undo キューに保持された削除済みノードも生存と判定される場合がある。
        """
        handle = self._handle
        return handle is not None and handle.isAlive()

    @_is_alias(isAlive)
    def alive(self, *args, **kwargs):
        """isAliveへ委譲するis省略の判定入口。

        Args:
            *args: 判定本体へ渡す位置引数。
            **kwargs: 判定本体へ渡すキーワード引数。

        Returns:
            object: 判定本体と同じ結果。
        """
        return self.isAlive(*args, **kwargs)

    def mnode(self):
        """保持している Maya API 2.0 MObject を返す。

        Returns:
            om2.MObject | None: ラップ対象の MObject。
        """
        return self._mobject

    def getType(self):
        """Maya の nodeType 名を返す。

        Returns:
            str: 対応する Maya nodeType。
        """
        return om2.MFnDependencyNode(self._mobject).typeName

    def getTypeId(self):
        """Maya の内部 typeId を整数で返す。

        同一 Maya セッション内でノード型を高速に比較する用途に使う。
        プラグインの版数や環境によって値が変わりうるため、永続化には向かない。

        Returns:
            int: MTypeId の数値表現。
        """
        return om2.MFnDependencyNode(self._mobject).typeId.id()

    def getPluginName(self):
        """ノード型がプラグイン由来の場合、そのプラグイン名を取得する。

        Returns:
            str: プラグイン名。Maya組み込みのノード型では空文字列。
        """
        return om2.MFnDependencyNode(self._mobject).pluginName

    def getClassification(self):
        """ノード型の分類文字列を取得する。

        Returns:
            list[str]: ``cmds.getClassification`` が返す分類文字列のリスト。
                該当が無い nodeType では空リスト。
        """
        return cmds.getClassification(self.getType())

    def isType(self, node_type):
        """自身の nodeType が指定型そのもの、またはその派生型か判定する。

        ``cmds.nodeType(inherited=True)`` による継承チェーンで判定するため、
        例えば mesh ノードは ``isType("shape")`` で True になる。

        Args:
            node_type (str): 判定する Maya nodeType 名。

        Returns:
            bool: 継承チェーンに node_type が含まれる場合は True。

        Raises:
            ValueError: node_type が空文字列または文字列以外の場合。
        """
        if not isinstance(node_type, str) or not node_type:
            raise ValueError("node_type must be a non-empty string")
        if not self.isValid():
            return False
        return node_type in (cmds.nodeType(self.getFullName(), inherited=True) or [])

    def isLocked(self):
        """ノード自体がロックされているか判定する。

        アトリビュート単位のロックは Plug.isLocked() を参照する。

        Returns:
            bool: ロックされている場合は True。
        """
        return om2.MFnDependencyNode(self._mobject).isLocked

    @_is_alias(isLocked)
    def locked(self, *args, **kwargs):
        """isLockedへ委譲するis省略の判定入口。

        Args:
            *args: 判定本体へ渡す位置引数。
            **kwargs: 判定本体へ渡すキーワード引数。

        Returns:
            object: 判定本体と同じ結果。
        """
        return self.isLocked(*args, **kwargs)

    def isFromReferencedFile(self):
        """ノードが参照ファイルから読み込まれたものか判定する。

        Returns:
            bool: 参照由来の場合は True。
        """
        return om2.MFnDependencyNode(self._mobject).isFromReferencedFile

    @_is_alias(isFromReferencedFile)
    def fromReferencedFile(self, *args, **kwargs):
        """isFromReferencedFileへ委譲するis省略の判定入口。

        Args:
            *args: 判定本体へ渡す位置引数。
            **kwargs: 判定本体へ渡すキーワード引数。

        Returns:
            object: 判定本体と同じ結果。
        """
        return self.isFromReferencedFile(*args, **kwargs)

    def isAncestorOf(self, other):
        """other が自身の DAG 階層上の子孫か判定する。

        Args:
            other (Node | str | Plug | Component | om2.MObject | om2.MDagPath | om2.MPlug):
                判定対象のノード。Plug は所有ノード、Component は所有シェイプとして扱う。

        Returns:
            bool: other が自身より下の階層にある場合は True。自身自身や
                非DAGノード、無効なノード、削除済みの対象(アトリビュートが削除済みの Plug・MPlug、
                削除済みのノードを指す om2 オブジェクトを含む)では False。

        Raises:
            TypeError: other が対応しない型の場合(対応する型は hlib.nodes.Node._resolve_input を参照)。
            RuntimeError: other の名前を解決できない場合、または空の MObject・MPlug の場合。
        """
        other_node = _query_target(other)
        self_full = self.getFullName()
        if other_node is None or not self_full:
            return False
        other_full = other_node.getFullName()
        return other_full != self_full and other_full.startswith(self_full + "|")

    @_is_alias(isAncestorOf)
    def ancestorOf(self, *args, **kwargs):
        """isAncestorOfへ委譲するis省略の判定入口。

        Args:
            *args: 判定本体へ渡す位置引数。
            **kwargs: 判定本体へ渡すキーワード引数。

        Returns:
            object: 判定本体と同じ結果。
        """
        return self.isAncestorOf(*args, **kwargs)

    def isParentOf(self, other):
        """other が自身の直接の子か判定する（孫以下は対象外）。

        Args:
            other (Node | str | Plug | Component | om2.MObject | om2.MDagPath | om2.MPlug):
                判定対象のノード。Plug は所有ノード、Component は所有シェイプとして扱う。

        Returns:
            bool: other が自身の直接の子の場合は True。無効なノードと削除済みの対象
                (アトリビュートが削除済みの Plug・MPlug、削除済みのノードを指す om2 オブジェクトを
                含む)では False。

        Raises:
            TypeError: other が対応しない型の場合(対応する型は hlib.nodes.Node._resolve_input を参照)。
            RuntimeError: other の名前を解決できない場合、または空の MObject・MPlug の場合。
        """
        other_node = _query_target(other)
        self_full = self.getFullName()
        if other_node is None or not self_full:
            return False
        other_full = other_node.getFullName()
        parent_prefix, separator, _ = other_full.rpartition("|")
        return bool(separator) and parent_prefix == self_full

    @_is_alias(isParentOf)
    def parentOf(self, *args, **kwargs):
        """isParentOfへ委譲するis省略の判定入口。

        Args:
            *args: 判定本体へ渡す位置引数。
            **kwargs: 判定本体へ渡すキーワード引数。

        Returns:
            object: 判定本体と同じ結果。
        """
        return self.isParentOf(*args, **kwargs)

    def isChildOf(self, other):
        """other が自身の直接の親か判定する（祖父母以上は対象外）。

        Args:
            other (Node | str | Plug | Component | om2.MObject | om2.MDagPath | om2.MPlug):
                判定対象のノード。Plug は所有ノード、Component は所有シェイプとして扱う。

        Returns:
            bool: other が自身の直接の親の場合は True。無効なノードと削除済みの対象
                (アトリビュートが削除済みの Plug・MPlug、削除済みのノードを指す om2 オブジェクトを
                含む)では False。

        Raises:
            TypeError: other が対応しない型の場合(対応する型は hlib.nodes.Node._resolve_input を参照)。
            RuntimeError: other の名前を解決できない場合、または空の MObject・MPlug の場合。
        """
        other_node = _query_target(other)
        if other_node is None:
            return False
        return other_node.isParentOf(self)

    @_is_alias(isChildOf)
    def childOf(self, *args, **kwargs):
        """isChildOfへ委譲するis省略の判定入口。

        Args:
            *args: 判定本体へ渡す位置引数。
            **kwargs: 判定本体へ渡すキーワード引数。

        Returns:
            object: 判定本体と同じ結果。
        """
        return self.isChildOf(*args, **kwargs)

    def getAttrCount(self):
        """ノードが持つアトリビュートの総数を取得する。

        Returns:
            int: アトリビュート数。
        """
        return om2.MFnDependencyNode(self._mobject).attributeCount()

    def getPath(self, full=False):
        """DAG ノードのパス名を返す。

        Args:
            full (bool): ``True`` の場合はフルDAGパス、``False`` の場合は
                パーシャルパスを返す。

        Returns:
            str: 指定形式の DAG パス名。

        Raises:
            RuntimeError: DAG パスを保持していない場合。
        """
        dagPath = self._current_dag_path()
        if dagPath is None:
            raise RuntimeError("DAG ノードではありません")
        if full:
            return dagPath.fullPathName()
        return dagPath.partialPathName()

    def isRoot(self):
        """DAG ノードがワールド直下か判定する。

        Returns:
            bool: 保持する DAG パスの長さが1なら True。

        Raises:
            RuntimeError: DAG パスを保持していない場合。
        """
        dagPath = self._current_dag_path()
        if dagPath is None:
            raise RuntimeError("DAG ノードではありません")
        return dagPath.length() == 1

    def getNodeName(self, remove_namespace=False):
        """DAG パスを除いたノード名を返す。

        Args:
            remove_namespace (bool): ``True`` の場合はnamespaceも除外する。

        Returns:
            str: namespaceを含むノード名。``remove_namespace`` が ``True`` の場合は
                namespaceを含まないノード名。
        """
        nodeName = om2.MFnDependencyNode(self._mobject).name()
        if remove_namespace:
            nodeName = nodeName.rsplit(":", 1)[-1]
        return nodeName

    def getNamespace(self):
        """ノードが属するネームスペースを返す。

        Returns:
            Namespace: ノードが属するNamespace。
        """
        # namespaces.namespace が ..nodes を逆方向 import するため、
        # 循環回避のためここで遅延 import する（hlib で意図的な相互依存の一つ）。
        from ..common import Namespace

        nodeName = self.getNodeName()
        if ":" not in nodeName:
            return Namespace(":")
        return Namespace(nodeName.rsplit(":", 1)[0])

    @undoChunk("hlibNodeSetNamespace")
    def setNamespace(self, namespace):
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
        from ..common import Namespace

        if isinstance(namespace, Namespace):
            target_namespace = namespace
        elif isinstance(namespace, str) and namespace:
            target_namespace = Namespace(namespace)
        else:
            raise ValueError("namespace must be a non-empty string")
        if not target_namespace.exists() and target_namespace.name != ":":
            target_namespace = Namespace.create(target_namespace)
        namespace_name = target_namespace.name
        nodeName = self.getNodeName(True)
        new_name = (
            f"{namespace_name}:{nodeName}"
            if namespace_name != ":"
            else nodeName
        )
        return cmds.rename(self.getName(), new_name)

    @undoChunk("hlibNodeDelete")
    def delete(self, *, safe=False):
        """自身をMaya標準の規則で削除する。

        DAGの子も削除し、一回のUndoで戻せる。
        派生クラスはこのメソッドを上書きして専用の削除処理を実装できる。

        Args:
            safe (bool): Trueなら自身またはDAG子孫にDG接続がある場合は削除しない。
                入力・出力・message・Set/マテリアル接続を全て含む。
                Falseは従来の削除。ロック解除や例外抑制は行わない。

        Returns:
            None: 値を返さない。

        Raises:
            TypeError: safeがboolでない場合。
            RuntimeError: 対象が無効、またはMayaが削除を拒否した場合。
        """
        if type(safe) is not bool:
            raise TypeError("safe must be bool")
        if not self.isValid():
            raise RuntimeError("Cannot delete an invalid node")
        if safe and self._has_delete_connections():
            return
        cmds.delete(self.getFullName())

    @undoChunk("hlibNodeRename")
    def rename(self, name, ignoreShape=False):
        """ノード名を変更し、変更後の名前を返す。

        Args:
            name (str): 新しいノード名。
            ignoreShape (bool): ``True`` の場合はShapeの名前変更を抑制する。

        Returns:
            str: Mayaが確定した変更後のノード名。

        Raises:
            RuntimeError: ノード名を変更できない場合。
        """
        return cmds.rename(self.getName(), name, ignoreShape=ignoreShape)

    def getInputs(self, **kwargs):
        """入力側の接続を指定条件で照会する。

        Args:
            **kwargs: connectionsの絞込み・返却形式指定。方向のs/dは指定しない。

        Returns:
            list | Plug | Node | tuple | None: 通常はリスト。index指定時は一件、範囲外はNone。
        """
        return self.getConnections(True, False, **kwargs)

    def getOutputs(self, **kwargs):
        """出力側の接続を指定条件で照会する。

        Args:
            **kwargs: connectionsの絞込み・返却形式指定。方向のs/dは指定しない。

        Returns:
            list | Plug | Node | tuple | None: 通常はリスト。index指定時は一件、範囲外はNone。
        """
        return self.getConnections(False, True, **kwargs)

    @flag_aliases(idx="index")
    def getConnections(self, s=True, d=True, c=False, t=None, et=False, scn=False,
                    source=True, destination=True, connections=False,
                    type=None, exactType=False, skipConversionNodes=False,
                    asPair=False, asNode=False, index=None, pcls=None):
        """接続をPlug・Node・ペアとして照会する。

        Args:
            s (bool): 入力を含める。sourceとANDする。
            d (bool): 出力を含める。destinationとANDする。
            c (bool): ペア指定の短縮名。
            t (str | None): typeの短縮名。
            et (bool): exactTypeの短縮名。
            scn (bool): skipConversionNodesの短縮名。
            source (bool): 入力を含める。
            destination (bool): 出力を含める。
            connections (bool): 自身側と相手側のペアを返す。
            type (str | None): 接続先ノード型。
            exactType (bool): 型名の完全一致で絞る。
            skipConversionNodes (bool): unitConversion系を飛ばす。
            asPair (bool): 自身側Plugと相手側のペアを返す。
            asNode (bool): 相手側をNodeで返す。
            index (int | None): 結果の一件。範囲外はNone。 別名 ``idx`` も使用可能。
            pcls (type | None): 返すPlugクラス。
        Returns:
            list | Plug | Node | tuple | None: 条件に合う結果。
        """
        from ..plugs.plug import Plug
        pairs = []
        for mp in self._dependency_fn().getConnections():
            local = Plug(self, mp)
            pairs.extend(local.getConnections(s, d, source=source, destination=destination,
                         scn=scn or skipConversionNodes, asPair=True,
                         checkChildren=False, checkElements=False))
        return Plug._connection_results(pairs, type or t, exactType or et,
                                       asPair or c or connections, asNode, index, pcls)

    def getHistory(self, type=None, future=False):
        """構築履歴を検索し、対応するノードラッパーを返す。

        Args:
            type (str | None): 継承型を含むノード型フィルター。Noneは全型。
            future (bool): Trueは下流、Falseは上流を検索する。

        Returns:
            list[Node]: Mayaの履歴順。自身と重複を除く。該当なしなら空リスト。

        Raises:
            RuntimeError: 無効なノード、またはMayaの履歴検索が失敗した場合。
        """
        names = cmds.listHistory(self.getFullName(), future=future) or []
        result, seen = [], {self.getUuid()}
        for name in names:
            node = Node(name)
            if node.getUuid() in seen:
                continue
            seen.add(node.getUuid())
            if type is None or node.isType(type):
                result.append(node)
        return result

    @flag_aliases(attrs="attributes")
    @undoChunk("hlibNodeResetAttrs")
    def resetAttrs(self, attributes=None):
        """指定アトリビュート、または書き込み可能なキー設定対象アトリビュートを既定値へ戻す。

        Args:
            attributes (str | Iterable[str] | None): アトリビュート名。Noneはキー設定可能な
                数値・単位・enumアトリビュートを対象とし、ロック・入力接続・非対応型は除外する。
                明示指定したアトリビュートのエラーは除外せず送出する。 別名 ``attrs`` も使用可能。

        Returns:
            list[Plug]: リセットしたアトリビュート。全変更を一回のUndoにまとめる。

        Raises:
            AttributeError: 指定アトリビュートが存在しない場合。
            TypeError: 明示指定したアトリビュートがリセット非対応の場合。
            RuntimeError: 明示指定したアトリビュートがロック・接続済みなどで書き込みできない場合。
        """
        if attributes is None:
            plugs = [plug for plug in self.getPlugs(keyable=True, scalar=True)
                     if plug.getDefault() is not None and not plug.isDestination()
                     and cmds.getAttr(plug.getFullName(), settable=True)]
        else:
            if isinstance(attributes, str):
                attributes = [attributes]
            plugs = [self.getPlug(name) for name in attributes]
        for plug in plugs:
            plug.reset()
        return plugs

    @flag_aliases(attrs="attributes")
    @fast_edit
    @undoChunk("hlibNodeSetAttrFlags")
    def setAttrFlags(self, attributes, locked=None, keyable=None, channelBox=None, *, fast=False):
        """指定したアトリビュートのロック・キー設定可否・Channel Box表示をまとめて変更する。

        Args:
            fast (bool): TrueはOpenMaya直接更新（Undoなし）。既定False。
            attributes (str | Iterable[str]): アトリビュート名。選択状態やChannel Box選択は使用しない。
                複合アトリビュートの子まで変更する場合は子アトリビュート名を明示する。 別名 ``attrs`` も使用可能。
            locked (bool | None): ロック状態。Noneは変更しない。
            keyable (bool | None): キー設定可否。Noneは変更しない。
            channelBox (bool | None): Channel Box表示。Noneは変更しない。
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
        flags = Plug._validated_flags(locked, keyable, channelBox)
        if isinstance(attributes, str):
            attributes = [attributes]
        plugs = [self.getPlug(name) for name in attributes]
        if flags:
            for plug in plugs:
                plug.setFlags(locked=locked, keyable=keyable, channelBox=channelBox)
        return self

    def getPlugs(self, **kwargs):
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
        if not self.isValid():
            raise RuntimeError("無効なノードのアトリビュートは列挙できません")
        names = cmds.listAttr(self.getFullName(), **kwargs) or []
        plugs = []
        for name in names:
            try:
                plugs.append(self.getPlug(name))
            except (AttributeError, RuntimeError, ValueError):
                continue
        return plugs

    def getAliases(self):
        """このノードのアトリビュートエイリアスを取得する。

        Returns:
            list[tuple[str, Plug]]: ``(エイリアス名, 対応するPlug)`` のリスト。
                エイリアスが無ければ空リスト。

        Raises:
            RuntimeError: ノードが無効な場合。
        """
        if not self.isValid():
            raise RuntimeError("無効なノードのエイリアスは取得できません")
        # 配列・複合パスの解決はplug()へ集約し、Mayaコマンドと名前再解決を避ける。
        return [(alias, self.getPlug(name)) for alias, name in self._dependency_fn().getAliasList()]

    @undoChunk("hlibNodeAddAttr")
    def addAttr(self, longName="", type=None, subType=None, channelBox=False,
                childNames=None, childShortNames=None, childSuffixes=None,
                proxy=None, getPlug=True, **kwargs):
        """型・既定値・フラグを指定してアトリビュートを追加する。

        Args:
            longName (str): ロング名。lnまたはsnだけの指定も可能。
            type (str | None): 型名。at:/dt:接頭辞も可。省略時double。
            subType (str | None): 自動生成する子の共通型。
            channelBox (bool): チャンネルボックス表示。cbでも指定可能。
            childNames (Sequence[str] | None): 子のロング名。
            childShortNames (Sequence[str] | None): 子のショート名。
            childSuffixes (Sequence[str] | None): 親名へ付加する子の接尾辞。
            proxy (Plug | str | None): プロキシの元アトリビュート。
            getPlug (bool): 既定はTrueで追加したPlugを返す。FalseならNone。
            **kwargs: Mayaの長名・短名フラグ。値・制限は内部単位。
        Returns:
            Plug | None: 追加したPlug。getPlug=Falseを明示した場合のみNone。
        """
        from .._core.flags import normalize_flags
        from ..plugs.plug import Plug
        flags = {key: value for key, value in normalize_flags("addAttr", kwargs).items()
                 if value is not None}
        if flags.get("query") or flags.get("edit"):
            raise ValueError("addAttr supports creation only")
        if longName:
            if "longName" in flags:
                raise TypeError("Specify longName or ln, not both")
            flags["longName"] = longName
        name = flags.get("longName") or flags.get("shortName")
        if not isinstance(name, str) or not name:
            raise ValueError("Specify longName or shortName")
        show = channelBox or flags.pop("channelBox", False)
        proxy = proxy or flags.pop("proxy", None)
        if proxy is not None:
            proxy = Plug._resolve_input(proxy)
            type = proxy.getDataType()
            flags["usedAsProxy"] = True
        if type is not None:
            flags.pop("attributeType", None)
            flags.pop("dataType", None)
            prefix, separator, kind = type.partition(":")
            if separator:
                if prefix not in ("at", "dt"):
                    raise ValueError("Expected at: or dt: type prefix")
                key = "attributeType" if prefix == "at" else "dataType"
            else:
                kind = type
                key = "dataType" if kind in {
                    "string", "matrix", "stringArray", "doubleArray", "floatArray", "Int32Array",
                    "Int64Array", "vectorArray", "floatVectorArray", "pointArray", "matrixArray",
                    "mesh", "nurbsCurve", "nurbsSurface", "lattice", "componentList", "polyFaces",
                    "reflectanceRGB", "spectrumRGB",
                } else "attributeType"
            flags[key] = kind
        elif not (flags.get("attributeType") or flags.get("dataType")):
            flags["attributeType"] = "double"
        if flags.get("attributeType") and flags.get("dataType"):
            raise ValueError("Cannot specify both attributeType and dataType")
        kind = flags.get("attributeType")
        numeric = re.fullmatch(r"(double|float|long|short)([234])", kind or "")
        count = int(numeric.group(2)) if numeric else 0
        if kind == "compound" and (childNames or childShortNames or childSuffixes):
            count = flags.get("numberOfChildren") or len(childNames or childShortNames or childSuffixes)
            flags["numberOfChildren"] = count
        if numeric:
            # 固定子数型へncを渡すMayaエラーを事前検出する。
            if "numberOfChildren" in flags and flags.pop("numberOfChildren") != count:
                raise ValueError("Vector child count does not match its type")
        deferred = None
        if count or flags.get("dataType"):
            deferred = flags.pop("defaultValue", None)
        unit = {"doubleAngle": (om2.MAngle, om2.MAngle.kRadians),
                "doubleLinear": (om2.MDistance, om2.MDistance.kCentimeters),
                "time": (om2.MTime, om2.MTime.kSeconds)}.get(kind)
        if unit:
            cls, internal = unit
            for flag in ("defaultValue", "minValue", "maxValue", "softMinValue", "softMaxValue"):
                if flag in flags:
                    value = flags[flag]
                    quantity = value if isinstance(value, cls) else cls(value, internal)
                    flags[flag] = quantity.asUnits(cls.uiUnit() if cls is om2.MTime else internal)
        if count:
            suffixes = childSuffixes or ("RGBA" if flags.get("usedAsColor") else "XYZW")[:count]
            names = list(childNames or [name + suffix for suffix in suffixes])
            short_names = list(childShortNames or [])
            if len(names) != count or (short_names and len(short_names) != count):
                raise ValueError("Child name count does not match its type")
            # 子の範囲・既定値は子へ指定し、親には渡さない。
            limits = {k: flags.pop(k) for k in ("minValue", "maxValue", "softMinValue", "softMaxValue") if k in flags}
            cmds.addAttr(self.getFullName(), **flags)
            for index, child_name in enumerate(names):
                child_flags = dict(parent=name, keyable=bool(flags.get("keyable", False)))
                if short_names:
                    child_flags["shortName"] = short_names[index]
                for key, value in limits.items():
                    child_flags[key] = value[index] if isinstance(value, (tuple, list)) else value
                if deferred is not None:
                    child_flags["defaultValue"] = deferred[index] if isinstance(deferred, (tuple, list)) else deferred
                self.addAttr(child_name, subType or (numeric.group(1) if numeric else "double"),
                             getPlug=False, **child_flags)
        else:
            cmds.addAttr(self.getFullName(), **flags)
        if not getPlug and (deferred is None or count) and not show and proxy is None:
            return None
        plug = self.getPlug(name)
        if deferred is not None and not count:
            plug.set(deferred)
        if show:
            plug.setFlags(channelBox=True)
        if proxy is not None:
            proxy.connectTo(plug)
        return plug if getPlug else None

    def getExtraAttrs(self, include_children=False):
        """ユーザー追加のエクストラアトリビュートを型付きPlugで取得する。

        Args:
            include_children (bool): Trueは複合アトリビュートの子も含める。

        Returns:
            list[Plug]: Mayaの列挙順のプラグ。配列はArrayPlugとして返す。
                非表示・非keyableも含む。個別取得はplug("名前")を使用する。

        Raises:
            TypeError: include_childrenがboolでない場合。
            RuntimeError: ノードが無効な場合。またはinclude_children=Trueで、
                番号を指定しない複合配列の子が含まれる場合。
        """
        if not isinstance(include_children, bool):
            raise TypeError("include_children must be a bool")
        if not self.isValid():
            raise RuntimeError("Cannot list attributes on an invalid node")
        # 名前へ変換して再検索せず、定義から型付きPlugを作る。配列の要素は展開しない。
        from ..plugs.plug import Plug
        return [Plug(self, om2.MPlug(self._mobject, attribute))
                for attribute in self._user_attributes(include_children)]

    def getExtraAttrNames(self):
        """トップレベルのユーザー定義アトリビュート名を現在の並び順で取得する。

        複合アトリビュートの子は含まない。

        Returns:
            list[str]: ロング名のリスト。並び順はMayaへの追加順。

        Raises:
            RuntimeError: ノードが無効な場合。
        """
        if not self.isValid():
            raise RuntimeError("無効なノードのアトリビュートは列挙できません")
        return [om2.MFnAttribute(attribute).name for attribute in self._user_attributes()]

    @undoChunk("hlibNodeMoveAttribute")
    def moveAttrOrder(self, name, offset):
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
        names = self.getExtraAttrNames()
        if name not in names:
            raise ValueError(f"{name} is not a top-level user-defined attribute of {self.getFullName()}")
        old_index = names.index(name)
        new_index = max(0, min(len(names) - 1, old_index + offset))
        if new_index == old_index:
            return self
        names.remove(name)
        names.insert(new_index, name)
        window_start = min(old_index, new_index)
        to_recreate = names[window_start:]

        infos = [_dump_movable_attr(self.getPlug(attr_name)) for attr_name in to_recreate]
        for attr_name in to_recreate:
            self.getPlug(attr_name).delete(force=True)
        for info in infos:
            _create_movable_attr(self, info)
        return self

    def getPlug(self, name):
        """アトリビュートを扱う Plug オブジェクトを取得する。

        ノードのアトリビュート操作には、このメソッドを使用します。
        返された Plug で値の取得・設定や、ほかのプラグとの接続を行えます。

        アトリビュート名(ロング名・ショート名・エイリアス)に加え、配列要素と子アトリビュートを含むアトリビュートパス
        (``input1D[3]``、``worldMatrix[0]``、``pnts[2].pntx``、
        ``inputTarget[0].inputTargetGroup[7].inputTargetItem[6000].inputComponentsTarget``)を
        指定できる。形式は ``str(plug)`` のアトリビュート部分(``Plug.getFullName()`` の ``.`` 以降)と同じ。
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
        from ..plugs.plug import Plug as _InputPlug
        from ..plugs.plug import MAX_LOGICAL_INDEX
        if not isinstance(name, str) or not name:
            raise ValueError("name には空でないアトリビュートパスを指定してください")
        if not self.isValid():
            raise RuntimeError("無効なノードのアトリビュートにはアクセスできません")
        # plugs.plug ⇔ nodes の相互依存を避けるための遅延 import。inputs()/outputs() と同じ理由。
        from ..plugs.plug import Plug

        if "[" not in name:
            # 配列インデックスを含まない名前(``boundingBox.boundingBoxMin`` のような子アトリビュートの
            # パスを含む)は、従来どおり findPlug で解決する。
            try:
                mplug = self._dependency_fn().findPlug(name, False)
            except RuntimeError:
                mplug = None  # エイリアス名は findPlug で解決できないため、下で解決する。
            if mplug is not None:
                return Plug(self, mplug)

        mplug = _InputPlug._attribute_path_plug(self._mobject, name)
        if mplug is None:
            if _InputPlug._has_out_of_range_index(name):
                raise AttributeError(
                    f"配列インデックスは 0〜{MAX_LOGICAL_INDEX} で指定してください: {self.getName()}.{name}"
                )
            raise AttributeError(f"アトリビュートが見つかりません: {self.getName()}.{name}")
        return Plug(self, mplug)

    def hasAttr(self, name):
        """アトリビュートパスを解決できるか判定する。

        Args:
            name (str): アトリビュート名またはアトリビュートパス。

        Returns:
            bool: アトリビュートを解決できる場合は ``True``。
        """
        try:
            self.getPlug(name)
        except (AttributeError, RuntimeError, ValueError):
            return False
        return True

    def getUuid(self):
        """ノードの Maya UUID を返す。

        Returns:
            str | None: 有効なノードの UUID。無効な場合は ``None``。
        """
        if not self.isValid():
            return None
        return om2.MFnDependencyNode(self._mobject).uuid().asString()

    def getName(self):
        """Maya の最短一意ノード名を返す。

        Returns:
            str: 無効なノードでは空文字列。
        """
        handle = self._handle
        if handle is None or not handle.isValid():
            return ""
        dagPath = self._dag_path
        if dagPath is None:
            return self._dependency_fn().name()
        if not dagPath.isValid():
            dagPath = self._current_dag_path()
        return dagPath.partialPathName()

    def getFullName(self):
        """Maya の完全 DAG パスまたは DG ノード名を返す。

        Returns:
            str: 無効なノードでは空文字列。
        """
        handle = self._handle
        if handle is None or not handle.isValid():
            return ""
        dagPath = self._dag_path
        if dagPath is None:
            return self._dependency_fn().name()
        if not dagPath.isValid():
            dagPath = self._current_dag_path()
        return dagPath.fullPathName()

    @_getter_alias(getShadingEngines)
    def shadingEngines(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getShadingEngines(*args, **kwargs)

    @_getter_alias(getAssignedObjects)
    def assignedObjects(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getAssignedObjects(*args, **kwargs)

    @_getter_alias(getMaterials)
    def materials(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getMaterials(*args, **kwargs)

    @_getter_alias(getType)
    def type(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getType(*args, **kwargs)

    @_getter_alias(getTypeId)
    def typeId(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getTypeId(*args, **kwargs)

    @_getter_alias(getPluginName)
    def pluginName(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getPluginName(*args, **kwargs)

    @_getter_alias(getClassification)
    def classification(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getClassification(*args, **kwargs)

    @_getter_alias(getAttrCount)
    def attrCount(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getAttrCount(*args, **kwargs)

    @_getter_alias(getPath)
    def path(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getPath(*args, **kwargs)

    @_getter_alias(getNodeName)
    def nodeName(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getNodeName(*args, **kwargs)

    @_getter_alias(getNamespace)
    def namespace(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getNamespace(*args, **kwargs)

    @_getter_alias(getInputs)
    def inputs(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getInputs(*args, **kwargs)

    @_getter_alias(getOutputs)
    def outputs(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getOutputs(*args, **kwargs)

    @_getter_alias(getConnections)
    def connections(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getConnections(*args, **kwargs)

    @_getter_alias(getHistory)
    def history(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getHistory(*args, **kwargs)

    @_getter_alias(getPlugs)
    def plugs(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getPlugs(*args, **kwargs)

    @_getter_alias(getAliases)
    def aliases(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getAliases(*args, **kwargs)

    @_getter_alias(getExtraAttrs)
    def extraAttrs(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getExtraAttrs(*args, **kwargs)

    @_getter_alias(getExtraAttrNames)
    def extraAttrNames(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getExtraAttrNames(*args, **kwargs)

    @_getter_alias(getPlug)
    def plug(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getPlug(*args, **kwargs)

    @_getter_alias(getUuid)
    def uuid(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getUuid(*args, **kwargs)

    @_getter_alias(getName)
    def name(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getName(*args, **kwargs)

    @_getter_alias(getFullName)
    def fullName(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getFullName(*args, **kwargs)

    @staticmethod
    def _create_node_name(node_type, flags, *, require_creatable=False):
        """既存の作成規則でMayaノードを作り、Mayaが返した実名を取得する。

        Args:
            node_type (str): Maya nodeType名。
            flags (dict): createNodeへ渡すフラグ。parent/pを所有ノード名へ変換する。
            require_creatable (bool): Trueなら抽象型・未導入型を作成前に拒否する。

        Returns:
            str: Mayaの名前補正・連番を反映したノード名。

        Raises:
            ValueError: nodeType名が空文字列または文字列以外の場合。
            TypeError: 作成可能な具体型でない場合、またはparentが未対応型の場合。
            RuntimeError: Mayaがプラグインのロードやノード作成を拒否した場合。

        Note:
            Undoチャンクは呼出し側で管理する。既存Node.createとconstructorの
            create=Trueが同じ標準プラグイン・名前・親の処理を使う。
        """
        if not isinstance(node_type, str) or not node_type:
            raise ValueError("type must be a non-empty string")
        from ..common import Plugin
        Plugin.ensureNodePlugin(node_type)
        if require_creatable and node_type not in (cmds.allNodeTypes() or []):
            raise TypeError("create=True requires a creatable Maya nodeType: " + node_type)
        for key in ("parent", "p"):
            if flags.get(key) is not None:
                flags[key] = Node._input_name(flags[key])
        return cmds.createNode(node_type, **flags)

    def _has_delete_connections(self):
        """自身とDAG子孫のDG接続をOMで検査する。

        Returns:
            bool: 接続が一つでもあればTrue。DAG階層関係自体は接続に数えない。
        """
        pending, seen = [self.mnode()], set()
        while pending:
            obj = pending.pop()
            fn = om2.MFnDependencyNode(obj)
            key = fn.uuid().asString()
            if key in seen:
                continue
            seen.add(key)
            if len(fn.getConnections()):
                return True
            if obj.hasFn(om2.MFn.kDagNode):
                dag = om2.MFnDagNode(obj)
                pending.extend(dag.child(i) for i in range(dag.childCount()))
        return False

    @staticmethod
    def _selection_owner(selection, index, name=None):
        """MSelectionList の要素を所有するノードの MObject と DAG パスを返す。

        ノード・コンポーネントの要素は選択されたインスタンスの DAG パスを返す。
        アトリビュート(プラグ)の要素は ``MSelectionList.getDagPath()`` を使えず、選択リスト自体も
        インスタンスの情報を持たないため、インスタンス化された DAG ノードのアトリビュートは
        次の順にノード部分からインスタンスのパスを求める。

        1. name(要素を追加したときの文字列)。``|grpB|box1|boxShape.castsShadows`` は
           ``|grpB|box1|boxShape`` のインスタンスを指す。
        2. 選択文字列。``worldMatrix[1]`` のようなインスタンスごとのアトリビュートは、要素番号の
           インスタンスが選択文字列に現れる。

        ``|box1.castsShadows`` のように transform の名前でシェイプのアトリビュートを指す文字列は、
        ノード部分が指す transform のパスを所有シェイプまで伸ばす(``|box1|boxShape``)。
        どちらからも求められない場合は最初のインスタンスのパスを返す。

        Args:
            selection (om2.MSelectionList): 対象を含む選択リスト。
            index (int): 要素の位置。
            name (str | None): 要素を追加したときの文字列。分かっている場合に指定する。

        Returns:
            tuple[om2.MObject, om2.MDagPath | None]: 所有ノードの MObject と、DAG ノードで
                あれば DAG パス(DG ノードは None)。
        """
        mobject = selection.getDependNode(index)
        if not mobject.hasFn(om2.MFn.kDagNode):
            return mobject, None
        try:
            return mobject, selection.getDagPath(index)
        except (RuntimeError, TypeError):
            pass
        fn = om2.MFnDagNode(mobject)
        if fn.isInstanced():
            candidates = [name] if name else []
            candidates.extend(selection.getSelectionStrings(index))
            for text in candidates:
                # ノード名には "." を含められないため、最初の "." までがノード部分になる。
                owner = om2.MSelectionList()
                try:
                    owner.add(text.split(".", 1)[0])
                    dagPath = owner.getDagPath(0)
                except (RuntimeError, TypeError):
                    continue
                if dagPath.node() == mobject:
                    return mobject, dagPath
                # transform の名前でシェイプのアトリビュートを指す場合は、名前が指す transform の
                # インスタンスの下にある所有シェイプまでパスを伸ばす。
                for child in range(dagPath.childCount()):
                    if dagPath.child(child) == mobject:
                        dagPath.push(mobject)
                        return mobject, dagPath
        return mobject, fn.getPath()

    @staticmethod
    def _unique_node_name(mobject):
        """ノードの MObject から maya.cmds で一意に解決できる最短名を返す。

        DAG ノードは最初のインスタンスの最短一意パス(``MDagPath.partialPathName()``)、
        DG ノードはノード名を返す。``Node.getName()`` と同じ規則。

        Args:
            mobject (om2.MObject): 依存ノードの MObject。

        Returns:
            str: 最短一意名。
        """
        if mobject.hasFn(om2.MFn.kDagNode):
            return om2.MFnDagNode(mobject).getPath().partialPathName()
        return om2.MFnDependencyNode(mobject).name()

    @staticmethod
    def _mobject_name(mobject):
        """依存ノードの MObject を完全 DAG パスまたは DG ノード名へ変換する。

        Args:
            mobject (om2.MObject): 変換対象。

        Returns:
            str: 完全 DAG パス(最初のインスタンス)、または DG ノード名。

        Raises:
            ValueError: 空、または削除済みノードの MObject の場合。
            TypeError: アトリビュート・コンポーネント・データなど依存ノード以外を指す場合。
        """
        if mobject.isNull():
            raise ValueError("空の MObject は指定できません")
        if not om2.MObjectHandle(mobject).isValid():
            raise ValueError("削除済みノードの MObject は指定できません")
        if not mobject.hasFn(om2.MFn.kDependencyNode):
            raise TypeError("MObject には依存ノードを指定してください(アトリビュート・コンポーネント・データは不可)")
        if mobject.hasFn(om2.MFn.kDagNode):
            return om2.MFnDagNode(mobject).getPath().fullPathName()
        return om2.MFnDependencyNode(mobject).name()

    @staticmethod
    def _resolve_input(value):
        """対象を Node インスタンスへ変換する。

        Plug・MPlug は所有ノード、Component・Components は所有シェイプへ解決する。

        Args:
            value (Node | str | Plug | Component | Components | om2.MObject | om2.MDagPath | om2.MPlug):
                変換対象。

        Returns:
            Node: value が Node ならそのまま、Plug なら ``plug.node``、コンポーネントなら
                ``shape``。それ以外は ``Node(value)`` (Maya へ解決し、型に応じたラッパーを返す)。
                削除済みの Node と、所有ノードが削除済みの Plug・Component は例外にせずそのまま
                返す(``Node.isValid()`` が ``False``。扱いは呼び出し側で決める)。

        Raises:
            TypeError: 対応しない型の場合。
            ValueError: 所有ノードは有効で、アトリビュートが ``deleteAttr`` で削除済みの Plug・MPlug の場合
                (:class:`DeletedAttributeError`。``RuntimeError`` の派生でもある)。
            RuntimeError: 名前を解決できない(存在しない、または複数のノードに一致する)場合、
                または空・削除済みのノードを指す om2 オブジェクトの場合(``Node(value)`` と同じ)。
        """
        from .._core.object import Object as _InputObject
        from ..plugs.plug import Plug as _InputPlug
        node_class, plug_class, component_class, components_class = _InputObject._classes()
        if isinstance(value, node_class):
            return value
        if isinstance(value, plug_class):
            error = _InputPlug._deleted_attribute_error(value)
            if error is not None:
                raise error
            return value.getNode()
        if isinstance(value, (component_class, components_class)):
            return value.shape
        if isinstance(value, (str, om2.MObject, om2.MDagPath, om2.MPlug)):
            return node_class(value)
        raise _InputObject._unsupported(value)

    @staticmethod
    def _input_name(value):
        """ノードが必要な単一の引数(``parent`` など)を、所有ノードの完全パスへ変換する。

        Node._resolve_input と同じ規則で解決する(Plug・MPlug は所有ノード、Component は所有シェイプ)。
        ``"node.attribute"`` 形式の文字列も所有ノードになるため、maya.cmds のように
        プラグ名の ``parent`` が黙って無視されることはない。

        Args:
            value (str | Node | Plug | Component | om2.MObject | om2.MDagPath | om2.MPlug): 変換対象。

        Returns:
            str: 所有ノードの完全 DAG パス(DG ノードはノード名)。

        Raises:
            TypeError: 対応しない型、または Components などの複数の対象を渡した場合。
            ValueError: 空文字列、または無効な(削除済みの。アトリビュートだけが削除された Plug・MPlug を
                含む)対象の場合。
            RuntimeError: 文字列を解決できない(存在しない、または複数のノードに一致する)場合。
        """
        from .._core.object import Object as _InputObject
        # 型と有効性の検査は Object._input_name と同じ規則(TypeError / ValueError)にそろえる。
        _InputObject._input_name(value)
        return Node._resolve_input(value).getFullName()

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
        ノードが有効(:meth:`isValid`)であることを呼び出し側で確かめてから使う。

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
        dagPath = self._dag_path
        if dagPath is not None and not dagPath.isValid():
            raise RuntimeError("The referenced DAG instance no longer exists")
        return dagPath

    def _connected_plugs(self, as_source, as_destination, type=None):
        """ノードの指定方向に接続された外部Plugを収集する。

        Args:
            as_source (bool): 接続元Plugを検索対象に含めるかどうか。
            as_destination (bool): 接続先Plugを検索対象に含めるかどうか。
            type (str | None): 指定した場合、接続先ノードの nodeType が
                ``isType`` で一致するものだけに絞り込む(継承チェーンも判定)。

        Returns:
            list[Plug]: 接続先の外部Plugを重複なしで格納したリスト。
        """
        from ..plugs.plug import Plug as _InputPlug
        # plugs.plug が ..nodes.node を逆方向 import するため、
        # 循環回避のためここで遅延 import する（hlib で意図的な相互依存の一つ）。
        from ..plugs.plug import Plug

        plugs = []
        seen = set()
        for mplug in om2.MFnDependencyNode(self._mobject).getConnections():
            for connected in mplug.connectedTo(as_source, as_destination):
                # MPlug.name() は短いノード名しか含まず、同名ノード(grp1|dup と grp2|dup)の
                # プラグを同一視してしまうため、所有ノードの一意な名前とアトリビュートパスで重複を判定する
                # (MObjectHandle.hashCode() は別ノードで衝突しうるため使わない)。
                key = (Node._unique_node_name(connected.getNode()), _InputPlug._plug_path(connected))
                if key in seen:
                    continue
                node = Node(connected.getNode())
                if type is not None and not node.isType(type):
                    continue
                seen.add(key)
                plugs.append(Plug(node, connected))
        return plugs

    @staticmethod
    def _add_attribute(target, **kwargs):
        """Maya形式のフラグで追加し、Plugを返す共通実装。

        Args:
            target (str | Node | Plug): 操作対象。
            **kwargs (object): 正規化済みのMaya長名フラグ。
        Returns:
            Plug: 追加した参照。
        Raises:
            ValueError: 照会・編集、または名前の指定が不正な場合。
            RuntimeError: Mayaが追加を拒否した場合。
        """
        from .._core.object import Object as _InputObject
        from ..plugs.plug import Plug as _InputPlug

        if kwargs.get("query") or kwargs.get("edit"):
            raise ValueError("addAttr supports creation only")
        name = _InputObject._input_name(target)
        if (
            not kwargs.get("query")
            and "." not in name
            and not (kwargs.get("longName") or kwargs.get("shortName"))
        ):
            raise ValueError("Specify longName or shortName")
        cmds.addAttr(name, **kwargs)
        if "." in name:
            return _InputPlug._resolve_input(name)
        attribute = kwargs.get("longName") or kwargs.get("shortName")
        if not attribute:
            raise ValueError("Specify longName or shortName")
        return Node._resolve_input(target).getPlug(attribute)

    def _user_attributes(self, include_children=False):
        """動的アトリビュートの定義を追加順に列挙する。

        Args:
            include_children (bool): Trueなら複合型の子の定義も含める。

        Yields:
            om2.MObject: アトリビュート定義。配列要素の取得・作成は行わない。
        """
        fn = self._dependency_fn()
        for index in range(fn.attributeCount()):
            attribute = fn.attribute(index)
            definition = om2.MFnAttribute(attribute)
            if definition.dynamic and (include_children or definition.parent.isNull()):
                yield attribute


class _PerItemOnly:
    """継承した一括入口も隠し、callEachからの要素別指定だけを許可する。"""

    def __init__(self, name):
        """直接呼び出しを禁止するメソッド名を保持する。

        Args:
            name (str): 要素別の引数を必要とする単数メソッド名。
        """
        self._name = name

    def __get__(self, instance, owner=None):
        """クラス・インスタンスのどちらからも直接取得を拒否する。

        Args:
            instance: 取得元のインスタンス。クラスから取得する場合はNone。
            owner: 取得元のクラス。

        Raises:
            AttributeError: 要素別の引数指定が必要な場合。
        """
        raise AttributeError(f"{self._name} requires callEach with per-item arguments")


class Nodes:
    """型を検証し、入力順のノード参照を保持するコレクション。

    同一ノード・同一DAGパスの重複だけを除外する。異なるインスタンスパスは保持する。
    コピーやスライスは参照を共有し、シーンのノードは複製しない。
    """

    item_class = Node

    _bulk_returns = {
        "getShadingEngines": "list",
        "shadingEngines": "list",
        "getAssignedObjects": "list",
        "assignedObjects": "list",
        "getMaterials": "list",
        "materials": "list",
        "sameNode": "list",
        "sameInstance": "list",
        "isValid": "list",
        "valid": "list",
        "isAlive": "list",
        "alive": "list",
        "mnode": "list",
        "getType": "list",
        "type": "list",
        "getTypeId": "list",
        "typeId": "list",
        "getPluginName": "list",
        "pluginName": "list",
        "getClassification": "list",
        "classification": "list",
        "isType": "list",
        "isLocked": "list",
        "locked": "list",
        "isFromReferencedFile": "list",
        "fromReferencedFile": "list",
        "isAncestorOf": "list",
        "ancestorOf": "list",
        "isParentOf": "list",
        "parentOf": "list",
        "isChildOf": "list",
        "childOf": "list",
        "getAttrCount": "list",
        "attrCount": "list",
        "getPath": "list",
        "path": "list",
        "isRoot": "list",
        "getNodeName": "list",
        "nodeName": "list",
        "getNamespace": "list",
        "namespace": "list",
        "rename": "list",
        "getInputs": "list",
        "inputs": "list",
        "getOutputs": "list",
        "outputs": "list",
        "getConnections": "list",
        "connections": "list",
        "getHistory": "list",
        "history": "list",
        "resetAttrs": "list",
        "getPlugs": "list",
        "plugs": "list",
        "getAliases": "list",
        "aliases": "list",
        "addAttr": "list",
        "getExtraAttrs": "list",
        "extraAttrs": "list",
        "getExtraAttrNames": "list",
        "extraAttrNames": "list",
        "getPlug": "list",
        "plug": "list",
        "hasAttr": "list",
        "getUuid": "list",
        "uuid": "list",
        "getName": "list",
        "name": "list",
        "getFullName": "list",
        "fullName": "list",
        "delete": "self",
        "setNamespace": "self",
        "setAttrFlags": "self",
        "moveAttrOrder": "self",
    }
    _bulk_methods = {
        "getShadingEngines": Node.getShadingEngines,
        "shadingEngines": Node.shadingEngines,
        "getAssignedObjects": Node.getAssignedObjects,
        "assignedObjects": Node.assignedObjects,
        "getMaterials": Node.getMaterials,
        "materials": Node.materials,
        "sameNode": Node.sameNode,
        "sameInstance": Node.sameInstance,
        "isValid": Node.isValid,
        "valid": Node.valid,
        "isAlive": Node.isAlive,
        "alive": Node.alive,
        "mnode": Node.mnode,
        "getType": Node.getType,
        "type": Node.type,
        "getTypeId": Node.getTypeId,
        "typeId": Node.typeId,
        "getPluginName": Node.getPluginName,
        "pluginName": Node.pluginName,
        "getClassification": Node.getClassification,
        "classification": Node.classification,
        "isType": Node.isType,
        "isLocked": Node.isLocked,
        "locked": Node.locked,
        "isFromReferencedFile": Node.isFromReferencedFile,
        "fromReferencedFile": Node.fromReferencedFile,
        "isAncestorOf": Node.isAncestorOf,
        "ancestorOf": Node.ancestorOf,
        "isParentOf": Node.isParentOf,
        "parentOf": Node.parentOf,
        "isChildOf": Node.isChildOf,
        "childOf": Node.childOf,
        "getAttrCount": Node.getAttrCount,
        "attrCount": Node.attrCount,
        "getPath": Node.getPath,
        "path": Node.path,
        "isRoot": Node.isRoot,
        "getNodeName": Node.getNodeName,
        "nodeName": Node.nodeName,
        "getNamespace": Node.getNamespace,
        "namespace": Node.namespace,
        "rename": Node.rename,
        "getInputs": Node.getInputs,
        "inputs": Node.inputs,
        "getOutputs": Node.getOutputs,
        "outputs": Node.outputs,
        "getConnections": Node.getConnections,
        "connections": Node.connections,
        "getHistory": Node.getHistory,
        "history": Node.history,
        "resetAttrs": Node.resetAttrs,
        "getPlugs": Node.getPlugs,
        "plugs": Node.plugs,
        "getAliases": Node.getAliases,
        "aliases": Node.aliases,
        "addAttr": Node.addAttr,
        "getExtraAttrs": Node.getExtraAttrs,
        "extraAttrs": Node.extraAttrs,
        "getExtraAttrNames": Node.getExtraAttrNames,
        "extraAttrNames": Node.extraAttrNames,
        "getPlug": Node.getPlug,
        "plug": Node.plug,
        "hasAttr": Node.hasAttr,
        "getUuid": Node.getUuid,
        "uuid": Node.uuid,
        "getName": Node.getName,
        "name": Node.name,
        "getFullName": Node.getFullName,
        "fullName": Node.fullName,
        "delete": Node.delete,
        "setNamespace": Node.setNamespace,
        "setAttrFlags": Node.setAttrFlags,
        "moveAttrOrder": Node.moveAttrOrder,
    }
    _bulk_per_item_only = frozenset()
    _bulk_undo = True

    def __init__(self, names=()):
        """ノード入力を解決して構築する。検索やシーン変更は行わない。

        Args:
            names (object | Iterable[object]): 名前・Node・API参照等、またはその列。
                単一の名前も受け付ける。解決はNodesの共通入力規則に従う。
        Raises:
            TypeError: 解決結果がitem_classの派生でない場合。
            RuntimeError: 名前を解決できない、または削除済みの対象の場合。
            ValueError: 共通入力解決が不正な参照を検出した場合。
        """
        if isinstance(names, (str, Node)):
            names = [names]
        else:
            try:
                names = iter(names)
            except TypeError:
                names = [names]
        names = Nodes._resolve_inputs(names)
        items, seen = [], set()
        for value in names:
            node = Node._resolve_input(value)
            if not node.isValid():
                raise RuntimeError("Cannot collect an invalid node")
            if not isinstance(node, self.item_class):
                raise TypeError(f"{type(self).__name__} requires {self.item_class.__name__}, got {type(node).__name__}")
            # 構築時だけキーを使用。以後の改名・親変更はNode参照が追跡する。
            key = (node.getUuid(), node.getFullName())
            if key not in seen:
                seen.add(key)
                items.append(node)
        self._items = items

    def __iter__(self):
        """保持順に要素を反復する。

        Returns:
            Iterator: 保持している要素のイテレータ。
        """
        return iter(self._items)

    def __len__(self):
        """保持要素数。

        Returns:
            int: 保持要素数。
        """
        return len(self._items)

    def __getitem__(self, index):
        """Node | Nodes: 単体参照または同じ具象型のスライスを返す。

        構築後に削除された参照も保持し、要素数を暗黙に変更しない。

        Args:
            index: 対象要素の番号または探索開始番号。
        """
        if not isinstance(index, slice):
            return self._items[index]
        result = self.copy()
        result._items = self._items[index]
        return result

    def __repr__(self):
        """具象コレクション名と保持参照を表示する。

        Returns:
            str: 具象コレクション名と保持参照を表示する。
        """
        return f"{type(self).__name__}({self._items!r})"

    def getShadingEngines(self, *args, **kwargs):
        """各要素のgetShadingEnginesを同じ引数で呼び、保持順の戻り値リストを返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            list: 保持順の戻り値リスト。
        """
        return self._dispatch_shared("getShadingEngines", args, kwargs)

    getShadingEngines.__signature__ = inspect.signature(Node.getShadingEngines)

    def getAssignedObjects(self, *args, **kwargs):
        """各要素のgetAssignedObjectsを同じ引数で呼び、保持順の戻り値リストを返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            list: 保持順の戻り値リスト。
        """
        return self._dispatch_shared("getAssignedObjects", args, kwargs)

    getAssignedObjects.__signature__ = inspect.signature(Node.getAssignedObjects)

    def getMaterials(self, *args, **kwargs):
        """各要素のgetMaterialsを同じ引数で呼び、保持順の戻り値リストを返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            list: 保持順の戻り値リスト。
        """
        return self._dispatch_shared("getMaterials", args, kwargs)

    getMaterials.__signature__ = inspect.signature(Node.getMaterials)

    def sameNode(self, *args, **kwargs):
        """各要素のsameNodeを同じ引数で呼び、保持順の戻り値リストを返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            list: 保持順の戻り値リスト。
        """
        return self._dispatch_shared("sameNode", args, kwargs)

    sameNode.__signature__ = inspect.signature(Node.sameNode)

    def sameInstance(self, *args, **kwargs):
        """各要素のsameInstanceを同じ引数で呼び、保持順の戻り値リストを返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            list: 保持順の戻り値リスト。
        """
        return self._dispatch_shared("sameInstance", args, kwargs)

    sameInstance.__signature__ = inspect.signature(Node.sameInstance)

    def isValid(self, *args, **kwargs):
        """各要素のisValidを同じ引数で呼び、保持順の戻り値リストを返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            list: 保持順の戻り値リスト。
        """
        return self._dispatch_shared("isValid", args, kwargs)

    isValid.__signature__ = inspect.signature(Node.isValid)

    @_is_alias(isValid)
    def valid(self, *args, **kwargs):
        """isValidへ委譲するis省略の判定入口。

        Args:
            *args: 判定本体へ渡す位置引数。
            **kwargs: 判定本体へ渡すキーワード引数。

        Returns:
            object: 判定本体と同じ結果。
        """
        return self.isValid(*args, **kwargs)

    def isAlive(self, *args, **kwargs):
        """各要素のisAliveを同じ引数で呼び、保持順の戻り値リストを返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            list: 保持順の戻り値リスト。
        """
        return self._dispatch_shared("isAlive", args, kwargs)

    isAlive.__signature__ = inspect.signature(Node.isAlive)

    @_is_alias(isAlive)
    def alive(self, *args, **kwargs):
        """isAliveへ委譲するis省略の判定入口。

        Args:
            *args: 判定本体へ渡す位置引数。
            **kwargs: 判定本体へ渡すキーワード引数。

        Returns:
            object: 判定本体と同じ結果。
        """
        return self.isAlive(*args, **kwargs)

    def mnode(self, *args, **kwargs):
        """各要素のmnodeを同じ引数で呼び、保持順の戻り値リストを返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            list: 保持順の戻り値リスト。
        """
        return self._dispatch_shared("mnode", args, kwargs)

    mnode.__signature__ = inspect.signature(Node.mnode)

    def getType(self, *args, **kwargs):
        """各要素のgetTypeを同じ引数で呼び、保持順の戻り値リストを返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            list: 保持順の戻り値リスト。
        """
        return self._dispatch_shared("getType", args, kwargs)

    getType.__signature__ = inspect.signature(Node.getType)

    def getTypeId(self, *args, **kwargs):
        """各要素のgetTypeIdを同じ引数で呼び、保持順の戻り値リストを返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            list: 保持順の戻り値リスト。
        """
        return self._dispatch_shared("getTypeId", args, kwargs)

    getTypeId.__signature__ = inspect.signature(Node.getTypeId)

    def getPluginName(self, *args, **kwargs):
        """各要素のgetPluginNameを同じ引数で呼び、保持順の戻り値リストを返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            list: 保持順の戻り値リスト。
        """
        return self._dispatch_shared("getPluginName", args, kwargs)

    getPluginName.__signature__ = inspect.signature(Node.getPluginName)

    def getClassification(self, *args, **kwargs):
        """各要素のgetClassificationを同じ引数で呼び、保持順の戻り値リストを返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            list: 保持順の戻り値リスト。
        """
        return self._dispatch_shared("getClassification", args, kwargs)

    getClassification.__signature__ = inspect.signature(Node.getClassification)

    def isType(self, *args, **kwargs):
        """各要素のisTypeを同じ引数で呼び、保持順の戻り値リストを返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            list: 保持順の戻り値リスト。
        """
        return self._dispatch_shared("isType", args, kwargs)

    isType.__signature__ = inspect.signature(Node.isType)

    def isLocked(self, *args, **kwargs):
        """各要素のisLockedを同じ引数で呼び、保持順の戻り値リストを返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            list: 保持順の戻り値リスト。
        """
        return self._dispatch_shared("isLocked", args, kwargs)

    isLocked.__signature__ = inspect.signature(Node.isLocked)

    @_is_alias(isLocked)
    def locked(self, *args, **kwargs):
        """isLockedへ委譲するis省略の判定入口。

        Args:
            *args: 判定本体へ渡す位置引数。
            **kwargs: 判定本体へ渡すキーワード引数。

        Returns:
            object: 判定本体と同じ結果。
        """
        return self.isLocked(*args, **kwargs)

    def isFromReferencedFile(self, *args, **kwargs):
        """各要素のisFromReferencedFileを同じ引数で呼び、保持順の戻り値リストを返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            list: 保持順の戻り値リスト。
        """
        return self._dispatch_shared("isFromReferencedFile", args, kwargs)

    isFromReferencedFile.__signature__ = inspect.signature(Node.isFromReferencedFile)

    @_is_alias(isFromReferencedFile)
    def fromReferencedFile(self, *args, **kwargs):
        """isFromReferencedFileへ委譲するis省略の判定入口。

        Args:
            *args: 判定本体へ渡す位置引数。
            **kwargs: 判定本体へ渡すキーワード引数。

        Returns:
            object: 判定本体と同じ結果。
        """
        return self.isFromReferencedFile(*args, **kwargs)

    def isAncestorOf(self, *args, **kwargs):
        """各要素のisAncestorOfを同じ引数で呼び、保持順の戻り値リストを返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            list: 保持順の戻り値リスト。
        """
        return self._dispatch_shared("isAncestorOf", args, kwargs)

    isAncestorOf.__signature__ = inspect.signature(Node.isAncestorOf)

    @_is_alias(isAncestorOf)
    def ancestorOf(self, *args, **kwargs):
        """isAncestorOfへ委譲するis省略の判定入口。

        Args:
            *args: 判定本体へ渡す位置引数。
            **kwargs: 判定本体へ渡すキーワード引数。

        Returns:
            object: 判定本体と同じ結果。
        """
        return self.isAncestorOf(*args, **kwargs)

    def isParentOf(self, *args, **kwargs):
        """各要素のisParentOfを同じ引数で呼び、保持順の戻り値リストを返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            list: 保持順の戻り値リスト。
        """
        return self._dispatch_shared("isParentOf", args, kwargs)

    isParentOf.__signature__ = inspect.signature(Node.isParentOf)

    @_is_alias(isParentOf)
    def parentOf(self, *args, **kwargs):
        """isParentOfへ委譲するis省略の判定入口。

        Args:
            *args: 判定本体へ渡す位置引数。
            **kwargs: 判定本体へ渡すキーワード引数。

        Returns:
            object: 判定本体と同じ結果。
        """
        return self.isParentOf(*args, **kwargs)

    def isChildOf(self, *args, **kwargs):
        """各要素のisChildOfを同じ引数で呼び、保持順の戻り値リストを返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            list: 保持順の戻り値リスト。
        """
        return self._dispatch_shared("isChildOf", args, kwargs)

    isChildOf.__signature__ = inspect.signature(Node.isChildOf)

    @_is_alias(isChildOf)
    def childOf(self, *args, **kwargs):
        """isChildOfへ委譲するis省略の判定入口。

        Args:
            *args: 判定本体へ渡す位置引数。
            **kwargs: 判定本体へ渡すキーワード引数。

        Returns:
            object: 判定本体と同じ結果。
        """
        return self.isChildOf(*args, **kwargs)

    def getAttrCount(self, *args, **kwargs):
        """各要素のgetAttrCountを同じ引数で呼び、保持順の戻り値リストを返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            list: 保持順の戻り値リスト。
        """
        return self._dispatch_shared("getAttrCount", args, kwargs)

    getAttrCount.__signature__ = inspect.signature(Node.getAttrCount)

    def getPath(self, *args, **kwargs):
        """各要素のgetPathを同じ引数で呼び、保持順の戻り値リストを返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            list: 保持順の戻り値リスト。
        """
        return self._dispatch_shared("getPath", args, kwargs)

    getPath.__signature__ = inspect.signature(Node.getPath)

    def isRoot(self, *args, **kwargs):
        """各要素のisRootを同じ引数で呼び、保持順の戻り値リストを返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            list: 保持順の戻り値リスト。
        """
        return self._dispatch_shared("isRoot", args, kwargs)

    isRoot.__signature__ = inspect.signature(Node.isRoot)

    def getNodeName(self, *args, **kwargs):
        """各要素のgetNodeNameを同じ引数で呼び、保持順の戻り値リストを返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            list: 保持順の戻り値リスト。
        """
        return self._dispatch_shared("getNodeName", args, kwargs)

    getNodeName.__signature__ = inspect.signature(Node.getNodeName)

    def getNamespace(self, *args, **kwargs):
        """各要素のgetNamespaceを同じ引数で呼び、保持順の戻り値リストを返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            list: 保持順の戻り値リスト。
        """
        return self._dispatch_shared("getNamespace", args, kwargs)

    getNamespace.__signature__ = inspect.signature(Node.getNamespace)

    def setNamespace(self, *args, **kwargs):
        """各要素のsetNamespaceを同じ引数で呼び、コレクション自身を返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            Nodes | list: コレクション自身。
        """
        return self._dispatch_shared("setNamespace", args, kwargs)

    setNamespace.__signature__ = inspect.signature(Node.setNamespace)

    def rename(self, *args, **kwargs):
        """各要素のrenameを同じ引数で呼び、保持順の戻り値リストを返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            list: 保持順の戻り値リスト。
        """
        return self._dispatch_shared("rename", args, kwargs)

    rename.__signature__ = inspect.signature(Node.rename)

    def getInputs(self, *args, **kwargs):
        """各要素のgetInputsを同じ引数で呼び、保持順の戻り値リストを返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            list: 保持順の戻り値リスト。
        """
        return self._dispatch_shared("getInputs", args, kwargs)

    getInputs.__signature__ = inspect.signature(Node.getInputs)

    def getOutputs(self, *args, **kwargs):
        """各要素のgetOutputsを同じ引数で呼び、保持順の戻り値リストを返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            list: 保持順の戻り値リスト。
        """
        return self._dispatch_shared("getOutputs", args, kwargs)

    getOutputs.__signature__ = inspect.signature(Node.getOutputs)

    def getConnections(self, *args, **kwargs):
        """各要素のgetConnectionsを同じ引数で呼び、保持順の戻り値リストを返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            list: 保持順の戻り値リスト。
        """
        return self._dispatch_shared("getConnections", args, kwargs)

    getConnections.__signature__ = inspect.signature(Node.getConnections)

    def getHistory(self, *args, **kwargs):
        """各要素のgetHistoryを同じ引数で呼び、保持順の戻り値リストを返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            list: 保持順の戻り値リスト。
        """
        return self._dispatch_shared("getHistory", args, kwargs)

    getHistory.__signature__ = inspect.signature(Node.getHistory)

    def resetAttrs(self, *args, **kwargs):
        """各要素のresetAttrsを同じ引数で呼び、保持順の戻り値リストを返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            list: 保持順の戻り値リスト。
        """
        return self._dispatch_shared("resetAttrs", args, kwargs)

    resetAttrs.__signature__ = inspect.signature(Node.resetAttrs)

    def getPlugs(self, *args, **kwargs):
        """各要素のgetPlugsを同じ引数で呼び、保持順の戻り値リストを返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            list: 保持順の戻り値リスト。
        """
        return self._dispatch_shared("getPlugs", args, kwargs)

    getPlugs.__signature__ = inspect.signature(Node.getPlugs)

    def getAliases(self, *args, **kwargs):
        """各要素のgetAliasesを同じ引数で呼び、保持順の戻り値リストを返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            list: 保持順の戻り値リスト。
        """
        return self._dispatch_shared("getAliases", args, kwargs)

    getAliases.__signature__ = inspect.signature(Node.getAliases)

    def addAttr(self, *args, **kwargs):
        """各要素のaddAttrを同じ引数で呼び、保持順の戻り値リストを返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            list: 保持順の戻り値リスト。
        """
        return self._dispatch_shared("addAttr", args, kwargs)

    addAttr.__signature__ = inspect.signature(Node.addAttr)

    def getExtraAttrs(self, *args, **kwargs):
        """各要素のgetExtraAttrsを同じ引数で呼び、保持順の戻り値リストを返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            list: 保持順の戻り値リスト。
        """
        return self._dispatch_shared("getExtraAttrs", args, kwargs)

    getExtraAttrs.__signature__ = inspect.signature(Node.getExtraAttrs)

    def getExtraAttrNames(self, *args, **kwargs):
        """各要素のgetExtraAttrNamesを同じ引数で呼び、保持順の戻り値リストを返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            list: 保持順の戻り値リスト。
        """
        return self._dispatch_shared("getExtraAttrNames", args, kwargs)

    getExtraAttrNames.__signature__ = inspect.signature(Node.getExtraAttrNames)

    def getPlug(self, *args, **kwargs):
        """各要素のgetPlugを同じ引数で呼び、保持順の戻り値リストを返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            list: 保持順の戻り値リスト。
        """
        return self._dispatch_shared("getPlug", args, kwargs)

    getPlug.__signature__ = inspect.signature(Node.getPlug)

    def hasAttr(self, *args, **kwargs):
        """各要素のhasAttrを同じ引数で呼び、保持順の戻り値リストを返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            list: 保持順の戻り値リスト。
        """
        return self._dispatch_shared("hasAttr", args, kwargs)

    hasAttr.__signature__ = inspect.signature(Node.hasAttr)

    def getUuid(self, *args, **kwargs):
        """各要素のgetUuidを同じ引数で呼び、保持順の戻り値リストを返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            list: 保持順の戻り値リスト。
        """
        return self._dispatch_shared("getUuid", args, kwargs)

    getUuid.__signature__ = inspect.signature(Node.getUuid)

    def getName(self, *args, **kwargs):
        """各要素のgetNameを同じ引数で呼び、保持順の戻り値リストを返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            list: 保持順の戻り値リスト。
        """
        return self._dispatch_shared("getName", args, kwargs)

    getName.__signature__ = inspect.signature(Node.getName)

    def getFullName(self, *args, **kwargs):
        """各要素のgetFullNameを同じ引数で呼び、保持順の戻り値リストを返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            list: 保持順の戻り値リスト。
        """
        return self._dispatch_shared("getFullName", args, kwargs)

    getFullName.__signature__ = inspect.signature(Node.getFullName)

    def setAttrFlags(self, *args, **kwargs):
        """各要素のsetAttrFlagsを同じ引数で呼び、コレクション自身を返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            Nodes | list: コレクション自身。
        """
        return self._dispatch_shared("setAttrFlags", args, kwargs)

    setAttrFlags.__signature__ = inspect.signature(Node.setAttrFlags)

    def moveAttrOrder(self, *args, **kwargs):
        """各要素のmoveAttrOrderを同じ引数で呼び、コレクション自身を返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            Nodes | list: コレクション自身。
        """
        return self._dispatch_shared("moveAttrOrder", args, kwargs)

    moveAttrOrder.__signature__ = inspect.signature(Node.moveAttrOrder)

    def callEach(self, method, arguments, keyword_arguments=None):
        """各要素へ異なる引数を渡す。メソッド名は単体の公開インスタンスメソッドのみ。

        Args:
            method (str): setTranslate等。create・特殊メソッドは不可。
            arguments (Iterable[tuple]): 要素数と同じ数の位置引数タプル。
            keyword_arguments (Iterable[dict] | None): 要素別キーワード引数。省略時は空。
        Returns:
            list | Nodes: 照会・結果を返す操作は保持順のリスト、更新は自身。
                ネストしたリストもそのまま保持する。
        Raises:
            ValueError: メソッド名・件数が不正な場合。
            TypeError: 引数のシグネチャが不正な場合。実行前に全件確認する。
            RuntimeError: 単体の処理が失敗した場合。対象番号を含み、後続は実行しない。

        シーン編集は1回のUndoにまとめる。自動ロールバックはしない。
        ファイルI/OはUndo対象外。
        """
        functions, args, kwargs = self._prepare_calls(method, arguments, keyword_arguments)
        return self._execute_calls(method, functions, args, kwargs)

    def copy(self):
        """同じ参照を共有する、同じ具象型の独立した容器を返す。

        Returns:
            Nodes: 同じ参照を共有する、同じ具象型の独立した容器を返す。
        """
        result = object.__new__(type(self))
        result.__dict__.update(self.__dict__)
        result._items = list(self._items)
        return result

    def getNames(self):
        """保持順の現在のノード名。

        Returns:
            list[str]: 保持順の現在のノード名。
        """
        return [node.getName() for node in self]

    @undoChunk("hlibNodesDelete")
    def delete(self, *, safe=False):
        """各ノードの専用deleteを呼び、親削除で消えた後続対象はスキップする。

        Args:
            safe (bool): Trueなら各対象にsafe=Trueを渡し、DG接続を持つ対象を残す。

        Returns:
            None: 空なら何もしない。Jointsは専用の階層・ウェイト処理を優先する。
        Raises:
            TypeError: safeがboolでない場合。
            RuntimeError: 実行前に削除済みの参照がある、または削除失敗。
                途中までの変更は自動で戻さない。全体は一回のUndoで戻せる。
        """
        if type(safe) is not bool:
            raise TypeError("safe must be bool")
        for index, node in enumerate(self):
            if not node.isValid():
                raise RuntimeError(f"{type(self).__name__}.delete invalid item {index}")
        for index, node in enumerate(self):
            if node.isValid():
                try:
                    if safe:
                        node.delete(safe=True)
                    else:
                        node.delete()
                except Exception as exc:
                    raise RuntimeError(f"{type(self).__name__}.delete failed at item {index}: {exc}") from exc

    @_getter_alias(getShadingEngines)
    def shadingEngines(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getShadingEngines(*args, **kwargs)

    @_getter_alias(getAssignedObjects)
    def assignedObjects(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getAssignedObjects(*args, **kwargs)

    @_getter_alias(getMaterials)
    def materials(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getMaterials(*args, **kwargs)

    @_getter_alias(getType)
    def type(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getType(*args, **kwargs)

    @_getter_alias(getTypeId)
    def typeId(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getTypeId(*args, **kwargs)

    @_getter_alias(getPluginName)
    def pluginName(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getPluginName(*args, **kwargs)

    @_getter_alias(getClassification)
    def classification(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getClassification(*args, **kwargs)

    @_getter_alias(getAttrCount)
    def attrCount(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getAttrCount(*args, **kwargs)

    @_getter_alias(getPath)
    def path(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getPath(*args, **kwargs)

    @_getter_alias(getNodeName)
    def nodeName(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getNodeName(*args, **kwargs)

    @_getter_alias(getNamespace)
    def namespace(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getNamespace(*args, **kwargs)

    @_getter_alias(getInputs)
    def inputs(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getInputs(*args, **kwargs)

    @_getter_alias(getOutputs)
    def outputs(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getOutputs(*args, **kwargs)

    @_getter_alias(getConnections)
    def connections(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getConnections(*args, **kwargs)

    @_getter_alias(getHistory)
    def history(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getHistory(*args, **kwargs)

    @_getter_alias(getPlugs)
    def plugs(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getPlugs(*args, **kwargs)

    @_getter_alias(getAliases)
    def aliases(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getAliases(*args, **kwargs)

    @_getter_alias(getExtraAttrs)
    def extraAttrs(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getExtraAttrs(*args, **kwargs)

    @_getter_alias(getExtraAttrNames)
    def extraAttrNames(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getExtraAttrNames(*args, **kwargs)

    @_getter_alias(getPlug)
    def plug(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getPlug(*args, **kwargs)

    @_getter_alias(getUuid)
    def uuid(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getUuid(*args, **kwargs)

    @_getter_alias(getName)
    def name(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getName(*args, **kwargs)

    @_getter_alias(getFullName)
    def fullName(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getFullName(*args, **kwargs)

    @_getter_alias(getNames)
    def names(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getNames(*args, **kwargs)

    @staticmethod
    def _resolve_inputs(values):
        """対象列を一度だけ展開し、名前とNodeの混在を変換前に拒否する。

        Args:
            values (object): 単体、または対象の反復可能列。既存のAPI型も保持する。
        Returns:
            list: 入力順の対象。空列は空のまま返す。
        Raises:
            TypeError: 同じ対象列に文字列とNodeが混在している場合。
        """
        result = Object._flatten_inputs(values)
        Nodes._validate_inputs(result)
        return result

    @staticmethod
    def _validate_inputs(values):
        """展開済み対象列の名前とNodeの混在を拒否する。

        Args:
            values (list): Objectが展開した対象列。値の変換は行わない。
        Raises:
            TypeError: 名前とNodeが混在する場合。
        """
        if any(isinstance(value, str) for value in values) and any(isinstance(value, Node) for value in values):
            raise TypeError("Names and Node objects cannot be mixed in the same target collection")

    def _execute_calls(self, method, functions, args, kwargs):
        """検証済み呼出しを実行し、更新操作では不要な結果配列を作らない。

        Args:
            method: 一括実行するメソッド名。
            functions: 要素ごとに解決済みの呼出し先関数。
            args: 処理先へ渡す位置引数の列。
            kwargs: 処理先へ渡すキーワード引数の辞書。
        """
        all_fast = bool(kwargs) and all(flags.get("fast") is True for flags in kwargs)
        context = undoChunk("hlibBulk_" + method) if self._bulk_undo and not all_fast else contextlib.nullcontext()
        calculating = False
        if method in {"setTranslate", "setRotate", "setQuaternion", "setScale", "setShearing", "setMatrix", "setTransformation"}:
            calculating = any(inspect.signature(fn).bind(*row, **flags).arguments.get("get", False)
                              for fn, row, flags in zip(functions, args, kwargs))
        result = [] if calculating or self._bulk_returns[method] != "self" else None
        with context:
            for index, (function, row, flags) in enumerate(zip(functions, args, kwargs)):
                try:
                    value = function(*row, **flags)
                    if result is not None:
                        result.append(value)
                except Exception as exc:
                    raise RuntimeError(f"{type(self).__name__}.{method} failed at item {index}: {exc}") from exc
        return self if result is None else result

    def _dispatch_shared(self, method, args, kwargs):
        """単体APIの転送先を決める。独自callEachのoverrideを維持する。

        Args:
            method: 一括実行するメソッド名。
            args: 処理先へ渡す位置引数の列。
            kwargs: 処理先へ渡すキーワード引数の辞書。
        """
        if type(self).callEach is not Nodes.callEach:
            return self.callEach(method, [args] * len(self), [kwargs] * len(self))
        return self._call_shared(method, args, kwargs)

    def _call_shared(self, method, args, kwargs):
        """同じ入力の検証を実関数ごとに共有し、全件検証後に実行する。

        共有はこの呼出し内だけに限定する。派生overrideと個体callableは別に
        検証し、クラス差替え・reload後の古いメソッドを保持しない。

        Args:
            method: 一括実行するメソッド名。
            args: 処理先へ渡す位置引数の列。
            kwargs: 処理先へ渡すキーワード引数の辞書。
        """
        functions = [self._call_target(item, method) for item in self._items]
        shared = {}
        signatures = {}
        keywords = []
        for function in functions:
            key = function.__func__ if inspect.ismethod(function) else None
            if key is not None and key in shared:
                flags = shared[key]
            else:
                flags = normalize_flags(function, kwargs)
                self._signature(function, signatures).bind(*args, **flags)
                if key is not None:
                    shared[key] = flags
            keywords.append(flags)
        return self._execute_calls(method, functions, [args] * len(functions), keywords)

    def _prepare_calls(self, method, arguments, keyword_arguments):
        """全要素の引数を実行前に解決・検証する。

        Args:
            method (str): 登録済みの単体メソッド名。
            arguments (Iterable[tuple]): 要素別の位置引数。
            keyword_arguments (Iterable[dict] | None): 要素別のキーワード引数。

        Returns:
            tuple: 呼出先・位置引数・正規化済みキーワード引数の各リスト。

        Raises:
            ValueError: メソッド名または件数が不正な場合。
            TypeError: 引数が各呼出先のシグネチャと一致しない場合。
        """
        if method not in self._bulk_methods:
            raise ValueError(f"Unsupported instance method: {method}")
        args = [tuple(row) for row in arguments]
        kwargs = [{} for _ in self._items] if keyword_arguments is None else [dict(row) for row in keyword_arguments]
        if len(args) != len(self) or len(kwargs) != len(self):
            raise ValueError("Argument count must match collection length")
        functions = [self._call_target(item, method) for item in self._items]
        kwargs = [normalize_flags(function, flags) for function, flags in zip(functions, kwargs)]
        # この呼出内だけ共有し、reloadやクラスの差替え後に古いsignatureを保持しない。
        signatures = {}
        for function, row, flags in zip(functions, args, kwargs):
            self._signature(function, signatures).bind(*row, **flags)
        return functions, args, kwargs

    @staticmethod
    def _call_target(item, method):
        """取得・判定の省略名は呼出時の本体へ解決し、実際の署名とフラグを検査する。

        Args:
            item (Node): 呼出し先の単数参照。
            method (str): 管理表に登録した公開メソッド名。

        Returns:
            callable: 派生override・個体差替えを反映した実際の呼出し先。
        """
        function = getattr(item, method)
        getter_name = getattr(function, "__hlib_getter_name__", None)
        return getattr(item, getter_name) if getter_name is not None else function

    @staticmethod
    def _signature(function, signatures):
        """一回の検証内で実メソッドのsignatureだけを共有する。

        Args:
            function (callable): 実際に呼び出すメソッドまたは個体callable。
            signatures (dict): 呼出し内だけで使うキャッシュ。

        Returns:
            inspect.Signature: 束縛済み引数に対応するsignature。
        """
        if not inspect.ismethod(function):
            return inspect.signature(function)
        key = function.__func__
        if key not in signatures:
            signatures[key] = inspect.signature(function)
        return signatures[key]
