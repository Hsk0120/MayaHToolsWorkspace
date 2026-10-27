"""Maya の依存ノードと DAG ノードを扱う基底ラッパー。"""

import contextlib
import inspect
import re
from contextlib import nullcontext
from typing import Any

import maya.api.OpenMaya as om2
import maya.cmds as cmds

from ..core.object import Object
from ..core.registry import _inherited_node_types, _node_type_exists
from ..decorator import undoChunk, undoTransaction
from ..logger import raise_with_notify
from ..util import _ArgumentError, _UNSET

_MOVABLE_NUMERIC_TYPES = {
    om2.MFnNumericData.kBoolean: "bool",
    om2.MFnNumericData.kByte: "byte",
    om2.MFnNumericData.kShort: "short",
    om2.MFnNumericData.kInt: "long",
    om2.MFnNumericData.kLong: "long",
    om2.MFnNumericData.kFloat: "float",
    om2.MFnNumericData.kDouble: "double",
}  #: moveAttrOrder() が再作成できる数値アトリビュート型と cmds.addAttr(attributeType=) の対応。

#: ``cmds.listAttr(scalar=True)`` が除く、複数成分の数値型(double3 等。複合アトリビュートとして定義される)。
_MULTI_COMPONENT_NUMERIC_TYPES = frozenset(
    getattr(om2.MFnNumericData, name) for name in dir(om2.MFnNumericData) if name[:2] in ("k2", "k3", "k4")
)

#: Node.getPlugs() が ``cmds.listAttr`` を使わず OpenMaya で列挙するフラグ(値は True のときだけ)。
_OM2_LIST_ATTR_FLAGS = frozenset(("keyable", "scalar"))

#: ラッパー型の選択で型名だけを読むために使い回す関数セット。setObject() で対象を差し替えるため、
#: ノードごとに MFnDependencyNode を作るより速い。値や名前を保持せず、呼出しのたびに対象を設定し直す。
_TYPE_NAME_FN = om2.MFnDependencyNode()


def _subclass_overrides(base, name):
    """baseの派生クラス(孫以降を含む)のいずれかがメソッドを上書きしているか調べる。

    呼出しのたびに現在の派生クラスを調べるため、後から定義・登録されたクラスも反映する。

    Args:
        base (type): 基底クラス。
        name (str): メソッド名。

    Returns:
        bool: 1つでも上書きしていればTrue。
    """
    original = getattr(base, name)
    stack = list(base.__subclasses__())
    while stack:
        cls = stack.pop()
        if getattr(cls, name, original) is not original:
            return True
        stack.extend(cls.__subclasses__())
    return False


def _node_type_name(mobject):
    """検証済みの依存ノードの MObject から nodeType 名を取得する。

    ``om2.MFnDependencyNode(mobject).typeName`` と同じ値を、使い回しの関数セットで読む。

    Args:
        mobject (om2.MObject): 有効な依存ノードの MObject。

    Returns:
        str: Maya の nodeType 名。
    """
    fn = _TYPE_NAME_FN
    fn.setObject(mobject)
    return fn.typeName


def _resolve_node(node):
    """ノードを表す入力を MObject と MDagPath へ解決する。

    Node.__new__ (ラッパー型の選択)を通じてNodeの入力解決が利用する下位の解決処理。
    Node(...) の生成では __new__ で1回だけ呼び、結果を __init__ へ引き継ぐ。Plug・MPlug は
    所有ノード、コンポーネント(単体・複数形)は所有シェイプへ解決する。

    Args:
        node (str | Node | Plug | Component | Components | om2.MObject | om2.MDagPath | om2.MPlug):
            対象ノードの名前、mlib のラッパー、または Maya API 2.0 オブジェクト。
            ``"node.attribute"`` や ``"pCube1.vtx[0]"`` のような文字列も所有ノードへ解決する
            (インスタンス化されたノードは、名前が指すインスタンスのパスを保持する)。

    Returns:
        tuple[om2.MObject, om2.MDagPath | None]: 解決した MObject と、DAG ノードで
            あれば対応する MDagPath(非DAGノードでは None)。

    Raises:
        TypeError: 対応しない入力型、または依存ノード以外(アトリビュートなど)を指す MObject の場合。
        ValueError: 所有ノードは有効で、アトリビュートが ``deleteAttr`` で削除済みの Plug・MPlug の場合
            (:class:`mlib.plugs.plug.DeletedAttributeError`。``RuntimeError`` の派生でもある)。
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
        return Node._selection_owner(selection, 0, node)
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
    # nodesとの循環importを避け、Plugは呼出し時に取得する(名前・API参照の解決では使わないため、その後で取得する)。
    from ..plugs.plug import DeletedAttributeError, Plug
    if isinstance(node, om2.MPlug):
        if node.isNull:
            raise RuntimeError("空の MPlug からノードは解決できません")
        owner = node.node()
        # 所有ノードが有効でも、deleteAttr で削除されたアトリビュートの MPlug は削除済みの対象として扱う
        # (mlib のコマンドと同じ。所有ノードが削除済みなら下の MObject の解決で RuntimeError)。
        if om2.MObjectHandle(owner).isValid() and not Plug._mplug_attribute_exists(node, owner):
            raise DeletedAttributeError("削除済みのアトリビュートの MPlug からノードは解決できません")
        return _resolve_node(owner)
    if isinstance(node, Node):
        if not node.isValid():
            raise RuntimeError("無効な(削除済みの)ノードは指定できません")
        dag_path = node._current_dag_path()
        return om2.MObject(node._mobject), om2.MDagPath(dag_path) if dag_path is not None else None
    # Componentもnodesを参照するため、必要な分岐に達してからimportする。
    from ..components.component import Component, Components

    if isinstance(node, Plug):
        error = Plug._deleted_attribute_error(node)
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

    ``mlib.nodes.Node._resolve_input`` と同じ規則で解決し、削除済みの対象(削除済みの Node、
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
    definition = om2.MFnAttribute(attr)
    if not definition.connectable:
        raise TypeError("Cannot recreate a non-connectable attribute with Maya commands: " + plug.getFullName())
    info = {
        "longName": plug.getLongName(),
        "shortName": plug.getShortName(),
        "niceName": plug.getNiceName(),
        "hidden": plug.isHidden(),
        "keyable": plug.isKeyable(),
        "channelBox": plug.mplug().isChannelBox,
        "locked": plug.isLocked(),
        "value": plug.get(),
        "flags": {flag: getattr(definition, property_name) for flag, property_name in (
            ("readable", "readable"), ("writable", "writable"),
            ("storable", "storable"),
            ("cachedInternally", "cached"), ("usedAsColor", "usedAsColor"),
            ("usedAsFilename", "usedAsFilename"), ("disconnectBehaviour", "disconnectBehavior"),
        )},
    }
    source = plug.getSource(skipConversionNodes=False)
    info["source"] = _movable_connection_ref(source) if source is not None else None
    info["destinations"] = [_movable_connection_ref(target)
                            for target in plug.getDestinations(skipConversionNodes=False)]
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
        if plug.hasSoftMin():
            info["softMin"] = plug.getSoftMin()
        if plug.hasSoftMax():
            info["softMax"] = plug.getSoftMax()
        info["defaultValue"] = plug.getDefault()
    elif attr.hasFn(om2.MFn.kEnumAttribute):
        info["attributeType"] = "enum"
        info["enumName"] = _enum_definition(plug)
        info["defaultValue"] = plug.getDefault()
    elif attr.hasFn(om2.MFn.kTypedAttribute) and om2.MFnTypedAttribute(attr).attrType() == om2.MFnData.kString:
        info["dataType"] = "string"
    else:
        raise TypeError(f"Unsupported attribute type for reordering: {plug.getFullName()}")
    return info


def _enum_definition(plug):
    """enum の全フィールドを ``cmds.attributeQuery(listEnum=True)`` と同じ書式の文字列にする。

    値の昇順に並べ、直前の値 + 1(先頭は0)と異なる値だけ ``名前=値`` と書く(例: ``a=1:b=5``)。

    Args:
        plug (Plug): enum アトリビュートのプラグ。

    Returns:
        str: ``addAttr(enumName=...)`` へそのまま渡せるフィールド定義。
    """
    parts = []
    expected = 0
    for name, value in plug.getEnumNames():
        parts.append(name if value == expected else "{}={}".format(name, value))
        expected = value + 1
    return ":".join(parts)


def _scalar_attribute(attribute):
    """``cmds.listAttr(scalar=True)`` が列挙する、単一成分の数値・単位・enum 型か判定する。

    配列(multi)であっても、要素が単一成分なら対象に含める(listAttr と同じ)。

    Args:
        attribute (om2.MObject): アトリビュート定義。

    Returns:
        bool: scalar として列挙する場合は True。
    """
    if attribute.hasFn(om2.MFn.kCompoundAttribute):
        return False
    if attribute.hasFn(om2.MFn.kNumericAttribute):
        return om2.MFnNumericAttribute(attribute).numericType() not in _MULTI_COMPONENT_NUMERIC_TYPES
    return attribute.hasFn(om2.MFn.kUnitAttribute) or attribute.hasFn(om2.MFn.kEnumAttribute)


def _writable_plug(plug):
    """Plug._require_writable() が通るか(ロック・入力接続・書込み禁止が無いか)を返す。

    Args:
        plug (Plug): 検査するプラグ。

    Returns:
        bool: 書き込める場合は True。シーンは変更しない。
    """
    try:
        plug._require_writable()
    except RuntimeError:
        return False
    return True


def _movable_connection_ref(plug):
    """削除する定義を保持せず、所有ノードと再解決用のパスを保存する。

    Args:
        plug (Plug): 変更前に存在する接続端点。

    Returns:
        tuple[Node, str]: 所有ノードとaliasを使わないアトリビュートパス。
    """
    return plug.getNode(), plug.mplug().partialName(
        includeNonMandatoryIndices=True, includeInstancedIndices=True,
        useFullAttributePath=True, useLongNames=True)


def _create_movable_attr(node, info):
    """退避した定義と値を再作成する。接続とロックは全定義の作成後に戻す。

    Args:
        node (Node): アトリビュートを追加する対象ノード。
        info (dict): _dump_movable_attr() が返した情報。

    Returns:
        Plug: 再作成したアトリビュートプラグ。
    """
    kwargs = dict(info["flags"], shortName=info["shortName"], hidden=info["hidden"])
    if info["niceName"]:
        kwargs["niceName"] = info["niceName"]
    if "min" in info:
        kwargs["minValue"] = info["min"]
    if "max" in info:
        kwargs["maxValue"] = info["max"]
    if "softMin" in info:
        kwargs["softMinValue"] = info["softMin"]
    if "softMax" in info:
        kwargs["softMaxValue"] = info["softMax"]
    if "enumName" in info:
        kwargs["enumName"] = info["enumName"]
    plug = node.addAttr(
        info["longName"],
        attributeType=info.get("attributeType"),
        dataType=info.get("dataType"),
        defaultValue=info.get("defaultValue"),
        **kwargs,
    )
    if info["source"] is None:
        plug.set(info["value"])
    plug.setFlags(keyable=info["keyable"], channelBox=info["channelBox"])
    return plug


class Node(Object):
    """Mayaノードと、DAGノードでは特定インスタンスのパスを参照する。

    nodeTypeの登録型、近い登録祖先型、Nodeの順にラッパー型を選ぶ。
    Nodeを渡しても新しいラッパーを返し、Mayaノードは複製しない。
    名前・MDagPath・既存ラッパーのDAGパスを保持し、MObject・MPlugでは最初のパスを使う。
    保持インスタンスが消失した場合は別パスへ切り替えず、パスを使う操作でRuntimeErrorになる。
    str(node)は改名・親変更に追従する最短一意名、削除済みなら空文字列を返す。

    取得専用のクラスで、ノードの作成は :func:`mlib.createNode` で行う(``Node.create`` や
    ``Node(name, create=True)`` の作成経路は無い)。``isinstance`` の階層は手書きクラスの継承に
    従い、Mayaの抽象祖先型(``geometryFilter``・``containerBase``・``entity`` 等)のクラスは含まない。
    Mayaの継承チェーンによる判定は :meth:`isType` または :meth:`getType` の ``inherited=True`` を使う。

    Args:
        node (str | Node | Plug | Component | Components | om2.MObject | om2.MDagPath | om2.MPlug):
            名前または参照。Plug・MPlugは所有ノード、Component・Componentsは所有シェイプへ解決する。

    Raises:
        TypeError: 入力型が不正、または指定クラスと対象型が非互換の場合。
        ValueError: 所有ノードが有効でアトリビュートだけが削除済みのPlugの場合。
            MPlugも含み、DeletedAttributeError（RuntimeErrorの派生でもある）。
        RuntimeError: 取得対象が空・削除済み・存在しない・一意でない場合。
    """

    _registry = None  #: mlib.__init__ が構築後に注入する NodeRegistry。
    _fn_cache = None  #: _dependency_fn() が初回に作る MFnDependencyNode(ノードごとに1つ)。

    def __new__(cls, node, *args, **kwargs):
        """ノード型の登録情報に従ってラッパーを割り当てる。

        入力を一度だけ解決し、nodeTypeに対応する登録クラス(登録が無い型は登録表の規則で
        選ぶクラス。無ければNode)を選ぶ。具体的なクラスを指定した場合は、そのクラスの
        派生型以外を拒否し、黙って別の型へ差し替えない。ノードの作成は行わない。

        Args:
            node (str | Node | Plug | Component | Components | om2.MObject | om2.MDagPath | om2.MPlug):
                対象ノードの名前、mlib のラッパー、または Maya API 2.0 オブジェクト。
                Plug・MPlugは所有ノード、Component・Componentsは所有シェイプを指す。
            *args (object): 選んだクラスの ``__init__`` へ渡す位置引数。
            **kwargs (object): 選んだクラスの ``__init__`` へ渡すキーワード引数。
                ``create`` は受け付けない(``__init__`` が TypeError にする)。

        Returns:
            Node: 解決したMayaノードを参照する、適合クラスの新しいインスタンス。

        Raises:
            TypeError: ノード入力が対応しない型、指定クラスと対象型が非互換、または選んだクラスの
                ``__init__`` が受けない引数(廃止した ``create`` 等)を渡した場合。
            ValueError: アトリビュートが ``deleteAttr`` で削除済みの Plug・MPlug の場合
                (``DeletedAttributeError``。RuntimeError の派生でもある)。
            RuntimeError: ノードを解決できない場合。
        """
        if args or kwargs:
            # 廃止した create= 等、__init__ が受けない引数は入力を解決する前に TypeError にする。
            inspect.signature(cls.__init__).bind(None, node, *args, **kwargs)
        registry = cls._registry
        if registry is None:
            return super().__new__(cls)
        # 入力の解決(名前の検索など)は1回だけ行い、結果を __init__ へ引き継ぐ。
        resolved = _resolve_node(node)
        resolved_class = registry.wrapper_class(_node_type_name(resolved[0]))
        if cls is not Node and not issubclass(resolved_class, cls):
            message = "{} requires a compatible node, got {}".format(cls.__name__, resolved_class.__name__)
            if getattr(cls, "_generated", False):
                # 登録表の作り直し(reload・register)で無効になった生成クラスを保持したまま使った場合の案内。
                message += " (a generated class kept across mlib.reload() or a registry change is stale;"                            " fetch mlib.nodes.{} again)".format(cls.__name__)
            raise TypeError(message)
        instance = super().__new__(resolved_class)
        instance._pending_resolution = resolved
        return instance

    def __init__(self, node):
        """ノード入力を解決し、MObject と必要に応じた MDagPath を保持する。

        既存の Node を渡した場合は、同じ MObject と DAG パス(インスタンス)を
        指す新しいラッパーになる。

        Args:
            node (str | Node | Plug | Component | Components | om2.MObject | om2.MDagPath | om2.MPlug):
                対象ノードの名前、mlib のラッパー、または Maya API 2.0 オブジェクト。
                Plug・MPlugは所有ノード、Component・Componentsは所有シェイプを指す。

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
                :meth:`getPlug` が RuntimeError にする名前(``input3Dx`` のような、配列要素の
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

    def getShadingEngines(self):
        """自身から直接接続されているShadingEngineを重複なしで返す。

        Returns:
            list[ShadingEngine]: 直接接続先。テクスチャから履歴を辿る操作ではない。
        """
        from .shadingEngine import ShadingEngine
        result, seen = [], set()
        for plug in self._dependency_fn().getConnections():
            for destination in plug.connectedTo(False, True):
                obj = destination.node()
                key = om2.MObjectHandle(obj).hashCode()
                if obj.hasFn(om2.MFn.kShadingEngine) and key not in seen:
                    seen.add(key)
                    result.append(ShadingEngine(obj))
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

    def isValid(self):
        """Maya シーン上でノードが有効か判定する。

        ノード全体の有効性を返し、保持したDAGインスタンスのパスは検証しない。
        保持インスタンスだけが削除されてもノードが残っていればTrueになり、
        そのパスを使う操作はRuntimeErrorになる。

        Returns:
            bool: ノードハンドルが有効な場合は ``True``。
        """
        handle = self._handle
        return handle is not None and handle.isValid()

    def isAlive(self):
        """ノードの Maya オブジェクトがメモリ上に生存しているか判定する。

        Returns:
            bool: MObjectHandle.isAlive() の結果。Undo キューに保持された削除済みノードも生存と判定される場合がある。
        """
        handle = self._handle
        return handle is not None and handle.isAlive()

    def mnode(self):
        """保持している Maya API 2.0 MObject を返す。

        Returns:
            om2.MObject | None: ラップ対象の MObject。
        """
        return self._mobject

    def mfn(self):
        """このノードで最も具体的な om2 function set を、呼び出すたびに新しく作って返す。

        Node は ``om2.MFnDependencyNode``。DagNode は ``MFnDagNode``、Transform は ``MFnTransform`` のように
        派生クラスが最も具体的な function set へ上書きする。内部のキャッシュとは共有しないため、
        戻り値を保持しても他の照会に影響しない。

        Returns:
            om2.MFnDependencyNode: このノードの function set。

        Raises:
            RuntimeError: ノードが破棄されている(削除後にUndoの記録から消えた)場合。
        """
        return self._alive_fn()

    def getType(self, inherited=False):
        """Maya の nodeType 名、または nodeType の継承チェーンを返す。

        動的に生成したクラスを含め、ラッパーのクラス名ではなく Maya の nodeType 名をそのまま返す。

        Args:
            inherited (bool): True なら ``cmds.nodeType(inherited=True)`` と同じ順
                (基底型から自身へ。``node`` は含まない)の継承チェーンを返す。既定 False は型名だけ。

        Returns:
            str | list[str]: 既定は対応する Maya nodeType 名。inherited=True は継承チェーンの新しいリスト。

        Raises:
            TypeError: inherited が bool 以外の場合。
            RuntimeError: ノードが破棄されている(削除後にUndoの記録から消えた)場合。
        """
        if not isinstance(inherited, bool):
            raise TypeError("inherited must be a bool")
        type_name = self._alive_fn().typeName
        if not inherited:
            return type_name
        return list(reversed(_inherited_node_types(type_name)))

    def hasFn(self, fn):
        """保持する MObject が指定の OpenMaya 関数型に対応するか判定する。

        ``mnode().hasFn(fn)`` の公開入口。Maya の nodeType の継承(:meth:`isType`)ではなく、
        ``om2.MFn.kDagNode`` のような API の関数型で判定する。

        Args:
            fn (int): ``om2.MFn`` の定数。

        Returns:
            bool: 対応する場合は True。

        Raises:
            TypeError: fn が int 以外の場合。
            RuntimeError: ノードが破棄されている(削除後にUndoの記録から消えた)場合。
        """
        if not isinstance(fn, int) or isinstance(fn, bool):
            raise TypeError("fn must be an int (om2.MFn constant)")
        self._alive_fn()
        return self._mobject.hasFn(fn)

    def getTypeId(self):
        """Maya の内部 typeId を整数で返す。

        同一 Maya セッション内でノード型を高速に比較する用途に使う。
        プラグインの版数や環境によって値が変わりうるため、永続化には向かない。

        Returns:
            int: MTypeId の数値表現。

        Raises:
            RuntimeError: ノードが破棄されている(削除後にUndoの記録から消えた)場合。
        """
        return self._alive_fn().typeId.id()

    def getPluginName(self):
        """ノード型がプラグイン由来の場合、そのプラグイン名を取得する。

        Returns:
            str: プラグイン名。Maya組み込みのノード型では空文字列。

        Raises:
            RuntimeError: ノードが破棄されている(削除後にUndoの記録から消えた)場合。
        """
        return self._alive_fn().pluginName

    def getClassification(self):
        """ノード型の分類文字列を1要素のリストで取得する。

        Returns:
            list[str]: ``MNodeClass.classification`` を保持する。分類がなければ ``[""]``。
        """
        # cmdsは分類なしでも[""]を返す。その既存の返却形を維持する。
        return [om2.MNodeClass(self.getType()).classification]

    def isType(self, nodeType):
        """自身の nodeType が指定型そのもの、またはその派生型か判定する。

        ``cmds.nodeType(inherited=True)`` による継承チェーンで判定するため、
        例えば mesh ノードは ``isType("shape")`` で True になる。

        Args:
            nodeType (str): 判定する Maya nodeType 名。

        Returns:
            bool: 継承チェーンに nodeType が含まれる場合は True。

        Raises:
            ValueError: nodeType が空文字列または文字列以外の場合。
        """
        if not isinstance(nodeType, str) or not nodeType:
            raise ValueError("nodeType must be a non-empty string")
        if not self.isValid():
            return False
        return nodeType in _inherited_node_types(self.getType())

    def isLocked(self):
        """ノード自体がロックされているか判定する。

        アトリビュート単位のロックは Plug.isLocked() を参照する。

        Returns:
            bool: ロックされている場合は True。

        Raises:
            RuntimeError: ノードが破棄されている(削除後にUndoの記録から消えた)場合。
        """
        return self._alive_fn().isLocked

    def setLocked(self, state=True, *, fast=False):
        """ノード自体のロック状態を設定する。アトリビュート単位のロックは Plug.setLocked() を使う。

        通常は ``cmds.lockNode`` で更新し Undo に記録する。``fast=True`` は
        ``MFnDependencyNode.isLocked`` を直接更新し Undo に記録しない。

        Args:
            state (bool): True でロック、False で解除。既定 True。
            fast (bool): True は OpenMaya 直接更新(Undo なし)。既定 False。

        Returns:
            Node: 自身。

        Raises:
            TypeError: state または fast が bool でない場合。
            RuntimeError: ノードが破棄されている(削除後にUndoの記録から消えた)、または Maya が更新を拒否した場合。
        """
        if not isinstance(fast, bool):
            raise TypeError("fast must be a bool")
        with nullcontext() if fast else undoChunk("mlibNodeSetLocked"):
            if not isinstance(state, bool):
                raise TypeError("state must be a bool")
            fn = self._alive_fn()
            if fast:
                fn.isLocked = state
            else:
                cmds.lockNode(self.getFullName(), lock=state)
            return self

    def isFromReferencedFile(self):
        """ノードが参照ファイルから読み込まれたものか判定する。

        Returns:
            bool: 参照由来の場合は True。

        Raises:
            RuntimeError: ノードが破棄されている(削除後にUndoの記録から消えた)場合。
        """
        return self._alive_fn().isFromReferencedFile

    def isAncestorOf(self, other):
        """保持するDAGパスで、otherが自身の子孫か判定する。

        Args:
            other (Node | str | Plug | Component | Components | om2.MObject | om2.MDagPath | om2.MPlug):
                対象の参照や名前。Plugは所有ノード、Componentは所有シェイプへ解決する。

        Returns:
            bool: 自身を除く子孫ならTrue。非DAG・無効なノード・削除済みアトリビュートはFalse。

        Raises:
            TypeError: otherが未対応型の場合。
            RuntimeError: 名前を解決できない、MObject・MPlugが空、または保持インスタンスが消失した場合。
        """
        other_node = _query_target(other)
        self_full = self.getFullName()
        if other_node is None or not self_full:
            return False
        other_full = other_node.getFullName()
        return other_full != self_full and other_full.startswith(self_full + "|")

    def isParentOf(self, other):
        """保持するDAGパスで、otherが自身の直接の子か判定する。

        Args:
            other (Node | str | Plug | Component | Components | om2.MObject | om2.MDagPath | om2.MPlug):
                対象の参照や名前。Plugは所有ノード、Componentは所有シェイプへ解決する。

        Returns:
            bool: 直接の子ならTrue。非DAG・無効なノード・削除済みアトリビュートはFalse。

        Raises:
            TypeError: otherが未対応型の場合。
            RuntimeError: 名前を解決できない、MObject・MPlugが空、または保持インスタンスが消失した場合。
        """
        other_node = _query_target(other)
        self_full = self.getFullName()
        if other_node is None or not self_full:
            return False
        other_full = other_node.getFullName()
        parent_prefix, separator, _ = other_full.rpartition("|")
        return bool(separator) and parent_prefix == self_full

    def isRoot(self):
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

    def getNodeName(self, removeNamespace=False):
        """DAG パスを除いたノード名を返す。

        DGノードにも使用できる。DAGの別階層に同名ノードがある場合も
        親パスは付けないため、Mayaコマンドへ渡す一意な名前にはgetNameを使う。

        Args:
            removeNamespace (bool): ``True`` の場合はnamespaceも除外する。

        Returns:
            str: namespaceを含むノード名。``removeNamespace`` が ``True`` の場合は
                namespaceを含まないノード名。

        Raises:
            RuntimeError: ノードが破棄されている(削除後にUndoの記録から消えた)場合。
        """
        node_name = self._alive_fn().name()
        if removeNamespace:
            node_name = node_name.rsplit(":", 1)[-1]
        return node_name

    def getNamespace(self):
        """ノードが属するネームスペースを返す。

        Returns:
            Namespace: ノードが属するNamespace。
        """
        # common.namespace がNodeを参照するため、
        # 循環回避のためここで遅延 import する（mlib で意図的な相互依存の一つ）。
        from ..common import Namespace

        node_name = self.getNodeName()
        if ":" not in node_name:
            return Namespace(":")
        return Namespace(node_name.rsplit(":", 1)[0])

    def setNamespace(self, namespace, *, fast=False):
        """ノードを指定したネームスペースへ移動する。

        Args:
            namespace (str | Namespace): 移動先のnamespace名。末尾の ``":"`` は任意。
            fast (bool): TrueはOpenMaya直接更新でUndoなし。既定FalseはMaya標準コマンドを使用する。

        Returns:
            str: Mayaが確定したnamespace付きノード名。

        Raises:
            ValueError: namespaceが空文字列または文字列でない場合。
            RuntimeError: namespace移動に失敗した場合。
        """
        # common.namespaceとnodesの相互依存を避けるための遅延import。getNamespaceと同じ理由。
        if not isinstance(fast, bool):
            raise TypeError("fast must be a bool")
        with nullcontext() if fast else undoChunk("mlibNodeSetNamespace"):
            from ..common import Namespace

            if isinstance(namespace, Namespace):
                target_namespace = namespace
            elif isinstance(namespace, str) and namespace:
                target_namespace = Namespace(namespace)
            else:
                raise ValueError("namespace must be a non-empty string")
            if not target_namespace.exists() and target_namespace.name != ":":
                if fast:
                    om2.MNamespace.addNamespace(target_namespace.name)
                else:
                    target_namespace = Namespace.create(target_namespace)
            namespace_name = target_namespace.name
            node_name = self.getNodeName(True)
            new_name = (
                f"{namespace_name}:{node_name}"
                if namespace_name != ":"
                else node_name
            )
            return self.rename(new_name, fast=fast)

    def delete(self, *, safe=False, fast=False):
        """自身をMaya標準の規則で削除する。

        DAGの子も削除し、一回のUndoで戻せる。
        派生クラスはこのメソッドを上書きして専用の削除処理を実装できる。

        削除の前に自身とDAG子孫を検査し、ロック・参照のノード、または既定・共有ノード等の
        Mayaが削除を拒否するノード(``cmds.ls(undeletable=True)`` が返すもの。time1・persp・
        defaultLayer など)が含まれる場合は何も削除せずRuntimeErrorにする。通常経路の文言は
        cmds.deleteの要素ごとの表示に合わせ(``Cannot delete locked node 'x'.``・
        ``Cannot delete 'x' as it has locked or read-only children.``・
        ``Non-deletable node 'x' cannot be deleted.``)、fastのロック・参照は従来の
        ``Node is locked or referenced: x``。

        Args:
            safe (bool): Trueなら自身またはDAG子孫にDG接続がある場合は削除しない。
                入力・出力・message・Set/マテリアル接続を全て含む。
                Falseは従来の削除。ロック解除や例外抑制は行わない。
            fast (bool): TrueはOpenMaya直接更新でUndoなし。既定FalseはMaya標準コマンドを使用する。

        Returns:
            None: 値を返さない。

        Raises:
            TypeError: safeがboolでない場合。
            RuntimeError: 対象が無効、ロック・参照・削除できないノードを含む、またはMayaが
                削除を拒否した場合。
        """
        if not isinstance(fast, bool):
            raise TypeError("fast must be a bool")
        with nullcontext() if fast else undoChunk("mlibNodeDelete"):
            if type(safe) is not bool:
                raise TypeError("safe must be bool")
            if not self.isValid():
                raise RuntimeError("Cannot delete an invalid node")
            if safe and self._has_delete_connections():
                return
            from ..core.nodeEdit import delete_nodes
            delete_nodes([self], fast=fast)

    def rename(self, name, ignoreShape=False, *, fast=False):
        """ノード名を変更し、変更後の名前を返す。

        Args:
            name (str): 新しいノード名。
            ignoreShape (bool): ``True`` の場合はShapeの名前変更を抑制する。
            fast (bool): TrueはOpenMaya直接更新でUndoなし。既定FalseはMaya標準コマンドを使用する。

        Returns:
            str: Mayaが確定した変更後のノード名。

        Raises:
            TypeError: fastがboolでない場合。
            RuntimeError: ノードが無効(削除済み)の場合(``Cannot rename an invalid node``。
                fastも同じ)、保持するDAGインスタンスが削除された場合、またはMayaが
                改名を拒否した場合。
        """
        if not isinstance(fast, bool):
            raise TypeError("fast must be a bool")
        with nullcontext() if fast else undoChunk("mlibNodeRename"):
            if not self.isValid():
                # cmds.renameへ空の名前を渡すと文言の無いRuntimeErrorになるため、先に判定する。
                raise RuntimeError("Cannot rename an invalid node")
            if fast:
                from ..core.nodeEdit import rename_node
                return rename_node(self.mnode(), name, ignoreShape)
            return cmds.rename(self.getName(), name, ignoreShape=ignoreShape)

    def getConnections(self, s=True, d=True, c=False, t=None, et=False, scn=False, source=True, destination=True,
        connections=False, type=None, exactType=False, skipConversionNodes=False, asPair=False, asNode=False,
        index=_UNSET, *, idx=_UNSET):
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
            idx (int | None): indexの別名。同時指定は不可。

        Returns:
            list | Plug | Node | tuple | None: 条件に合う結果。
        """
        if idx is not _UNSET:
            if index is not _UNSET:
                raise _ArgumentError("Specify only one of 'index' and 'idx'")
            index = idx
        if index is _UNSET:
            index = None
        from ..plugs.plug import Plug
        pairs = []
        as_pair = asPair or c or connections
        skip_conversion = scn or skipConversionNodes
        directions = [incoming for incoming, enabled in ((True, s and source), (False, d and destination))
                      if enabled]

        def collect(mplug, local):
            """Plug.getConnections(asPair=True, 子・要素の展開なし)と同じ順で直接の接続を集める。

            その中の重複の統合は、下の_connection_resultsが同じ初出順で行うため省く。

            Args:
                mplug (om2.MPlug): 接続をたどる自身側のプラグ。
                local (Plug | None): ペアの自身側。ペアで返さない場合はNone。
            """
            for incoming in directions:
                if skip_conversion:
                    if incoming:
                        source_plug = mplug.source()
                        targets = [] if source_plug.isNull else [source_plug]
                    else:
                        targets = mplug.destinations()
                else:
                    targets = mplug.connectedTo(incoming, not incoming)
                pairs.extend((local, Plug(Plug._node_from_mplug(target), target)) for target in targets)

        # ペアで返さない場合、自身側のPlugは結果にも重複の判定にも使わない。
        # 接続の照会を上書きする派生クラスが無ければ、自身側のPlugを作らずMPlugから直接たどる。
        local_unused = not as_pair and not _subclass_overrides(Plug, "getConnections")
        for mp in self._dependency_fn().getConnections():
            if local_unused:
                collect(mp, None)
                continue
            local = Plug(self, mp)
            if local.__class__.getConnections is not Plug.getConnections:
                # 派生クラスが接続の照会を上書きする場合は、その実装を通す(引数typeが組込みを隠すため__class__)。
                pairs.extend(local.getConnections(s, d, source=source, destination=destination,
                             scn=skip_conversion, asPair=True,
                             checkChildren=False, checkElements=False))
                continue
            collect(local.mplug(), local)
        return Plug._connection_results(pairs, type or t, exactType or et,
                                       as_pair, asNode, index)

    def getHistory(self, type=None, future=False):
        """構築履歴を ``MItDependencyGraph`` で検索し、対応するノードラッパーを返す。

        Args:
            type (str | None): 継承型を含むノード型フィルター。Noneは全型。
            future (bool): Trueは下流、Falseは上流を検索する。

        Returns:
            list[Node]: ``cmds.listHistory`` と同じ順(深さ優先)。自身と重複を除く。該当なしなら空リスト。
                Shapeを持つTransformは、``listHistory`` と同じく中間オブジェクトでない直下のShapeの
                履歴を返す。DAGノードは最初のDAGパスで返す。

        Raises:
            RuntimeError: 無効な(削除済みの)ノードの場合。
        """
        if not self.isValid():
            raise RuntimeError("Cannot get the history of an invalid node")
        # cmds.listHistory(leaf=True) と同じく、Shapeを持つTransformは中間オブジェクトでない
        # 直下のShapeから探索する(Transform自身の入出力は含めない)。
        roots = [self._mobject]
        if self._mobject.hasFn(om2.MFn.kTransform):
            dag = om2.MFnDagNode(self._mobject)
            shapes = []
            for index in range(dag.childCount()):
                child = dag.child(index)
                if child.hasFn(om2.MFn.kShape) and not om2.MFnDagNode(child).isIntermediateObject:
                    shapes.append(child)
            roots = shapes or roots
        direction = om2.MItDependencyGraph.kDownstream if future else om2.MItDependencyGraph.kUpstream
        result = []
        uuid_fn = om2.MFnDependencyNode()

        def uuid_of(mobject):
            """重複判定用のUUID文字列(ノードごとに一意)。"""
            uuid_fn.setObject(mobject)
            return uuid_fn.uuid().asString()

        seen = {uuid_of(self._mobject)}
        for root in roots:
            # listHistory と同じ深さ優先・ノード単位の順。各ノードは最初の出現だけを残す。
            iterator = om2.MItDependencyGraph(root, om2.MFn.kInvalid, direction,
                                              om2.MItDependencyGraph.kDepthFirst,
                                              om2.MItDependencyGraph.kNodeLevel)
            while not iterator.isDone():
                mobject = iterator.currentNode()
                iterator.next()
                key = uuid_of(mobject)
                if key in seen:
                    continue
                seen.add(key)
                node = Node._wrap_resolved(*_resolve_node(mobject))
                if type is None or node.isType(type):
                    result.append(node)
        return result

    def resetAttrs(self, attributes=_UNSET, *, fast=False, attrs=_UNSET):
        """指定アトリビュート、または書き込み可能なキー設定対象アトリビュートを既定値へ戻す。

        Args:
            attributes (str | Iterable[str] | None): アトリビュート名。Noneはキー設定可能な
                数値・単位・enumアトリビュートを対象とし、配列・ロック・入力接続・書込み禁止・
                非対応型は除外する(通常/fastで同じ選択)。
                明示指定したアトリビュートのエラーは除外せず送出する。 別名 ``attrs`` も使用可能。
            fast (bool): TrueはOpenMaya直接更新でUndoなし。既定FalseはMaya標準コマンドを使用する。
            attrs (str | Iterable[str] | None): attributesの別名。同時指定は不可。

        Returns:
            list[Plug]: リセットしたアトリビュート。全変更を一回のUndoにまとめる。

        Raises:
            AttributeError: 指定アトリビュートが存在しない場合。
            TypeError: 明示指定したアトリビュートがリセット非対応の場合。
            RuntimeError: 明示指定したアトリビュートがロック・接続済みなどで書き込みできない場合。
        """
        if attrs is not _UNSET:
            if attributes is not _UNSET:
                raise _ArgumentError("Specify only one of 'attributes' and 'attrs'")
            attributes = attrs
        if attributes is _UNSET:
            attributes = None
        if not isinstance(fast, bool):
            raise TypeError("fast must be a bool")
        with nullcontext() if fast else undoChunk("mlibNodeResetAttrs"):
            if attributes is None:
                # getPlugs(keyable, scalar) は cmds.listAttr と同じ列挙を om2 で行うため、fastでもcmdsを呼ばない。
                # listAttr(scalar=True) は配列も返すため配列を除く(要素ごとのresetが必要)。
                plugs = [plug for plug in self.getPlugs(keyable=True, scalar=True)
                         if not plug.mplug().isArray and plug.getDefault() is not None
                         and not plug.isDestination()]
                # 通常/fastとも、ロック・入力接続・書込み禁止をfastの書込みと同じ検査で除く。
                plugs = [plug for plug in plugs if _writable_plug(plug)]
            else:
                if isinstance(attributes, str):
                    attributes = [attributes]
                plugs = [self.getPlug(name) for name in attributes]
            for plug in plugs:
                plug.reset(fast=fast)
            return plugs

    def setAttrFlags(self, attributes=_UNSET, locked=None, keyable=None, channelBox=None, *, fast=False,
        attrs=_UNSET):
        """指定アトリビュートのロック・キー設定可否・Channel Box表示を変更する。

        状態の型を検査し、全アトリビュートを解決してから順に更新する。
        途中の失敗で、先行の変更は自動では戻さない。

        Args:
            attributes (str | Iterable[str]): アトリビュート名。子も変更するなら子名を明示する。
            locked (bool | None): ロック状態。Noneは変更しない。
            keyable (bool | None): キー設定可否。Noneは変更しない。
            channelBox (bool | None): Channel Box表示。Noneは変更しない。keyable=TrueならMayaにより表示される。
            fast (bool): TrueはUndoなしのOM2更新。FalseはUndo有効時に一つのチャンクへ記録する。
                Undo設定は変更しない。
            attrs (str | Iterable[str]): attributesの別名。同時指定は不可。

        Returns:
            Node: 自身。

        Raises:
            AttributeError: 指定アトリビュートが存在しない場合。
            TypeError: 必須引数の不足・長短名の競合、fastや状態の型が不正な場合。
            RuntimeError: Mayaが更新を拒否した場合。
        """
        if attrs is not _UNSET:
            if attributes is not _UNSET:
                raise _ArgumentError("Specify only one of 'attributes' and 'attrs'")
            attributes = attrs
        if attributes is _UNSET:
            raise _ArgumentError("Missing required argument: 'attributes'")
        if not isinstance(fast, bool):
            raise TypeError("fast must be a bool")
        with nullcontext() if fast else undoChunk("mlibNodeSetAttrFlags"):
            from ..plugs.plug import Plug
            flags = Plug._validated_flags(locked, keyable, channelBox)
            if isinstance(attributes, str):
                attributes = [attributes]
            plugs = [self.getPlug(name) for name in attributes]
            if flags:
                for plug in plugs:
                    plug.setFlags(locked=locked, keyable=keyable, channelBox=channelBox, fast=fast)
            return self

    def getPlugs(self, userDefined=False, includeChildren=True, **listAttrFlags):
        """アトリビュートをPlug参照として列挙する。

        ``userDefined=True`` はユーザー追加(動的)アトリビュートだけを、Mayaの定義から追加順に
        型付きPlugで作る(cmdsは使わない。配列はArrayPlug、非表示・非keyableも含む)。
        それ以外は ``cmds.listAttr`` の条件で列挙する(``keyable=True`` 等)。フラグ無し・``keyable=True``・
        ``scalar=True`` (併用可)は ``cmds.listAttr`` を呼ばず、同じ順序・同じ結果をOpenMayaの定義の
        走査で求める(トップレベルの定義順に、複合の子を親の直後へ並べ、配列の複合の子は含めない)。

        Args:
            userDefined (bool): Trueはユーザー定義アトリビュートだけを返す。listAttrのフラグとは併用できない。
            includeChildren (bool): Trueは複合アトリビュートの子も含める。Falseはトップレベルだけ。
            **listAttrFlags: ``userDefined=False`` のときに ``cmds.listAttr`` へ渡すフラグ。

        Returns:
            list[Plug]: 追加順(userDefined)またはlistAttr順の新しい参照リスト。解決できないパスは省き、
                該当なしなら空。名前が必要なら ``[plug.getLongName() for plug in ...]`` を使う。

        Raises:
            TypeError: userDefined・includeChildrenがboolでない、またはuserDefined=TrueにlistAttrのフラグを併用した場合。
            RuntimeError: ノードが無効、listAttrが失敗、またはuserDefined=TrueかつincludeChildren=Trueで
                番号を指定しない複合配列の子が含まれる場合。
        """
        if type(userDefined) is not bool:
            raise TypeError("userDefined must be a bool")
        if type(includeChildren) is not bool:
            raise TypeError("includeChildren must be a bool")
        if not self.isValid():
            raise RuntimeError("Cannot list attributes on an invalid node")
        if userDefined:
            if listAttrFlags:
                raise TypeError("userDefined=True cannot be combined with listAttr flags: "
                                + ", ".join(sorted(listAttrFlags)))
            # 名前へ変換して再検索せず、定義から型付きPlugを作る。配列の要素は展開しない。
            from ..plugs.plug import Plug
            return [Plug(self, om2.MPlug(self._mobject, attribute))
                    for attribute in self._user_attributes(includeChildren)]
        if all(name in _OM2_LIST_ATTR_FLAGS and value is True for name, value in listAttrFlags.items()):
            from ..plugs.plug import Plug
            return [Plug(self, om2.MPlug(self._mobject, attribute))
                    for attribute in self._listed_attributes(includeChildren, **listAttrFlags)]
        names = cmds.listAttr(self.getFullName(), **listAttrFlags) or []
        plugs = []
        for name in names:
            try:
                plug = self.getPlug(name)
            except (AttributeError, RuntimeError, ValueError):
                continue
            if includeChildren or not plug.mplug().isChild:
                plugs.append(plug)
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
        # 配列・複合パスはgetPlugで解決し、別のMayaコマンドで名前を再解決しない。
        return [(alias, self.getPlug(name)) for alias, name in self._dependency_fn().getAliasList()]

    def addAttr(self, longName=_UNSET, type=None, subType=None, channelBox=_UNSET, childNames=None,
        childShortNames=None, childSuffixes=None, proxy=_UNSET, getPlug=True, *, fast=False, attributeType=_UNSET,
        at=_UNSET, binaryTag=_UNSET, bt=_UNSET, cachedInternally=_UNSET, ci=_UNSET, category=_UNSET, ct=_UNSET,
        dataType=_UNSET, dt=_UNSET, defaultValue=_UNSET, dv=_UNSET, disconnectBehaviour=_UNSET, dcb=_UNSET,
        edit=_UNSET, e=_UNSET, enforcingUniqueName=_UNSET, eun=_UNSET, enumName=_UNSET, en=_UNSET, exists=_UNSET,
        ex=_UNSET, fromPlugin=_UNSET, fp=_UNSET, hasMaxValue=_UNSET, hxv=_UNSET, hasMinValue=_UNSET, hnv=_UNSET,
        hasSoftMaxValue=_UNSET, hsx=_UNSET, hasSoftMinValue=_UNSET, hsn=_UNSET, hidden=_UNSET, h=_UNSET,
        indexMatters=_UNSET, im=_UNSET, internalSet=_UNSET, keyable=_UNSET, k=_UNSET, ln=_UNSET, maxValue=_UNSET,
        max=_UNSET, minValue=_UNSET, min=_UNSET, multi=_UNSET, m=_UNSET, niceName=_UNSET, nn=_UNSET,
        numberOfChildren=_UNSET, nc=_UNSET, parent=_UNSET, p=_UNSET, pxy=_UNSET, query=_UNSET, q=_UNSET,
        readable=_UNSET, r=_UNSET, shortName=_UNSET, sn=_UNSET, softMaxValue=_UNSET, smx=_UNSET,
        softMinValue=_UNSET, smn=_UNSET, storable=_UNSET, s=_UNSET, usedAsColor=_UNSET, uac=_UNSET,
        usedAsFilename=_UNSET, uaf=_UNSET, usedAsProxy=_UNSET, uap=_UNSET, worldSpace=_UNSET, ws=_UNSET,
        writable=_UNSET, w=_UNSET, cb=_UNSET, **kwargs):
        """型・既定値・フラグを指定してアトリビュートを追加する。

        作成専用。query/edit=Trueは拒否する。長名と対応する短名は同時指定できない。
        型はproxyの元、明示type、attributeType/dataTypeの順に使い、全て省略時はdouble。
        単位型を直接追加する場合、既定値・制限は距離cm・角度rad・時刻秒で指定する。
        通常はUndo有効時に記録する。fastはUndo設定を変えずOM2で追加し、未対応の型・定義フラグは追加前に拒否する。

        Args:
            longName (str): ロング名。lnまたはsnだけの指定も可能。
            type (str | None): 型名。at:/dt:接頭辞も可。明示時はattributeType/dataTypeより優先。
            subType (str | None): 自動生成する子の共通型。
            channelBox (bool): チャンネルボックス表示。cbでも指定可能。
            childNames (Sequence[str] | None): 子のロング名。
            childShortNames (Sequence[str] | None): 子のショート名。
            childSuffixes (Sequence[str] | None): 親名へ付加する子の接尾辞。
            proxy (Plug | str | None): プロキシの元アトリビュート。
            getPlug (bool): 既定Trueは追加したPlug、FalseはNoneを返す。
            fast (bool): TrueはUndoなしの直接追加。既定Falseはcmds。
            attributeType (str): MayaのattributeTypeフラグ。
            at (str): attributeTypeの別名。
            binaryTag (str): MayaのbinaryTagフラグ。
            bt (str): binaryTagの別名。
            cachedInternally (bool): MayaのcachedInternallyフラグ。
            ci (bool): cachedInternallyの別名。
            category (str | Sequence[str]): Mayaのcategoryフラグ。
            ct (str | Sequence[str]): categoryの別名。
            dataType (str | Sequence[str]): MayaのdataTypeフラグ。
            dt (str | Sequence[str]): dataTypeの別名。
            defaultValue (object): 追加する型に対応した既定値。複合数値は成分列、型付きデータはPlug.setと同じ形で指定する。
            dv (object): defaultValueの別名。
            disconnectBehaviour (int): MayaのdisconnectBehaviourフラグ。
            dcb (int): disconnectBehaviourの別名。
            edit (bool): Trueは作成専用のため拒否する。
            e (bool): editの別名。
            enforcingUniqueName (bool): MayaのenforcingUniqueNameフラグ。
            eun (bool): enforcingUniqueNameの別名。
            enumName (str): MayaのenumNameフラグ。
            en (str): enumNameの別名。
            exists (bool): Mayaのexistsフラグ。
            ex (bool): existsの別名。
            fromPlugin (bool): MayaのfromPluginフラグ。
            fp (bool): fromPluginの別名。
            hasMaxValue (bool): MayaのhasMaxValueフラグ。
            hxv (bool): hasMaxValueの別名。
            hasMinValue (bool): MayaのhasMinValueフラグ。
            hnv (bool): hasMinValueの別名。
            hasSoftMaxValue (bool): MayaのhasSoftMaxValueフラグ。
            hsx (bool): hasSoftMaxValueの別名。
            hasSoftMinValue (bool): MayaのhasSoftMinValueフラグ。
            hsn (bool): hasSoftMinValueの別名。
            hidden (bool): Mayaのhiddenフラグ。
            h (bool): hiddenの別名。
            indexMatters (bool): MayaのindexMattersフラグ。
            im (bool): indexMattersの別名。
            internalSet (bool): MayaのinternalSetフラグ。
            keyable (bool): Mayaのkeyableフラグ。
            k (bool): keyableの別名。
            ln (str): longNameの別名。
            maxValue (float | om2.MAngle | om2.MDistance | om2.MTime): MayaのmaxValueフラグ。
            max (float | om2.MAngle | om2.MDistance | om2.MTime): maxValueの別名。
            minValue (float | om2.MAngle | om2.MDistance | om2.MTime): MayaのminValueフラグ。
            min (float | om2.MAngle | om2.MDistance | om2.MTime): minValueの別名。
            multi (bool): Mayaのmultiフラグ。
            m (bool): multiの別名。
            niceName (str): MayaのniceNameフラグ。
            nn (str): niceNameの別名。
            numberOfChildren (int): MayaのnumberOfChildrenフラグ。
            nc (int): numberOfChildrenの別名。
            parent (str): 親にする既存の複合アトリビュート名。ノードの親指定ではない。
            p (str): parentの別名。
            pxy (Plug | str | None): proxyの別名。
            query (bool): Trueは作成専用のため拒否する。
            q (bool): queryの別名。
            readable (bool): Mayaのreadableフラグ。
            r (bool): readableの別名。
            shortName (str): MayaのshortNameフラグ。
            sn (str): shortNameの別名。
            softMaxValue (float | om2.MAngle | om2.MDistance | om2.MTime): MayaのsoftMaxValueフラグ。
            smx (float | om2.MAngle | om2.MDistance | om2.MTime): softMaxValueの別名。
            softMinValue (float | om2.MAngle | om2.MDistance | om2.MTime): MayaのsoftMinValueフラグ。
            smn (float | om2.MAngle | om2.MDistance | om2.MTime): softMinValueの別名。
            storable (bool): Mayaのstorableフラグ。
            s (bool): storableの別名。
            usedAsColor (bool): MayaのusedAsColorフラグ。
            uac (bool): usedAsColorの別名。
            usedAsFilename (bool): MayaのusedAsFilenameフラグ。
            uaf (bool): usedAsFilenameの別名。
            usedAsProxy (bool): MayaのusedAsProxyフラグ。
            uap (bool): usedAsProxyの別名。
            worldSpace (bool): MayaのworldSpaceフラグ。
            ws (bool): worldSpaceの別名。
            writable (bool): Mayaのwritableフラグ。
            w (bool): writableの別名。
            cb (bool): channelBoxの別名。
            **kwargs: Mayaへ渡す追加フラグ。
                予約語の短名isは辞書展開で指定する。internalSetとの同時指定は不可。

        Returns:
            Plug | None: getPlug=Trueでは追加したPlug。getPlug=FalseではNone。
                getPlug=Falseでもアトリビュートの追加・既定値等の設定は実行する。

        Raises:
            TypeError: 長短名の同時指定、またはfastがbool以外の場合。
            ValueError: 名前の省略、不正な型接頭辞、解決後のattributeType/dataType併用、またはquery/edit=True。
            NotImplementedError: fastで型や定義フラグが未対応の場合。

        Note:
            子名・成分数と検証可能な型付き既定値は追加前に検査する。
            通常の子追加だけは公開addAttrへ委譲し、overrideを呼ぶ。fastは親子定義を一括構築する。
            Mayaやoverride、作成後の既定値・表示・proxy接続が失敗しても、完了済みの追加は戻さない。
        """
        if at is not _UNSET:
            if attributeType is not _UNSET:
                raise _ArgumentError("Specify only one of 'attributeType' and 'at'")
            attributeType = at
        if attributeType is not _UNSET:
            kwargs["attributeType"] = attributeType
        if bt is not _UNSET:
            if binaryTag is not _UNSET:
                raise _ArgumentError("Specify only one of 'binaryTag' and 'bt'")
            binaryTag = bt
        if binaryTag is not _UNSET:
            kwargs["binaryTag"] = binaryTag
        if ci is not _UNSET:
            if cachedInternally is not _UNSET:
                raise _ArgumentError("Specify only one of 'cachedInternally' and 'ci'")
            cachedInternally = ci
        if cachedInternally is not _UNSET:
            kwargs["cachedInternally"] = cachedInternally
        if ct is not _UNSET:
            if category is not _UNSET:
                raise _ArgumentError("Specify only one of 'category' and 'ct'")
            category = ct
        if category is not _UNSET:
            kwargs["category"] = category
        if dt is not _UNSET:
            if dataType is not _UNSET:
                raise _ArgumentError("Specify only one of 'dataType' and 'dt'")
            dataType = dt
        if dataType is not _UNSET:
            kwargs["dataType"] = dataType
        if dv is not _UNSET:
            if defaultValue is not _UNSET:
                raise _ArgumentError("Specify only one of 'defaultValue' and 'dv'")
            defaultValue = dv
        if defaultValue is not _UNSET:
            kwargs["defaultValue"] = defaultValue
        if dcb is not _UNSET:
            if disconnectBehaviour is not _UNSET:
                raise _ArgumentError("Specify only one of 'disconnectBehaviour' and 'dcb'")
            disconnectBehaviour = dcb
        if disconnectBehaviour is not _UNSET:
            kwargs["disconnectBehaviour"] = disconnectBehaviour
        if e is not _UNSET:
            if edit is not _UNSET:
                raise _ArgumentError("Specify only one of 'edit' and 'e'")
            edit = e
        if edit is not _UNSET:
            kwargs["edit"] = edit
        if eun is not _UNSET:
            if enforcingUniqueName is not _UNSET:
                raise _ArgumentError("Specify only one of 'enforcingUniqueName' and 'eun'")
            enforcingUniqueName = eun
        if enforcingUniqueName is not _UNSET:
            kwargs["enforcingUniqueName"] = enforcingUniqueName
        if en is not _UNSET:
            if enumName is not _UNSET:
                raise _ArgumentError("Specify only one of 'enumName' and 'en'")
            enumName = en
        if enumName is not _UNSET:
            kwargs["enumName"] = enumName
        if ex is not _UNSET:
            if exists is not _UNSET:
                raise _ArgumentError("Specify only one of 'exists' and 'ex'")
            exists = ex
        if exists is not _UNSET:
            kwargs["exists"] = exists
        if fp is not _UNSET:
            if fromPlugin is not _UNSET:
                raise _ArgumentError("Specify only one of 'fromPlugin' and 'fp'")
            fromPlugin = fp
        if fromPlugin is not _UNSET:
            kwargs["fromPlugin"] = fromPlugin
        if hxv is not _UNSET:
            if hasMaxValue is not _UNSET:
                raise _ArgumentError("Specify only one of 'hasMaxValue' and 'hxv'")
            hasMaxValue = hxv
        if hasMaxValue is not _UNSET:
            kwargs["hasMaxValue"] = hasMaxValue
        if hnv is not _UNSET:
            if hasMinValue is not _UNSET:
                raise _ArgumentError("Specify only one of 'hasMinValue' and 'hnv'")
            hasMinValue = hnv
        if hasMinValue is not _UNSET:
            kwargs["hasMinValue"] = hasMinValue
        if hsx is not _UNSET:
            if hasSoftMaxValue is not _UNSET:
                raise _ArgumentError("Specify only one of 'hasSoftMaxValue' and 'hsx'")
            hasSoftMaxValue = hsx
        if hasSoftMaxValue is not _UNSET:
            kwargs["hasSoftMaxValue"] = hasSoftMaxValue
        if hsn is not _UNSET:
            if hasSoftMinValue is not _UNSET:
                raise _ArgumentError("Specify only one of 'hasSoftMinValue' and 'hsn'")
            hasSoftMinValue = hsn
        if hasSoftMinValue is not _UNSET:
            kwargs["hasSoftMinValue"] = hasSoftMinValue
        if h is not _UNSET:
            if hidden is not _UNSET:
                raise _ArgumentError("Specify only one of 'hidden' and 'h'")
            hidden = h
        if hidden is not _UNSET:
            kwargs["hidden"] = hidden
        if im is not _UNSET:
            if indexMatters is not _UNSET:
                raise _ArgumentError("Specify only one of 'indexMatters' and 'im'")
            indexMatters = im
        if indexMatters is not _UNSET:
            kwargs["indexMatters"] = indexMatters
        if "is" in kwargs:
            if internalSet is not _UNSET:
                raise _ArgumentError("Specify only one of 'internalSet' and 'is'")
            internalSet = kwargs.pop("is")
        if internalSet is not _UNSET:
            kwargs["internalSet"] = internalSet
        if k is not _UNSET:
            if keyable is not _UNSET:
                raise _ArgumentError("Specify only one of 'keyable' and 'k'")
            keyable = k
        if keyable is not _UNSET:
            kwargs["keyable"] = keyable
        if ln is not _UNSET:
            if longName is not _UNSET:
                raise _ArgumentError("Specify only one of 'longName' and 'ln'")
            longName = ln
        if longName is _UNSET:
            longName = ""
        if max is not _UNSET:
            if maxValue is not _UNSET:
                raise _ArgumentError("Specify only one of 'maxValue' and 'max'")
            maxValue = max
        if maxValue is not _UNSET:
            kwargs["maxValue"] = maxValue
        if min is not _UNSET:
            if minValue is not _UNSET:
                raise _ArgumentError("Specify only one of 'minValue' and 'min'")
            minValue = min
        if minValue is not _UNSET:
            kwargs["minValue"] = minValue
        if m is not _UNSET:
            if multi is not _UNSET:
                raise _ArgumentError("Specify only one of 'multi' and 'm'")
            multi = m
        if multi is not _UNSET:
            kwargs["multi"] = multi
        if nn is not _UNSET:
            if niceName is not _UNSET:
                raise _ArgumentError("Specify only one of 'niceName' and 'nn'")
            niceName = nn
        if niceName is not _UNSET:
            kwargs["niceName"] = niceName
        if nc is not _UNSET:
            if numberOfChildren is not _UNSET:
                raise _ArgumentError("Specify only one of 'numberOfChildren' and 'nc'")
            numberOfChildren = nc
        if numberOfChildren is not _UNSET:
            kwargs["numberOfChildren"] = numberOfChildren
        if p is not _UNSET:
            if parent is not _UNSET:
                raise _ArgumentError("Specify only one of 'parent' and 'p'")
            parent = p
        if parent is not _UNSET:
            kwargs["parent"] = parent
        if pxy is not _UNSET:
            if proxy is not _UNSET:
                raise _ArgumentError("Specify only one of 'proxy' and 'pxy'")
            proxy = pxy
        if proxy is _UNSET:
            proxy = None
        if q is not _UNSET:
            if query is not _UNSET:
                raise _ArgumentError("Specify only one of 'query' and 'q'")
            query = q
        if query is not _UNSET:
            kwargs["query"] = query
        if r is not _UNSET:
            if readable is not _UNSET:
                raise _ArgumentError("Specify only one of 'readable' and 'r'")
            readable = r
        if readable is not _UNSET:
            kwargs["readable"] = readable
        if sn is not _UNSET:
            if shortName is not _UNSET:
                raise _ArgumentError("Specify only one of 'shortName' and 'sn'")
            shortName = sn
        if shortName is not _UNSET:
            kwargs["shortName"] = shortName
        if smx is not _UNSET:
            if softMaxValue is not _UNSET:
                raise _ArgumentError("Specify only one of 'softMaxValue' and 'smx'")
            softMaxValue = smx
        if softMaxValue is not _UNSET:
            kwargs["softMaxValue"] = softMaxValue
        if smn is not _UNSET:
            if softMinValue is not _UNSET:
                raise _ArgumentError("Specify only one of 'softMinValue' and 'smn'")
            softMinValue = smn
        if softMinValue is not _UNSET:
            kwargs["softMinValue"] = softMinValue
        if s is not _UNSET:
            if storable is not _UNSET:
                raise _ArgumentError("Specify only one of 'storable' and 's'")
            storable = s
        if storable is not _UNSET:
            kwargs["storable"] = storable
        if uac is not _UNSET:
            if usedAsColor is not _UNSET:
                raise _ArgumentError("Specify only one of 'usedAsColor' and 'uac'")
            usedAsColor = uac
        if usedAsColor is not _UNSET:
            kwargs["usedAsColor"] = usedAsColor
        if uaf is not _UNSET:
            if usedAsFilename is not _UNSET:
                raise _ArgumentError("Specify only one of 'usedAsFilename' and 'uaf'")
            usedAsFilename = uaf
        if usedAsFilename is not _UNSET:
            kwargs["usedAsFilename"] = usedAsFilename
        if uap is not _UNSET:
            if usedAsProxy is not _UNSET:
                raise _ArgumentError("Specify only one of 'usedAsProxy' and 'uap'")
            usedAsProxy = uap
        if usedAsProxy is not _UNSET:
            kwargs["usedAsProxy"] = usedAsProxy
        if ws is not _UNSET:
            if worldSpace is not _UNSET:
                raise _ArgumentError("Specify only one of 'worldSpace' and 'ws'")
            worldSpace = ws
        if worldSpace is not _UNSET:
            kwargs["worldSpace"] = worldSpace
        if w is not _UNSET:
            if writable is not _UNSET:
                raise _ArgumentError("Specify only one of 'writable' and 'w'")
            writable = w
        if writable is not _UNSET:
            kwargs["writable"] = writable
        if cb is not _UNSET:
            if channelBox is not _UNSET:
                raise _ArgumentError("Specify only one of 'channelBox' and 'cb'")
            channelBox = cb
        if channelBox is _UNSET:
            channelBox = False
        if not isinstance(fast, bool):
            raise TypeError("fast must be a bool")
        with nullcontext() if fast else undoChunk("mlibNodeAddAttr"):
            from ..plugs.plug import Plug
            flags = {key: value for key, value in kwargs.items()
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
                type = proxy.getType()
                flags["usedAsProxy"] = True
            numeric, count, deferred = self._prepare_extra_attr_definition(
                flags, type, childNames, childShortNames, childSuffixes)
            prepared = self._create_extra_attr_definition(
                name, flags, numeric, count, deferred, childNames, childShortNames, childSuffixes, subType, fast=fast)
            if not getPlug and (deferred is None or count) and not show and proxy is None:
                return None
            plug = self.getPlug(name)
            if deferred is not None and not count:
                if fast and prepared is not None:
                    setter, value, owner = prepared
                    setter(plug.mplug(), value)
                else:
                    plug.set(deferred, fast=fast)
            if show:
                plug.setFlags(channelBox=True, fast=fast)
            if proxy is not None:
                proxy.connectTo(plug, fast=fast)
            return plug if getPlug else None

    def moveAttrOrder(self, name, offset):
        """ユーザー定義アトリビュートを Channel Box 上で前後に移動する。

        Maya にはアトリビュートの並び替え API が無いため、移動元と移動先のうち手前側の
        位置から末尾までのアトリビュートをまとめて削除し、新しい順序で再作成すること
        で実現する(移動先より後ろにある、移動と無関係なアトリビュートも再作成対象に
        含まれる。数値・enum・文字列型の非複合・非配列トップレベル動的アトリビュート
        のみ対応。対応しないアトリビュートが再作成対象に含まれる場合は何も変更せず
        例外を送出する)。

        並び替えが必要な場合はUndo有効を要求し、再作成中の失敗ではUndoによる復元を試みる。
        成功後は削除前に取得したPlug参照が無効になるため、必要なPlugを取得し直す。

        Args:
            name (str): 移動するユーザー定義アトリビュートのロング名。
            offset (int): 正の値で末尾方向、負の値で先頭方向へ移動する位置数。
                範囲を超える指定は先頭・末尾で止まる。

        Returns:
            Node: 自身。全変更を一回の Undo にまとめる。

        Raises:
            ValueError: name がトップレベルのユーザー定義アトリビュート一覧に無い場合。
            TypeError: 移動範囲に複合・配列アトリビュート、または対応しないアトリビュート型が
                含まれる場合。cmdsで再現できないnon-connectable定義も変更前に拒否する。
            RuntimeError: ノードが無効、または安全な復元に必要なUndoが無効な場合。
        """
        # aliasAttrが管理する内部の保存領域は、表示順の変更や再作成の対象にしない。
        names = [om2.MFnAttribute(attribute).name for attribute in self._user_attributes()]
        names = [name for name in names if name != "attributeAliasList"]
        if name not in names:
            raise ValueError(f"{name} is not a top-level user-defined attribute of {self.getFullName()}")
        old_index = names.index(name)
        new_index = max(0, min(len(names) - 1, old_index + offset))
        if new_index == old_index:
            return self
        if not cmds.undoInfo(query=True, state=True):
            raise RuntimeError("moveAttrOrder requires Undo to restore attributes after a failure")
        window_start = min(old_index, new_index)
        # Mayaの削除Undoは定義を末尾へ戻すため、元の並びの逆順に削除する。
        to_remove = list(reversed(names[window_start:]))
        names.remove(name)
        names.insert(new_index, name)
        to_recreate = names[window_start:]

        infos = [_dump_movable_attr(self.getPlug(attr_name)) for attr_name in to_recreate]
        aliases = [(alias, attr_name) for alias, attr_name in self._dependency_fn().getAliasList()
                   if attr_name in to_recreate]
        connections = {}
        for info in infos:
            endpoint = self, info["longName"]
            pairs = [(endpoint, destination) for destination in info["destinations"]]
            if info["source"] is not None:
                pairs.append((info["source"], endpoint))
            for source, destination in pairs:
                key = source[0].getUuid(), source[1], destination[0].getUuid(), destination[1]
                connections[key] = source, destination
        # 削除後は古いPlugを使わず、全定義を作ってから接続を再解決する。
        # 途中のMayaエラーでは、この処理のチャンクだけをUndoして元の状態へ戻す。
        with undoTransaction("mlibNodeMoveAttribute"):
            for alias, _ in aliases:
                cmds.aliasAttr(self.getFullName() + "." + alias, remove=True)
            for attr_name in to_remove:
                self.getPlug(attr_name).delete(force=True)
            for info in infos:
                _create_movable_attr(self, info)
            for alias, attr_name in aliases:
                self.getPlug(attr_name).setAlias(alias)
            for source, destination in connections.values():
                source[0].getPlug(source[1]).connectTo(destination[0].getPlug(destination[1]))
            for info in infos:
                plug = self.getPlug(info["longName"])
                if info["locked"]:
                    plug.setFlags(locked=True)
        return self

    def getPlug(self, name):
        """このノードのアトリビュートを、値の評価や要素作成なしで参照する。

        Args:
            name (str): ロング名・ショート名・エイリアス、またはノード名を除いたパス。
                配列要素と子を ``input3D[2].input3Dx`` のように指定できる。
                論理番号は0〜2147483647。

        Returns:
            Plug: 自身を所有Nodeとする、型に対応した新しいラッパー。
                未作成の配列要素も参照できる。genericは基底Plugで、値の型はget時に解釈する。

        Raises:
            ValueError: nameが空または文字列以外の場合。
            RuntimeError: ノードが無効、または ``input3Dx`` 等の未確定な論理番号を含む参照の場合。
            AttributeError: パスを解決できない、または論理番号が上限を超える場合。
        """
        # nodes/plugsの相互依存を避けるため遅延importする。
        from ..plugs.plug import MAX_LOGICAL_INDEX, Plug
        _InputPlug = Plug
        if not isinstance(name, str) or not name:
            raise ValueError("name には空でないアトリビュートパスを指定してください")
        if not self.isValid():
            raise RuntimeError("無効なノードのアトリビュートにはアクセスできません")

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
        """Mayaコマンドで保持インスタンスを指定できる最短一意名を取得する。

        DAGノードは保持パスのpartialPathName、DGノードはノード名を返す。
        名前はキャッシュせず、呼ぶたびにMayaへ問い合わせる。

        Returns:
            str: 現在の名前。ノード自体が無効なら空文字列。

        Raises:
            RuntimeError: ノードは有効だが保持するDAGインスタンスが削除された場合。
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

    def getFullName(self):
        """保持インスタンスの完全DAGパス、またはDGノード名を取得する。

        Returns:
            str: DAGではワールドから始まる完全パス。DGではノード名。
                ノード自体が無効なら空文字列。

        Raises:
            RuntimeError: ノードは有効だが保持するDAGインスタンスが削除された場合。
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

    @staticmethod
    def _create_node(node_type, flags, *, fast=False):
        """Mayaノードを作成し、実際のnodeTypeに対応するラッパーを返す(作成処理の唯一の実体)。

        :func:`mlib.createNode` と :meth:`Container.createNode` が呼ぶ内部ヘルパーで、Undoチャンクは
        呼出し側で管理する。Mayaが認識しない型名(標準プラグインのロード後も未知の型)を拒否する。
        cmds.createNodeは未知の型でも例外にせずunknownノードを作るため、ここで止める。型名の照会で
        認識できる名前は作成前に判定する。版の互換名(2027のaddDoubleLinear等)のように照会では
        分からない名前は、通常経路では作成した結果がunknownノードなら削除して拒否し(Undoの記録は
        作成と削除が対になる)、fastでは作成前に拒否する。

        Args:
            node_type (str): Maya nodeType名。
            flags (dict): createNodeへ渡す正規化済みのフラグ。parent/pを所有ノード名へ変換する。
            fast (bool): TrueならOpenMayaで作成し(Undoなし)、Falseならcmdsで作成する。

        Returns:
            Node: 作成(sharedでは共有)したノードの、実際のnodeTypeに対応するラッパー。
                登録表の規則で選んだクラス(登録型・動的クラス・Node)になる。

        Raises:
            ValueError: nodeType名が空文字列または文字列以外、またはparentが空文字列・無効な参照の場合。
            TypeError: parentが未対応型・複数対象の場合。
            RuntimeError: Mayaが認識しないnodeType名の場合、親名を解決できない場合、またはMayaが
                プラグインのロードやノード作成を拒否した場合。
            NotImplementedError: fastで未対応のフラグを指定した場合。
        """
        if not isinstance(node_type, str) or not node_type:
            raise ValueError("type must be a non-empty string")
        # 遅延公開の__getattr__を毎回通らないよう、実装モジュールから直接取得する。
        from ..common.plugin import Plugin
        Plugin.ensureNodePlugin(node_type)
        # Mayaの版で改名された型の旧名(2027のaddDoubleLinear→addDL等)は、型名の照会・OpenMayaでは
        # 解決できないがcmds.createNodeは互換名として作成する。照会で分からない名前は、通常経路では
        # 作成した結果がunknownノードかどうかで判定し、fastはOpenMayaが作成できないため作成前に拒否する。
        known = _node_type_exists(node_type)
        if not known and fast:
            raise RuntimeError("Unknown Maya nodeType: " + node_type)
        for key in ("parent", "p"):
            if flags.get(key) is not None:
                flags[key] = Node._input_name(flags[key])
        if fast:
            # nodeEditはNodeを参照するため、循環importを避けて関数内で読み込む。
            from ..core.nodeEdit import create_node
            obj = create_node(node_type, flags)
            # 作成したばかりの有効なMObjectなので、Node(obj)と同じ解決・型選択を入口の再判定なしで行う。
            return Node._wrap_resolved(*_resolve_node(obj))
        if known:
            created = cmds.createNode(node_type, **flags)
        else:
            unknown_types = ["unknown", "unknownDag", "unknownTransform"]
            existing = set(cmds.ls(type=unknown_types, uuid=True) or [])
            selection = cmds.ls(selection=True, long=True) or []
            created = cmds.createNode(node_type, **flags)
            if isinstance(created, str) and cmds.objExists(created):
                uuid = (cmds.ls(created, uuid=True) or [None])[0]
                if cmds.nodeType(created) in unknown_types and uuid not in existing:
                    # 未知の名前でMayaが作ったunknownノードは消し、作成前の選択へ戻してから拒否する。
                    cmds.delete(created)
                    cmds.select(selection, replace=True) if selection else cmds.select(clear=True)
                    raise RuntimeError("Unknown Maya nodeType: " + node_type)
        if created is None:
            # shared=Trueで同名・同型のノードが既にある場合、cmds.createNodeは作成せずNoneを返す。
            name = flags.get("name") or flags.get("n")
            if not name:
                raise RuntimeError("Maya did not create a node of type " + node_type)
            return Node(name)
        return Node(created)

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
    def _selection_owner(selection, index, name=None, plug=False):
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
            plug (bool): 要素がアトリビュート(``getPlug`` で取得できる要素)と分かっている場合は True。
                インスタンス化されていない DAG ノードはパスが1つだけなので、失敗すると分かっている
                ``getDagPath()`` の例外処理を省いてそのパスを返す(結果は False の場合と同じ)。

        Returns:
            tuple[om2.MObject, om2.MDagPath | None]: 所有ノードの MObject と、DAG ノードで
                あれば DAG パス(DG ノードは None)。
        """
        mobject = selection.getDependNode(index)
        if not mobject.hasFn(om2.MFn.kDagNode):
            return mobject, None
        fn = None
        if plug:
            fn = om2.MFnDagNode(mobject)
            if not fn.isInstanced():
                return mobject, fn.getPath()
        try:
            return mobject, selection.getDagPath(index)
        except (RuntimeError, TypeError):
            pass
        if fn is None:
            fn = om2.MFnDagNode(mobject)
        if fn.isInstanced():
            candidates = [name] if name else []
            candidates.extend(selection.getSelectionStrings(index))
            for text in candidates:
                # ノード名には "." を含められないため、最初の "." までがノード部分になる。
                owner = om2.MSelectionList()
                try:
                    owner.add(text.split(".", 1)[0])
                    dag_path = owner.getDagPath(0)
                except (RuntimeError, TypeError):
                    continue
                if dag_path.node() == mobject:
                    return mobject, dag_path
                # transform の名前でシェイプのアトリビュートを指す場合は、名前が指す transform の
                # インスタンスの下にある所有シェイプまでパスを伸ばす。
                for child in range(dag_path.childCount()):
                    if dag_path.child(child) == mobject:
                        dag_path.push(mobject)
                        return mobject, dag_path
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
            Node: value が Node ならそのまま、Plug なら ``plug.getNode()``、コンポーネントなら
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
        if isinstance(value, Node):
            return value
        if isinstance(value, str):
            # Node(value) と同じ解決・型選択を、生成の入口の再判定なしで行う。
            return Node._wrap_resolved(*_resolve_node(value))
        # 循環importを避け、入力型の判定に使う参照型をここで取得する(Node・名前の分岐では使わない)。
        from ..components.component import Component, Components
        from ..plugs.plug import Plug

        if isinstance(value, Plug):
            error = Plug._deleted_attribute_error(value)
            if error is not None:
                raise error
            return value.getNode()
        if isinstance(value, (Component, Components)):
            return value.shape
        if isinstance(value, (om2.MObject, om2.MDagPath, om2.MPlug)):
            return Node(value)
        raise Object._unsupported(value)

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
        # 型と有効性の検査は Object._input_name と同じ規則(TypeError / ValueError)にそろえる。
        Object._input_name(value)
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

    def _alive_fn(self):
        """破棄されていないことを確かめて、保持するノードの MFnDependencyNode を返す。

        Undo の記録から消えて破棄されたノード(削除後の flushUndo 等)へ関数セットを作ると
        Maya が異常終了するため、その前に RuntimeError にする。Undo で戻せる削除済みノード
        (生存中)は従来どおり問い合わせる。

        Returns:
            om2.MFnDependencyNode: このノードの関数セット。

        Raises:
            RuntimeError: ノードが破棄されている場合。
        """
        handle = self._handle
        if handle is None or not handle.isAlive():
            raise RuntimeError("Cannot access an invalid node")
        return om2.MFnDependencyNode(self._mobject)

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

    @staticmethod
    def _wrap_dag_path(dag_path):
        """呼出し元が作った有効なMDagPathを、名前や入力の再解決なしでラッパーにする。

        ``Node(dag_path)`` と同じ型選択(nodeTypeの登録、無ければMaya継承に沿って生成したクラス)と
        初期化を行い、入力の種類判定・MDagPathの複製だけを省く。パスが無効なら ``Node(dag_path)`` と
        同じ例外を送出する。子・親の列挙のように、API で直前に取得・延長・短縮したパスにだけ使う。

        Args:
            dag_path (om2.MDagPath): 有効なDAGパス。ラッパーがそのまま保持するため、
                呼出し元は以後このオブジェクトを変更しない。

        Returns:
            DagNode: 実際のノード型に対応するラッパー。
        """
        # アンダーワールドの根を指すパスなど、延長・短縮の結果が無効な場合は Node(...) と同じ例外にする。
        if not dag_path.isValid():
            return Node(dag_path)
        mobject = dag_path.node()
        handle = om2.MObjectHandle(mobject)
        if not handle.isValid():
            return Node(dag_path)
        # 有効性を確かめたハンドルは、ラッパーが保持するハンドルとしてそのまま使う。
        return Node._wrap_resolved(mobject, dag_path, handle)

    @staticmethod
    def _wrap_resolved(mobject, dag_path, handle=None):
        """API で直前に解決した有効な MObject と DAG パスを、入力の再解決なしでラッパーにする。

        ``Node(dag_path)``・``Node(mobject)`` と同じ型選択(nodeTypeの登録、無ければMaya継承に沿って生成したクラス)と
        初期化(選んだクラスの ``__init__``)を行い、入力の種類判定・有効性検査・複製だけを省く。
        ``_resolve_node`` の戻り値や、``MSelectionList``・``MItDag`` 等から取得したばかりの値にだけ使う。

        Args:
            mobject (om2.MObject): 有効な依存ノードの MObject。DAG ノードでは ``dag_path.node()`` と同じノード。
            dag_path (om2.MDagPath | None): DAG ノードの有効なパス。DG ノードは None。
                ラッパーがそのまま保持するため、呼出し元は以後これらのオブジェクトを変更しない。
            handle (om2.MObjectHandle | None): 呼出し元が mobject から作ったハンドル。指定すると
                ラッパーが保持するハンドルとして使い、作り直さない。

        Returns:
            Node: 実際のノード型に対応するラッパー。
        """
        registry = Node._registry
        if registry is None:
            return Node(dag_path if dag_path is not None else mobject)
        resolved_class = registry.wrapper_class(_node_type_name(mobject))
        instance = object.__new__(resolved_class)
        if resolved_class.__init__ is Node.__init__:
            # __init__ を上書きしないクラスでは、Node.__init__ の解決済み入力の分岐と同じ属性を直接設定する。
            instance._mobject = mobject
            instance._dag_path = dag_path
            if handle is None:
                handle = om2.MObjectHandle(mobject)
            instance._handle = handle
            instance._identity_hash = handle.hashCode()
            return instance
        instance._pending_resolution = (mobject, dag_path)
        instance.__init__(dag_path if dag_path is not None else mobject)
        return instance

    def _current_dag_path(self):
        """保持パスを返す。消失したインスタンスを別パスへ切り替えない。

        ノードごと削除された場合は、Undoの記録に残る間(MDagPathが有効のまま古いパスを返す間)も
        無効として扱う。

        Returns:
            om2.MDagPath | None: 保持しているパス。非DAGはNone。

        Raises:
            RuntimeError: 保持しているDAGインスタンス、またはノード自体が削除された場合。
        """
        dag_path = self._dag_path
        if dag_path is not None:
            if not dag_path.isValid():
                raise RuntimeError("The referenced DAG instance no longer exists")
            handle = self._handle
            if handle is not None and not handle.isValid():
                # 削除直後のMDagPathはisValid()がTrueのまま空のパス・削除前の名前を返すため、
                # ノードのハンドルでも確かめる。
                raise RuntimeError("The referenced DAG node no longer exists")
        return dag_path

    @staticmethod
    def _prepare_extra_attr_definition(flags, attribute_type, child_names, child_short_names, child_suffixes):
        """追加する型・子数・既定値と単位を、Mayaへの書込み前に解決する。

        Args:
            flags (dict): 正規化済みフラグ。型と単位をこの辞書へ反映する。
            attribute_type (str | None): 明示された型。
            child_names (Sequence[str] | None): 子のロング名。
            child_short_names (Sequence[str] | None): 子のショート名。
            child_suffixes (Sequence[str] | None): 子名の接尾辞。

        Returns:
            tuple: 数値複合型の一致情報・子数・作成後に設定する既定値。
        """
        if attribute_type is not None:
            flags.pop("attributeType", None)
            flags.pop("dataType", None)
            prefix, separator, kind = attribute_type.partition(":")
            if separator:
                if prefix not in ("at", "dt"):
                    raise ValueError("Expected at: or dt: type prefix")
                key = "attributeType" if prefix == "at" else "dataType"
            else:
                kind = attribute_type
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
        if kind == "compound" and (child_names or child_short_names or child_suffixes):
            count = flags.get("numberOfChildren") or len(child_names or child_short_names or child_suffixes)
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
        return numeric, count, deferred

    def _create_extra_attr_definition(self, name, flags, numeric, count, deferred,
                                      child_names, child_short_names, child_suffixes, sub_type, *, fast=False):
        """親と子の定義を従来の順序で追加する。

        通常は子を公開addAttrへ順に委譲する。fastは未登録の親子定義を一括構築して追加する。

        Args:
            name (str): 親アトリビュート名。
            flags (dict): 親へ渡すフラグ。子用の範囲値を取り出す。
            numeric (object): 数値複合型の一致情報。
            count (int): 子数。
            deferred (object): 子に渡す既定値。
            child_names (Sequence[str] | None): 子のロング名。
            child_short_names (Sequence[str] | None): 子のショート名。
            child_suffixes (Sequence[str] | None): 子名の接尾辞。
            sub_type (str | None): 子の型。
            fast (bool): Trueなら定義をOpenMayaで追加する。
        """
        from ..core.attributeEdit import extra_children, validate_extra_attribute
        children = extra_children(name, flags, numeric, count, deferred, child_names,
                                  child_short_names, child_suffixes, sub_type)
        validate_extra_attribute(self, name, flags, count, deferred, children,
                                 validate_defaults=not fast)
        if fast:
            from ..core.attributeEdit import create_extra_attribute
            return create_extra_attribute(self, name, flags, numeric, count, deferred,
                                          child_names, child_short_names, child_suffixes, sub_type)
        if count:
            # 子の範囲・既定値は子へ指定し、親には渡さない。
            for key in ("minValue", "maxValue", "softMinValue", "softMaxValue"):
                flags.pop(key, None)
            cmds.addAttr(self.getFullName(), **flags)
            for child_name, child_type, child_flags in children:
                self.addAttr(child_name, child_type, getPlug=False, fast=fast, **child_flags)
        else:
            cmds.addAttr(self.getFullName(), **flags)

    def _listed_attributes(self, include_children=True, keyable=False, scalar=False):
        """``cmds.listAttr`` と同じ順で、getPlugs() が返すアトリビュート定義を列挙する。

        トップレベルの定義を定義順に辿り、配列でない複合は子を親の直後へ深さ優先で並べる
        (配列の複合の子は、番号の無い名前を Plug にできないため listAttr の結果からも除かれる)。

        Args:
            include_children (bool): Falseならトップレベルの定義だけを返す。
            keyable (bool): Trueならプラグがkeyableのものだけ(``listAttr(keyable=True)``)。
            scalar (bool): Trueなら単一成分の数値・単位・enumだけ(``listAttr(scalar=True)``)。

        Returns:
            list[om2.MObject]: アトリビュート定義。配列要素の取得・作成は行わない。
        """
        fn = self._dependency_fn()
        ordered = []

        def visit(attribute):
            """定義を追加し、配列でない複合なら子を続けて追加する。"""
            ordered.append(attribute)
            if (include_children and attribute.hasFn(om2.MFn.kCompoundAttribute)
                    and not om2.MFnAttribute(attribute).array):
                compound = om2.MFnCompoundAttribute(attribute)
                for index in range(compound.numChildren()):
                    visit(compound.child(index))

        for index in range(fn.attributeCount()):
            attribute = fn.attribute(index)
            if om2.MFnAttribute(attribute).parent.isNull():
                visit(attribute)
        if keyable:
            # 定義でなくプラグのkeyable(Shapeのvisibility等はノードが上書きする)で判定する。
            ordered = [attribute for attribute in ordered if om2.MPlug(self._mobject, attribute).isKeyable]
        if scalar:
            ordered = [attribute for attribute in ordered if _scalar_attribute(attribute)]
        return ordered

    def _user_attributes(self, include_children=False):
        """動的アトリビュートの定義を追加順に列挙する。

        Args:
            include_children (bool): Trueなら複合型の子の定義も含める。

        Yields:
            om2.MObject: アトリビュート定義。配列要素の取得・作成は行わない。
        """
        fn = self._dependency_fn()
        # 静的・拡張アトリビュートはattributeClassで先に除き、MFnAttributeの作成を動的なものだけにする。
        # kLocalDynamicAttrはMFnAttribute.dynamicがTrueのものと同じで、列挙の順序も変えない。
        local_dynamic = om2.MFnDependencyNode.kLocalDynamicAttr
        for index in range(fn.attributeCount()):
            attribute = fn.attribute(index)
            if fn.attributeClass(attribute) != local_dynamic:
                continue
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

    # 基底Nodes.callEachや利用側の同名メソッドにも適用する結果収集方針。
    _calculating_setters = frozenset((
        "setTranslate", "setRotate", "setQuaternion", "setScale", "setShear",
        "setMatrix", "setTransformation",
    ))

    # 単数の呼出し先と返却方針を同じ行で宣言し、追加漏れを防ぐ。
    _bulk_entries = {
        "getShadingEngines": (Node.getShadingEngines, "list"),
        "sameNode": (Node.sameNode, "list"),
        "isValid": (Node.isValid, "list"),
        "isAlive": (Node.isAlive, "list"),
        "mnode": (Node.mnode, "list"),
        "mfn": (Node.mfn, "list"),
        "getType": (Node.getType, "list"),
        "getTypeId": (Node.getTypeId, "list"),
        "getPluginName": (Node.getPluginName, "list"),
        "getClassification": (Node.getClassification, "list"),
        "isType": (Node.isType, "list"),
        "hasFn": (Node.hasFn, "list"),
        "isLocked": (Node.isLocked, "list"),
        "isFromReferencedFile": (Node.isFromReferencedFile, "list"),
        "isAncestorOf": (Node.isAncestorOf, "list"),
        "isParentOf": (Node.isParentOf, "list"),
        "isRoot": (Node.isRoot, "list"),
        "getNodeName": (Node.getNodeName, "list"),
        "getNamespace": (Node.getNamespace, "list"),
        "rename": (Node.rename, "list"),
        "getConnections": (Node.getConnections, "list"),
        "getHistory": (Node.getHistory, "list"),
        "resetAttrs": (Node.resetAttrs, "list"),
        "getPlugs": (Node.getPlugs, "list"),
        "getAliases": (Node.getAliases, "list"),
        "addAttr": (Node.addAttr, "list"),
        "getPlug": (Node.getPlug, "list"),
        "hasAttr": (Node.hasAttr, "list"),
        "getUuid": (Node.getUuid, "list"),
        "getName": (Node.getName, "list"),
        "getFullName": (Node.getFullName, "list"),
        "delete": (Node.delete, "self"),
        "setNamespace": (Node.setNamespace, "self"),
        "setAttrFlags": (Node.setAttrFlags, "self"),
        "setLocked": (Node.setLocked, "self"),
        "moveAttrOrder": (Node.moveAttrOrder, "self"),
    }
    _bulk_methods = {
        **{name: entry[0] for name, entry in _bulk_entries.items()},
    }
    _bulk_returns = {
        **{name: entry[1] for name, entry in _bulk_entries.items()},
    }
    _bulk_per_item_only = frozenset()
    _bulk_undo = True

    def __init__(self, names=()):
        """入力からノード参照を解決し、要素型を検証して保持する。

        Args:
            names (object | Iterable[object]): 名前・Node・API参照等、またはその列。単一名も受理する。

        Raises:
            TypeError: 解決結果がitem_classの派生でない場合。
            RuntimeError: 名前を解決できない、または無効なノードの場合。
            ValueError: 入力解決で不正な参照を検出した場合。
        """
        if isinstance(names, (str, Node)):
            names = [names]
        else:
            try:
                names = iter(names)
            except TypeError:
                names = [names]
        names = Nodes._resolve_inputs(names)
        # 重複の判定は (UUID, 完全パス) の一致で行う(構築時だけ使用。以後の改名・親変更はNode参照が追跡する)。
        # 同じノードはハンドルのハッシュが等しいため、ハッシュごとに分けて、同じハッシュの要素が
        # 既にある場合だけキーを求めて比べる。完全パスの取得は階層の深さに比例して重いため、
        # 重複の無い要素では求めない。キーが一致する組は必ず同じハッシュなので結果は変わらない。
        items, buckets = [], {}
        for value in names:
            node = Node._resolve_input(value)
            if not node.isValid():
                raise RuntimeError("Cannot collect an invalid node")
            if not isinstance(node, self.item_class):
                raise TypeError(f"{type(self).__name__} requires {self.item_class.__name__}, got {type(node).__name__}")
            # 保持インスタンスが削除されたDAG参照は、キーを求めた場合と同じRuntimeErrorにする。
            node._current_dag_path()
            bucket = buckets.get(node._identity_hash)
            if bucket is None:
                buckets[node._identity_hash] = [[node, None]]
                items.append(node)
                continue
            key = Nodes._duplicate_key(node)
            for entry in bucket:
                if entry[1] is None:
                    entry[1] = Nodes._duplicate_key(entry[0])
                if entry[1] == key:
                    break
            else:
                bucket.append([node, key])
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
        """保持列の位置からNode参照、sliceから同型の部分コレクションを取得する。

        取得したNodeは元と同じ参照。シーンの実番号による検索や有効性の再検査は行わず、
        構築後に削除された参照も保持する。

        Args:
            index (int | slice): Pythonリストの添字。負数とboolも同じ規則で扱う。

        Returns:
            Node | Nodes: 同じNode参照、または参照を共有する新しい容器。
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

    def mfn(self, *args, **kwargs):
        """各要素のmfnを同じ引数で呼び、保持順の戻り値リストを返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            list: 保持順の戻り値リスト。
        """
        return self._dispatch_shared("mfn", args, kwargs)

    mfn.__signature__ = inspect.signature(Node.mfn)

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

    def hasFn(self, *args, **kwargs):
        """各要素のhasFnを同じ引数で呼び、保持順の戻り値リストを返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            list: 保持順の戻り値リスト。
        """
        return self._dispatch_shared("hasFn", args, kwargs)

    hasFn.__signature__ = inspect.signature(Node.hasFn)

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

    def setLocked(self, *args, **kwargs):
        """各要素のsetLockedを同じ引数で呼び、コレクション自身を返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            Nodes | list: コレクション自身。
        """
        return self._dispatch_shared("setLocked", args, kwargs)

    setLocked.__signature__ = inspect.signature(Node.setLocked)

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

    def callEach(self, method, arguments, keywordArguments=None):
        """各ノードの公開メソッドを、要素別の引数で保持順に呼ぶ。

        呼出形式は全件、fastのbool型はfast引数を持つ呼出先について実行前に検査する。長短名の組合せ・省略値・その他の値は
        単数メソッド内で順に検査し、後続が失敗しても先行変更は自動で戻さない。
        通常・混在呼出しのUndo対象操作は一つのチャンクへまとめ、全件fastは記録しない。

        Args:
            method (str): setTranslate等の登録済み単数メソッド。create・特殊メソッドは不可。
            arguments (Iterable[tuple]): 要素数と同数の位置引数tuple。
            keywordArguments (Iterable[dict] | None): 要素別キーワード引数。省略時は空辞書。

        Returns:
            list | Nodes: 照会・結果を返す操作は保持順のリスト、更新は自身。入れ子のリストも保持する。

        Raises:
            ValueError: メソッド名または件数が不正な場合。
            TypeError: 呼出形式・fast型が不正、または単数メソッドで長短名の競合等を検出した場合。
            RuntimeError: 単数メソッドのその他の失敗。対象番号を含み、後続は実行しない。
        """
        functions, args, kwargs = self._prepare_calls(method, arguments, keywordArguments)
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

    def delete(self, *, safe=False, fast=False):
        """全ノードを1回の削除にまとめて削除する。

        通常は1回の ``cmds.delete``、fastは1つの MDagModifier の doIt 1回で削除する。
        削除の順・連鎖して消えるノードはMayaがまとめて削除するときの規則に従い、
        親子の両方・重複を含めてもよい(親と一緒に消えた子は重ねて削除しない)。
        削除の前に全対象とDAG子孫を検査し、ロック・参照・削除できないノード(既定・共有ノード等)が
        あれば何も削除せずRuntimeErrorにする(検査は :meth:`Node.delete` と同じ)。
        専用のdeleteを上書きした派生クラスの要素を含む場合だけ、従来どおり各ノードのdeleteを
        順に呼び、親削除で消えた後続対象はスキップする。

        Args:
            safe (bool): TrueならDG接続を持つ対象(自身またはDAG子孫)を残す。
            fast (bool): TrueはOpenMaya直接更新でUndoなし。既定FalseはMaya標準コマンドを使用する。

        Returns:
            None: 空なら何もしない。Jointsも同じMaya標準削除を継承する。

        Raises:
            TypeError: safeがboolでない場合。
            RuntimeError: 実行前に削除済みの参照がある(``invalid item <番号>``)、または
                削除できない対象を含む(``failed at item <番号>: <理由>``。何も削除しない)。
                全体は一回のUndoで戻せる。
        """
        if not isinstance(fast, bool):
            raise TypeError("fast must be a bool")
        with nullcontext() if fast else undoChunk("mlibNodesDelete"):
            if type(safe) is not bool:
                raise TypeError("safe must be bool")
            for index, node in enumerate(self):
                if not node.isValid():
                    raise RuntimeError(f"{type(self).__name__}.delete invalid item {index}")
            from ..core.nodeEdit import check_deletion, delete_nodes
            batch = all(type(node).delete is Node.delete for node in self)
            if batch or fast:
                indices = [index for index, node in enumerate(self)
                           if not (safe and node._has_delete_connections())]
                if batch and not indices:
                    return
                try:
                    if batch:
                        delete_nodes([self._items[index] for index in indices], fast=fast)
                    else:
                        # 専用deleteを持つ要素を含むfastは、従来どおり各deleteの前に全体を検査する。
                        check_deletion([self._items[index] for index in indices], fast=True)
                except RuntimeError as exc:
                    if not hasattr(exc, "index"):
                        raise
                    raise RuntimeError(f"{type(self).__name__}.delete failed at item "
                                       f"{indices[exc.index]}: {exc}") from exc
                if batch:
                    return
            for index, node in enumerate(self):
                if node.isValid():
                    try:
                        node.delete(safe=safe, fast=fast)
                    except Exception as exc:
                        raise RuntimeError(f"{type(self).__name__}.delete failed at item {index}: {exc}") from exc

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
    def _duplicate_key(node):
        """構築時の重複判定に使うキーを返す。

        Args:
            node (Node): 有効なノード参照。

        Returns:
            tuple[str | None, str]: UUIDと、DAGの完全パスまたはDGのノード名。
        """
        return (node.getUuid(), node.getFullName())

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

    @staticmethod
    def _calculation_results(method, functions, args, kwargs, bindings=None):
        """get指定で計算値を返すsetterについて結果列が必要か判定する。

        Args:
            method (str): 一括実行するメソッド名。
            functions (Sequence[callable]): 実際の呼出し先。
            args (Sequence[tuple]): 要素別の位置引数。
            kwargs (Sequence[dict]): 要素別のキーワード引数。
            bindings (Sequence[inspect.BoundArguments | None] | None): 同じ呼出し内で
                束縛済みの引数。Noneの要素と省略時はここで束縛する。

        Returns:
            bool: 少なくとも一つの対象がget指定で計算値を返す場合True。
        """
        if method not in Nodes._calculating_setters:
            return False
        if bindings is None:
            bindings = [None] * len(functions)
        return any((bound if bound is not None else inspect.signature(fn).bind(*row, **flags))
                   .arguments.get("get", False)
                   for fn, row, flags, bound in zip(functions, args, kwargs, bindings))

    def _execute_calls(self, method, functions, args, kwargs):
        """検証済み呼出しを実行し、更新操作では不要な結果配列を作らない。

        Args:
            method: 一括実行するメソッド名。
            functions: 要素ごとに解決済みの呼出し先関数。
            args: 処理先へ渡す位置引数の列。
            kwargs: 処理先へ渡すキーワード引数の辞書。
        """
        fast_values = []
        bindings = []
        # signatureは同じ実メソッドで、束縛結果は同じ引数オブジェクトの組でこの呼出し内だけ共有する。
        # 一括の共有呼出しでは全要素が同じ位置引数tuple・同じキーワード辞書を受け取るため、
        # 要素ごとのinspect.signature/bindを省ける。呼出し後はどちらも保持しない。
        signatures = {}
        bound_cache = {}
        for function, row, flags in zip(functions, args, kwargs):
            signature = self._signature(function, signatures)
            parameter = signature.parameters.get("fast")
            if parameter is None:
                fast_values.append(False)
                bindings.append(None)
                continue
            key = (function.__func__ if inspect.ismethod(function) else None, id(row), id(flags))
            bound = bound_cache.get(key) if key[0] is not None else None
            if bound is None:
                bound = signature.bind(*row, **flags)
                if key[0] is not None:
                    bound_cache[key] = bound
            requested = bound.arguments.get("fast", parameter.default)
            if not isinstance(requested, bool):
                raise TypeError("fast must be a bool")
            fast_values.append(requested)
            bindings.append(bound)
        all_fast = bool(fast_values) and all(fast_values)
        # 全件fastの直接更新ではチャンクを作らず、通常・混在・空列は既存のUndo方針に従う。
        if self._bulk_undo and not all_fast:
            context = undoChunk("mlibBulk_" + method)
        else:
            context = contextlib.nullcontext()
        calculating = self._calculation_results(method, functions, args, kwargs, bindings)
        result = [] if calculating or self._bulk_returns[method] != "self" else None
        with context:
            for index, (function, row, flags) in enumerate(zip(functions, args, kwargs)):
                try:
                    value = function(*row, **flags)
                    if result is not None:
                        result.append(value)
                except _ArgumentError as exc:
                    raise _ArgumentError(f"{type(self).__name__}.{method} failed at item {index}: {exc}") from exc
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
        """同じ引数の呼出形式を関数ごとに検証し、保持順に実行する。

        共有はこの呼出し内だけに限定する。派生overrideと個体callableは別に検証し、
        クラス差替え・reload後の古いメソッドを保持しない。fast型を除く値の検証は各単数本文で行う。

        Args:
            method: 登録済みの単数メソッド名。
            args: 全要素に渡す位置引数。
            kwargs: 全要素に渡すキーワード引数。
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
                flags = dict(kwargs)
                self._signature(function, signatures).bind(*args, **flags)
                if key is not None:
                    shared[key] = flags
            keywords.append(flags)
        return self._execute_calls(method, functions, [args] * len(functions), keywords)

    def _prepare_calls(self, method, arguments, keyword_arguments):
        """全要素の呼出形式を実行前に解決・検証する。

        Args:
            method (str): 登録済みの単体メソッド名。
            arguments (Iterable[tuple]): 要素別の位置引数。
            keyword_arguments (Iterable[dict] | None): 要素別のキーワード引数。

        Returns:
            tuple: 呼出先・位置引数・キーワード引数の各リスト。

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
        kwargs = [dict(flags) for flags in kwargs]
        # この呼出内だけ共有し、reloadやクラスの差替え後に古いsignatureを保持しない。
        signatures = {}
        # 長短の組合せ・省略判定・値の妥当性は、各メソッド本文が保持順で検査する。
        for function, row, flags in zip(functions, args, kwargs):
            self._signature(function, signatures).bind(*row, **flags)
        return functions, args, kwargs

    @staticmethod
    def _call_target(item, method):
        """保持中の単数参照から、現在の公開メソッドを解決する。

        Args:
            item (Node): 呼出し先の単数参照。
            method (str): 管理表に登録した公開メソッド名。

        Returns:
            callable: 派生override・個体差替えを反映した実際の呼出し先。
        """
        return getattr(item, method)

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
